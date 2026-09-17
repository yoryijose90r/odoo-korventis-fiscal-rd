"""ZIP membership tests. No PostgreSQL required."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from korventis_dgii_registry.archive import ArchiveError, ZipLimits, inspect_zip
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
