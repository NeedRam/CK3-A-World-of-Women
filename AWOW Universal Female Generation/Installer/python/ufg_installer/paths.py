"""Windows-safe relative path and reparse-point helpers."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path, PurePosixPath


class PathSafetyError(ValueError):
    pass


def validate_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PathSafetyError(f"invalid relative path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ":" in value or any(part in ("", ".", "..") for part in pure.parts):
        raise PathSafetyError(f"invalid relative path: {value!r}")
    if any(ord(ch) < 32 or ch in '*?"<>|' for ch in value):
        raise PathSafetyError(f"invalid relative path: {value!r}")
    return value


def is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if os.name == "nt":
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            return attrs != 0xFFFFFFFF and bool(attrs & 0x400)
    except OSError:
        return False
    return False


def assert_no_reparse_ancestors(root: Path) -> None:
    root = root.absolute()
    current = root
    chain: list[Path] = []
    while True:
        chain.append(current)
        if current.parent == current:
            break
        current = current.parent
    for item in reversed(chain):
        if item.exists() and is_reparse(item):
            raise PathSafetyError(f"reparse point in target ancestry: {item}")


def contained(root: Path, relative: str, *, allow_missing: bool = True) -> Path:
    validate_relative(relative)
    root = root.absolute()
    candidate = root / PurePosixPath(relative)
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=not allow_missing)
        resolved.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PathSafetyError(f"path escapes target root: {relative}") from exc
    # Existing path and every existing ancestor are checked independently.
    current = candidate
    while current != root and current != current.parent:
        if current.exists() and is_reparse(current):
            raise PathSafetyError(f"reparse target: {relative}")
        current = current.parent
    return candidate
