"""Optional developer helper for compiling the historical Cython smoke test."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    try:
        from Cython.Build import cythonize
        from setuptools import setup
    except ImportError as exc:
        raise SystemExit(
            "Install the optional Cython development dependency first."
        ) from exc

    test_source = Path(__file__).resolve().parents[1] / "tests" / "test_cython.py"
    setup(ext_modules=cythonize(str(test_source)))


if __name__ == "__main__":
    main()
