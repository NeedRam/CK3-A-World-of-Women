"""Steam library discovery and explicit target selection.

Discovery is deliberately advisory: callers must still show the selected
target and the core engine performs all containment and compatibility checks.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


APP_ID = "1158310"
GAME_DIRECTORY = "Crusader Kings III"
EXECUTABLE_NAME = "ck3.exe"


@dataclass(frozen=True)
class SteamTarget:
    """A discovered CK3 binaries directory and its Steam library origin."""

    binaries: Path
    library: Path
    source: str


def canonical_existing_path(path: Path) -> Path:
    """Return the filesystem's on-disk capitalization when the path exists."""

    try:
        return path.resolve() if path.exists() else path
    except OSError:
        return path


def standard_steam_executable() -> Path:
    """Return the conventional Program Files Steam CK3 executable path."""

    roots = [
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
    ]
    for value in roots:
        if value:
            return canonical_existing_path(Path(value) / "Steam" / "steamapps" / "common" / GAME_DIRECTORY / "binaries" / EXECUTABLE_NAME)
    # This is primarily a deterministic fallback for environments without the
    # Windows Program Files variables (for example, test runners).
    return Path(r"C:\Program Files (x86)") / "Steam" / "steamapps" / "common" / GAME_DIRECTORY / "binaries" / EXECUTABLE_NAME


def default_target(options: Iterable[SteamTarget] | None = None) -> Path:
    """Return the best initial GUI target as an executable path."""

    values = list(options if options is not None else discover_steam_targets())
    if values:
        return canonical_existing_path(values[0].binaries / EXECUTABLE_NAME)
    return standard_steam_executable()


def _registry_steam_paths() -> list[Path]:
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []
    keys = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
    )
    paths: list[Path] = []
    for hive, subkey in keys:
        for access in (getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)):
            try:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | access) as key:
                    value, _ = winreg.QueryValueEx(key, "SteamPath")
                    if value:
                        paths.append(Path(os.path.expandvars(str(value))))
            except (FileNotFoundError, OSError):
                continue
    return _unique_paths(paths)


def parse_libraryfolders(text: str) -> list[Path]:
    """Extract Steam library paths from both old and new VDF layouts.

    Steam's file is a small quoted key/value format rather than strict JSON.
    Only values for a ``path`` key are accepted; arbitrary strings in the file
    are never treated as filesystem roots.
    """

    found: list[Path] = []
    for match in re.finditer(r'"(?:path|\d+)"\s+"((?:\\.|[^"\\])*)"', text, re.IGNORECASE):
        raw = match.group(1).replace(r'\\', "\\").replace(r'\"', '"')
        candidate = Path(raw)
        if candidate.is_absolute() and (candidate not in found):
            found.append(candidate)
    return _unique_paths(found)


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = os.path.normcase(str(path.resolve()))
        except OSError:
            key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def discover_steam_targets(
    registry_paths: Iterable[Path] | None = None,
    filesystem_exists: Callable[[Path], bool] = lambda p: p.is_dir(),
) -> list[SteamTarget]:
    """Return existing CK3 binaries directories from Steam libraries."""

    roots = list(registry_paths) if registry_paths is not None else _registry_steam_paths()
    libraries: list[tuple[Path, str]] = []
    for root in roots:
        root = Path(root)
        libraries.append((root, "registry"))
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            libraries.extend((path, "libraryfolders.vdf") for path in parse_libraryfolders(vdf.read_text(encoding="utf-8")))
        except (OSError, UnicodeError):
            pass
    result: list[SteamTarget] = []
    seen: set[str] = set()
    for library, source in libraries:
        binaries = library / "steamapps" / "common" / GAME_DIRECTORY / "binaries"
        if filesystem_exists(binaries):
            binaries = canonical_existing_path(binaries)
            library = canonical_existing_path(library)
            key = os.path.normcase(str(binaries.resolve()))
            if key not in seen:
                seen.add(key)
                result.append(SteamTarget(binaries=binaries, library=library, source=source))
    return result


def select_target(
    manual: str | os.PathLike[str] | None = None,
    discovered: Iterable[SteamTarget] | None = None,
    chooser: Callable[[list[SteamTarget]], SteamTarget | str | os.PathLike[str] | None] | None = None,
) -> Path | None:
    """Choose a target explicitly, optionally using a UI chooser callback.

    A manually supplied path may be either the ``binaries`` directory or the
    CK3 game directory. No path is silently selected when multiple libraries
    are discovered and no chooser/manual path was supplied.
    """

    if manual is not None:
        path = Path(manual).expanduser()
        if path.name.casefold() == EXECUTABLE_NAME:
            path = path.parent
        elif path.name.casefold() in ("crusader kings iii", "crusader_kings_iii"):
            path = path / "binaries"
        elif path.name.casefold() != "binaries":
            candidate = path / "binaries"
            if candidate.is_dir():
                path = candidate
        return path
    options = list(discovered if discovered is not None else discover_steam_targets())
    if chooser is None:
        return options[0].binaries if len(options) == 1 else None
    selected = chooser(options)
    if selected is None:
        return None
    return selected.binaries if isinstance(selected, SteamTarget) else Path(selected)
