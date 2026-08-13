"""
evaluation.py — Evaluates ActionResults from Agent execution.
"""

from __future__ import annotations

from .contracts import ActionResult, ActionStatus, EvaluationResult


class ActionEvaluator:
    """Evaluates ActionResults from JAYA Agent execution."""

    def evaluate(self, result: ActionResult, total_steps_in_plan: int = 1) -> EvaluationResult:
        if result.status == ActionStatus.SUCCESS:
            step_num = 1
            try:
                step_num = int(result.step_id.replace("step-", ""))
            except ValueError:
                pass

            is_last_step = step_num >= total_steps_in_plan
            next_step = f"step-{step_num + 1}" if not is_last_step else None

            return EvaluationResult(
                request_id=result.request_id,
                is_goal_achieved=is_last_step,
                should_replan=False,
                summary=f"Langkah {result.step_id} berhasil dieksekusi.",
                next_step_id=next_step,
            )

        if result.status in (ActionStatus.FAILED, ActionStatus.SKIPPED):
            return EvaluationResult(
                request_id=result.request_id,
                is_goal_achieved=False,
                should_replan=True,
                summary=f"Langkah {result.step_id} gagal ({result.error_code or 'UNKNOWN_ERROR'}): {result.error_message or ''}",
                next_step_id=None,
            )

        if result.status == ActionStatus.REQUIRES_APPROVAL:
            return EvaluationResult(
                request_id=result.request_id,
                is_goal_achieved=False,
                should_replan=False,
                summary=f"Langkah {result.step_id} membutuhkan persetujuan pengguna sebelum dilanjutkan.",
                next_step_id=result.step_id,
            )

        return EvaluationResult(
            request_id=result.request_id,
            is_goal_achieved=False,
            should_replan=False,
            summary=f"Status langkah {result.step_id}: {result.status.value}",
            next_step_id=None,
        )
