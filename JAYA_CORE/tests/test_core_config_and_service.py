from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.core_config import ConfigurationError, CoreConfig
from src.core_service import DependencyStatus, create_app

_API_KEY = "api-" + ("a" * 40)
_SOUL_PASSWORD = "soul-" + ("b" * 40)
_PRIVACY_SECRET = "privacy-" + ("p" * 40)


def _environment(
    tmp_path: Path,
    *,
    runtime_environment: str = "test",
) -> tuple[dict[str, str], Path, Path]:
    model_path = tmp_path / "brain.jay"
    model_path.write_bytes(b"verified-test-model")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    values = {
        "JAYA_ENVIRONMENT": runtime_environment,
        "JAYA_SOUL_PASSWORD": _SOUL_PASSWORD,
        "JAYA_CORE_API_KEY": _API_KEY,
        "JAYA_MODEL_PATH": str(model_path),
        "JAYA_CORE_DATA_DIR": str(data_dir),
        "JAYA_CORE_BIND_HOST": "127.0.0.1",
        "JAYA_CORE_BIND_PORT": "8765",
        "JAYA_CORE_TRUSTED_HOSTS": "testserver",
    }
    if runtime_environment == "production":
        values["JAYA_PRIVACY_KEY_SECRET"] = _PRIVACY_SECRET
    return values, model_path, data_dir


def _config(tmp_path: Path) -> CoreConfig:
    environment, _, _ = _environment(tmp_path)
    return CoreConfig.from_env(environment, core_dir=tmp_path)


def _authorization() -> dict[str, str]:
    return {"Authorization": f"Bearer {_API_KEY}"}


def test_production_config_fails_closed_when_required_values_are_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigurationError) as captured:
        CoreConfig.from_env(
            {"JAYA_ENVIRONMENT": "production"},
            core_dir=tmp_path,
        )

    message = str(captured.value)
    assert "missing:JAYA_SOUL_PASSWORD" in message
    assert "missing:JAYA_CORE_API_KEY" in message
    assert "missing:JAYA_MODEL_PATH" not in message
    assert "missing:JAYA_CORE_BIND_HOST" in message


def test_conflicting_environment_names_fail_closed(tmp_path: Path) -> None:
    environment, _, _ = _environment(tmp_path)
    environment["JAYA_ENVIRONMENT"] = "development"
    environment["JAYA_ENV"] = "production"

    with pytest.raises(ConfigurationError) as captured:
        CoreConfig.from_env(environment, core_dir=tmp_path)

    assert "conflict:JAYA_ENVIRONMENT,JAYA_ENV" in str(captured.value)


def test_production_model_is_optional_until_model_puzzle_is_required(
    tmp_path: Path,
) -> None:
    environment, model_path, _ = _environment(
        tmp_path,
        runtime_environment="production",
    )
    model_path.unlink()
    environment.pop("JAYA_MODEL_PATH")

    optional = CoreConfig.from_env(environment, core_dir=tmp_path)
    assert optional.model_required is False

    environment["JAYA_REQUIRE_MODEL"] = "true"
    with pytest.raises(ConfigurationError) as captured:
        CoreConfig.from_env(environment, core_dir=tmp_path)
    assert "missing:JAYA_MODEL_PATH" in str(captured.value)


def test_production_requires_sovereign_privacy_secret(tmp_path: Path) -> None:
    environment, _, _ = _environment(tmp_path, runtime_environment="production")
    environment.pop("JAYA_PRIVACY_KEY_SECRET")

    with pytest.raises(ConfigurationError) as captured:
        CoreConfig.from_env(environment, core_dir=tmp_path)

    assert "missing:JAYA_PRIVACY_KEY_SECRET" in str(captured.value)


