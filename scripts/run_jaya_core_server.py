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
_CORE_ROOT = _ROOT / "JAYA_CORE"


class CoreServerConfigurationError(RuntimeError):
    """Raised when the canonical service cannot be launched truthfully."""


def _canonical_components() -> tuple[Any, Callable[..., Any]]:
    """Load only the public Core configuration and service factory."""
    # Legacy Core modules still use the canonical ``JAYA_CORE.src`` namespace,
    # while the service package uses ``src``. Both roots must resolve when this
    # launcher is executed from any working directory.
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    if str(_CORE_ROOT) not in sys.path:
        sys.path.insert(0, str(_CORE_ROOT))
    from src.core_config import core_config
    from src.core_service import create_app

    return core_config, create_app


def _build_runtime(config: Any) -> Any:
    """Construct the production runtime from validated/discovered identity data."""
    from src.brain_v2.protection.dna_anchor import (
        DNAAnchor,
        EncryptedFileKeyStore,
    )
    from src.brain_v2.protection.hardware import (
        NodeBindingAuthority,
        WindowsDPAPIMachineProvider,
    )
    from src.brain_v2.protection.pqc import QuantumPolicy, QuantumSuite
    from src.brain_v2.protection.zero_trust import ZeroTrustAuthority
    from src.cognitive.runtime import JayaCoreRuntime
    from src.security.capsule import JayaCapsuleCodec
    from src.security.cryptographic_skin import CryptographicSkin
    from src.security.immune_system import ImmuneSystem
    from src.security.quantum_lifecycle import PersistentQuantumAuthority
    from src.security.sovereign_privacy import SovereignPrivacy

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
            raise CoreServerConfigurationError(
                "Zero Trust requires an enrolled DNA Anchor"
            )
        zero_trust_authority = ZeroTrustAuthority(
            config.data_dir / "jaya_core_runtime.db",
            attestation_verifier=identity_anchor.verify_attestation,
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
            raise CoreServerConfigurationError(
                "Hardware Locked requires an enrolled DNA Anchor"
            )
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
            raise CoreServerConfigurationError(
                "Cryptographic Skin requires an enrolled DNA Anchor"
            )
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
            raise CoreServerConfigurationError(
                "Quantum Security requires Cryptographic Skin"
            )
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
    return JayaCoreRuntime(
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
    )


def build_app(*, runtime: Any | None = None) -> Any:
    """Build the canonical service with a real runtime by default."""
    config, factory = _canonical_components()
    active_runtime = runtime or _build_runtime(config)
    app = factory(config, runtime=active_runtime)
    if runtime is None:
        app.add_event_handler("shutdown", active_runtime.close)
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
    if runtime is None:
        app.add_event_handler("shutdown", active_runtime.close)
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
