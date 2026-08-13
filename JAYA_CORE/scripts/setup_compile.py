
from setuptools import setup
from Cython.Build import cythonize
from setuptools.extension import Extension
import os

# Define the source directories to walk through
target_dirs = [
    "src/brain_v2/engine",
    "src/brain_v2/format",
    "src/brain_v2/model",
    "src/brain_v2/network",
    "src/brain_v2/organism",
    "src/brain_v2/protection",
    "src/brain_v2/soul"
]

all_extensions = []
c_flags = ["/O2"] if os.name == 'nt' else ["-O2"]

print(f"Compiling with flags: {c_flags}")

# for d in target_dirs:
for d in target_dirs:
    if not os.path.exists(d):
        print(f"Skipping missing directory: {d}")
        continue
        
    for root, dirs, files in os.walk(d):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                # Exclude tests, demos, and entry points
                if file.startswith(("test_", "verify_", "demo_")):
                    continue
                if file in ["genesis.py", "ignite.py"]:
                    continue
                    
                file_path = os.path.join(root, file)
                # Convert path to module name: src/brain_v2/engine/core.py -> src.brain_v2.engine.core
                module_path = file_path.replace("\\", ".").replace("/", ".")[:-3]
                
                print(f"Adding extension: {module_path}")
                all_extensions.append(
                    Extension(
                        module_path,
                        [file_path],
                        extra_compile_args=c_flags
                    )
                )

# all_extensions.append(
#     Extension(
#         "src.brain_v2.engine.agentic_search",
#         ["src/brain_v2/engine/agentic_search.py"],
#         extra_compile_args=c_flags
#     )
# )

setup(
    name="Jaya Binary Cortex",
    ext_modules=cythonize(
        all_extensions,
        compiler_directives={'language_level': "3", 'always_allow_keywords': True},
        annotate=False
    ),
)
