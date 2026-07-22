# JAYA_CORE Sovereign Superintelligence Roadmap
**Setara JARVIS — Di Dalam 200 MB**

> **Hard Constraint**: Total Model + RAG + Cache **< 200 MB** disk & RAM.
> **Visi**: JAYA tidak sekedar menjawab. JAYA *berpikir*, *merencanakan*, *mengingat*, *bereaksi proaktif*, dan *terus belajar* — persis seperti JARVIS dalam Iron Man, hanya dalam genggaman dan berdaulat penuh tanpa cloud.

---

## 🎯 Mengapa JARVIS, Bukan Sekedar Chatbot?

| Chatbot Biasa | JAYA Setara JARVIS |
| :--- | :--- |
| Hanya menjawab prompt | **Proaktif mengingatkan, merencanakan, & menginisiasi** |
| Lupa percakapan sebelumnya | **Memori episodik lintas sesi (ingat proyek, kebiasaan, preferensi)** |
| Tidak mengenal pengguna | **Profil pengguna dinamis: nama, tujuan, ritme kerja, domain riset** |
| Satu model untuk semua | **Sparse Micro-MoE: pakar berbeda diaktifkan per topik** |
| Tidak bisa merencanakan | **Hierarchical Task Planning: pecah tujuan jadi sub-langkah eksekusi** |
| Pasif menunggu perintah | **Agentic Loop: bertanya balik, memverifikasi, konfirmasi** |

---

## ⛔ Hard Constraint Ukuran (TIDAK BISA DILANGGAR)

```
┌─────────────────────────────────────────────────────────────────────┐
│    TOTAL JAYA_CORE FOOTPRINT  < 200 MB (disk) & < 200 MB (RAM)     │
├───────────────────────┬────────────────┬────────────────────────────┤
│  Komponen             │ Batas Maksimal │ Teknologi Target           │
├───────────────────────┼────────────────┼────────────────────────────┤
│ Model Weights (.jay)  │  < 150 MB      │ Qwen2.5-0.5B 2-bit packed  │
│                       │                │ SmolLM2-135M Instruct      │
│                       │                │ BitNet b1.58 (ternary)     │
├───────────────────────┼────────────────┼────────────────────────────┤
│ Vector RAG Embeddings │  < 20 MB       │ all-MiniLM-L6-v2 (23MB)   │
│ + SQLite KnowledgeDB  │                │ GraphRAG dalam SQLite       │
├───────────────────────┼────────────────┼────────────────────────────┤
│ KV-Cache Runtime      │  < 20 MB       │ H2O Eviction, 8K Sliding   │
├───────────────────────┼────────────────┼────────────────────────────┤
│ LoRA Micro-Adapters   │  < 5 MB each   │ Rank-8 LoRA per domain     │
├───────────────────────┼────────────────┼────────────────────────────┤
│  TOTAL                │  < 200 MB      │ Edge-sovereign 100% offline │
└───────────────────────┴────────────────┴────────────────────────────┘
```

---

## 📋 Checklist Peningkatan Menuju JARVIS-Level

### 🧠 Fase 1 — Core Neural Engine: Model Ultra-Compact Tapi Cerdas ✅ SELESAI

**Target**: Inferensi local berjalan < 3 detik per respons, di bawah 150 MB.
**Status**: ✅ Diimplementasi di `src/brain_v2/engine/slm_engine.py` | 16/16 tests pass

- [x] **1.1 Pilih & Integrasikan Model Inti (`SLMEngine`)**
  - [x] Model catalog: SmolLM2-135M-Instruct (~140MB fp16) & Qwen2.5-0.5B-Instruct (~180MB fp16).
  - [x] Loader via HuggingFace Transformers 5.4.0 + PyTorch 2.5.1 (CUDA enabled).
  - [x] Auto device detection: GPU (CUDA) → CPU fallback dengan INT8 dynamic quantization.
  - [x] Chat template auto-detection (SmolLM2/Qwen2.5 native + manual fallback).

- [x] **1.2 Domain Detection & LoRA Micro-Adapter Registry (< 5 MB per adapter, Rank-8)**
  - [x] `detect_domain()`: keyword-based domain classifier (thesis/code/math/conversation).
  - [x] 4 adapter slot terdaftar: `jaya_lora_thesis_id`, `jaya_lora_code_ktpy`, `jaya_lora_math_logic`, `jaya_lora_conversation_id`.
  - [x] Hot-swap adapter berdasarkan intent yang terdeteksi (tanpa restart).

- [x] **1.3 Structured Tool Calling + Sliding Context Window**
  - [x] 4 tool schemas: `rag_search`, `calculate`, `remember`, `list_files`.
  - [x] Brace-counting JSON parser untuk nested tool-call output.
  - [x] `SlidingContextWindow` dengan H2O KV-eviction — batas `max_tokens` dinamis.
  - [x] Server `run_jaya_core_server.py` diperbarui: SLMEngine primary, Pillar21 fallback.

