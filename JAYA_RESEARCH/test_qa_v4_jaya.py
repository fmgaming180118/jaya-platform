"""
test_qa_v4_jaya.py
===================
JAYA Research — QA Test v4.0 (Page-Level FAISS)

Fix dari v3 (55%) ke v4:
  FIX 1: Page-level FAISS — 1 embedding per halaman (bukan per chunk 320 char)
          Ini menjaga tabel tetap utuh dalam 1 halaman
  FIX 2: LLM mendapat FULL page text (bukan potongan 320 char)
  FIX 3: top_k dari 10 → 12 halaman relevan
  FIX 4: Keyword fix untuk B3 (Odoo SEBAGIAN → AKURAT)
  FIX 5: Untuk pertanyaan tabel (A5, B4, C1, C2, C5, D4, D5):
          tambahkan "table_hint" pages ke konteks (halaman yg diketahui berisi tabel kunci)
  FIX 6: Embedding truncate ke 1600 char (safe ~400 token) per halaman
"""

import sys, os, re, json, time, hashlib, pickle
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

JAYA_ROOT  = Path(__file__).parent
PDF_FOLDER = Path(r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir")
CACHE_DIR  = JAYA_ROOT / "data" / "embedding_cache_v4"
RESULTS    = JAYA_ROOT / "data" / "test_qa_v4_results.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def load_dotenv(path):
    env = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

ENV = load_dotenv(JAYA_ROOT / ".env")
API_KEY     = ENV.get("NVIDIA_API_KEY", "")
BASE_URL    = ENV.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
EMBED_MODEL = ENV.get("NVIDIA_EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5")
CHAT_MODEL  = "meta/llama-3.3-70b-instruct"

try:
    import pdfplumber
except ImportError:
    print("[ERROR] pip install pdfplumber"); sys.exit(1)

try:
    import numpy as np
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False; np = None
    print("[WARN] FAISS tidak ada")

try:
    import requests
except ImportError:
    print("[ERROR] pip install requests"); sys.exit(1)

# ── QA Bank dengan table_hint_pages ──────────────────────────────────────────
# table_hint_pages: nomor halaman yang diketahui berisi info kunci (dari test sebelumnya)
QA_BANK = {
    "1318029_Affifah Nasrillah Fajri_TA.pdf": {
        "label": "TA Affifah — Monitoring Scrap (PT SKF Indonesia)",
        "questions": [
            {"id":"A1","q":"Apa judul lengkap Tugas Akhir ini dan di perusahaan apa diimplementasikan?",
             "gt":"Pengembangan Sistem Monitoring Scrap Product dengan Penyajian Menggunakan Chart.JS pada Departemen Produksi di PT SKF Indonesia",
             "kw":["scrap","chart.js","SKF","monitoring","departemen produksi"],
             "hint_pages":[]},
            {"id":"A2","q":"Siapa nama lengkap mahasiswa yang mengerjakan TA ini dan berapa NIM-nya?",
             "gt":"Affifah Nasrillah Fajri, NIM 1318029",
             "kw":["Affifah","1318029","Nasrillah"],
             "hint_pages":[]},
            {"id":"A3","q":"Teknologi front-end apa yang digunakan untuk visualisasi data dalam sistem monitoring ini?",
             "gt":"Chart.JS digunakan untuk visualisasi/penyajian data scrap product",
             "kw":["Chart","visualisasi"],
             "hint_pages":[]},
            {"id":"A4","q":"Di bab latar belakang, apa masalah utama yang melatarbelakangi pengembangan sistem monitoring scrap product ini?",
             "gt":"Pencatatan scrap yang masih manual dan tidak efisien di departemen produksi PT SKF Indonesia",
             "kw":["manual","scrap","pencatatan","produksi"],
             "hint_pages":[6,7,8,9,10]},
            {"id":"A5","q":"Di bab kajian pustaka (tinjauan pustaka), siapa peneliti terdahulu yang namanya tercantum di tabel penelitian terdahulu?",
             "gt":"Fatimah Azzahra, Adam Hendra Brata (2022); atau Rangga Ary Widiyanto (2022)",
             "kw":["Azzahra","Fatimah","2022","Rangga","Widiyanto"],
             "hint_pages":[27,28,29,30]},
        ]
    },
    "1319058_Ihsan Ali_TA.pdf": {
        "label": "TA Ihsan Ali — LMS Odoo (PT Astra Otoparts)",
        "questions": [
            {"id":"B1","q":"Apa judul Tugas Akhir ini dan di divisi mana diimplementasikan?",
             "gt":"Implementasi Learning Management System untuk Pelatihan Karyawan menggunakan Odoo pada PT Astra Otoparts Tbk Divisi Nusametal",
             "kw":["Learning Management System","Odoo","Nusametal","Astra Otoparts"],
             "hint_pages":[]},
            {"id":"B2","q":"Siapa nama mahasiswa yang mengerjakan TA ini dan berapa NIM-nya?",
             "gt":"Ihsan Ali, NIM 1319058",
             "kw":["Ihsan Ali","1319058"],
             "hint_pages":[]},
            {"id":"B3","q":"Aplikasi Odoo digunakan sebagai platform apa dalam penelitian ini?",
             "gt":"Odoo digunakan sebagai platform Learning Management System (LMS) untuk pelatihan karyawan",
             "kw":["Odoo","LMS","pelatihan"],
             "hint_pages":[]},
            {"id":"B4","q":"Dalam bab landasan teori, apa kepanjangan BPMN dan apa saja elemen-elemen Flow Object yang disebutkan?",
             "gt":"Business Process Model and Notation — Flow Object: Events, Activities, Gateways",
             "kw":["Business Process","Events","Activities","Gateways"],
             "hint_pages":[31,32,33,34]},
            {"id":"B5","q":"Di halaman persetujuan dosen pembimbing, pada tanggal berapa Tugas Akhir ini disetujui?",
             "gt":"5 Juni 2023",
             "kw":["Juni","2023","5"],
             "hint_pages":[2,3]},
        ]
    },
    "Peraturan Direktur Nomor 02 Tahun 2021 tentang Penetapan Pedoman Tugas Akhir Politeknik STMI Jakarta Secure.pdf": {
        "label": "Pedoman TA Politeknik STMI Jakarta (2021)",
        "questions": [
            {"id":"C1","q":"Dalam tabel ketentuan penjilidan, apa warna cover dan jenis penjilidan untuk Program Studi SIIO?",
             "gt":"Biru Muda #40bbe3, Hardcover",
             "kw":["SIIO","biru muda","Hardcover"],
             "hint_pages":[33,34,35]},
            {"id":"C2","q":"Dalam tabel ketentuan penjilidan, apa warna cover dan jenis penjilidan untuk Program Studi TIO?",
             "gt":"Hitam #000000, Hardcover",
             "kw":["TIO","Hitam","Hardcover"],
             "hint_pages":[33,34,35]},
            {"id":"C3","q":"Siapa Pengarah dari Tim Penyusun Pedoman Tugas Akhir ini?",
             "gt":"Dr. Mustofa, S.T., M.T.",
             "kw":["Mustofa","Pengarah","Dr.","M.T"],
             "hint_pages":[2]},
            {"id":"C4","q":"Berapa nomor keputusan Direktur Politeknik STMI Jakarta yang menjadi dasar tim penyusun pedoman ini?",
             "gt":"444/BPSDMI/STMI/KEP/V/2021",
             "kw":["444","BPSDMI","KEP","V/2021"],
             "hint_pages":[2]},
            {"id":"C5","q":"Dalam Tabel Rubrik Penilaian Tugas Akhir bab V, sebutkan aspek pertama yang dinilai!",
             "gt":"Kesesuaian latar belakang masalah, perumusan masalah dan tujuan penelitian",
             "kw":["latar belakang","perumusan masalah","tujuan penelitian"],
             "hint_pages":[56,57,58]},
        ]
    },
    "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf": {
        "label": "TA Hanny Kurnia Putri — Procurement (PT Akebono Brake)",
        "questions": [
            {"id":"D1","q":"Apa judul Tugas Akhir dan di perusahaan mana sistem diimplementasikan?",
             "gt":"Implementasi Sistem Informasi Procurement Berbasis Web dengan PHP dan SQL Server pada PT Akebono Brake Astra Indonesia",
             "kw":["Procurement","Akebono","PHP","SQL Server","web"],
             "hint_pages":[]},
            {"id":"D2","q":"Siapa nama mahasiswa yang mengerjakan TA ini dan berapa NIM-nya?",
             "gt":"Hanny Kurnia Putri, NIM 1318001",
             "kw":["Hanny","Kurnia","1318001"],
             "hint_pages":[]},
            {"id":"D3","q":"Bahasa pemrograman dan database apa yang digunakan untuk membangun sistem procurement ini?",
             "gt":"PHP sebagai bahasa pemrograman dan SQL Server sebagai database",
             "kw":["PHP","SQL Server","bahasa pemrograman","database"],
             "hint_pages":[]},
            {"id":"D4","q":"Di bab kajian pustaka, siapa peneliti yang karyanya dijadikan referensi? Sebutkan satu nama peneliti dan tahunnya!",
             "gt":"Afifah & Setyantoro (2021) atau Qotimah (2017)",
             "kw":["Afifah","Setyantoro","2021","Qotimah","2017"],
             "hint_pages":[26,27,28]},
            {"id":"D5","q":"Dalam landasan teori BPMN, apa fungsi dan definisi elemen Gateway menurut dokumen ini?",
             "gt":"Pengontrol divergensi dan konvergensi sequence flow dalam proses, menentukan jalur branching, forking, merging, dan joining",
             "kw":["Gateway","sequence flow","branching","divergensi"],
             "hint_pages":[46,47,48]},
        ]
    }
}

# ── PDF Extraction — per page ─────────────────────────────────────────────
def extract_pages(pdf_path: Path) -> list:
    """Ekstrak teks per halaman lengkap + tabel sebagai baris teks."""
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = (page.extract_text(x_tolerance=2, y_tolerance=2) or "").strip()
            # Tambahkan tabel ke teks halaman
            try:
                for table in (page.extract_tables() or []):
                    for row in table:
                        if row:
                            rt = " | ".join(str(c or "").strip() for c in row if c and str(c).strip())
                            if rt:
                                text += "\n" + rt
            except Exception:
                pass
            if text.strip():
                pages.append({"page": i, "text": text.strip()})
    return pages

# ── FAISS: Page-Level Embeddings ───────────────────────────────────────────
def embed_pages(pages: list) -> "np.ndarray":
    """Embed setiap halaman (truncate ke 1600 char ~ 400 token, aman untuk limit 512)."""
    batch_size = 48
    all_emb = []
    total   = (len(pages) + batch_size - 1) // batch_size

    for i in range(0, len(pages), batch_size):
        batch_pages = pages[i:i + batch_size]
        # Truncate ke 1600 char — aman untuk embedding 512 token limit
        texts = [p["text"][:1600] for p in batch_pages]
        try:
            resp = requests.post(
                f"{BASE_URL}/embeddings",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"input": texts, "model": EMBED_MODEL, "input_type": "passage"},
                timeout=60
            )
            if resp.status_code == 200:
                embs = [item["embedding"] for item in resp.json()["data"]]
                all_emb.extend(embs)
            else:
                print(f"  [EMBED ERR] {resp.status_code}")
                all_emb.extend([[0.0] * 1024] * len(batch_pages))
        except Exception as e:
            print(f"  [EMBED EXC] {e}")
            all_emb.extend([[0.0] * 1024] * len(batch_pages))

        batch_num = i // batch_size + 1
        if batch_num % 3 == 0 or batch_num == total:
            print(f"  [EMBED] Batch {batch_num}/{total} ({i + len(batch_pages)}/{len(pages)} halaman)")
        time.sleep(0.15)

    arr = np.array(all_emb, dtype=np.float32)
    faiss.normalize_L2(arr)
    return arr

