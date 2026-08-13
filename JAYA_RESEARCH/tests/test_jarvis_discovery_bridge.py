import json

from research.experiment_designer import ExperimentDesigner
from research.experiment_runner import ExperimentRunner
from research.experimental_memory import ExperimentalMemory
from research.jarvis_discovery_bridge import JarvisDiscoveryBridge
from research.research_artifact import validate_artifact_dict


def _hypothesis():
    return {
        "hypothesis_id": "HYP-TEST-001",
        "topic": "Measured Throughput",
        "statement": "The treatment changes measured throughput.",
    }


def test_candidate_is_non_executable_and_targets_public_boundary(tmp_path):
    bridge = JarvisDiscoveryBridge(outbox_dir=tmp_path / "outbox")
    candidate = bridge.create_jarvis_patch(
        _hypothesis(),
        {"posterior_confidence": 0.88, "recommendation": "HOLD"},
    )

    assert candidate["target_system"] == "JAYA_CORE"
    assert candidate["confidence"] == 0.88
    assert candidate["executable"] is False
    assert candidate["proposed_directives"][0]["active"] is False


def test_direct_core_database_mutation_is_always_blocked(tmp_path):
    legacy_db = tmp_path / "legacy-core.db"
    bridge = JarvisDiscoveryBridge(
        outbox_dir=tmp_path / "outbox",
        core_db_path=legacy_db,
    )
    candidate = bridge.create_jarvis_patch(_hypothesis(), {})

    assert bridge.apply_patch_to_core(candidate) is False
    assert not legacy_db.exists()


def test_simulation_is_rejected_before_outbox(tmp_path):
    outbox = tmp_path / "outbox"
    bridge = JarvisDiscoveryBridge(outbox_dir=outbox)
    disposition = bridge.deploy_discovery_to_jarvis(
        _hypothesis(),
        {
            "run_id": "RUN-SIM-001",
            "evidence_kind": "SIMULATION",
            "reproduction": {"reproduced": False, "run_count": 1},
        },
        {
            "posterior_confidence": 0.9,
            "recommendation": "ACCEPT_HYPOTHESIS",
        },
    )

    assert disposition["status"] == "REJECTED_SIMULATION"
    assert disposition["auto_deployed"] is False
    assert list(outbox.glob("*.json")) == []


def test_reproduced_empirical_candidate_is_exported_for_review(tmp_path):
    outbox = tmp_path / "outbox"
    bridge = JarvisDiscoveryBridge(outbox_dir=outbox)
    hypothesis = _hypothesis()
    hypothesis.update(
        {
            "observations": {
                "baseline": [1.0, 1.1, 0.9],
                "treatment": [2.0, 2.1, 1.9],
            },
            "provenance": {
                "source_hashes": ["a" * 64],
                "license_id": "CC-BY-4.0",
                "runner_id": "runner-a",
                "environment_id": "environment-a",
            },
        }
    )
    first_result = ExperimentRunner(
        ExperimentalMemory(tmp_path / "first-memory.json")
    ).run_experiment(
        ExperimentDesigner().design_experiment(
            hypothesis,
            execution_mode="EMPIRICAL",
        )
    )
    hypothesis["observations"] = {
        "baseline": [1.2, 1.3, 1.1],
        "treatment": [2.2, 2.3, 2.1],
    }
    hypothesis["provenance"] = {
        "source_hashes": ["b" * 64],
        "license_id": "CC-BY-4.0",
        "runner_id": "runner-b",
        "environment_id": "environment-b",
    }
    hypothesis["prior_empirical_runs"] = [first_result]
    run_result = ExperimentRunner(
        ExperimentalMemory(tmp_path / "second-memory.json")
    ).run_experiment(
        ExperimentDesigner().design_experiment(
            hypothesis,
            execution_mode="EMPIRICAL",
        )
    )
    disposition = bridge.deploy_discovery_to_jarvis(
        hypothesis,
        run_result,
        {
            "posterior_confidence": 0.89,
            "recommendation": "ACCEPT_HYPOTHESIS",
        },
    )

    assert disposition["status"] == "PENDING_REVIEW"
    assert disposition["auto_deployed"] is False
    artifact_path = outbox / f"{disposition['patch_id']}.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    validate_artifact_dict(artifact)
    assert artifact["status"] == "PENDING_REVIEW"
    assert artifact["payload"]["executable"] is False


def test_empirical_promotion_rejects_tampered_run_receipt(tmp_path):
    bridge = JarvisDiscoveryBridge(outbox_dir=tmp_path / "outbox")
    run_result = {
        "run_id": "RUN-FORGED",
        "evidence_kind": "EMPIRICAL",
        "status": "COMPLETED_EMPIRICAL",
        "reproduction": {"reproduced": True, "run_count": 2},
        "result_sha256": "0" * 64,
    }

    disposition = bridge.deploy_discovery_to_jarvis(
        _hypothesis(),
        run_result,
        {
            "posterior_confidence": 0.99,
            "recommendation": "ACCEPT_HYPOTHESIS",
        },
    )

    assert disposition["status"] == "INVALID_EVIDENCE_RECEIPT"
    assert disposition["auto_deployed"] is False
    assert list((tmp_path / "outbox").glob("*.json")) == []
