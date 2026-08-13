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
