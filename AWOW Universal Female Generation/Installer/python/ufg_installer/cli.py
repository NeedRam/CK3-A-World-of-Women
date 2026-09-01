"""Command-line front end for the independently built UFG EXEs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .core import InstallError, Installer
from .discovery import discover_steam_targets, select_target


def build_parser(operation: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="UFGInstaller" if operation == "install" else "UFGUninstaller" if operation == "uninstall" else "ufg-installer")
    parser.add_argument("operation", nargs="?", choices=("install", "uninstall", "discover"), default=operation)
    parser.add_argument("--target", help="CK3 executable, binaries directory, or CK3 game directory")
    parser.add_argument("--package-root", help="unpacked UFG release root")
    parser.add_argument("--confirmation", help="exact safety confirmation token")
    parser.add_argument("--json", action="store_true", help="emit machine-readable result")
    return parser


def _result_json(result: object) -> dict[str, object]:
    return {key: str(value) if isinstance(value, Path) else value for key, value in vars(result).items()}


def main(operation: str | None = None, argv: list[str] | None = None) -> int:
    args = build_parser(operation).parse_args(argv)
    if args.operation == "discover":
        values = [{"binaries": str(item.binaries), "library": str(item.library), "source": item.source} for item in discover_steam_targets()]
        print(json.dumps(values, indent=2))
        return 0 if values else 1
    if not args.operation:
        build_parser(operation).print_help()
        return 2
    target = select_target(args.target)
    if target is None:
        print("No target selected. Use --target or choose a Steam library in the GUI.", file=sys.stderr)
        return 2
    try:
        engine = Installer(package_root=args.package_root)
        result = engine.install(target, args.confirmation) if args.operation == "install" else engine.uninstall(target, args.confirmation)
    except InstallError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload = _result_json(result)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{result.operation}: {result.decision} ({result.classification} -> {result.next_state})")
        if result.message:
            print(result.message)
    return 0 if result.decision in ("proceed", "no_op") else 1
