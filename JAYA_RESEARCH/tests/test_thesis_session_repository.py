import json
import sqlite3

import pytest

from research.academic.thesis_session_repository import (
    PersistentThesisSessions,
    ThesisSessionError,
    ThesisSessionRepository,
)


def _payload(status: str = "uploaded"):
    return {
        "workspace_id": "workspace_a",
        "status": status,
        "raw_text": "Durable thesis source text",
        "steps": [],
        "analysis": None,
    }


def test_session_survives_repository_reconstruction(tmp_path):
    database = tmp_path / "thesis.db"
    first_repository = ThesisSessionRepository(database)
    first_repository.save("session-001", _payload())

    restarted_repository = ThesisSessionRepository(database)
    restored = restarted_repository.get("session-001")

    assert restored["raw_text"] == "Durable thesis source text"
    assert restored["status"] == "uploaded"


def test_nested_progress_can_be_explicitly_persisted(tmp_path):
    sessions = PersistentThesisSessions(ThesisSessionRepository(tmp_path / "thesis.db"))
    sessions["session-002"] = _payload()
    session = sessions["session-002"]
    session["status"] = "analyzing"
    session["steps"].append({"step": "meta", "status": "done"})

    sessions.persist("session-002", session)

    restored = sessions["session-002"]
    assert restored["status"] == "analyzing"
    assert restored["steps"] == [{"step": "meta", "status": "done"}]


def test_restart_marks_in_process_analysis_as_interrupted(tmp_path):
    repository = ThesisSessionRepository(tmp_path / "thesis.db")
    repository.save("session-003", _payload(status="analyzing"))

    recovered_count = ThesisSessionRepository(
        tmp_path / "thesis.db"
    ).recover_interrupted()
    recovered = repository.get("session-003")

    assert recovered_count == 1
    assert recovered["status"] == "interrupted"
    assert "restart" in recovered["error"]
    assert recovered["raw_text"] == "Durable thesis source text"


def test_payload_must_be_json_serializable(tmp_path):
    repository = ThesisSessionRepository(tmp_path / "thesis.db")
    payload = _payload()
    payload["bad_value"] = object()

    with pytest.raises(ThesisSessionError, match="not JSON serializable"):
        repository.save("session-004", payload)


def test_corrupt_session_payload_returns_typed_error(tmp_path):
    database = tmp_path / "thesis.db"
    repository = ThesisSessionRepository(database)
    repository.save("session-005", _payload())
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE thesis_sessions SET payload_json = ? WHERE session_id = ?",
            ("{broken", "session-005"),
        )
        connection.commit()

    with pytest.raises(ThesisSessionError, match="invalid JSON"):
        repository.get("session-005")


def test_save_increments_revision_without_losing_creation_time(tmp_path):
    database = tmp_path / "thesis.db"
    repository = ThesisSessionRepository(database)

    assert repository.save("session-006", _payload()) == 1
    assert repository.save("session-006", _payload(status="done")) == 2

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT revision, created_at, updated_at, payload_json "
            "FROM thesis_sessions WHERE session_id = ?",
            ("session-006",),
        ).fetchone()
    assert row[0] == 2
    assert row[1] <= row[2]
    assert json.loads(row[3])["status"] == "done"
