# #387 — Paired ingest: treatment = exposure, invocation = stratifier

Parent: #384 (Amendment 3 of `docs/findings/v0.2-preregistration.md`, landed by #386).

## What changed

The paired ingest lane now treats **exposure** (the skill's description present in
the agent's transcript) as the treatment, and **invocation** (Skill tool call) as a
recorded stratifier. The `ORACLE_METRIC_VERSION` is bumped from `0.3.0` to `0.4.0`.

Key changes in `src/skill_harness/subject/ingest.py`:
- `ZeroInvocationError` is retired from the write path (deprecated, kept for
  backward compatibility). Zero invocations with full exposure is ADMISSIBLE — the
  write proceeds with pi_c = 0/n.
- Two new refusal predicates in `_validate_pair`: (a) `UnexposedFullEpochError` —
  Full-arm epoch with exposure not detected; (b) `NullArmContaminationError` —
  widened from invocation-only to include channel-(c) exposure.
- `ExposureSummary` model and `_exposure_summary()` function added, mandatory on
  every `IngestResult`.
- `_paired_cell_counts()` computes the four paired-outcome cell counts (both pass,
  full only, null only, both fail) and records them in the run's `config_json`.
- `config_json` records `pi_c`, `exposure`, and `paired_cells` blocks.

## Acceptance criteria — evidence

### AC1: Each parsed sample carries `exposed_skill` beside `invoked_skill`

`ParsedSample.exposed_skill: bool` is present at `ingest.py:232`. The field defaults
to `False` (typed "not computed" for the screen lane). Computed by the v2 channel-(c)
detector `detect_skill_exposure()` when `skill_description` is non-empty; otherwise
`False`. The detector scans user-role messages for the skill's description text as a
substring (the same duck-typed, conservative scan style as the v1 invocation detector).

Test: `test_parse_eval_log_exposed_skill_defaults_false_without_description` (line 998)
pins the default. The screen lane path through `parse_eval_log` with empty description
produces `exposed_skill=False` on every sample.

### AC2: Paired write refusal predicates

Refusal predicate (a) — `UnexposedFullEpochError`: `test_full_arm_unexposed_refuses`
(line 716) creates a Full-arm epoch with `exposed=False` and asserts the refusal fires
with "exposure not detected" in the message. Before the change: N/A (field didn't
exist). After: refusal fires.

Refusal predicate (b) — `NullArmContaminationError` (channel c): `test_null_arm_exposed_refuses`
(line 729) creates a Null-arm epoch with `exposed=True` and asserts the refusal fires
with "exposure detected". `test_null_arm_invoked_still_refuses` (line 739) verifies the
0/22 fixture from #46 stays green (invocation channel). `test_null_arm_exposed_and_invoked_refuses`
(line 750) covers both channels simultaneously.

### AC3: Zero invocations with full exposure WRITES

`test_zero_invocations_with_full_exposure_writes_successfully` (line 609) creates a
Full arm with `invoked=False, exposed=True` across 2 epochs, writes successfully, and
asserts: `pi_c.invocations == 0`, `pi_c.trials == 2`, `pi_c.ci_low == 0.0`,
`exposure.exposed_count == 2`. The run is written (1 run, 4 samples, 2 verdicts).

Before the change: this pair would have raised `ZeroInvocationError`. After: the write
succeeds with pi_c = 0/2.

### AC4: Paired-outcome cell counts in config_json

`test_config_json_records_paired_cell_counts` (line 918) creates a 4-epoch pair with
known outcomes and asserts the `config_json.paired_cells` dict matches:
`both_pass=1, full_only=2, null_only=0, both_fail=1`. The computation is in
`_paired_cell_counts()` (line 889).

`test_config_json_records_exposure_summary` (line 950) asserts the exposure block in
config_json: `exposed_count=2, trials=2, detector_version="v2-description-channel"`.

`test_config_json_records_pi_c_block` (line 970) asserts the pi_c block in config_json.

### AC5: Verdict rationale carries pi_c line

`test_paired_verdict_carries_pi_c_line` (line 1036) calls `paired_verdict` with pi_c
parameters and asserts the rationale contains `pi_c_hat = 0.2500`, `8 trials`,
`95% CI [0.0319, 0.6509]`.

`test_paired_verdict_pi_c_zero_says_cace_not_identified` (line 1052) asserts that at
pi_c = 0, the rationale contains "CACE secondary is not identified".

`test_paired_verdict_without_pi_c_has_no_pi_c_line` (line 1067) asserts backward
compatibility: no pi_c parameters means no pi_c line.

### AC6: Fixtures at the ingest seam

All synthetic (2026-09-01 logs are private):
- `test_exposed_and_invoked_pair_writes` (line 767): exposed-and-invoked pair writes.
- `test_exposed_not_invoked_pair_writes_pi_c_0` (line 788): exposed-not-invoked pair
  writes with pi_c = 0/n (the 2026-09-01 git-pull-rebase-trap scenario).
- `test_unexposed_full_epoch_refuses` (line 824): Full epoch unexposed refuses;
  verifies epoch index on the error and zero rows written.
- `test_null_epoch_exposed_refuses` (line 843): Null epoch exposed refuses.
- `test_null_epoch_invoked_refuses_0_22_fixture` (line 853): the 0/22 structural
  false-positive fixture from #46 stays green.
- `test_screen_lane_parse_reports_exposure_not_computed` (line 865): screen-lane parse
  reports exposure as `False` (typed "not computed").

### AC7: Mutation receipts

`test_mutation_unexposed_full_refusal_removes_predicate` (line 1078): monkey-patches
`_validate_pair` to set `exposed_skill=True` on all Full samples before the original
validation runs. The assertion `result.run_id` (write succeeded) turns from pass to
fail without the predicate — proving it is load-bearing. The original predicate is then
verified to still block the same pair.

`test_mutation_null_contamination_refusal_removes_predicate` (line 1128): monkey-patches
`_validate_pair` to set `exposed_skill=False` and `invoked_skill=False` on all Null
samples. The assertion `result.run_id` turns from pass to fail without the predicate.
The original predicate is then verified.

Both tests name the specific assertion (`result.run_id`), not the exit code.

### AC8: INVARIANTS section recording the ruling

`docs/INVARIANTS.md` gains section 10 recording:
- Treatment = exposure; pi_c = mandatory stratifier
- Two refusal predicates with enforced-in lines naming `ingest.py::_validate_pair`
  and the six tests that pin them
- Revisit-if for a non-`claude_code` solver whose transcript lacks the listing

### AC9: Oracle identity hash / metric version

The `ORACLE_METRIC_VERSION` is bumped to `0.4.0` (`ingest.py:113`). The
`_oracle_implementation_hash()` computes SHA-256 over `ingest.py`'s raw bytes at
runtime, so the hash automatically covers this file byte-for-byte.

The SERS fixture `tests/fixtures/sers/minted_synthetic_control_v1_1_0.json` is updated
to record `metric_version: "0.4.0"` to match the live code.

`test_fresh_subject_identity_mint_hashes_the_live_oracle_module` (SERS conformance)
verifies the mint's implementation_hash equals SHA-256 of the live ingest.py bytes.
`test_v11_receipt_subject_identity_matches_harness_mint` verifies the fixture's
metric_version matches the live code.

## Conflict: test_paired_arm_epoch_adversarial.py

`test_zero_invocation_arm_swap_refused_as_dead_arm` was renamed to
`test_zero_invocation_arm_swap_with_null_contamination_refused` and updated:
the Null-arm samples now have `invoked=True` (contamination) instead of
`invoked=False` (which no longer triggers any refusal under the new treatment
model). The match string changed from "dead treated arm" to "contamination".
The module docstring's "honest boundary" section is updated to reflect that
ZeroInvocationError is retired and the swap surface is now closed by the
contamination and unexposed-Full predicates.

## Gate results

- `pytest tests/test_subject_ingest.py`: 56 passed
- `pytest tests/test_sers_conformance.py`: 22 passed
- `pytest tests/test_paired_arm_epoch_adversarial.py`: 7 passed
- `pytest tests/test_oracle_implementation_identity.py`: 41 passed
- `pytest tests/test_drift_check.py`: 45 passed
- `ruff check` on changed files: all passed
