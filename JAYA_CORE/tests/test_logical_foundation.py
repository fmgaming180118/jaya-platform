"""Evidence gates for Stage 1: Pondasi Logika.

Every test exercises production implementations. Small deterministic providers
exist only in this test module to force resource failure paths safely.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.run_jaya_core_server import _build_runtime
from src.brain_v2.engine.jaya_ir_exec import JayaIRExecutor
from src.brain_v2.engine.jaya_ir_translator import (
    logic_expr_to_ir,
    logic_request_to_ir,
    text_to_ir,
)
from src.brain_v2.organism.homeostasis import (
    HomeostasisEventStore,
    HomeostasisState,
    LogicalHomeostasisController,
)
from src.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyBundle,
    PolicyEffect,
    PolicyRisk,
    PolicyRule,
)
from src.capabilities.puzzle import (
    CapabilityPuzzleRegistry,
    PuzzleError,
    PuzzleFailureCode,
    PuzzleManifest,
)
from src.cognitive.runtime import JayaCoreRuntime
from src.core_config import CoreConfig
from src.core_service import create_app
from src.identity.models import NodeClass
from src.operations.snapshot import (
    CoreSnapshotManager,
    SnapshotError,
    SnapshotFailureCode,
)
from src.reasoning import pure_logic
from src.reasoning.pure_logic import (
    LogicFailureCode,
    LogicProofStore,
    LogicStatus,
    PureLogicError,
    PureLogicService,
    PureLogicSolver,
    SolverLimits,
)
from src.resources.budget import ResourceBudgetCalculator
from src.resources.modes import ExecutionMode, ExecutionModeController
from src.resources.profiler import ResourceProfile, ResourceProfiler

_API_KEY = "logic-test-" + ("a" * 32)
_SOUL_PASSWORD = "logic-soul-" + ("b" * 32)


def _profile(
    *,
    available_memory_mb: int | None = 4_096,
    storage_free_mb: int | None = 8_192,
    network_available: bool | None = True,
    power_mode: str = "NORMAL",
    thermal_celsius: float | None = None,
) -> ResourceProfile:
    return ResourceProfile(
        node_class=NodeClass.STANDARD,
        total_memory_mb=8_192 if available_memory_mb is not None else None,
        available_memory_mb=available_memory_mb,
        process_memory_mb=64,
        cpu_count=4,
        storage_free_mb=storage_free_mb,
        network_available=network_available,
        power_mode=power_mode,
        thermal_celsius=thermal_celsius,
        sources={"fixture": "test_only"},
    )


class _StaticProfiler:
    def __init__(self, profile: ResourceProfile) -> None:
        self._profile = profile

    def profile(self) -> ResourceProfile:
        return self._profile


def _logic_service(db_path: Path) -> PureLogicService:
    return PureLogicService(LogicProofStore(db_path))


def _config(tmp_path: Path) -> CoreConfig:
    model_path = tmp_path / "brain.jay"
    model_path.write_bytes(b"logical-foundation-test-artifact")
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    return CoreConfig.from_env(
        {
            "JAYA_ENVIRONMENT": "test",
            "JAYA_SOUL_PASSWORD": _SOUL_PASSWORD,
            "JAYA_CORE_API_KEY": _API_KEY,
            "JAYA_MODEL_PATH": str(model_path),
            "JAYA_CORE_DATA_DIR": str(data_dir),
            "JAYA_CORE_BIND_HOST": "127.0.0.1",
            "JAYA_CORE_BIND_PORT": "8765",
            "JAYA_CORE_TRUSTED_HOSTS": "testserver",
        },
        core_dir=tmp_path,
    )


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_API_KEY}"}


def test_p01_contract_truth_states_and_proof_trace(tmp_path: Path) -> None:
    service = _logic_service(tmp_path / "logic.db")
    try:
        proved = service.evaluate(
            request_id="proof-1",
            facts=["sensor.ready"],
            rules=[
                {"id": "r1", "if": ["sensor.ready"], "then": "node.ready"},
                {"id": "r2", "if": ["node.ready"], "then": "task.allowed"},
            ],
            query="task.allowed",
        )
        disproved = service.evaluate(
            request_id="proof-2",
            facts=["!task.allowed"],
            rules=[],
            query="task.allowed",
        )
        unknown = service.evaluate(
            request_id="proof-3",
            facts=["sensor.ready"],
            rules=[],
            query="task.allowed",
        )
        conflict = service.evaluate(
            request_id="proof-4",
            facts=["task.allowed", "!task.allowed"],
            rules=[],
            query="task.allowed",
        )
    finally:
        service.close()

    assert proved.status is LogicStatus.PROVED
    assert [step.source for step in proved.proof] == ["FACT", "r1", "r2"]
    assert disproved.status is LogicStatus.DISPROVED
    assert unknown.status is LogicStatus.UNKNOWN
    assert conflict.status is LogicStatus.CONFLICT
    assert conflict.contradictions == ("task.allowed",)


def test_p01_failure_limits_and_invalid_input(tmp_path: Path) -> None:
    service = PureLogicService(
        LogicProofStore(tmp_path / "limits.db"),
        PureLogicSolver(SolverLimits(max_facts=1)),
    )
    try:
        with pytest.raises(PureLogicError) as oversized:
            service.evaluate(
                request_id="too-large",
                facts=["a", "b"],
                rules=[],
                query="a",
            )
        with pytest.raises(PureLogicError) as invalid:
            service.evaluate(
                request_id="bad-input",
                facts=["contains spaces"],
                rules=[],
                query="a",
            )
        with pytest.raises(PureLogicError) as missing_rule_id:
            service.evaluate(
                request_id="bad-rule",
                facts=["a"],
                rules=[{"if": ["a"], "then": "b"}],
                query="b",
            )
    finally:
        service.close()

    assert oversized.value.code is LogicFailureCode.THEORY_LIMIT_EXCEEDED
    assert invalid.value.code is LogicFailureCode.INVALID_INPUT
    assert missing_rule_id.value.code is LogicFailureCode.INVALID_INPUT


def test_p01_solver_timeout_is_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter((0.0, 1.0))
    monkeypatch.setattr(pure_logic.time, "monotonic", lambda: next(ticks))
    service = PureLogicService(
        LogicProofStore(tmp_path / "timeout.db"),
        PureLogicSolver(SolverLimits(timeout_seconds=0.001)),
    )
    try:
        with pytest.raises(PureLogicError) as captured:
            service.evaluate(
                request_id="timeout",
                facts=["a"],
                rules=[],
                query="a",
            )
    finally:
        service.close()

    assert captured.value.code is LogicFailureCode.SOLVER_TIMEOUT


def test_p01_process_memory_limit_is_enforced(tmp_path: Path) -> None:
    service = _logic_service(tmp_path / "memory-limit.db")
    try:
        with pytest.raises(PureLogicError) as captured:
            service.evaluate(
                request_id="memory-limited",
                facts=["a"],
                rules=[],
                query="a",
                max_process_memory_mb=1,
            )
    finally:
        service.close()

    assert captured.value.code is LogicFailureCode.MEMORY_LIMIT_EXCEEDED


def test_p01_persistence_restart_idempotency_and_corruption(tmp_path: Path) -> None:
    db_path = tmp_path / "restart.db"
    service = _logic_service(db_path)
    first = service.evaluate(
        request_id="stable-request",
        facts=["a"],
        rules=[{"id": "derive-b", "if": ["a"], "then": "b"}],
        query="b",
    )
    service.close()

    restarted = _logic_service(db_path)
    try:
        repeated = restarted.evaluate(
            request_id="stable-request",
            facts=["a"],
            rules=[{"id": "derive-b", "if": ["a"], "then": "b"}],
            query="b",
        )
        assert repeated == first
        with pytest.raises(PureLogicError) as duplicate:
            restarted.evaluate(
                request_id="stable-request",
                facts=["different"],
                rules=[],
                query="b",
            )
        assert duplicate.value.code is LogicFailureCode.DUPLICATE_REQUEST
    finally:
        restarted.close()

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE logic_proofs SET result_json = ? WHERE request_id = ?",
            ("{}", "stable-request"),
        )
        connection.commit()
    corrupt = LogicProofStore(db_path)
    try:
        with pytest.raises(PureLogicError) as captured:
            corrupt.get("stable-request")
        assert captured.value.code is LogicFailureCode.CORRUPT_PROOF
    finally:
        corrupt.close()


def test_p01_runtime_and_api_vertical_slice(tmp_path: Path) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "runtime.db",
        node_id="test-node",
        resource_profiler=_StaticProfiler(_profile()),  # type: ignore[arg-type]
    )
    request = {
        "request_id": "api-logic-1",
        "facts": ["device.present"],
        "rules": [
            {"id": "device-rule", "if": ["device.present"], "then": "device.known"}
        ],
        "query": "device.known",
    }
    try:
        with TestClient(create_app(_config(tmp_path), runtime=runtime)) as client:
            unauthorized = client.post("/v1/logic/evaluate", json=request)
            response = client.post(
                "/v1/logic/evaluate",
                json=request,
                headers=_auth(),
            )
        events = runtime.episodic_memory.query_by_goal("api-logic-1")
    finally:
        runtime.close()

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["status"] == "PROVED"
    assert events[0].event_type == "PURE_LOGIC_EVALUATED"


def test_p01_api_rejects_unknown_fields_and_conflicting_duplicate(
    tmp_path: Path,
) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "api-failure.db",
        node_id="test-node",
        resource_profiler=_StaticProfiler(_profile()),  # type: ignore[arg-type]
    )
    base = {
        "request_id": "duplicate-api",
        "facts": ["a"],
        "rules": [],
        "query": "a",
    }
    try:
        with TestClient(create_app(_config(tmp_path), runtime=runtime)) as client:
            assert (
                client.post(
                    "/v1/logic/evaluate", json=base, headers=_auth()
                ).status_code
                == 200
            )
            changed = dict(base, facts=["b"])
            duplicate = client.post("/v1/logic/evaluate", json=changed, headers=_auth())
            malformed = client.post(
                "/v1/logic/evaluate",
                json=dict(base, unexpected=True),
                headers=_auth(),
            )
    finally:
        runtime.close()

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_request"
    assert malformed.status_code == 422


def test_stage1_authenticated_metrics_report_real_runtime_state(
    tmp_path: Path,
) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "metrics.db",
        node_id="metrics-node",
        resource_profiler=_StaticProfiler(_profile()),  # type: ignore[arg-type]
    )
    request = {
        "request_id": "metrics-logic",
        "facts": ["a"],
        "rules": [],
        "query": "a",
    }
    try:
        with TestClient(create_app(_config(tmp_path), runtime=runtime)) as client:
            unauthorized = client.get("/v1/metrics")
            evaluated = client.post(
                "/v1/logic/evaluate",
                json=request,
                headers=_auth(),
            )
            metrics = client.get("/v1/metrics", headers=_auth())
    finally:
        runtime.close()

    assert unauthorized.status_code == 401
    assert evaluated.status_code == 200
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["service"]["requests_total"] >= 2
    assert payload["service"]["errors_total"] >= 1
    assert payload["service"]["logic_results"]["PROVED"] == 1
    assert payload["runtime"]["logic_proofs"] == 1
    assert payload["runtime"]["puzzles"] >= 1
    assert payload["runtime"]["homeostasis_state"] == "NORMAL"


def test_p01_solver_performance_is_measured(tmp_path: Path) -> None:
    service = _logic_service(tmp_path / "benchmark.db")
    rules = [
        {"id": f"r-{index}", "if": [f"n.{index}"], "then": f"n.{index + 1}"}
        for index in range(250)
    ]
    started = time.perf_counter()
    try:
        result = service.evaluate(
            request_id="benchmark-logic",
            facts=["n.0"],
            rules=rules,
            query="n.250",
        )
    finally:
        service.close()
    wall_ms = (time.perf_counter() - started) * 1_000

    assert result.status is LogicStatus.PROVED
    assert result.iterations == 250
    # Windows VM clocks can be coarsely quantized. Keep both measurements and
    # require the internal timer to stay within a narrow scheduling tolerance.
    assert result.elapsed_ms <= max(wall_ms * 3, wall_ms + 25)
    assert wall_ms < 2_000


def test_p02_real_profile_has_provenance_and_no_invented_metrics(
    tmp_path: Path,
) -> None:
    profile = ResourceProfiler(storage_path=tmp_path).profile()

    assert profile.cpu_count >= 1
    assert profile.sources["cpu"] == "os.cpu_count"
    assert profile.sources["storage"] == "shutil.disk_usage"
    assert profile.storage_free_mb is not None
    assert profile.hostname
    assert profile.operating_system
    assert profile.architecture
    assert profile.process_id > 0
    assert profile.cpu_usage_percent is not None
    assert profile.sources["cpu_usage"] == "psutil.cpu_percent"
    assert "accelerator" in profile.sources
    if profile.accelerator_available is True:
        assert profile.accelerator_name
        assert profile.accelerator_total_memory_mb is not None
        assert profile.accelerator_free_memory_mb is not None
    if profile.total_memory_mb is not None:
        assert profile.sources["total_memory"] == "psutil.virtual_memory"


def test_p02_unknown_metrics_fail_conservatively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    real_import = builtins.__import__

    def deny_psutil(name: str, *args: object, **kwargs: object) -> object:
        if name == "psutil":
            raise ImportError("test provider unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_psutil)
    profile = ResourceProfiler(storage_path=tmp_path / "missing").profile()
    budget = ResourceBudgetCalculator().calculate(profile)
    mode = ExecutionModeController().auto_determine_mode(profile)

    assert profile.total_memory_mb is None
    assert profile.available_memory_mb is None
    assert profile.storage_free_mb is None
    assert profile.complete is False
    assert budget.allow_network is False
    assert budget.allow_remote_offload is False
    assert mode is ExecutionMode.OFFLINE_SAFE


def test_p02_profile_changes_runtime_budget_and_mode() -> None:
    profiler = ResourceProfiler()
    profile = profiler.profile(
        override_total_mem_mb=2_048,
        override_available_mem_mb=256,
        network_available=False,
        power_mode="SAVER",
    )
    budget = ResourceBudgetCalculator().calculate(profile)
    mode = ExecutionModeController().auto_determine_mode(profile)

    assert profile.node_class is NodeClass.EDGE
    assert budget.max_memory_mb == 128
    assert budget.allow_network is False
    assert mode is ExecutionMode.OFFLINE_SAFE


def test_p02_profiler_overhead_is_measured(tmp_path: Path) -> None:
    profiler = ResourceProfiler(storage_path=tmp_path)
    started = time.perf_counter()
    samples = [profiler.profile() for _ in range(10)]
    average_ms = ((time.perf_counter() - started) * 1_000) / len(samples)

    assert all(sample.collected_at for sample in samples)
    assert average_ms < 250


def test_p05_state_transitions_hysteresis_and_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "homeostasis.db"
    store = HomeostasisEventStore(db_path)
    controller = LogicalHomeostasisController(store)
    assert (
        controller.evaluate(_profile(), logic_ready=True, memory_ready=True).state
        is HomeostasisState.NORMAL
    )
    assert (
        controller.evaluate(
            _profile(available_memory_mb=300), logic_ready=True, memory_ready=True
        ).state
        is HomeostasisState.DEGRADED
    )
    assert (
        controller.evaluate(
            _profile(available_memory_mb=600), logic_ready=True, memory_ready=True
        ).state
        is HomeostasisState.DEGRADED
    )
    assert (
        controller.evaluate(
            _profile(available_memory_mb=800), logic_ready=True, memory_ready=True
        ).state
        is HomeostasisState.NORMAL
    )
    assert store.count() == 2
    controller.close()

    restarted_store = HomeostasisEventStore(db_path)
    restarted = LogicalHomeostasisController(restarted_store)
    try:
        assert restarted.state is HomeostasisState.NORMAL
    finally:
        restarted.close()


def test_p05_runtime_safe_stop_blocks_logic(tmp_path: Path) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "safe-stop.db",
        node_id="critical-node",
        resource_profiler=_StaticProfiler(  # type: ignore[arg-type]
            _profile(available_memory_mb=32)
        ),
    )
    try:
        with pytest.raises(PureLogicError) as captured:
            runtime.reason_logic(
                request_id="blocked-logic",
                facts=["a"],
                rules=[],
                query="a",
            )
        assert runtime.homeostasis.state is HomeostasisState.SAFE_STOP
        assert runtime.homeostasis.store.count() == 1
    finally:
        runtime.close()

    assert captured.value.code is LogicFailureCode.RUNTIME_NOT_READY


def test_p05_corrupt_ledger_fails_closed_and_recovers_after_health(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "corrupt-homeostasis.db"
    first_store = HomeostasisEventStore(db_path)
    first = LogicalHomeostasisController(first_store)
    first.evaluate(
        _profile(available_memory_mb=300),
        logic_ready=True,
        memory_ready=True,
    )
    first.close()

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE homeostasis_transitions SET state = 'NORMAL'
            WHERE transition_id = (
                SELECT MAX(transition_id) FROM homeostasis_transitions
            )
            """
        )
        connection.commit()

    recovered_store = HomeostasisEventStore(db_path)
    recovered = LogicalHomeostasisController(recovered_store)
    try:
        assert recovered.state is HomeostasisState.SAFE_STOP
        assert recovered_store.corruption_count() == 1
        decision = recovered.evaluate(
            _profile(available_memory_mb=1_024),
            logic_ready=True,
            memory_ready=True,
        )
        assert decision.state is HomeostasisState.NORMAL
        assert "ledger_recovered_after_health_validation" in decision.reasons
    finally:
        recovered.close()

    final_store = HomeostasisEventStore(db_path)
    final = LogicalHomeostasisController(final_store)
    try:
        assert final.state is HomeostasisState.NORMAL
    finally:
        final.close()


