# UFG release tooling

Maintainers use `build-release.ps1` to assemble three unsigned Windows
packages:

- `AWOW UFG v1.1.1 Base Files (Manual Install).zip`
- `AWOW UFG v1.1.1 Batch File Installer.zip`
- `AWOW UFG v1.1.1 EXE Installer.zip`

Each archive contains only its selected installation method, the shared UFG
proxy/payload, a focused README, the MIT license, and internal checksums. The
builder excludes native test content, source, build staging, unrelated AWOW
modules, and repository metadata.

The canonical CI packages are produced on GitHub's `windows-2022` runner from
the verified published native v1.1.0 archive; only the 1.1.1 installer EXEs
are rebuilt. Local output is a smoke-test candidate and is labeled as such in
provenance.

All 12 required CK3 1.21.0.3 gameplay scenarios passed, including the restored
Ruler Designer wrapper exclusion. See `validation.json` and its evidence files.

AGP installer recognition of these new UFG binaries is a separate follow-up; use this UFG release's uninstaller to disable UFG while retaining AGP.
