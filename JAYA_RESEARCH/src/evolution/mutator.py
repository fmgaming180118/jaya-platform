import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import config
import os
import shutil
import ast
from pathlib import Path
from typing import Optional, Tuple

from src.teacher import Teacher
from src.evolution.sandbox import EvolutionSandbox

class CodeMutator:
    """
    Responsible for evolving the codebase.
    Can rewrite functions, optimize algorithms, and fix bugs.
    """
    def __init__(self):
        self.brain = Teacher(model_type="coding") # Use Coding Model (Qwen/Llama-Coder)
        self.sandbox = EvolutionSandbox()
        self.backup_dir = Path(config.EVOLUTION_BACKUPS_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def evolve_file(self, target_file: str, instruction: str) -> bool:
        """
        Attempts to evolve a specific file based on instruction.
        Returns True if evolution was successful (tests passed), False otherwise.
        """
        target_path = Path(target_file)
        if not target_path.exists():
            print(f"[Mutator] Target file {target_file} not found.")
            return False

        # 1. Backup original
        backup_path = self.backup_dir / f"{target_path.name}.bak"
        shutil.copy(target_path, backup_path)

        try:
            # 2. Read original code
            with open(target_path, 'r', encoding='utf-8') as f:
                original_code = f.read()

            # 3. Generate Mutation
            print(f"[Mutator] Mutating {target_file}...")
            prompt = f"""
            You are JAYA Evolution Engine (Expert Python Developer).
            Target File: {target_file}
            Instruction: {instruction}
            
            Instead of rewriting the whole file, output one or more SEARCH/REPLACE blocks to apply changes.
            Use this exact format:
            
            <<<<<<< SEARCH
            [exact lines of code from original file to replace]
            =======
            [new lines of code to replace them with]
            >>>>>>> REPLACE
            
            Maintain all existing functionality unless asked to change it.
            Original Code reference:
            ```python
            {original_code}
            ```
            """
            
            mutated_response = self.brain.generate_completion(prompt)
            
            # Check if response contains search/replace blocks
            import re
            blocks = re.findall(
                r"<<<<<<<\s*SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>>\s*REPLACE",
                mutated_response,
                re.DOTALL
            )
            
            if blocks:
                mutated_code = original_code
                for search_block, replace_block in blocks:
                    if search_block in mutated_code:
                        mutated_code = mutated_code.replace(search_block, replace_block)
                    else:
                        # Pencocokan lebih longgar jika ada perbedaan spasi
                        search_clean = search_block.strip()
                        replace_clean = replace_block.strip()
                        if search_clean in mutated_code:
                            mutated_code = mutated_code.replace(search_clean, replace_clean)
                        else:
                            print(f"[Mutator] Warning: SEARCH block not found in original file.")
            else:
                # Fallback ke overwrite seluruh file jika LLM tidak menggunakan SEARCH/REPLACE
                mutated_code = mutated_response
                code_match = re.search(r"```python\s*(.*?)\s*```", mutated_code, re.DOTALL | re.IGNORECASE)
                if not code_match:
                    code_match = re.search(r"```\s*(.*?)\s*```", mutated_code, re.DOTALL | re.IGNORECASE)
                
                mutated_code = code_match.group(1).strip() if code_match else mutated_code.strip()

            # 4. Verify Syntax (Static Analysis)
            try:
                ast.parse(mutated_code)
            except SyntaxError as e:
                print(f"[Mutator] Mutation failed syntax check: {e}")
                return False

            # 5. Apply Mutation (Sandbox/Dry Run)
            # For now, we overwrite the file directly BUT we have a backup.
            # Ideally, we write to a temp file and run tests first.
            temp_test_file = target_path.parent / f"test_mut_{target_path.name}"
            with open(temp_test_file, 'w', encoding='utf-8') as f:
                f.write(mutated_code)
            
            # 6. Run Tests (EvolutionTest)
            # If the file has an associated test in tests/, run it.
            # For MVP, we just check if it imports and runs basic sanity.
            valid = self._validate_mutation(temp_test_file)
            
            if valid:
                print(f"[Mutator] Mutation validated! Applying to {target_file}")
                shutil.move(temp_test_file, target_path)
                return True
            else:
                print(f"[Mutator] Mutation failed validation. Reverting...")
                temp_test_file.unlink(missing_ok=True)
                return False

        except Exception as e:
            print(f"[Mutator] Evolution error: {e}")
            # Restore backup
            shutil.copy(backup_path, target_path)
            return False

    def _validate_mutation(self, file_path: Path) -> bool:
        """
        Runs basic validation on the mutated file.
        In the future, this will run pytest.
        """
        try:
            # Try to compile it
            with open(file_path, 'r', encoding='utf-8') as f:
                compile(f.read(), file_path, 'exec')
            return True
        except Exception:
            return False
