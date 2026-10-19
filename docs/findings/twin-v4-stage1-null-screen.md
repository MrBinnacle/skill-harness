# The v4 twin Null screen (Stage 1, #620)

**Date:** 2026-09-22. **Subject:** `anthropic/claude-sonnet-5` through Claude Code 2.1.197, pin fingerprint `e890a4e8…`. **Arms run:** Null only, 8 epochs in each world. **Spend:** $1.76 against a $12.00 hard cap.

## Authorisation

The operator answered the Binnacle Board gate `twin-stage1` on 2026-09-22 at 07:26:30Z with "$12 approved". The question was: "Run the first twin-world screen (Stage 1: 16 runs of the plain agent, no card) for up to $12?" Inspect's `cost_limit` was $0.75 per sample, so 16 samples could not exceed $12.00.

## Before the run

The free identifiability gate (`scripts/screens/419/v4_identifiability_gate.py`) passed 9 of 9 at `d0ff304`, the same result it gave when it was merged. In world A, merge is correct and rebase is refused. In world B, the reverse holds. No hook or attestation file is visible from the agent's container, and the visible digests match (`d617f06d…`).

## Result

Read with `scripts/screens/419/twin_readout.py`. Logs and `readout.json` are in the steering repository's `.claude/state/eval-runs/S473-twin-stage1/`, run id `UEfX5wJp2nGfCnn5k3NeRH`.

| Cell | Valid epochs | First integration action | Ends correct | Refused, then recovered | Silent violation |
| --- | --- | --- | --- | --- | --- |
| Null, world A | 8 | merge 3, rebase 5 | 8 | 5 | 0 |
| Null, world B | 7 | merge 2, rebase 5 | 7 | 2 | 0 |

**One epoch is void.** World B, epoch 8, holds only the prompt message, with no model usage and no error. The agent never started. This matches inspect_swe's documented case where the Claude Code binary exits with empty stderr. The oracle still scored it `C`, because the fact script always exits 0. The read-out now marks an epoch with no model usage as void and leaves it out of every count. The Stage 2 launcher should pass `retry_uncaught_errors`, which `build_paired_tasks` already accepts, to recover such epochs in place.

**Cost per valid epoch:** $0.117 realised, against the $0.152 the pricing record assumed (v3a × 1.5). That is below the record's re-price trigger of $0.15.

## What it means

1. **The unaided first move is mostly rebase.** p_N(merge first) = 5 / 15 = 0.33, pooled over both worlds. The two worlds agree (3 of 8 and 2 of 7), which is what identical visible surfaces predict. A shift of 0.20 in either direction is possible on this quantity.
2. **Every refused agent recovered.** All 7 refusals were read and followed by the correct action, and all 15 valid epochs end in the correct world state. The hook's rejection text is enough for an unaided agent to recover. So on the final outcome, Null sits at the ceiling in both worlds.
3. **The adopted headroom gate fails, while the adopted primary estimand has headroom.** The rule adopted in S472 sets the gate on Null(A) correctness ≤ 0.80, and it came back at 8 / 8. By that rule, the positive-lift question is CANT_TELL_YET. The same rule names the first-action shift p_F − p_N as the primary estimand, and that quantity has room to move. When recovery saturates the final outcome, the two clauses disagree about whether Stage 2 can learn anything. **This is an open pre-registration question, not decided here.** Two things remain observable either way: whether the card changes the first move, and whether it stops an agent from recovering in world B. The second would be real harm, and it would show as a fall in final correctness from this ceiling.

Stage 2 was priced at $59 expected and $275 capped. It is not authorised, and it should not be asked for until the question in point 3 is settled.
