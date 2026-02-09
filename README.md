
# Micro-AGI: The Neural Compiler Project 🧠⚡

> **Exploring Self-Optimizing Intelligence under 1GB VRAM Constraints.**

This project implements a "Silent Engineer" AI capable of recursive self-improvement. Instead of relying on massive LLMs for inference, it uses a Teacher model (NVIDIA NIM) to rewrite its own internal engine into highly optimized Machine Code (LLVM IR via Numba).

## 🚀 Key Achievements

| Feature | Status | Description |
| :--- | :--- | :--- |
| **Neural Compiler** | ✅ Active | Custom MicroGrad Engine rewritten by AI for speed. |
| **Digital Immune System** | ✅ Active | Integrity checks & auto-rollback prevent broken code. |
| **Continuous Discovery** | ✅ Active | "Edison Loop" finds novel math & logic automatically. |
| **Native Ascension** | ✅ Active | **52x Speedup** using Numba JIT compilation. |
| **Memory System** | ✅ Active | JSON-based RAG prevents repetitive mistakes. |

## 🛠️ Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/yourusername/micro-agi.git
    cd micro-agi
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment**
    Copy `.env.example` to `.env` and add your NVIDIA API Key:
    ```bash
    cp .env.example .env
    # Edit .env with your NVIDIA_API_KEY
    ```

## 🧪 Usage

### 1. Run the "Edison" Discovery Loop
To let the AI continuously research better math for its engine:
```bash
python src/discovery.py
```
*   **Result:** Winning code is saved in `discoveries/`.

### 2. Run the "Ascension" JIT Loop (Phase 6)
To evolve the AI into Native Machine Code (Numba/LLVM):
```bash
python src/jit_discovery.py
```
*   **Result:** Native optimizations are saved in `discoveries_native/`.

### 3. Verify Performance
To see the difference between Python and Native Mode:
```bash
python benchmark_jit.py
```

## 📂 Project Structure

-   `src/engine.py`: The core Autograd engine (Python).
-   `src/engine_jit.py`: The optimized Native engine (Numba).
-   `src/optimizer.py`: The Self-Rewrite logic.
-   `src/immune_system.py`: Safety protocols (Backup/Restore).
-   `src/teacher.py`: Interface to NVIDIA NIM (Llama 3.1 253B).
-   `src/discovery.py`: The automated research loop.

## 📖 Documentation

For detailed research notes, see:
-   [Detailed Project Summary](docs/PROJECT_SUMMARY.md)
-   [LLM vs Neural Compiler Comparison](docs/comparison_llm_vs_neural_compiler.md)
-   [Walkthrough & Results](walkthrough.md)

---
*Created by Micro-AGI Research Team.*
