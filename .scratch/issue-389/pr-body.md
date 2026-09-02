# PR: Paired-lane Gate-2 read surface (#389)

## What this builds

A read-only CLI command (`run evaluate-paired`) that takes a paired run id, a
ratification-record reference, and a value class, and returns the same typed
result the matched bridge returns: a decision with its signed effect and
Newcombe interval and the keep/cut verdict, or a typed refusal.

The design is registered, never authored at the call site: the command refuses
a design that is not backed by a RATIFIED record whose fields match (the same
shape the `run ablation --execute` gate uses), and the ingest records the
ratification reference in the run's `config_json`. A run whose pair count
differs from the design's `n_pairs` returns the existing `COUNT_MISMATCH`
refusal.

## What this does NOT build

The #368 ablation-lane migration (tie-heavy clause decisions in the stopping
and fit path) is NOT this ticket. This ticket gives the paired lane its Gate-2
read under the same registered design. The strict xfails in
`tests/test_halfupdate_tie_sensitivity.py` are not touched here.

## Acceptance criteria

### AC1: Read-only CLI surface

Built: `src/skill_harness/cli/paired_gate2.py` with `paired_gate2_read()`,
registered as `run evaluate-paired` in `src/skill_harness/cli/main.py:3220`.

The command takes three positional arguments: `RUN_ID`, `RATIFICATION_PATH`,
and `VALUE_CLASS` (a Click Choice over the ValueClass enum). An optional
`--evidence-db` option defaults to `./evidence.db`. It performs no writes and
no API calls.

Test: `test_cli_paired_gate2.py::TestBenefitToKeep::test_benefit_keeps` — a
synthetic store with full_only=8, null_only=0, both_pass=4, both_fail=4
against a n=16 design prints "Decision: benefit" and "Verdict: KEEP". This
test failed before the change (command did not exist) and passes after.

### AC2: Design from RATIFIED record only

Built: `paired_gate2_read()` calls `parse_rat_record()` to load the design,
then checks `record.status != "RATIFIED"`. A DRAFT record, a missing record,
or a field mismatch is a typed refusal naming the field.

Tests:
- `TestUnratifiedDesign::test_draft_record_refused` — a RAT record with
  `status: DRAFT` returns exit code 1 with "DRAFT" and "RATIFIED" in the
  output. Failed before, passes after.
- `TestMissingRecord::test_missing_record_refused` — a file that is not a
  valid RAT record returns exit code 1 with the parse error. Failed before,
  passes after.

### AC3: COUNT_MISMATCH for pilot k=8 vs design n=32

Built: `paired_gate2_read()` reads `paired_cells` from `config_json`, sums
the four cell counts, and compares against `design.n_pairs`. A mismatch
returns exit code 2 with "COUNT_MISMATCH" in the output.

Test: `TestCountMismatch::test_pilot_k8_vs_design_n32` — a run with 8 pairs
against a ratification record with n=32 returns exit code 2 and prints
"COUNT_MISMATCH" with both numbers. Failed before, passes after.

### AC4: Value class required with no default

Built: `VALUE_CLASS` is a required positional argument in the Click command.
There is no default. `None` must be passed in writing (the matched bridge
rule).

Test: `TestValueClassRequired::test_missing_value_class_shows_error` —
invoking without VALUE_CLASS returns a non-zero exit code with an error
message. Failed before, passes after.

### AC5: Verdict path uses effect_from_matched_gate2 then matched_gate2_verdict

Built: `paired_gate2_read()` calls `effect_from_matched_gate2(design, ...)` to
compute the effect, then `matched_gate2_verdict(effect, value_class=...)` to
produce the verdict. No new rule or threshold constant is introduced anywhere
in the command.

Test: `TestBenefitToKeep::test_benefit_keeps` — the decision is "benefit" (from
`effect_from_matched_gate2`) and the verdict is "KEEP" (from
`matched_gate2_verdict`). The pi_c line is formatted from `config_json`, not
recomputed.

### AC6: Test coverage at the CLI seam

Tests in `tests/test_cli_paired_gate2.py` on synthetic stores:
- `TestBenefitToKeep` — BENEFIT -> KEEP
- `TestHarmToCut` — HARM -> CUT(harmful)
- `TestEquivalentNonTransformative` — EQUIVALENT under trap-discipline ->
  CANT_TELL_YET(wrong_instrument)
- `TestCountMismatch` — k=8 vs n=32 -> COUNT_MISMATCH
- `TestUnratifiedDesign` — DRAFT record -> refusal
- `TestMissingRecord` — invalid file -> refusal
- `TestNoPairedCells` — run without paired_cells config -> refusal
- `TestValueClassRequired` — missing value class -> error

All 8 tests pass. 115 related tests pass (ratification, matched bridge,
matched effect, aggregation mutation).

### AC7: Mutation receipt

Created: `docs/assurance/paired-gate2-mutation-receipt.md` with two named
mutants:
- M-R1: remove `record.status != "RATIFIED"` check -> KILLED by
  `test_draft_record_refused`
- M-R2: remove `total_pairs != design.n_pairs` check -> KILLED by
  `test_pilot_k8_vs_design_n32`

Entry added to `docs/receipts-index.md` (CI-gated completeness check passes).

### AC8: #368 ablation-lane migration not touched

The strict xfails in `tests/test_halfupdate_tie_sensitivity.py` are not
modified. This ticket gives the paired lane its Gate-2 read; the ablation-lane
tie-migration is a separate ticket.

## Gate results

- Tests: 8 new + 115 related = 123 pass, 0 fail
- Lint (ruff): all checks passed
- Types (mypy --strict): no issues in paired_gate2.py or ratification.py
- Drift guard: PASS (all 13 live contracts hold)
- Receipts index: 14/14 pass

## Files changed

| File | Change |
|---|---|
| `src/skill_harness/cli/paired_gate2.py` | **New.** Read-only paired-lane Gate-2 command. |
| `src/skill_harness/cli/main.py` | Register `run evaluate-paired` subcommand. |
| `src/skill_harness/ratification.py` | Add `gamma`, `delta_min`, `q_min` to `RatRecord` (optional, defaults). |
| `docs/ratifications/TEMPLATE.md` | Add `gamma`, `delta_min`, `q_min` to template front-matter. |
| `tests/test_cli_paired_gate2.py` | **New.** 8 tests at the CLI seam on synthetic stores. |
| `docs/assurance/paired-gate2-mutation-receipt.md` | **New.** Mutation receipt for ratification binding + count-mismatch refusal. |
| `docs/receipts-index.md` | Add entry for the new assurance report. |