def test_identity_is_optional_but_required_mode_needs_secret_and_contained_path(
    tmp_path: Path,
) -> None:
    environment, _, data_dir = _environment(tmp_path)
    environment["JAYA_REQUIRE_IDENTITY"] = "true"
    with pytest.raises(ConfigurationError) as missing:
        CoreConfig.from_env(environment, core_dir=tmp_path)
    assert "missing:JAYA_IDENTITY_KEY_SECRET" in str(missing.value)

    environment["JAYA_IDENTITY_KEY_SECRET"] = "identity-" + ("c" * 40)
    environment["JAYA_IDENTITY_DIR"] = str(tmp_path / "outside-core-data")
    with pytest.raises(ConfigurationError) as escaped:
        CoreConfig.from_env(environment, core_dir=tmp_path)
    assert "invalid:JAYA_IDENTITY_DIR" in str(escaped.value)

    environment["JAYA_IDENTITY_DIR"] = str(data_dir / "identity")
    config = CoreConfig.from_env(environment, core_dir=tmp_path)
    assert config.identity_required is True
    assert config.identity_dir == (data_dir / "identity").resolve()
    assert environment["JAYA_IDENTITY_KEY_SECRET"] not in repr(config)


def test_zero_trust_requires_identity_and_privacy(tmp_path: Path) -> None:
    environment, _, _ = _environment(tmp_path)
    environment["JAYA_REQUIRE_ZERO_TRUST"] = "true"
    with pytest.raises(ConfigurationError) as missing_dependencies:
        CoreConfig.from_env(environment, core_dir=tmp_path)
    message = str(missing_dependencies.value)
    assert "invalid:JAYA_REQUIRE_ZERO_TRUST_REQUIRES_IDENTITY" in message
    assert "invalid:JAYA_REQUIRE_ZERO_TRUST_REQUIRES_PRIVACY" in message

    environment.update(
        {
            "JAYA_REQUIRE_IDENTITY": "true",
            "JAYA_IDENTITY_KEY_SECRET": "identity-" + ("i" * 40),
            "JAYA_REQUIRE_PRIVACY": "true",
            "JAYA_PRIVACY_KEY_SECRET": _PRIVACY_SECRET,
        }
    )
    config = CoreConfig.from_env(environment, core_dir=tmp_path)
    assert config.zero_trust_required is True
    assert config.privacy_required is True
    assert config.identity_required is True


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("JAYA_CORE_BIND_PORT", "not-a-port"),
        ("JAYA_CORE_BIND_PORT", "70000"),
        ("JAYA_CORE_CORS_ORIGINS", "*"),
        ("JAYA_CORE_CORS_ORIGINS", "http://public.example"),
        ("JAYA_CORE_CORS_ORIGINS", "https://public.example:notaport"),
        ("JAYA_CORE_TRUSTED_HOSTS", "*"),
    ),
)
def test_malformed_production_config_is_rejected_without_echoing_value(
    tmp_path: Path,
    name: str,
    value: str,
) -> None:
    environment, _, _ = _environment(
        tmp_path,
        runtime_environment="production",
    )
    environment[name] = value

    with pytest.raises(ConfigurationError) as captured:
        CoreConfig.from_env(environment, core_dir=tmp_path)

    assert f"invalid:{name}" in str(captured.value)
    if value not in {"*", "70000"}:
        assert value not in str(captured.value)


def test_config_diagnostics_and_repr_redact_secrets(tmp_path: Path) -> None:
    config = _config(tmp_path)

    rendered = f"{config!r}\n{config.to_safe_dict()}"

    assert _API_KEY not in rendered
    assert _SOUL_PASSWORD not in rendered
    assert "api_key_configured" in rendered
    assert "soul_password_configured" in rendered


def test_default_research_inbox_is_owned_by_core_data(tmp_path: Path) -> None:
    config = _config(tmp_path)

    assert config.research_inbox_path == (
        config.data_dir / "research_inbox" / "research_memory.json"
    )
    assert "JAYA_RESEARCH" not in config.research_inbox_path.parts
    assert config.research_inbox_path.is_relative_to(config.data_dir)


def test_cross_boundary_research_inbox_is_rejected(tmp_path: Path) -> None:
    environment, _, _ = _environment(tmp_path)
    environment["JAYA_RESEARCH_INBOX_PATH"] = str(
        tmp_path.parent / "outside-core" / "research_memory.json"
    )

    with pytest.raises(ConfigurationError) as captured:
        CoreConfig.from_env(environment, core_dir=tmp_path)

    assert "invalid:JAYA_RESEARCH_INBOX_PATH" in str(captured.value)


@dataclass
class _StaticDependency:
    name: str
    ready: bool
    critical: bool = True

    def check(self) -> DependencyStatus:
        return DependencyStatus(
            name=self.name,
            ready=self.ready,
            code="ready" if self.ready else "dependency_down",
            critical=self.critical,
        )


