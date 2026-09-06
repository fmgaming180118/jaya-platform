"""
demo_jaya_agent.py — Demo Sederhana Penggunaan Fitur JAYA Agent.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "packages" / "jaya-agent" / "src"))
sys.path.insert(0, str(repo_root / "packages" / "jaya-os" / "src"))

from jaya_agent.contracts.core_agent_os_contract import (
    AgentToolRequest,
    ContractValidator,
    CoreToAgentDispatch,
)
from jaya_agent.security.capability_sandbox import CapabilitySandbox
from jaya_os.consent_audit_manager import PermissionManager


async def run_agent_demo():
    print("=" * 60)
    print("        DEMO FITUR JAYA AGENT (TASK ORCHESTRATION & TOOLS)")
    print("=" * 60)

    # 1. Inisialisasi Security Interlock JAYA OS & Capability Sandbox
    print("\n1. [JAYA OS] Menginisialisasi Capability Sandbox & Permission Manager...")
    sandbox = CapabilitySandbox()
    permission_mgr = PermissionManager(sandbox=sandbox)

    sample_file_path = str(
        (repo_root / "data" / "jaya-research" / "jurnal_pdf" / "sample.txt").resolve()
    )

    # Record User Consent
    consent = permission_mgr.record_consent(
        subject="agent_researcher_01",
        action_set=["fs.read"],
        reference="user-tapped-allow-2026",
        ttl_seconds=3600,
    )
    print(f"   -> Consent Record Dibuat : ID={consent.consent_id}, Subject={consent.subject}")

    # 2. Menerima Dispatch Task dari JAYA Core ke JAYA Agent
    print("\n2. [JAYA CORE -> AGENT] Menerima Dispatch Task Penalaran...")
    dispatch = CoreToAgentDispatch(
        request_id="req-dispatch-001",
        plan_id="plan-research-001",
        goal_title="Eksplorasi material superkonduktor",
        steps=[{"step_id": "step-01", "action": "fs.read", "target": sample_file_path}],
    )

    validator = ContractValidator()
    val_res = validator.validate_core_to_agent(dispatch)
    print(f"   -> Validasi Kontrak Dispatch : Valid={val_res.is_valid}, Violations={val_res.violations}")

    # 3. Issue Grant dari JAYA OS ke Agent
    grant = permission_mgr.issue_grant(
        subject="agent_researcher_01",
        actions=["fs.read"],
        resources={"fs.read": (sample_file_path,)},
        ttl_seconds=300,
    )
    print(f"   -> Grant Token Terdaftar OS  : {grant[:16]}...")

    # 4. Agent Mengajukan Tool Request ke Sandbox JAYA OS
    print("\n4. [JAYA AGENT] Agent Memanggil Tool Melalui Capability Sandbox...")
    tool_req = AgentToolRequest(
        dispatch_id=dispatch.request_id,
        step_id="step-01",
        action="fs.read",
        resources=[sample_file_path],
        grant_token=grant,
        idempotency_key="idem-key-tool-001",
        inputs={"file_path": sample_file_path},
    )
    val_tool_res = validator.validate_agent_tool_request(tool_req)
    print(f"   -> Validasi Request Tool     : Valid={val_tool_res.is_valid}, Violations={val_tool_res.violations}")

    # Operations function
    async def async_file_reader():
        return {"status": "SUCCESS", "read_bytes": 1024, "data": "Material superkonduktor T_c = 135K."}

    # Eksekusi Terisolasi Sandbox OS Nyata
    execution = await sandbox.execute(
        grant_token=grant,
        action="fs.read",
        resources=(sample_file_path,),
        idempotency_key="idem-key-tool-001",
        request_payload={"file_path": sample_file_path},
        operation=async_file_reader,
    )

    print(f"   -> Output Sandbox Tool       : {execution.result}")
    print(f"   -> Receipt Grant Digest OS   : {execution.receipt.grant_digest[:16]}...")

    print("\n" + "=" * 60)
    print("   SUKSES: Fitur JAYA Agent Aktif & Berfungsi Terisolasi Aman!")
    print("=" * 60)


def main():
    asyncio.run(run_agent_demo())


if __name__ == "__main__":
    main()
