# Code signing policy

AWOW Universal Female Generation `v1.0.0` is intentionally unsigned. SHA-256
checksums and GitHub build-provenance attestations identify its release ZIP;
the project does not create or claim an Authenticode signature for this
version.

## Release authority and provenance

The canonical artifact is built by `.github/workflows/ufg-release.yml` from a
commit reachable from `main`. Native compilation is pinned by `toolchain.json`,
bundled as `BUILD_TOOLCHAIN.json`, to GitHub's `windows-2022` runner, MSVC
`14.44.35207`, Windows SDK `10.0.22621.0`, and an x64 host/target. The build
fails if those exact native tools cannot be selected.

Repository DLLs and locally assembled ZIPs are developer outputs, not release
authority. Local provenance is labeled `local_smoke_test`; only the artifact
emitted by the canonical GitHub Actions job may be attached to a release.

Canonical assembly regenerates staged DLL hashes and sizes before producing
`SHA256SUMS.txt`, the ZIP checksum, provenance JSON, and GitHub attestation.

## Future signing

A future release may add a reviewed code-signing service. Any such integration
must retain source-origin verification, protected approval, pinned tools,
post-signing hash publication, and signature verification. Private keys,
passwords, and signing credentials must never be stored in this repository or
requested by the installer. A later signed release must use a new version and
must not relabel `v1.0.0` as signed.
