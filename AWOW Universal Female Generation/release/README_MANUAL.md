# AWOW UFG v1.1.0 Base Files (Manual Install)

This package contains only the AWOW Universal Female Generation native files
for manual installation on Windows x64 with Crusader Kings III
`1.21.0.3`. UFG requires Any-Gender Parenthook (AGP) and does not use a CK3
playset descriptor.

Use these steps only when AGP is already installed and the target files match
the exact supported hashes below:

- `ck3.exe`: `859f0d380098adcb130eb9d453458222749fcdf6d46126ad0ed99d78f9a0aa28`
- `dxcompiler.dll` (AGP v1.1.0 proxy): `e8365d61ffd80b4d8fcaf4d6d79ac00c8373831a0a86e66647a4fc1e4cef2e58`
- `dxcompiler_original.dll`: `40e381d1d0ccf3bd725e30914b07d3d0cdaa907900e4d194da0e9cbd41d06e65`
- `AGP Native Hook\agp_parenthook.dll`: `e6bb03805e7caa4392210fa45e3253de769d082ccd59087475a50c24b420071c`

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

To disable a manual UFG installation safely, obtain the EXE or batch package
and run its installer once to adopt the exact manual layout into managed state.
Then run that package's uninstaller. It removes UFG's payload and logs while
leaving the active chained proxy in place so AGP continues to load.

This release is intentionally unsigned. `SHA256SUMS.txt` records the exact
files in this package.

AGP installer recognition of these new UFG binaries is a separate follow-up; use this UFG release's uninstaller to disable UFG while retaining AGP.
