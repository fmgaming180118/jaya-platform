"""
Compile speaker_id.py dan voice_bridge.py ke .pyd binary.
Run from JAYA_CORE: python scripts/compile_speaker.py build_ext --inplace
"""
from setuptools import setup
from Cython.Build import cythonize
from setuptools.extension import Extension
import os

c_flags = ["/O2"] if os.name == 'nt' else ["-O2"]

extensions = [
    Extension(
        "src.brain_v2.protection.speaker_id",
        ["src/brain_v2/protection/speaker_id.py"],
        extra_compile_args=c_flags
    ),
    Extension(
        "src.brain_v2.engine.voice_bridge",
        ["src/brain_v2/engine/voice_bridge.py"],
        extra_compile_args=c_flags
    ),
]

setup(
    name="Jaya Speaker Recognition Patch",
    ext_modules=cythonize(
        extensions,
        compiler_directives={'language_level': "3", 'always_allow_keywords': True},
        annotate=False
    ),
)
