"""Pillar 30 - Twin Protocol.

Deterministic peer-sync protocol for twin-to-twin coordination.
Features:
- signed handshake and sync packets (HMAC-SHA256),
- nonce replay protection,
- monotonic sequence guard per peer,
- bounded in-memory state.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple, cast


def _canonical_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")


def _clamp_non_negative(value: int, default: int = 0) -> int:
    if value < 0:
        return default
    return value


class TwinProtocol:
    """Signed twin handshake/sync protocol with replay and stale guards."""

    def __init__(
        self,
        node_id: str,
        shared_secret: str,
        max_clock_skew_s: float = 45.0,
        max_nonce_history: int = 512,
    ) -> None:
        clean_node = str(node_id or "node").strip()
        if not clean_node:
            clean_node = "node"
        self.node_id = clean_node

        secret = str(shared_secret or "").strip()
        if not secret:
            raise ValueError("shared_secret must not be empty")

        self._secret_key = hashlib.sha256(secret.encode("utf-8")).digest()
        self.max_clock_skew_s = max(5.0, float(max_clock_skew_s))
        self.max_nonce_history = max(64, int(max_nonce_history))

        self._seen_nonce_order: List[str] = []
        self._seen_nonce_set: set[str] = set()
        self._last_seq_by_peer: Dict[str, int] = {}
        self._tx_seq: int = 0

        self._handshake_accepts = 0
        self._handshake_rejects = 0
        self._sync_accepts = 0
        self._sync_rejects = 0

    @staticmethod
    def derive_secret(password: str, model_ref: str) -> str:
        material = f"{password}|{model_ref}|JAYA_TWIN_PROTOCOL_V1"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def create_handshake(
        self,
        peer_id: str,
        capabilities: Optional[Dict[str, Any]] = None,
        ts: Optional[float] = None,
        nonce: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "type": "TWIN_HANDSHAKE",
            "version": "1.0",
            "node_id": self.node_id,
            "peer_id": str(peer_id or "peer"),
            "ts": round(float(time.time() if ts is None else ts), 3),
            "nonce": str(nonce or secrets.token_hex(12)),
            "capabilities": dict(capabilities or {}),
        }
        payload["sig"] = self._sign_payload(payload)
        return payload

    def verify_handshake(
        self,
        payload: Dict[str, Any],
        expected_peer_id: Optional[str] = None,
        expected_sender: Optional[str] = None,
    ) -> Tuple[bool, str]:
        ok, reason = self._verify_common(
            payload=payload,
            expected_type="TWIN_HANDSHAKE",
            expected_peer_id=expected_peer_id,
            expected_sender=expected_sender,
        )
        if not ok:
            self._handshake_rejects += 1
            return False, reason

        nonce = str(payload.get("nonce") or "")
        if self._is_nonce_seen(nonce):
            self._handshake_rejects += 1
            return False, "replay_nonce"

        self._remember_nonce(nonce)
        self._handshake_accepts += 1
        return True, "ok"

    def create_sync_packet(
        self,
        peer_id: str,
        state: Dict[str, Any],
        ts: Optional[float] = None,
        nonce: Optional[str] = None,
        sequence: Optional[int] = None,
    ) -> Dict[str, Any]:
        if sequence is None:
            self._tx_seq += 1
            seq = self._tx_seq
        else:
            seq = _clamp_non_negative(int(sequence), default=0)
            self._tx_seq = max(self._tx_seq, seq)

        payload: Dict[str, Any] = {
            "type": "TWIN_SYNC",
            "version": "1.0",
            "node_id": self.node_id,
            "peer_id": str(peer_id or "peer"),
            "ts": round(float(time.time() if ts is None else ts), 3),
            "nonce": str(nonce or secrets.token_hex(10)),
            "seq": seq,
            "state": dict(state),
        }
        payload["sig"] = self._sign_payload(payload)
        return payload

    def verify_sync_packet(
        self,
        payload: Dict[str, Any],
        expected_peer_id: Optional[str] = None,
        expected_sender: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        ok, reason = self._verify_common(
            payload=payload,
            expected_type="TWIN_SYNC",
            expected_peer_id=expected_peer_id,
            expected_sender=expected_sender,
        )
        if not ok:
            self._sync_rejects += 1
            return False, reason, {}

        seq_raw = payload.get("seq")
        if not isinstance(seq_raw, (int, float, str)):
            self._sync_rejects += 1
            return False, "invalid_seq", {}
        try:
            seq = int(seq_raw)
        except (TypeError, ValueError):
            self._sync_rejects += 1
            return False, "invalid_seq", {}

        sender = str(payload.get("node_id") or "")
        last_seq = self._last_seq_by_peer.get(sender, 0)
        if seq <= last_seq:
            self._sync_rejects += 1
            return False, "stale_seq", {}

        nonce = str(payload.get("nonce") or "")
        if self._is_nonce_seen(nonce):
            self._sync_rejects += 1
            return False, "replay_nonce", {}

        state_raw = payload.get("state")
        if not isinstance(state_raw, dict):
            self._sync_rejects += 1
            return False, "invalid_state", {}

        state_map = cast(Dict[Any, Any], state_raw)
        clean_state: Dict[str, Any] = {}
        for key, value in state_map.items():
            clean_state[str(key)] = value

        self._last_seq_by_peer[sender] = seq
        self._remember_nonce(nonce)
        self._sync_accepts += 1
        return True, "ok", clean_state

    def status(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "tx_seq": self._tx_seq,
            "known_peers": len(self._last_seq_by_peer),
            "handshake_accepts": self._handshake_accepts,
            "handshake_rejects": self._handshake_rejects,
            "sync_accepts": self._sync_accepts,
            "sync_rejects": self._sync_rejects,
            "nonce_cache": len(self._seen_nonce_order),
        }

    def _verify_common(
        self,
        payload: Any,
        expected_type: str,
        expected_peer_id: Optional[str],
        expected_sender: Optional[str],
    ) -> Tuple[bool, str]:
        if not isinstance(payload, dict):
            return False, "invalid_payload"

        data = cast(Dict[str, Any], payload)

        if str(data.get("type") or "") != expected_type:
            return False, "invalid_type"

        sig = data.get("sig")
        if not isinstance(sig, str) or not sig:
            return False, "missing_sig"

        if not self._verify_signature(data):
            return False, "bad_signature"

        ts_raw = data.get("ts")
        if not isinstance(ts_raw, (int, float, str)):
            return False, "invalid_ts"
        try:
            ts = float(ts_raw)
        except (TypeError, ValueError):
            return False, "invalid_ts"

        if abs(time.time() - ts) > self.max_clock_skew_s:
            return False, "clock_skew"

        if expected_peer_id is not None:
            peer_id = str(data.get("peer_id") or "")
            if peer_id != str(expected_peer_id):
                return False, "unexpected_peer"

        if expected_sender is not None:
            sender = str(data.get("node_id") or "")
            if sender != str(expected_sender):
                return False, "unexpected_sender"

        nonce = str(data.get("nonce") or "")
        if len(nonce) < 8:
            return False, "invalid_nonce"

        return True, "ok"

    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        body = self._unsigned_payload(payload)
        mac = hmac.new(self._secret_key, _canonical_json(body), hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(mac).decode("ascii")
        return token.rstrip("=")

    def _verify_signature(self, payload: Dict[str, Any]) -> bool:
        sig_raw = payload.get("sig")
        if not isinstance(sig_raw, str):
            return False
        expected = self._sign_payload(payload)
        return hmac.compare_digest(expected, sig_raw)

    def _unsigned_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = dict(payload)
        body.pop("sig", None)
        return body

    def _is_nonce_seen(self, nonce: str) -> bool:
        return nonce in self._seen_nonce_set

    def _remember_nonce(self, nonce: str) -> None:
        if nonce in self._seen_nonce_set:
            return
        self._seen_nonce_set.add(nonce)
        self._seen_nonce_order.append(nonce)
        if len(self._seen_nonce_order) > self.max_nonce_history:
            dropped = self._seen_nonce_order.pop(0)
            self._seen_nonce_set.discard(dropped)
