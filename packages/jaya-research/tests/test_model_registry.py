"""Offline tests for the typed NVIDIA model registry boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from jaya_research.network.model_registry import (
    ModelRegistryConfigurationError,
    NVIDIARegistryService,
    validate_model_id,
)
from jaya_research.provider_errors import ProviderPolicy


def test_missing_credential_is_explicit_and_does_not_call_provider() -> None:
    called = False

    def factory(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not be constructed")

    result = NVIDIARegistryService(
        api_key=None,
        base_url="https://integrate.api.nvidia.com/v1",
        configured_models=["nvidia/model-a"],
        client_factory=factory,
    ).list_models()

    assert result.status == "UNAVAILABLE_NO_CREDENTIAL"
    assert result.provider_models == ()
    assert result.configured_models == ("nvidia/model-a",)
    assert called is False


def test_provider_call_uses_timeout_no_internal_retry_and_sorted_ids() -> None:
    captured = {}
    fake_client = SimpleNamespace(
        models=SimpleNamespace(
            list=lambda: SimpleNamespace(
                data=[
                    SimpleNamespace(id="nvidia/model-b"),
                    SimpleNamespace(id="nvidia/model-a"),
                ]
            )
        )
    )

    def factory(**kwargs):
        captured.update(kwargs)
        return fake_client

    result = NVIDIARegistryService(
        api_key="secret-present-but-never-returned",
        base_url="https://integrate.api.nvidia.com/v1",
        configured_models=["nvidia/configured"],
        policy=ProviderPolicy(
            connect_timeout_seconds=1,
            read_timeout_seconds=7,
            max_attempts=1,
            retry_base_delay_seconds=0,
            retry_max_delay_seconds=0,
        ),
        client_factory=factory,
    ).list_models()

    assert result.status == "AVAILABLE"
    assert result.provider_models == ("nvidia/model-a", "nvidia/model-b")
    assert captured["timeout"] == 7
    assert captured["max_retries"] == 0
    assert captured["base_url"].startswith("https://")
    assert "secret-present" not in str(result.to_dict())


def test_provider_failure_is_typed_status_not_configured_fallback() -> None:
    class FailingModels:
        @staticmethod
        def list():
            raise TimeoutError("network timeout with no response")

    result = NVIDIARegistryService(
        api_key="configured-secret",
        base_url="https://integrate.api.nvidia.com/v1",
        configured_models=["nvidia/configured"],
        policy=ProviderPolicy(
            max_attempts=1,
            retry_base_delay_seconds=0,
            retry_max_delay_seconds=0,
        ),
        client_factory=lambda **_kwargs: SimpleNamespace(models=FailingModels()),
    ).list_models()

    assert result.status == "PROVIDER_ERROR"
    assert result.provider_models == ()
    assert result.provider_error["code"] == "provider_timeout_error"
    assert result.configured_models == ("nvidia/configured",)


@pytest.mark.parametrize(
    "model_id",
    ("", "../escape", "model with spaces", "model?secret=x"),
)
def test_model_ids_are_strictly_validated(model_id: str) -> None:
    with pytest.raises(ModelRegistryConfigurationError):
        validate_model_id(model_id)


def test_plain_http_provider_is_rejected_outside_explicit_test_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JAYA_ENV", "production")
    monkeypatch.delenv("JAYA_PROVIDER_ALLOW_INSECURE_TEST", raising=False)

    with pytest.raises(ModelRegistryConfigurationError, match="HTTPS"):
        NVIDIARegistryService(
            api_key="secret",
            base_url="http://provider.invalid/v1",
            configured_models=["nvidia/model"],
        )
