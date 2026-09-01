# Explicit spec for the independent UFG uninstall EXE.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
hiddenimports = collect_submodules("ufg_installer")
a = Analysis([str(root / "uninstall_main.py")], pathex=[str(root)], hiddenimports=hiddenimports, datas=[], binaries=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="UFGUninstaller", console=False, uac_admin=True, version=str(root / "UFGUninstaller.version.txt"))
