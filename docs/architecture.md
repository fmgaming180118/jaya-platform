# Jaya Research Architecture: The AI-Native Language Discovery System

This document describes the architecture of the **Jaya Research** self-improving AI system. The core mission is not just optimization, but **Logic Compression**: discovering a new, highly compact, and efficient "AI-Native Language" (machine code) that allows Advanced General Intelligence (AGI) to run on small, portable devices.

## High-Level Vision: "Big Brain, Small Body"

The architecture is designed to bridge the gap between massive cloud intelligence and portable local execution:
*   **The Goal**: Create an AGI that fits on a USB drive or small laptop ("The Body") but possesses the distilled wisdom of a supercomputer ("The Brain").
*   **The Method**: Use a massive "Teacher" model to distill complex reasoning into a compact, high-performance "New Language" (compiled bytecode) that the local "Student" engine can execute instantly.

## Core Components

### 1. The Engine & Runtime (`src/engine.py`, `src/engine_jit.py`)
The Runtime is the "Virtual Machine" for the AI's new language.
*   **`engine.py`**: The reference implementation of the runtime logic (Autograd/Reasoning Kernel).
*   **`engine_jit.py` (The Accelerator)**:
    *   **Function**: Acts as the JIT (Just-In-Time) compiler for the AI-Native language.
    *   **Mechanism**: Compiles high-level abstract logic into raw machine code (via Numba/LLVM).
    *   **Result**: Allows complex behavior to run with minimal resources, enabling portability.

### 2. Language Discovery & Compression (`src/discovery.py`)
This module is responsible for **Compressing Intelligence**.
*   **The Challenge**: Large models (LLMs) are too big for portable AGI.
*   **The Solution**:
    *   The **Teacher** (NVIDIA NIM Llama 3.1) analyzes complex problems.
    *   It **distills** the solution into a dense algorithmic form (the "Discovery").
    *   This "Discovery" is not just a summary, but executable code—a "compressed thought".
    *   **`discovery.py`** manages this loop: `Reasoning -> Distillation -> Code Generation`.

### 3. The Compiler ("Ascension") (`src/jit_discovery.py`)
This process translates the "Compressed Thoughts" into the "AI-Native Language".
*   **Input**: Python logic (the "Compressed Thought").
*   **Process**: "Ascension" re-writes this logic into strict, static-typed machine code instructions.
*   **Output**: A binary-compatible function that runs at C++ speeds.
*   **Why?**: To minimize the "energy cost" of thinking. A portable AGI must be efficient.

### 4. Immune System (`src/immune_system.py`, `src/safeguard.py`)
Safety is paramount when an AI rewrites its own kernel.
*   **Role**: Ensures that the "New Language" constructs are valid and safe.
*   **Process**:
    1.  **Backup**: Snapshot current state.
    2.  **Mutate**: Apply the new language construct.
    3.  **Verify**: Run integrity checks (`src/integrity.py`).
    4.  **Rollback**: If the new logic is unstable, revert instantly.

### 5. Persistent Memory ("Prasasti")
*   **Concept**: Once a skill or logic is discovered and compiled, it is saved as a "Prasasti" (Inscription).
*   **Storage**: These are small, efficient files (code + weights) stored in `discoveries/` and `discoveries_native/`.
*   **Portability**: This allows the "Mind" of the AI to be transferred simply by copying these small files, without needing to carry the massive "Teacher" model.

## Directory Structure

*   `src/`: The source code (the "DNA").
*   `discoveries/`: Compressed logic algorithms (Python).
*   `discoveries_native/`: Compiled AI-Native Language functions (Machine Code).
*   `backups/`: Safety snapshots.
*   `docs/`: Documentation.

## 🚀 How to Run

### 1. Run Logic Compression ("Edison Loop")
To let the AI distill complex reasoning into compact algorithms:
```bash
python src/discovery.py
```
*   **Action**: Teacher distills reasoning into `src/engine.py`.
*   **Output**: "Compressed Thoughts" saved in `discoveries/`.

### 2. Run Language Compilation ("Ascension")
To compile the compressed logic into the high-speed AI-Native Language:
```bash
python src/jit_discovery.py
```
*   **Action**: Compiles logic into `src/engine_jit.py` (Machine Code).
*   **Output**: Native functions saved in `discoveries_native/`.

### 3. Verify Efficiency
To measure the speed and efficiency of the new language:
```bash
python benchmark_jit.py
```
*   **Result**: Shows the efficiency gain (Speedup Factor).

### 4. Verify Compiler Status
To ensure the local environment supports the AI-Native language compilation:
```bash
python verify_numba.py
```
