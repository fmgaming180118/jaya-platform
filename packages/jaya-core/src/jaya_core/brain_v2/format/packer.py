# pyright: reportMissingTypeArgument=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownType=false, reportGeneralTypeIssues=false, reportUndefinedVariable=false
# type: ignore

"""Pillar 22 / V18 — 2-bit Ternary Weight Packer.

Encodes ternary weights {-1, 0, +1} into 2 bits per value,
packing 4 values per byte.  This reduces IRON_BODY section size
from ~1 MB (int8) to ~250 KB (STANDARD) or ~50 KB (NANO).

Encoding table
--------------
  0b00  →  -1
  0b01  →   0
  0b10  →  +1
  0b11  →   0  (unused; treated as 0 on decode)

Usage
-----
    from jaya_core.brain_v2.format.packer import pack_ternary, unpack_ternary

    packed = pack_ternary(weight_array)   # bytes
    restored = unpack_ternary(packed, len(weight_array))  # np.ndarray int8
"""

from __future__ import annotations

import struct
from typing import Any, Union

import numpy as np

# Sentinel stored at the start of a packed blob so we can sanity-check.
_PACK_MAGIC = b"T2BV"  # "Ternary 2-Bit Values"

# Map {-1→0, 0→1, +1→2} for encoding
_ENC = np.array([0, 1, 2], dtype=np.uint8)  # index with val+1

# Map 2-bit code back to ternary {0→-1, 1→0, 2→+1, 3→0}
_DEC = np.array([-1, 0, 1, 0], dtype=np.int8)


def pack_ternary(arr: Union[np.ndarray[Any, Any], list[Any]]) -> bytes:
    """Pack a ternary weight array into a 2-bit-per-value byte string.

    Parameters
    ----------
    arr:
        Array of int8 values in {-1, 0, +1}.  Other values are clipped
        to the nearest valid ternary value before packing.

    Returns
    -------
    bytes
        4-byte magic + 4-byte length (uint32 LE) + packed bytes.
    """
    a = np.asarray(arr, dtype=np.int8).ravel()
    n = len(a)

    # Clip to valid ternary range and encode to 2-bit codes (0,1,2)
    codes = _ENC[np.clip(a, -1, 1) + 1]  # shape (n,), dtype uint8, values 0-2

    # Pad to multiple of 4 so we always fill complete bytes
    pad = (4 - n % 4) % 4
    if pad:
        codes = np.append(codes, np.ones(pad, dtype=np.uint8))  # pad with code 1 (=0)

    # Pack 4 codes per byte: byte = c0 | (c1<<2) | (c2<<4) | (c3<<6)
    reshaped = codes.reshape(-1, 4)
    packed_bytes = (
        reshaped[:, 0].astype(np.uint8)
        | (reshaped[:, 1].astype(np.uint8) << 2)
        | (reshaped[:, 2].astype(np.uint8) << 4)
        | (reshaped[:, 3].astype(np.uint8) << 6)
    ).tobytes()

    return _PACK_MAGIC + struct.pack("<I", n) + packed_bytes


def unpack_ternary(data: bytes, length: int | None = None) -> np.ndarray[Any, Any]:
    """Unpack a 2-bit-packed blob back to a ternary int8 array.

    Parameters
    ----------
    data:
        Bytes produced by :func:`pack_ternary`.
    length:
        Expected number of elements.  If *None*, taken from the embedded
        header.  Pass an explicit value to truncate padding.

    Returns
    -------
    np.ndarray of int8 with values in {-1, 0, +1}.
    """
    if data[:4] != _PACK_MAGIC:
        raise ValueError(f"Invalid packer magic: expected {_PACK_MAGIC!r}, got {data[:4]!r}")

    stored_n: int = struct.unpack("<I", data[4:8])[0]
    n = length if length is not None else stored_n
    raw = np.frombuffer(data[8:], dtype=np.uint8)

    # Unpack: extract 4 codes per byte
    codes = np.empty(len(raw) * 4, dtype=np.uint8)
    codes[0::4] = raw & 0x03
    codes[1::4] = (raw >> 2) & 0x03
    codes[2::4] = (raw >> 4) & 0x03
    codes[3::4] = (raw >> 6) & 0x03

    return _DEC[codes[:n]]


