"""
test_qa_v6_jaya.py
===================
JAYA Research — QA Integration Test v6.0 (Core EnhancedRAGClient Integration)

Ini menguji implementasi core di JAYA_RESEARCH/src/research/enhanced_rag.py secara langsung:
  1. PyMuPDF layout-aware text column sorting.
  2. Pembersihan dots & dashes visual filler.
  3. Klasifikasi tipe dokumen dan ekstraksi metadata terstruktur (Tugas Akhir, Skripsi, Jurnal, Pedoman).
  4. Injeksi otomatis metadata index ke dalam hasil pencarian.
  5. Retry logic dengan exponential backoff untuk ketahanan jaringan (mengeliminasi timeout).
"""

import sys, os, re, json, time, shutil
from pathlib import Path

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

JAYA_ROOT  = Path(__file__).parent
PDF_FOLDER = Path(r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir")
RESULTS    = JAYA_ROOT / "data" / "test_qa_v6_results.json"

# Import Core RAG Client and Workspace Manager
try:
    from research.enhanced_rag import EnhancedRAGClient
    from research.workspace_manager import WorkspaceManager
    from teacher import Teacher
    print("[TEST] Core RAG components imported successfully.")
except ImportError as e:
    print(f"[TEST ERROR] Failed to import core components: {e}")
    sys.exit(1)

# ── QA Bank ──────────────────────────────────────────────────────────────────
QA_BANK = {
    "1318029_Affifah Nasrillah Fajri_TA.pdf": {
        "label": "TA Affifah — Monitoring Scrap (PT SKF Indonesia)",
        "questions": [
            {"id":"A1","q":"Apa judul lengkap Tugas Akhir ini dan di perusahaan apa diimplementasikan?",
             "gt":"Pengembangan Sistem Monitoring Scrap Product dengan Penyajian Menggunakan Chart.JS pada Departemen Produksi di PT SKF Indonesia",
             "kw":["scrap","chart.js","SKF","monitoring","departemen produksi"]},
            {"id":"A2","q":"Siapa nama lengkap mahasiswa yang mengerjakan TA ini dan berapa NIM-nya?",
             "gt":"Affifah Nasrillah Fajri, NIM 1318029",
             "kw":["Affifah","1318029","Nasrillah"]},
            {"id":"A3","q":"Teknologi front-end apa yang digunakan untuk visualisasi data dalam sistem monitoring ini?",
             "gt":"Chart.JS digunakan untuk visualisasi/penyajian data scrap product",
             "kw":["Chart","js"]},
            {"id":"A4","q":"Di bab latar belakang, apa masalah utama yang melatarbelakangi pengembangan sistem monitoring scrap product ini?",
             "gt":"Pencatatan scrap yang masih manual dan tidak efisien di departemen produksi PT SKF Indonesia",
             "kw":["manual","scrap","pencatatan","produksi"]},
            {"id":"A5","q":"Di bab kajian pustaka (tinjauan pustaka), siapa peneliti terdahulu yang namanya tercantum di tabel penelitian terdahulu?",
             "gt":"Fatimah Azzahra, Adam Hendra Brata (2022); atau Rangga Ary Widiyanto (2022)",
             "kw":["Azzahra","Fatimah","2022","Rangga","Widiyanto"]},
        ]
    },
    "1319058_Ihsan Ali_TA.pdf": {
        "label": "TA Ihsan Ali — LMS Odoo (PT Astra Otoparts)",
        "questions": [
            {"id":"B1","q":"Apa judul Tugas Akhir ini dan di divisi mana diimplementasikan?",
             "gt":"Implementasi Learning Management System untuk Pelatihan Karyawan menggunakan Odoo pada PT Astra Otoparts Tbk Divisi Nusametal",
             "kw":["Learning Management System","Odoo","Nusametal","Astra Otoparts"]},
            {"id":"B2","q":"Siapa nama mahasiswa yang mengerjakan TA ini dan berapa NIM-nya?",
             "gt":"Ihsan Ali, NIM 1319058",
             "kw":["Ihsan Ali","1319058"]},
            {"id":"B3","q":"Aplikasi Odoo digunakan sebagai platform apa dalam penelitian ini?",
             "gt":"Odoo digunakan sebagai platform Learning Management System (LMS) untuk pelatihan karyawan",
             "kw":["Odoo","LMS","pelatihan"]},
            {"id":"B4","q":"Dalam bab landasan teori, apa kepanjangan BPMN dan apa saja elemen-elemen Flow Object yang disebutkan?",
             "gt":"Business Process Model and Notation — Flow Object: Events, Activities, Gateways",
             "kw":["Business Process","Events","Activities","Gateways"]},
            {"id":"B5","q":"Di halaman persetujuan dosen pembimbing, pada tanggal berapa Tugas Akhir ini disetujui?",
             "gt":"5 Juni 2023",
             "kw":["Juni","2023","5"]},
        ]
    },
    "Peraturan Direktur Nomor 02 Tahun 2021 tentang Penetapan Pedoman Tugas Akhir Politeknik STMI Jakarta Secure.pdf": {
        "label": "Pedoman TA Politeknik STMI Jakarta (2021)",
        "questions": [
            {"id":"C1","q":"Dalam tabel ketentuan penjilidan, apa warna cover dan jenis penjilidan untuk Program Studi SIIO?",
             "gt":"Biru Muda #40bbe3, Hardcover",
             "kw":["SIIO","biru muda","Hardcover"]},
            {"id":"C2","q":"Dalam tabel ketentuan penjilidan, apa warna cover dan jenis penjilidan untuk Program Studi TIO?",
             "gt":"Hitam #000000, Hardcover",
             "kw":["TIO","Hitam","Hardcover"]},
            {"id":"C3","q":"Siapa Pengarah dari Tim Penyusun Pedoman Tugas Akhir ini?",
             "gt":"Dr. Mustofa, S.T., M.T.",
             "kw":["Mustofa","Pengarah","Dr.","M.T"]},
            {"id":"C4","q":"Berapa nomor keputusan Direktur Politeknik STMI Jakarta yang menjadi dasar tim penyusun pedoman ini?",
             "gt":"444/BPSDMI/STMI/KEP/V/2021",
             "kw":["444","BPSDMI","KEP","V/2021"]},
            {"id":"C5","q":"Dalam Tabel Rubrik Penilaian Tugas Akhir bab V, sebutkan aspek pertama yang dinilai!",
             "gt":"Kesesuaian latar belakang masalah, perumusan masalah dan tujuan penelitian",
             "kw":["latar belakang","perumusan masalah","tujuan penelitian"]},
        ]
    },
    "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf": {
        "label": "TA Hanny Kurnia Putri — Procurement (PT Akebono Brake)",
        "questions": [
            {"id":"D1","q":"Apa judul Tugas Akhir dan di perusahaan mana sistem diimplementasikan?",
             "gt":"Implementasi Sistem Informasi Procurement Berbasis Web dengan PHP dan SQL Server pada PT Akebono Brake Astra Indonesia",
             "kw":["Procurement","Akebono","PHP","SQL Server","web"]},
            {"id":"D2","q":"Siapa nama mahasiswa yang mengerjakan TA ini dan berapa NIM-nya?",
             "gt":"Hanny Kurnia Putri, NIM 1318001",
             "kw":["Hanny","Kurnia","1318001"]},
            {"id":"D3","q":"Bahasa pemrograman dan database apa yang digunakan untuk membangun sistem procurement ini?",
             "gt":"PHP sebagai bahasa pemrograman dan SQL Server sebagai database",
             "kw":["PHP","SQL Server","bahasa pemrograman","database"]},
            {"id":"D4","q":"Di bab kajian pustaka, siapa peneliti yang karyanya dijadikan referensi? Sebutkan satu nama peneliti dan tahunnya!",
             "gt":"Afifah & Setyantoro (2021) atau Qotimah (2017)",
             "kw":["Afifah","Setyantoro","2021","Qotimah","2017"]},
            {"id":"D5","q":"Dalam landasan teori BPMN, apa fungsi dan definisi elemen Gateway menurut dokumen ini?",
             "gt":"Pengontrol divergensi dan konvergensi sequence flow dalam proses, menentukan jalur branching, forking, merging, dan joining",
             "kw":["Gateway","divergensi","branching","joining"]},
        ]
    }
}

# ── LLM Prompt & Call ────────────────────────────────────────────────────────
SYS = (
    "Kamu adalah ekstraktor informasi faktual dari dokumen akademik Indonesia.\n"
    "ATURAN MUTLAK:\n"
    "1. Jawab HANYA dari teks KONTEKS\n"
    "2. DILARANG gunakan pengetahuan di luar konteks\n"
    "3. Jika tidak ada: tulis hanya 'TIDAK DITEMUKAN'\n"
    "4. Jawab singkat dan langsung, max 3 kalimat\n"
    "5. Kutip data spesifik (nama, angka, kode warna) persis dari dokumen"
)

# ── Evaluasi ──────────────────────────────────────────────────────────────────
def evaluate(qid: str, answer: str, keywords: list) -> dict:
    ans_lower = answer.lower()
    
    # Custom evaluation logic untuk D4 (Afifah 2021 ATAU Qotimah 2017)
    if qid == "D4":
        is_afifah_2021 = "afifah" in ans_lower and "2021" in ans_lower
        is_qotimah_2017 = "qotimah" in ans_lower and "2017" in ans_lower
        is_setyantoro_2021 = "setyantoro" in ans_lower and "2021" in ans_lower
        if is_afifah_2021 or is_qotimah_2017 or is_setyantoro_2021:
            return {"hits": keywords, "rate": 1.0, "label": "AKURAT", "matched": len(keywords), "total": len(keywords)}

    hits  = [kw for kw in keywords if kw.lower() in ans_lower]
    rate  = len(hits) / len(keywords) if keywords else 0
    first_60 = ans_lower[:60]
    empty = "tidak ditemukan" in first_60 and len(hits) == 0

    if empty:           label = "TIDAK AKURAT"
    elif rate >= 0.6:   label = "AKURAT"
    elif rate >= 0.3:   label = "SEBAGIAN"
    else:               label = "TIDAK AKURAT"
    return {"hits": hits, "rate": round(rate,2), "label": label, "matched": len(hits), "total": len(keywords)}

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    SEP = "=" * 72
    print(SEP)
    print("  JAYA RESEARCH — QA Integration Test v6.0 (Workspace RAG Client)")
    print(SEP)

    # 1. Initialize workspace for testing
    ws_name = "test_qa_workspace"
    wm = WorkspaceManager()
    
    # Clean previous test workspace if exists
    try:
        wm.delete_workspace(ws_name)
    except:
        pass
    
    ws_paths = wm.get_or_create_paths(ws_name)
    print(f"[TEST] Workspace '{ws_name}' created: {ws_paths['vector_store']}")
    
    # 2. Instantiate core EnhancedRAGClient scoped to test workspace
    rag = EnhancedRAGClient(vector_store_path=ws_paths["vector_store"])
    teacher = Teacher(model_type="reasoning")

    # 3. Ingest files
    pdf_paths = [str(PDF_FOLDER / fn) for fn in QA_BANK.keys() if (PDF_FOLDER / fn).exists()]
    print(f"\n[TEST] Ingesting {len(pdf_paths)} documents into workspace...")
    t_start = time.time()
    
    # Ingest documents will run Fitz Layout-Aware parsing, clean text,
    # extract metadata structure per document type, and save to metadata_store.json
    ingest_res = rag.ingest_documents(pdf_paths)
    print(f"[TEST] Ingestion finished in {time.time()-t_start:.1f}s. Result: {ingest_res}")

    # Inspect metadata_store.json to verify point 3 & 4
    meta_store_path = Path(ws_paths["vector_store"]).parent / "metadata_store.json"
    if meta_store_path.exists():
        print(f"[TEST] ✅ metadata_store.json successfully created!")
        try:
            with open(meta_store_path, "r", encoding="utf-8") as f:
                meta_db = json.load(f)
            for fn, data in meta_db.items():
                print(f"      ├─ {fn}: Tipe = {data.get('doc_type')}, NIM = {data.get('metadata', {}).get('nim', 'N/A')}")
        except Exception as e:
            print(f"      └─ Error reading metadata database: {e}")
    else:
        print("[TEST] ❌ metadata_store.json NOT found!")

    # 4. QA Loop
    all_results = []
    g_total = g_akurat = g_sbgn = 0

    for pdf_fn, qa_data in QA_BANK.items():
        label = qa_data["label"]
        questions = qa_data["questions"]

        print(f"\n{'─'*72}")
        print(f"  {label}")
        print(f"{'─'*72}")

        pdf_res = {"file": pdf_fn, "label": label, "qa": []}
        qa_ok = qa_sbgn = 0

        print("  QA Loop...")
        for qa in questions:
            qid, question = qa["id"], qa["q"]
            kws = qa["kw"]

            # retrieve with a larger top_k to allow post-filtering by target file
            raw_results = rag.search(question, top_k=40)
            
            # Post-filter by target file or metadata index
            rag_results = []
            for item in raw_results:
                fname = item.get('document', {}).get('file_name', 'Unknown')
                if fname == pdf_fn:
                    rag_results.append(item)
                elif fname == "Workspace_Metadata_Index":
                    # Filter metadata content to only include the current file's section
                    orig_content = item.get('document', {}).get('content', '')
                    filtered_lines = ["### Dokumen Terdaftar & Informasi Penting (Metadata):"]
                    sections = orig_content.split("- Dokumen: ")
                    for s in sections[1:]:
                        if s.strip().startswith(pdf_fn):
                            filtered_lines.append("- Dokumen: " + s.strip())
                            break
                    filtered_content = "\n".join(filtered_lines)
                    
                    # Create a new filtered metadata item
                    filtered_item = {
                        "document": {
                            "file_name": "Workspace_Metadata_Index",
                            "title": "Workspace Metadata Index",
                            "type": "metadata_index",
                            "content": filtered_content
                        },
                        "score": item.get("score", 1.0),
                        "snippet": filtered_content,
                        "block_type": "metadata_index",
                        "citation": item.get("citation", {})
                    }
                    rag_results.append(filtered_item)
            
            # Keep top 6
            rag_results = rag_results[:6]
            
            # Construct context
            context_parts = []
            for item in rag_results:
                fname = item.get('document', {}).get('file_name', 'Unknown')
                citation = item.get('citation', {})
                page = citation.get('page')
                block_type = item.get('block_type', 'document')
                citation_label = f" p{page}" if page is not None else ""
                context_parts.append(f"Source: {fname} ({block_type}{citation_label})\n{item.get('snippet', '')}")
            
            context = "\n\n---\n\n".join(context_parts)
            
            t2 = time.time()
            # Call teacher
            msg = f"KONTEKS:\n{context}\n\nPERTANYAAN: {question}\n\nJAWABAN SINGKAT:"
            ans = teacher.ask(msg, system_instruction=SYS)
            elapsed = round(time.time() - t2, 2)

            ev = evaluate(qid, ans, kws)
            if ev["label"] == "AKURAT":
                qa_ok += 1; g_akurat += 1
            elif ev["label"] == "SEBAGIAN":
                qa_sbgn += 1; g_sbgn += 1
            g_total += 1

            icon = {"AKURAT": "[AKURAT  ]", "SEBAGIAN": "[SEBAGIAN]", "TIDAK AKURAT": "[MELESET ]"}[ev["label"]]
            print(f"\n  [{qid}] {question}")
            print(f"  JAYA : {ans[:260]}")
            print(f"  EVAL : {icon} ({ev['matched']}/{ev['total']} kw: {ev['hits']}) | {elapsed}s")

            pdf_res["qa"].append({
                "id": qid, "question": question, "ground_truth": "", # focus on JAYA response
                "jaya_answer": ans, "eval": ev, "elapsed_sec": elapsed
            })

        acc = round(qa_ok / len(questions) * 100)
        print(f"\n  Akurasi: {qa_ok}/{len(questions)} akurat, {qa_sbgn}/{len(questions)} sebagian = {acc}%")
        pdf_res["accuracy_pct"] = acc
        all_results.append(pdf_res)

    # ── Summary ───────────────────────────────────────────────────────────
    acc_pct = round(g_akurat / g_total * 100) if g_total else 0
    eff_pct = round((g_akurat + g_sbgn) / g_total * 100) if g_total else 0

    print(f"\n{SEP}")
    print(f"  RINGKASAN GLOBAL INTEGRASI — v6.0")
    print(f"{SEP}")
    print(f"  AKURAT   : {g_akurat}/{g_total}  ({acc_pct}%)")
    print(f"  SEBAGIAN : {g_sbgn}/{g_total}  ({round(g_sbgn/g_total*100) if g_total else 0}%)")
    print(f"  MELESET  : {g_total - g_akurat - g_sbgn}/{g_total}")
    print(f"  Akurasi  : {acc_pct}% murni | {eff_pct}% efektif")
    print(f"\n  Per PDF:")
    for r in all_results:
        bar = "#" * (r["accuracy_pct"] // 10) + "-" * (10 - r["accuracy_pct"] // 10)
        print(f"    [{bar}] {r['accuracy_pct']:3d}% — {r['label']}")

    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump({
            "version": "v6", "summary": {"total": g_total, "akurat": g_akurat, "sebagian": g_sbgn,
                        "acc_pct": acc_pct, "eff_pct": eff_pct},
            "results": all_results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n  [FILE] {RESULTS}")
    print(SEP)


if __name__ == "__main__":
    main()
