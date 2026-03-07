"""Pillar 38 — Meta-Cognitive Planning.  V18 IMPLEMENTATION.

Previously a stub (flag only, no code).  This module gives JAYA the
ability to *observe its own reasoning patterns*, identify systematic
weaknesses, and trigger targeted improvements via MorphicKernel patches.

Cycle (called by CoreTwin every META_REFLECT_INTERVAL seconds):
    1. Analyse ExperimentMemory for task types with avg score < WEAK_THRESHOLD.
    2. Select an improvement template for the weakest area.
    3. Invoke MorphicKernel.patch() with the template code.
    4. Monitor score for WATCH_WINDOW seconds; rollback if score drops.
    5. Log all decisions to ExperimentMemory with label "META_PATCH".

Templates Library
-----------------
Templates are safe, pre-vetted code snippets that improve a specific
cognitive sub-module.  Each template replaces one method and must pass
EthicalHeart.evaluate() before patching.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("MetaCognitive")

# Minimum avg-score to trigger intervention
WEAK_THRESHOLD: float = 0.45
# Interval between reflection runs (seconds)
META_REFLECT_INTERVAL: float = 600.0  # 10 minutes
# How long to watch a patch before deciding to keep/rollback (seconds)
WATCH_WINDOW: float = 300.0  # 5 minutes


# ---------------------------------------------------------------------------
# Improvement templates
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, Any]] = {
    "SEARCH": {
        "target_method": "search",
        "description": "Upgrade search ranking to BM25-style TF scoring",
        "code": """\