def test_p05_thermal_and_power_signals_gate_runtime(tmp_path: Path) -> None:
    store = HomeostasisEventStore(tmp_path / "thermal.db")
    controller = LogicalHomeostasisController(store)
    try:
        thermal = controller.evaluate(
            _profile(thermal_celsius=96.0),
            logic_ready=True,
            memory_ready=True,
        )
        power = controller.evaluate(
            _profile(power_mode="CRITICAL"),
            logic_ready=True,
            memory_ready=True,
        )
        storage = controller.evaluate(
            _profile(storage_free_mb=16),
            logic_ready=True,
            memory_ready=True,
        )
        dependency = controller.evaluate(
            _profile(),
            logic_ready=False,
            memory_ready=False,
        )
    finally:
        controller.close()

    assert thermal.state is HomeostasisState.SAFE_STOP
    assert "thermal_critical" in thermal.reasons
    assert power.state is HomeostasisState.SAFE_STOP
    assert "power_critical" in power.reasons
    assert storage.state is HomeostasisState.SAFE_STOP
    assert "storage_critical" in storage.reasons
    assert dependency.state is HomeostasisState.SAFE_STOP
    assert "logic_unavailable" in dependency.reasons
    assert "memory_unavailable" in dependency.reasons


def test_p21_lingua_to_jayair_executes_supported_contract() -> None:
    expression, graph = text_to_ir("open desktop")
    result = JayaIRExecutor().execute_graph(graph)

    assert expression == ("ACTION", "OPEN", "desktop")
    assert result["ok"] is True
    assert result["result"]["target"] == "desktop"


