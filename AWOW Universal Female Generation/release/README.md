# UFG release tooling

Maintainers use `build-release.ps1` to assemble three unsigned Windows
packages:

- `AWOW UFG v1.0.0 Base Files (Manual Install).zip`
- `AWOW UFG v1.0.0 Batch File Installer.zip`
- `AWOW UFG v1.0.0 EXE Installer.zip`

Each archive contains only its selected installation method, the shared UFG
proxy/payload, a focused README, the MIT license, and internal checksums. The
builder excludes native test content, source, build staging, unrelated AWOW
modules, and repository metadata.

The canonical CI packages are produced on GitHub's `windows-2022` runner with
the pinned native toolchain in `toolchain.json`. Local output is a smoke-test
candidate and is labeled as such in provenance.