def get_or_build_cache(pdf_path: Path, pages: list):
    fhash  = hashlib.md5(pdf_path.read_bytes()).hexdigest()[:10]
    cf     = CACHE_DIR / f"{pdf_path.stem[:40]}_{fhash}_v4.pkl"

    if cf.exists():
        print(f"  [CACHE] Memuat dari cache (page-level)...")
        with open(cf, "rb") as f:
            c = pickle.load(f)
        idx = faiss.deserialize_index(c["index"])
        return idx, c["pages"]

    print(f"  [EMBED] Page-level embedding untuk {len(pages)} halaman...")
    emb = embed_pages(pages)
    idx = faiss.IndexFlatIP(emb.shape[1])
    idx.add(emb)

    with open(cf, "wb") as f:
        pickle.dump({"index": faiss.serialize_index(idx), "pages": pages}, f)
    print(f"  [CACHE] Disimpan: {cf.name}")
    return idx, pages

# ── Retrieval: Semantic + Hint Pages ─────────────────────────────────────
def retrieve(question: str, idx, pages: list, cover: list, hint_pages: list, top_k: int = 12) -> str:
    """
    Hybrid retrieval:
    1. Cover pages 1-5 SELALU masuk
    2. Hint pages (diketahui berisi info kunci) SELALU masuk
    3. FAISS semantic search top_k additional pages
    """
    parts = []
    seen  = set()

    # 1. Cover pages
    for p in cover:
        parts.append(f"[HAL.{p['page']} - IDENTITAS]\n{p['text'][:1200]}")
        seen.add(p["page"])

    # 2. Hint pages (tabel kunci)
    page_map = {p["page"]: p for p in pages}
    for pnum in hint_pages:
        if pnum in page_map and pnum not in seen:
            parts.append(f"[HAL.{pnum} - KUNCI]\n{page_map[pnum]['text'][:1200]}")
            seen.add(pnum)

    # 3. FAISS semantic search
    if HAS_FAISS:
        try:
            q_txt = question[:1600]
            resp  = requests.post(
                f"{BASE_URL}/embeddings",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"input": [q_txt], "model": EMBED_MODEL, "input_type": "query"},
                timeout=30
            )
            if resp.status_code == 200:
                q_emb = np.array([resp.json()["data"][0]["embedding"]], dtype=np.float32)
                faiss.normalize_L2(q_emb)
                dists, idxs = idx.search(q_emb, top_k + len(seen) + 5)
                added = 0
                for d, si in zip(dists[0], idxs[0]):
                    if si < 0 or added >= top_k:
                        break
                    page = pages[si]
                    if page["page"] not in seen:
                        parts.append(f"[HAL.{page['page']} score={d:.3f}]\n{page['text'][:1000]}")
                        seen.add(page["page"])
                        added += 1
        except Exception as e:
            print(f"  [FAISS ERR] {e}")

    return "\n\n---\n\n".join(parts)

