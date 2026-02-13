
import os
import subprocess
import sys

target_dirs = [
    "src/brain_v2/engine",
    "src/brain_v2/format",
    "src/brain_v2/model",
    "src/brain_v2/network",
    "src/brain_v2/organism",
    "src/brain_v2/protection",
    "src/brain_v2/soul"
]

def compile_file(file_path):
    module_name = file_path.replace(os.sep, ".")[:-3]
    # Handle Windows paths for Cython source list
    source_path = file_path.replace(os.sep, '/').replace('\\', '/')
    
    setup_content = f"""
from setuptools import setup
from Cython.Build import cythonize
from setuptools.extension import Extension
import os

c_flags = ["/O2"] if os.name == 'nt' else ["-O2"]

setup(
    ext_modules=cythonize([
        Extension(
            "{module_name}",
            ["{source_path}"],
            extra_compile_args=c_flags
        )
    ], compiler_directives={{'language_level': "3", 'always_allow_keywords': True}})
)
"""
    with open("setup_temp.py", "w") as f:
        f.write(setup_content)
        
    print(f"Compiling {file_path}...")
    try:
        result = subprocess.run(
            [sys.executable, "setup_temp.py", "build_ext", "--inplace"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"PASS: {file_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"FAIL: {file_path}")
        print("---- ERROR ----")
        print(e.stderr[-500:]) # Last 500 chars
        print("---------------")
        return False

failed = []
passed = []

for d in target_dirs:
    if not os.path.exists(d): continue
    for root, dirs, files in os.walk(d):
        for file in files:
            if file == "awakening.py": # Only target this file
                path = os.path.join(root, file)
                if compile_file(path):
                    passed.append(path)
                else:
                    failed.append(path)

print(f"\nSummary: {len(passed)} Passed, {len(failed)} Failed.")
if failed:
    print("Failed files:")
    for f in failed:
        print(f"- {f}")