def test_p21_unsupported_action_fails_closed() -> None:
    graph = logic_expr_to_ir(("ACTION", "TURN_ON", "lamp"))
    result = JayaIRExecutor().execute_graph(graph)

    assert result["ok"] is False
    assert result["error"] == "dependency_unavailable"


def test_p21_arithmetic_error_is_typed_and_not_fabricated() -> None:
    graph = logic_expr_to_ir(("QUERY", "ARITH", ("DIV", 8, 0)))
    result = JayaIRExecutor().execute_graph(graph)

    assert result["ok"] is False
    assert result["error"] == "divide_by_zero"


def test_p21_deterministic_replay_and_performance() -> None:
    executor = JayaIRExecutor()
    graph = logic_expr_to_ir(("QUERY", "ARITH", ("MUL", 7, 6)))
    started = time.perf_counter()
    first = executor.execute_graph(graph)
    second = executor.execute_graph(graph)
    wall_ms = (time.perf_counter() - started) * 1_000

    assert first["result"] == second["result"] == 42
    assert second["cache_hit"] is True
    assert wall_ms < 1_000


def test_stage1_canonical_launcher_builds_real_runtime(tmp_path: Path) -> None:
    config = _config(tmp_path)
    runtime = _build_runtime(config)
    try:
        assert runtime.is_ready() is True
        assert Path(runtime.episodic_memory.db_path) == (
            config.data_dir / "jaya_core_runtime.db"
        )
    finally:
        runtime.close()


