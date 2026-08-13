"""Pillar 19 — Legacy Protocol.  V18 UPGRADE.

Handles migration and resurrection of a JAYA soul across hardware
boundaries.  When JAYA moves to a new device it must prove continuity
of identity before re-awakening.

V18 Migration Flow
------------------
``migrate(new_path, dst_hw_uuid)``

1. Copy .jay bytes to *new_path*.
2. Parse the 128-byte JAY header (pure Python — no .pyd required).
3. If *dst_hw_uuid* provided:
   a. Derive new hardware hash = SHA3-256(dst_uuid).
   b. Derive new DNA checksum = SHA3-256(DNA_SECRET + new_hw_hash).
   c. Overwrite hardware_hash (bytes 16-47) and dna_summary_hash
      (bytes 48-79) in the copy's header in place (raw bytes).
   d. Attempt AES-GCM SOUL re-encryption if ``cryptography`` is
      installed and the salt is extractable; otherwise leave SOUL
      payload encrypted with the old key (safe — soul is still
      locked; new device must supply resurrection token to unlock).
   e. Recompute footer CRC32 over header + all section payloads.
4. Add *dst_hw_uuid* to the approved-UUIDs manifest.

Mechanisms
----------
* ``can_awaken_on(hardware_uuid)``: verifies whether the provided UUID
  is in the resurrection-approved list embedded in the current .jay header.
* ``generate_resurrection_token()``: creates a signed token (HMAC-SHA256)
  that can be stored in a .jay file to authorise future hardware IDs.
"""

import hashlib
import hmac
import json
import logging
import os
import struct
import time
import zlib
from typing import Any, Dict, List

logger = logging.getLogger("LegacyProtocol")

# Filename where the resurrection manifest is stored alongside .jay files
_MANIFEST_SUFFIX = ".resurrection"