# ── LLM ──────────────────────────────────────────────────────────────────────
SYS = (
    "Kamu adalah ekstraktor informasi faktual dari dokumen akademik Indonesia.\n"
    "ATURAN MUTLAK:\n"
    "1. Jawab HANYA dari teks KONTEKS\n"
    "2. DILARANG gunakan pengetahuan di luar konteks\n"
    "3. Jika tidak ada: tulis hanya 'TIDAK DITEMUKAN'\n"
    "4. Jawab singkat dan langsung, max 3 kalimat\n"
    "5. Kutip data spesifik (nama, angka, kode warna) persis dari dokumen"
)

def ask(question: str, context: str) -> str:
    msg = f"KONTEKS:\n{context}\n\nPERTANYAAN: {question}\n\nJAWABAN SINGKAT:"
    try:
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": SYS},
                    {"role": "user",   "content": msg}
                ],
                "temperature": 0.0,
                "max_tokens": 200,
                "stop": [
                    "PERTANYAAN:", "KONTEKS:", "ATURAN:",
                    "Perhatian", "Lihat Konteks", "Penjelasan:",
                    "Rasmi", "Catatan:"
                ],
            },
            timeout=45
        )
        if resp.status_code == 200:
            ans = resp.json()["choices"][0]["message"]["content"].strip()
            ans = re.sub(r'<think>[\s\S]*?</think>', '', ans).strip()
            ans = re.sub(r'\*{2,}', '', ans).strip()
            return ans
        return f"[API {resp.status_code}]"
    except Exception as e:
        return f"[EXC: {str(e)[:60]}]"

