#!/usr/bin/env python3
"""Canonical JAYA Core HTTP launcher with no fabricated fallback responses."""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_CORE_SRC = _ROOT / "packages" / "jaya-core" / "src"
_DEFAULT_PILLAR_MANIFEST = _PACKAGE_CORE_SRC / "jaya_core" / "contracts" / "40_pillars.yaml"


class CoreServerConfigurationError(RuntimeError):
    """Raised when the canonical service cannot be launched truthfully."""


def _canonical_components() -> tuple[Any, Callable[..., Any]]:
    """Load only the public Core configuration and service factory."""
    if str(_PACKAGE_CORE_SRC) not in sys.path:
        sys.path.insert(0, str(_PACKAGE_CORE_SRC))
    from jaya_core.core_config import CoreConfig
    from jaya_core.core_service import create_app

    return CoreConfig.from_env(core_dir=_ROOT), create_app


def _build_runtime(config: Any) -> Any:
    """Construct the production runtime from validated/discovered identity data."""
    from jaya_core.brain_v2.protection.dna_anchor import (
        DNAAnchor,
        DNAAnchorError,
        DNAFailureCode,
        EncryptedFileKeyStore,
    )
    from jaya_core.brain_v2.protection.hardware import (
        NodeBindingAuthority,
        WindowsDPAPIMachineProvider,
    )
    from jaya_core.brain_v2.protection.pqc import QuantumPolicy, QuantumSuite
    from jaya_core.brain_v2.protection.zero_trust import ZeroTrustAuthority
    from jaya_core.cognitive.runtime import JayaCoreRuntime
    from jaya_core.security.capsule import JayaCapsuleCodec
    from jaya_core.security.cryptographic_skin import CryptographicSkin
    from jaya_core.security.immune_system import ImmuneSystem
    from jaya_core.security.quantum_lifecycle import PersistentQuantumAuthority
    from jaya_core.security.sovereign_privacy import SovereignPrivacy
    from jaya_core.pillars import DynamicPillarRegistry, PillarRuntimeView

    if not config.data_dir.exists() or not config.data_dir.is_dir():
        raise CoreServerConfigurationError(
            "JAYA_CORE_DATA_DIR must exist before the runtime starts"
        )
    node_id = config.node_id or platform.node().strip()
    if not node_id:
        raise CoreServerConfigurationError(
            "JAYA_NODE_ID is required when host identity cannot be discovered"
        )
    puzzle_dirs = tuple(
        Path(item).expanduser()
        for item in os.environ.get("JAYA_CORE_PUZZLE_DIRS", "").split(os.pathsep)
        if item.strip()
    )
    identity_anchor = None
    if config.identity_required:
        key_store = EncryptedFileKeyStore(
            config.identity_dir / "keystore",
            config.identity_key_secret.get_secret_value(),
        )
        identity_anchor = DNAAnchor(config.identity_dir, key_store)
    zero_trust_authority = None
    if config.zero_trust_required:
        if identity_anchor is None:
            raise CoreServerConfigurationError("Zero Trust requires an enrolled DNA Anchor")

        def resolve_principal_state(principal_id: str) -> dict[str, object] | None:
            try:
                record = identity_anchor.load_identity()
            except DNAAnchorError as exc:
                if exc.code is DNAFailureCode.IDENTITY_REVOKED:
                    return {"active": False, "key_version": 0}
                raise
            if record.brain_id != principal_id:
                return None
            return {
                "active": True,
                "key_version": record.key_version,
            }

        zero_trust_authority = ZeroTrustAuthority(
            config.data_dir / "jaya_core_runtime.db",
            attestation_verifier=identity_anchor.verify_attestation,
            principal_state_resolver=resolve_principal_state,
        )
    privacy_guard = None
    if config.privacy_required:
        privacy_guard = SovereignPrivacy(
            config.data_dir / "jaya_core_runtime.db",
            config.privacy_key_secret.get_secret_value(),
        )
    hardware_binding = None
    hardware_boot_receipt = None
    hardware_key_context = None
    if config.hardware_lock_required:
        if identity_anchor is None:
            raise CoreServerConfigurationError("Hardware Locked requires an enrolled DNA Anchor")
        identity_record = identity_anchor.load_identity()
        hardware_binding = NodeBindingAuthority(
            config.data_dir / "jaya_core_runtime.db",
            WindowsDPAPIMachineProvider(),
            attestation_signer=lambda purpose, digest: identity_anchor.sign_attestation(
                purpose, digest
            ).to_dict(),
            attestation_verifier=identity_anchor.verify_attestation,
        )
        hardware_boot_receipt = hardware_binding.authorize_boot(
            identity_record.brain_id,
            node_id,
            os.urandom(32),
        )
        hardware_key_context = hardware_binding.binding_key_context(
            identity_record.brain_id,
            node_id,
        )
    cryptographic_skin = None
    if config.cryptographic_skin_required:
        if identity_anchor is None:
            raise CoreServerConfigurationError("Cryptographic Skin requires an enrolled DNA Anchor")
        cryptographic_skin = CryptographicSkin(
            config.data_dir / "jaya_core_runtime.db",
            config.cryptographic_skin_secret.get_secret_value(),
            attestation_signer=lambda purpose, digest: identity_anchor.sign_attestation(
                purpose, digest
            ).to_dict(),
            attestation_verifier=identity_anchor.verify_attestation,
            key_binding_context=hardware_key_context,
        )
    immune_system = None
    if config.immune_system_required:
        if identity_anchor is None or cryptographic_skin is None:
            raise CoreServerConfigurationError(
                "Immune System requires DNA Anchor and Cryptographic Skin"
            )
        immune_system = ImmuneSystem(
            config.data_dir / "jaya_core_runtime.db",
            config.data_dir,
            cryptographic_skin,
            attestation_signer=lambda purpose, digest: identity_anchor.sign_attestation(
                purpose, digest
            ).to_dict(),
            attestation_verifier=identity_anchor.verify_attestation,
        )
    quantum_authority = None
    if config.quantum_security_required:
        if cryptographic_skin is None:
            raise CoreServerConfigurationError("Quantum Security requires Cryptographic Skin")
        quantum_authority = PersistentQuantumAuthority(
            config.data_dir / "jaya_core_runtime.db",
            cryptographic_skin,
            QuantumPolicy(
                policy_version=config.quantum_policy_version,
                minimum_suite=QuantumSuite.HYBRID_ED25519_ML_DSA_65,
                asset_lifetime_days=config.quantum_asset_lifetime_days,
                threat_horizon_year=config.quantum_threat_horizon_year,
                allow_classical_until_year=config.quantum_classical_cutoff_year,
            ),
            current_year=datetime.now(timezone.utc).year,
        )
    capsule_codec = (
        JayaCapsuleCodec(
            cryptographic_skin,
            quantum_authority=quantum_authority,
            quantum_required=config.quantum_security_required,
        )
        if cryptographic_skin is not None
        else None
    )
    raw_manifests = os.environ.get("JAYA_PILLAR_MANIFEST_PATHS", "").strip()
    pillar_manifests = tuple(
        Path(item).expanduser().resolve()
        for item in raw_manifests.split(os.pathsep)
        if item.strip()
    ) or (_DEFAULT_PILLAR_MANIFEST.resolve(),)
    raw_registry_db = os.environ.get("JAYA_PILLAR_REGISTRY_DB", "").strip()
    pillar_registry_db = (
        Path(raw_registry_db).expanduser()
        if raw_registry_db
        else (config.data_dir / "pillar_registry.db")
    )
    if not pillar_registry_db.is_absolute():
        pillar_registry_db = config.data_dir / pillar_registry_db
    pillar_registry_db = pillar_registry_db.resolve()
    try:
        pillar_registry_db.relative_to(config.data_dir.resolve())
    except ValueError as exc:
        raise CoreServerConfigurationError(
            "JAYA_PILLAR_REGISTRY_DB must remain inside JAYA_CORE_DATA_DIR"
        ) from exc
    pillar_registry = DynamicPillarRegistry(
        database_path=pillar_registry_db,
        manifest_paths=pillar_manifests,
    )
    runtime = JayaCoreRuntime(
        db_path=config.data_dir / "jaya_core_runtime.db",
        node_id=node_id,
        puzzle_dirs=puzzle_dirs,
        identity_anchor=identity_anchor,
        identity_required=config.identity_required,
        privacy_guard=privacy_guard,
        privacy_required=config.privacy_required,
        zero_trust_authority=zero_trust_authority,
        zero_trust_required=config.zero_trust_required,
        cryptographic_skin=cryptographic_skin,
        cryptographic_skin_required=config.cryptographic_skin_required,
        hardware_binding=hardware_binding,
        hardware_boot_receipt=hardware_boot_receipt,
        hardware_lock_required=config.hardware_lock_required,
        immune_system=immune_system,
        immune_system_required=config.immune_system_required,
        quantum_authority=quantum_authority,
        quantum_security_required=config.quantum_security_required,
        capsule_codec=capsule_codec,
        pillar_registry=pillar_registry,
        narrative_db_path=config.narrative_path,
        narrative_required=config.identity_required,
        narrative_max_payload_bytes=config.narrative_max_payload_bytes,
        local_pillar_data_dir=config.data_dir / "pillar_capabilities",
        lineage_signing_key=(
            config.lineage_signing_key.get_secret_value().encode("utf-8")
            if config.lineage_signing_key
            else None
        ),
        twin_shared_secret=(
            config.twin_shared_secret.get_secret_value()
            if config.twin_enabled and config.twin_shared_secret
            else None
        ),
        twin_allowed_peers=config.twin_allowed_peers,
        ollama_base_url=config.ollama_base_url or None,
        local_model_name=config.local_pillar_model or None,
        local_model_timeout_seconds=config.local_model_timeout_seconds,
        ternary_model_path=config.ternary_model_path,
        ternary_model_sha256=config.ternary_model_sha256 or None,
    )
    runtime.pillar_runtime_view = PillarRuntimeView(
        pillar_registry,
        runtime.capability_registry,
    )
    return runtime


