"""Tkinter front end that delegates all safety decisions to :mod:`core`."""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from .core import ConfirmationRequest, InstallError, Installer, Result
from .discovery import canonical_existing_path, default_target, discover_steam_targets, select_target


_WINDOWS_DRIVE_PREFIX = re.compile(r"^([A-Za-z]):")


def normalize_display_path(value: str) -> str:
    """Use on-disk capitalization and an uppercase Windows drive prefix."""

    value = str(canonical_existing_path(Path(value)))
    return _WINDOWS_DRIVE_PREFIX.sub(lambda match: f"{match.group(1).upper()}:", value, count=1)


def _result_message(result: Result) -> str:
    """Return a user-facing result without claiming success for non-commits."""

    successful_states = {"install": "managed_ufg", "uninstall": "ufg_proxy_only"}
    if result.operation in successful_states and result.decision == "proceed" and result.next_state == successful_states[result.operation]:
        return {
            "install": "AWOW Universal Female Generation installed successfully.",
            "uninstall": "UFG payload disabled; the active UFG proxy remains unchanged and continues loading AGP alone.",
        }[result.operation]
    details = f"{result.operation}: {result.decision}"
    return f"{details}\n{result.message}".strip() if result.message else details


def _ask_confirmation(request: ConfirmationRequest, parent: tk.Misc | None = None) -> bool:
    return messagebox.askokcancel(request.title, request.message, icon="question", default=messagebox.CANCEL, parent=parent)


def _browse_for_target(parent: tk.Misc, target_var: tk.StringVar) -> None:
    """Select an executable and put its full path into the editable field."""

    current = target_var.get().strip()
    initial = str(Path(current).parent) if current else str(default_target().parent)
    selected = filedialog.askopenfilename(
        parent=parent,
        title="Select Crusader Kings III executable",
        initialdir=initial,
        filetypes=(("Crusader Kings III executable", "ck3.exe"), ("Executable files", "*.exe"), ("All files", "*.*")),
    )
    if not selected:
        return
    if Path(selected).name.casefold() != "ck3.exe":
        messagebox.showerror("Invalid CK3 executable", "Select the Crusader Kings III executable named ck3.exe.", parent=parent)
        return
    target_var.set(normalize_display_path(selected))


def _run_operation(root: tk.Misc, operation: str, package_root: str | None, target_text: str) -> int:
    """Run one operation after the user submits the path field."""

    if not target_text.strip():
        messagebox.showerror("Missing CK3 path", "Enter the path to ck3.exe or its binaries directory.", parent=root)
        return 2
    selected = select_target(target_text.strip())
    if selected is None:
        messagebox.showerror("Missing CK3 path", "Select a CK3 installation before continuing.", parent=root)
        return 2
    engine = Installer(package_root=package_root)
    try:
        classification = engine.classify(Path(selected))
        request = engine.install_confirmation(selected, classification) if operation == "install" else None
        if request and not _ask_confirmation(request, root):
            return 2
        confirmation = request.token if request else None
        result = engine.install(selected, confirmation) if operation == "install" else engine.uninstall(selected, confirmation)
        messagebox.showinfo("AWOW Universal Female Generation", _result_message(result), parent=root)
        return 0 if result.decision in ("proceed", "no_op") else 1
    except InstallError as exc:
        messagebox.showerror("AWOW Universal Female Generation", str(exc), parent=root)
        return 1


def _close(root: tk.Misc, result: dict[str, int], code: int = 2) -> None:
    result["code"] = code
    root.destroy()


def run(operation: str = "install", package_root: str | None = None) -> int:
    root = tk.Tk()
    options = discover_steam_targets()
    root.title(f"AWOW Universal Female Generation - {'Install' if operation == 'install' else 'Uninstall'}")
    root.minsize(720, 170)
    root.columnconfigure(0, weight=1)
    frame = tk.Frame(root, padx=16, pady=16)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    tk.Label(frame, text="Crusader Kings III executable or path:").grid(row=0, column=0, columnspan=2, sticky="w")
    target_var = tk.StringVar(root, value=normalize_display_path(str(default_target(options))))
    entry = tk.Entry(frame, textvariable=target_var, width=90)
    entry.grid(row=1, column=0, padx=(0, 8), pady=(6, 12), sticky="ew")
    tk.Button(frame, text="Browse...", command=lambda: _browse_for_target(root, target_var)).grid(row=1, column=1, pady=(6, 12))
    result = {"code": 2}
    action = "Install" if operation == "install" else "Uninstall"
    tk.Button(frame, text=action, command=lambda: _close(root, result, _run_operation(root, operation, package_root, target_var.get()))).grid(row=2, column=0, columnspan=2, sticky="e")
    root.protocol("WM_DELETE_WINDOW", lambda: _close(root, result))
    entry.focus_set()
    root.mainloop()
    return result["code"]
