"""
Compile only agentic_search.py with the fixed ddgs import.
Run from JAYA_CORE directory: python scripts/compile_agentic.py build_ext --inplace
"""
from setuptools import setup
from Cython.Build import cythonize
from setuptools.extension import Extension
import os
import shutil

src_file = "src/brain_v2/engine/agentic_search.py"
c_flags = ["/O2"] if os.name == 'nt' else ["-O2"]

ext = Extension(
    "src.brain_v2.engine.agentic_search",
    [src_file],
    extra_compile_args=c_flags
)

setup(
    name="Jaya AgenticSearch Patch",
    ext_modules=cythonize(
        [ext],
        compiler_directives={'language_level': "3", 'always_allow_keywords': True},
        annotate=False
    ),
)