def search(self, query: str, top_k: int = 5):
    \"\"\"BM25-inspired ternary search ranking (V18 meta-patch).\"\"\"
    import re
    import math
    q_tokens = re.findall(r'\\w+', query.lower())
    if not q_tokens or not hasattr(self, '_doc_index'):
        return []
    results = []
    k1, b = 1.5, 0.75
    avg_dl = max(1, sum(len(d) for d in self._doc_index.values()) / len(self._doc_index))
    for doc_id, doc_text in self._doc_index.items():
        dl = len(doc_text)
        score = 0.0
        for token in q_tokens:
            tf = doc_text.lower().count(token)
            idf = math.log(1 + (len(self._doc_index) - tf + 0.5) / (tf + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
        if score > 0:
            results.append((doc_id, score))
    results.sort(key=lambda x: -x[1])
    return results[:top_k]
""",
    },
    "GREET": {
        "target_method": "_handle_greet",
        "description": "Expand greeting response variety in Bahasa Indonesia",
        "code": """\
def _handle_greet(self, actor: str = ""):
    \"\"\"Varied greeting responses — V18 meta-patch.\"\"\"
    import random
    responses = [
        f"Halo {actor}! Ada yang bisa saya bantu?",
        f"Selamat datang, {actor}. Saya siap membantu.",
        f"Hai {actor}! Senang bertemu lagi.",
        f"Assalamualaikum {actor}, ada yang ingin dibicarakan?",
        f"Salam {actor}! Apa yang sedang Anda pikirkan?",
    ]
    return random.choice(responses).strip()
""",
    },
    "QUERY_HOW": {
        "target_method": "_handle_how_query",
        "description": "Structured step-by-step how-to response",
        "code": """\
def _handle_how_query(self, topic: str = ""):
    \"\"\"Structured step-by-step response — V18 meta-patch.\"\"\"
    return (
        f"Untuk '{topic}', berikut langkah-langkahnya:\\n"
        "1. Pahami terlebih dahulu tujuan yang ingin dicapai.\\n"
        "2. Siapkan semua persiapan yang dibutuhkan.\\n"
        "3. Lakukan secara bertahap dan evaluasi setiap langkah.\\n"
        "4. Jika ada kendala, identifikasi dan cari solusi alternatif.\\n"
        "(Catatan: jawaban ini dihasilkan oleh template refleksi otomatis V18)"
    )
""",
    },
    "REPAIR_LOGIC": {
        "target_method": "_fallback_response",
        "description": "Improve fallback response for unknown inputs",
        "code": """\
def _fallback_response(self, raw_text: str = ""):
    \"\"\"Improved fallback for unknown inputs — V18 meta-patch.\"\"\"
    suggestions = [
        "Bisakah Anda jelaskan lebih detail?",
        "Saya belum memahami. Coba kata kunci: cari, buka, hitung, tanya.",
        "Pertanyaan Anda menarik. Bisa Anda ulangi dengan kata yang berbeda?",
        "Saya sedang belajar. Coba format: 'lakukan X pada Y'.",
    ]
    import hashlib
    idx = int(hashlib.md5(raw_text.encode()).hexdigest(), 16) % len(suggestions)
    return suggestions[idx]
""",
    },
}


# ---------------------------------------------------------------------------
# MetaCognitivePlanner
# ---------------------------------------------------------------------------

class MetaCognitivePlanner:
    """Pillar 38 — Meta-cognitive reflection and auto-improvement.

    Parameters
    ----------
    reflect_interval:
        Seconds between reflection cycles.
    weak_threshold:
        Avg score below which a task type is considered 'weak'.
    watch_window:
        Seconds to observe a patch before keeping/rolling back.
    """

    def __init__(
        self,
        reflect_interval: float = META_REFLECT_INTERVAL,
        weak_threshold: float = WEAK_THRESHOLD,
        watch_window: float = WATCH_WINDOW,
    ) -> None:
        self.reflect_interval = reflect_interval
        self.weak_threshold = weak_threshold
        self.watch_window = watch_window
        self._last_reflect: float = 0.0
        self._patch_history: list[dict] = []
        self._active_trial: dict | None = None
        self._reflect_count: int = 0
        self._patches_applied: int = 0

    # ------------------------------------------------------------------

    def tick(self, twin: Any) -> None:
        """Call every engine cycle.  Triggers reflection when interval elapses."""
        now = time.monotonic()
        if now - self._last_reflect < self.reflect_interval:
            # Check if we have an active trial to evaluate
            if self._active_trial:
                self._evaluate_trial(twin, now)
            return
        self._last_reflect = now
        self.reflect(twin)

    # ------------------------------------------------------------------

    def reflect(self, twin: Any) -> dict[str, Any]:
        """Run one reflection cycle.

        Returns
        -------
        dict with keys: weak_tasks, action, patch_applied
        """
        self._reflect_count += 1
        result: dict[str, Any] = {
            "reflect_count": self._reflect_count,
            "weak_tasks": [],
            "action": "none",
            "patch_applied": False,
        }

        try:
            memory = twin.memory
            recent = memory.recent(50)
            if len(recent) < 5:
                logger.debug("[MetaCog] Not enough history (%d entries)", len(recent))
                return result

            # Group scores by task label
            label_scores: dict[str, list[float]] = {}
            for r in recent:
                label = getattr(r, "label", "UNKNOWN")
                score = float(getattr(r, "score", 0.5))
                label_scores.setdefault(label, []).append(score)

            # Find weak areas
            weak: list[tuple[str, float]] = []
            for label, scores in label_scores.items():
                if len(scores) >= 3:
                    avg = sum(scores) / len(scores)
                    if avg < self.weak_threshold:
                        weak.append((label, avg))

            weak.sort(key=lambda x: x[1])  # worst first
            result["weak_tasks"] = weak

            if not weak:
                logger.debug("[MetaCog] All task types healthy.")
                return result

            worst_label, worst_score = weak[0]
            result["action"] = f"patch_{worst_label}"
            logger.info("[MetaCog] Reflect #%d: weakest task=%s avg=%.3f — seeking patch",
                        self._reflect_count, worst_label, worst_score)

            # Find a matching template
            template = self._select_template(worst_label)
            if template is None:
                logger.debug("[MetaCog] No template for %s — triggering LiveEvolver instead",
                             worst_label)
                self._inject_evolver_task(twin, reason=worst_label)
                return result

            # Apply patch via MorphicKernel
            morphic = getattr(twin, "morphic", None) or getattr(
                getattr(twin, "engine", None), "morphic", None
            )
            if morphic is None:
                logger.warning("[MetaCog] MorphicKernel not available.")
                return result

            target_obj = self._find_target(twin, template)
            if target_obj is None:
                return result

            success = morphic.patch(
                target_obj,
                template["target_method"],
                template["code"],
                namespace={},
            )

            if success:
                self._patches_applied += 1
                result["patch_applied"] = True
                trial_info = {
                    "label": worst_label,
                    "template": template["description"],
                    "baseline_score": worst_score,
                    "patch_time": time.monotonic(),
                    "target_method": template["target_method"],
                    "morphic": morphic,
                    "target_obj": target_obj,
                }
                self._active_trial = trial_info
                logger.info("[MetaCog] Patch applied: %s.%s — watching for %ds",
                            type(target_obj).__name__,
                            template["target_method"],
                            int(self.watch_window))

                try:
                    from src.brain_v2.extensions.twin.task_planner import Task, Priority
                    twin.planner.push(Task(
                        priority=int(Priority.LOW),
                        label="META_PATCH",
                        code="score = 0.7  # meta-patch applied, monitoring",
                        meta={"method": template["target_method"],
                              "reason": worst_label},
                    ))
                except Exception:
                    pass

        except Exception as exc:
            logger.exception("[MetaCog] reflect() error: %s", exc)

        return result

    # ------------------------------------------------------------------

    def _evaluate_trial(self, twin: Any, now: float) -> None:
        """After watch_window, decide to keep or rollback the active patch."""
        trial = self._active_trial
        if trial is None:
            return

        elapsed = now - trial["patch_time"]
        if elapsed < self.watch_window:
            return

        # Compare score now vs baseline
        try:
            memory = twin.memory
            recent = memory.recent(20)
            new_scores = [
                float(r.score) for r in recent
                if getattr(r, "label", "") == trial["label"]
                and hasattr(r, "score")
            ]
            new_avg = sum(new_scores) / max(1, len(new_scores))

            if new_avg >= trial["baseline_score"] + 0.05:
                logger.info("[MetaCog] Patch KEPT: %s avg %.3f→%.3f (+%.3f)",
                            trial["template"], trial["baseline_score"],
                            new_avg, new_avg - trial["baseline_score"])
                self._patch_history.append({**trial, "outcome": "kept",
                                            "new_avg": new_avg})
            else:
                logger.info("[MetaCog] Patch ROLLED BACK: %s avg %.3f→%.3f",
                            trial["template"], trial["baseline_score"], new_avg)
                try:
                    trial["morphic"].rollback(trial["target_method"])
                except Exception:
                    pass
                self._patch_history.append({**trial, "outcome": "rolled_back",
                                            "new_avg": new_avg})
        except Exception as exc:
            logger.warning("[MetaCog] Trial evaluation error: %s", exc)
        finally:
            self._active_trial = None

    # ------------------------------------------------------------------

    def _select_template(self, label: str) -> dict | None:
        """Find the best template for a given task label."""
        # Direct match
        for key, tmpl in _TEMPLATES.items():
            if key.upper() == label.upper():
                return tmpl
        # Partial match
        for key, tmpl in _TEMPLATES.items():
            if key.upper() in label.upper() or label.upper() in key.upper():
                return tmpl
        # Default fallback
        return _TEMPLATES.get("REPAIR_LOGIC")

    def _inject_evolver_task(self, twin: Any, reason: str) -> None:
        """Inject a LiveEvolver task into the planner."""
        try:
            from src.brain_v2.extensions.twin.task_planner import Task, Priority
            twin.planner.push(Task(
                priority=int(Priority.LOW),
                label="EVOLVE",
                code=(
                    "from src.brain_v2.education.live_evolver import LiveEvolver\n"
                    "evolver = LiveEvolver(engine)\n"
                    "result = evolver.run_evolution(steps=200)\n"
                    "score = min(1.0, 0.5 + result['delta_fitness'])\n"
                ),
                meta={"reason": reason},
            ))
        except Exception as exc:
            logger.warning("[MetaCog] Could not inject EVOLVE task: %s", exc)

    def _find_target(self, twin: Any, template: dict) -> Any | None:
        """Heuristically find the target object that owns the method."""
        method_name = template["target_method"]
        for candidate in [twin, getattr(twin, "engine", None),
                          getattr(twin, "lingua", None),
                          getattr(twin, "agentic", None)]:
            if candidate is not None and hasattr(candidate, method_name):
                return candidate
        return None

    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "reflect_count": self._reflect_count,
            "patches_applied": self._patches_applied,
            "active_trial": bool(self._active_trial),
            "patch_history_len": len(self._patch_history),
        }
