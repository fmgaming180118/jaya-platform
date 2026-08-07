"""
approval_authority.py — Manages capability approval receipts, signing keys, and nonce ledger.
"""

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Core OS boundary definitions
JAYA_HOME = Path.home() / ".jaya"
JAYA_HOME.mkdir(parents=True, exist_ok=True)

KEY_FILE = JAYA_HOME / "approval_key"
LEDGER_DB = JAYA_HOME / "approval_ledger.db"


def _get_or_create_signing_key() -> str:
    """Retrieve the persistent signing key, or create one if it doesn't exist."""
    env_key = os.environ.get("JAYA_APPROVAL_SIGNING_KEY")
    if env_key:
        return env_key
        
    if KEY_FILE.exists():
        try:
            return KEY_FILE.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("Failed to read persistent signing key: %s", e)
            
    # Generate new persistent key
    new_key = secrets.token_hex(32)
    try:
        # Secure file creation: rw-------
        # Python 3.8+ open opener support for strict permissions
        def opener(path, flags):
            return os.open(path, flags, 0o600)
            
        with open(KEY_FILE, "w", opener=opener, encoding="utf-8") as f:
            f.write(new_key)
    except Exception as e:
        logger.warning("Failed to persist signing key: %s. Using ephemeral key.", e)
        
    return new_key

_PERSISTENT_SIGNING_KEY = _get_or_create_signing_key()


class NonceLedger:
    """Durable SQLite-based ledger for replay protection (nonce consumption)."""
    
    def __init__(self, db_path: Path = LEDGER_DB):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS consumed_nonces (
                        nonce TEXT PRIMARY KEY,
                        consumed_at REAL NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to initialize NonceLedger DB: %s", e)
            
    def is_consumed(self, nonce: str) -> bool:
        """Check if a nonce has already been consumed."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT 1 FROM consumed_nonces WHERE nonce = ?", (nonce,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error("Failed to query nonce: %s", e)
            # Fail-safe: if DB is broken, assume consumed to prevent replay
            return True
            
    def consume(self, nonce: str) -> bool:
        """Consume a nonce. Returns True if successful, False if already consumed."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                try:
                    conn.execute(
                        "INSERT INTO consumed_nonces (nonce, consumed_at) VALUES (?, ?)",
                        (nonce, time.time())
                    )
                    conn.commit()
                    return True
                except sqlite3.IntegrityError:
                    return False
        except Exception as e:
            logger.error("Failed to consume nonce: %s", e)
            return False


@dataclass
class ApprovalReceipt:
    """
    Signed human approval receipt for sensitive operations.
    
    Binds: user_id, session_id, action, resource, request_digest, 
           issued_at, expires_at, nonce, signature
    """
    receipt_id: str
    user_id: str
    session_id: str
    action: str
    resource: str
    request_digest: str
    issued_at: float
    expires_at: float
    nonce: str
    signature: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ApprovalAuthority:
    """Authority for issuing and verifying capability approval receipts."""
    
    def __init__(self, ledger: Optional[NonceLedger] = None):
        self.ledger = ledger or NonceLedger()
        self.signing_key = _PERSISTENT_SIGNING_KEY
        
    def issue_receipt(
        self,
        user_id: str,
        session_id: str,
        action: str,
        resource: str,
        request_digest: str,
        ttl_seconds: float = 300.0,
    ) -> ApprovalReceipt:
        """Create a new signed approval receipt."""
        receipt_id = f"approval-{int(time.time() * 1000)}-{secrets.token_hex(4)}"
        issued_at = time.time()
        expires_at = issued_at + ttl_seconds
        nonce = secrets.token_hex(16)
        
        message = f"{receipt_id}|{user_id}|{session_id}|{action}|{resource}|{request_digest}|{issued_at}|{expires_at}|{nonce}"
        signature = hmac.new(
            self.signing_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        
        return ApprovalReceipt(
            receipt_id=receipt_id,
            user_id=user_id,
            session_id=session_id,
            action=action,
            resource=resource,
            request_digest=request_digest,
            issued_at=issued_at,
            expires_at=expires_at,
            nonce=nonce,
            signature=signature,
        )
        
    def verify_and_consume(
        self, 
        receipt: ApprovalReceipt, 
        current_session_id: str,
        expected_user_id: str,
        expected_action: str,
        expected_resource: str,
        expected_request_digest: str
    ) -> tuple[bool, str]:
        """
        Strictly verify the receipt signature, expiry, identity, operation bindings, and nonce.
        Returns (is_valid, reason).
        """
        # 1. Verify signature first (prevents expensive operations on forged receipts)
        message = f"{receipt.receipt_id}|{receipt.user_id}|{receipt.session_id}|{receipt.action}|{receipt.resource}|{receipt.request_digest}|{receipt.issued_at}|{receipt.expires_at}|{receipt.nonce}"
        expected_signature = hmac.new(
            self.signing_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        
        if not hmac.compare_digest(receipt.signature, expected_signature):
            return False, "INVALID_APPROVAL_RECEIPT: Signature verification failed"

        # 2. Verify expiry
        if time.time() > receipt.expires_at:
            return False, "INVALID_APPROVAL_RECEIPT: Receipt has expired"
            
        # 3. Verify user
        if receipt.user_id != expected_user_id:
            return False, f"INVALID_APPROVAL_RECEIPT: User ID mismatch (expected {expected_user_id}, got {receipt.user_id})"
            
        # 4. Verify session
        if not current_session_id:
            return False, "INVALID_APPROVAL_RECEIPT: SESSION_REQUIRED"
            
        if receipt.session_id != current_session_id:
            return False, f"INVALID_APPROVAL_RECEIPT: Session ID mismatch (expected {current_session_id}, got {receipt.session_id})"
            
        # 5. Verify action
        if receipt.action != expected_action:
            return False, f"INVALID_APPROVAL_RECEIPT: Action mismatch (expected {expected_action}, got {receipt.action})"

        # 6. Verify canonical resource
        if receipt.resource != expected_resource:
            return False, f"INVALID_APPROVAL_RECEIPT: Resource mismatch (expected {expected_resource}, got {receipt.resource})"

        # 7. Verify request digest
        if receipt.request_digest != expected_request_digest:
            return False, "INVALID_APPROVAL_RECEIPT: Request digest mismatch"
            
        # 8. Verify not revoked (skipped / to be implemented if revocation list added)
            
        # 9. Verify nonce unused -> atomically consume nonce
        if not self.ledger.consume(receipt.nonce):
            return False, "INVALID_APPROVAL_RECEIPT: Nonce already consumed (replay detected)"
            
        return True, "OK"
