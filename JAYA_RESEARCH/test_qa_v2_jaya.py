"""
test_qa_v2_jaya.py
===================
JAYA Research — Pengujian QA v2.0 (Improved)

Perbaikan dari v1 (akurasi 35%) ke v2:
  1. NVIDIA Semantic Embedding (nv-embedqa-e5-v5) + FAISS — ganti BM25
  2. Cover Page Injection — halaman 1-5 SELALU masuk konteks (nama, NIM, judul)
  3. Table-Aware Chunking — tabel diindeks sebagai chunk terpisah
  4. Model Lebih Besar (nemotron-ultra-253b) dengan thinking mode
  5. Anti-Halusinasi Prompt ketat (FORBIDDEN to use outside knowledge)
  6. Temperature=0 untuk jawaban faktual
  7. Embedding Cache — tidak perlu recompute setiap run

Jalankan:
  cd JAYA_RESEARCH
  .\.venv312\Scripts\python.exe test_qa_v2_jaya.py
"""

import sys, os, re, json, time, math, hashlib, pickle
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Config ──────────────────────────────────────────────────────────────────
JAYA_ROOT  = Path(__file__).parent
PDF_FOLDER = Path(r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir")
CACHE_DIR  = JAYA_ROOT / "data" / "embedding_cache"
RESULTS_V2 = JAYA_ROOT / "data" / "test_qa_v2_results.json"

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
NVIDIA_API_KEY   = ENV.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL  = ENV.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
EMBED_MODEL      = ENV.get("NVIDIA_EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5")
# Gunakan model besar dengan thinking untuk akurasi tertinggi
CHAT_MODEL       = "nvidia/llama-3.1-nemotron-ultra-253b-v1"
CHAT_MODEL_FAST  = "nvidia/llama-3.1-nemotron-nano-8b-v1"

# ── Library checks ──────────────────────────────────────────────────────────
try:
    import pdfplumber; HAS_PDF = True
except ImportError:
    print("[ERROR] pip install pdfplumber"); sys.exit(1)

try:
    import numpy as np; import faiss; HAS_FAISS = True
except ImportError:
    print("[WARN] FAISS tidak tersedia - gunakan BM25 fallback"); HAS_FAISS = False; np = None

try:
    import requests; HAS_REQUESTS = True
except ImportError:
    print("[ERROR] pip install requests"); sys.exit(1)

# ── 20 Pertanyaan QA Bank ────────────────────────────────────────────────────
QA_BANK = {
    "1318029_Affifah Nasrillah Fajri_TA.pdf": {
        "label": "TA Affifah — Monitoring Scrap (PT SKF Indonesia)",
        "questions": [
            {"id":"A1","q":"Apa judul lengkap Tugas Akhir ini dan di perusahaan apa diimplementasikan?",
             "gt":"Pengembangan Sistem Monitoring Scrap Product dengan Penyajian Menggunakan Chart.JS pada Departemen Produksi di PT SKF Indonesia",
             "kw":["scrap","chart.js","SKF","monitoring","departemen produksi"]},
            {"id":"A2","q":"Siapa nama lengkap mahasiswa yang mengerjakan TA ini dan berapa NIM-nya?",
             "gt":"Affifah Nasrillah Fajri, NIM 1318029, Program Studi Sistem Informasi Industri Otomotif",
             "kw":["Affifah","1318029","SIIO","Nasrillah"]},
            {"id":"A3","q":"Teknologi front-end apa yang digunakan untuk visualisasi data dalam sistem monitoring ini?",
             "gt":"Chart.JS digunakan untuk visualisasi/penyajian data scrap product",
             "kw":["Chart.JS","Chart","visualisasi","chart"]},
            {"id":"A4","q":"Apa masalah utama yang melatarbelakangi pengembangan sistem monitoring scrap product ini?",
             "gt":"Pencatatan scrap yang masih manual dan tidak efisien di departemen produksi PT SKF Indonesia",
             "kw":["masalah","manual","scrap","pencatatan","produksi"]},
            {"id":"A5","q":"Sebutkan salah satu peneliti terdahulu yang dijadikan referensi beserta tahunnya!",
             "gt":"Fatimah Azzahra, Adam Hendra Brata, dan Komang Candra Brata (2022) — monitoring truk tangki air berbasis GIS",
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
             "gt":"Ihsan Ali, NIM 1319058, Program Studi Sistem Informasi Industri Otomotif",
             "kw":["Ihsan Ali","1319058","SIIO"]},
            {"id":"B3","q":"Platform atau aplikasi apa yang digunakan untuk mengimplementasikan LMS?",
             "gt":"Odoo digunakan sebagai platform LMS untuk pelatihan karyawan",
             "kw":["Odoo","platform","LMS","aplikasi"]},
            {"id":"B4","q":"Apa kepanjangan BPMN dan sebutkan elemen-elemen utamanya menurut dokumen ini?",
             "gt":"Business Process Model and Notation — elemen: Flow Object (Events, Activities, Gateways), Swimlanes (Pools, Lines), Connecting Objects (Sequence Flows, Message Flows, Associations), Artifacts",
             "kw":["BPMN","Business Process","Events","Activities","Gateways","Swimlanes"]},
            {"id":"B5","q":"Kapan tepatnya Tugas Akhir Ihsan Ali disetujui oleh dosen pembimbing?",
             "gt":"5 Juni 2023",
             "kw":["Juni 2023","2023","5 Juni","persetujuan","pembimbing"]},
        ]
    },
    "Peraturan Direktur Nomor 02 Tahun 2021 tentang Penetapan Pedoman Tugas Akhir Politeknik STMI Jakarta Secure.pdf": {
        "label": "Pedoman TA Politeknik STMI Jakarta (2021)",
        "questions": [
            {"id":"C1","q":"Apa warna cover Tugas Akhir untuk Program Studi SIIO?",
             "gt":"Biru Muda dengan kode warna #40bbe3, dijilid Hardcover",
             "kw":["SIIO","biru muda","#40bbe3","Biru","cover"]},
            {"id":"C2","q":"Apa warna cover untuk Program Studi TIO?",
             "gt":"Hitam dengan kode warna #000000, dijilid Hardcover",
             "kw":["TIO","hitam","#000000","Hitam","cover"]},
            {"id":"C3","q":"Siapa Pengarah dari Tim Penyusun Pedoman Tugas Akhir ini?",
             "gt":"Dr. Mustofa, S.T., M.T.",
             "kw":["Mustofa","Pengarah","Dr.","M.T"]},
            {"id":"C4","q":"Berapa nomor keputusan Direktur yang menjadi dasar pembentukan tim penyusun pedoman ini?",
             "gt":"Nomor: 444/BPSDMI/STMI/KEP/V/2021",
             "kw":["444","BPSDMI","STMI","KEP","2021"]},
            {"id":"C5","q":"Apa saja aspek penilaian dalam rubrik sidang Tugas Akhir?",
             "gt":"Kesesuaian latar belakang masalah, perumusan masalah dan tujuan penelitian (skala SB/B/C/K)",
             "kw":["penilaian","latar belakang","perumusan masalah","tujuan penelitian","sidang","SB"]},
        ]
    },
    "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf": {
        "label": "TA Hanny Kurnia Putri — Procurement (PT Akebono Brake)",
        "questions": [
            {"id":"D1","q":"Apa judul Tugas Akhir dan di perusahaan mana sistem diimplementasikan?",
             "gt":"Implementasi Sistem Informasi Procurement Berbasis Web dengan PHP dan SQL Server pada PT Akebono Brake Astra Indonesia",
             "kw":["Procurement","Akebono","PHP","SQL Server","web"]},
            {"id":"D2","q":"Siapa nama mahasiswa yang mengerjakan TA ini dan berapa NIM-nya?",
             "gt":"Hanny Kurnia Putri, NIM 1318001, Program Studi Sistem Informasi Industri Otomotif",
             "kw":["Hanny","Kurnia","1318001","SIIO"]},
            {"id":"D3","q":"Teknologi apa yang digunakan untuk membangun sistem informasi procurement ini?",
             "gt":"PHP sebagai bahasa pemrograman dan SQL Server sebagai database, berbasis web",
             "kw":["PHP","SQL Server","web","bahasa pemrograman","database"]},
            {"id":"D4","q":"Sebutkan salah satu peneliti terdahulu yang dijadikan referensi dalam penelitian ini!",
             "gt":"Afifah & Setyantoro (2021) — Rancangan Sistem Pemilihan dan Penetapan Harga dalam Proses Pengadaan; atau Qotimah (2017) — Sistem Informasi E-Procurement",
             "kw":["Afifah","Setyantoro","2021","Qotimah","2017","E-Procurement"]},
            {"id":"D5","q":"Apa definisi elemen BPMN 'Gateway' menurut dokumen ini?",
             "gt":"Gateway adalah pengontrol divergensi dan konvergensi sequence flow dalam proses, menentukan jalur branching, forking, merging, dan joining",
             "kw":["Gateway","divergensi","konvergensi","sequence flow","branching","forking"]},
        ]
    }
}

# ── PDF Extraction ─────────────────────────────────────────────────────────
def extract_structured_pages(pdf_path: Path) -> list:
    """Ekstrak teks per halaman + tabel sebagai teks tambahan."""
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = (page.extract_text(x_tolerance=2, y_tolerance=2) or "").strip()
            # Tambahkan isi tabel ke teks halaman
            try:
                for table in (page.extract_tables() or []):
                    for row in table:
                        if row:
                            row_text = " | ".join(str(c or "").strip() for c in row if c)
                            if row_text.strip():
                                text += "\n" + row_text
            except Exception:
                pass
            if text.strip():
                pages.append({"page": i, "text": text.strip()})
    return pages

def make_chunks(pages: list, chunk_size: int = 800, overlap: int = 200) -> list:
    """Buat chunks dari halaman dengan overlap — menyertakan nomor halaman asal."""
    chunks = []
    for page_data in pages:
        text = page_data["text"]
        page_num = page_data["page"]
        pos = 0
        while pos < len(text):
            chunk_text = text[pos:pos + chunk_size]
            chunks.append({"text": chunk_text, "page": page_num})
            pos += chunk_size - overlap
            if pos >= len(text):
                break
    return chunks

# ── NVIDIA Embedding API ────────────────────────────────────────────────────
def embed_texts_nvidia(texts: list, batch_size: int = 32) -> "np.ndarray":
    """Panggil NVIDIA embedding API dengan batching."""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        # Truncate texts to 512 tokens (approx 2000 chars)
        batch = [t[:2000] for t in batch]
        try:
            resp = requests.post(
                f"{NVIDIA_BASE_URL}/embeddings",
                headers={"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"},
                json={"input": batch, "model": EMBED_MODEL, "input_type": "passage"},
                timeout=60
            )
            if resp.status_code == 200:
                data = resp.json()
                embeddings = [item["embedding"] for item in data["data"]]
                all_embeddings.extend(embeddings)
            else:
                print(f"  [!!] Embedding API error {resp.status_code}: {resp.text[:100]}")
                # Fallback: zero vectors
                dim = 1024  # nv-embedqa-e5-v5 dimension
                all_embeddings.extend([[0.0] * dim] * len(batch))
        except Exception as e:
            print(f"  [!!] Embedding exception: {e}")
            dim = 1024
            all_embeddings.extend([[0.0] * dim] * len(batch))
        # Rate limit pause
        if i + batch_size < len(texts):
            time.sleep(0.3)
    return np.array(all_embeddings, dtype=np.float32)

def embed_query_nvidia(query: str) -> "np.ndarray":
    """Embed satu query untuk pencarian."""
    try:
        resp = requests.post(
            f"{NVIDIA_BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"},
            json={"input": [query[:2000]], "model": EMBED_MODEL, "input_type": "query"},
            timeout=30
        )
        if resp.status_code == 200:
            return np.array([resp.json()["data"][0]["embedding"]], dtype=np.float32)
    except Exception as e:
        print(f"  [!!] Query embedding error: {e}")
    dim = 1024
    return np.zeros((1, dim), dtype=np.float32)

