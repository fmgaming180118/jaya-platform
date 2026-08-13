
import os
import sys

class Introspection:
    def __init__(self, root_dir="src"):
        self.root_dir = root_dir

    def read_module_source(self, module_name):
        """
        Reads the source code of a module in the root_dir.
        e.g. read_module_source("engine.py")
        """
        path = os.path.join(self.root_dir, module_name)
        if not os.path.exists(path):
            return f"[ERROR] Module {module_name} not found."
        
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def get_all_modules(self):
        """
        Lists all python files in the root_dir.
        """
        files = [f for f in os.listdir(self.root_dir) if f.endswith(".py")]
        return files

    def analyze_complexity(self, source_code):
        """
        Simple heuristic to measure complexity (LOC).
        """
        lines = source_code.split('\n')
        loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])
        return loc

if __name__ == "__main__":
    intro = Introspection()
    print("[*] Scan Self:")
    modules = intro.get_all_modules()
    print(f"Found modules: {modules}")
    
    print("\n[*] Reading DNA (engine.py):")
    source = intro.read_module_source("engine.py")
    print(f"Length: {len(source)} chars")
    print(f"Complexity: {intro.analyze_complexity(source)} LOC")
    print(f"Preview:\n{source[:100]}...")
