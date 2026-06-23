"""
test_qa_jaya.py
================
Pengujian akurasi JAYA Research: 5 pertanyaan per PDF
Sistem: Ekstrak teks -> Cari konteks relevan (BM25) -> Jawab dengan NVIDIA LLM
Bandingkan jawaban JAYA vs ground truth dari dokumen.

Jalankan:
  cd JAYA_RESEARCH
  .\.venv312\Scripts\python.exe test_qa_jaya.py
"""

import sys
import os
import re
import json
import time
import math
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Load .env
JAYA_ROOT = Path(__file__).parent
ENV_PATH  = JAYA_ROOT / ".env"

def load_dotenv(path):
    env = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

ENV = load_dotenv(ENV_PATH)
NVIDIA_API_KEY    = ENV.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL   = ENV.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL      = ENV.get("QLORA_OLLAMA_MODEL", "qwen3:4b")

# Gunakan LLM yang lebih cepat untuk pengujian
NVIDIA_CHAT_MODEL = "nvidia/llama-3.1-nemotron-nano-8b-v1"

PDF_FOLDER = Path(r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir")
RESULTS_PATH = JAYA_ROOT / "data" / "test_qa_results.json"

# ── Cek library ───────────────────────────────────────────────────────────────
try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    print("[ERROR] pdfplumber tidak tersedia. Jalankan: pip install pdfplumber")
    sys.exit(1)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── Definisi QA per PDF ───────────────────────────────────────────────────────
QA_BANK = {
    "1318029_Affifah Nasrillah Fajri_TA.pdf": {
        "label": "TA Affifah — Monitoring Scrap (PT SKF Indonesia)",
        "questions": [
            {
                "id": "A1",
                "question": "Apa judul lengkap Tugas Akhir ini dan di perusahaan apa diimplementasikan?",
                "ground_truth": "Pengembangan Sistem Monitoring Scrap Product dengan Penyajian Menggunakan Chart.JS pada Departemen Produksi di PT SKF Indonesia",
                "keywords": ["scrap", "chart.js", "SKF", "monitoring", "departemen produksi"]
            },
            {
                "id": "A2",
                "question": "Siapa nama mahasiswa yang mengerjakan TA ini dan berapa NIM-nya?",
                "ground_truth": "Affifah Nasrillah Fajri, NIM 1318029, Program Studi Sistem Informasi Industri Otomotif (SIIO)",
                "keywords": ["Affifah", "1318029", "SIIO", "Nasrillah"]
            },
            {
                "id": "A3",
                "question": "Teknologi front-end apa yang digunakan untuk visualisasi data dalam sistem ini?",
                "ground_truth": "Chart.JS digunakan untuk visualisasi/penyajian data scrap product",
                "keywords": ["chart.js", "Chart", "visualisasi", "chart"]
            },
            {
                "id": "A4",
                "question": "Apa masalah utama yang melatarbelakangi pengembangan sistem monitoring scrap product ini?",
                "ground_truth": "Masalah pencatatan scrap yang masih manual/tidak efisien di departemen produksi PT SKF Indonesia",
                "keywords": ["masalah", "manual", "scrap", "pencatatan", "produksi"]
            },
            {
                "id": "A5",
                "question": "Sebutkan salah satu peneliti terdahulu yang dijadikan referensi dalam penelitian ini beserta tahunnya!",
                "ground_truth": "Fatimah Azzahra, Adam Hendra Brata, dan Komang Candra Brata (2022) — penelitian monitoring truk tangki air berbasis GIS",
                "keywords": ["Azzahra", "Fatimah", "2022", "Rangga", "Widiyanto"]
            }
        ]
    },
    "1319058_Ihsan Ali_TA.pdf": {
        "label": "TA Ihsan Ali — LMS Odoo (PT Astra Otoparts)",
        "questions": [
            {
                "id": "B1",
                "question": "Apa judul Tugas Akhir ini dan di divisi mana diimplementasikan?",
                "ground_truth": "Implementasi Learning Management System untuk Pelatihan Karyawan menggunakan Odoo pada PT Astra Otoparts Tbk Divisi Nusametal",
                "keywords": ["Learning Management System", "Odoo", "Nusametal", "Astra Otoparts"]
            },
            {
                "id": "B2",
                "question": "Siapa nama mahasiswa dan berapa NIM-nya?",
                "ground_truth": "Ihsan Ali, NIM 1319058, Program Studi Sistem Informasi Industri Otomotif",
                "keywords": ["Ihsan Ali", "1319058", "SIIO"]
            },
            {
                "id": "B3",
                "question": "Platform atau aplikasi apa yang digunakan untuk mengimplementasikan LMS dalam penelitian ini?",
                "ground_truth": "Odoo digunakan sebagai platform LMS untuk pelatihan karyawan",
                "keywords": ["Odoo", "platform", "LMS", "aplikasi"]
            },
            {
                "id": "B4",
                "question": "Apa itu BPMN dan elemen apa saja yang disebutkan dalam dokumen ini?",
                "ground_truth": "BPMN (Business Process Model and Notation) — elemen: Flow Object (Events, Activities, Gateways), Swimlanes (Pools, Lines), Connecting Objects (Sequence Flows, Message Flows, Associations), Artifacts",
                "keywords": ["BPMN", "Business Process", "Events", "Activities", "Gateways", "Swimlanes"]
            },
            {
                "id": "B5",
                "question": "Kapan Tugas Akhir Ihsan Ali disetujui oleh dosen pembimbing?",
                "ground_truth": "5 Juni 2023",
                "keywords": ["Juni 2023", "2023", "5 Juni", "persetujuan", "dosen pembimbing"]
            }
        ]
    },
    "Peraturan Direktur Nomor 02 Tahun 2021 tentang Penetapan Pedoman Tugas Akhir Politeknik STMI Jakarta Secure.pdf": {
        "label": "Pedoman TA Politeknik STMI Jakarta (2021)",
        "questions": [
            {
                "id": "C1",
                "question": "Apa warna cover Tugas Akhir untuk Program Studi SIIO (Sistem Informasi Industri Otomotif)?",
                "ground_truth": "Biru Muda dengan kode warna #40bbe3, dijilid Hardcover",
                "keywords": ["SIIO", "biru muda", "#40bbe3", "Biru", "cover"]
            },
            {
                "id": "C2",
                "question": "Apa warna cover untuk Program Studi TIO (Teknik Industri Otomotif)?",
                "ground_truth": "Hitam dengan kode warna #000000, dijilid Hardcover",
                "keywords": ["TIO", "hitam", "#000000", "Hitam", "cover"]
            },
            {
                "id": "C3",
                "question": "Siapa Pengarah dari Tim Penyusun Pedoman Tugas Akhir ini?",
                "ground_truth": "Dr. Mustofa, S.T., M.T.",
                "keywords": ["Mustofa", "Pengarah", "Dr.", "M.T"]
            },
            {
                "id": "C4",
                "question": "Berapa nomor keputusan Direktur yang menjadi dasar pembentukan tim penyusun pedoman ini?",
                "ground_truth": "Nomor: 444/BPSDMI/STMI/KEP/V/2021",
                "keywords": ["444", "BPSDMI", "KEP", "2021", "keputusan"]
            },
            {
                "id": "C5",
                "question": "Apa saja aspek penilaian dalam rubrik sidang Tugas Akhir?",
                "ground_truth": "Kesesuaian latar belakang masalah, perumusan masalah dan tujuan penelitian (dengan skala SB/B/C/K)",
                "keywords": ["penilaian", "latar belakang", "perumusan masalah", "tujuan penelitian", "sidang", "SB", "aspek"]
            }
        ]
    },
    "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf": {
        "label": "TA Hanny Kurnia Putri — Procurement (PT Akebono Brake)",
        "questions": [
            {
                "id": "D1",
                "question": "Apa judul Tugas Akhir dan di perusahaan mana sistem diimplementasikan?",
                "ground_truth": "Implementasi Sistem Informasi Procurement Berbasis Web dengan PHP dan SQL Server pada PT Akebono Brake Astra Indonesia",
                "keywords": ["Procurement", "Akebono", "PHP", "SQL Server", "web"]
            },
            {
                "id": "D2",
                "question": "Siapa nama mahasiswa dan berapa NIM-nya?",
                "ground_truth": "Hanny Kurnia Putri, NIM 1318001, Program Studi Sistem Informasi Industri Otomotif",
                "keywords": ["Hanny", "Kurnia", "1318001", "SIIO"]
            },
            {
                "id": "D3",
                "question": "Teknologi apa yang digunakan untuk membangun sistem informasi procurement ini?",
                "ground_truth": "PHP sebagai bahasa pemrograman dan SQL Server sebagai database, berbasis web",
                "keywords": ["PHP", "SQL Server", "web", "bahasa pemrograman", "database"]
            },
            {
                "id": "D4",
                "question": "Sebutkan salah satu peneliti terdahulu yang dijadikan referensi dalam penelitian ini!",
                "ground_truth": "Afifah & Setyantoro (2021) — Rancangan Sistem Pemilihan dan Penetapan Harga dalam Proses Pengadaan Barang dan Jasa Logistik Berbasis Web; atau Qotimah (2017) — Sistem Informasi E-Procurement",
                "keywords": ["Afifah", "Setyantoro", "2021", "Qotimah", "2017", "E-Procurement"]
            },
            {
                "id": "D5",
                "question": "Apa elemen BPMN 'Gateway' menurut dokumen ini?",
                "ground_truth": "Gateway adalah pengontrol divergensi dan konvergensi sequence flow dalam proses, menentukan jalur branching, forking, merging, dan joining",
                "keywords": ["Gateway", "divergensi", "konvergensi", "sequence flow", "branching", "forking"]
            }
        ]
    }
}

# ── BM25-like retriever ───────────────────────────────────────────────────────
def tokenize(text):
    return re.findall(r'\b\w+\b', text.lower())

def bm25_score(query_tokens, doc_tokens, k1=1.5, b=0.75):
    doc_len = len(doc_tokens)
    avg_len = 300
    tf = Counter(doc_tokens)
    score = 0.0
    for qt in query_tokens:
        if qt in tf:
            f = tf[qt]
            idf = math.log(2)  # simplified
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / avg_len))
    return score

