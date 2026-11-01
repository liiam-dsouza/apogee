"""Content-addressed asset storage: thrust curves, drag tables, .ork files.

An asset is identified by the sha256 of its bytes, so a mission that names a
hash names exactly one file, forever. Stores verify the hash on read: a
corrupted or swapped file is an error, never a silently different flight.
"""

import hashlib
from pathlib import Path
from typing import Protocol


class AssetError(LookupError):
    """An asset is missing, or its bytes do not match its hash."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AssetStore(Protocol):
    def read(self, sha256: str) -> bytes: ...


class DirectoryAssetStore:
    """Assets as files named by their hash, in one directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, sha256: str) -> Path:
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise AssetError(f"not a sha256: {sha256!r}")
        return self.root / sha256

    def read(self, sha256: str) -> bytes:
        try:
            data = self._path(sha256).read_bytes()
        except FileNotFoundError as e:
            raise AssetError(f"asset {sha256} is not in the store") from e
        if sha256_hex(data) != sha256:
            raise AssetError(f"asset {sha256} is corrupt: its contents do not match its hash")
        return data

    def put(self, data: bytes) -> str:
        """Store bytes; returns their sha256. Idempotent."""
        sha = sha256_hex(data)
        path = self._path(sha)
        if not path.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)  # atomic: readers never see a partial file
        return sha

    def has(self, sha256: str) -> bool:
        return self._path(sha256).exists()


class MemoryAssetStore:
    """In-memory store, for tests and scripts."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self._files = dict(files or {})

    def put(self, data: bytes) -> str:
        sha = sha256_hex(data)
        self._files[sha] = data
        return sha

    def read(self, sha256: str) -> bytes:
        try:
            return self._files[sha256]
        except KeyError as e:
            raise AssetError(f"asset {sha256} is not in the store") from e


def assets_from_directory(root: Path) -> MemoryAssetStore:
    """Every file under ``root``, keyed by hash whatever its name.

    For scripts and the CLI, where assets sit beside the mission file with
    their original names.
    """
    store = MemoryAssetStore()
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            store.put(path.read_bytes())
    return store