# ── FAISS Index ─────────────────────────────────────────────────────────────
def build_faiss_index(embeddings: "np.ndarray"):
    """Buat FAISS index dengan Inner Product (cosine setelah normalisasi)."""
    dim = embeddings.shape[1]
    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    return index

def get_or_build_index(pdf_path: Path, chunks: list):
    """Cache index ke disk agar tidak recompute setiap run."""
    # Hash file untuk cache key
    file_hash = hashlib.md5(pdf_path.read_bytes()).hexdigest()[:12]
    cache_file = CACHE_DIR / f"{pdf_path.stem}_{file_hash}.pkl"

    if cache_file.exists():
        print(f"  [CACHE] Memuat index dari cache: {cache_file.name}")
        with open(cache_file, "rb") as f:
            cached = pickle.load(f)
        index = faiss.deserialize_index(cached["index_bytes"])
        return index, cached["chunks"]

    print(f"  [EMBED] Membuat embedding untuk {len(chunks)} chunks via NVIDIA API...")
    texts = [c["text"] for c in chunks]
    embeddings = embed_texts_nvidia(texts)
    index = build_faiss_index(embeddings)

    # Simpan ke cache
    index_bytes = faiss.serialize_index(index)
    with open(cache_file, "wb") as f:
        pickle.dump({"index_bytes": index_bytes, "chunks": chunks}, f)
    print(f"  [CACHE] Index disimpan ke: {cache_file.name}")

    return index, chunks

