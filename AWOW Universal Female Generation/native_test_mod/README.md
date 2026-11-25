# UFG Native Test Mod

This is a disposable acceptance-test mod for AWOW Universal Female Generation. It is not required for normal play.

## Installation

Copy `UFG Native Test.mod` to the CK3 user `mod` directory and enable it in a test playset. The descriptor points to this source directory. Run it with the matching UFG and AGP native DLLs installed.

Disable AWOW CORE, AWOW Vanilla History OVERRIDES, AWOW Vanilla Male Source OVERRIDES, and unrelated gameplay mods while testing.

## Fixtures

The self-interactions are visible in debug mode when the actor targets herself:

- `UFG: Run History Tests` checks history gender and spouse relations.
- `UFG: Run Runtime Generation Tests` creates three unrelated male requests that must resolve female and one player-dynasty male that must remain male.
- `UFG: Prepare Forced-Male Child Birth Test` creates a pregnancy whose child must remain male at birth.

The history fixtures use the `ufg_native_history_*` character IDs. Test results are written to `debug.log` with `UFG_NATIVE_TEST_PASS`, `UFG_NATIVE_TEST_FAIL`, or `UFG_NATIVE_TEST_INFO` prefixes.

## Required checks

1. Start a new game and run the history and runtime interactions.
2. Confirm all unrelated generated characters are female and the player-dynasty fixture is male.
3. Create and finalize a male Ruler Designer character; confirm he remains male after entering the game.
4. Run the forced-male birth fixture and confirm the child remains male.
5. Save, reload, and confirm preserved males remain male.
6. Run the runtime interaction again after loading and inspect `debug.log`, `awow_ufg.log`, `error.log`, and `database_conflicts.log`.

## Isolated 1.21 acceptance

Use `tools/run-acceptance.ps1` from the UFG root with `-GameExecutable <ck3.exe>`.
The ignored `build/ck3-user` profile does not use ordinary user saves or playsets.
All in-game actions are user-operated; no computer-use automation is required.

1. With published AGP only, launch `-Mode baseline`, click **Create baseline male
   (AGP only)**, save the acceptance game, then exit. This writes `ufg_121_baseline`.
2. Install the UFG candidate and load that checkpoint using `-Mode reload
   -SaveName ufg_121_baseline`. Check the existing-save male, then runtime generation.
3. Launch `-Mode setup` for a fresh 1066 game. Check history/marriages and runtime
   generation, set up parent-role persistence, and prepare the forced-male birth.
4. Advance time until birth, check the result, and save `ufg_121_acceptance`.
5. Check saved roles after main-menu reload and after a process restart. Use
   `-NormalMode` for compressed exit-autosave coverage, then load it in debug mode.
6. Launch `-Mode menu` for a male Ruler Designer run and use its check button.
7. Disable UFG with its uninstaller, relaunch, and verify AGP-only behavior.

Controls show a result event and write `UFG_ACCEPTANCE_PASS/FAIL` markers. Missing
scopes fail explicitly. Reload checks never recreate the setup. Native generation
logs sample each supported origin and report unavailable player-protection data.
Read native/CK3 logs before accepting results; event text alone is insufficient.
The baseline's history males intentionally remain male when that save is loaded
with UFG: conversion applies to new history initialization, not existing saves.