def retrieve_context(query: str, pages: list, top_k: int = 5) -> str:
    """Cari halaman paling relevan dengan BM25 sederhana."""
    q_tokens = tokenize(query)
    scored = []
    for page_data in pages:
        doc_tokens = tokenize(page_data.get("text", ""))
        score = bm25_score(q_tokens, doc_tokens)
        scored.append((score, page_data))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    context_parts = []
    for score, pd in top:
        if score > 0:
            context_parts.append(f"[Hal. {pd['page']}]\n{pd['text'][:800]}")

    return "\n\n---\n\n".join(context_parts) if context_parts else "Tidak ada konteks relevan ditemukan."

# ── Ekstrak teks per halaman ──────────────────────────────────────────────────
def extract_pages(pdf_path: Path) -> list:
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = (page.extract_text(x_tolerance=2, y_tolerance=2) or "").strip()
            # Tambahkan tabel ke teks halaman
            try:
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        if row:
                            text += "\n" + " | ".join(str(c or "") for c in row)
            except Exception:
                pass
            if text:
                pages.append({"page": i, "text": text})
    return pages

# ── NVIDIA LLM Call ───────────────────────────────────────────────────────────
def ask_nvidia(question: str, context: str, use_ollama: bool = False) -> str:
    """Kirim pertanyaan ke NVIDIA NIM API."""
    if not HAS_REQUESTS:
        return "[ERROR: requests tidak tersedia]"

    prompt = f"""Kamu adalah asisten penelitian yang menjawab pertanyaan berdasarkan dokumen akademik.
Jawab HANYA berdasarkan konteks di bawah ini. Jawab dalam Bahasa Indonesia.
Jika tidak ada informasi yang relevan, katakan "Informasi tidak ditemukan di dokumen."

KONTEKS DOKUMEN:
{context}

PERTANYAAN: {question}

JAWABAN (singkat dan presisi, 1-3 kalimat):"""

    if NVIDIA_API_KEY and not use_ollama:
        # NVIDIA NIM API
        try:
            resp = requests.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {NVIDIA_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": NVIDIA_CHAT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 256,
                    "top_p": 0.9,
                },
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                answer = data["choices"][0]["message"]["content"].strip()
                # Hapus <think> block jika ada
                answer = re.sub(r'<think>[\s\S]*?</think>', '', answer).strip()
                return answer
            else:
                return f"[NVIDIA API Error {resp.status_code}: {resp.text[:200]}]"
        except Exception as e:
            return f"[NVIDIA API Exception: {e}]"

    # Fallback: Ollama lokal
    try:
        ollama_model = ENV.get("QLORA_OLLAMA_MODEL", "qwen3:4b")
        ollama_host  = ENV.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        resp = requests.post(
            f"{ollama_host}/api/generate",
            json={"model": ollama_model, "prompt": prompt, "stream": False},
            timeout=60
        )
        if resp.status_code == 200:
            answer = resp.json().get("response", "").strip()
            answer = re.sub(r'<think>[\s\S]*?</think>', '', answer).strip()
            return answer
        else:
            return f"[Ollama Error {resp.status_code}]"
    except Exception as e:
        return f"[Ollama Exception: {e}]"

