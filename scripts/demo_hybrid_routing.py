#!/usr/bin/env python3
"""Interactive vertical slice demo for Pillar 37: Hybrid Consciousness."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability  # noqa: E402
from jaya_core.pillars.control_capabilities import (  # noqa: E402
    HYBRID_CAPABILITY_ID,
    HybridRoutingCapability,
    RemoteModelProviderProtocol,
)
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability  # noqa: E402
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402
from jaya_core.pillars.media_capability import MediaObservationCapability  # noqa: E402


class DemoLocalRetrievalProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {
            "answer": f"Local model synthesis: {evidence[0]['content']}",
            "citations": [evidence[0]["evidence_id"]],
        }


class DemoRemoteModelProvider(RemoteModelProviderProtocol):
    provider_type = "REMOTE_MODEL"

    def __init__(self, healthy: bool = True, should_fail: bool = False) -> None:
        self.healthy = healthy
        self.should_fail = should_fail

    def health_check(self) -> bool:
        return self.healthy

    def ask(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if not self.healthy or self.should_fail:
            raise RuntimeError("Cloud upstream unavailable (503 Service Unavailable)")
        prompt = payload.get("prompt", payload.get("question", ""))
        return {
            "answer": f"Remote model generated answer for: {prompt}",
            "model_id": "cloud-reasoning-v1",
            "citations": ["remote-ref-001"],
            "usage": {"prompt_tokens": 12, "completion_tokens": 18},
        }


def run_demo() -> None:
    print("=" * 80)
    print("  JAYA SYSTEM — PILAR 37: HYBRID CONSCIOUSNESS VERTICAL SLICE DEMO")
    print("=" * 80)

    work_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_p37_"))
    db_path = work_dir / "hybrid_routing.sqlite3"
    rag_db = work_dir / "rag.sqlite3"
    media_db = work_dir / "media.sqlite3"
    media_root = work_dir / "media"
    media_root.mkdir(parents=True, exist_ok=True)

    try:
        # -------------------------------------------------------------
        # STAGE 1: Capability Initialization and Provider Setup
        # -------------------------------------------------------------
        print("\n[STAGE 1] Initializing Hybrid Consciousness and Real Production Adapters...")
        rag = AgenticRAGCapability(rag_db, DemoLocalRetrievalProvider())
        sandbox = SandboxedImaginationCapability()
        media = MediaObservationCapability(root=media_root, database_path=media_db)
        remote_provider = DemoRemoteModelProvider(healthy=True)

        router = HybridRoutingCapability(
            database_path=db_path,
            rag=rag,
            sandbox=sandbox,
            media=media,
            remote_provider=remote_provider,
            offline_mode=False,
        )

        providers = router.list_providers()
        print(f"  -> Capability ID: {HYBRID_CAPABILITY_ID}")
        print(f"  -> Database: {db_path.name}")
        print(f"  -> Registered Providers ({len(providers)}):")
        for p in providers:
            print(f"     - [{p['provider_type']}] Name: {p['provider_name']}, Health: {p['health_status']}")

        # -------------------------------------------------------------
        # STAGE 2: Deterministic Rule-Based Route Execution
        # -------------------------------------------------------------
        print("\n[STAGE 2] Routing Rule-Based Expression (Pure Deterministic Sandbox)...")
        rule_req = {
            "action": "route",
            "request_kind": "expression",
            "sensitivity": "restricted",
            "payload": {"expression": "42 * 2 + 10"},
        }
        rule_res = router.execute(rule_req)
        print(f"  -> Provider Type: {rule_res.data['provider_type']}")
        print(f"  -> Route ID: {rule_res.data['route_id']}")
        print(f"  -> Result Value: {rule_res.data['result']['result']}")
        print(f"  -> Latency: {rule_res.data['latency_ns'] / 1e6:.3f} ms")
        print(f"  -> State Result Digest: {rule_res.data['result_digest'][:16]}...")
        assert rule_res.data["provider_type"] == "RULE_BASED"
        assert rule_res.data["result"]["result"] == 94

        # -------------------------------------------------------------
        # STAGE 3: Grounded Retrieval Route Execution
        # -------------------------------------------------------------
        print("\n[STAGE 3] Ingesting Evidence and Routing to Grounded Retrieval...")
        rag.execute(
            {
                "action": "ingest",
                "source_ref": "manual://flight-rules",
                "title": "Flight Rules v3",
                "content": "Flight rule 304: Battery reserve must stay above 25% at orbital insertion.",
            }
        )
        retrieval_req = {
            "action": "route",
            "request_kind": "retrieval",
            "sensitivity": "internal",
            "payload": {"query": "battery reserve"},
        }
        ret_res = router.execute(retrieval_req)
        evidence_found = ret_res.data["result"]["evidence"]
        print(f"  -> Provider Type: {ret_res.data['provider_type']}")
        print(f"  -> Route ID: {ret_res.data['route_id']}")
        print(f"  -> Evidence Count: {len(evidence_found)}")
        print(f"  -> First Match: {evidence_found[0]['content'][:65]}...")
        print(f"  -> Citations: {ret_res.data['citations']}")
        assert ret_res.data["provider_type"] == "RETRIEVAL"
        assert len(ret_res.data["citations"]) > 0

        # -------------------------------------------------------------
        # STAGE 4: Grounded Local Model Route Execution
        # -------------------------------------------------------------
        print("\n[STAGE 4] Routing to Grounded Local Model Adapter...")
        local_req = {
            "action": "route",
            "request_kind": "grounded_answer",
            "sensitivity": "internal",
            "payload": {"question": "What is the requirement for battery reserve at orbital insertion?"},
        }
        local_res = router.execute(local_req)
        print(f"  -> Provider Type: {local_res.data['provider_type']}")
        print(f"  -> Route ID: {local_res.data['route_id']}")
        print(f"  -> Answer: {local_res.data['result']['answer']}")
        print(f"  -> Citations: {local_res.data['citations']}")
        assert local_res.data["provider_type"] == "LOCAL_MODEL"
        assert len(local_res.data["citations"]) > 0

        # -------------------------------------------------------------
        # STAGE 5: Authorized Remote Model Route Execution
        # -------------------------------------------------------------
        print("\n[STAGE 5] Routing to Authorized Remote Cloud Model...")
        remote_req = {
            "action": "route",
            "request_kind": "remote_answer",
            "sensitivity": "public",
            "payload": {"prompt": "Optimize delta-v for Hohmann transfer to Mars"},
        }
        remote_res = router.execute(remote_req)
        print(f"  -> Provider Type: {remote_res.data['provider_type']}")
        print(f"  -> Route ID: {remote_res.data['route_id']}")
        print(f"  -> Answer: {remote_res.data['result']['answer']}")
        print(f"  -> Model: {remote_res.data['result']['model_id']}")
        assert remote_res.data["provider_type"] == "REMOTE_MODEL"

        # -------------------------------------------------------------
        # STAGE 6: Privacy Gating (Restricted Sensitivity Blocks Egress)
        # -------------------------------------------------------------
        print("\n[STAGE 6] Testing Privacy Gating on RESTRICTED Data Egress...")
        priv_req = {
            "action": "route",
            "request_kind": "remote_answer",
            "sensitivity": "restricted",
            "payload": {"prompt": "CONFIDENTIAL mission parameters and telemetry keys"},
            "allow_fallback": False,
        }
        try:
            router.execute(priv_req)
            raise AssertionError("Should have raised LocalPillarError for PRIVACY_DENIAL")
        except LocalPillarError as exc:
            print(f"  -> Successfully Blocked Remote Egress: {exc.code} - {exc}")
            assert exc.code == "PRIVACY_DENIAL"

        # -------------------------------------------------------------
        # STAGE 7: Offline Mode Enforcement
        # -------------------------------------------------------------
        print("\n[STAGE 7] Testing Offline Mode Enforcement...")
        offline_router = HybridRoutingCapability(
            database_path=db_path,
            rag=rag,
            sandbox=sandbox,
            media=media,
            remote_provider=remote_provider,
            offline_mode=True,
        )
        off_req = {
            "action": "route",
            "request_kind": "remote_answer",
            "sensitivity": "public",
            "payload": {"prompt": "Attempt remote query when offline"},
            "allow_fallback": False,
        }
        try:
            offline_router.execute(off_req)
            raise AssertionError("Should have raised LocalPillarError for OFFLINE_REQUIRED")
        except LocalPillarError as exc:
            print(f"  -> Successfully Enforced Offline Safety: {exc.code} - {exc}")
            assert exc.code == "OFFLINE_REQUIRED"

        # -------------------------------------------------------------
        # STAGE 8: Transparent Failover Chain
        # -------------------------------------------------------------
        print("\n[STAGE 8] Testing Capable Failover Chain (Offline Remote -> Local Model)...")
        failover_req = {
            "action": "route",
            "request_kind": "remote_answer",
            "sensitivity": "public",
            "payload": {"question": "What is the requirement for battery reserve?"},
            "allow_fallback": True,
        }
        fo_res = offline_router.execute(failover_req)
        print(f"  -> Final Provider Type: {fo_res.data['provider_type']}")
        print(f"  -> Route ID: {fo_res.data['route_id']}")
        print(f"  -> Answer: {fo_res.data['result']['answer']}")
        print(f"  -> Failover History ({len(fo_res.data['failover_history'])}):")
        for fo in fo_res.data["failover_history"]:
            print(f"     - Fallback: {fo['fallback_from']} -> {fo['fell_back_to']} (Reason: {fo['reason']})")
        assert fo_res.data["provider_type"] == "LOCAL_MODEL"
        assert len(fo_res.data["failover_history"]) == 1
        assert fo_res.data["failover_history"][0]["fallback_from"] == "REMOTE_MODEL"
        assert fo_res.data["failover_history"][0]["fell_back_to"] == "LOCAL_MODEL"

        # -------------------------------------------------------------
        # STAGE 9: Media Observation Tool Route
        # -------------------------------------------------------------
        print("\n[STAGE 9] Routing to Real Tool Adapter (Media Observation)...")
        demo_image = media_root / "target_sample.png"
        demo_image.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        tool_req = {
            "action": "route",
            "request_kind": "media",
            "sensitivity": "internal",
            "payload": {"path": "target_sample.png"},
        }
        tool_res = router.execute(tool_req)
        print(f"  -> Provider Type: {tool_res.data['provider_type']}")
        print(f"  -> Route ID: {tool_res.data['route_id']}")
        print(f"  -> Modality Observed: {tool_res.data['result']['modality']}")
        print(f"  -> File MIME: {tool_res.data['result'].get('detected_mime', 'image/png')}")
        print(f"  -> Observation ID: {tool_res.data['result']['observation_id']}")
        assert tool_res.data["provider_type"] == "TOOL"
        assert tool_res.data["result"]["modality"] == "IMAGE"

        # -------------------------------------------------------------
        # STAGE 10: Cryptographic Tamper-Evidence Verification
        # -------------------------------------------------------------
        print("\n[STAGE 10] Cryptographically Verifying Audit Log & Receipt Chain Integrity...")
        integrity = router.verify_integrity()
        print(f"  -> Status: {integrity.data['status']}")
        print(f"  -> Receipts Checked: {integrity.data['receipts_checked']}")
        assert integrity.data["status"] == "HEALTHY"

        history = router.history(limit=5)
        print(f"  -> Total Logged Routes in DB: {len(history['routes'])}")
        print(f"  -> Total Audit Events: {len(history['audit_events'])}")
        print(f"  -> Total Signed Receipts: {len(history['receipts'])}")

        print("\n" + "=" * 80)
        print("  ALL 10 VERTICAL SLICE STAGES COMPLETED SUCCESSFULLY!")
        print("  Pilar 37: Hybrid Consciousness operational & verified.")
        print("=" * 80)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    run_demo()