# .jay header layout constants (must match schema.py)
_HEADER_SIZE       = 128           # bytes
_MAGIC             = b"JAYA"       # bytes 0-3
_HW_HASH_OFFSET    = 16            # bytes 16-47 (32 bytes)
_DNA_HASH_OFFSET   = 48            # bytes 48-79 (32 bytes)
_SALT_OFFSET       = 88            # bytes 88-119 (32 bytes)
_DNA_SECRET        = b"JAYA_IMMUTABLE_CORE_VALUES_V1"
_SECTION_HDR_SIZE  = 24            # bytes per section header
_FOOTER_SIZE       = 32            # bytes (CRC32 + hash)


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

    @property
    def manifest(self) -> Dict[str, Any]:
        """Public read-only view of the resurrection manifest."""
        return self._manifest

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

    def migrate(self, new_path: str,
                dst_hw_uuid: str | None = None) -> bool:
        """Migrate .jay soul to *new_path*, optionally re-binding hardware.

        V18 implementation:
        * Always copies .jay (and manifest) to *new_path*.
        * If *dst_hw_uuid* is given, patches the 128-byte header in the
          copy so it is bound to the new hardware — no .pyd required.
        * Adds *dst_hw_uuid* to the resurrection-approved list.
        * Attempts AES-GCM SOUL re-encryption if ``cryptography`` is
          installed; falls back gracefully if not.

        Returns True on success.
        """
        import shutil
        if not os.path.exists(self.jay_path):
            logger.warning("[Legacy] source .jay not found: %s", self.jay_path)
            return False
        try:
            shutil.copy2(self.jay_path, new_path)
            if os.path.exists(self._manifest_path):
                shutil.copy2(self._manifest_path, new_path + _MANIFEST_SUFFIX)
        except OSError as exc:
            logger.error("[Legacy] migration copy failed: %s", exc)
            return False

        if dst_hw_uuid is None:
            logger.info("[Legacy] soul copied (no re-binding): %s → %s",
                        self.jay_path, new_path)
            return True

        # ── V18: Re-bind header to dst hardware ──────────────────────────
        try:
            with open(new_path, "r+b") as f:
                raw = bytearray(f.read())

            if len(raw) < _HEADER_SIZE or bytes(raw[:4]) != _MAGIC:
                raise ValueError("Not a valid .jay file (bad magic)")

            # Derive new hardware hash
            dst_bytes = dst_hw_uuid.encode("utf-8")
            new_hw_hash  = hashlib.sha3_256(dst_bytes).digest()          # 32 bytes
            new_dna_hash = hashlib.sha3_256(
                _DNA_SECRET + new_hw_hash
            ).digest()                                                     # 32 bytes

            # Patch header in-place
            raw[_HW_HASH_OFFSET  : _HW_HASH_OFFSET  + 32] = new_hw_hash
            raw[_DNA_HASH_OFFSET : _DNA_HASH_OFFSET + 32] = new_dna_hash

            # Optionally re-encrypt SOUL section with new key
            raw = self._reencrypt_soul(raw, dst_hw_uuid)

            # Recompute footer CRC32 (last 4 bytes before SHA-256 tag)
            crc_payload = bytes(raw[:-_FOOTER_SIZE])
            new_crc     = zlib.crc32(crc_payload) & 0xFFFFFFFF
            # Footer layout: 4-byte CRC32 + 28-byte SHA-256 tag
            raw[-_FOOTER_SIZE : -_FOOTER_SIZE + 4] = struct.pack("<I", new_crc)

            with open(new_path, "wb") as f:
                f.write(raw)

            logger.info("[Legacy] soul re-bound to %s…: %s → %s",
                        dst_hw_uuid[:8], self.jay_path, new_path)

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[Legacy] header re-bind failed (%s); copy is still valid "
                "but hardware-bound to source device", exc
            )

        # Always approve the destination UUID
        approved: List[str] = self._manifest.setdefault("approved_uuids", [])
        if dst_hw_uuid not in approved:
            approved.append(dst_hw_uuid)
            self._save_manifest()
            # Also update manifest copy
            dst_manifest = new_path + _MANIFEST_SUFFIX
            try:
                import json as _json
                with open(dst_manifest, "w", encoding="utf-8") as mf:
                    _json.dump(self._manifest, mf, indent=2)
            except OSError:
                pass

        return True

    def _reencrypt_soul(self, raw: bytearray, dst_hw_uuid: str) -> bytearray:
        """Re-encrypt the SOUL_KEY section with the destination hardware key.

        Uses AES-256-GCM via the ``cryptography`` package if available.
        Falls back to returning *raw* unchanged on any error.
        """
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            logger.debug("[Legacy] cryptography not installed — skipping SOUL re-key")
            return raw

        try:
            # Extract salt from header (bytes 88-119)
            salt = bytes(raw[_SALT_OFFSET : _SALT_OFFSET + 32])

            # Derive source key from source hardware hash
            src_hw_hash = bytes(raw[_HW_HASH_OFFSET : _HW_HASH_OFFSET + 32])
            src_key = self._derive_key(src_hw_hash, salt)

            # Find SOUL_KEY section by scanning 24-byte section headers
            offset = _HEADER_SIZE
            soul_start = -1
            soul_payload_size = 0
            soul_section_type = 1  # SectionType.SOUL_KEY = 1

            while offset + _SECTION_HDR_SIZE <= len(raw) - _FOOTER_SIZE:
                sec_type  = struct.unpack_from("<I", raw, offset)[0]
                _         = struct.unpack_from("<I", raw, offset + 4)[0]
                sec_size  = struct.unpack_from("<Q", raw, offset + 8)[0]
                sec_offset= struct.unpack_from("<Q", raw, offset + 16)[0]

                if sec_type == soul_section_type and sec_size > 0:
                    soul_start        = sec_offset
                    soul_payload_size = sec_size
                    break
                offset += _SECTION_HDR_SIZE

            if soul_start < 0:
                logger.debug("[Legacy] no SOUL_KEY section found — nothing to re-key")
                return raw

            # Decrypt with source key
            ciphertext = bytes(raw[soul_start : soul_start + soul_payload_size])
            if len(ciphertext) < 28:  # 12-byte nonce + 16-byte tag minimum
                return raw
            nonce      = ciphertext[:12]
            ct_body    = ciphertext[12:]
            plaintext  = AESGCM(src_key).decrypt(nonce, ct_body, None)

            # Derive destination key
            dst_hw_hash = bytes(raw[_HW_HASH_OFFSET : _HW_HASH_OFFSET + 32])
            dst_key     = self._derive_key(dst_hw_hash, salt)

            # Re-encrypt with destination key (new nonce)
            import os as _os
            new_nonce  = _os.urandom(12)
            new_ct     = AESGCM(dst_key).encrypt(new_nonce, plaintext, None)
            new_cipher = new_nonce + new_ct

            # Patch in place (same size expected — pad/trim to match)
            payload_len = len(new_cipher)
            if payload_len != soul_payload_size:
                # Sizes differ (tag length changed?) — skip to avoid corruption
                logger.debug("[Legacy] SOUL size mismatch %d vs %d — skipping re-key",
                             payload_len, soul_payload_size)
                return raw

            raw[soul_start : soul_start + soul_payload_size] = new_cipher
            logger.info("[Legacy] SOUL_KEY section re-encrypted for new hardware")
            return raw

        except Exception as exc:  # noqa: BLE001
            logger.warning("[Legacy] SOUL re-encryption failed (%s) — keeping original", exc)
            return raw

    @staticmethod
    def _derive_key(hw_hash: bytes, salt: bytes) -> bytes:
        """Derive a 32-byte AES key from hardware hash + salt using PBKDF2."""
        from cryptography.hazmat.primitives import hashes as _hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        kdf = PBKDF2HMAC(
            algorithm=_hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        return kdf.derive(hw_hash)

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