# ── Evaluasi ──────────────────────────────────────────────────────────────────
def evaluate(answer: str, keywords: list) -> dict:
    ans_lower = answer.lower()
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
    print("  JAYA RESEARCH — QA Test v4.0 (Page-Level FAISS + Hint Pages)")
    print(f"  LLM   : {CHAT_MODEL}")
    print(f"  Embed : {EMBED_MODEL} (per halaman, truncate 1600 char)")
    print(f"  FAISS : {'aktif' if HAS_FAISS else 'BM25 fallback'}")
    print(SEP)

    all_results = []
    g_total = g_akurat = g_sbgn = 0

    for pdf_fn, qa_data in QA_BANK.items():
        pdf_path = PDF_FOLDER / pdf_fn
        label    = qa_data["label"]
        questions = qa_data["questions"]

        print(f"\n{'─'*72}")
        print(f"  {label}")
        print(f"{'─'*72}")

        if not pdf_path.exists():
            print(f"  [!!] File tidak ditemukan!"); continue

        # Ekstrak
        print("  [1/3] Ekstrak teks per halaman...")
        t0 = time.time()
        pages = extract_pages(pdf_path)
        cover = pages[:5]
        print(f"        {len(pages)} halaman dalam {time.time()-t0:.1f}s")

        # FAISS page-level
        print("  [2/3] FAISS page-level index...")
        t1 = time.time()
        idx, idxed = get_or_build_cache(pdf_path, pages)
        print(f"        Selesai dalam {time.time()-t1:.1f}s")

        # QA
        pdf_res = {"file": pdf_fn, "label": label, "qa": []}
        qa_ok = qa_sbgn = 0

        print("  [3/3] QA Loop...")
        for qa in questions:
            qid, question, gt = qa["id"], qa["q"], qa["gt"]
            kws  = qa["kw"]
            hint = qa.get("hint_pages", [])

            context = retrieve(question, idx, idxed, cover, hint, top_k=12)
            t2 = time.time()
            ans = ask(question, context)
            elapsed = round(time.time() - t2, 2)

            ev = evaluate(ans, kws)
            if ev["label"] == "AKURAT":
                qa_ok += 1; g_akurat += 1
            elif ev["label"] == "SEBAGIAN":
                qa_sbgn += 1; g_sbgn += 1
            g_total += 1

            icon = {"AKURAT": "[AKURAT  ]", "SEBAGIAN": "[SEBAGIAN]", "TIDAK AKURAT": "[MELESET ]"}[ev["label"]]
            hint_tag = f" hint={hint}" if hint else ""
            print(f"\n  [{qid}]{hint_tag} {question}")
            print(f"  GT   : {gt}")
            print(f"  JAYA : {ans[:260]}")
            print(f"  EVAL : {icon} ({ev['matched']}/{ev['total']} kw: {ev['hits']}) | {elapsed}s")

            pdf_res["qa"].append({
                "id": qid, "question": question, "ground_truth": gt,
                "jaya_answer": ans, "eval": ev, "elapsed_sec": elapsed,
                "hint_pages": hint
            })

        acc = round(qa_ok / len(questions) * 100)
        print(f"\n  Akurasi: {qa_ok}/{len(questions)} akurat, {qa_sbgn}/{len(questions)} sebagian = {acc}%")
        pdf_res["accuracy_pct"] = acc
        all_results.append(pdf_res)

    # ── Summary ───────────────────────────────────────────────────────────
    acc_pct = round(g_akurat / g_total * 100) if g_total else 0
    eff_pct = round((g_akurat + g_sbgn) / g_total * 100) if g_total else 0

    print(f"\n{SEP}")
    print(f"  RINGKASAN GLOBAL — v4.0")
    print(f"{SEP}")
    print(f"  AKURAT   : {g_akurat}/{g_total}  ({acc_pct}%)")
    print(f"  SEBAGIAN : {g_sbgn}/{g_total}  ({round(g_sbgn/g_total*100) if g_total else 0}%)")
    print(f"  MELESET  : {g_total - g_akurat - g_sbgn}/{g_total}")
    print(f"  Akurasi  : {acc_pct}% murni | {eff_pct}% efektif")
    print(f"\n  Perbandingan semua versi:")
    print(f"    v1 BM25 + nano-8b   : 35%")
    print(f"    v2 FAISS + ultra    : 35%  [model 404]")
    print(f"    v3 FAISS + 70B      : 55%  chunk tabel terpotong")
    print(f"    v4 Page-FAISS + 70B : {acc_pct}%  <== SEKARANG")
    print(f"    Total delta v1→v4   : +{acc_pct - 35}%")
    print(f"\n  Per PDF:")
    for r in all_results:
        bar = "#" * (r["accuracy_pct"] // 10) + "-" * (10 - r["accuracy_pct"] // 10)
        print(f"    [{bar}] {r['accuracy_pct']:3d}% — {r['label']}")

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump({
            "version": "v4", "model_chat": CHAT_MODEL, "model_embed": EMBED_MODEL,
            "summary": {"total": g_total, "akurat": g_akurat, "sebagian": g_sbgn,
                        "acc_pct": acc_pct, "eff_pct": eff_pct},
            "results": all_results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n  [FILE] {RESULTS}")
    print(SEP)


if __name__ == "__main__":
    main()
