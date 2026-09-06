from pathlib import Path

from scripts import run_test_matrix

TIMEOUT_EXIT_CODE = 124


def _component() -> run_test_matrix.Component:
    return run_test_matrix.Component(
        name="fixture",
        test_path=Path("tests"),
        python_paths=(Path(),),
    )


def test_collection_failure_has_stable_error_code(tmp_path, monkeypatch) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_broken.py").write_text(
        "import module_that_does_not_exist\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_test_matrix, "ROOT", tmp_path)

    result = run_test_matrix._run_component(
        _component(),
        collect_only=True,
        offline=True,
        quiet=True,
        timeout_seconds=10,
    )

    assert result["status"] == "FAILED"
    assert result["error_code"] == "TEST_DISCOVERY_FAILED"
    assert result["exit_code"] != 0
    assert "module_that_does_not_exist" in result["output_tail"]


def test_collection_timeout_is_bounded(tmp_path, monkeypatch) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_slow_import.py").write_text(
        "import time\ntime.sleep(3)\ndef test_late(): pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_test_matrix, "ROOT", tmp_path)

    result = run_test_matrix._run_component(
        _component(),
        collect_only=True,
        offline=True,
        quiet=True,
        timeout_seconds=0.2,
    )

    assert result["status"] == "TIMEOUT"
    assert result["error_code"] == "TEST_DISCOVERY_FAILED"
    assert result["exit_code"] == TIMEOUT_EXIT_CODE
