from __future__ import annotations

import tomllib
from pathlib import Path

from jaya_core.core_config import CoreConfig
from jaya_research.config import ResearchSettings


WORKSPACE = Path(__file__).resolve().parents[2]
PYTHON_PACKAGES = ("jaya-core", "jaya-agent", "jaya-os", "jaya-research")
ALL_PACKAGES = (*PYTHON_PACKAGES, "jaya-android")
LEGACY_ROOTS = ("JAYA_CORE", "JAYA_AGENT", "JAYA_OS", "JAYA_RESEARCH", "JAYA_ANDROID")


def test_canonical_monorepo_roots_exist_and_legacy_roots_are_absent() -> None:
    required = (
        ".github",
        "benchmarks",
        "configs",
        "data",
        "docker",
        "logs",
        "outputs",
        "packages",
        "scripts",
        "tests",
        "tools",
    )

    assert all((WORKSPACE / name).is_dir() for name in required)
    assert all(not (WORKSPACE / name).exists() for name in LEGACY_ROOTS)


def test_every_component_has_an_owned_package_root() -> None:
    for package in ALL_PACKAGES:
        package_root = WORKSPACE / "packages" / package
        assert package_root.is_dir(), package
        assert (package_root / "README.md").is_file(), package

    for package in PYTHON_PACKAGES:
        package_root = WORKSPACE / "packages" / package
        module_name = package.replace("-", "_")
        assert (package_root / "pyproject.toml").is_file(), package
        assert (package_root / "src" / module_name / "__init__.py").is_file(), package
        assert (package_root / "tests").is_dir(), package


def test_uv_workspace_members_match_the_python_packages() -> None:
    configuration = tomllib.loads((WORKSPACE / "pyproject.toml").read_text(encoding="utf-8"))
    members = configuration["tool"]["uv"]["workspace"]["members"]

    assert members == [f"packages/{name}" for name in PYTHON_PACKAGES]
    assert all((WORKSPACE / member / "pyproject.toml").is_file() for member in members)


def test_default_runtime_paths_use_central_data_ownership(tmp_path: Path) -> None:
    core = CoreConfig.from_env({"JAYA_ENVIRONMENT": "test"})
    assert core.core_dir == WORKSPACE
    assert core.data_dir == (WORKSPACE / "data" / "jaya-core").resolve()
    assert core.model_path == (
        WORKSPACE / "data" / "models" / "jaya-core" / "JAYA_SOVEREIGN_V18.jay"
    ).resolve()

    empty_nim_config = tmp_path / "nim.yaml"
    empty_nim_config.write_text("{}\n", encoding="utf-8")
    research = ResearchSettings.load(
        environment={},
        config_path=WORKSPACE / "configs" / "research" / "research_config.yaml",
        nim_config_path=empty_nim_config,
    )
    assert research.base_dir == WORKSPACE
    assert research.root_dir == WORKSPACE
    assert research.data_dir == (WORKSPACE / "data" / "jaya-research").resolve()


def test_dynamic_pillar_contract_is_package_owned() -> None:
    manifest = (
        WORKSPACE
        / "packages"
        / "jaya-core"
        / "src"
        / "jaya_core"
        / "contracts"
        / "40_pillars.yaml"
    )
    extension_example = (
        WORKSPACE
        / "packages"
        / "jaya-core"
        / "examples"
        / "pillar-041-adaptive-evidence.yaml"
    )

    assert manifest.is_file()
    assert extension_example.is_file()
