"""ZIP membership tests. No PostgreSQL required."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from korventis_dgii_registry.archive import ArchiveError, BoundedReader, ZipLimits, inspect_zip
from tests.zip_fixtures import csv_bytes, valid_rows, write_zip


def test_inspect_accepts_single_csv(tmp_path):
    path = write_zip(tmp_path / "ok.zip", csv_bytes(valid_rows()))
    member = inspect_zip(path)
    assert member.filename == "padron.csv"


def test_inspect_rejects_corrupt_zip(tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"this is not a zip")
    with pytest.raises(ArchiveError):
        inspect_zip(path)


def test_inspect_rejects_multiple_csv(tmp_path):
    path = write_zip(
        tmp_path / "multi.zip",
        {"a.csv": csv_bytes(valid_rows()), "b.csv": csv_bytes(valid_rows())},
    )
    with pytest.raises(ArchiveError):
        inspect_zip(path)


def test_inspect_rejects_dangerous_path(tmp_path):
    path = tmp_path / "trav.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape.csv", csv_bytes(valid_rows()))
    with pytest.raises(ArchiveError):
        inspect_zip(path)


def test_inspect_rejects_encrypted_member():
    class _Member(object):
        filename = "padron.csv"
        flag_bits = 0x1
        external_attr = 0

        def is_dir(self):
            return False

    from korventis_dgii_registry.archive import _is_unsafe_member

    assert _is_unsafe_member(_Member()) is True


def test_inspect_rejects_uncompressed_limit(tmp_path):
    path = write_zip(tmp_path / "big.zip", csv_bytes(valid_rows()))
    with pytest.raises(ArchiveError):
        inspect_zip(path, ZipLimits(max_uncompressed_bytes=10))


def test_bounded_reader_aborts_over_limit():
    inner = io.BytesIO(b"x" * 80)
    reader = BoundedReader(inner, 50)
    with pytest.raises(ArchiveError, match="uncompressed size exceeded during read"):
        reader.read()


def test_bounded_reader_seek_zero_resets_count():
    inner = io.BytesIO(b"abcdefghij")
    reader = BoundedReader(inner, 6)
    assert reader.read(4) == b"abcd"
    reader.seek(0)
    assert reader.read(6) == b"abcdef"
    with pytest.raises(ArchiveError, match="uncompressed size exceeded during read"):
        reader.read(1)


class _RecordingStream(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.read_sizes = []
        self.read1_sizes = []
        self.peek_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)

    def read1(self, size=-1):
        self.read1_sizes.append(size)
        if size is None or size < 0:
            size = 8192
        return super().read(size)

    def peek(self, size=0):
        self.peek_sizes.append(size)
        pos = self.tell()
        if size is None or size < 0 or size == 0:
            data = super().read()
        else:
            data = super().read(size)
        self.seek(pos)
        return data


def test_bounded_reader_unlimited_read_uses_chunks():
    payload = b"abcdefghijklmnopqrstuvwxyz"
    inner = _RecordingStream(payload)
    reader = BoundedReader(inner, len(payload), chunk_size=8)
    assert reader.read(-1) == payload
    assert inner.read_sizes
    assert all(isinstance(size, int) and 0 < size <= 8 for size in inner.read_sizes)
    assert -1 not in inner.read_sizes
    assert None not in inner.read_sizes


def test_bounded_reader_chunked_reads_stay_within_budget():
    payload = b"x" * 40
    inner = _RecordingStream(payload)
    reader = BoundedReader(inner, 40, chunk_size=16)
    chunks = []
    while True:
        piece = reader.read(16)
        if not piece:
            break
        chunks.append(piece)
    assert b"".join(chunks) == payload
    assert all(size <= 16 for size in inner.read_sizes)


def test_bounded_reader_unlimited_read_detects_overflow():
    inner = _RecordingStream(b"x" * 80)
    reader = BoundedReader(inner, 20, chunk_size=8)
    with pytest.raises(ArchiveError, match="uncompressed size exceeded during read"):
        reader.read(-1)
    assert all(isinstance(size, int) and 0 < size <= 8 for size in inner.read_sizes)
    assert max(inner.read_sizes) <= 8
    assert -1 not in inner.read_sizes


def test_bounded_reader_read1_and_readinto_never_request_unlimited():
    payload = b"y" * 50
    inner = _RecordingStream(payload)
    reader = BoundedReader(inner, 50, chunk_size=10)
    assert reader.read1(-1) == payload[:10]
    buf = bytearray(1000)
    filled = reader.readinto(buf)
    assert filled == 10
    buf2 = bytearray(1000)
    filled2 = reader.readinto1(buf2)
    assert filled2 == 10
    assert -1 not in inner.read_sizes
    assert -1 not in inner.read1_sizes
    assert all(size <= 10 for size in inner.read_sizes)
    assert all(size <= 10 for size in inner.read1_sizes)


def test_bounded_reader_peek_is_capped():
    inner = _RecordingStream(b"z" * 40)
    reader = BoundedReader(inner, 12, chunk_size=8)
    peeked = reader.peek(-1)
    assert peeked == b"z" * 8
    assert reader.peek(0) == b"z" * 8
    assert inner.peek_sizes
    assert all(size > 0 and size <= 8 for size in inner.peek_sizes)


def test_bounded_reader_textiowrapper_within_limit():
    inner = io.BytesIO(b"RNC,NAME\n131000001,ACME\n")
    reader = BoundedReader(inner, 64, chunk_size=8)
    with io.TextIOWrapper(reader, encoding="latin-1", newline="") as text:
        assert "ACME" in text.read()


def test_bounded_reader_textiowrapper_exceeds_limit():
    inner = io.BytesIO(b"x" * 80)
    reader = BoundedReader(inner, 10, chunk_size=4)
    with io.TextIOWrapper(reader, encoding="latin-1", newline="") as text:
        with pytest.raises(ArchiveError, match="uncompressed size exceeded during read"):
            text.read()
