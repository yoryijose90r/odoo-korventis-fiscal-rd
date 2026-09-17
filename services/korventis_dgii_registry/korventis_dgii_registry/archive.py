"""ZIP membership checks. No extraction to disk. No remote download."""

from __future__ import annotations

import io
import pathlib
import stat
import zipfile
from dataclasses import dataclass


class ArchiveError(ValueError):
    """ZIP rejected. Message must not include secrets."""


@dataclass(frozen=True)
class ZipLimits:
    max_archive_bytes: int = 100 * 1024 * 1024
    max_uncompressed_bytes: int = 300 * 1024 * 1024
    max_compression_ratio: float = 25.0


@dataclass(frozen=True)
class ZipMember:
    filename: str
    file_size: int


BOUNDED_READ_CHUNK = 64 * 1024


class BoundedReader(io.BufferedIOBase):
    """Count decompressed bytes and abort if the declared ZIP size was a lie."""

    def __init__(self, inner, limit, chunk_size=BOUNDED_READ_CHUNK):
        self._inner = inner
        self._limit = int(limit)
        self._chunk = max(1, int(chunk_size))
        self._seen = 0

    def readable(self):
        return True

    def seekable(self):
        seekable = getattr(self._inner, "seekable", None)
        if seekable:
            return bool(seekable())
        return False

    def _budget(self):
        remaining = self._limit - self._seen
        if remaining < 0:
            raise ArchiveError("uncompressed size exceeded during read")
        return remaining + 1

    def _want(self, size):
        budget = self._budget()
        if size is None or size < 0:
            return min(self._chunk, budget)
        return min(int(size), self._chunk, budget)

    def _pull(self, size):
        want = self._want(size)
        data = self._inner.read(want)
        if len(data) > want:
            data = data[:want]
        self._account(data)
        return data

    def read(self, size=-1):
        if size == 0:
            return b""
        if size is None or size < 0:
            chunks = []
            while True:
                piece = self._pull(-1)
                if not piece:
                    break
                chunks.append(piece)
            return b"".join(chunks)
        return self._pull(size)

    def read1(self, size=-1):
        if size == 0:
            return b""
        want = self._want(-1 if size is None or size < 0 else size)
        read1 = getattr(self._inner, "read1", None)
        data = read1(want) if read1 else self._inner.read(want)
        if len(data) > want:
            data = data[:want]
        self._account(data)
        return data

    def readinto(self, buffer):
        data = self._pull(len(buffer))
        n = len(data)
        buffer[:n] = data
        return n

    def readinto1(self, buffer):
        data = self.read1(len(buffer))
        n = len(data)
        buffer[:n] = data
        return n

    def peek(self, size=0):
        peek = getattr(self._inner, "peek", None)
        if not peek:
            return b""
        remaining = self._limit - self._seen
        if remaining <= 0:
            return b""
        if size is None or size < 0 or size == 0:
            want = min(self._chunk, remaining)
        else:
            want = min(int(size), self._chunk, remaining)
        data = peek(want)
        if len(data) > want:
            data = data[:want]
        return data

    def _account(self, data):
        if data:
            self._seen += len(data)
            if self._seen > self._limit:
                raise ArchiveError("uncompressed size exceeded during read")

    def seek(self, pos, whence=io.SEEK_SET):
        result = self._inner.seek(pos, whence)
        if whence == io.SEEK_SET:
            self._seen = int(pos)
        else:
            self._seen = int(self._inner.tell())
        return result

    def tell(self):
        return self._inner.tell()


def _is_unsafe_member(member):
    pure_name = pathlib.PurePosixPath(member.filename.replace("\\", "/"))
    mode = member.external_attr >> 16
    return bool(
        member.is_dir()
        or pure_name.is_absolute()
        or ".." in pure_name.parts
        or len(pure_name.parts) != 1
        or pure_name.suffix.lower() != ".csv"
        or stat.S_ISLNK(mode)
        or member.flag_bits & 0x1
    )


def inspect_zip(path, limits=None):
    limits = limits or ZipLimits()
    size = path.stat().st_size
    if size <= 0 or size > limits.max_archive_bytes:
        raise ArchiveError("ZIP size is outside the allowed range")
    if not zipfile.is_zipfile(path):
        raise ArchiveError("file is not a valid ZIP")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != 1:
            raise ArchiveError("ZIP must contain exactly one CSV member")
        member = members[0]
        if _is_unsafe_member(member):
            raise ArchiveError("ZIP member path or type is not allowed")
        ratio = member.file_size / float(max(member.compress_size, 1))
        if (
            member.file_size <= 0
            or member.file_size > limits.max_uncompressed_bytes
            or ratio > limits.max_compression_ratio
        ):
            raise ArchiveError("ZIP compression ratio or size is not allowed")
        if archive.testzip() is not None:
            raise ArchiveError("ZIP is corrupt")
        pure_name = pathlib.PurePosixPath(member.filename.replace("\\", "/"))
        return ZipMember(filename=pure_name.name, file_size=member.file_size)