def test_stage1_sqlite_backup_integrity_and_rollback(tmp_path: Path) -> None:
    data_dir = tmp_path / "core-data"
    data_dir.mkdir()
    database = data_dir / "runtime.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO state VALUES ('version-1')")
        connection.commit()

    manager = CoreSnapshotManager(data_dir)
    snapshot = manager.create(database)
    assert manager.verify(snapshot) is True

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE state SET value = 'version-2'")
        connection.commit()
    rollback = manager.rollback(snapshot)
    with closing(sqlite3.connect(database)) as connection:
        restored = connection.execute("SELECT value FROM state").fetchone()[0]

    assert restored == "version-1"
    assert rollback.operation == "ROLLBACK"
    assert rollback.parent_snapshot_id is not None
    assert manager.load_receipt(snapshot.snapshot_id) == snapshot


def test_stage1_tampered_snapshot_cannot_be_restored(tmp_path: Path) -> None:
    data_dir = tmp_path / "core-data"
    data_dir.mkdir()
    database = data_dir / "runtime.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO state VALUES ('safe')")

    manager = CoreSnapshotManager(data_dir)
    snapshot = manager.create(database)
    Path(snapshot.snapshot_path).write_bytes(b"tampered")

    assert manager.verify(snapshot) is False
    with pytest.raises(SnapshotError) as captured:
        manager.rollback(snapshot)
    assert captured.value.code is SnapshotFailureCode.INTEGRITY_FAILED