# ── Retrieval ───────────────────────────────────────────────────────────────
def retrieve_semantic(query: str, index, chunks: list, cover_pages: list, top_k: int = 8) -> str:
    """
    Hybrid retrieval:
    1. Selalu sertakan cover pages (halaman 1-5) — berisi nama, NIM, judul
    2. Semantic FAISS search untuk top_k chunk paling relevan
    """
    context_parts = []

    # 1. Cover pages SELALU masuk (perbaikan utama)
    cover_texts = [f"[Hal. {p['page']} — COVER/IDENTITAS]\n{p['text'][:600]}"
                   for p in cover_pages]
    context_parts.extend(cover_texts)

    # 2. Semantic search
    if HAS_FAISS and NVIDIA_API_KEY:
        q_emb = embed_query_nvidia(query)
        faiss.normalize_L2(q_emb)
        distances, indices = index.search(q_emb, top_k + 5)

        seen_pages = set(p["page"] for p in cover_pages)
        added = 0
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or added >= top_k:
                break
            chunk = chunks[idx]
            if chunk["page"] not in seen_pages:
                context_parts.append(f"[Hal. {chunk['page']} — Score: {dist:.3f}]\n{chunk['text'][:700]}")
                seen_pages.add(chunk["page"])
                added += 1
    else:
        # BM25 fallback
        q_tokens = set(re.findall(r'\b\w+\b', query.lower()))
        scored = []
        for c in chunks:
            doc_tokens = re.findall(r'\b\w+\b', c["text"].lower())
            score = len(q_tokens & set(doc_tokens))
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, chunk in scored[:top_k]:
            if score > 0:
                context_parts.append(f"[Hal. {chunk['page']}]\n{chunk['text'][:700]}")

    return "\n\n---\n\n".join(context_parts)

