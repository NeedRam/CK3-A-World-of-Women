# AWOW Universal Female Generation v1.0.0

This is the unsigned Windows x64 UFG package for Steam Crusader Kings III
`1.19.0.6`. UFG is an optional native payload that runs behind a compatible
Any-Gender Parenthook (AGP) installation. Keep the extracted folder together.

## Install

1. Close Crusader Kings III.
2. Install the exact compatible AGP release first. UFG checks AGP's proxy,
   payload, and preserved Steam compiler by SHA-256; a version label alone is
   not sufficient.
3. Extract this ZIP and run `UFG-Installer.exe`, or use `Install UFG.bat` for
   the standard Steam location.
4. Confirm the selected `ck3.exe` path. When UFG finds an existing installation,
   review the short explanation and choose **OK** to continue or **Cancel** to
   leave everything unchanged.

On a fresh install UFG replaces only active `dxcompiler.dll` with its chained
proxy and installs `AWOW Universal Female Generation/awow_ufg.dll`. It never
replaces `dxcompiler_original.dll`, the AGP payload, or AGP state. UFG does
not use a CK3 playset descriptor; disable AWOW history/male-source override
mods when using native UFG history generation.

## Manual installation (advanced users)

Use this only when the target already has the exact compatible AGP layout:

```text
Crusader Kings III\binaries\
  ck3.exe
  dxcompiler.dll                 (AGP proxy)
  dxcompiler_original.dll        (Steam original)
  AGP Native Hook\
    agp_parenthook.dll
```

1. Close CK3.
2. Copy the package `dxcompiler.dll` over the active AGP proxy only after
   verifying the SHA-256 in `Installer/release-manifest.json`.
3. Copy `AWOW Universal Female Generation/awow_ufg.dll` to the same relative
   path below `binaries`.
4. Start CK3 and inspect `awow_ufg_dxcompiler_loader.log` and `awow_ufg.log`.

If a backup already exists, another proxy is installed, files have drifted,
or you are upgrading/converting a layout, use `UFG-Installer.exe`. Never
overwrite or delete the original compiler or AGP payload.

## Uninstall / disable UFG

Run `UFG-Uninstaller.exe`, or use `Uninstall UFG.bat`. The transactional
uninstaller removes only the exact UFG payload and the two named UFG logs. It
leaves the active UFG `dxcompiler.dll` proxy byte-for-byte unchanged and
records `ufg_proxy_only`, so it continues loading AGP alone. The Steam
original, AGP payload, AGP state, and unknown files are left unchanged.

If a state or dependency hash has drifted, the uninstaller refuses to guess;
resolve the installation manually and preserve the journal/quarantine data.

## Upgrading AGP or UFG

For a UFG-only upgrade whose manifest still lists the installed AGP hashes,
run the new UFG installer, review the upgrade explanation, and choose **OK**.
It verifies the old state-owned UFG bytes before replacing both UFG artifacts.

For an AGP upgrade, use this order:

1. Disable UFG with the UFG uninstaller.
2. Run the new release's `AGP-Installer.exe` so its standalone proxy replaces
   the old, version-coupled UFG proxy. AGP v1.0.1 predates this UFG v1.0.0 proxy hash,
   so it reports the proxy-only layout as `unknown_conflicting`; after
   verifying UFG is disabled and the preserved compiler/AGP payload hashes are
   unchanged, enter its displayed `I_UNDERSTAND_UNKNOWN_CONFLICT` confirmation.
3. Run the UFG release whose manifest exactly lists the new CK3 and AGP hashes,
   then review the re-enable explanation and choose **OK**.

Do not carry the old UFG proxy across an AGP version change. Reinstall AGP at
any time if you want its standalone proxy instead of UFG's chained proxy.

## Scope and verification

The package excludes the native test mod, source, build staging, repository
metadata, and unrelated AWOW modules. Verify the adjacent ZIP `.sha256` file
and the included `SHA256SUMS.txt`. Version 1.0.0 is intentionally unsigned.
See `SECURITY.md`, `PRIVACY.md`, and `SIGNING.md` for the packaged policies and
canonical-build details.
