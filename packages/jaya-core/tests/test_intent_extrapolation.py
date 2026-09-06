"""Comprehensive unit and integration tests for Pillar 40 Intent Extrapolation."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from jaya_core.pillars.control_capabilities import (
    INTENT_CAPABILITY_ID,
    IntentExtrapolationCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError


def _setup_consented_cap(database: Path, owner_id: str = "user-alice", ttl_hours: float = 2.0) -> IntentExtrapolationCapability:
    cap = IntentExtrapolationCapability(database)
    now = time.time()
    cap.execute(
        {
            "action": "record_consent",
            "owner_id": owner_id,
            "receipt_id": f"receipt-{owner_id}",
            "granted_at": now - 10,
            "expires_at": now + (ttl_hours * 3600),
        }
    )
    return cap


def test_p040_consent_required_before_observation_or_prediction(tmp_path: Path) -> None:
    db = tmp_path / "intent_test.sqlite3"
    cap = IntentExtrapolationCapability(db)

    # Observation without consent
    with pytest.raises(LocalPillarError) as exc:
        cap.execute({"action": "observe", "owner_id": "unconsented-user", "sequence": ["login", "view_dashboard"]})
    assert exc.value.code == "CONSENT_REQUIRED"

    # Prediction without consent
    with pytest.raises(LocalPillarError) as exc:
        cap.execute({"action": "predict", "owner_id": "unconsented-user", "current_intent": "login"})
    assert exc.value.code == "CONSENT_REQUIRED"

    # Check status
    status = cap.execute({"action": "consent_status", "owner_id": "unconsented-user"})
    assert status.data["has_consent"] is False
    assert status.data["active"] is False


def test_p040_consent_expiration_and_revocation(tmp_path: Path) -> None:
    db = tmp_path / "intent_expire.sqlite3"
    cap = IntentExtrapolationCapability(db)
    now = time.time()

    # Record consent that expires in 0.2 seconds
    cap.execute(
        {
            "action": "record_consent",
            "owner_id": "user-bob",
            "receipt_id": "receipt-bob",
            "granted_at": now - 1,
            "expires_at": now + 0.2,
        }
    )

    # Initially valid
    status = cap.execute({"action": "consent_status", "owner_id": "user-bob"})
    assert status.data["has_consent"] is True
    assert status.data["active"] is True

    # Wait for consent to expire
    time.sleep(0.35)

    with pytest.raises(LocalPillarError) as exc:
        cap.execute({"action": "observe", "owner_id": "user-bob", "sequence": ["search", "download"]})
    assert exc.value.code == "CONSENT_EXPIRED"

    status = cap.execute({"action": "consent_status", "owner_id": "user-bob"})
    assert status.data["has_consent"] is True
    assert status.data["active"] is False
    assert status.data["opted_out"] is False


def test_p040_opt_out_disables_profiling_and_clears_transitions(tmp_path: Path) -> None:
    db = tmp_path / "intent_optout.sqlite3"
    cap = _setup_consented_cap(db, "user-charlie")

    # Observe transitions
    cap.execute(
        {
            "action": "observe",
            "owner_id": "user-charlie",
            "sequence": ["compile_code", "run_tests", "commit_changes"],
        }
    )
    cap.execute(
        {
            "action": "observe",
            "owner_id": "user-charlie",
            "sequence": ["compile_code", "run_tests", "commit_changes"],
        }
    )

    # Opt out
    opt_res = cap.execute({"action": "opt_out", "owner_id": "user-charlie"})
    assert opt_res.data["owner_id"] == "user-charlie"

    # Check status
    status = cap.execute({"action": "consent_status", "owner_id": "user-charlie"})
    assert status.data["has_consent"] is True
    assert status.data["active"] is False
    assert status.data["opted_out"] is True

    # Subsequent prediction fails with CONSENT_REQUIRED
    with pytest.raises(LocalPillarError) as exc:
        cap.execute({"action": "predict", "owner_id": "user-charlie", "current_intent": "compile_code"})
    assert exc.value.code == "CONSENT_REQUIRED"


def test_p040_sovereign_deletion_erases_all_records(tmp_path: Path) -> None:
    db = tmp_path / "intent_purge.sqlite3"
    cap = _setup_consented_cap(db, "user-dave")

    cap.execute(
        {
            "action": "observe",
            "owner_id": "user-dave",
            "sequence": ["load_model", "warmup", "benchmark"],
        }
    )
    pred = cap.execute(
        {
            "action": "predict",
            "owner_id": "user-dave",
            "current_intent": "load_model",
            "minimum_observations": 1,
        }
    )
    assert pred.data["candidate"] == "warmup"

    # Sovereign delete
    del_res = cap.execute({"action": "delete", "owner_id": "user-dave"})
    assert del_res.data["purged"] is True

    # Check consent status is completely reset
    status = cap.execute({"action": "consent_status", "owner_id": "user-dave"})
    assert status.data["has_consent"] is False
    assert status.data["active"] is False

    # Check database tables directly to ensure zero residue
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT COUNT(*) FROM intent_transitions WHERE owner_id='user-dave'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM intent_predictions WHERE owner_id='user-dave'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM intent_consent WHERE owner_id='user-dave'").fetchone()[0] == 0


def test_p040_prediction_contract_and_non_execution(tmp_path: Path) -> None:
    db = tmp_path / "intent_contract.sqlite3"
    cap = _setup_consented_cap(db, "user-eve")

    for _ in range(3):
        cap.execute(
            {
                "action": "observe",
                "owner_id": "user-eve",
                "sequence": ["open_editor", "write_spec", "review_plan"],
            }
        )

    pred = cap.execute(
        {
            "action": "predict",
            "owner_id": "user-eve",
            "current_intent": "open_editor",
            "minimum_observations": 2,
            "ttl_seconds": 120,
        }
    )

    data = pred.data
    # Strict validation of contract labels
    assert data["source"] == "INFERENCE", "Must strictly label as INFERENCE"
    assert data["candidate"] == "write_spec"
    assert data["confidence"] == 1.0
    assert data["confirmation_required"] is True, "Must require explicit confirmation"
    assert data["executed"] is False, "Must NEVER auto-execute proactive side-effects"
    assert "explanation" in data
    assert data["expires_at"] > time.time()


def test_p040_insufficient_history_and_ambiguity(tmp_path: Path) -> None:
    db = tmp_path / "intent_ambiguity.sqlite3"
    cap = _setup_consented_cap(db, "user-frank")

    # Only 1 observation, minimum required is 2
    cap.execute(
        {
            "action": "observe",
            "owner_id": "user-frank",
            "sequence": ["step_a", "step_b"],
        }
    )

    with pytest.raises(LocalPillarError) as exc:
        cap.execute(
            {
                "action": "predict",
                "owner_id": "user-frank",
                "current_intent": "step_a",
                "minimum_observations": 2,
            }
        )
    assert exc.value.code == "INSUFFICIENT_HISTORY"

    # Add a conflicting transition to create a tie
    cap.execute(
        {
            "action": "observe",
            "owner_id": "user-frank",
            "sequence": ["step_a", "step_c"],
        }
    )

    # Now total is 2, but step_b (1) and step_c (1) are tied!
    with pytest.raises(LocalPillarError) as exc:
        cap.execute(
            {
                "action": "predict",
                "owner_id": "user-frank",
                "current_intent": "step_a",
                "minimum_observations": 2,
            }
        )
    assert exc.value.code == "AMBIGUOUS_INTENT"


def test_p040_staleness_filtering(tmp_path: Path) -> None:
    db = tmp_path / "intent_stale.sqlite3"
    cap = _setup_consented_cap(db, "user-grace")

    cap.execute(
        {
            "action": "observe",
            "owner_id": "user-grace",
            "sequence": ["query_doc", "extract_table"],
        }
    )
    cap.execute(
        {
            "action": "observe",
            "owner_id": "user-grace",
            "sequence": ["query_doc", "extract_table"],
        }
    )

    # Predict with staleness window of 3600 seconds -> passes
    pred = cap.execute(
        {
            "action": "predict",
            "owner_id": "user-grace",
            "current_intent": "query_doc",
            "max_staleness_seconds": 3600,
        }
    )
    assert pred.data["candidate"] == "extract_table"

    # Manipulate timestamp in DB to simulate old transition
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE intent_transitions SET updated_at = ?", (time.time() - 7200,))

    # Now predict with max_staleness_seconds = 3600 -> should be filtered out
    with pytest.raises(LocalPillarError) as exc:
        cap.execute(
            {
                "action": "predict",
                "owner_id": "user-grace",
                "current_intent": "query_doc",
                "max_staleness_seconds": 3600,
            }
        )
    assert exc.value.code == "INSUFFICIENT_HISTORY"


def test_p040_feedback_adaptation_and_alternative_learning(tmp_path: Path) -> None:
    db = tmp_path / "intent_feedback.sqlite3"
    cap = _setup_consented_cap(db, "user-heidi")

    # Observe 2 times: plan -> test
    for _ in range(2):
        cap.execute({"action": "observe", "owner_id": "user-heidi", "sequence": ["plan", "test"]})

    pred = cap.execute({"action": "predict", "owner_id": "user-heidi", "current_intent": "plan"})
    assert pred.data["candidate"] == "test"

    # User rejects "test" and corrects with alternative "review"
    cap.execute(
        {
            "action": "feedback",
            "prediction_id": pred.data["prediction_id"],
            "confirmed": False,
            "alternative_intent": "review",
        }
    )

    # Effective count for "test" dropped from 2 to 1 (2 observations - 1 correction)
    # New transition for "review" has 1 observation
    # Now tied: test (1) vs review (1) -> AMBIGUOUS_INTENT
    with pytest.raises(LocalPillarError) as exc:
        cap.execute({"action": "predict", "owner_id": "user-heidi", "current_intent": "plan"})
    assert exc.value.code == "AMBIGUOUS_INTENT"

    # Reinforce "review" once more
    cap.execute({"action": "observe", "owner_id": "user-heidi", "sequence": ["plan", "review"]})

    # Now review has 2 effective observations vs test (1) -> predict "review"
    pred2 = cap.execute({"action": "predict", "owner_id": "user-heidi", "current_intent": "plan"})
    assert pred2.data["candidate"] == "review"
    assert pred2.data["confidence"] == round(2 / 3, 4)


def test_p040_sqlite_wal_durability_and_restart(tmp_path: Path) -> None:
    db = tmp_path / "intent_wal.sqlite3"
    cap1 = _setup_consented_cap(db, "user-ivan")

    for _ in range(3):
        cap1.execute({"action": "observe", "owner_id": "user-ivan", "sequence": ["start", "finish"]})

    # Restart capability instance on same DB file
    cap2 = IntentExtrapolationCapability(db)
    assert cap2.health_check() is True

    # Predict on restarted instance
    pred = cap2.execute({"action": "predict", "owner_id": "user-ivan", "current_intent": "start"})
    assert pred.data["candidate"] == "finish"
    assert pred.data["source"] == "INFERENCE"

    # Verify WAL journal mode is active
    with sqlite3.connect(db) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.upper() == "WAL"


def test_p040_integrity_and_tamper_detection(tmp_path: Path) -> None:
    db = tmp_path / "intent_integrity.sqlite3"
    cap = _setup_consented_cap(db, "user-judy")

    cap.execute({"action": "observe", "owner_id": "user-judy", "sequence": ["stage_1", "stage_2"]})
    assert cap.verify_integrity() is True

    # Tamper with the transition table directly without calling capability
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE intent_transitions SET observations = 9999 WHERE current_intent='stage_1'")

    # verify_integrity should detect state mismatch and raise STORAGE_CORRUPT
    with pytest.raises(LocalPillarError) as exc:
        cap.verify_integrity()
    assert exc.value.code == "STORAGE_CORRUPT"
