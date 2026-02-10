import os
import json
import glob
import random

class FineTuneGenerator:
    def __init__(self, data_dir="data/language_evolution"):
        self.data_dir = data_dir
        self.output_file = os.path.join("data", "finetune_dataset.jsonl")

    def get_latest_artifacts(self):
        """Find the latest Syntax Spec and Compiler."""
        specs = glob.glob(os.path.join(self.data_dir, "*.spec"))
        compilers = glob.glob(os.path.join(self.data_dir, "compiler_*.py"))
        
        if not specs or not compilers:
            return None, None
            
        # Sort by modification time (or name if timestamps in name)
        latest_spec = max(specs, key=os.path.getctime)
        latest_compiler = max(compilers, key=os.path.getctime)
        
        return latest_spec, latest_compiler

    def read_file(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def generate_dataset(self, num_samples=50):
        print(f"[DATASET] 💾 Generating Fine-Tuning Data...")
        
        spec_path, compiler_path = self.get_latest_artifacts()
        if not spec_path:
            print("[DATASET] ❌ No artifacts found. Run Digital Twin first.")
            return

        print(f"[DATASET] 📜 Using Spec: {spec_path}")
        print(f"[DATASET] ⚙️  Using Compiler: {compiler_path}")

        syntax_content = self.read_file(spec_path)
        compiler_content = self.read_file(compiler_path)

        dataset = []

        # 1. System Prompt Injection (The Context)
        # We teach the model WHO it is.
        system_msg = {
            "role": "system",
            "content": f"You are the JAYA-Native Compiler. You translate Python logic into the JAYA Language.\n\nSYNTAX SPEC:\n{syntax_content}\n\nCOMPILER LOGIC:\n{compiler_content}"
        }

        # 2. Synthetic Examples
        # In a real scenario, we'd have pairs of (Python Logc -> JAYA Code).
        # Since this is a simulation, we will generate "Meta-Examples" where we ask the model to implement core features.
        
        tasks = [
            "Implement a backward pass for Matrix Multiplication.",
            "optimize the ReLU activation function.",
            "Create a struct for a Tensor.",
            "Define the addition operation with gradient tracking."
        ]

        for i in range(num_samples):
            task = random.choice(tasks)
            entry = {
                "messages": [
                    system_msg,
                    {"role": "user", "content": f"Please {task} in JAYA-Native."},
                    # Ideally we would have the 'ground truth' JAYA code here.
                    # For this simulation, we use a placeholder that the user would replace or the AI would self-generate.
                    {"role": "assistant", "content": f"// JAYA-Native Implementation for {task}\n// Optimized for LLVM IR...\n[CODE_PLACEHOLDER_{i}]"}
                ]
            }
            dataset.append(entry)

        # 3. Save to JSONL
        with open(self.output_file, "w", encoding="utf-8") as f:
            for entry in dataset:
                f.write(json.dumps(entry) + "\n")
        
        print(f"[DATASET] ✅ Saved {len(dataset)} examples to {self.output_file}")
        print(f"[DATASET] 🚀 Ready for Fine-Tuning (Llama-3/Mistral/etc.)")

if __name__ == "__main__":
    generator = FineTuneGenerator()
    generator.generate_dataset()
