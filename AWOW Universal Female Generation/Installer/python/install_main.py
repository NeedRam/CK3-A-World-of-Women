"""PyInstaller entry point for the independent UFG graphical installer."""

import sys

from ufg_installer.cli import main
from ufg_installer.core import frozen_package_root
from ufg_installer.gui import run


if __name__ == "__main__":
    package_root = frozen_package_root()
    if len(sys.argv) > 1:
        arguments = list(sys.argv[1:])
        if package_root and "--package-root" not in arguments:
            arguments.extend(["--package-root", str(package_root)])
        raise SystemExit(main("install", arguments))
    raise SystemExit(run("install", str(package_root) if package_root else None))
