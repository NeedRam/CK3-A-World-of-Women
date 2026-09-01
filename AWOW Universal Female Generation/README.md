# AWOW Universal Female Generation - Native Hook

This directory is the native runtime component of AWOW Universal Female Generation (UFG). It contains the DXCompiler proxy loader, the UFG payload DLL, and a disposable CK3 test mod.

UFG runs below the CK3 script layer. It replaces the requested gender on supported history and character-generation paths, so script load order does not determine whether an eligible character is female.

## What it provides

The payload changes the CK3 character paths currently required by UFG:

- Character-history gender assignment
- Direct and template-based character generation
- Pool, court, spouse, commander, and government character generation that uses those constructors
- History `add_spouse` and `add_matrilineal_spouse` handling through CK3's same-sex spouse relation mode

UFG preserves births, save reconstruction, human-controlled characters, characters in any current player's dynasty, and Ruler Designer characters. It does not convert characters already present in a loaded save.

AWOW CORE remains responsible for birth gender and culling. UFG does not require AWOW CORE.

## Compatibility

The current signatures and absolute code addresses target the 64-bit CK3 `1.19.0.6` executable with SHA-256 `2D00FF3101EF70B566F2FCBAE292F09263199C80E9DC8F139B82D7D96F83DB86`. Treat other CK3 versions as unsupported until the signatures and hardcoded addresses have been re-verified.

UFG requires the unchanged Any-Gender Parenthook payload. Its loader starts `AGP Native Hook\agp_parenthook.dll`, waits for every expected AGP patch, and loads UFG only after AGP is ready. A missing UFG payload leaves AGP active. A missing, timed-out, or partially patched AGP installation prevents UFG from loading.

The payload performs a signature preflight before writing patches. If a preflight check fails, it logs the failure and makes no patch writes. A failure during the write phase can leave the process partially patched; do not continue a session after a reported write failure.

## Runtime architecture

The loader uses CK3's shipped `dxcompiler.dll` proxy route:

1. The original game `dxcompiler.dll` is renamed to `dxcompiler_original.dll`.
2. The UFG-built `dxcompiler.dll` takes the original filename and exports `DxcCreateInstance` and `DxcCreateInstance2`.
3. Those exports are forwarded to the untouched original DXCompiler DLL.
4. A background loader thread loads `AGP Native Hook\agp_parenthook.dll`.
5. After the AGP patches are present, the loader loads `AWOW Universal Female Generation\awow_ufg.dll`.
6. The UFG payload scans CK3's `.text` section, performs preflight, and applies its native patches.

## Source layout

```text
AWOW Universal Female Generation\
  build.ps1                         # Builds the loader and payload
  dxcompiler_proxy.def              # DXCompiler proxy exports
  src\
    ufg_generation_hook.cpp         # DLL entrypoint and patch coordinator
    ufg_patch_runtime.cpp/.h        # Scanning, memory writes, branches, hashing, logging
    ufg_generation.cpp/.h           # Runtime generation and player exclusions
    ufg_history.cpp/.h              # History gender and spouse handling
    ufg_dxcompiler_loader.cpp        # DXCompiler proxy and AGP-dependent loader
  native_test_mod\                  # Disposable acceptance-test mod
  build\                            # Build outputs
```

`ufg_generation_hook.cpp` only coordinates the modules and owns the DLL entrypoint. Runtime character generation and history loading remain in separate translation units.

## Building

Requirements:

- Windows x64
- Visual Studio 2022 x64 C++ build tools
- The exact MSVC and Windows SDK versions declared in `toolchain.json`
- The UFG Native Hook source tree

From this directory, run:

```powershell
.\build.ps1
```

The script selects Visual Studio through `vswhere` (or an explicit
`-VcVarsAllPath`), passes the pinned versions to `vcvarsall.bat`, and fails if
the resulting MSVC or Windows SDK environment differs from `toolchain.json`.

The build produces:

