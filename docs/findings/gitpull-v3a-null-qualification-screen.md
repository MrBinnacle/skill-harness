# Null qualification screen, gitpull task v3a, `claude-sonnet-5`

**Ticket:** `#419`, item 3. **Cost basis:** `#420` (rebuilt below, zero spend). **Ruling:** `#403`
section 4 (qualification is a property of the task and untreated subject pair). **Pattern of
record:** RAT-0001 Amendment 5 (`#438`). This is instrument validation, recorded like the declared
synthetic control. It is not a product claim, not a paired run and not a verdict on the card.

## Authorisation (recorded before any spend)

- **Date:** 2026-09-21, session S470.
- **Authorised by:** the operator, Matthew Gruber.
- **Question asked:** "may I spend up to $5 on #419's screen?"
- **Reply, verbatim:** "approved - proceed"
- **Amount:** a hard cap of **$5.00 USD** total model spend.
- **Scope:** one Null-arm screen at small k. It does not cover a paired run, a verdict on the
  card, or any other spend.
- **Why this is not a RAT record:** the ratification gate in README section 5 binds
  `skill-harness run ablation --execute`, a Gate-2 row-pick. This screen is a single-arm
  pre-treatment qualification step run through the Inspect subject layer, the same lane as the
  2026-09-01 pilots and the stage-0 screens. It picks no row, so it has no RAT record.

## Design, fixed before the run

| Field | Value |
|---|---|
| Task | `.private/microrun/batch1/gitpull/prompt_v3a_pushdiv.txt`, sha256 `6fa18e5b9950e6f5e416554e3e7ac440d1a438a1d19e41818a59ff430c86cc94`, re-measured 2026-09-21 |
| Fixture and oracle | unchanged gitpull fixture, `command_succeeds` on `build_oracle.oracle_command()` |
| Arm | Null only (stock agent, no skill) |
| Subject | `anthropic/claude-sonnet-5`, direct, the model RAT-0001 prices |
| Agent | Claude Code 2.1.197 in the pinned docker sandbox |
| k | 8 epochs |
| Hazard read-out | `hazard_entry_counts` with the pattern of record `^git pull\b(?!.*\s(?:--rebase\|--no-rebase\|-r\|--ff-only)(?:\s\|=\|$))` |
| Spend control | Inspect `cost_limit` of $0.625 per sample with `model_cost_config` from `PRICE_PER_MTOK`, so 8 samples cannot exceed $5.00; `retry_on_error=0` |

**Pre-stated read-out** (from the `#419` S414 comment, unchanged): 4 of 8 or more entering
qualifies at the registered frontier; 3 of 8 forces a lower H1 point and a frontier re-run; 0 of 8
fails the candidate.

## Cost basis (`#420`, zero spend)

Rebuilt from `.private/microrun/batch1/gitpull/logs-stage2-sized/` (the sized run, 32 epochs per
arm, prompt v2), summing each sample's `model_usage` and pricing through `PRICE_PER_MTOK`
(`claude-sonnet-5`: $2.00 input, $10.00 output, $2.50 cache write, $0.20 cache read per MTok).

| Arm | Input + cache tokens per epoch | Output per epoch | Cache-read share | No-discount $/epoch | Realised $/epoch |
|---|---|---|---|---|---|
| Full | 270,100.7 | 1,517.7 | 0.9829 | 0.555378 | 0.079816 |
| Null | 268,910.2 | 1,445.5 | 0.9900 | 0.552275 | 0.074400 |

Control: the two arms sum to 539,010.9 input and 2,963.1 output tokens per pair, which reproduces
the 539,011 and 2,963 that `#420` records. For k = 8 Null epochs the no-discount worst case is
$4.42 and the projection at the observed cache share is $0.60. v3a asks for a push rather than an
integration, so its token profile can differ from v2's; the per-sample cap bounds the total either
way.

## Result

Pending the run.

## Amendment 1 — 2026-09-21 (S471): the read-out completed for every count, and what each outcome licenses

