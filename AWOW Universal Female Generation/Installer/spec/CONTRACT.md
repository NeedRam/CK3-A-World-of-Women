# AWOW Universal Female Generation installer contract v1

The Python and PowerShell engines are independent implementations of the JSON
contract in this directory. They must make the same classification, ownership,
transition, and rollback decisions.

## Ownership boundary

UFG depends on an installed Any-Gender Parenthook (AGP). A compatible AGP
installation is recognized only when the CK3 executable and every dependency
hash listed in
`compatible_agp_builds` matches. Version labels are descriptive; SHA-256 is
the compatibility authority. UFG replaces the active AGP proxy path only as an
owned UFG installation step; it never changes `dxcompiler_original.dll`, the
AGP payload, or AGP state.

UFG owns only the active UFG proxy replacement, the
`AWOW Universal Female Generation/awow_ufg.dll` payload, its two named logs,
its state file, and its transaction directories. Unknown files are preserved.

## States and transitions

- `agp_ready`: exact compatible AGP is installed and no UFG state/payload is
  present. Fresh UFG installation is allowed.
- `manual_ufg`: exact UFG proxy/payload/AGP layout without UFG state. Explicit
  `ADOPT_UFG_LAYOUT` creates state without touching AGP.
- `managed_ufg`: UFG state is valid and every recorded UFG hash and AGP
  dependency hash still matches. Upgrade requires `UPGRADE_UFG_IN_PLACE`.
- `ufg_proxy_only`: uninstall has removed the UFG payload. The active file may
  be the state-owned UFG proxy, or the newly compatible standalone AGP proxy
  after an AGP replacement. Same-release re-enable requires `RE_ENABLE_UFG`.
  Replacing an older state-owned UFG proxy with a new UFG release requires
  `UPGRADE_UFG_IN_PLACE`; uninstall is a no-op.
- `unknown_conflicting`: any drift, incompatible AGP, invalid state, or
  ambiguous layout. Install and uninstall refuse without mutation.

## Transaction protocol

Each mutating operation validates CK3 is closed, rejects reparse points and
escaping paths, reads all expected hashes, snapshots UFG-owned targets, writes
the journal, stages artifacts, mutates only UFG-owned paths, verifies hashes and
state, and commits by removing the journal. A failure restores the snapshot;
an unverifiable rollback retains the journal and reports manual recovery.

Uninstall is intentionally asymmetric: it removes the exact UFG payload and
named UFG logs, writes `ufg_proxy_only`, and leaves active UFG
`dxcompiler.dll`, `dxcompiler_original.dll`, AGP payload/state, and unknown
files byte-for-byte unchanged.

An AGP version transition is intentionally ordered: disable UFG, install the
new AGP so its standalone proxy replaces the old version-coupled UFG proxy,
then run the UFG release whose manifest exactly lists the new CK3/AGP hashes.
Only a valid old `ufg_proxy_only` state plus an exact incoming AGP candidate can
authorize this rebase; ambiguous or drifted layouts remain untouched.

## Package boundary

The release package contains only the UFG proxy/payload, installer engines,
contracts, tests needed for audit, and end-user documentation/launchers. The
native test mod, source, build staging, repository metadata, and unrelated
AWOW modules are excluded. `SHA256SUMS.txt`, the adjacent ZIP checksum, and
provenance identify the exact staged bytes.