# ── Evaluasi akurasi sederhana ────────────────────────────────────────────────
def evaluate(answer: str, keywords: list) -> dict:
    """Hitung keyword match rate sebagai proxy akurasi."""
    answer_lower = answer.lower()
    hits = [kw for kw in keywords if kw.lower() in answer_lower]
    rate = len(hits) / len(keywords) if keywords else 0
    # Kategorikan
    if rate >= 0.6:
        label = "AKURAT"
    elif rate >= 0.3:
        label = "SEBAGIAN"
    else:
        label = "TIDAK AKURAT"
    return {"hits": hits, "rate": round(rate, 2), "label": label, "matched": len(hits), "total": len(keywords)}

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    SEP = "=" * 72

    print(SEP)
    print("  JAYA RESEARCH — Pengujian QA: 5 Pertanyaan per PDF")
    print(SEP)

    if NVIDIA_API_KEY:
        print(f"  LLM: NVIDIA NIM ({NVIDIA_CHAT_MODEL})")
    else:
        print("  LLM: Ollama lokal (NVIDIA API key tidak ditemukan)")
    print()

    all_results = []
    grand_total = 0
    grand_akurat = 0

    for pdf_filename, qa_data in QA_BANK.items():
        pdf_path = PDF_FOLDER / pdf_filename
        label    = qa_data["label"]
        questions = qa_data["questions"]

        print(f"\n{'─'*72}")
        print(f"  PDF : {pdf_filename[:65]}")
        print(f"  Topik: {label}")
        print(f"{'─'*72}")

        if not pdf_path.exists():
            print(f"  [!!] File tidak ditemukan: {pdf_path}")
            continue

        # Ekstrak teks
        print(f"  [>>] Mengekstrak teks dari {pdf_path.name}...")
        t0 = time.time()
        pages = extract_pages(pdf_path)
        print(f"  [OK] {len(pages)} halaman diekstrak dalam {time.time()-t0:.1f}s")

        pdf_results = {
            "file": pdf_filename,
            "label": label,
            "pages": len(pages),
            "qa": []
        }

        qa_correct = 0
        for qa in questions:
            qid      = qa["id"]
            question = qa["question"]
            gt       = qa["ground_truth"]
            keywords = qa["keywords"]

            # 1. Retrieve konteks
            context = retrieve_context(question, pages, top_k=6)

            # 2. Tanya LLM
            t1 = time.time()
            jaya_answer = ask_nvidia(question, context)
            elapsed = round(time.time() - t1, 2)

            # 3. Evaluasi
            eval_result = evaluate(jaya_answer, keywords)
            if eval_result["label"] == "AKURAT":
                qa_correct += 1
                grand_akurat += 1

            grand_total += 1

            # 4. Tampilkan
            status_icon = {
                "AKURAT": "[AKURAT]",
                "SEBAGIAN": "[SEBAGIAN]",
                "TIDAK AKURAT": "[MELESET]"
            }[eval_result["label"]]

            print(f"\n  [{qid}] {question}")
            print(f"  GROUND TRUTH: {gt}")
            print(f"  JAYA JAWAB : {jaya_answer[:300]}")
            print(f"  EVALUASI   : {status_icon} ({eval_result['matched']}/{eval_result['total']} keyword cocok: {eval_result['hits']}) | {elapsed}s")

            pdf_results["qa"].append({
                "id": qid,
                "question": question,
                "ground_truth": gt,
                "jaya_answer": jaya_answer,
                "eval": eval_result,
                "elapsed_sec": elapsed
            })

        akurasi_pdf = round(qa_correct / len(questions) * 100)
        print(f"\n  Akurasi PDF ini: {qa_correct}/{len(questions)} = {akurasi_pdf}%")
        pdf_results["accuracy_pct"] = akurasi_pdf
        all_results.append(pdf_results)

    # Global summary
    grand_pct = round(grand_akurat / grand_total * 100) if grand_total else 0
    print(f"\n{SEP}")
    print(f"  RINGKASAN GLOBAL")
    print(f"{SEP}")
    print(f"  Total pertanyaan : {grand_total}")
    print(f"  Jawaban akurat   : {grand_akurat}")
    print(f"  Jawaban sebagian : {sum(1 for r in all_results for qa in r['qa'] if qa['eval']['label'] == 'SEBAGIAN')}")
    print(f"  Jawaban meleset  : {sum(1 for r in all_results for qa in r['qa'] if qa['eval']['label'] == 'TIDAK AKURAT')}")
    print(f"  AKURASI KESELURUHAN: {grand_akurat}/{grand_total} = {grand_pct}%")
    print(f"\n  Akurasi per PDF:")
    for r in all_results:
        bar = "#" * (r["accuracy_pct"] // 10) + "-" * (10 - r["accuracy_pct"] // 10)
        print(f"    [{bar}] {r['accuracy_pct']:3d}% — {r['label']}")

    # Simpan hasil
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": grand_total,
                "akurat": grand_akurat,
                "pct": grand_pct
            },
            "results": all_results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n  [FILE] Hasil detail: {RESULTS_PATH}")
    print(SEP)


if __name__ == "__main__":
    main()
