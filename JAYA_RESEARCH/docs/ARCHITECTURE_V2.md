# JAYA Research Workspaces & NVIDIA Architecture

## 1. Model Standardization (NVIDIA NIM) 🧠
JAYA kini menggunakan standar **Strict No-Hardcoding** untuk model AI. Semua model dikonfigurasi melalui Environment Variables (`.env`) untuk fleksibilitas maksimal.

| Peran (Role) | Variabel Lingkungan | Model Default (Disarankan) | Deskripsi |
| :--- | :--- | :--- | :--- |
| **Reasoning** | `NVIDIA_LLAMA31_MODEL` | `nvidia/llama-3.1-nemotron-ultra-253b-v1` | Model "Otak" utama untuk sintesis, logika berat, dan pengambilan keputusan. |
| **Chat/Research** | `NVIDIA_CHAT_MODEL` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | Model seimbang untuk interaksi chat dan riset cepat. |
| **Coding** | `NVIDIA_CODING_MODEL` | `qwen/qwen3-coder-480b-instruct` | Spesialis pembuatan dan perbaikan kode. |
| **Vision** | `VIDEO_VLM_MODEL` | `nvidia/vila-1.5-40b` | Analisis visual (gambar/video). |
| **Embedding** | `NVIDIA_EMBEDDING_MODEL` | `nvidia/llama-3.2-nemoretriever-1b` | Mengubah teks menjadi vektor untuk pencarian (RAG). |

### Implementasi Kode
- **`src/teacher.py`**: Kelas `Teacher` sekarang menerima parameter `model_type` (`reasoning`, `chat`, `coding`, `vision`) untuk memilih model yang tepat secara dinamis.
- **`src/research/enhanced_rag.py`**: Menggunakan `NVIDIA_EMBEDDING_MODEL` untuk inisialisasi vector store.

---

## 2. Research Workspaces (Rooms) 📂
Fitur Workspaces memungkinkan isolasi data riset, sehingga topik yang berbeda tidak saling tercampur.

### Struktur Data
Setiap workspace memiliki folder sendiri di dalam `data/workspaces/`:

```text
data/
└── workspaces/
    ├── default/
    │   ├── vector_store.json    # Memori Vektor (RAG)
    │   └── knowledge_graph.json # Graf Pengetahuan
    ├── football_manager_2024/
    │   ├── vector_store.json
    │   └── knowledge_graph.json
    └── quantum_physics/
        ├── ...
```

### Komponen Utama
1.  **`WorkspaceManager` (`src/research/workspace_manager.py`)**:
    - Bertanggung jawab membuat (`create_workspace`), mendaftar (`list_workspaces`), dan mengelola path folder.
    - Menyimpan metadata workspace di `metadata.json`.

2.  **API Integration (`src/network/research_api.py`)**:
    - Endpoint `/workspaces/*` untuk manajemen room.
    - Endpoint `/chat` dan `/research/autonomous` sekarang menerima parameter `workspace_id`.
    - Menggunakan sistem *Lazy Loading* untuk memuat mesin RAG/Graph hanya saat dibutuhkan.

3.  **Frontend (UI)**:
    - **Sidebar Selector**: Dropdown untuk berpindah workspace.
    - **Persistence**: Browser mengingat room terakhir yang dibuka (`localStorage`).

---

## 3. Workflow Penggunaan
1.  User membuat room baru via UI (misal: "Project A").
2.  Backend membuat folder `data/workspaces/project_a`.
3.  User melakukan riset/chat di room tersebut.
4.  Semua dokumen PDF, hasil riset internet, dan memori chat disimpan *hanya* di folder `project_a`.
5.  Saat user pindah ke room "Default", konteks "Project A" hilang dari memori aktif, menjaga kebersihan konteks.