def test_p01_p21_pure_logic_is_consumed_through_jayair(tmp_path: Path) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "logic-ir.db",
        node_id="logic-ir-node",
        resource_profiler=_StaticProfiler(_profile()),  # type: ignore[arg-type]
    )
    try:
        graph = logic_request_to_ir(
            request_id="logic-ir-1",
            facts=["foundation.ready"],
            rules=[
                {
                    "id": "allow-reasoning",
                    "if": ["foundation.ready"],
                    "then": "reasoning.allowed",
                }
            ],
            query="reasoning.allowed",
        )
        result = runtime.reason_logic_ir(
            request_id="logic-ir-1",
            facts=["foundation.ready"],
            rules=[
                {
                    "id": "allow-reasoning",
                    "if": ["foundation.ready"],
                    "then": "reasoning.allowed",
                }
            ],
            query="reasoning.allowed",
        )
        unavailable = JayaIRExecutor().execute_graph(graph)
        events = runtime.episodic_memory.query_by_goal("logic-ir-1")
    finally:
        runtime.close()

    assert result["ok"] is True
    assert result["result"]["status"] == "PROVED"
    assert result["result"]["puzzle_receipt"]["capability_id"] == (
        "core.logic.evaluate"
    )
    assert events[0].event_type == "PURE_LOGIC_EVALUATED"
    assert unavailable["ok"] is False
    assert unavailable["error"] == "dependency_unavailable"


