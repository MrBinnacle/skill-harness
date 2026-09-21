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
