"""Build the two independent one-file Windows UFG front ends."""

from __future__ import annotations

import shutil
import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def build() -> None:
    pyinstaller = shutil.which("pyinstaller") or shutil.which("pyinstaller.exe")
    if not pyinstaller:
        raise SystemExit("PyInstaller is required; install from requirements-build.txt")
    for name, entry in (("UFGInstaller", "install_main.py"), ("UFGUninstaller", "uninstall_main.py")):
        env = os.environ.copy()
        # A locked per-user site-packages directory can make PyInstaller's
        # dependency scan fail before it reaches project code.
        env["PYTHONNOUSERSITE"] = "1"
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), str(ROOT / f"{name}.spec")], check=True, cwd=ROOT, env=env)
        built = ROOT / "dist" / f"{name}.exe"
        if not built.is_file():
            raise SystemExit(f"PyInstaller did not produce {built}")
        shutil.copy2(built, ROOT.parent / f"{name}.exe")


if __name__ == "__main__":
    build()