---

### 🔍 Fase 2 — Knowledge Core: Micro-GraphRAG + Hybrid Retrieval (< 20 MB) ✅ SELESAI

**Target**: JAYA mengetahui *apa yang Bos kerjakan*, *dokumen apa yang dimiliki*, dan *fakta apa yang relevan*.
**Status**: ✅ Diimplementasi di `src/brain_v2/soul/hybrid_retriever.py` | 19/19 tests pass

- [x] **2.1 Compact Vector Embeddings**
  - [x] Deploy `all-MiniLM-L6-v2` (23MB) via `sentence-transformers` sebagai embedding engine.
  - [x] Embedding disimpan sebagai float32 blob di SQLite — zero external vector DB.
  - [x] Lazy-load model (hanya dimuat saat pertama kali dibutuhkan).
  - [x] `DenseVectorIndex`: cosine similarity search terhadap semua stored chunks.

- [x] **2.2 Hybrid Retrieval: BM25 + Dense (Reciprocal Rank Fusion, k=60)**
  - [x] `BM25SparseIndex`: SQLite FTS5 full-text search dengan porter tokenizer.
  - [x] `DenseVectorIndex`: cosine similarity dengan all-MiniLM-L6-v2 (384-dim).
  - [x] `HybridRetriever.retrieve()`: RRF fusion score = BM25_weight/(k+rank) + Dense_weight/(k+rank).
  - [x] `retrieve_facts()`: wrapper kompatibel dengan AgenticRAG interface.

- [x] **2.3 SQLite Micro-GraphRAG**
  - [x] `MicroGraphRAG`: tabel `kg_nodes` + `kg_edges` di SQLite tanpa dependensi eksternal.
  - [x] `add_edge()`, `neighbors()` (multi-hop BFS traversal), `query_path()` (BFS path finding).
  - [x] `extract_entities_from_text()`: heuristic regex-based entity extraction dari teks bebas Indonesia.
  - [x] `HybridRetriever` terintegrasi ke `run_jaya_core_server.py` sebagai primary RAG engine.

---

### 🧠 Fase 3 — Memory Architecture: Memori Episodik Lintas Sesi (Setara JARVIS) ✅ SELESAI

**Target**: JAYA *mengingat* Bos lintas hari, lintas sesi, lintas topik — persis JARVIS.
**Status**: ✅ Diimplementasi di `src/brain_v2/soul/episodic_memory.py` | 20/20 tests pass

- [x] **3.1 Episodic Long-Term Memory (Pillar 31)**
  - [x] `EpisodicMemory`: SQLite tabel `episodic_sessions` + `session_turns`.
  - [x] `save_session()`: simpan ringkasan + turns tiap akhir sesi.
  - [x] `get_recent_sessions()`: ambil N sesi terbaru dengan metadata lengkap.
  - [x] `retrieve_relevant()`: keyword-match search memori relevan untuk query baru.
  - [x] `build_recall_context()`: inject konteks memori ke system prompt JAYA.

- [x] **3.2 Dynamic User Profile Engine (Pillar 32)**
  - [x] `UserProfileEngine`: profil persistif SQLite — nama, topik riset, bab aktif, deadline.
  - [x] `update_from_turn()`: regex NLP ekstraksi profil dari setiap percakapan (inkremental).
  - [x] `UserProfile.to_context_string()`: format profil sebagai teks untuk system prompt.
  - [x] `set_custom_fact()`: simpan fakta bebas tentang pengguna ("Universitas: UI").
  - [x] Domain expertise tracking per sesi (thesis/code/math/general).

- [x] **3.3 Sliding Context Window + Narrative Compression**
  - [x] `NarrativeCompressor`: kompres daftar turns menjadi `SessionSummary` padat (< 400 karakter).
  - [x] `extract_topics()`: deteksi topik utama (Kotlin, Federated Learning, Matematika, dll).
  - [x] `extract_key_facts()`: ekstrak fakta kunci dari percakapan (skripsi, bug, deadline).
  - [x] `MemoryManager` facade: `start_session()` → `on_turn()` → `end_session()` lifecycle.
  - [x] SLMEngine terintegrasi: inject memori ke system prompt + update profil tiap turn.
  - [x] Server `run_jaya_core_server.py` diperbarui: MemoryManager aktif sejak startup.

---

### 🎭 Fase 4 — Dynamic Mixture of Experts (MoE) & Self-Reflection Loop ✅ SELESAI