def test_p21_external_puzzle_is_discovered_and_connected_automatically(
    tmp_path: Path,
) -> None:
    puzzle_dir = tmp_path / "puzzles" / "turn-on"
    puzzle_dir.mkdir(parents=True)
    artifact = puzzle_dir / "adapter.py"
    artifact.write_text(
        """
class TurnOnPuzzle:
    def health_check(self):
        return True

    def invoke(self, payload):
        return {
            "accepted": True,
            "action": payload["action"],
            "target": payload["target"],
        }

def create_puzzle():
    return TurnOnPuzzle()
""".strip(),
        encoding="utf-8",
    )
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_path = puzzle_dir / "puzzle.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "puzzle_id": "device.turn-on",
                "capability_id": "action.turn_on",
                "version": "1.0.0",
                "artifact": "adapter.py",
                "artifact_sha256": digest,
                "entrypoint": "create_puzzle",
            }
        ),
        encoding="utf-8",
    )

    registry = CapabilityPuzzleRegistry((tmp_path / "puzzles",))
    policy = EthicalHeart(
        tmp_path / "p21-policy.db",
        PolicyBundle(
            policy_id="test.p21-policy",
            version=1,
            brain_id="brain-p21-test",
            rules=(
                PolicyRule(
                    rule_id="allow.turn-on-evidence",
                    effect=PolicyEffect.ALLOW,
                    capability_ids=("action.turn_on",),
                    risk_classes=(PolicyRisk.SECURITY_SENSITIVE,),
                    reason_code="P21_INTEGRATION_TEST_ALLOWED",
                ),
            ),
        ),
    )
    try:
        graph = logic_expr_to_ir(("ACTION", "TURN_ON", "lamp"))
        result = JayaIRExecutor(
            puzzle_registry=registry,
            policy_engine=policy,
            actor_brain_id="brain-p21-test",
            node_id="node-p21-test",
        ).execute_graph(graph)
        manifest_path.unlink()
        registry.refresh()
        with pytest.raises(PuzzleError) as removed:
            registry.invoke("action.turn_on", {})
    finally:
        registry.close()
        policy.close()

    assert result["ok"] is True
    assert result["result"]["accepted"] is True
    assert result["result"]["target"] == "lamp"
    assert result["result"]["puzzle_receipt"]["puzzle_id"] == "device.turn-on"
    assert removed.value.code is PuzzleFailureCode.CAPABILITY_UNAVAILABLE


