"""Pillar 24 — fail-closed Morphic Kernel.

Candidate source is validated in an isolated worker. The live runtime never
executes candidate Python. Only explicitly supported safe function specs are
translated into Core-owned callables.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import marshal
import threading
import time
import types
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.brain_v2.engine.evolution_sandbox import EvolutionSandbox

if TYPE_CHECKING:
    from src.brain_v2.extensions.twin.experiment_memory import ExperimentMemory
    from src.brain_v2.soul.ethical_heart import EthicalHeart

logger = logging.getLogger("MorphicKernel")

_FORBIDDEN_TARGETS = frozenset(
    {
        "__init__",
        "__del__",
        "__class__",
        "__builtins__",
        "ignite",
        "dna_anchor",
        "apply_feedback",
    }
)
_MISSING = object()


def _stable_value(value: Any) -> bytes:
    try:
        serialized = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        serialized = f"{type(value).__module__}.{type(value).__qualname__}"
    return serialized.encode("utf-8")


def _callable_digest(value: Any) -> str:
    """Return a deterministic digest for an effective callable."""

    function = getattr(value, "__func__", value)
    digest = hashlib.sha256()
    digest.update(
        f"{getattr(function, '__module__', '')}:"
        f"{getattr(function, '__qualname__', type(function).__qualname__)}".encode(
            "utf-8"
        )
    )
    code = getattr(function, "__code__", None)
    if code is not None:
        digest.update(marshal.dumps(code))
    digest.update(_stable_value(getattr(function, "__defaults__", None)))
    digest.update(_stable_value(getattr(function, "__kwdefaults__", None)))
    closure = getattr(function, "__closure__", None) or ()
    for cell in closure:
        try:
            digest.update(_stable_value(cell.cell_contents))
        except ValueError:
            digest.update(b"<empty-cell>")
    return digest.hexdigest()


def _constant_method(name: str, value: Any) -> Any:
    frozen_value = copy.deepcopy(value)

    def safe_method(_self: Any, *_args: Any, **_kwargs: Any) -> Any:
        return copy.deepcopy(frozen_value)

    safe_method.__name__ = name
    safe_method.__qualname__ = f"MorphicSafePatch.{name}"
    return safe_method


@dataclass
class PatchRecord:
    name: str
    target_obj: Any
    original_instance_value: Any
    had_instance_value: bool
    baseline_digest: str
    patched_digest: str
    candidate_digest: str
    timestamp: float


class MorphicKernel:
    """Apply allowlisted patch specs and restore digest-verified baselines."""

    def __init__(
        self,
        ethical_heart: Optional["EthicalHeart"] = None,
        memory: Optional["ExperimentMemory"] = None,
        sandbox: Optional[EvolutionSandbox] = None,
    ) -> None:
        self._ethical_heart = ethical_heart
        self._memory = memory
        self._sandbox = sandbox if sandbox is not None else EvolutionSandbox()
        self._patches: List[PatchRecord] = []
        self._patch_count = 0
        self._reject_count = 0
        self._lock = threading.RLock()
        self._last_rollback: Dict[str, Any] = {
            "ok": True,
            "restored": 0,
            "failures": [],
        }

    def patch(
        self,
        target_obj: Any,
        method_name: str,
        new_code: str,
        namespace: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Apply a worker-validated safe function specification.

        The current safe API accepts exactly one function that returns a
        JSON-compatible literal. Imports, attribute access, loops, calls, and
        arbitrary namespace injection are rejected.
        """

        if (
            not isinstance(method_name, str)
            or not method_name.isidentifier()
            or method_name.startswith("__")
            or method_name in _FORBIDDEN_TARGETS
        ):
            return self._reject(f"protected or invalid target: {method_name!r}")
        if namespace:
            return self._reject("runtime namespace injection is forbidden")
        if not isinstance(new_code, str) or not new_code.strip():
            return self._reject("patch source must be a non-empty string")

        original = getattr(target_obj, method_name, None)
        if not callable(original):
            return self._reject("patch target must already be callable")
        instance_dict = getattr(target_obj, "__dict__", None)
        if not isinstance(instance_dict, dict):
            return self._reject("patch target does not expose atomic instance state")

        if self._ethical_heart:
            allowed, reason = self._ethical_heart.evaluate(new_code)
            if not allowed:
                return self._reject(f"EthicalHeart denied patch: {reason}")

        sandbox_result = self._sandbox.validate_morphic(
            new_code,
            expected_function=method_name,
        )
        if not sandbox_result.ok:
            failure = sandbox_result.failure_payload()
            return self._reject(
                f"sandbox rejected patch [{failure['code']}]: "
                f"{failure['message']}"
            )

        spec = sandbox_result.function_spec
        if (
            spec.get("kind") != "constant_return"
            or spec.get("name") != method_name
            or "value" not in spec
        ):
            return self._reject("sandbox returned an unsupported patch API spec")
        safe_function = _constant_method(method_name, spec["value"])

        with self._lock:
            original = getattr(target_obj, method_name, None)
            baseline_digest = _callable_digest(original)
            had_instance_value = method_name in instance_dict
            original_instance_value = instance_dict.get(method_name, _MISSING)
            bound_function = types.MethodType(safe_function, target_obj)
            try:
                setattr(target_obj, method_name, bound_function)
                patched_digest = _callable_digest(
                    getattr(target_obj, method_name)
                )
            except Exception as exc:
                self._restore_instance_value(
                    target_obj,
                    method_name,
                    had_instance_value,
                    original_instance_value,
                )
                return self._reject(f"atomic patch application failed: {exc}")

            if patched_digest == baseline_digest:
                self._restore_instance_value(
                    target_obj,
                    method_name,
                    had_instance_value,
                    original_instance_value,
                )
                return self._reject("patch did not change callable digest")

            record = PatchRecord(
                name=method_name,
                target_obj=target_obj,
                original_instance_value=original_instance_value,
                had_instance_value=had_instance_value,
                baseline_digest=baseline_digest,
                patched_digest=patched_digest,
                candidate_digest=sandbox_result.code_digest,
                timestamp=time.time(),
            )
            self._patches.append(record)
            self._patch_count += 1

        logger.info(
            "[Morphic] patched %r on %r baseline=%s patched=%s",
            method_name,
            type(target_obj).__name__,
            baseline_digest[:12],
            patched_digest[:12],
        )
        if self._memory:
            self._memory.record(
                code=new_code,
                outcome={
                    "patched": method_name,
                    "candidate_digest": sandbox_result.code_digest,
                    "baseline_digest": baseline_digest,
                    "patched_digest": patched_digest,
                },
                score=0.0,
                label="MORPHIC",
            )
        return True

    def rollback(self, method_name: Optional[str] = None) -> int:
        """Atomically restore matching patches and verify baseline digests."""

        restored = 0
        failures: List[Dict[str, Any]] = []
        with self._lock:
            targets = [
                record
                for record in reversed(self._patches)
                if method_name is None or record.name == method_name
            ]
            restored_records: List[PatchRecord] = []
            for record in targets:
                current = getattr(record.target_obj, record.name, None)
                current_digest = _callable_digest(current)
                if current_digest != record.patched_digest:
                    failures.append(
                        {
                            "method": record.name,
                            "reason": "current_digest_mismatch",
                            "expected": record.patched_digest,
                            "observed": current_digest,
                        }
                    )
                    continue

                instance_dict = getattr(record.target_obj, "__dict__", {})
                current_had_value = record.name in instance_dict
                current_instance_value = instance_dict.get(
                    record.name,
                    _MISSING,
                )
                try:
                    self._restore_instance_value(
                        record.target_obj,
                        record.name,
                        record.had_instance_value,
                        record.original_instance_value,
                    )
                    restored_digest = _callable_digest(
                        getattr(record.target_obj, record.name, None)
                    )
                    if restored_digest != record.baseline_digest:
                        raise RuntimeError(
                            "restored callable digest does not match baseline"
                        )
                except Exception as exc:
                    self._restore_instance_value(
                        record.target_obj,
                        record.name,
                        current_had_value,
                        current_instance_value,
                    )
                    failures.append(
                        {
                            "method": record.name,
                            "reason": "atomic_restore_failed",
                            "error": str(exc),
                        }
                    )
                    continue

                restored += 1
                restored_records.append(record)
                logger.info(
                    "[Morphic] rollback restored %r digest=%s",
                    record.name,
                    record.baseline_digest[:12],
                )

            restored_ids = {id(record) for record in restored_records}
            self._patches = [
                record
                for record in self._patches
                if id(record) not in restored_ids
            ]
            self._last_rollback = {
                "ok": not failures,
                "restored": restored,
                "failures": failures,
            }

        if self._memory:
            self._memory.record(
                code="<morphic_rollback>",
                outcome=dict(self._last_rollback),
                score=0.0,
                label="MORPHIC_ROLLBACK",
            )
        return restored

    def status(self) -> Dict[str, Any]:
        return {
            "patches": self._patch_count,
            "rejected": self._reject_count,
            "active": len(self._patches),
            "active_digests": [
                {
                    "method": record.name,
                    "baseline": record.baseline_digest,
                    "patched": record.patched_digest,
                    "candidate": record.candidate_digest,
                }
                for record in self._patches
            ],
            "last_rollback": dict(self._last_rollback),
            "sandbox": self._sandbox.status(),
        }

    def _reject(self, reason: str) -> bool:
        self._reject_count += 1
        logger.warning("[Morphic] rejected: %s", reason)
        return False

    @staticmethod
    def _restore_instance_value(
        target_obj: Any,
        method_name: str,
        had_instance_value: bool,
        value: Any,
    ) -> None:
        if had_instance_value:
            setattr(target_obj, method_name, value)
            return
        instance_dict = getattr(target_obj, "__dict__", {})
        if method_name in instance_dict:
            delattr(target_obj, method_name)
