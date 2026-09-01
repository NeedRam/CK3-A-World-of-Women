# UFG release tooling

Maintainers use `build-release.ps1` to assemble the unsigned Windows package.
The script stages only the UFG proxy/payload, installer contracts and
entrypoints, documentation, and checksums. It excludes native test content,
source, build staging, unrelated AWOW modules, and repository metadata.

The canonical CI package is produced on GitHub's `windows-2022` runner with
the pinned native toolchain in `toolchain.json`. Local output is a smoke-test
candidate and is labeled as such in provenance.
