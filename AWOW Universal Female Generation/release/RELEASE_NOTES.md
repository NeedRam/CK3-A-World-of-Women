# AWOW Universal Female Generation v1.1.1

Targets Windows x64 CK3 1.21.0.3 and the frozen published UFG native v1.1.0
bytes. The installer accepts matching AGP state versions 1.1.0 and 1.1.1.
The previous UFG release remains separate for CK3 1.19.0.6.

- Re-audited runtime generation, gender-locked history assignment, and
  history marriage handling against the current executable.
- Classified the legacy direct site as manager restoration; leave it unpatched.
  Both explicit script requests and named templates use the live constructor.
- Rebuilt relays with current register/stack layouts and volatile XMM protection.
- Revalidated current-player, player-dynasty and requested-house exclusions;
  unknown origins and unavailable protection data preserve the requested gender.
- Restored the legacy Ruler Designer wrapper-caller exclusion before player
  registration, with native regression checks and an in-game male-ruler retest.
- Validate all 22 AGP modifications, including parent serialization, before UFG.
- Stage native changes transactionally with original-byte checks and rollback.
- Added UFG schema-v2 state/journals, legacy-state migration, and AGP v2-state support.
- Retain UFG-only ownership and proxy-only disable behavior.
- Package-only 1.1.1 installer update; native DLL pins and embedded native
  resource versions remain v1.1.0.
- Added native machine-code tests, binary auditing, and isolated manual fixtures.

All 12 required gameplay scenarios passed on CK3 1.21.0.3, including history
marriages, generation and player/dynasty exclusions, male Ruler Designer,
forced-male birth, parent roles, text and compressed save reloads, exit autosave,
and disabling UFG while AGP remains active. Automated validation includes 145
native checks, 48 executable audit checks, and 56 installer/profile tests.
See `validation.json` and the archived evidence. Public packages are produced
by the canonical CI workflow; local builds are identified in provenance.

AGP's currently published installers do not recognize this new UFG proxy/payload.
Use UFG's own uninstaller to disable UFG and keep AGP running. Updating AGP's
recognition of the final UFG hashes is a separate follow-up, outside this work.