def build_app(*, runtime: Any | None = None) -> Any:
    """Build the canonical service with a real runtime by default."""
    config, factory = _canonical_components()
    active_runtime = runtime or _build_runtime(config)
    app = factory(config, runtime=active_runtime)
    if runtime is None and hasattr(active_runtime, "close"):
        if hasattr(app, "add_event_handler"):
            app.add_event_handler("shutdown", active_runtime.close)
        elif hasattr(app.router, "add_event_handler"):
            app.router.add_event_handler("shutdown", active_runtime.close)
    return app


def run_server(*, runtime: Any | None = None) -> None:
    """Run uvicorn using only validated host and port configuration."""
    try:
        import uvicorn
    except ImportError as exc:
        raise CoreServerConfigurationError("uvicorn is not installed") from exc
    config, factory = _canonical_components()
    active_runtime = runtime or _build_runtime(config)
    app = factory(config, runtime=active_runtime)
    if runtime is None and hasattr(active_runtime, "close"):
        if hasattr(app, "add_event_handler"):
            app.add_event_handler("shutdown", active_runtime.close)
        elif hasattr(app.router, "add_event_handler"):
            app.router.add_event_handler("shutdown", active_runtime.close)
    uvicorn.run(
        app,
        host=config.bind_host,
        port=config.bind_port,
        log_level="info",
    )


if __name__ == "__main__":
    try:
        run_server()
    except Exception as exc:
        print(f"JAYA Core server did not start: {exc}", file=sys.stderr)
        sys.exit(2)
