import sys
from pathlib import Path
src_dir = Path(__file__).resolve().parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from teacher import Teacher

target_file = src_dir / "playground" / "math_demo.py"

print("[BEFORE MUTATION]")
with open(target_file, "r") as f:
    print(f.read())

teacher = Teacher(model_type="coding")
print(f"[AI CONSULTATION] Using model: {teacher.model}")

with open(target_file, "r") as f:
    code = f.read()

prompt = "Rewrite calculate_sum(n) to use math formula n*(n-1)//2 for O(1) time complexity instead of loop. Return ONLY Python code."
new_code = teacher.suggest_optimization(code, focus="O(1) time complexity using formula")

print("[AFTER AI MUTATION - WRITING TO DISK]")
print(new_code)

with open(target_file, "w", encoding="utf-8") as f:
    f.write(new_code)

print("[VERIFICATION] Reading back from file:")
with open(target_file, "r", encoding="utf-8") as f:
    print(f.read())