def pack_state_dict(state_dict: dict[Any, Any]) -> bytes:
    """Flatten and pack an entire model state-dict into one blob.

    Format
    ------
    4-byte magic
    4-byte number of tensors (uint32 LE)
    For each tensor:
        2-byte key length (uint16 LE)
        key bytes (UTF-8)
        4-byte shape rank (uint32 LE)
        shape dims (rank × uint32 LE)
        packed tensor blob (from pack_ternary)
        4-byte blob length (uint32 LE)  ← written *after* blob for easy skip

    Returns
    -------
    bytes
    """
    import io
    buf = io.BytesIO()
    buf.write(b"JAYA_SD1")  # state-dict magic

    # Accept list of (key, array) tuples OR a nested dict
    if isinstance(state_dict, (list, tuple)):
        # list of (key, array) tuples — convert to flat dict directly
        flat: dict[str, Any] = {k: v for k, v in state_dict}
    else:
        # Flatten nested dict into key→array mapping
        flat: dict[str, Any] = {}
        _flatten(state_dict, "", flat)

    buf.write(struct.pack("<I", len(flat)))

    for key, arr in flat.items():
        key_b = key.encode("utf-8")
        buf.write(struct.pack("<H", len(key_b)))
        buf.write(key_b)
        a = np.asarray(arr, dtype=np.int8)
        shape = a.shape
        buf.write(struct.pack("<I", len(shape)))
        buf.write(struct.pack(f"<{len(shape)}I", *shape))
        blob = pack_ternary(a)
        buf.write(struct.pack("<I", len(blob)))
        buf.write(blob)

    return buf.getvalue()


def unpack_state_dict(data: bytes) -> dict[str, Any]:
    """Inverse of :func:`pack_state_dict`. Returns nested dict.

    The returned mapping is string keys to NumPy arrays (or nested
    structures).  Precise types are difficult to express, so we use
    ``Any`` for the values to keep static checkers happy.
    """
    import io
    buf = io.BytesIO(data)
    magic = buf.read(8)
    if magic != b"JAYA_SD1":
        raise ValueError(f"Invalid state-dict magic: {magic!r}")

    n_tensors = struct.unpack("<I", buf.read(4))[0]
    flat: dict[str, np.ndarray[Any, Any]] = {}
    for _ in range(n_tensors):
        key_len = struct.unpack("<H", buf.read(2))[0]
        key = buf.read(key_len).decode("utf-8")
        rank = struct.unpack("<I", buf.read(4))[0]
        shape = struct.unpack(f"<{rank}I", buf.read(4 * rank))
        blob_len = struct.unpack("<I", buf.read(4))[0]
        blob = buf.read(blob_len)
        total = 1
        for d in shape:
            total *= d
        arr = unpack_ternary(blob, total).reshape(shape)
        flat[key] = arr

    # Rebuild nested dict
    result: dict[Any, Any] = {}
    _unflatten(flat, result)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten(obj: dict[Any, Any] | np.ndarray[Any, Any], prefix: str, out: dict[Any, Any]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(v, f"{prefix}{k}.", out)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _flatten(v, f"{prefix}{i}.", out)
    else:
        key = prefix.rstrip(".")
        out[key] = obj


def _unflatten(flat: dict[Any, Any], out: dict[Any, Any]) -> None:
    for dotted_key, arr in flat.items():
        parts = dotted_key.split(".")
        d: dict = out
        for p in parts[:-1]:
            if p.isdigit():
                p = int(p)  # type: ignore[assignment]
            d = d.setdefault(p, {})
        last = parts[-1]
        if last.isdigit():
            last = int(last)  # type: ignore[assignment]
        d[last] = arr
