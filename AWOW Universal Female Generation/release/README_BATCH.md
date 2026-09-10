# AWOW UFG v1.0.0 Batch File Installer

This package contains the AWOW Universal Female Generation batch/PowerShell
installer and uninstaller for Windows x64 with Steam Crusader Kings III
`1.19.0.6`. Install a compatible Any-Gender Parenthook release first.

## Install

1. Close Crusader Kings III and extract the entire ZIP.
2. Run `Install UFG.bat`.
3. Review the standard Steam path and confirm any requested safe transition.

The installer authorizes CK3 and AGP only by exact SHA-256 values. It preserves
Steam's original compiler, the AGP payload and state, and unknown files.

## Uninstall or disable UFG

Close CK3 and run `Uninstall UFG.bat`. It removes only the exact UFG payload
and named UFG logs. The active chained `dxcompiler.dll` remains unchanged so
AGP continues to load, and the resulting state is recorded as
`ufg_proxy_only`.

Keep the extracted folder together; the batch files require the `Installer`
folder and native files beside them. This release is intentionally unsigned.
`SHA256SUMS.txt` records the exact files in this package.
