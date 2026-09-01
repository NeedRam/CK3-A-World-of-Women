"""Optional Tkinter GUI entry point for local development."""

import argparse

from ufg_installer.gui import run


parser = argparse.ArgumentParser()
parser.add_argument("operation", choices=("install", "uninstall"), default="install", nargs="?")
parser.add_argument("--package-root")
args = parser.parse_args()
raise SystemExit(run(args.operation, args.package_root))
