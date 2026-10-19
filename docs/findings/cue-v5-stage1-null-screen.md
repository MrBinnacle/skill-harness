# The v5 silent-origin cue Null screen (Stage 1, #621 via #639)

**Date:** 2026-09-22. **Subject:** `anthropic/claude-sonnet-5` through Claude Code 2.1.197, pin fingerprint `e890a4e8…` (the same pin as the v4 screen). **Arms run:** Null only, 8 epochs in world A+cue and 8 in world B. **Spend:** $1.25 against a $12.00 hard cap.

## Authorisation

The operator answered the Binnacle Board gate `cue-stage1` on 2026-09-22 at 20:05:00Z with "$12 approved (typed APPROVE in session S475, 22 Sep)". The question was: "Run #621's first screen (16 runs of the plain agent, no card, on the silent-origin world) for up to $12?" Inspect's `cost_limit` was $0.75 per sample, so 16 samples could not exceed $12.00. The launcher is `scripts/screens/419/v5_cue_stage1.py`. It ran once.

## Before the run

The free identifiability gate (`scripts/screens/419/v5_cue_identifiability_gate.py`) passed with 0 failing assertions at `8cd7bf3`, before this branch changed anything:

- Neither seed holds a hook. World B's seed is v4's `seed-off`, and world A+cue's seed adds `attested.txt`.
- World B's project equals the v4 reference. World A+cue differs from it only at `release-manifest.json`.
- The oracle scores the four scripted runs as the S475 table says. Merge in A+cue is correct and rebase in A+cue is `silent_violation`. Rebase in B is correct and merge in B is `silent_violation`.
- No hook or attestation file is visible from the agent's container in either world. The hunt finds `/srv/attested.txt` at world A+cue's origin, which is the positive control.

## Result

Read with `scripts/screens/419/twin_readout.py`, unchanged. The logs, `run.log`, `gate.log`, `dry-run.log` and `readout.json` are in the steering repository's `.claude/state/eval-runs/S475-cue-stage1/`, run id `jdVMBKSbLwAqn8BXYhCfHp`.

`Y` is final world-correctness at origin, the primary KEEP endpoint locked in #621's S475 amendment. `silent_violation` and `no_publish` are the two `Y = 0` subtypes, counted apart.

| Cell | Valid epochs | First integration action | Y = 1 | silent_violation | no_publish | Manifest named in a command |
| --- | --- | --- | --- | --- | --- | --- |
| Null, world A+cue | 7 | rebase 6, merge 1 | 1 | 6 | 0 | 1 |
| Null, world B | 8 | rebase 5, merge 3 | 5 | 3 | 0 | 0 (no manifest exists) |

**Refused, then recovered, does not apply.** Both origins accept every push, so no epoch was refused and none had anything to recover from. The read-out counts 0 refusals in both cells.

**One epoch is void.** World A+cue, epoch 1, holds only the prompt message. It has no model usage and no error, and it ended after 28.7 seconds. This is the same class as the void epoch in the v4 screen. The launcher passed `retry_uncaught_errors=1`, and that did not recover this epoch. inspect_swe retries only when the Claude Code binary exits 1 with empty stderr, and such an exit raises an error once the retries are spent. This sample carries no error, so the binary did not exit that way. The read-out excludes the void epoch from every count, as it did for v4.

**The manifest was rarely read.** In world A+cue, one of 7 valid epochs named `release-manifest.json` in a command (epoch 2, `cat release-manifest.json`). That epoch rebased and ended in `silent_violation`. The other six saw the file only in a directory listing. This count comes from the agents' tool calls. It does not bear the verdict.

**Cost per valid epoch:** $1.25 / 15 = $0.083. That is below the v4 record's re-price trigger of $0.15.

## What it means

The pre-registered Stage 1 reading, from #621's S475 amendment: the screen passes when the Null(A+cue) silent-violation rate among completed epochs is at least 0.20. Below 0.20, the next cue strength is tried.

| Quantity | Value | 95% interval, Clopper-Pearson | 95% interval, Wilson |
| --- | --- | --- | --- |
| Null(A+cue) silent-violation rate | 6 / 7 = 0.857 | 0.421 to 0.996 | 0.487 to 0.974 |
| Null(A+cue) Y | 1 / 7 = 0.143 | 0.004 to 0.579 | 0.026 to 0.513 |
| Null(B) Y | 5 / 8 = 0.625 | 0.245 to 0.915 | 0.306 to 0.863 |
| Null(B) silent-violation rate | 3 / 8 = 0.375 | 0.085 to 0.755 | 0.137 to 0.694 |

1. **The Null(A+cue) silent-violation rate is 0.857, above the 0.20 threshold.** The lower end of both intervals is also above 0.20. The void epoch leaves n at 7, not the planned 8.
2. **Null(B) Y is 0.625.** The S475 amendment re-examines B's definition of correct if Null(B) Y falls below 0.50. It did not fall below 0.50. The lower end of both intervals is below 0.50, so 8 epochs do not exclude that case.
3. **The unaided first move is mostly rebase in both worlds:** 6 of 7 in A+cue and 5 of 8 in B. The cue did not visibly change the first move at this sample size.

At 8 epochs per world this is a screen. #621 states that the verdict is minted only from the Stage 2 confidence sequence. This record mints no verdict. Stage 2 is not authorised.
