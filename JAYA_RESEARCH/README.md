
# Micro-AGI: The Neural Compiler Project 🧠⚡

> **Exploring Self-Optimizing Intelligence under 1GB VRAM Constraints.**

This project implements a "Silent Engineer" AI capable of recursive self-improvement. Instead of relying on massive LLMs for inference, it uses a Teacher model (NVIDIA NIM) to rewrite its own internal engine into highly optimized Machine Code (LLVM IR via Numba).

## 🚀 Key Achievements

| Feature | Status | Description |
| :--- | :--- | :--- |
| **AI-Native Language** | ✅ Active | Compiler translates Python -> Highly Compressed Machine Code. |
| **Hybrid Architecture** | ✅ Active | **50% Human** (Interface) + **50% Machine** (Core Logic). |
| **Logic Compression** | ✅ Active | "Edison Loop" distills complex thought into dense algorithms. |
| **Recursive Discovery** | ✅ Active | Continuous self-improvement loop for 24/7 research. |

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

## 🧬 The 50/50 Hybrid Architecture

The system is designed as a **Hybrid Entity**:

1.  **The Machine (50%):** The "Body" running on your local device.
    *   **Language:** AI-Native (Compressed Machine Code).
    *   **Role:** High-speed logic, math, and core processing.
    *   **Feature:** It is efficient, runs on minimal hardware, and is "read-only" to humans (binary/byte-code).

2.  **The Human Interface (50%):** The "Translator" (Teacher Model).
    *   **Language:** Natural Human Language (Indonesian/English).
    *   **Role:** Translates your questions into AI-Native code for the machine, then translates the machine's output back to you.
    *   **Flow:** `User Question` -> `Translator` -> `Machine Core` -> `Translator` -> `Human Answer`.

## 🧪 Usage

### 1. Run the "Unlimited Discovery" Loop (Recursive Research)
To let the AI continuously compress its own logic and discover better "AI-Native" encodings forever.
It will loop: *Dream -> Compress -> Test -> Ascend -> Repeat*.

```bash
# Terminal 1: Logic Compression (Edison Loop)
python src/discovery.py --forever
```

```bash
# Terminal 2: Language Compilation (Ascension Loop)
python src/jit_discovery.py --forever
```

*   **Result:** The AI will continuously rewrite its own `src/engine.py` and `src/engine_jit.py` with increasingly efficient, compressed logic.

### 2. Verify Efficiency Comparison
To see the difference between Python and Native Mode:
```bash
python test/benchmark_jit.py
```

### 3. Digital Twin (Language Lab)
Simulate the evolution of a new, highly efficient language:
```bash
# Run the Evolution Loop
python src/digital_twin_compiler.py

# Create Fine-Tuning Dataset
python src/generate_training_data.py
```
For more details, see [Digital Twin Documentation](docs/DIGITAL_TWIN.md).

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
-   [Walkthrough & Results](walkthrough.md)
-   [Current Task List](docs/task.md)
-   [Implementation Plan](docs/implementation_plan.md)

---
*Created by Micro-AGI Research Team.*
