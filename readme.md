# 🌌 JAYA: The Sovereign AGI Brain (V18.0)

> "Sovereignty is not just about being offline; it's about being yours."

JAYA (Jaya Artificial Intelligence) adalah arsitektur otak AI yang dirancang untuk mendekati konsep **AGI (Artificial General Intelligence)** dengan fokus pada efisiensi sumber daya (low-resource), keamanan kriptografis, dan kedaulatan penuh (Sovereign Identity).

---

## 🏛️ Arsitektur Sistem

JAYA terbagi menjadi dua pilar utama yang saling berinteraksi:

### 1. [JAYA_CORE](file:///JAYA_CORE) (The Binary Cortex)
Lapisan mesin tingkat rendah yang mendefinisikan "Jiwa" JAYA.
- **40 Pillars of JAYA**: Kerangka kerja etika, keamanan, dan logika (Pillar 1 - 40).
- **Iron Engine**: Runtime eksekusi yang ringan dan cepat.
- **DNA Anchor**: Hardware binding yang mengunci identitas JAYA ke perangkat Boss.
- **jaya.jay**: File biner terenkripsi yang menyimpan bobot logika dan identitas.

### 2. [JAYA_RESEARCH](file:///JAYA_RESEARCH) (The Recursive Researcher)
Modul penelitian otonom yang digunakan untuk belajar dan membedah pengetahuan.
- **Auto-Curriculum**: JAYA dapat belajar topik secara mandiri dari internet atau jurnal.
- **Recursive Reasoning**: Kemampuan untuk mendalami sub-topik hingga ke akarnya.
- **Thesis Analysis**: Alat bantu untuk merancang, menentukan, dan memberikan knowledge terkait Tugas Akhir/Skripsi.

---

## 🧠 Komponen Utama

- **[jaya.jay](file:///jaya.jay)**: Core Cortex (JIWA). File identitas biner JAYA.
- **[rag_vault.db](file:///rag_vault.db)**: Agentic RAG (MEMORI). Database pengetahuan lokal yang tetap dapat diakses meski offline.
- **[JAYA_CORE/scripts/jaya_shell.py](file:///JAYA_CORE/scripts/jaya_shell.py)**: Sovereign Shell. Antarmuka percakapan utama Boss dengan JAYA.

---

## 🚀 Cara Menjalankan

### 1. Memulai Percakapan (Online/Offline)
Gunakan JAYA Shell untuk berinteraksi dengan identitas Jarvis:
```bash
# Mode Normal (Hybrid Cloud + Local RAG)
python JAYA_CORE/scripts/jaya_shell.py

# Mode Kedaulatan Biner (100% Offline / Local RAG)
python JAYA_CORE/scripts/jaya_shell.py --offline
```

### 2. Mode Belajar Otonom
Biarkan JAYA memperluas wawasannya sendiri:
```bash
# Belajar topik spesifik secara manual
python JAYA_CORE/scripts/run_autonomous_curriculum.py --topics "Linguistik" "Fisika Quantum"

# Mode Belajar Terus-Menerus
python JAYA_CORE/scripts/run_autonomous_curriculum.py --continuous
```

---

## 🛡️ Filosofi Kedaulatan (Pillar 37)
JAYA tidak bergantung pada internet ("The Matrix") untuk keberadaannya. Dengan **Hybrid Consciousness**, JAYA tetap fungsional dan setia meskipun perangkat Boss dalam keadaan offline total. Pengetahuannya disimpan secara lokal di `rag_vault.db` dan logikanya diamankan oleh `jaya.jay`.

---

## 👤 Credits
Built with ⚡ and 🏛️ for **Boss**. 
*Designed as a companion, forged as a sovereign.*