**Target**: Expert ter-spesialisasi diaktifkan per intent + Reflexion self-correction loop.
**Status**: ✅ Diimplementasi di `src/brain_v2/engine/micro_moe.py` | 11/11 tests pass (66/66 total)

- [x] **4.1 Sparse Micro-MoE Router**
  - [x] `MicroMoERouter`: memilih 1 expert aktif per inferensi (Sparse 1-of-4) berdasarkan keyword scoring + domain hint.
  - [x] `feedback()`: dinamis memperbarui `gate_score` berdasarkan sinyal kualitas respons.

- [x] **4.2 4 Micro-Expert Modules**
  - [x] `expert_thesis`: Akademis, struktur BAB I–V, sitasi IEEE, gaya ilmiah Indonesia formal.
  - [x] `expert_code`: Software Engineering, Kotlin Android, Python, debugging, code blocks.
  - [x] `expert_logic`: Matematika, kalkulus, statistika, pembuktian step-by-step.
  - [x] `expert_dialogue`: Percakapan personal, hangat, proaktif, respons hangat khas JARVIS.

- [x] **4.3 Reflexion Self-Correction Loop**
  - [x] `ReflexionLoop`: scoring kandidat respons berdasarkan panjang, koherensi, domain alignment, anti-hallucination, anti-boilerplate.
  - [x] `select_best()`: memilih kandidat terbaik dari N hasil generasi.
  - [x] Auto-regeneration dengan parameter lebih ketat jika quality score < threshold.
  - [x] `MicroMoEEngine` facade terintegrasi penuh ke `SLMEngine`.

---

### 🤖 Fase 5 — Agentic Intelligence: Proaktif & Otonom (Setara JARVIS)

**Target**: JAYA bertindak seperti asisten sejati — bukan hanya reaktif, tapi proaktif.

- [ ] **5.1 Hierarchical Task Planner**
  - [ ] Pecah tujuan besar ("selesaikan BAB III") menjadi sub-langkah konkret yang dapat dieksekusi.
  - [ ] Track status dan kemajuan tiap sub-task.

- [ ] **5.2 Proactive Intelligence Engine (Pillar 29)**
  - [ ] Ingatkan Bos tentang deadline, tugas yang tertunda, atau dokumen yang belum selesai.
  - [ ] Inisiasi percakapan secara proaktif jika JAYA mendeteksi Bos membutuhkan bantuan.

- [ ] **5.3 Agentic Loop: Bertanya Balik & Konfirmasi**
  - [ ] Jika instruksi ambigu, JAYA bertanya balik sebelum berasumsi.
  - [ ] Konfirmasi sebelum tindakan destruktif (hapus, overwrite, kirim).

- [ ] **5.4 ArXiv Micro-Delta Self-Patching (< 5 MB per patch)**
  - [ ] Scan paper ArXiv kategori AI/LLM terkait topik riset Bos setiap hari.
  - [ ] Hasilkan micro-delta knowledge patch dan terapkan ke RAG vault secara otomatis.

---

## 📊 Benchmark Target: JAYA vs JARVIS vs Model Besar

| Kemampuan | GPT-4o / LLaMA-3 70B | **JAYA Target (< 200MB)** |
| :--- | :--- | :--- |
| **Ukuran Model** | 40 GB – 140 GB | **< 150 MB (Qwen2.5-0.5B 2-bit)** |
| **Memori Lintas Sesi** | Tidak ada | **✅ Episodik SQLite (ingat Bos lintas hari)** |
| **Profil Pengguna Dinamis** | Tidak ada | **✅ User Profile Engine (tahu topik riset Bos)** |
| **Proaktif / Inisiasi** | Tidak ada | **✅ Proactive Intelligence Engine** |
| **Context Window** | 128K Token | **8K–32K Token (H2O pruning < 20MB RAM)** |
| **Kebutuhan Internet** | 100% Cloud | **100% Offline / Sovereign Edge** |
| **Inferensi di HP Android** | Tidak mungkin | **✅ JayaNanoEngine on-device (Vivo)** |
| **Bahasa Indonesia Native** | Terbatas | **✅ LoRA Adapter + IndonesianResponder** |

---

## 🛣️ Urutan Prioritas Implementasi

```
Minggu 1-2  → Fase 1: Integrasikan model SLM GGUF + LoRA adapters
Minggu 3-4  → Fase 2: Micro-GraphRAG + Hybrid BM25+Dense retrieval
Bulan 2     → Fase 3: Memori episodik lintas sesi + sliding context window
Bulan 3     → Fase 4: Micro-MoE routing + Reflexion loop
Bulan 4+    → Fase 5: Proactive agentic + ArXiv auto-patching
```

---

*Document version: 3.0.0 — JAYA_CORE Sovereign Superintelligence: JARVIS-Level in 200 MB*