# ── NVIDIA LLM ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Kamu adalah asisten ekstraksi informasi faktual dari dokumen akademik Indonesia.

ATURAN WAJIB (tidak boleh dilanggar):
1. Jawab HANYA berdasarkan teks yang ada di KONTEKS DOKUMEN di bawah
2. DILARANG KERAS menggunakan pengetahuan di luar konteks
3. Jika informasi tidak ada dalam konteks: jawab PERSIS "Informasi ini tidak tersedia dalam konteks dokumen yang diberikan."
4. Jawab dalam Bahasa Indonesia yang formal dan ringkas (1-3 kalimat)
5. Untuk data spesifik (nama, angka, tanggal, kode warna): kutip PERSIS dari dokumen
6. JANGAN menambahkan penjelasan tambahan atau catatan di luar jawaban"""

def ask_llm(question: str, context: str, use_big_model: bool = True) -> tuple:
    """Kirim ke NVIDIA LLM dengan strict grounding. Return (answer, model_used)."""
    model = CHAT_MODEL if use_big_model else CHAT_MODEL_FAST
    user_msg = f"""KONTEKS DOKUMEN:
{context}

PERTANYAAN: {question}

JAWABAN FAKTUAL (hanya dari konteks, 1-3 kalimat):"""

    try:
        resp = requests.post(
            f"{NVIDIA_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg}
                ],
                "temperature": 0.0,  # Deterministik untuk fakta
                "max_tokens": 300,
                "top_p": 1.0,
                "stop": ["PERTANYAAN:", "KONTEKS:", "Kamu adalah", "Rasikan"],  # Cegah prompt leak
            },
            timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            answer = data["choices"][0]["message"]["content"].strip()
            # Bersihkan thinking block
            answer = re.sub(r'<think>[\s\S]*?</think>', '', answer).strip()
            # Bersihkan markdown berlebihan
            answer = re.sub(r'\*{2,}', '', answer).strip()
            return answer, model
        else:
            # Fallback ke model kecil
            if use_big_model:
                return ask_llm(question, context, use_big_model=False)
            return f"[API Error {resp.status_code}]", model
    except Exception as e:
        if use_big_model:
            return ask_llm(question, context, use_big_model=False)
        return f"[Exception: {str(e)[:100]}]", model

# ── Evaluasi ─────────────────────────────────────────────────────────────────
def evaluate(answer: str, keywords: list) -> dict:
    answer_lower = answer.lower()
    hits = [kw for kw in keywords if kw.lower() in answer_lower]
    rate = len(hits) / len(keywords) if keywords else 0
    # Penalti jika jawaban adalah "tidak tersedia" tapi seharusnya ada
    is_not_found = "tidak tersedia" in answer_lower or "tidak ditemukan" in answer_lower
    if is_not_found:
        label = "TIDAK AKURAT"
    elif rate >= 0.6:
        label = "AKURAT"
    elif rate >= 0.3:
        label = "SEBAGIAN"
    else:
        label = "TIDAK AKURAT"
    return {"hits": hits, "rate": round(rate, 2), "label": label,
            "matched": len(hits), "total": len(keywords), "not_found_response": is_not_found}

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    SEP = "=" * 72
    print(SEP)
    print("  JAYA RESEARCH — QA Test v2.0 (NVIDIA Embedding + FAISS)")
    print(SEP)
    print(f"  Embedding : {EMBED_MODEL}")
    print(f"  LLM Model : {CHAT_MODEL}")
    print(f"  FAISS     : {'aktif' if HAS_FAISS else 'tidak tersedia'}")
    print(f"  API Key   : {'ada' if NVIDIA_API_KEY else 'TIDAK ADA'}")
    print()

    if not NVIDIA_API_KEY:
        print("  [ERROR] NVIDIA_API_KEY tidak ditemukan di .env!")
        return

    all_results = []
    grand_total = 0
    grand_akurat = 0
    grand_sebagian = 0

    for pdf_filename, qa_data in QA_BANK.items():
        pdf_path = PDF_FOLDER / pdf_filename
        label    = qa_data["label"]
        questions = qa_data["questions"]

        print(f"\n{'─'*72}")
        print(f"  PDF  : {pdf_filename[:68]}")
        print(f"  Topik: {label}")
        print(f"{'─'*72}")

        if not pdf_path.exists():
            print(f"  [!!] File tidak ditemukan!")
            continue

        # 1. Ekstrak teks
        print(f"  [1/3] Ekstrak teks...")
        t0 = time.time()
        pages = extract_structured_pages(pdf_path)
        cover_pages = pages[:5]  # Halaman 1-5 selalu masuk konteks
        print(f"        {len(pages)} halaman dalam {time.time()-t0:.1f}s")

        # 2. Chunking
        print(f"  [2/3] Chunking (800 char, 200 overlap)...")
        chunks = make_chunks(pages, chunk_size=800, overlap=200)
        print(f"        {len(chunks)} chunks dibuat")

        # 3. Build/load FAISS index
        print(f"  [3/3] FAISS index (NVIDIA embedding)...")
        t1 = time.time()
        index, indexed_chunks = get_or_build_index(pdf_path, chunks)
        print(f"        Selesai dalam {time.time()-t1:.1f}s")

        # 4. QA Loop
        pdf_results = {"file": pdf_filename, "label": label, "qa": []}
        qa_correct = 0
        qa_sebagian = 0

        for qa in questions:
            qid, question, gt, keywords = qa["id"], qa["q"], qa["gt"], qa["kw"]

            # Retrieve konteks
            context = retrieve_semantic(question, index, indexed_chunks, cover_pages, top_k=8)

            # Tanya LLM
            t2 = time.time()
            jaya_answer, model_used = ask_llm(question, context)
            elapsed = round(time.time() - t2, 2)

            # Evaluasi
            ev = evaluate(jaya_answer, keywords)
            if ev["label"] == "AKURAT":
                qa_correct += 1; grand_akurat += 1
            elif ev["label"] == "SEBAGIAN":
                qa_sebagian += 1; grand_sebagian += 1
            grand_total += 1

            # Tampilkan
            status = {"AKURAT": "[AKURAT  ]", "SEBAGIAN": "[SEBAGIAN]", "TIDAK AKURAT": "[MELESET ]"}[ev["label"]]
            model_tag = "ultra" if "ultra" in model_used else "nano"

            print(f"\n  [{qid}] {question}")
            print(f"  GT    : {gt}")
            print(f"  JAYA  : {jaya_answer[:280]}")
            print(f"  EVAL  : {status} ({ev['matched']}/{ev['total']} kw: {ev['hits']}) | {elapsed}s | {model_tag}")

            pdf_results["qa"].append({
                "id": qid, "question": question, "ground_truth": gt,
                "jaya_answer": jaya_answer, "eval": ev,
                "elapsed_sec": elapsed, "model": model_used
            })

        acc = round(qa_correct / len(questions) * 100)
        print(f"\n  Akurasi: {qa_correct}/{len(questions)} akurat, {qa_sebagian}/{len(questions)} sebagian = {acc}%")
        pdf_results["accuracy_pct"] = acc
        all_results.append(pdf_results)

    # ── Ringkasan ──────────────────────────────────────────────────────────
    grand_pct = round(grand_akurat / grand_total * 100) if grand_total else 0
    eff_pct   = round((grand_akurat + grand_sebagian) / grand_total * 100) if grand_total else 0

    print(f"\n{SEP}")
    print(f"  RINGKASAN GLOBAL")
    print(f"{SEP}")
    print(f"  Total pertanyaan   : {grand_total}")
    print(f"  [AKURAT ]          : {grand_akurat}  ({grand_pct}%)")
    print(f"  [SEBAGIAN]         : {grand_sebagian}  ({round(grand_sebagian/grand_total*100) if grand_total else 0}%)")
    print(f"  [MELESET ]         : {grand_total - grand_akurat - grand_sebagian}")
    print(f"  Akurasi Murni      : {grand_pct}%")
    print(f"  Akurasi Efektif    : {eff_pct}% (termasuk sebagian)")

    print(f"\n  Perbandingan vs v1:")
    print(f"    v1 (BM25 + nano-8b) : 35% akurat | 60% efektif")
    print(f"    v2 (FAISS + ultra)  : {grand_pct}% akurat | {eff_pct}% efektif")
    delta = grand_pct - 35
    print(f"    Delta               : {'+' if delta >= 0 else ''}{delta}% akurasi murni")

    print(f"\n  Akurasi per PDF:")
    for r in all_results:
        bar = "#" * (r["accuracy_pct"] // 10) + "-" * (10 - r["accuracy_pct"] // 10)
        print(f"    [{bar}] {r['accuracy_pct']:3d}% — {r['label']}")

    # Simpan hasil
    RESULTS_V2.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_V2, "w", encoding="utf-8") as f:
        json.dump({
            "version": "v2",
            "models": {"embed": EMBED_MODEL, "chat": CHAT_MODEL},
            "summary": {"total": grand_total, "akurat": grand_akurat, "sebagian": grand_sebagian, "pct": grand_pct, "eff_pct": eff_pct},
            "results": all_results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n  [FILE] Hasil: {RESULTS_V2}")
    print(SEP)


if __name__ == "__main__":
    main()
