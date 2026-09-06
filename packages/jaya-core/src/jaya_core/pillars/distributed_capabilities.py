"""Encrypted resumable twin transport and signed collective evidence capabilities."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import socket
import socketserver
import sqlite3
import struct
import threading
import time
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .agentic_rag_capability import AgenticRAGCapability
from .local_capabilities import LocalPillarError, LocalPillarResult

TWIN_TRANSFER_CAPABILITY_ID = "core.twin.sync"
COLLECTIVE_EVIDENCE_CAPABILITY_ID = "core.collective.pulse"
_MAX_WIRE_BYTES = 16 * 1024 * 1024
_MAX_BATCH_CHUNKS = 32


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
    candidate = value.strip()
    if not 1 <= len(candidate) <= maximum:
        raise LocalPillarError("INVALID_INPUT", f"{field} must contain 1-{maximum} characters")
    return candidate


def _require_fields(
    request: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    supplied = set(request)
    allowed = required | (optional or set())
    missing = required - supplied
    unknown = supplied - allowed
    if missing:
        raise LocalPillarError("MISSING_FIELD", f"missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise LocalPillarError("UNKNOWN_FIELD", f"unknown fields: {', '.join(sorted(unknown))}")


def _recv_json(stream: socket.socket) -> Mapping[str, Any]:
    header = b""
    while len(header) < 4:
        block = stream.recv(4 - len(header))
        if not block:
            raise LocalPillarError("TRANSPORT_CLOSED", "peer closed before frame header")
        header += block
    length = struct.unpack("!I", header)[0]
    if not 1 <= length <= _MAX_WIRE_BYTES:
        raise LocalPillarError("RESOURCE_LIMIT", "transport frame size is invalid")
    payload = bytearray()
    while len(payload) < length:
        block = stream.recv(min(65536, length - len(payload)))
        if not block:
            raise LocalPillarError("TRANSPORT_CLOSED", "peer closed before frame body")
        payload.extend(block)
    try:
        value = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise LocalPillarError("INVALID_TRANSPORT_FRAME", "transport frame is invalid") from exc
    if not isinstance(value, Mapping):
        raise LocalPillarError("INVALID_TRANSPORT_FRAME", "transport frame must be an object")
    return value


def _send_json(stream: socket.socket, value: Mapping[str, Any]) -> None:
    payload = _canonical(value)
    if len(payload) > _MAX_WIRE_BYTES:
        raise LocalPillarError("RESOURCE_LIMIT", "transport response exceeds frame limit")
    stream.sendall(struct.pack("!I", len(payload)) + payload)


class _TwinTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _TwinHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        owner: TwinMigrationCapability = self.server.owner  # type: ignore[attr-defined]
        try:
            request = _recv_json(self.request)
            response = owner._receive(request)
        except LocalPillarError as exc:
            response = {"ok": False, "code": exc.code}
        except (OSError, sqlite3.Error, ValueError, TypeError):
            response = {"ok": False, "code": "TRANSPORT_FAILED"}
        try:
            _send_json(self.request, response)
        except (OSError, LocalPillarError):
            return


class TwinMigrationCapability:
    """Transfer encrypted state batches between allowlisted local nodes over TCP."""

    CHUNK_SIZE = 256 * 1024

    def __init__(
        self,
        *,
        node_id: str,
        root: Path,
        database_path: Path,
        shared_secret: str | None,
        allowed_peers: tuple[str, ...],
        timeout_seconds: float = 10.0,
    ) -> None:
        self.node_id = _text(node_id, "node_id", 128)
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "received").mkdir(exist_ok=True)
        (self.root / "inbound-temp").mkdir(exist_ok=True)
        self.database_path = database_path.resolve()
        self.allowed_peers = frozenset(_text(item, "peer_id", 128) for item in allowed_peers)
        self.timeout_seconds = timeout_seconds
        self._key = (
            hashlib.sha256((shared_secret + "|twin-transfer-v2").encode()).digest()
            if shared_secret and len(shared_secret) >= 32
            else None
        )
        self._server: _TwinTCPServer | None = None
        self._thread: threading.Thread | None = None
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS twin_outbound(
                        transfer_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL,
                        source_path TEXT NOT NULL, cursor INTEGER NOT NULL,
                        status TEXT NOT NULL, receipt_json TEXT, updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS twin_inbound(
                        transfer_id TEXT PRIMARY KEY, metadata_digest TEXT NOT NULL,
                        metadata_json TEXT NOT NULL, cursor INTEGER NOT NULL,
                        temp_path TEXT NOT NULL, status TEXT NOT NULL,
                        receipt_json TEXT, updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS twin_nonces(
                        nonce TEXT PRIMARY KEY, seen_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS brain_authority(
                        brain_id TEXT PRIMARY KEY, holder_node TEXT NOT NULL,
                        lease_expires_at REAL NOT NULL, transfer_id TEXT NOT NULL
                    );
                    """
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "twin ledger unavailable") from exc

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def health_check(self) -> bool:
        return bool(self._key and self.allowed_peers and 0.1 <= self.timeout_seconds <= 120)

    def _sign(self, value: bytes) -> str:
        if self._key is None:
            raise LocalPillarError("KEY_NOT_CONFIGURED", "twin transport key is unavailable")
        return hmac.new(self._key, value, hashlib.sha256).hexdigest()

    def _verify(self, value: bytes, signature: object) -> None:
        if not isinstance(signature, str) or not hmac.compare_digest(signature, self._sign(value)):
            raise LocalPillarError("TWIN_AUTHENTICATION_FAILED", "twin signature is invalid")

    def _signed_response(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {**payload, "response_signature": self._sign(_canonical(payload))}

    def _confined(self, value: object, *, must_exist: bool) -> Path:
        raw = Path(_text(value, "path", 1_024))
        candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise LocalPillarError("PERMISSION_DENIED", "twin path escapes node root") from exc
        if must_exist and not candidate.is_file():
            raise LocalPillarError("FILE_NOT_FOUND", "twin source was not found")
        return candidate

    def start_receiver(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _require_fields(
            request,
            required={"action"},
            optional={"bind_host", "port"},
        )
        host = str(request.get("bind_host", "127.0.0.1"))
        port = request.get("port", 0)
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise LocalPillarError("PERMISSION_DENIED", "implemented-local twin binds loopback only")
        if type(port) is not int or not 0 <= port <= 65535:
            raise LocalPillarError("INVALID_INPUT", "receiver port is invalid")
        if not self.health_check():
            raise LocalPillarError("CAPABILITY_UNAVAILABLE", "twin transport is not configured")
        if self._server is not None:
            raise LocalPillarError("RECEIVER_RUNNING", "twin receiver is already running")
        try:
            server = _TwinTCPServer((host, port), _TwinHandler)
        except OSError as exc:
            raise LocalPillarError("TRANSPORT_UNAVAILABLE", "twin receiver could not bind") from exc
        server.owner = self  # type: ignore[attr-defined]
        thread = threading.Thread(
            target=server.serve_forever,
            name=f"jaya-twin-{self.node_id}",
            daemon=True,
        )
        thread.start()
        self._server = server
        self._thread = thread
        return LocalPillarResult(
            "P030",
            "TWIN_RECEIVER_STARTED",
            {"host": host, "port": server.server_address[1], "node_id": self.node_id},
        )

    def stop_receiver(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)

    def _validated_envelope(self, request: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
        _require_fields(
            request,
            required={"action", "metadata", "request_ts", "nonce", "chunks", "signature"},
        )
        action = request.get("action")
        if action not in {"status", "batch"}:
            raise LocalPillarError("INVALID_TRANSPORT_FRAME", "twin transport action is unsupported")
        metadata = request.get("metadata")
        if not isinstance(metadata, Mapping):
            raise LocalPillarError("INVALID_TRANSPORT_FRAME", "twin metadata is missing")
        required = {
            "transfer_id",
            "sender_id",
            "target_id",
            "brain_id",
            "source_digest",
            "total_size",
            "chunk_size",
            "total_chunks",
            "destination_name",
            "created_at",
        }
        if set(metadata) != required:
            raise LocalPillarError("INVALID_TRANSPORT_FRAME", "twin metadata schema is invalid")
        sender = _text(metadata["sender_id"], "sender_id", 128)
        if sender not in self.allowed_peers or metadata["target_id"] != self.node_id:
            raise LocalPillarError("PEER_DENIED", "twin sender or target is not allowlisted")
        destination_name = _text(metadata["destination_name"], "destination_name", 255)
        if Path(destination_name).name != destination_name:
            raise LocalPillarError("INVALID_INPUT", "destination_name must be a file name")
        total_size = metadata["total_size"]
        chunk_size = metadata["chunk_size"]
        total_chunks = metadata["total_chunks"]
        if type(total_size) is not int or not 1 <= total_size <= 64 * 1024 * 1024:
            raise LocalPillarError("RESOURCE_LIMIT", "twin transfer size is invalid")
        if chunk_size != self.CHUNK_SIZE or type(total_chunks) is not int or not 1 <= total_chunks <= 4096:
            raise LocalPillarError("INVALID_TRANSPORT_FRAME", "twin chunk metadata is invalid")
        if total_chunks != math.ceil(total_size / self.CHUNK_SIZE):
            raise LocalPillarError("INVALID_TRANSPORT_FRAME", "twin chunk count does not match size")
        timestamp = request.get("request_ts")
        nonce = _text(request.get("nonce"), "nonce", 128)
        if timestamp is None:
            raise LocalPillarError("INVALID_TRANSPORT_FRAME", "request timestamp is required")
        try:
            timestamp_value = float(timestamp)
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_TRANSPORT_FRAME", "request timestamp is invalid") from exc
        if not math.isfinite(timestamp_value) or abs(time.time() - timestamp_value) > 300:
            raise LocalPillarError("CLOCK_SKEW", "twin request timestamp is stale")
        material = _canonical(
            {
                "action": action,
                "metadata_digest": _digest(_canonical(metadata)),
                "request_ts": timestamp,
                "nonce": nonce,
                "chunks_digest": _digest(_canonical(request.get("chunks", []))),
            }
        )
        self._verify(material, request.get("signature"))
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM twin_nonces WHERE seen_at < ?", (time.time() - 86_400,))
                connection.execute("INSERT INTO twin_nonces VALUES(?,?)", (nonce, time.time()))
        except sqlite3.IntegrityError as exc:
            raise LocalPillarError("REPLAY_DETECTED", "twin request nonce was already used") from exc
        return str(action), metadata

    def _receive(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        action, metadata = self._validated_envelope(request)
        transfer_id = _text(metadata["transfer_id"], "transfer_id", 128)
        metadata_digest = _digest(_canonical(metadata))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM twin_inbound WHERE transfer_id=?", (transfer_id,)
            ).fetchone()
            if row is None:
                authority = connection.execute(
                    "SELECT * FROM brain_authority WHERE brain_id=?", (metadata["brain_id"],)
                ).fetchone()
                if (
                    authority is not None
                    and authority["holder_node"] != metadata["sender_id"]
                    and float(authority["lease_expires_at"]) > time.time()
                ):
                    raise LocalPillarError("SPLIT_BRAIN_PREVENTED", "brain authority belongs to another node")
                temp = self.root / "inbound-temp" / f"{transfer_id}.partial"
                temp.unlink(missing_ok=True)
                connection.execute(
                    "INSERT INTO twin_inbound VALUES(?,?,?,?,?,?,NULL,?)",
                    (transfer_id, metadata_digest, _canonical(metadata).decode(), 0, str(temp.relative_to(self.root)), "RECEIVING", time.time()),
                )
                row = connection.execute(
                    "SELECT * FROM twin_inbound WHERE transfer_id=?", (transfer_id,)
                ).fetchone()
            elif row["metadata_digest"] != metadata_digest:
                raise LocalPillarError("TRANSFER_CONFLICT", "transfer_id metadata changed")
            if row["status"] == "COMPLETE":
                return self._signed_response(
                    {
                        "ok": True,
                        "cursor": row["cursor"],
                        "complete": True,
                        "receipt": json.loads(row["receipt_json"]),
                    }
                )
            cursor = int(row["cursor"])
            if action == "status":
                return self._signed_response({"ok": True, "cursor": cursor, "complete": False})
            chunks = request.get("chunks")
            if not isinstance(chunks, list) or not 1 <= len(chunks) <= _MAX_BATCH_CHUNKS:
                raise LocalPillarError(
                    "RESOURCE_LIMIT",
                    f"twin batch must contain 1-{_MAX_BATCH_CHUNKS} chunks",
                )
            temporary = self.root / row["temp_path"]
            expected = cursor
            plaintext_chunks: list[bytes] = []
            try:
                for chunk in chunks:
                    if not isinstance(chunk, Mapping) or set(chunk) != {"index", "nonce", "ciphertext"}:
                        raise LocalPillarError("INVALID_CHUNK", "twin chunk schema is invalid")
                    if chunk.get("index") != expected or expected >= int(metadata["total_chunks"]):
                        raise LocalPillarError("CURSOR_MISMATCH", "twin chunk cursor is not sequential")
                    nonce = base64.b64decode(chunk.get("nonce", ""), validate=True)
                    ciphertext = base64.b64decode(chunk.get("ciphertext", ""), validate=True)
                    if len(nonce) != 12:
                        raise LocalPillarError("INVALID_CHUNK", "twin AES-GCM nonce must be 12 bytes")
                    aad = f"{transfer_id}|{expected}".encode()
                    if self._key is None:
                        raise LocalPillarError("KEY_NOT_CONFIGURED", "twin key is unavailable")
                    plaintext = AESGCM(self._key).decrypt(nonce, ciphertext, aad)
                    remaining = int(metadata["total_size"]) - expected * self.CHUNK_SIZE
                    expected_size = min(self.CHUNK_SIZE, remaining)
                    if len(plaintext) != expected_size:
                        raise LocalPillarError("INVALID_CHUNK", "twin plaintext chunk size is invalid")
                    plaintext_chunks.append(plaintext)
                    expected += 1

                committed_size = cursor * self.CHUNK_SIZE
                if cursor:
                    existing = temporary.read_bytes()
                    if len(existing) < committed_size:
                        raise LocalPillarError("TRANSFER_CORRUPTED", "twin partial state is shorter than its cursor")
                    existing = existing[:committed_size]
                else:
                    existing = b""
                replacement = temporary.with_name(f"{temporary.name}.{uuid.uuid4().hex}.next")
                try:
                    with replacement.open("xb") as output:
                        output.write(existing)
                        for plaintext in plaintext_chunks:
                            output.write(plaintext)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(replacement, temporary)
                finally:
                    replacement.unlink(missing_ok=True)
            except LocalPillarError:
                raise
            except (OSError, ValueError, TypeError, binascii.Error, InvalidTag) as exc:
                raise LocalPillarError("CHUNK_DECRYPTION_FAILED", "twin batch is invalid") from exc
            cursor = expected
            complete = cursor == int(metadata["total_chunks"])
            receipt = None
            if complete:
                raw = temporary.read_bytes()
                if len(raw) != metadata["total_size"] or _digest(raw) != metadata["source_digest"]:
                    raise LocalPillarError("TRANSFER_DIGEST_MISMATCH", "received state differs from source")
                destination = self.root / "received" / str(metadata["destination_name"])
                if destination.exists():
                    raise LocalPillarError("DESTINATION_EXISTS", "twin destination already exists")
                os.replace(temporary, destination)
                receipt_payload = {
                    "transfer_id": transfer_id,
                    "brain_id": metadata["brain_id"],
                    "source_node": metadata["sender_id"],
                    "target_node": self.node_id,
                    "source_digest": metadata["source_digest"],
                    "destination": str(destination.relative_to(self.root)),
                    "completed_at": time.time(),
                }
                receipt = {**receipt_payload, "signature": self._sign(_canonical(receipt_payload))}
                connection.execute(
                    """INSERT INTO brain_authority VALUES(?,?,?,?)
                    ON CONFLICT(brain_id) DO UPDATE SET holder_node=excluded.holder_node,
                    lease_expires_at=excluded.lease_expires_at,transfer_id=excluded.transfer_id""",
                    (metadata["brain_id"], self.node_id, time.time() + 3600, transfer_id),
                )
            connection.execute(
                "UPDATE twin_inbound SET cursor=?,status=?,receipt_json=?,updated_at=? WHERE transfer_id=?",
                (cursor, "COMPLETE" if complete else "RECEIVING", json.dumps(receipt) if receipt else None, time.time(), transfer_id),
            )
        return self._signed_response(
            {"ok": True, "cursor": cursor, "complete": complete, "receipt": receipt}
        )

    def _wire_request(
        self,
        host: str,
        port: int,
        action: str,
        metadata: Mapping[str, Any],
        chunks: list[dict[str, Any]],
    ) -> Mapping[str, Any]:
        timestamp = time.time()
        nonce = uuid.uuid4().hex
        material = _canonical(
            {
                "action": action,
                "metadata_digest": _digest(_canonical(metadata)),
                "request_ts": timestamp,
                "nonce": nonce,
                "chunks_digest": _digest(_canonical(chunks)),
            }
        )
        request = {
            "action": action,
            "metadata": metadata,
            "request_ts": timestamp,
            "nonce": nonce,
            "chunks": chunks,
            "signature": self._sign(material),
        }
        try:
            with socket.create_connection((host, port), timeout=self.timeout_seconds) as stream:
                stream.settimeout(self.timeout_seconds)
                _send_json(stream, request)
                response = _recv_json(stream)
        except (OSError, TimeoutError) as exc:
            raise LocalPillarError("TRANSPORT_UNAVAILABLE", "twin peer is unreachable") from exc
        if not response.get("ok"):
            raise LocalPillarError(str(response.get("code", "TRANSPORT_FAILED")), "twin peer rejected transfer")
        authenticated = dict(response)
        response_signature = authenticated.pop("response_signature", None)
        self._verify(_canonical(authenticated), response_signature)
        return authenticated

    def send_batch(self, request: Mapping[str, Any]) -> LocalPillarResult:
        required = {"action", "host", "port", "transfer_id", "source_path", "target_node_id", "brain_id", "destination_name"}
        _require_fields(request, required=required, optional={"maximum_chunks"})
        host = _text(request["host"], "host", 255)
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise LocalPillarError("PERMISSION_DENIED", "implemented-local twin connects loopback only")
        port = request["port"]
        maximum_chunks = request.get("maximum_chunks", _MAX_BATCH_CHUNKS)
        if type(port) is not int or not 1 <= port <= 65535:
            raise LocalPillarError("INVALID_INPUT", "peer port is invalid")
        if type(maximum_chunks) is not int or not 1 <= maximum_chunks <= _MAX_BATCH_CHUNKS:
            raise LocalPillarError(
                "RESOURCE_LIMIT",
                f"maximum_chunks must be 1-{_MAX_BATCH_CHUNKS}",
            )
        transfer_id = _text(request["transfer_id"], "transfer_id", 128)
        target = _text(request["target_node_id"], "target_node_id", 128)
        if target not in self.allowed_peers:
            raise LocalPillarError("PEER_DENIED", "target node is not allowlisted")
        source = self._confined(request["source_path"], must_exist=True)
        raw = source.read_bytes()
        if not 1 <= len(raw) <= 64 * 1024 * 1024:
            raise LocalPillarError("RESOURCE_LIMIT", "twin source size is invalid")
        total_chunks = math.ceil(len(raw) / self.CHUNK_SIZE)
        requested_metadata = {
            "transfer_id": transfer_id,
            "sender_id": self.node_id,
            "target_id": target,
            "brain_id": _text(request["brain_id"], "brain_id", 128),
            "source_digest": _digest(raw),
            "total_size": len(raw),
            "chunk_size": self.CHUNK_SIZE,
            "total_chunks": total_chunks,
            "destination_name": _text(request["destination_name"], "destination_name", 255),
            "created_at": time.time(),
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM twin_outbound WHERE transfer_id=?", (transfer_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO twin_outbound VALUES(?,?,?,0,'SENDING',NULL,?)",
                    (transfer_id, _canonical(requested_metadata).decode(), str(source.relative_to(self.root)), time.time()),
                )
                metadata = requested_metadata
            else:
                metadata = json.loads(row["metadata_json"])
                comparable = {**requested_metadata, "created_at": metadata["created_at"]}
                if metadata != comparable or row["source_path"] != str(source.relative_to(self.root)):
                    raise LocalPillarError("TRANSFER_CONFLICT", "outbound transfer metadata changed")
        status = self._wire_request(host, port, "status", metadata, [])
        cursor = int(status["cursor"])
        if status.get("complete"):
            complete_response = status
        else:
            end = min(total_chunks, cursor + maximum_chunks)
            chunks = []
            if self._key is None:
                raise LocalPillarError("KEY_NOT_CONFIGURED", "twin key is unavailable")
            for index in range(cursor, end):
                plaintext = raw[index * self.CHUNK_SIZE : (index + 1) * self.CHUNK_SIZE]
                nonce = os.urandom(12)
                ciphertext = AESGCM(self._key).encrypt(
                    nonce, plaintext, f"{transfer_id}|{index}".encode()
                )
                chunks.append(
                    {
                        "index": index,
                        "nonce": base64.b64encode(nonce).decode(),
                        "ciphertext": base64.b64encode(ciphertext).decode(),
                    }
                )
            complete_response = self._wire_request(host, port, "batch", metadata, chunks)
            cursor = int(complete_response["cursor"])
        if complete_response.get("complete"):
            receipt = complete_response.get("receipt")
            if not isinstance(receipt, Mapping):
                raise LocalPillarError("RECEIPT_INVALID", "completed twin transfer has no receipt")
            receipt_payload = dict(receipt)
            receipt_signature = receipt_payload.pop("signature", None)
            expected_receipt_fields = {
                "transfer_id",
                "brain_id",
                "source_node",
                "target_node",
                "source_digest",
                "destination",
                "completed_at",
            }
            if set(receipt_payload) != expected_receipt_fields:
                raise LocalPillarError("RECEIPT_INVALID", "twin receipt schema is invalid")
            self._verify(_canonical(receipt_payload), receipt_signature)
            if (
                receipt_payload["transfer_id"] != transfer_id
                or receipt_payload["brain_id"] != metadata["brain_id"]
                or receipt_payload["source_node"] != self.node_id
                or receipt_payload["target_node"] != target
                or receipt_payload["source_digest"] != metadata["source_digest"]
            ):
                raise LocalPillarError("RECEIPT_INVALID", "twin receipt does not match the transfer")
        with self._connect() as connection:
            connection.execute(
                "UPDATE twin_outbound SET cursor=?,status=?,receipt_json=?,updated_at=? WHERE transfer_id=?",
                (
                    cursor,
                    "COMPLETE" if complete_response.get("complete") else "PARTIAL",
                    json.dumps(complete_response.get("receipt")) if complete_response.get("receipt") else None,
                    time.time(),
                    transfer_id,
                ),
            )
        return LocalPillarResult(
            "P030",
            "TWIN_TRANSFER_COMPLETE" if complete_response.get("complete") else "TWIN_TRANSFER_PARTIAL",
            {
                "transfer_id": transfer_id,
                "cursor": cursor,
                "total_chunks": total_chunks,
                "complete": bool(complete_response.get("complete")),
                "receipt": complete_response.get("receipt"),
                "transport": "TCP_LOOPBACK_AES_256_GCM",
            },
        )

    def probe_transport(self) -> dict[str, Any]:
        return {
            "transport_type": "TCP_LOOPBACK_AES_256_GCM",
            "cipher": "AES-256-GCM",
            "signature_algorithm": "HMAC-SHA256",
            "chunk_size_bytes": self.CHUNK_SIZE,
            "max_batch_chunks": _MAX_BATCH_CHUNKS,
            "max_wire_bytes": _MAX_WIRE_BYTES,
            "node_id": self.node_id,
            "allowed_peers": sorted(self.allowed_peers),
            "receiver_running": self._server is not None,
            "bound_port": self._server.server_address[1] if self._server is not None else None,
        }

    def query_authority(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _require_fields(request, required={"action", "brain_id"})
        brain_id = _text(request["brain_id"], "brain_id", 128)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM brain_authority WHERE brain_id=?", (brain_id,)
            ).fetchone()
        if row is None:
            return LocalPillarResult(
                "P030",
                "BRAIN_AUTHORITY_NOT_FOUND",
                {"brain_id": brain_id, "has_lease": False},
            )
        now = time.time()
        expires_at = float(row["lease_expires_at"])
        is_active = expires_at > now
        return LocalPillarResult(
            "P030",
            "BRAIN_AUTHORITY_QUERIED",
            {
                "brain_id": brain_id,
                "holder_node": row["holder_node"],
                "lease_expires_at": expires_at,
                "transfer_id": row["transfer_id"],
                "is_active": is_active,
                "has_lease": True,
            },
        )

    def verify_receipt(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _require_fields(request, required={"action", "receipt"})
        receipt = request["receipt"]
        if not isinstance(receipt, Mapping):
            raise LocalPillarError("INVALID_INPUT", "receipt must be an object")
        payload = dict(receipt)
        sig = payload.pop("signature", None)
        expected_receipt_fields = {
            "transfer_id",
            "brain_id",
            "source_node",
            "target_node",
            "source_digest",
            "destination",
            "completed_at",
        }
        if set(payload) != expected_receipt_fields:
            raise LocalPillarError("RECEIPT_INVALID", "twin receipt schema is invalid")
        self._verify(_canonical(payload), sig)
        return LocalPillarResult(
            "P030",
            "TWIN_RECEIPT_VERIFIED",
            {"status": "VALID", "transfer_id": payload["transfer_id"], "brain_id": payload["brain_id"]},
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        if action == "start_receiver":
            return self.start_receiver(request)
        if action == "send_batch":
            return self.send_batch(request)
        if action == "stop_receiver":
            _require_fields(request, required={"action"})
            self.stop_receiver()
            return LocalPillarResult("P030", "TWIN_RECEIVER_STOPPED", {"node_id": self.node_id})
        if action == "probe_transport":
            return LocalPillarResult("P030", "TWIN_TRANSPORT_PROBED", self.probe_transport())
        if action == "query_authority":
            return self.query_authority(request)
        if action == "verify_receipt":
            return self.verify_receipt(request)
        raise LocalPillarError("UNSUPPORTED_ACTION", "twin transfer action is unsupported")

    def close(self) -> None:
        self.stop_receiver()


class CollectiveEvidenceCapability:
    """Verify consent-bound peer contributions and compute a robust recommendation."""

    def __init__(
        self,
        *,
        node_id: str,
        database_path: Path,
        shared_secret: str | None,
        allowed_peers: tuple[str, ...],
        rag: AgenticRAGCapability,
    ) -> None:
        self.node_id = node_id
        self.database_path = database_path.resolve()
        self.allowed_peers = frozenset(allowed_peers)
        self.rag = rag
        self._key = (
            hashlib.sha256((shared_secret + "|collective-evidence-v1").encode()).digest()
            if shared_secret and len(shared_secret) >= 32
            else None
        )
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS collective_contributions(
                        contribution_id TEXT PRIMARY KEY, source_node TEXT NOT NULL,
                        evidence_id TEXT NOT NULL, value REAL NOT NULL,
                        trust REAL NOT NULL, quality REAL NOT NULL,
                        privacy_budget REAL NOT NULL, consent_receipt TEXT NOT NULL,
                        nonce TEXT UNIQUE NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
                        packet_json TEXT NOT NULL, created_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_collective_active
                    ON collective_contributions(revoked,source_node);
                    CREATE TABLE IF NOT EXISTS collective_revocations(
                        nonce TEXT PRIMARY KEY, contribution_id TEXT NOT NULL,
                        source_node TEXT NOT NULL, created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS collective_consent_nonces(
                        nonce TEXT PRIMARY KEY, source_node TEXT NOT NULL,
                        contribution_id TEXT NOT NULL, consumed_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS collective_aggregates(
                        aggregate_id TEXT PRIMARY KEY, local_evidence_id TEXT NOT NULL,
                        local_value REAL NOT NULL, peer_median REAL NOT NULL,
                        recommendation REAL NOT NULL, peer_count INTEGER NOT NULL,
                        conflict_detected INTEGER NOT NULL, spread REAL NOT NULL,
                        privacy_budget_spent REAL NOT NULL, peer_evidence_ids_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "collective evidence store unavailable") from exc

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def health_check(self) -> bool:
        return bool(self._key and len(self.allowed_peers) >= 2)

    def _sign(self, payload: Mapping[str, Any]) -> str:
        if self._key is None:
            raise LocalPillarError("KEY_NOT_CONFIGURED", "collective key is unavailable")
        return hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()

    def _validate_consent(
        self,
        receipt: object,
        *,
        source_node: str,
        evidence_id: str,
        privacy_budget: float,
    ) -> Mapping[str, Any]:
        if not isinstance(receipt, Mapping):
            raise LocalPillarError("CONSENT_INVALID", "collective consent receipt must be an object")
        payload = dict(receipt)
        signature = payload.pop("signature", None)
        expected = {
            "type",
            "version",
            "source_node",
            "evidence_id",
            "max_privacy_budget",
            "issued_at",
            "expires_at",
            "nonce",
        }
        if set(payload) != expected or payload.get("type") != "COLLECTIVE_CONSENT" or payload.get("version") != 1:
            raise LocalPillarError("CONSENT_INVALID", "collective consent schema is invalid")
        if not isinstance(signature, str) or not hmac.compare_digest(signature, self._sign(payload)):
            raise LocalPillarError("CONSENT_INVALID", "collective consent signature is invalid")
        if (
            payload.get("source_node") != source_node
            or payload.get("evidence_id") != evidence_id
        ):
            raise LocalPillarError("CONSENT_INVALID", "collective consent does not match contribution")
        try:
            issued_at = float(payload["issued_at"])
            expires_at = float(payload["expires_at"])
            maximum = float(payload["max_privacy_budget"])
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("CONSENT_INVALID", "collective consent limits are invalid") from exc
        now = time.time()
        if (
            not all(math.isfinite(item) for item in (issued_at, expires_at, maximum))
            or issued_at > now + 300
            or expires_at <= now
            or expires_at - issued_at > 30 * 24 * 3600
            or not 0 <= maximum <= 0.25
            or privacy_budget > maximum
        ):
            raise LocalPillarError("CONSENT_INVALID", "collective consent is expired or exceeded")
        _text(payload.get("nonce"), "consent nonce", 128)
        return receipt

    def issue_consent(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _require_fields(
            request,
            required={"action", "evidence_id", "max_privacy_budget", "expires_at"},
        )
        evidence_id = _text(request.get("evidence_id"), "evidence_id", 128)
        if not self.rag.evidence_exists(evidence_id):
            raise LocalPillarError("INVALID_EVIDENCE", "consent evidence is unavailable")
        max_budget_raw = request.get("max_privacy_budget")
        expires_at_raw = request.get("expires_at")
        if max_budget_raw is None or expires_at_raw is None:
            raise LocalPillarError("INVALID_INPUT", "consent limits must be numeric")
        try:
            maximum = float(max_budget_raw)
            expires_at = float(expires_at_raw)
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "consent limits must be numeric") from exc
        now = time.time()
        if (
            not math.isfinite(maximum)
            or not 0 <= maximum <= 0.25
            or not math.isfinite(expires_at)
            or not now < expires_at <= now + 30 * 24 * 3600
        ):
            raise LocalPillarError("INVALID_INPUT", "consent limits violate local policy")
        payload = {
            "type": "COLLECTIVE_CONSENT",
            "version": 1,
            "source_node": self.node_id,
            "evidence_id": evidence_id,
            "max_privacy_budget": maximum,
            "issued_at": now,
            "expires_at": expires_at,
            "nonce": uuid.uuid4().hex,
        }
        receipt = {**payload, "signature": self._sign(payload)}
        return LocalPillarResult("P032", "COLLECTIVE_CONSENT_ISSUED", {"receipt": receipt})

    def create(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _require_fields(
            request,
            required={
                "action",
                "evidence_id",
                "value",
                "trust",
                "quality",
                "privacy_budget",
                "consent_receipt",
            },
        )
        evidence_id = _text(request.get("evidence_id"), "evidence_id", 128)
        if not self.rag.evidence_exists(evidence_id):
            raise LocalPillarError("INVALID_EVIDENCE", "local contribution evidence is unavailable")
        val_raw = request.get("value")
        trust_raw = request.get("trust")
        quality_raw = request.get("quality")
        budget_raw = request.get("privacy_budget")
        if val_raw is None or trust_raw is None or quality_raw is None or budget_raw is None:
            raise LocalPillarError("INVALID_INPUT", "collective metrics must be numeric")
        try:
            value = float(val_raw)
            trust = float(trust_raw)
            quality = float(quality_raw)
            privacy_budget = float(budget_raw)
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "collective metrics must be numeric") from exc
        if not all(math.isfinite(item) and 0 <= item <= 1 for item in (value, trust, quality, privacy_budget)):
            raise LocalPillarError("INVALID_INPUT", "collective metrics must be finite and 0-1")
        consent = self._validate_consent(
            request.get("consent_receipt"),
            source_node=self.node_id,
            evidence_id=evidence_id,
            privacy_budget=privacy_budget,
        )
        payload = {
            "type": "COLLECTIVE_CONTRIBUTION",
            "version": 1,
            "contribution_id": uuid.uuid4().hex,
            "source_node": self.node_id,
            "evidence_id": evidence_id,
            "value": value,
            "trust": trust,
            "quality": quality,
            "privacy_budget": privacy_budget,
            "consent_receipt": consent,
            "nonce": uuid.uuid4().hex,
            "created_at": time.time(),
        }
        packet = {**payload, "signature": self._sign(payload)}
        return LocalPillarResult("P032", "COLLECTIVE_CONTRIBUTION_CREATED", {"packet": packet})

    def ingest(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _require_fields(request, required={"action", "packet"})
        packet = request.get("packet")
        if not isinstance(packet, Mapping):
            raise LocalPillarError("INVALID_INPUT", "collective packet must be an object")
        payload = dict(packet)
        signature = payload.pop("signature", None)
        expected_packet_fields = {
            "type",
            "version",
            "contribution_id",
            "source_node",
            "evidence_id",
            "value",
            "trust",
            "quality",
            "privacy_budget",
            "consent_receipt",
            "nonce",
            "created_at",
        }
        if set(payload) != expected_packet_fields:
            raise LocalPillarError("PACKET_INVALID", "collective packet schema is invalid")
        if payload.get("type") != "COLLECTIVE_CONTRIBUTION" or payload.get("version") != 1:
            raise LocalPillarError("PACKET_INVALID", "collective packet type is invalid")
        if not isinstance(signature, str) or not hmac.compare_digest(signature, self._sign(payload)):
            raise LocalPillarError("SIGNATURE_INVALID", "collective packet signature is invalid")
        source = _text(payload.get("source_node"), "source_node", 128)
        if source not in self.allowed_peers:
            raise LocalPillarError("PEER_DENIED", "collective source is not allowlisted")
        contribution_id = _text(payload.get("contribution_id"), "contribution_id", 128)
        evidence_id = _text(payload.get("evidence_id"), "evidence_id", 128)
        nonce = _text(payload.get("nonce"), "nonce", 128)
        if not self.rag.evidence_exists(evidence_id):
            raise LocalPillarError("INVALID_EVIDENCE", "peer evidence is not in the local evidence catalog")
        try:
            created = float(payload["created_at"])
            value = float(payload["value"])
            trust = float(payload["trust"])
            quality = float(payload["quality"])
            budget = float(payload["privacy_budget"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LocalPillarError("PACKET_INVALID", "collective metrics are invalid") from exc
        if abs(time.time() - created) > 300:
            raise LocalPillarError("CLOCK_SKEW", "collective packet is stale")
        if not all(math.isfinite(item) and 0 <= item <= 1 for item in (value, trust, quality, budget)):
            raise LocalPillarError("PACKET_INVALID", "collective metrics are outside 0-1")
        if trust < 0.5 or quality < 0.5:
            raise LocalPillarError("POISONING_GUARD", "collective contribution failed trust/quality gate")
        if budget > 0.25:
            raise LocalPillarError("PRIVACY_BUDGET_EXCEEDED", "collective privacy budget exceeds policy")
        consent = self._validate_consent(
            payload.get("consent_receipt"),
            source_node=source,
            evidence_id=evidence_id,
            privacy_budget=budget,
        )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO collective_consent_nonces VALUES(?,?,?,?)",
                    (consent["nonce"], source, contribution_id, time.time()),
                )
                connection.execute(
                    "INSERT INTO collective_contributions VALUES(?,?,?,?,?,?,?,?,?,0,?,?)",
                    (
                        contribution_id,
                        source,
                        evidence_id,
                        value,
                        trust,
                        quality,
                        budget,
                        json.dumps(consent, sort_keys=True),
                        nonce,
                        json.dumps(packet, sort_keys=True),
                        created,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise LocalPillarError("REPLAY_DETECTED", "collective contribution was already ingested") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "collective contribution was not stored") from exc
        return LocalPillarResult("P032", "COLLECTIVE_CONTRIBUTION_ACCEPTED", {"contribution_id": contribution_id, "source_node": source})

    def aggregate(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _require_fields(request, required={"action", "local_evidence_id", "local_value"})
        local_evidence = _text(request.get("local_evidence_id"), "local_evidence_id", 128)
        if not self.rag.evidence_exists(local_evidence):
            raise LocalPillarError("INVALID_EVIDENCE", "local authority evidence is unavailable")
        local_val_raw = request.get("local_value")
        if local_val_raw is None:
            raise LocalPillarError("INVALID_INPUT", "local_value is required")
        try:
            local_value = float(local_val_raw)
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "local_value must be numeric") from exc
        if not math.isfinite(local_value) or not 0 <= local_value <= 1:
            raise LocalPillarError("INVALID_INPUT", "local_value must be within 0-1")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM collective_contributions WHERE revoked=0 ORDER BY source_node,created_at DESC"
            ).fetchall()
        latest: dict[str, sqlite3.Row] = {}
        for row in rows:
            latest.setdefault(row["source_node"], row)
        if len(latest) < 2:
            raise LocalPillarError("INSUFFICIENT_PEERS", "at least two trusted peer contributions are required")
        values = sorted(float(row["value"]) for row in latest.values())
        midpoint = len(values) // 2
        median = values[midpoint] if len(values) % 2 else (values[midpoint - 1] + values[midpoint]) / 2
        spread = max(values) - min(values)
        recommendation = 0.7 * local_value + 0.3 * median
        aggregate_id = uuid.uuid4().hex
        peer_evidence_ids = [row["evidence_id"] for row in latest.values()]
        budget_spent = sum(float(row["privacy_budget"]) for row in latest.values())
        created_at = time.time()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO collective_aggregates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    aggregate_id,
                    local_evidence,
                    local_value,
                    median,
                    recommendation,
                    len(latest),
                    1 if spread > 0.4 else 0,
                    spread,
                    budget_spent,
                    json.dumps(peer_evidence_ids),
                    created_at,
                ),
            )
        return LocalPillarResult(
            "P032",
            "COLLECTIVE_RECOMMENDATION_CREATED",
            {
                "aggregate_id": aggregate_id,
                "local_value": local_value,
                "peer_median": median,
                "recommendation": recommendation,
                "peer_count": len(latest),
                "conflict_detected": spread > 0.4,
                "spread": spread,
                "privacy_budget_spent": budget_spent,
                "overrides_local_authority": False,
                "local_evidence_id": local_evidence,
                "peer_evidence_ids": peer_evidence_ids,
            },
        )

    def revoke(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _require_fields(
            request,
            required={"action", "type", "contribution_id", "source_node", "nonce", "signature"},
        )
        contribution_id = _text(request.get("contribution_id"), "contribution_id", 128)
        source_node = _text(request.get("source_node"), "source_node", 128)
        nonce = _text(request.get("nonce"), "nonce", 128)
        signature = request.get("signature")
        payload = {
            "type": "COLLECTIVE_REVOCATION",
            "contribution_id": contribution_id,
            "source_node": source_node,
            "nonce": nonce,
        }
        if request.get("type") != "COLLECTIVE_REVOCATION":
            raise LocalPillarError("PACKET_INVALID", "revocation packet type is invalid")
        if source_node not in self.allowed_peers:
            raise LocalPillarError("PEER_DENIED", "revocation source is not allowlisted")
        if not isinstance(signature, str) or not hmac.compare_digest(signature, self._sign(payload)):
            raise LocalPillarError("SIGNATURE_INVALID", "revocation signature is invalid")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO collective_revocations VALUES(?,?,?,?)",
                    (nonce, contribution_id, source_node, time.time()),
                )
            except sqlite3.IntegrityError as exc:
                raise LocalPillarError("REPLAY_DETECTED", "revocation nonce was already used") from exc
            cursor = connection.execute(
                "UPDATE collective_contributions SET revoked=1 WHERE contribution_id=? AND source_node=? AND revoked=0",
                (contribution_id, source_node),
            )
            if cursor.rowcount != 1:
                raise LocalPillarError("CONTRIBUTION_NOT_FOUND", "contribution cannot be revoked")
        return LocalPillarResult("P032", "COLLECTIVE_CONTRIBUTION_REVOKED", {"contribution_id": contribution_id})

    def create_revocation(self, contribution_id: str) -> dict[str, Any]:
        payload = {
            "type": "COLLECTIVE_REVOCATION",
            "contribution_id": contribution_id,
            "source_node": self.node_id,
            "nonce": uuid.uuid4().hex,
        }
        return {**payload, "signature": self._sign(payload)}

    def probe_collective(self) -> dict[str, Any]:
        return {
            "capability_id": COLLECTIVE_EVIDENCE_CAPABILITY_ID,
            "provider": "signed_robust_evidence_aggregation",
            "node_id": self.node_id,
            "allowed_peers": sorted(self.allowed_peers),
            "signature_algorithm": "HMAC-SHA256",
            "aggregation_strategy": "ROBUST_MEDIAN_WITH_LOCAL_AUTHORITY",
            "min_peers_required": 2,
            "max_privacy_budget_per_node": 0.25,
            "max_clock_skew_seconds": 300,
            "poisoning_trust_threshold": 0.5,
            "poisoning_quality_threshold": 0.5,
            "conflict_spread_threshold": 0.4,
            "local_authority_weight": 0.7,
            "peer_median_weight": 0.3,
            "database_path": str(self.database_path),
            "healthy": self.health_check(),
        }

    def get_contributions(self, request: Mapping[str, Any]) -> LocalPillarResult:
        include_revoked = bool(request.get("include_revoked", False))
        with self._connect() as connection:
            if include_revoked:
                rows = connection.execute(
                    "SELECT * FROM collective_contributions ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM collective_contributions WHERE revoked=0 ORDER BY created_at DESC"
                ).fetchall()
        items = [dict(r) for r in rows]
        return LocalPillarResult("P032", "COLLECTIVE_CONTRIBUTIONS_RETRIEVED", {"count": len(items), "contributions": items})

    def get_aggregates(self, request: Mapping[str, Any]) -> LocalPillarResult:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM collective_aggregates ORDER BY created_at DESC"
            ).fetchall()
        items = [dict(r) for r in rows]
        return LocalPillarResult("P032", "COLLECTIVE_AGGREGATES_RETRIEVED", {"count": len(items), "aggregates": items})

    def verify_packet(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _require_fields(request, required={"action", "packet"})
        packet = request.get("packet")
        if not isinstance(packet, Mapping):
            raise LocalPillarError("INVALID_INPUT", "packet must be an object")
        payload = dict(packet)
        signature = payload.pop("signature", None)
        if not isinstance(signature, str) or not hmac.compare_digest(signature, self._sign(payload)):
            raise LocalPillarError("SIGNATURE_INVALID", "packet signature is invalid")
        return LocalPillarResult("P032", "COLLECTIVE_PACKET_VERIFIED", {"valid": True, "contribution_id": payload.get("contribution_id")})

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        if action == "issue_consent":
            return self.issue_consent(request)
        if action == "create":
            return self.create(request)
        if action == "ingest":
            return self.ingest(request)
        if action == "aggregate":
            return self.aggregate(request)
        if action == "revoke":
            return self.revoke(request)
        if action == "probe":
            return LocalPillarResult("P032", "COLLECTIVE_PROBED", self.probe_collective())
        if action == "get_contributions":
            return self.get_contributions(request)
        if action == "get_aggregates":
            return self.get_aggregates(request)
        if action == "verify_packet":
            return self.verify_packet(request)
        raise LocalPillarError("UNSUPPORTED_ACTION", "collective action is unsupported")
