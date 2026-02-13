
from setuptools import setup
from Cython.Build import cythonize
from setuptools.extension import Extension
import os

c_flags = ["/O2"] if os.name == 'nt' else ["-O2"]

setup(
    ext_modules=cythonize([
        Extension(
            "src/brain_v2/engine.awakening",
            ["src/brain_v2/engine/awakening.py"],
            extra_compile_args=c_flags
        )
    ], compiler_directives={'language_level': "3", 'always_allow_keywords': True})
)
