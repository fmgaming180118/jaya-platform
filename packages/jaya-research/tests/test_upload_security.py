import io
import time
from pathlib import Path

import pytest

from jaya_research.network.upload_security import (
    UploadPolicy,
    UploadSecurityError,
    store_upload,
)


PDF_POLICY = UploadPolicy(
    allowed_extensions=frozenset({".pdf"}),
    max_file_bytes=1024,
    max_directory_bytes=4096,
    stream_timeout_seconds=1.0,
)


def _store(tmp_path: Path, content: bytes, filename: str = "paper.pdf"):
    return store_upload(
        io.BytesIO(content),
        original_filename=filename,
        media_type="application/pdf",
        destination_dir=tmp_path / "uploads",
        policy=PDF_POLICY,
    )


def test_valid_pdf_is_hashed_and_atomically_stored(tmp_path):
    receipt = _store(tmp_path, b"%PDF-1.7\nminimal")

    assert receipt.path.is_file()
    assert receipt.path.parent == (tmp_path / "uploads").resolve()
    assert len(receipt.sha256) == 64
    assert receipt.size_bytes == len(b"%PDF-1.7\nminimal")
    assert receipt.duplicate is False
    assert list((tmp_path / "uploads" / ".quarantine").glob("*.part")) == []


@pytest.mark.parametrize(
    "filename",
    [
        "../paper.pdf",
        r"..\paper.pdf",
        "/tmp/paper.pdf",
        r"C:\temp\paper.pdf",
        "NUL.pdf",
        "paper.pdf.",
        "paper\x00.pdf",
    ],
)
def test_path_like_or_reserved_filename_is_rejected(tmp_path, filename):
    with pytest.raises(UploadSecurityError) as exc_info:
        _store(tmp_path, b"%PDF-1.7\nminimal", filename)

    assert exc_info.value.code == "INVALID_FILENAME"
    assert not list((tmp_path / "uploads").glob("*.pdf"))


def test_extension_and_magic_must_agree(tmp_path):
    with pytest.raises(UploadSecurityError) as exc_info:
        _store(tmp_path, b"not a pdf")

    assert exc_info.value.code == "MAGIC_MISMATCH"
    assert not list((tmp_path / "uploads").glob("*.pdf"))


def test_declared_mime_must_match_extension(tmp_path):
    with pytest.raises(UploadSecurityError) as exc_info:
        store_upload(
            io.BytesIO(b"%PDF-1.7\nminimal"),
            original_filename="paper.pdf",
            media_type="image/png",
            destination_dir=tmp_path / "uploads",
            policy=PDF_POLICY,
        )

    assert exc_info.value.code == "MIME_MISMATCH"


def test_oversize_upload_is_deleted_from_quarantine(tmp_path):
    with pytest.raises(UploadSecurityError) as exc_info:
        _store(tmp_path, b"%PDF-" + (b"x" * 2048))

    assert exc_info.value.code == "FILE_TOO_LARGE"
    assert not list((tmp_path / "uploads").rglob("*.part"))
    assert not list((tmp_path / "uploads").glob("*.pdf"))


def test_identical_content_is_deduplicated_even_under_another_name(tmp_path):
    content = b"%PDF-1.7\nsame-content"
    first = _store(tmp_path, content, "first.pdf")
    second = _store(tmp_path, content, "second.pdf")

    assert second.duplicate is True
    assert second.path == first.path
    assert len(list((tmp_path / "uploads").glob("*.pdf"))) == 1


def test_same_filename_never_overwrites_different_content(tmp_path):
    first = _store(tmp_path, b"%PDF-1.7\nfirst", "paper.pdf")
    second = _store(tmp_path, b"%PDF-1.7\nsecond", "paper.pdf")

    assert first.path != second.path
    assert first.path.read_bytes().endswith(b"first")
    assert second.path.read_bytes().endswith(b"second")


def test_workspace_quota_is_enforced(tmp_path):
    policy = UploadPolicy(
        allowed_extensions=frozenset({".pdf"}),
        max_file_bytes=64,
        max_directory_bytes=64,
        stream_timeout_seconds=1.0,
    )
    store_upload(
        io.BytesIO(b"%PDF-" + (b"a" * 20)),
        original_filename="first.pdf",
        media_type="application/pdf",
        destination_dir=tmp_path / "uploads",
        policy=policy,
    )

    with pytest.raises(UploadSecurityError) as exc_info:
        store_upload(
            io.BytesIO(b"%PDF-" + (b"b" * 40)),
            original_filename="second.pdf",
            media_type="application/pdf",
            destination_dir=tmp_path / "uploads",
            policy=policy,
        )

    assert exc_info.value.code == "WORKSPACE_QUOTA_EXCEEDED"


class SlowStream:
    def __init__(self):
        self.calls = 0

    def read(self, _size):
        self.calls += 1
        time.sleep(0.02)
        return b"%PDF-1.7\nslow" if self.calls == 1 else b""


def test_stream_timeout_removes_partial_file(tmp_path):
    policy = UploadPolicy(
        allowed_extensions=frozenset({".pdf"}),
        max_file_bytes=1024,
        max_directory_bytes=4096,
        stream_timeout_seconds=0.01,
    )

    with pytest.raises(UploadSecurityError) as exc_info:
        store_upload(
            SlowStream(),
            original_filename="slow.pdf",
            media_type="application/pdf",
            destination_dir=tmp_path / "uploads",
            policy=policy,
        )

    assert exc_info.value.code == "UPLOAD_TIMEOUT"
    assert not list((tmp_path / "uploads").rglob("*.part"))
