# #421 — three deterministic checks that close the unlabelled-inference paths the sized run of 2026-09-03 falsified

## What happened

RAT-0001 Amendment 2 (#418) records three assumptions that the sized run of 2026-09-03 falsified, and #419 records the fixture finding. This PR implements the three deterministic checks the ticket names, each closing one unlabelled-inference path: a bridge between two verified facts that inherited their credibility without being written as a claim and tested.

## Check 1: a trap-discipline read refuses when the Null arm never met the hazard

### What was built

1. **`hazard_action` registered on the record.** A new optional front-matter field on `RatRecord` (`ratification.py`), parsed by `parse_rat_record` into `RatRecord.hazard_action: str | None`. When present, it is compiled as a regular expression; a non-compiling pattern is refused by name (`RatificationError` naming `hazard_action`). It is registered the way the oracle knobs (gamma, delta_min, q_min) are: an optional field that the parser validates, so a later run cannot quietly change what "entered" means.

2. **`hazard_entry_counts` in a tracked module.** `skill_harness.subject.paired_launch` gains `hazard_entry_counts(eval_log_path, pattern) -> HazardEntry` (fields: `pattern`, `epochs`, `entered`). It reads one Inspect `.eval` log (lazily importing `inspect_ai.log.read_eval_log`, same convention as `parse_eval_log`), scans every bash tool-call command per epoch (function name case-insensitively matching `HAZARD_BASH_TOOL = "bash"`, command extracted from `arguments["command"]`), and counts epochs where at least one command matched the pattern. A tracked module carries the computation because an untracked runner script cannot be the place a control lives.

3. **The refusal lives in `evaluate-paired`, which knows the value class.** In `cli/paired_gate2.py`, after the runner-declaration check and before the decision: for `value_class == trap-discipline`, refuse `HAZARD_NOT_RECORDED` (exit 1) when `runner.hazard` is absent, and refuse `HAZARD_NOT_MET` (exit 2, the same exit code as `COUNT_MISMATCH`) when `runner.hazard.null.entered == 0`. Both refusals name the counts. For other value classes the hazard block is printed when present and never refused on.

4. **`subject/ingest.py` is byte-identical.** The ingest already records the runner block verbatim under `config_json["runner"]`; the hazard sub-block is added to the runner config dict by the caller (the runner script) after `hazard_entry_counts` runs, not by the ingest. The oracle identity 0.4.1 hash is unchanged: `test_paired_launch.py::TestIngestByteIdentical` asserts `sha256(subject/ingest.py) == ae28a10512c62a5b16a2ca272d07a81510afba9085197e926c50e39c879d09a4` and `ORACLE_METRIC_VERSION == "0.4.1"`.

5. **Reading `0700d089…` after this lands returns `HAZARD_NOT_RECORDED`.** Its runner block predates the `hazard` field, so `runner.hazard` is absent and the trap-discipline read refuses. Amendment 2 of RAT-0001 gains a dated line (2026-09-03) recording this; the store is not rewritten (append-only stands).

### Tests that pin it

- `test_cli_paired_gate2.py::TestHazardNotMet::test_hazard_not_met_refuses_under_trap_discipline` — ARM: `null.entered = 0` under `trap-discipline` → exit 2, `HAZARD_NOT_MET` in output, no `Verdict`. Watched it fail before the `paired_gate2.py` hazard block was added (the seeded run with `null.entered = 0` returned exit 0 with a `Verdict` line).
- `test_cli_paired_gate2.py::TestHazardNotMet::test_hazard_not_met_decides_under_transformative_lift` — CONTROL: the same seeded run under `transformative-lift` decides (exit 0). Confirms the check is trap-discipline only, not unconditional.
- `test_cli_paired_gate2.py::TestHazardNotRecorded::test_no_hazard_block_refuses_under_trap_discipline` — ARM: no `hazard` block under `trap-discipline` → exit 1, `HAZARD_NOT_RECORDED` in output. Watched it fail before the check (the seeded run with no hazard block returned exit 0).
- `test_cli_paired_gate2.py::TestHazardNotRecorded::test_no_hazard_block_decides_under_transformative_lift` — CONTROL: no hazard block under `transformative-lift` decides.
- `test_cli_paired_gate2.py::TestHazardPositivePath::test_hazard_entered_decides_under_trap_discipline` — the positive path: `null.entered > 0` under `trap-discipline` → exit 0, `Decision:` in output. Decides as before.
- `test_paired_launch.py::TestHazardEntryCounts::test_zero_of_32_when_no_epoch_ran_git_pull` — `hazard_entry_counts` over a 32-epoch log where no epoch ran `git pull` returns `entered = 0 of 32`. Measured by mocking `read_eval_log` with a `SimpleNamespace` log whose bash calls all ran `git fetch … && git merge …`.
- `test_paired_launch.py::TestHazardEntryCounts::test_three_of_8_when_three_epochs_ran_git_pull` — 3 of 8 epochs ran `git pull` (with and without `-C <path>`); `hazard_entry_counts` returns `entered = 3`. The pattern `git.*pull` matches `git pull`, `git pull --rebase`, and `git -C /root pull`.
- `test_ratification.py::TestHazardAction::test_hazard_action_non_compiling_regex_refused_by_name` — `hazard_action: git(s+pull` (unbalanced group) is refused by `parse_rat_record`, naming `hazard_action`.
- `test_ratification.py::TestHazardAction::test_hazard_action_present_parses` — a valid regex parses into `RatRecord.hazard_action`.
- `test_paired_launch.py::TestIngestByteIdentical::test_ingest_py_hash_is_unchanged` — pins `subject/ingest.py` to the pre-change hash; would fail if the file were edited.

## Check 2: a pilot on one subject cannot size a run on another silently

### What was built

1. **`pilot_subject_model` on the record.** A new optional front-matter field on `RatRecord` (`ratification.py`), parsed by `parse_rat_record` into `RatRecord.pilot_subject_model: str | None`. Optional at parse time (existing records without it still parse); required at pre-flight.

2. **`subject_change_waiver` on the record.** A new optional nested-block front-matter field (`RatRecord.subject_change_waiver: dict[str, str] | None`), parsed by `parse_rat_record`. Present iff `pilot_subject_model` differs from the priced subject and the transfer is authorised. The waiver must carry `reason`, `measurement`, and `date` keys.

3. **The refusal in `preflight_sized_run`.** When `evidence_db` is provided (a real launch always carries the evidence DB), `preflight_sized_run` refuses by name when `pilot_subject_model` is missing, and refuses when it differs from `bare_model` unless a `subject_change_waiver` block carrying `reason`, `measurement`, and `date` is present. The check is gated on `evidence_db` so the cap-boundary tests (which omit it) are unaffected; a real launch always provides it.

### Tests that pin it

- `test_paired_launch.py::TestPilotSubjectModel::test_missing_pilot_subject_model_refuses_by_name` — the real RAT-0001 (which has no `pilot_subject_model`) with `evidence_db` → `PairedLaunchRefusal` matching `pilot_subject_model`. Watched it fail before the check was added (the call returned a tuple instead of raising).
- `test_paired_launch.py::TestPilotSubjectModel::test_mismatched_pilot_subject_model_refuses_without_waiver` — a fixture record with `pilot_subject_model: claude-sonnet-4.5` priced at `claude-sonnet-5` → `PairedLaunchRefusal` matching `subject_change_waiver`.
- `test_paired_launch.py::TestPilotSubjectModel::test_mismatched_pilot_subject_model_passes_with_waiver` — the same mismatch with a `subject_change_waiver` block (`reason`, `measurement`, `date`) → passes, returns the design.

## Check 3: prior ledgered measurements are printed before spend

### What was built

1. **`prior_measurements` in `paired_launch.py`.** Queries the evidence store (`runs` table) and the screen store (`screen_runs` table) for prior measurements matching the record's `task_family` / card and the priced subject, by fixture SHA and model. Returns one line per measurement; printing is the check (#421: refusal is not proposed here).

2. **`preflight_sized_run` prints them before the cost line.** When `evidence_db` is provided, the prior measurements are printed before the cost projection, so the launcher sees the ceiling at zero cost.

### Tests that pin it

- `test_paired_launch.py::TestPriorMeasurements::test_dry_run_prints_screen_row_and_refuses_on_missing_pilot_subject_model` — the real dry run of RAT-0001: seeds an evidence DB with a screen run matching OBS-0007's parameters (`git-pull-rebase-trap`, `claude-sonnet-5`, Null 3 of 3, p0 = 1), calls `preflight_sized_run` with `evidence_db`, captures stdout. Asserts `prior: screen run dae60c17` and `Null 3 of 3` and `p0 = 1.0000` are printed, then `PairedLaunchRefusal` matching `pilot_subject_model` is raised. Watched it fail before both checks were added (no prior line printed, no refusal raised).

## Amendment 2

`docs/ratifications/RAT-0001-git-pull-rebase-trap.md` gains a dated line (2026-09-03) recording that `evaluate-paired` now returns `HAZARD_NOT_RECORDED` for run `0700d089…` because its runner block predates the `hazard` field. The `CANT_TELL_YET` line in Amendment 2's decision table is superseded; the store is not rewritten (append-only stands).

## Mutation campaign

No formal mutation campaign was run. Each ARM above was verified by watching the seeded test fail for the right reason before the implementation was added, and pass after. The CONTROL tests (same seed under `transformative-lift`) confirm the trap-discipline refusals are not unconditional.

## Gate

- tests: `PYTHONHASHSEED=0 pytest tests/test_paired_launch.py tests/test_cli_paired_gate2.py tests/test_ratification.py tests/test_subject_ingest.py tests/test_oracle_implementation_identity.py tests/test_receipts_index.py` — 219 passed.
- types: `pyright src/skill_harness/ratification.py src/skill_harness/subject/paired_launch.py src/skill_harness/cli/paired_gate2.py` — 0 errors, 1 warning (the expected `inspect_ai` missing-import on the optional extra).
- lint: `ruff check` on the changed files — all checks passed.
- drift-guard: `python scripts/drift_check.py` — PASS, all 13 live contracts hold.
