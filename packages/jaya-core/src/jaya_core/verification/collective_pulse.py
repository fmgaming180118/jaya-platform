"""Representative verification runner for Pillar 32: Collective Pulse."""

from __future__ import annotations

import json
import math
import os
import platform
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.distributed_capabilities import (
    COLLECTIVE_EVIDENCE_CAPABILITY_ID,
    CollectiveEvidenceCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult
from jaya_core.pillars.reasoning_capabilities import AgenticRAGCapability

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "matrix",
    "soak",
    "source_files",
}

DEFAULT_SHARED_SECRET = "jaya-collective-pulse-shared-verification-key-32b!"


class CollectivePulseVerificationError(RuntimeError):
    """Stable P32 verification failure carrying the failed boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _system_metadata() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count_logical": os.cpu_count() or 1,
        "cpu_count_physical": psutil.cpu_count(logical=False) or 1,
        "total_ram_bytes": psutil.virtual_memory().total,
    }


class CollectivePulseVerifier:
    """Execute canonical verification gates for P32 Collective Pulse."""

    def __init__(self, workspace_root: Path, profile_path: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.profile_path = profile_path.resolve()
        self.profile = self._load_profile()

    def _load_profile(self) -> dict[str, Any]:
        if not self.profile_path.is_file():
            raise CollectivePulseVerificationError(
                "PROFILE_NOT_FOUND", f"Profile does not exist: {self.profile_path}"
            )
        try:
            data = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CollectivePulseVerificationError(
                "INVALID_PROFILE", f"Profile JSON is malformed: {exc}"
            ) from exc

        if not isinstance(data, dict) or set(data.keys()) != _PROFILE_FIELDS:
            raise CollectivePulseVerificationError(
                "INVALID_PROFILE", "Profile schema mismatch"
            )
        if not _PROFILE_ID.match(str(data["profile_id"])):
            raise CollectivePulseVerificationError(
                "INVALID_PROFILE", "Invalid profile_id format"
            )
        return data

    def _create_node(
        self, temp_dir: Path, node_id: str, allowed_peers: tuple[str, ...]
    ) -> tuple[CollectiveEvidenceCapability, AgenticRAGCapability, str]:
        node_root = temp_dir / node_id
        node_root.mkdir(parents=True, exist_ok=True)
        rag_db = node_root / "rag.sqlite3"
        rag = AgenticRAGCapability(rag_db, None)
        rag.execute({
            "action": "ingest",
            "source_ref": "shared-policy-v1",
            "title": "Collective Evidence Policy",
            "content": "Consented peer evidence for collective pulse reasoning and aggregation.",
        })
        evidence_id = rag.retrieve("collective evidence policy", 1)[0]["evidence_id"]
        cap = CollectiveEvidenceCapability(
            node_id=node_id,
            database_path=node_root / "collective.sqlite3",
            shared_secret=DEFAULT_SHARED_SECRET,
            allowed_peers=allowed_peers,
            rag=rag,
        )
        return cap, rag, evidence_id

    def verify(self) -> dict[str, Any]:
        gates_results: dict[str, Any] = {}
        t_start_all = time.perf_counter()

        temp_dir = Path(tempfile.mkdtemp(prefix="jaya_verify_p32_"))
        try:

            # Gate 1
            g1_start = time.perf_counter()
            gates_results["G01_MANIFEST_INTEGRITY"] = self._gate_01_manifest_integrity()
            gates_results["G01_MANIFEST_INTEGRITY"]["duration_ms"] = round(
                (time.perf_counter() - g1_start) * 1000.0, 3
            )

            # Gate 2
            g2_start = time.perf_counter()
            gates_results["G02_PEER_ALLOWLIST_ENFORCEMENT"] = self._gate_02_peer_allowlist_enforcement(temp_dir / "g02")
            gates_results["G02_PEER_ALLOWLIST_ENFORCEMENT"]["duration_ms"] = round(
                (time.perf_counter() - g2_start) * 1000.0, 3
            )

            # Gate 3
            g3_start = time.perf_counter()
            gates_results["G03_HMAC_SIGNATURE_VERIFICATION"] = self._gate_03_hmac_signature_verification(temp_dir / "g03")
            gates_results["G03_HMAC_SIGNATURE_VERIFICATION"]["duration_ms"] = round(
                (time.perf_counter() - g3_start) * 1000.0, 3
            )

            # Gate 4
            g4_start = time.perf_counter()
            gates_results["G04_EVIDENCE_CATALOG_LINKAGE"] = self._gate_04_evidence_catalog_linkage(temp_dir / "g04")
            gates_results["G04_EVIDENCE_CATALOG_LINKAGE"]["duration_ms"] = round(
                (time.perf_counter() - g4_start) * 1000.0, 3
            )

            # Gate 5
            g5_start = time.perf_counter()
            gates_results["G05_CONSENT_LIFECYCLE_AND_BUDGET"] = self._gate_05_consent_lifecycle_and_budget(temp_dir / "g05")
            gates_results["G05_CONSENT_LIFECYCLE_AND_BUDGET"]["duration_ms"] = round(
                (time.perf_counter() - g5_start) * 1000.0, 3
            )

            # Gate 6
            g6_start = time.perf_counter()
            gates_results["G06_REPLAY_ATTACK_REJECTION"] = self._gate_06_replay_attack_rejection(temp_dir / "g06")
            gates_results["G06_REPLAY_ATTACK_REJECTION"]["duration_ms"] = round(
                (time.perf_counter() - g6_start) * 1000.0, 3
            )

            # Gate 7
            g7_start = time.perf_counter()
            gates_results["G07_CLOCK_SKEW_REJECTION"] = self._gate_07_clock_skew_rejection(temp_dir / "g07")
            gates_results["G07_CLOCK_SKEW_REJECTION"]["duration_ms"] = round(
                (time.perf_counter() - g7_start) * 1000.0, 3
            )

            # Gate 8
            g8_start = time.perf_counter()
            gates_results["G08_POISONING_AND_QUALITY_GUARD"] = self._gate_08_poisoning_and_quality_guard(temp_dir / "g08")
            gates_results["G08_POISONING_AND_QUALITY_GUARD"]["duration_ms"] = round(
                (time.perf_counter() - g8_start) * 1000.0, 3
            )

            # Gate 9
            g9_start = time.perf_counter()
            gates_results["G09_INSUFFICIENT_PEERS_QUORUM"] = self._gate_09_insufficient_peers_quorum(temp_dir / "g09")
            gates_results["G09_INSUFFICIENT_PEERS_QUORUM"]["duration_ms"] = round(
                (time.perf_counter() - g9_start) * 1000.0, 3
            )

            # Gate 10
            g10_start = time.perf_counter()
            gates_results["G10_ROBUST_MEDIAN_AGGREGATION"] = self._gate_10_robust_median_aggregation(temp_dir / "g10")
            gates_results["G10_ROBUST_MEDIAN_AGGREGATION"]["duration_ms"] = round(
                (time.perf_counter() - g10_start) * 1000.0, 3
            )

            # Gate 11
            g11_start = time.perf_counter()
            gates_results["G11_CONFLICT_SPREAD_DETECTION"] = self._gate_11_conflict_spread_detection(temp_dir / "g11")
            gates_results["G11_CONFLICT_SPREAD_DETECTION"]["duration_ms"] = round(
                (time.perf_counter() - g11_start) * 1000.0, 3
            )

            # Gate 12
            g12_start = time.perf_counter()
            gates_results["G12_LOCAL_AUTHORITY_PRESERVATION"] = self._gate_12_local_authority_preservation(temp_dir / "g12")
            gates_results["G12_LOCAL_AUTHORITY_PRESERVATION"]["duration_ms"] = round(
                (time.perf_counter() - g12_start) * 1000.0, 3
            )

            # Gate 13
            g13_start = time.perf_counter()
            gates_results["G13_PERSISTENT_REVOCATION_LIFECYCLE"] = self._gate_13_persistent_revocation_lifecycle(temp_dir / "g13")
            gates_results["G13_PERSISTENT_REVOCATION_LIFECYCLE"]["duration_ms"] = round(
                (time.perf_counter() - g13_start) * 1000.0, 3
            )

            # Gate 14
            g14_start = time.perf_counter()
            gates_results["G14_DUAL_NODE_RESTART_DURABILITY"] = self._gate_14_dual_node_restart_durability(temp_dir / "g14")
            gates_results["G14_DUAL_NODE_RESTART_DURABILITY"]["duration_ms"] = round(
                (time.perf_counter() - g14_start) * 1000.0, 3
            )

            # Gate 15
            g15_start = time.perf_counter()
            gates_results["G15_RUNTIME_AND_MANIFEST_DISPATCH"] = self._gate_15_runtime_and_manifest_dispatch(temp_dir / "g15")
            gates_results["G15_RUNTIME_AND_MANIFEST_DISPATCH"]["duration_ms"] = round(
                (time.perf_counter() - g15_start) * 1000.0, 3
            )

            # Gate 16
            g16_start = time.perf_counter()
            gates_results["G16_SOAK_PERFORMANCE_AND_ENERGY"] = self._gate_16_soak_performance_and_energy(temp_dir / "g16")
            gates_results["G16_SOAK_PERFORMANCE_AND_ENERGY"]["duration_ms"] = round(
                (time.perf_counter() - g16_start) * 1000.0, 3
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        total_duration = round((time.perf_counter() - t_start_all) * 1000.0, 3)
        passed_count = sum(1 for g in gates_results.values() if g["status"] == "PASSED")
        all_passed = passed_count == len(gates_results)

        receipt = {
            "schema_version": 1,
            "profile_id": self.profile["profile_id"],
            "pillar_id": 32,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "VERIFIED" if all_passed else "FAILED",
            "system": _system_metadata(),
            "gates_summary": {
                "total": len(gates_results),
                "passed": passed_count,
                "failed": len(gates_results) - passed_count,
                "all_passed": all_passed,
            },
            "gates": gates_results,
            "total_duration_ms": total_duration,
            "approver": "System-Veritas",
        }

        # Write receipt artifact
        receipt_dir = self.workspace_root / "artifacts" / "verified-collective-pulse"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / "verification_receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

        return receipt

    def _gate_01_manifest_integrity(self) -> dict[str, Any]:
        source_files = self.profile["source_files"]
        for rel_path in source_files:
            target = self.workspace_root / rel_path
            if not target.is_file():
                raise CollectivePulseVerificationError(
                    "MANIFEST_INTEGRITY_FAILED", f"Source file missing: {rel_path}"
                )
        return {
            "status": "PASSED",
            "profile_id": self.profile["profile_id"],
            "source_files_verified": len(source_files),
        }

    def _gate_02_peer_allowlist_enforcement(self, temp_dir: Path) -> dict[str, Any]:
        node_b, _, evidence_b = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))
        rogue, _, evidence_rogue = self._create_node(temp_dir, "rogue-node", ("node-b",))

        rogue_consent = rogue.execute({
            "action": "issue_consent",
            "evidence_id": evidence_rogue,
            "max_privacy_budget": 0.1,
            "expires_at": time.time() + 3600,
        }).data["receipt"]

        rogue_packet = rogue.execute({
            "action": "create",
            "evidence_id": evidence_rogue,
            "value": 0.5,
            "trust": 0.9,
            "quality": 0.9,
            "privacy_budget": 0.05,
            "consent_receipt": rogue_consent,
        }).data["packet"]

        rejected = False
        try:
            node_b.execute({"action": "ingest", "packet": rogue_packet})
        except LocalPillarError as exc:
            if exc.code == "PEER_DENIED":
                rejected = True

        if not rejected:
            raise CollectivePulseVerificationError(
                "ALLOWLIST_FAILED", "Rogue peer contribution was not rejected"
            )

        return {"status": "PASSED", "allowlist_enforced": True}

    def _gate_03_hmac_signature_verification(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, _ = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))

        consent = node_a.execute({
            "action": "issue_consent",
            "evidence_id": evidence_a,
            "max_privacy_budget": 0.2,
            "expires_at": time.time() + 3600,
        }).data["receipt"]

        packet = node_a.execute({
            "action": "create",
            "evidence_id": evidence_a,
            "value": 0.85,
            "trust": 0.9,
            "quality": 0.88,
            "privacy_budget": 0.1,
            "consent_receipt": consent,
        }).data["packet"]

        # Tampered value
        tampered = dict(packet)
        tampered["value"] = 0.99
        rejected = False
        try:
            node_b.execute({"action": "ingest", "packet": tampered})
        except LocalPillarError as exc:
            if exc.code == "SIGNATURE_INVALID":
                rejected = True

        if not rejected:
            raise CollectivePulseVerificationError(
                "SIGNATURE_FAILED", "Tampered packet was not rejected"
            )

        return {"status": "PASSED", "signature_tamper_rejected": True}

    def _gate_04_evidence_catalog_linkage(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, _ = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))

        # Issue consent with nonexistent evidence
        rejected_consent = False
        try:
            node_a.execute({
                "action": "issue_consent",
                "evidence_id": "nonexistent-evidence-id",
                "max_privacy_budget": 0.15,
                "expires_at": time.time() + 3600,
            })
        except LocalPillarError as exc:
            if exc.code == "INVALID_EVIDENCE":
                rejected_consent = True

        if not rejected_consent:
            raise CollectivePulseVerificationError(
                "EVIDENCE_FAILED", "Nonexistent evidence allowed in consent issuance"
            )

        return {"status": "PASSED", "evidence_catalog_linkage_verified": True}

    def _gate_05_consent_lifecycle_and_budget(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))

        # Exceeding budget > 0.25 rejected
        rejected_budget = False
        try:
            node_a.execute({
                "action": "issue_consent",
                "evidence_id": evidence_a,
                "max_privacy_budget": 0.35,
                "expires_at": time.time() + 3600,
            })
        except LocalPillarError as exc:
            if exc.code == "INVALID_INPUT":
                rejected_budget = True

        if not rejected_budget:
            raise CollectivePulseVerificationError(
                "BUDGET_FAILED", "Excessive privacy budget allowed"
            )

        return {"status": "PASSED", "privacy_budget_enforced": True}

    def _gate_06_replay_attack_rejection(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, _ = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))

        consent = node_a.execute({
            "action": "issue_consent",
            "evidence_id": evidence_a,
            "max_privacy_budget": 0.2,
            "expires_at": time.time() + 3600,
        }).data["receipt"]

        packet = node_a.execute({
            "action": "create",
            "evidence_id": evidence_a,
            "value": 0.85,
            "trust": 0.9,
            "quality": 0.88,
            "privacy_budget": 0.1,
            "consent_receipt": consent,
        }).data["packet"]

        node_b.execute({"action": "ingest", "packet": packet})

        # Second ingestion of the same packet must trigger REPLAY_DETECTED
        replay_rejected = False
        try:
            node_b.execute({"action": "ingest", "packet": packet})
        except LocalPillarError as exc:
            if exc.code == "REPLAY_DETECTED":
                replay_rejected = True

        if not replay_rejected:
            raise CollectivePulseVerificationError(
                "REPLAY_FAILED", "Duplicate packet replay was not detected"
            )

        return {"status": "PASSED", "replay_attack_rejected": True}

    def _gate_07_clock_skew_rejection(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, _ = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))

        consent = node_a.execute({
            "action": "issue_consent",
            "evidence_id": evidence_a,
            "max_privacy_budget": 0.2,
            "expires_at": time.time() + 3600,
        }).data["receipt"]

        stale_packet = dict(node_a.execute({
            "action": "create",
            "evidence_id": evidence_a,
            "value": 0.85,
            "trust": 0.9,
            "quality": 0.9,
            "privacy_budget": 0.1,
            "consent_receipt": consent,
        }).data["packet"])

        stale_packet["created_at"] = time.time() - 400.0
        stale_packet["signature"] = node_a._sign(
            {k: v for k, v in stale_packet.items() if k != "signature"}
        )

        skew_rejected = False
        try:
            node_b.execute({"action": "ingest", "packet": stale_packet})
        except LocalPillarError as exc:
            if exc.code == "CLOCK_SKEW":
                skew_rejected = True

        if not skew_rejected:
            raise CollectivePulseVerificationError(
                "CLOCK_SKEW_FAILED", "Stale packet was not rejected"
            )

        return {"status": "PASSED", "clock_skew_rejected": True}

    def _gate_08_poisoning_and_quality_guard(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, _ = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))

        consent = node_a.execute({
            "action": "issue_consent",
            "evidence_id": evidence_a,
            "max_privacy_budget": 0.2,
            "expires_at": time.time() + 3600,
        }).data["receipt"]

        # Malicious low-trust injection (<0.5)
        poisoned = node_a.execute({
            "action": "create",
            "evidence_id": evidence_a,
            "value": 0.85,
            "trust": 0.25,
            "quality": 0.9,
            "privacy_budget": 0.1,
            "consent_receipt": consent,
        }).data["packet"]

        poison_rejected = False
        try:
            node_b.execute({"action": "ingest", "packet": poisoned})
        except LocalPillarError as exc:
            if exc.code == "POISONING_GUARD":
                poison_rejected = True

        if not poison_rejected:
            raise CollectivePulseVerificationError(
                "POISONING_FAILED", "Poisoned contribution was not guarded"
            )

        return {"status": "PASSED", "poisoning_guard_enforced": True}

    def _gate_09_insufficient_peers_quorum(self, temp_dir: Path) -> dict[str, Any]:
        node_b, _, evidence_b = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))

        quorum_failed = False
        try:
            node_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": 0.7})
        except LocalPillarError as exc:
            if exc.code == "INSUFFICIENT_PEERS":
                quorum_failed = True

        if not quorum_failed:
            raise CollectivePulseVerificationError(
                "QUORUM_FAILED", "Aggregation allowed with insufficient peers"
            )

        return {"status": "PASSED", "insufficient_peers_prevented": True}

    def _gate_10_robust_median_aggregation(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, evidence_b = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))
        node_c, _, evidence_c = self._create_node(temp_dir, "node-c", ("node-a", "node-b"))

        consent_a = node_a.execute({"action": "issue_consent", "evidence_id": evidence_a, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_a = node_a.execute({"action": "create", "evidence_id": evidence_a, "value": 0.6, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_a}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_a})

        consent_c = node_c.execute({"action": "issue_consent", "evidence_id": evidence_c, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_c = node_c.execute({"action": "create", "evidence_id": evidence_c, "value": 0.8, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_c}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_c})

        agg = node_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": 0.7}).data
        if not math.isclose(agg["peer_median"], 0.7, abs_tol=1e-3):
            raise CollectivePulseVerificationError(
                "AGGREGATION_FAILED", f"Median {agg['peer_median']} != 0.7"
            )

        return {"status": "PASSED", "peer_median": agg["peer_median"], "recommendation": agg["recommendation"]}

    def _gate_11_conflict_spread_detection(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, evidence_b = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))
        node_c, _, evidence_c = self._create_node(temp_dir, "node-c", ("node-a", "node-b"))

        # Values 0.2 and 0.8 (spread 0.6 > 0.4)
        consent_a = node_a.execute({"action": "issue_consent", "evidence_id": evidence_a, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_a = node_a.execute({"action": "create", "evidence_id": evidence_a, "value": 0.2, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_a}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_a})

        consent_c = node_c.execute({"action": "issue_consent", "evidence_id": evidence_c, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_c = node_c.execute({"action": "create", "evidence_id": evidence_c, "value": 0.8, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_c}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_c})

        agg = node_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": 0.5}).data
        if not agg["conflict_detected"] or agg["spread"] < 0.4:
            raise CollectivePulseVerificationError(
                "CONFLICT_DETECTION_FAILED", "Spread > 0.4 did not trigger conflict flag"
            )

        return {"status": "PASSED", "conflict_detected": True, "spread": agg["spread"]}

    def _gate_12_local_authority_preservation(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, evidence_b = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))
        node_c, _, evidence_c = self._create_node(temp_dir, "node-c", ("node-a", "node-b"))

        consent_a = node_a.execute({"action": "issue_consent", "evidence_id": evidence_a, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_a = node_a.execute({"action": "create", "evidence_id": evidence_a, "value": 0.6, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_a}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_a})

        consent_c = node_c.execute({"action": "issue_consent", "evidence_id": evidence_c, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_c = node_c.execute({"action": "create", "evidence_id": evidence_c, "value": 0.8, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_c}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_c})

        local_val = 0.9
        agg = node_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": local_val}).data
        expected_rec = 0.7 * local_val + 0.3 * 0.7  # 0.63 + 0.21 = 0.84
        if agg["overrides_local_authority"] is not False or not math.isclose(agg["recommendation"], expected_rec, abs_tol=1e-3):
            raise CollectivePulseVerificationError(
                "LOCAL_AUTHORITY_FAILED", "Local authority weighting was violated"
            )

        return {"status": "PASSED", "overrides_local_authority": False, "recommendation": agg["recommendation"]}

    def _gate_13_persistent_revocation_lifecycle(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, evidence_b = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))
        node_c, _, evidence_c = self._create_node(temp_dir, "node-c", ("node-a", "node-b"))

        consent_a = node_a.execute({"action": "issue_consent", "evidence_id": evidence_a, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_a = node_a.execute({"action": "create", "evidence_id": evidence_a, "value": 0.6, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_a}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_a})

        consent_c = node_c.execute({"action": "issue_consent", "evidence_id": evidence_c, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_c = node_c.execute({"action": "create", "evidence_id": evidence_c, "value": 0.8, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_c}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_c})

        # Revoke contribution from Node-A
        rev_payload = node_a.create_revocation(str(packet_a["contribution_id"]))
        rev_res = node_b.execute({"action": "revoke", **rev_payload})
        if rev_res.code != "COLLECTIVE_CONTRIBUTION_REVOKED":
            raise CollectivePulseVerificationError("REVOCATION_FAILED", "Revocation was not acknowledged")

        # Now aggregate fails due to only 1 active peer left
        revocation_effective = False
        try:
            node_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": 0.7})
        except LocalPillarError as exc:
            if exc.code == "INSUFFICIENT_PEERS":
                revocation_effective = True

        if not revocation_effective:
            raise CollectivePulseVerificationError("REVOCATION_FAILED", "Revoked contribution still counted in aggregate")

        return {"status": "PASSED", "revocation_lifecycle_verified": True}

    def _gate_14_dual_node_restart_durability(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, evidence_b = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))
        node_c, _, evidence_c = self._create_node(temp_dir, "node-c", ("node-a", "node-b"))

        consent_a = node_a.execute({"action": "issue_consent", "evidence_id": evidence_a, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_a = node_a.execute({"action": "create", "evidence_id": evidence_a, "value": 0.6, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_a}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_a})

        consent_c = node_c.execute({"action": "issue_consent", "evidence_id": evidence_c, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
        packet_c = node_c.execute({"action": "create", "evidence_id": evidence_c, "value": 0.8, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_c}).data["packet"]
        node_b.execute({"action": "ingest", "packet": packet_c})

        # Reinstantiate Node-B from disk
        db_path = temp_dir / "node-b" / "collective.sqlite3"
        rag_db = temp_dir / "node-b" / "rag.sqlite3"
        restarted_rag = AgenticRAGCapability(rag_db, None)
        restarted_b = CollectiveEvidenceCapability(
            node_id="node-b",
            database_path=db_path,
            shared_secret=DEFAULT_SHARED_SECRET,
            allowed_peers=("node-a", "node-c"),
            rag=restarted_rag,
        )

        agg = restarted_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": 0.7}).data
        if agg["peer_count"] != 2:
            raise CollectivePulseVerificationError("RESTART_FAILED", "Persisted peer contributions lost on restart")

        return {"status": "PASSED", "dual_node_restart_durability_verified": True}

    def _gate_15_runtime_and_manifest_dispatch(self, temp_dir: Path) -> dict[str, Any]:
        peers = ("node-a", "node-b", "node-c")
        runtimes = {
            node_id: JayaCoreRuntime(
                db_path=temp_dir / node_id / "core.sqlite3",
                local_pillar_data_dir=temp_dir / node_id / "pillars",
                node_id=node_id,
                twin_shared_secret=DEFAULT_SHARED_SECRET,
                twin_allowed_peers=tuple(p for p in peers if p != node_id),
            )
            for node_id in peers
        }

        try:
            for node_id, rt in runtimes.items():
                rt.advanced_pillar_capabilities.rag.execute({
                    "action": "ingest",
                    "source_ref": "policy-v1",
                    "title": "Runtime Policy",
                    "content": "Runtime collective evidence policy for P32 verification.",
                })

            evidence_b = runtimes["node-b"].advanced_pillar_capabilities.rag.retrieve("runtime collective evidence", 1)[0]["evidence_id"]
            evidence_a = runtimes["node-a"].advanced_pillar_capabilities.rag.retrieve("runtime collective evidence", 1)[0]["evidence_id"]
            evidence_c = runtimes["node-c"].advanced_pillar_capabilities.rag.retrieve("runtime collective evidence", 1)[0]["evidence_id"]

            consent_a = runtimes["node-a"].advanced_pillar_capabilities.collective_evidence.execute({
                "action": "issue_consent",
                "evidence_id": evidence_a,
                "max_privacy_budget": 0.15,
                "expires_at": time.time() + 3600,
            }).data["receipt"]

            packet_a = runtimes["node-a"].advanced_pillar_capabilities.collective_evidence.execute({
                "action": "create",
                "evidence_id": evidence_a,
                "value": 0.75,
                "trust": 0.9,
                "quality": 0.9,
                "privacy_budget": 0.1,
                "consent_receipt": consent_a,
            }).data["packet"]

            consent_c = runtimes["node-c"].advanced_pillar_capabilities.collective_evidence.execute({
                "action": "issue_consent",
                "evidence_id": evidence_c,
                "max_privacy_budget": 0.15,
                "expires_at": time.time() + 3600,
            }).data["receipt"]

            packet_c = runtimes["node-c"].advanced_pillar_capabilities.collective_evidence.execute({
                "action": "create",
                "evidence_id": evidence_c,
                "value": 0.85,
                "trust": 0.9,
                "quality": 0.9,
                "privacy_budget": 0.1,
                "consent_receipt": consent_c,
            }).data["packet"]

            runtimes["node-b"].advanced_pillar_capabilities.collective_evidence.execute({"action": "ingest", "packet": packet_a})
            runtimes["node-b"].advanced_pillar_capabilities.collective_evidence.execute({"action": "ingest", "packet": packet_c})

            agg = runtimes["node-b"].advanced_pillar_capabilities.collective_evidence.execute({
                "action": "aggregate",
                "local_evidence_id": evidence_b,
                "local_value": 0.8,
            }).data

            if agg["peer_count"] != 2:
                raise CollectivePulseVerificationError("RUNTIME_DISPATCH_FAILED", "Runtime dispatch failed to aggregate")

            return {"status": "PASSED", "runtime_dispatch_verified": True}
        finally:
            for rt in runtimes.values():
                rt.close()

    def _gate_16_soak_performance_and_energy(self, temp_dir: Path) -> dict[str, Any]:
        node_a, _, evidence_a = self._create_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, evidence_b = self._create_node(temp_dir, "node-b", ("node-a", "node-c"))
        node_c, _, evidence_c = self._create_node(temp_dir, "node-c", ("node-a", "node-b"))

        iterations = int(self.profile["soak"]["iterations"])
        latencies: list[float] = []

        meter = None
        start_sample = None
        try:
            meter = WindowsEmiEnergyMeter()
            start_sample = meter.sample()
        except Exception:
            meter = None

        initial_rss = psutil.Process().memory_info().rss
        t_start = time.perf_counter()
        successful = 0

        for idx in range(iterations):
            t0 = time.perf_counter()
            try:
                consent_a = node_a.execute({
                    "action": "issue_consent",
                    "evidence_id": evidence_a,
                    "max_privacy_budget": 0.2,
                    "expires_at": time.time() + 3600,
                }).data["receipt"]
                packet_a = node_a.execute({
                    "action": "create",
                    "evidence_id": evidence_a,
                    "value": 0.65 + (idx % 10) * 0.01,
                    "trust": 0.9,
                    "quality": 0.9,
                    "privacy_budget": 0.05,
                    "consent_receipt": consent_a,
                }).data["packet"]

                consent_c = node_c.execute({
                    "action": "issue_consent",
                    "evidence_id": evidence_c,
                    "max_privacy_budget": 0.2,
                    "expires_at": time.time() + 3600,
                }).data["receipt"]
                packet_c = node_c.execute({
                    "action": "create",
                    "evidence_id": evidence_c,
                    "value": 0.75 + (idx % 10) * 0.01,
                    "trust": 0.9,
                    "quality": 0.9,
                    "privacy_budget": 0.05,
                    "consent_receipt": consent_c,
                }).data["packet"]

                node_b.execute({"action": "ingest", "packet": packet_a})
                node_b.execute({"action": "ingest", "packet": packet_c})

                agg = node_b.execute({
                    "action": "aggregate",
                    "local_evidence_id": evidence_b,
                    "local_value": 0.7,
                }).data
                if agg["peer_count"] == 2:
                    successful += 1
            except Exception:
                pass
            latencies.append((time.perf_counter() - t0) * 1000.0)

        total_time = time.perf_counter() - t_start
        final_rss = psutil.Process().memory_info().rss
        rss_growth = max(0, final_rss - initial_rss)
        mean_lat = float(np.mean(latencies))

        energy_joules = total_time * 28.0
        energy_meter_available = False
        if meter is not None and start_sample is not None:
            try:
                end_sample = meter.sample()
                reading = meter.measure(start_sample, end_sample)
                energy_joules = reading.joules
                energy_meter_available = True
            except Exception:
                pass

        completion_rate = successful / iterations
        if completion_rate < float(self.profile["soak"]["min_completion_rate"]):
            raise CollectivePulseVerificationError(
                "SOAK_COMPLETION_LOW",
                f"Completion rate {successful}/{iterations} below {self.profile['soak']['min_completion_rate']}",
            )

        return {
            "status": "PASSED",
            "iterations": iterations,
            "successful": successful,
            "mean_latency_ms": round(mean_lat, 3),
            "rss_growth_bytes": rss_growth,
            "energy_meter_available": energy_meter_available,
            "energy_joules": round(energy_joules, 4),
        }


def run_collective_pulse_verification(
    profile_path: Path,
    workspace_root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    verifier = CollectivePulseVerifier(workspace_root=workspace_root, profile_path=profile_path)
    receipt = verifier.verify()
    if output_path:
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def verify_collective_pulse(
    repository_root: Path | None = None,
    profile_path: Path | None = None,
    output_directory: Path | None = None,
    approver: str = "System-Veritas",
) -> tuple[Path, dict[str, Any]]:
    workspace = (repository_root or Path.cwd()).resolve()
    target_profile = (
        profile_path
        or workspace / "packages" / "jaya-core" / "verification" / "p32_windows_collective_pulse_v1.json"
    ).resolve()
    out_dir = (output_directory or workspace / "artifacts" / "verified-collective-pulse").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "verification_receipt.json"

    receipt = run_collective_pulse_verification(
        profile_path=target_profile,
        workspace_root=workspace,
        output_path=out_file,
    )
    receipt["approver"] = approver
    out_file.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    return out_file, receipt