def test_p21_puzzle_permission_fails_closed() -> None:
    class PermissionPuzzle:
        def health_check(self) -> bool:
            return True

        def invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"value": payload.get("value")}

    registry = CapabilityPuzzleRegistry()
    registry.attach(
        PuzzleManifest(
            puzzle_id="secure.sample",
            capability_id="secure.sample",
            version="1.0.0",
            permissions_required=("secure.invoke",),
        ),
        PermissionPuzzle(),
    )
    try:
        with pytest.raises(PuzzleError) as conflict:
            registry.attach(
                PuzzleManifest(
                    puzzle_id="secure.replacement",
                    capability_id="secure.sample",
                    version="1.0.0",
                ),
                PermissionPuzzle(),
            )
        with pytest.raises(PuzzleError) as denied:
            registry.invoke("secure.sample", {"value": 1})
        allowed = registry.invoke(
            "secure.sample",
            {"value": 1},
            granted_permissions=("secure.invoke",),
        )
    finally:
        registry.close()

    assert conflict.value.code is PuzzleFailureCode.CAPABILITY_CONFLICT
    assert denied.value.code is PuzzleFailureCode.PERMISSION_DENIED
    assert allowed.result["value"] == 1


def test_p21_puzzle_health_payload_and_timeout_fail_closed() -> None:
    class BoundaryPuzzle:
        def __init__(self) -> None:
            self.healthy = True

        def health_check(self) -> bool:
            return self.healthy

        def invoke(self, payload: dict[str, object]) -> dict[str, object]:
            if payload.get("slow"):
                time.sleep(0.05)
            return {"accepted": True}

    puzzle = BoundaryPuzzle()
    registry = CapabilityPuzzleRegistry()
    registry.attach(
        PuzzleManifest(
            puzzle_id="bounded.sample",
            capability_id="bounded.sample",
            version="1.0.0",
            timeout_seconds=0.01,
            max_payload_bytes=32,
        ),
        puzzle,
    )
    try:
        with pytest.raises(PuzzleError) as oversized:
            registry.invoke("bounded.sample", {"value": "x" * 64})
        with pytest.raises(PuzzleError) as timed_out:
            registry.invoke("bounded.sample", {"slow": True})
        with pytest.raises(PuzzleError) as invalid:
            registry.invoke("bounded.sample", {"value": object()})
        puzzle.healthy = False
        with pytest.raises(PuzzleError) as unhealthy:
            registry.invoke("bounded.sample", {})
    finally:
        registry.close()

    assert oversized.value.code is PuzzleFailureCode.PAYLOAD_TOO_LARGE
    assert timed_out.value.code is PuzzleFailureCode.INVOCATION_TIMEOUT
    assert invalid.value.code is PuzzleFailureCode.PAYLOAD_INVALID
    assert unhealthy.value.code is PuzzleFailureCode.ADAPTER_UNHEALTHY


def test_p21_tampered_external_puzzle_is_never_imported(tmp_path: Path) -> None:
    puzzle_dir = tmp_path / "puzzles" / "tampered"
    puzzle_dir.mkdir(parents=True)
    artifact = puzzle_dir / "adapter.py"
    artifact.write_text(
        "raise RuntimeError('must never be imported')\n",
        encoding="utf-8",
    )
    (puzzle_dir / "puzzle.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "puzzle_id": "tampered.sample",
                "capability_id": "tampered.sample",
                "version": "1.0.0",
                "artifact": "adapter.py",
                "artifact_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    registry = CapabilityPuzzleRegistry((tmp_path / "puzzles",))
    try:
        refresh = registry.refresh()
        with pytest.raises(PuzzleError) as unavailable:
            registry.invoke("tampered.sample", {})
    finally:
        registry.close()

    assert list(refresh.values()) == ["ARTIFACT_INTEGRITY_FAILED"]
    assert unavailable.value.code is PuzzleFailureCode.CAPABILITY_UNAVAILABLE
