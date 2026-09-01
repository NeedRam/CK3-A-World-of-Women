"""Best-effort Windows elevation helper used by packaged GUI front ends."""

from __future__ import annotations

import ctypes
import os
import sys
from typing import Sequence


def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin(arguments: Sequence[str] | None = None) -> int | None:
    """Run this executable with UAC and return its exit code, or ``None``.

    The caller decides whether to invoke this before showing a UI. No private
    credentials are handled or logged.
    """

    if is_admin() or os.name != "nt":
        return None
    args = list(arguments or sys.argv[1:])
    params = " ".join('"' + item.replace('"', '\\"') + '"' for item in args)
    executable = sys.executable
    try:
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    except OSError:
        return None
    if result <= 32:
        return 1
    return 0
