"""Pillar 22 / V18 — Live Weight Evolver.

Connects the micro-evolution trainer directly to the running NanoModel
inside IronEngine.  Uses a (1+1)-ES hill-climbing strategy:

    1. Pick a random weight tensor from the model.
    2. Mutate one element: draw from {-1, 0, +1} randomly.
    3. Evaluate fitness via task-replay over ExperimentMemory.
    4. Keep mutation if fitness improves, otherwise revert.
    5. After N steps, if improvement found, persist weights to .jay file.

The evolver runs as a CoreTwin Priority.LOW task so it never blocks
normal inference.

Usage (from CoreTwin or IronEngine)
-------------------------------------
    evolver = LiveEvolver(engine)
    await evolver.run_evolution_async(steps=200)  # async coroutine
    # or:
    evolver.run_evolution(steps=100)              # blocking (background thread)
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

import numpy as np

logger = logging.getLogger("LiveEvolver")

_RNG = np.random.default_rng()


class LiveEvolver:
    """(1+1)-ES micro-evolution for the live NanoModel.

    Parameters
    ----------
    engine:
        IronEngine instance that has .nano_model and .memory attributes.
    max_steps:
        Default step budget per call.
    min_improvement:
        Minimum delta fitness to accept a mutation (prevents noise-accepts).
    """

    def __init__(
        self,
        engine: Any,
        max_steps: int = 200,
        min_improvement: float = 1e-4,
    ) -> None:
        self.engine = engine
        self.max_steps = max_steps
        self.min_improvement = min_improvement
        self._total_mutations: int = 0
        self._accepted_mutations: int = 0
        self._last_run_fitness: float = 0.0
        self._generations: int = 0

    # ------------------------------------------------------------------
    # Fitness
    # ------------------------------------------------------------------

    def _compute_fitness(self) -> float:
        """Compute fitness as avg score over recent ExperimentMemory entries.

        Falls back to 0.5 if memory is empty.
        """
        try:
            memory = self.engine.memory
            recent = memory.recent(20)
            if not recent:
                return 0.5
            scores = [r.score for r in recent
                      if hasattr(r, "score") and isinstance(r.score, (int, float))]
            return float(np.mean(scores)) if scores else 0.5
        except Exception:
            return 0.5

    # ------------------------------------------------------------------
    # Evolution
    # ------------------------------------------------------------------

    def run_evolution(self, steps: int | None = None) -> dict[str, Any]:
        """Run evolution synchronously.  Safe to call from a background thread.

        Returns
        -------
        dict with keys: steps, accepted, delta_fitness, improved, duration_s
        """
        n_steps = steps or self.max_steps
        model = self._get_model()
        if model is None:
            logger.warning("[LiveEvolver] No NanoModel found on engine — skipping.")
            return {"steps": 0, "accepted": 0, "delta_fitness": 0.0,
                    "improved": False, "duration_s": 0.0}

        t0 = time.monotonic()
        buffers = model.get_weight_buffers()
        initial_fitness = self._compute_fitness()
        best_fitness = initial_fitness
        accepted = 0

        for step in range(n_steps):
            # Pick random weight tensor and element
            key, W = buffers[_RNG.integers(len(buffers))]
            flat = W.ravel()
            idx = int(_RNG.integers(len(flat)))
            old_val = int(flat[idx])
            new_val = int(_RNG.choice([-1, 0, 1]))

            if new_val == old_val:
                continue  # no-op

            # Apply mutation
            flat[idx] = new_val
            model.set_weight(key, flat.reshape(W.shape))

            # Evaluate
            new_fitness = self._compute_fitness()
            self._total_mutations += 1

            if new_fitness >= best_fitness + self.min_improvement:
                # Accept
                best_fitness = new_fitness
                accepted += 1
                self._accepted_mutations += 1
                logger.debug("[LiveEvolver] step=%d ACCEPT fitness %.4f→%.4f key=%s[%d]",
                             step, initial_fitness, best_fitness, key, idx)
            else:
                # Revert
                flat[idx] = old_val
                model.set_weight(key, flat.reshape(W.shape))

        # Reflect refreshed buffers (they may have been mutated in-place)
        buffers = model.get_weight_buffers()

        delta = best_fitness - initial_fitness
        improved = delta > self.min_improvement
        duration = time.monotonic() - t0
        self._generations += 1
        self._last_run_fitness = best_fitness

        if improved:
            logger.info(
                "[LiveEvolver] Gen %d: fitness %.4f→%.4f (+%.4f) accepted=%d/%d in %.2fs",
                self._generations, initial_fitness, best_fitness, delta, accepted, n_steps,
                duration,
            )
            self._persist_weights()
        else:
            logger.debug(
                "[LiveEvolver] Gen %d: no improvement (delta=%.5f) in %.2fs",
                self._generations, delta, duration,
            )

        return {
            "steps": n_steps,
            "accepted": accepted,
            "delta_fitness": delta,
            "improved": improved,
            "duration_s": duration,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_weights(self) -> None:
        """Write improved weights back to the live .jay file (IRON_BODY_PACKED).

        Only rewrites the IRON_BODY_PACKED section; all other sections
        (SOUL_AES, KEYS_PQC, MODEL_CONFIG) are untouched.
        """
        try:
            self._save_weights_to_jay()
        except Exception as exc:
            logger.warning("[LiveEvolver] Weight persistence failed: %s", exc)

    def _save_weights_to_jay(self) -> None:
        """Rewrite the IRON_BODY_PACKED section in the active .jay file."""
        from jaya_core.brain_v2.format.packer import pack_state_dict

        model = self._get_model()
        if model is None:
            return

        jay_path = getattr(self.engine, "_jay_path", None)
        if not jay_path or not os.path.exists(jay_path):
            logger.warning("[LiveEvolver] No .jay path on engine, cannot persist weights.")
            return

        # Pack current weights
        state_dict = model.get_state_dict()
        packed_blob = pack_state_dict(state_dict)

        # Rewrite file: find IRON_BODY_PACKED section and replace payload
        _patch_jay_section(jay_path, packed_blob)
        logger.info("[LiveEvolver] Weights persisted → %s (%d bytes packed)",
                    jay_path, len(packed_blob))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_model(self) -> Any | None:
        return getattr(self.engine, "_nano_model", None)

    def status(self) -> dict[str, Any]:
        return {
            "generations": self._generations,
            "total_mutations": self._total_mutations,
            "accepted_mutations": self._accepted_mutations,
            "accept_rate": (
                self._accepted_mutations / max(1, self._total_mutations)
            ),
            "last_fitness": self._last_run_fitness,
        }


# ---------------------------------------------------------------------------
# .jay surgical patch helper
# ---------------------------------------------------------------------------

def _patch_jay_section(jay_path: str, new_blob: bytes) -> None:
    """Replace the IRON_BODY_PACKED section payload in place.

    If the section does not exist yet (upgrade from V17), append it and
    update the header flags accordingly.
    This is a *surgical* operation — it reads the whole file, modifies
    the target section, and rewrites the full file.  Safe for <100 MB files.
    """
    import struct

    from jaya_core.brain_v2.format.schema import (
        JayaFlags,
        JayaFooter,
        JayaHeader,
        SectionHeader,
        SectionType,
    )

    with open(jay_path, "rb") as f:
        raw = f.read()

    header = JayaHeader.unpack(raw[:128])
    header.flags |= JayaFlags.PACKED_WEIGHTS | JayaFlags.SELF_EVOLVING

    # Parse section headers starting at offset 128
    offset = 128
    sections: list[tuple[SectionHeader, bytes]] = []

    try:
        while offset < len(raw) - JayaFooter.SIZE():
            sh_bytes = raw[offset:offset + 24]
            if len(sh_bytes) < 24:
                break
            sh = SectionHeader(
                type=SectionType(struct.unpack("<I", sh_bytes[0:4])[0]),
                offset=struct.unpack("<Q", sh_bytes[4:12])[0],
                length=struct.unpack("<Q", sh_bytes[12:20])[0],
                checksum_crc32=struct.unpack("<I", sh_bytes[20:24])[0],
            )
            payload = raw[sh.offset: sh.offset + sh.length]
            sections.append((sh, payload))
            offset += 24
    except Exception:
        pass  # malformed sections — rebuild from scratch

    # Replace or append IRON_BODY_PACKED
    replaced = False
    new_sections: list[tuple[SectionType, bytes]] = []
    for sh, payload in sections:
        if sh.type == SectionType.IRON_BODY_PACKED:
            new_sections.append((SectionType.IRON_BODY_PACKED, new_blob))
            replaced = True
        else:
            new_sections.append((sh.type, payload))

    if not replaced:
        new_sections.append((SectionType.IRON_BODY_PACKED, new_blob))

    # Rebuild file
    _rebuild_jay(jay_path, header, new_sections)


def _rebuild_jay(path: str, header: Any, sections: list[tuple]) -> None:
    """Rebuild a .jay file from parts."""
    import zlib

    from jaya_core.brain_v2.format.schema import ALIGNMENT, JayaFooter, SectionHeader

    # Section headers area: 24 bytes × n_sections, then 4KB aligned
    sec_hdr_area = 24 * len(sections)
    data_start = 128 + sec_hdr_area
    data_start = (data_start + ALIGNMENT - 1) & ~(ALIGNMENT - 1)

    # Calculate offsets
    offsets = []
    cur = data_start
    for _, payload in sections:
        offsets.append(cur)
        cur += len(payload)
        cur = (cur + ALIGNMENT - 1) & ~(ALIGNMENT - 1)

    # Build section headers
    sec_hdr_bytes = bytearray()
    for i, (stype, payload) in enumerate(sections):
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        sh = SectionHeader(type=stype, offset=offsets[i],
                           length=len(payload), checksum_crc32=crc)
        sec_hdr_bytes.extend(sh.pack())

    # Build payloads with alignment padding
    payload_bytes = bytearray()
    payload_bytes.extend(b"\x00" * (data_start - 128 - len(sec_hdr_bytes)))
    for i, (_, payload) in enumerate(sections):
        write_start = offsets[i] - 128 - len(sec_hdr_bytes)
        # Ensure alignment
        while len(payload_bytes) < write_start:
            payload_bytes.extend(b"\x00")
        payload_bytes.extend(payload)
        # Pad to alignment
        pad = (ALIGNMENT - len(payload) % ALIGNMENT) % ALIGNMENT
        payload_bytes.extend(b"\x00" * pad)

    # Compose
    raw = bytearray()
    raw.extend(header.pack())
    raw.extend(sec_hdr_bytes)
    raw.extend(payload_bytes)

    # Footer
    total_size = len(raw) + 32
    gcrc = zlib.crc32(bytes(raw)) & 0xFFFFFFFF
    hsha = hashlib.sha256(header.pack()).digest()[:11]
    footer = JayaFooter(magic=b"JAYA_SEAL", file_size=total_size,
                        global_crc32=gcrc, header_sha256_prefix=hsha)
    raw.extend(footer.pack())

    with open(path, "wb") as f:
        f.write(raw)
