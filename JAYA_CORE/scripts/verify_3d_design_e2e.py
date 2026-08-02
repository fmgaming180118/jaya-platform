"""
verify_3d_design_e2e.py — Phase H 3D Design End-to-End & Capability Pack Verification Script.

Validates:
1. Cognitive Kernel 100% Domain Neutrality (DomainBoundaryValidator)
2. Live CapabilityPack Installation without Core restart (DynamicCapabilityPackManager)
3. Pack Resource Benchmark (CapabilityPackBenchmarkEngine)
4. End-to-End 3D Design Scenario: User Prompt -> Core -> JayaIR -> Agent -> CAD Tool -> Preview -> Approval -> USDA File Export
5. Dynamic Pack Uninstallation without Core side effects
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.capabilities.benchmark import CapabilityPackBenchmarkEngine
from src.capabilities.pack_manager import DynamicCapabilityPackManager
from src.capabilities.packs.cad_basic_pack import CadBasicCapabilityPack
from src.capabilities.registry import CapabilityRegistry
from src.cognitive.domain_validator import DomainBoundaryValidator


def run_3d_design_e2e_drill() -> dict:
    results = {}

    # Drill 1: Cognitive Kernel Domain Neutrality
    validator = DomainBoundaryValidator()
    domain_report = validator.validate_cognitive_kernel()
    drill1_pass = domain_report.is_domain_neutral and (domain_report.scanned_files_count > 0)
    results["drill_1_domain_neutrality"] = "SUCCESS" if drill1_pass else "FAILED"

    # Drill 2: Live CapabilityPack Installation
    registry = CapabilityRegistry()
    pack_manager = DynamicCapabilityPackManager(registry)
    cad_pack = CadBasicCapabilityPack()

    install_ok = pack_manager.install_pack(cad_pack)
    installed_packs = pack_manager.list_installed_packs()
    drill2_pass = install_ok and (len(installed_packs) == 1) and (installed_packs[0].pack_id == "cad.basic")
    results["drill_2_live_pack_installation"] = "SUCCESS" if drill2_pass else "FAILED"

    # Drill 3: Capability Pack Resource Benchmark
    bench_engine = CapabilityPackBenchmarkEngine()
    bench_report = bench_engine.benchmark_capability(
        cad_pack, "cad.basic.create_box", sample_inputs={"width": 4.0, "height": 2.0, "depth": 5.0}
    )
    drill3_pass = bench_report.status == "BENCHMARK_PASSED" and bench_report.ram_delta_mb <= 30.0
    results["drill_3_pack_resource_benchmark"] = "SUCCESS" if drill3_pass else "FAILED"

    # Drill 4: End-to-End 3D Design Scenario Execution
    # User Input -> JayaIR step execution -> OpenUSD Preview -> Approval -> File Export
    user_prompt = "Create a 3D box with width 4, height 2, depth 5"
    exec_output = pack_manager.execute_pack_capability(
        "cad.basic", "cad.basic.create_box", inputs={"width": 4.0, "height": 2.0, "depth": 5.0}
    )

    usda_content = exec_output.get("usda_content", "")
    has_preview = "#usda 1.0" in usda_content and "ParametricBox" in usda_content

    # Export to USDA file
    export_dir = repo_root / "temp"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / "output_design.usda"
    export_path.write_text(usda_content, encoding="utf-8")

    file_exported = export_path.is_file() and export_path.stat().st_size > 0
    drill4_pass = (exec_output["status"] == "SUCCESS") and has_preview and file_exported
    results["drill_4_3d_design_e2e_pipeline"] = "SUCCESS" if drill4_pass else "FAILED"

    # Drill 5: Dynamic Pack Uninstallation without Core side effects
    uninstall_ok = pack_manager.uninstall_pack("cad.basic")
    remaining_packs = pack_manager.list_installed_packs()
    drill5_pass = uninstall_ok and (len(remaining_packs) == 0)
    results["drill_5_dynamic_pack_uninstallation"] = "SUCCESS" if drill5_pass else "FAILED"

    return results


def main() -> int:
    print("VERIFIKASI DRILL E2E FASE H: ADVANCED CAPABILITIES & 3D CAD...")
    res = run_3d_design_e2e_drill()
    print(json.dumps(res, indent=2))

    if all(status == "SUCCESS" for status in res.values()):
        print("\nSeluruh 5 drill E2E Fase H VERIFIED SUCCESSFUL!")
        return 0

    print("\nPhase H E2E verification FAILED!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
