# Explicit spec for the independent UFG install EXE.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
hiddenimports = collect_submodules("ufg_installer")
a = Analysis([str(root / "install_main.py")], pathex=[str(root)], hiddenimports=hiddenimports, datas=[], binaries=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="UFGInstaller", console=False, uac_admin=True, version=str(root / "UFGInstaller.version.txt"))
