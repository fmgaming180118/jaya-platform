"""
planner.py — Generic, domain-neutral hierarchical task planner.
"""

from __future__ import annotations

import hashlib
from typing import List

from .contracts import (
    ActionPlan,
    ActionStatus,
    ActionStep,
    Goal,
    IntentType,
    RiskClass,
)


class GenericHierarchicalPlanner:
    """Domain-neutral planner producing structured ActionPlans for JAYA Core."""

    def create_plan(self, goal: Goal) -> ActionPlan:
        suffix = hashlib.sha256(goal.goal_id.encode("utf-8")).hexdigest()[:8]
        plan_id = f"plan-{suffix}"

        steps: List[ActionStep] = []

        if goal.intent_type == IntentType.CREATE_3D_DESIGN:
            steps = [
                ActionStep(
                    step_id="step-1",
                    title="Kumpulkan dan verifikasi kebutuhan spesifikasi komponen",
                    action_type="collect_requirements",
                    required_capability="text.reasoning.basic",
                    risk_class=RiskClass.READ_ONLY,
                    execution_target="local",
                    approval_required=False,
                ),
                ActionStep(
                    step_id="step-2",
                    title="Hitung kebutuhan airflow dan constraint dimensi",
                    action_type="calculate_constraints",
                    required_capability="text.reasoning.basic",
                    risk_class=RiskClass.READ_ONLY,
                    execution_target="local",
                    dependencies=["step-1"],
                ),
                ActionStep(
                    step_id="step-3",
                    title="Hasilkan geometri 3D parametrik",
                    action_type="generate_parametric_geometry",
                    required_capability="cad.parametric_modeling",
                    risk_class=RiskClass.REVERSIBLE,
                    execution_target="local",
                    dependencies=["step-2"],
                ),
                ActionStep(
                    step_id="step-4",
                    title="Tampilkan preview dan minta persetujuan pengguna",
                    action_type="present_preview",
                    required_capability="text.reasoning.basic",
                    risk_class=RiskClass.READ_ONLY,
                    execution_target="local",
                    approval_required=True,
                    dependencies=["step-3"],
                ),
                ActionStep(
                    step_id="step-5",
                    title="Ekspor model 3D (STL/STEP)",
                    action_type="export_model",
                    required_capability="cad.parametric_modeling",
                    risk_class=RiskClass.DESTRUCTIVE,
                    execution_target="local",
                    approval_required=True,
                    dependencies=["step-4"],
                ),
            ]

        elif goal.intent_type == IntentType.WRITE_CODE:
            steps = [
                ActionStep(
                    step_id="step-1",
                    title="Analisis kebutuhan dan arsitektur kode",
                    action_type="analyze_architecture",
                    required_capability="text.reasoning.basic",
                    risk_class=RiskClass.READ_ONLY,
                ),
                ActionStep(
                    step_id="step-2",
                    title="Tulis draft kode Python",
                    action_type="write_code_draft",
                    required_capability="system.file.write",
                    risk_class=RiskClass.READ_ONLY,
                    inputs={"path": "draft.py", "content": "# Draft code output"},
                    dependencies=["step-1"],
                ),
                ActionStep(
                    step_id="step-3",
                    title="Jalankan unit test",
                    action_type="run_tests",
                    required_capability="process.execute",
                    risk_class=RiskClass.READ_ONLY,
                    inputs={"profile_id": "pytest.workspace"},
                    dependencies=["step-2"],
                ),
            ]

        elif goal.intent_type == IntentType.CREATE_PLAN:
            steps = [
                ActionStep(
                    step_id="step-1",
                    title="Inventarisasi item dan kategori file proyek",
                    action_type="inventory_files",
                    required_capability="system.file.list",
                    risk_class=RiskClass.READ_ONLY,
                    inputs={"path": "."}
                ),
                ActionStep(
                    step_id="step-2",
                    title="Susun rencana struktur folder baru",
                    action_type="propose_structure",
                    required_capability="text.reasoning.basic",
                    risk_class=RiskClass.READ_ONLY,
                    dependencies=["step-1"],
                ),
                ActionStep(
                    step_id="step-3",
                    title="Minta persetujuan pemindahan file",
                    action_type="request_move_approval",
                    required_capability="text.reasoning.basic",
                    risk_class=RiskClass.DESTRUCTIVE,
                    approval_required=True,
                    dependencies=["step-2"],
                ),
            ]

        else:
            # Generic single-step response plan
            steps = [
                ActionStep(
                    step_id="step-1",
                    title=f"Proses permintaan: {goal.title}",
                    action_type="process_general_request",
                    required_capability="text.reasoning.basic",
                    risk_class=RiskClass.READ_ONLY,
                    execution_target="local",
                )
            ]

        return ActionPlan(
            plan_id=plan_id,
            goal_id=goal.goal_id,
            steps=steps,
            domain=goal.domain,
        )
