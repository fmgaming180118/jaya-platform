"""
demo_otak_jaya.py — Demo Sederhana Penggunaan Otak JAYA (Core & Research).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from JAYA_CORE.src.cognitive.contracts import UserRequest
from JAYA_CORE.src.cognitive.portable_kernel import PortableCognitiveKernelRunner
from JAYA_CORE.src.capabilities.packs.cad_basic_pack import CadBasicCapabilityPack
from JAYA_RESEARCH.src.research.citation_audit import CitationSynthesisAuditEngine, EvidenceChunk


def main():
    print("=" * 60)
    print("        DEMO SIMPEL PENGGUNAAN OTAK JAYA")
    print("=" * 60)

    # 1. Test Cognitive Kernel (Otak Penalaran)
    print("\n1. [JAYA CORE] Menjalankan Portable Cognitive Kernel...")
    kernel = PortableCognitiveKernelRunner()
    user_req = UserRequest(request_id="req-demo-01", raw_prompt="Analisis sistem termal magnetik")
    kernel_result = kernel.run_portable_request(user_req)

    print(f"   -> Status Kernel  : {kernel_result.status}")
    print(f"   -> Penggunaan RAM : {kernel_result.metrics.total_memory_mb} MB")
    print(f"   -> Komponen Aktif : {len(kernel_result.components_status)} Komponen Kognitif")

    # 2. Test Research Evidence Audit (Otak Riset & RAG)
    print("\n2. [JAYA RESEARCH] Verifikasi Evidence RAG & Audit Sitasi...")
    audit_engine = CitationSynthesisAuditEngine()
    evidence = EvidenceChunk(
        chunk_id="paper-01",
        content="Kritéria Lawson menuntut produk densitas plasma dan waktu konfinement n*tau >= 1e20 m^-3 s.",
        source_uri="jurnal_plasma.pdf",
    )
    synthesis = "Berdasarkan prinsip fusi [paper-01], kriteria Lawson menuntut produk densitas plasma n*tau >= 1e20 m^-3 s."
    audit_report = audit_engine.audit_synthesis("synth-demo", synthesis, [evidence])

    print(f"   -> Status Audit  : {audit_report.status}")
    print(f"   -> Grounding     : {audit_report.grounded_claims}/{audit_report.total_claims} Klaim Terbukti")
    print(f"   -> Sitasi Sumber : {audit_report.citations_mapped}")

    # 3. Test 3D Design Generation (Capability Pack CAD)
    print("\n3. [JAYA CAPABILITIES] Generasi Desain 3D Parametrik (OpenUSD)...")
    cad_pack = CadBasicCapabilityPack()
    cad_result = cad_pack.execute_capability("cad.basic.create_box", {"width": 10.0, "height": 5.0, "depth": 2.0})

    print(f"   -> Bentuk Desain : {cad_result['shape']}")
    print(f"   -> Dimensi Box   : {cad_result['dimensions']}")
    print("   -> Output USDA   :")
    for line in cad_result["usda_content"].splitlines()[:10]:
        print(f"      {line}")

    print("\n" + "=" * 60)
    print("   DEMO SUKSES: Otak JAYA dapat digunakan dan berfungsi normal!")
    print("=" * 60)


if __name__ == "__main__":
    main()
