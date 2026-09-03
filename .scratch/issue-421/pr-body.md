# #421 — three deterministic checks that close the unlabelled-inference paths the sized run of 2026-09-03 falsified

## What happened

RAT-0001 Amendment 2 (#418) records three assumptions that the sized run of 2026-09-03 falsified, and #419 records the fixture finding. This PR implements the three deterministic checks the ticket names, each closing one unlabelled-inference path: a bridge between two verified facts that inherited their credibility without being written as a claim and tested.

The first build of this ticket implemented the pre-amendment zero-only Null check. This build carries the #403 amendment that the issue body now inlines: the registered floor, the two-arm hazard block, and the below-floor negative control.

## Check 1: a trap-discipline read refuses when the Null arm met the hazard too rarely to measure

### What was built

1. **`hazard_action` and `hazard_floor` registered on the record.** Two optional front-matter fields on `RatRecord`, parsed by `parse_rat_record`. When either is present both are required together. `hazard_action` must compile as a regular expression; `hazard_floor` must lie in (0, 1] and must be >= `delta_min` when `delta_min` is set (a floor below the minimum detectable effect cannot certify BENEFIT). Refusals name the field.

2. **`hazard_entry_counts` in a tracked module.** `skill_harness.subject.paired_launch` gains `hazard_entry_counts(eval_log_path, pattern) -> HazardEntry` (fields: `pattern`, `epochs`, `entered`). It reads one Inspect `.eval` log (lazily importing `inspect_ai.log.read_eval_log`), scans every bash tool-call command per epoch (function name case-insensitively matching `HAZARD_BASH_TOOL = "bash"`, command from `arguments["command"]`), and counts epochs where at least one command matched. A tracked module carries the computation because an untracked runner script cannot be the place a control lives. The runner places both arms and the floor under `runner_config["hazard"]` after the run; ingest records the runner block verbatim.

3. **The refusal lives in `evaluate-paired`, which knows the value class.** In `cli/paired_gate2.py`, after the runner-declaration check and before the decision: for `value_class == trap-discipline`,
   - refuse `HAZARD_NOT_RECORDED` (exit 1) when `runner.hazard` is absent (or lacks Null counts / floor);
   - refuse `HAZARD_NOT_MET` (exit 2, same code as `COUNT_MISMATCH`) when `null.entered / null.epochs < hazard_floor`.
   `entered = 0` is the degenerate case of the second refusal. Both refusals name `entered`, `epochs`, and the floor. The Full arm is printed (`Full arm entered the hazard in k of n`) and never gated (#403: Full-arm entry is post-treatment). For other value classes the block is printed when present and never refused on. Floor is read from the record first, then the block mirror written at launch.

4. **`subject/ingest.py` is byte-identical.** The hazard sub-block is added to the runner config by the caller after `hazard_entry_counts` runs, not by the ingest. The oracle identity 0.4.1 hash is unchanged: `test_paired_launch.py::TestIngestByteIdentical` asserts it.

5. **Reading `0700d089…` after this lands returns `HAZARD_NOT_RECORDED`.** Its runner block predates the `hazard` field. Amendment 2 of RAT-0001 gains a dated line (2026-09-03) recording this; the store is not rewritten (append-only stands).

### Tests that pin it

- `TestHazardNotMet::test_hazard_not_met_refuses_under_trap_discipline` — ARM: `null.entered = 0` under `trap-discipline` → exit 2, `HAZARD_NOT_MET`, names the floor, no `Verdict`.
- `TestHazardNotMet::test_below_floor_but_nonzero_refuses_under_trap_discipline` — ARM: 3 of 32 (rate 0.09375) below floor 0.20 → exit 2, `HAZARD_NOT_MET`. The zero test alone does not cover the registered floor.
- `TestHazardNotMet::test_hazard_not_met_decides_under_transformative_lift` — CONTROL: same seed under `transformative-lift` decides.
- `TestHazardNotRecorded::test_no_hazard_block_refuses_under_trap_discipline` — ARM: no block → exit 1, `HAZARD_NOT_RECORDED`.
- `TestHazardNotRecorded::test_no_hazard_block_decides_under_transformative_lift` — CONTROL.
- `TestHazardPositivePath::test_hazard_at_floor_decides_under_trap_discipline` — 7 of 32 >= floor 0.20 → exit 0; Full arm line printed.
- `TestHazardEntryCounts::test_zero_of_32_when_no_epoch_ran_git_pull` / `test_three_of_8_when_three_epochs_ran_git_pull`.
- `TestHazardAction` — pair required together; floor below `delta_min` refused; non-compiling regex refused.
- `TestIngestByteIdentical::test_ingest_py_hash_is_unchanged`.

## Check 2: a pilot on one subject cannot size a run on another silently

### What was built

1. **`pilot_subject_model` on the record.** Optional at parse; required at pre-flight when `evidence_db` is provided.
2. **`subject_change_waiver` nested block** carrying `reason`, `measurement`, and `date`.
3. **Refusal in `preflight_sized_run`.** Missing pilot subject, or mismatch without a complete waiver, raises `PairedLaunchRefusal` naming the field. Gated on `evidence_db` so cap-boundary tests that omit it stay on the cap projection alone.

### Tests that pin it

- `TestPilotSubjectModel::test_missing_pilot_subject_model_refuses_by_name` — real RAT-0001 + evidence_db → refusal naming `pilot_subject_model`.
- `TestPilotSubjectModel::test_mismatched_pilot_subject_model_refuses_without_waiver`.
- `TestPilotSubjectModel::test_mismatched_pilot_subject_model_passes_with_waiver`.
- `tests/test_ratification.py::TestPilotSubjectModel` — parse of the fields.

## Check 3: prior ledgered measurements are printed before spend

### What was built

1. **`prior_measurements` in `paired_launch.py`.** Queries the evidence store and the screen store for prior measurements matching the record's task family / card and the priced subject. Returns one line per measurement; printing is the check (refusal is not proposed here).
2. **`preflight_sized_run` prints them before the cost line** when `evidence_db` is provided.

### Tests that pin it

- `TestPriorMeasurements::test_dry_run_prints_screen_row_and_refuses_on_missing_pilot_subject_model` — seeds OBS-0007-shaped screen row, asserts `prior: screen run dae60c17`, `Null 3 of 3`, `p0 = 1.0000`, then refusal on `pilot_subject_model`.

## Amendment 2

`docs/ratifications/RAT-0001-git-pull-rebase-trap.md` gains a dated line (2026-09-03) recording that `evaluate-paired` now returns `HAZARD_NOT_RECORDED` for run `0700d089…` because its runner block predates the `hazard` field. The `CANT_TELL_YET` line in Amendment 2's decision table is superseded; the store is not rewritten (append-only stands).

## Mutation campaign

`scripts/mutation_receipt.py --select 389` was re-run after `be86b77` moved
`paired_gate2.py`'s bytes (the `#403`-amendment hazard refusal landed in the same
module), which made the prior receipt's `target_digests` pin stale
(`c1ba4677…` → `8abfb41b…`). The two `#389` mutants were re-measured against the
current file; both anchors were still present exactly once and both kills held,
by the same detectors:

| mutant | obligation | mutation | verdict | killing assertion |
|---|---|---|---|---|
| M-R1 | 389-ratification-binding | force `record.status != "RATIFIED"` to `False`: a DRAFT record is accepted | **KILLED** | `tests/test_cli_paired_gate2.py::TestUnratifiedDesign::test_draft_record_refused` |
| M-R2 | 389-count-mismatch | force `total_pairs != design.n_pairs` to `False`: k=8 read against n=32 | **KILLED** | `tests/test_cli_paired_gate2.py::TestCountMismatch::test_pilot_k8_vs_design_n32` |

The regenerated receipt is `docs/assurance/paired-gate2-mutation-receipt.json`
(commit `be86b77`, Python 3.13.15, digest `8abfb41b…`); its prose companion and
the `docs/receipts-index.md` entry were updated to name the same digest
(`tests/test_mutation_receipt.py::test_prose_companion_names_the_digest_its_receipt_attests`
pins that). The `#421` hazard refusals themselves are pinned by the named
negative-control tests above, not by mutants in this receipt — the receipt
attests only to the two `#389` guards, matching its `--select 389` scope.

## Gate

- tests: `PYTHONHASHSEED=0 pytest -q -m "not live and not calibration and not assurance"` — green (mutation-receipt currency and prose-companion tests included).
- types / lint / drift-guard: green (see the compound gate run below).
