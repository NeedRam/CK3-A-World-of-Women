# AWOW UFG v1.0.0 Base Files (Manual Install)

This package contains only the AWOW Universal Female Generation native files
for manual installation on Windows x64 with Steam Crusader Kings III
`1.19.0.6`. UFG requires Any-Gender Parenthook (AGP) and does not use a CK3
playset descriptor.

Use these steps only when AGP is already installed and the target files match
the exact supported hashes below:

- `ck3.exe`: `2d00ff3101ef70b566f2fcbae292f09263199c80e9dc8f139b82d7d96f83db86`
- `dxcompiler.dll` (AGP proxy): `7c266520db764c7c334a610b8d975241671273c45a90157548a47ec2af732bb0`
- `dxcompiler_original.dll`: `40e381d1d0ccf3bd725e30914b07d3d0cdaa907900e4d194da0e9cbd41d06e65`
- `AGP Native Hook\agp_parenthook.dll`: `9a75b00582261e3af75d262e68dbd858a88e20888e81b127b84dc2e87348ee52`

For upgrades, an existing UFG installation, or any hash mismatch, use the EXE
or batch installer package instead.

## Install

1. Close Crusader Kings III.
2. Open the game's `binaries` folder.
3. Copy this package's `dxcompiler.dll` over the verified AGP proxy. Do not
   change `dxcompiler_original.dll`.
4. Copy the entire `AWOW Universal Female Generation` folder into `binaries`.
   The final payload path must be
   `binaries\AWOW Universal Female Generation\awow_ufg.dll`.
5. Start CK3 and inspect `awow_ufg_dxcompiler_loader.log` and `awow_ufg.log`.

To disable a manual UFG installation safely, use the uninstaller from the EXE
or batch package. It removes UFG's payload and logs while leaving the active
chained proxy in place so AGP continues to load.

This release is intentionally unsigned. `SHA256SUMS.txt` records the exact
files in this package.