class _ReadyRuntime:
    is_awake = True

    def is_ready(self) -> bool:
        return True

    def chat(self, message: str) -> str:
        return f"processed:{message}"


class _ExplodingDependency:
    name = "secret_provider"
    critical = True

    def check(self) -> DependencyStatus:
        raise RuntimeError(_API_KEY)


def test_health_is_live_while_readiness_reports_dependency_down(
    tmp_path: Path,
) -> None:
    app = create_app(
        _config(tmp_path),
        runtime=_ReadyRuntime(),
        dependencies=(_StaticDependency("memory", False),),
    )
    with TestClient(app) as client:
        health = client.get("/healthz")
        readiness = client.get("/readyz")

    assert health.status_code == 200
    assert health.json()["status"] == "alive"
    assert readiness.status_code == 503
    dependencies = {item["name"]: item for item in readiness.json()["dependencies"]}
    assert dependencies["memory"] == {
        "name": "memory",
        "ready": False,
        "code": "dependency_down",
        "critical": True,
    }


def test_ready_requires_all_real_dependencies(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path), runtime=_ReadyRuntime())) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_probe_errors_are_redacted(tmp_path: Path) -> None:
    app = create_app(
        _config(tmp_path),
        runtime=_ReadyRuntime(),
        dependencies=(_ExplodingDependency(),),
    )
    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert _API_KEY not in response.text
    dependencies = {item["name"]: item for item in response.json()["dependencies"]}
    assert dependencies["secret_provider"]["code"] == "probe_failed"


def test_default_readiness_fails_when_runtime_is_not_attached(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_config(tmp_path))) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    dependencies = {item["name"]: item for item in response.json()["dependencies"]}
    assert dependencies["model_artifact"]["ready"] is True
    assert dependencies["data_directory"]["ready"] is True
    assert dependencies["api_authentication"]["ready"] is True
    assert dependencies["brain_runtime"]["code"] == "not_configured"


def test_readiness_fails_when_configured_model_disappears(tmp_path: Path) -> None:
    environment, _, _ = _environment(tmp_path)
    environment["JAYA_REQUIRE_MODEL"] = "true"
    config = CoreConfig.from_env(environment, core_dir=tmp_path)
    config.model_path.unlink()

    with TestClient(create_app(config, runtime=_ReadyRuntime())) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    dependencies = {item["name"]: item for item in response.json()["dependencies"]}
    assert dependencies["model_artifact"]["code"] == "missing"


def test_unavailable_thesis_route_requires_auth_then_returns_501(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_config(tmp_path))) as client:
        unauthenticated = client.post("/v1/thesis/generate")
        authenticated = client.post(
            "/v1/thesis/generate",
            headers=_authorization(),
        )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 501
    assert authenticated.json()["error"]["code"] == "capability_not_implemented"


def test_nonpublic_routes_fail_closed_without_api_key(tmp_path: Path) -> None:
    environment, _, _ = _environment(tmp_path)
    environment.pop("JAYA_CORE_API_KEY")
    config = CoreConfig.from_env(environment, core_dir=tmp_path)

    with TestClient(create_app(config)) as client:
        response = client.post("/v1/chat", json={"message": "hello"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "authentication_not_configured"


def test_cors_is_deny_by_default_and_explicit_when_allowed(
    tmp_path: Path,
) -> None:
    environment, _, _ = _environment(tmp_path)
    config = CoreConfig.from_env(environment, core_dir=tmp_path)
    with TestClient(create_app(config)) as client:
        denied = client.get(
            "/healthz",
            headers={"Origin": "https://untrusted.example"},
        )
    assert denied.status_code == 403

    environment["JAYA_CORE_CORS_ORIGINS"] = "https://trusted.example"
    allowed_config = CoreConfig.from_env(environment, core_dir=tmp_path)
    with TestClient(create_app(allowed_config)) as client:
        allowed = client.get(
            "/healthz",
            headers={"Origin": "https://trusted.example"},
        )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://trusted.example"


def test_authenticated_chat_uses_injected_runtime(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path), runtime=_ReadyRuntime())) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "hello"},
            headers=_authorization(),
        )

    assert response.status_code == 200
    assert response.json() == {"response": "processed:hello"}
