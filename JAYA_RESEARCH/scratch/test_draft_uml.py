import sys, os
from pathlib import Path

# Configure sys.stdout to handle UTF-8 printing in Windows terminals
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add project root and src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from research.academic.drafter import ThesisDrafter

drafter = ThesisDrafter()
topic = "Sistem Monitoring Scrap Product PT SKF Indonesia"
spec = """
Sistem monitoring scrap product memiliki aktor:
1. Mahasiswa (sebagai analis) yang dapat login, melihat grafik scrap product, dan mencetak laporan scrap.
2. Dosen Pembimbing yang dapat login, memantau kemajuan bimbingan, dan memberikan persetujuan.
Sistem ini didefinisikan sebagai SistemAkademik.
"""

print("[INTEGRATION TEST] Drafting System Design Chapter with Use Case Diagram...")
chapter = drafter.generate_system_design_chapter(topic, spec, ["usecase"])

# Save to scratch folder first to protect data
output_file = Path(__file__).parent / "sample_chapter_bab3.md"
output_file.write_text(chapter, encoding="utf-8")
print(f"\n[INTEGRATION TEST] Saved to: {output_file}")

print("\n--- GENERATED DRAFT (Bab III) ---")
print(chapter)