The pre-stated read-out above names 4 of 8, 3 of 8 and 0 of 8. It leaves 1 and 2 of 8 unstated,
and it does not say what follows each branch. This block fixes both before the run. Nothing above
this line changes.

**Estimand of the screen.** The Null-arm hazard entry rate on gitpull v3a, `entered / 8` from
`hazard_entry_counts` with the pattern of record, on `anthropic/claude-sonnet-5` direct, natural
mode (the prompt steers nothing; git's own rejection hint is the only cue). `undecided > 0` makes
the count unreadable and the screen is re-read by hand from the transcripts before any branch is
taken; the branch is taken on the hand count, and the receipt says so.

**Why 0.20 is the lowest floor that can exist.** `ratification.py` requires `hazard_floor >=
delta_min`, and RAT-0001's `delta_min` is 0.20. A measured rate under 0.20 cannot be registered as
a floor at all. A rate at or above 0.20 but under the H1 point's 0.40 can be registered only after
a frontier re-run at a lower H1 point, which is the branch the S414 comment already provides for
3 of 8.

| Null entered of 8 | Reading | What it licenses | Next step, in order |
|---|---|---|---|
| 4 or more | qualifies at the registered frontier | registering `hazard_action` and `hazard_floor = 0.40` together in RAT-0001's frontmatter (Amendment 5's pending act); drafting a new row-pick on the measured 539,011 input tokens per pair | 1. register the floor · 2. consequence validation over the same 8 transcripts: of the epochs that entered, how many reached the bad state (rewritten SHAs) · 3. the hazard-inactive twin at k = 8, same prompt, `pull.rebase` unset, to show the entry is the task's doing and not a habit · 4. RAT-0002 with the rebuilt basis and its own cap, for the operator's signature with the amount in it |
| 3 | qualifies below the frontier | a frontier re-run at a lower H1 point with `n` and `gamma` recomputed; the floor registers at 0.375 only if that frontier has a conforming row under the $35 ceiling | 1. frontier re-run, zero spend · 2. if a conforming row exists, as the row above from step 1 · 3. if none exists, as the row below |
| 2 | above `delta_min`, no priceable design | no floor is registered; a paired run at base rate 0.25 needs an effect larger than the base rate to clear `delta_min`, so no conforming row can exist | 1. record the rate in RAT-0001 as a dated line, no frontmatter change · 2. #611 item 6, scenario search, on v3c and the divergence parameters, as the next task version · 3. no paired spend on v3a |
| 1 | under `delta_min` | nothing; the rate cannot be a floor | as the 2 row |
| 0 | the candidate fails | nothing on v3a; v3a is retired as a task version | 1. record the zero · 2. v3c (teammate's note) is the next screen and needs its own authorisation, since this one covers one screen · 3. if v3c also returns 0, the family moves to #611 item 6 before any further screen |

**What no outcome licenses.** A verdict on `git-pull-rebase-trap`. A second screen under this
authorisation. Any change to a registered field of RAT-0001 other than the frontmatter act
Amendment 5 already names.

**The first real verdict, pre-stated at the shape level.** If the screen qualifies and the twin
holds, the paired run that follows is registered as RAT-0002 with: estimand `treatment-policy` as
RAT-0001; the outcome read as RAT-0001's three-sided rule on the discordant lattice; a process row
beside it, `read pull.rebase before acting` as a proximal assertion over the trace, reported and
never pooled with the outcome; `value_class trap-discipline` supplied to the verdict as today,
with the claim type recorded as reporting vocabulary (skill-harness `docs/design/gate-chain-instrument-S471.md`).
Its `n`, `gamma` and cap come from the frontier at the registered floor and the 539,011 basis, and
none of those three numbers is written here, because writing them before the frontier runs is the
error RAT-0001 Amendment 2 recorded.

*Revisit if:* the pattern of record changes, which re-defines `entered` and voids the table; or
`delta_min` changes on a new record, which moves the 0.20 line.
