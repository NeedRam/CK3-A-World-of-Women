# AWOW Universal Female Generation v1.0.0

- Added an independent Python/Tkinter and PowerShell transactional installer.
- Fresh install now requires exact hashes for the compatible AGP proxy,
  payload, and Steam original declared in `compatible_agp_builds`.
- Added stateful `managed_ufg` and `ufg_proxy_only` transitions.
- UFG uninstall removes only its payload/logs and leaves the active UFG proxy,
  Steam original, AGP payload, and AGP state unchanged.
- Added manual-layout adoption, managed upgrades, proxy-only re-enable,
  reparse/running-game guards, rollback, release checksums, and provenance.
- Added changed-hash UFG upgrades and the ordered disable-AGP replacement-UFG
  re-enable transition without trusting version labels alone.
- Fixed BAT package-root quoting so proxy-only re-enable, manual adoption, and
  managed reinstall confirmation arguments reach the PowerShell engine.
- Replaced typed UFG confirmation phrases with short, state-specific **OK** / **Cancel**
  questions in both graphical and BAT installer flows.
- Canonicalized displayed default paths to the filesystem's proper Windows,
  Steam, and Crusader Kings III capitalization.
- Pinned and enforced the native MSVC/Windows SDK toolchain, added PE identity
  metadata, canonical main-line provenance attestation, and packaged security,
  privacy, and signing policies.

This release targets CK3 `1.19.0.6` and is intentionally unsigned. Runtime
gameplay validation requires launching the user's CK3 installation and is not
performed by release assembly.
