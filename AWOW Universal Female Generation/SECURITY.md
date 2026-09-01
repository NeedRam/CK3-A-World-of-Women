# Security policy

## Supported release

The current release targets the Windows x64 Steam build of Crusader Kings III
`1.19.0.6` and the exact AGP `v1.0.1` files identified by SHA-256 in
`Installer/release-manifest.json`. Do not bypass a compatibility refusal for a
different game or AGP build.

The installer validates path containment, reparse points, process state,
ownership state, and hashes before mutation. Unknown files are preserved. UFG
never changes `dxcompiler_original.dll`, the AGP payload, or AGP state, and its
uninstaller deliberately leaves the active UFG proxy unchanged.

## Reporting a vulnerability

Report suspected security issues privately through the repository's private
security-reporting or maintainer contact channel. Include the UFG, AGP,
Windows, and CK3 versions, reproduction steps, and relevant installer/runtime
log excerpts. Do not attach saves, credentials, keys, or other personal data
unless they are specifically necessary.

Do not weaken hash checks, path safety, transaction journals, or rollback to
work around an installation failure.

## Scope

The UFG installer, chained DXCompiler loader, and UFG payload are in scope.
CK3, Steam, AGP itself, and third-party mods are maintained separately.