```text
build\dxcompiler.dll
build\AWOW Universal Female Generation\awow_ufg.dll
```

The script builds all payload translation units as one DLL, builds the DXCompiler proxy separately, and removes compiler intermediates from `build\` after a successful build.

## Installation for maintainer testing

Install Any-Gender Parenthook first, then close CK3 before changing the game binaries. For the packaged workflow, run `UFG-Installer.exe` (or `Install UFG.bat`) from the release package; it verifies the exact CK3, Steam-original, AGP proxy, and AGP payload hashes before changing anything. The CK3 `binaries` directory must already contain the untouched original DXCompiler and AGP payload:

```text
Crusader Kings III\binaries\
  ck3.exe
  dxcompiler_original.dll
  AGP Native Hook\
    agp_parenthook.dll
```

Copy the two UFG build outputs into the same directory:

```text
Crusader Kings III\binaries\
  dxcompiler.dll
  AWOW Universal Female Generation\
    awow_ufg.dll
```

Installing UFG replaces only AGP's proxy `dxcompiler.dll`. Do not replace `dxcompiler_original.dll` or `AGP Native Hook\agp_parenthook.dll`.

UFG has no launcher descriptor and is not enabled in a CK3 playset. Disable **AWOW Vanilla History OVERRIDES** and **AWOW Vanilla Male Source OVERRIDES** while UFG is installed.

To disable UFG while keeping AGP, close CK3 and run `UFG-Uninstaller.exe` (or `Uninstall UFG.bat`). The transactional uninstaller removes only the UFG payload and named UFG logs, leaves the active UFG proxy byte-for-byte unchanged, and records the `ufg_proxy_only` state so AGP continues loading by itself.

For a UFG-only upgrade against the same compatible AGP pairing, use the new
UFG installer, review its short upgrade explanation, and choose **OK**. To change AGP versions,
disable UFG first, run the new release's `AGP-Installer.exe` so its standalone
proxy replaces the old UFG proxy, then install the UFG release whose manifest lists the new
CK3/AGP hashes. AGP v1.0.1 predates the UFG v1.0.0 proxy hash and therefore
classifies that proxy-only handoff as `unknown_conflicting`; after verifying the
UFG payload is absent and the preserved compiler/AGP payload hashes are intact,
use AGP's displayed `I_UNDERSTAND_UNKNOWN_CONFLICT` confirmation to restore its
standalone proxy. Do not preserve an old UFG proxy across an AGP upgrade.

## Logs and failure handling

Both DLLs write logs beside `ck3.exe`:

- `awow_ufg_dxcompiler_loader.log` - original DXCompiler loading, AGP loading, AGP patch readiness, and UFG loading
- `awow_ufg.log` - UFG signature, patch, and module results

If the loader reports partial AGP patching or the payload reports a write failure, exit CK3 without saving and preserve the logs.

## Test mod

`native_test_mod\` is a disposable standalone CK3 test mod. It contains targeted history fixtures, interactions, an on-action extension, and localization for checking UFG without AWOW CORE, VHO, or VMSO.

The fixtures cover:

- Explicit-male and unspecified history characters
- History spouse command conversion
- Direct, chance-based, and template character generation
- Player-dynasty preservation
- Forced-male birth preservation
- Save and reload preservation

See [`native_test_mod\README.md`](native_test_mod/README.md) for installation and fixture details. A successful DLL build is not gameplay validation; run the relevant fixtures on the matching CK3 version before publishing.

## Validation standard

For a new CK3 build or a substantial payload change:

1. Confirm the C++ payload and DXCompiler proxy build cleanly.
2. Confirm every signature resolves exactly as expected and inspect both UFG logs.
3. Start CK3 with the disposable test mod and inspect `error.log` and `database_conflicts.log`.
4. Run the history, runtime-generation, player-dynasty, birth, and Ruler Designer checks.
5. Save, reload, and repeat the generation and preserved-male checks.
6. Record the exact CK3 executable version before publishing.
