import inspect
import json

from research.ecosystem_bridge import (
    ResearchEcosystemBridge,
    ResearchFinding,
)
from research.research_artifact import ResearchArtifact, validate_artifact_dict


def _finding(**overrides):
    values = {
        "finding_id": "find-001",
        "paper_title": "Measured Attention Evaluation",
        "authors": ["Research team"],
        "topic": "attention_sparsity",
        "gap_summary": "A candidate relationship requiring review.",
        "suggested_patch_type": "knowledge_proposal",
        "patch_code": "Non-executable proposal text.",
        "confidence_score": 0.6,
    }
    values.update(overrides)
    return ResearchFinding(**values)


def test_finding_conversion_returns_research_owned_artifact(tmp_path):
    bridge = ResearchEcosystemBridge(outbox_dir=tmp_path / "outbox")

    artifact = bridge.convert_finding_to_candidate(_finding())

    assert isinstance(artifact, ResearchArtifact)
    assert artifact.artifact_id == "candidate-find-001"
    assert artifact.producer == "JAYA_RESEARCH"
    assert artifact.payload["executable"] is False
    assert artifact.status.value == "DRAFT_INCOMPLETE"


def test_submission_writes_only_to_research_outbox(tmp_path):
    outbox = tmp_path / "research-outbox"
    bridge = ResearchEcosystemBridge(outbox_dir=outbox)

    result = bridge.submit_research_upgrade(_finding(evidence_kind="SIMULATION"))

    assert result["gate_passed"] is False
    assert result["human_review_required"] is True
    assert result["auto_deployed_by_research"] is False
    artifact = json.loads(
        (outbox / "candidate-find-001.json").read_text(encoding="utf-8")
    )
    validate_artifact_dict(artifact)
    assert artifact["status"] == "SIMULATION_ONLY"


def test_bridge_has_no_internal_core_import_or_deploy_path(tmp_path):
    bridge = ResearchEcosystemBridge(outbox_dir=tmp_path / "outbox")
    source = inspect.getsource(inspect.getmodule(ResearchEcosystemBridge))

    assert "from JAYA_CORE" not in source
    assert "src.brain_v2" not in source
    assert bridge.deploy_patch_to_core(_finding())[0] is False
