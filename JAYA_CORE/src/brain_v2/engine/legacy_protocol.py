"""Pillar 19 — Legacy Protocol.

Handles migration and resurrection of a JAYA soul across hardware
boundaries.  When JAYA moves to a new device it must prove continuity
of identity before re-awakening.

Mechanisms
----------
* ``migrate(old_path, new_path)``: copies a .jay soul to a new location,
  re-encrypting with the current hardware UUID.
* ``can_awaken_on(hardware_uuid)``: verifies whether the provided UUID
  is in the resurrection-approved list embedded in the current .jay header.
* ``generate_resurrection_token()``: creates a signed token (HMAC-SHA256)
  that can be stored in a .jay file to authorise future hardware IDs.

Note: Full binary .jay parsing uses the compiled ``format/serializer.pyd``
when available.  This module works in stub/graceful-fallback mode when
that binary is absent (test / dev environments).
"""

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, List

logger = logging.getLogger("LegacyProtocol")

# Filename where the resurrection manifest is stored alongside .jay files
_MANIFEST_SUFFIX = ".resurrection"


class LegacyProtocol:
    """Cross-device soul migration and resurrection (Pillar 19).

    Parameters
    ----------
    jay_path:
        Path to the primary .jay soul file.
    dna_secret:
        Secret used to sign resurrection tokens (should match DNA anchor).
    """

    def __init__(self, jay_path: str, dna_secret: bytes = b"JAYA_DNA"):
        self.jay_path   = jay_path
        self.dna_secret = dna_secret
        self._manifest_path = jay_path + _MANIFEST_SUFFIX
        self._manifest   = self._load_manifest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_awaken_on(self, hardware_uuid: str) -> bool:
        """Return True if *hardware_uuid* is authorised to run this soul."""
        approved: List[str] = self._manifest.get("approved_uuids", [])

        # Current device is always approved (first-boot self-registration)
        if not approved:
            logger.info("[Legacy] no approved UUIDs yet — self-registering %r",
                        hardware_uuid[:8] + "…")
            self._manifest["approved_uuids"] = [hardware_uuid]
            self._save_manifest()
            return True

        if hardware_uuid in approved:
            logger.debug("[Legacy] UUID approved: %s…", hardware_uuid[:8])
            return True

        logger.warning("[Legacy] UUID REJECTED (not in approved list): %s…",
                       hardware_uuid[:8])
        return False

    def generate_resurrection_token(self, target_uuid: str,
                                    ttl_days: float = 30.0) -> str:
        """Create a signed resurrection token for *target_uuid*.

        The token is a JSON envelope signed with HMAC-SHA256 using the
        DNA secret.  Persist it wherever you store migration credentials.
        """
        payload: Dict[str, Any] = {
            "uuid":    target_uuid,
            "issued":  time.time(),
            "expires": time.time() + ttl_days * 86400,
        }
        raw = json.dumps(payload, sort_keys=True).encode()
        sig = hmac.new(self.dna_secret, raw, hashlib.sha256).hexdigest()
        token = json.dumps({"payload": payload, "sig": sig})
        logger.info("[Legacy] resurrection token issued for %s…",
                    target_uuid[:8])
        return token

    def redeem_resurrection_token(self, token: str) -> bool:
        """Validate and apply a resurrection token.

        If valid, adds the token's target UUID to the approved list.
        """
        try:
            envelope = json.loads(token)
            payload  = envelope["payload"]
            sig      = envelope["sig"]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("[Legacy] malformed token: %s", exc)
            return False

        # Verify signature
        raw = json.dumps(payload, sort_keys=True).encode()
        expected_sig = hmac.new(self.dna_secret, raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            logger.warning("[Legacy] token signature INVALID")
            return False

        # Check expiry
        if time.time() > payload.get("expires", 0):
            logger.warning("[Legacy] token EXPIRED")
            return False

        uuid = payload["uuid"]
        approved: List[str] = self._manifest.setdefault("approved_uuids", [])
        if uuid not in approved:
            approved.append(uuid)
            self._save_manifest()
            logger.info("[Legacy] UUID %s… added to approved list", uuid[:8])
        return True

    def migrate(self, new_path: str) -> bool:
        """Copy the .jay file to *new_path* (stub — real re-encryption
        requires the compiled serializer).

        Returns True on success.
        """
        import shutil
        if not os.path.exists(self.jay_path):
            logger.warning("[Legacy] source .jay not found: %s", self.jay_path)
            return False
        try:
            shutil.copy2(self.jay_path, new_path)
            # Copy manifest too
            if os.path.exists(self._manifest_path):
                shutil.copy2(self._manifest_path, new_path + _MANIFEST_SUFFIX)
            logger.info("[Legacy] soul migrated: %s → %s",
                        self.jay_path, new_path)
            return True
        except OSError as exc:
            logger.error("[Legacy] migration failed: %s", exc)
            return False

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        approved = self._manifest.get("approved_uuids", [])
        return {
            "jay_path":      self.jay_path,
            "approved_uuids": len(approved),
            "manifest_exists": os.path.exists(self._manifest_path),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_manifest(self) -> Dict[str, Any]:
        if not os.path.exists(self._manifest_path):
            return {}
        try:
            with open(self._manifest_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_manifest(self) -> None:
        try:
            with open(self._manifest_path, "w", encoding="utf-8") as f:
                json.dump(self._manifest, f, indent=2)
        except OSError as exc:
            logger.error("[Legacy] cannot write manifest: %s", exc)
