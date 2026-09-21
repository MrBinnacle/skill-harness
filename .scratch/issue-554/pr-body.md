# PR: #554 — the runner expresses declared-arm (composition) runs, and the receipt carries the declared arm set

This change gives the ablation runner a second unit of comparison. The
per-clause loop still contrasts full/ablated_k/null over one card's own
clauses. Beside it, a run can now declare a set of named arms, each a whole
prompt assembly, and sample every arm into evidence. The receipt vocabulary
opens from the two-value enum (`null`, `full`) to the declared arm set. This
change is the runner and the receipt only; scoring the contrasts (for example
the interaction term of a 2x2 factorial) is a separate ticket whose number the
ticket text does not state.

The `Revisit if` clause of the ticket asks whether the composition study in
MrBinnacle/skills#305 is abandoned. This container holds no GitHub token and
the ticket instructs reading the tracker from the ticket text, so that question
was decided from the ticket's own lines: "Blocked by: None. Can start
immediately." and the motivating study description above it. The ticket states
the study is parked because this instrument cannot express its arms; this
change removes that reason for the parking.

## Files changed

- `src/skill_harness/ablation/arms.py` (new) — `ArmSpec`, `ArmAssembly`,
  `ArmSpecError`, `validate_arm_specs`, `resolve_arm_assemblies`, JSON
  roundtrip helpers, and `cross_factorial` with `ArmFactor`/`ArmLevel`.
- `src/skill_harness/ablation/render.py` — `ConditionRenderer.render_arm_assembly`,
  the block layout for a whole-prompt assembly.
- `src/skill_harness/ablation/runner.py` — `RunConfig.arms` (+ JSON roundtrip,
  `receipt_arm_names`), `ArmResult`, `ReceiptArmsMismatchError`,
  `ArmNeverSampledError`, `assert_receipt_arms_match`, and
  `AblationRunner.run_arms`, the declared-arm sampling loop.
- `src/skill_harness/storage/migrations_sql/evidence/1200_arm_samples.sql`
  (new) — the append-only `arm_samples` table.
- `src/skill_harness/storage/models.py` — `ARM_NAME_PATTERN`/`ARM_NAME_RE`/
  `is_valid_arm_name` (one vocabulary, defined in the lowest layer per the
  `task_frontier` precedent) and the `ArmSampleWrite` write model.
- `src/skill_harness/storage/repositories/evidence/runs.py` —
  `insert_arm_sample`, `count_arm_samples_by_arm`. These functions live in
  `runs.py` rather than a new module for the same reason `clause_run_outcomes`
  does: the rows are children of a run and the evidence repo module set is
  pinned by `test_expected_module_set`. No registered module name changed.
- `src/skill_harness/ablation/reconciler.py` — the A41 evidence cost sum now
  reads `samples.usd` and `arm_samples.usd` together.
- `docs/sers/sers.schema.json` — `subject_identity.arms` accepts the declared
  arm set.
- `src/skill_harness/sers/subject_identity.py` — `build_subject_identity`
  enforces the same declared-arm vocabulary.
- `docs/sers/README.md` — the documented `arms` row states the new vocabulary.
- `tests/ablation/test_arms.py` (new), `tests/test_sers_declared_arms.py` (new),
  `tests/fixtures/sers/poison_arms_bad_name.json` (new poison fixture).
- `docs/assurance/coverage-floors.md` and `docs/receipts-index.md` — registry
  entries for the new module, described under "Registered documents" below.

## Acceptance criteria

### AC1: A run config declares named arms, each resolving to a distinct system-prompt assembly

Built: `RunConfig.arms` is a tuple of `ArmSpec` (name, inline `body_texts`,
`skill_body_paths`), serialized into `runs.config_json` and read back.
`resolve_arm_assemblies` turns each spec into an `ArmAssembly` (base system
block plus one text block per body, cache markers on the base block and the
last body block) and refuses an empty set, ill-formed or duplicate names, blank
bodies, and two arms that resolve to the same assembly. Refusals happen before
any run row is written, so a refused declaration spends nothing.
`AblationRunner.run_arms` samples every declared arm, `samples_per_arm` times
each (default `N_MIN`), into `evidence.arm_samples`, and writes the declared set
into `runs.config_json` (written even when empty, on the same reasoning as the
`ratification_id` field).

Tests: `TestRunConfigArms::test_arms_roundtrip_through_config_json` pins the
config roundtrip; `TestResolveArmAssemblies::test_each_declared_arm_resolves_to_a_distinct_assembly`
pins one distinct assembly per declared arm;
`TestRunArms::test_run_samples_every_declared_arm` and
`test_run_config_json_carries_the_declared_arms` pin the run behaviour and the
stored config; `test_refusals_write_no_run_row` pins zero spend on refusal.

Observed: before the change the whole file failed at collection with
`ModuleNotFoundError: No module named 'skill_harness.ablation.arms'`. After the
change all pass.

### AC2: An arm can include a skill body that is not the subject's own, named by path

Built: `ArmSpec.skill_body_paths` names SKILL.md files. Resolution reads each
path through `skill_harness.extractor.parser.parse_skill_file`, so the
frontmatter is treated as metadata and the body joins the assembly verbatim. An
unreadable or frontmatter-only path raises `ArmSpecError` before any write.

Tests: `TestArmIncludesForeignBodyByPath::test_path_body_is_read_verbatim_without_frontmatter`,
`test_foreign_body_reaches_the_wire_in_a_declared_arm_run`,
`test_skill_body_paths_roundtrip_through_config_json`,
`test_unreadable_body_path_is_refused_before_spend`,
`test_frontmatter_only_body_path_is_refused`.

Observed: the path mechanism is part of the resolution machinery and landed
with AC1's commit, one commit before this criterion's tests. To observe the red
state I checked the branch's parent source out (`f57182e -- src/skill_harness`),
ran the AC2 tests, and watched collection fail with `ImportError while
importing test module` because the arms module does not exist there; restoring
`HEAD` turned them green. The tests pin behaviour that did not exist before the
branch; I record the commit-level ordering honestly rather than claiming the
tests predated the mechanism that serves them.

### AC3: The receipt schema accepts the declared arm set, and an existing two-arm receipt still validates

Built: `subject_identity.arms` in `docs/sers/sers.schema.json` changed from a
two-value enum to one lowercase-slug name or an array of unique names
(`^[a-z0-9][a-z0-9_-]*$`, `minItems 1`, `uniqueItems`; the two-item cap is
gone). `build_subject_identity` enforces the same vocabulary through
`ARM_NAME_PATTERN` defined once in `storage/models.py` and shared with the
runner and the `arm_samples` write model, so the runner's declared arms, the
stored rows and the receipt carry one vocabulary. A poison fixture
(`poison_arms_bad_name.json`, arms `["null", "Full"]`) is picked up by the
existing parametrized poison test and pins the schema floor. The documented
`arms` row in `docs/sers/README.md` states the new vocabulary.

Tests (`tests/test_sers_declared_arms.py`):
`test_mint_accepts_a_declared_arm_set` mints the four arms of the motivating
factorial naming and validates the receipt;
`test_mint_accepts_a_single_declared_arm` pins the string shape;
`test_existing_two_arm_receipt_still_validates` pins `["null", "full"]` and
`"null"`;
`test_mint_refuses_invalid_declared_arm_names`,
`test_schema_refuses_an_ill_formed_arm_name`,
`test_schema_refuses_duplicate_arm_names`,
`test_poison_fixture_for_ill_formed_arm_names_fails` pin the floor.

Observed: before the change, `test_mint_accepts_a_declared_arm_set`,
`test_mint_accepts_a_single_declared_arm` and
`test_poison_fixture_for_ill_formed_arm_names_fails` failed with `ValueError:
arms contains values outside {null, full}: [...]` from the mint helper. The
backward-compatibility test (`test_existing_two_arm_receipt_still_validates`)
passed before and after by construction: its claim is that the old vocabulary
keeps working, which the old schema already made true. It pins the clause
against future tightening rather than demonstrating a red-to-green move. The
existing conformance suite (`tests/test_sers_conformance.py`, including every
receipt in `docs/sers/receipts/` and every poison fixture) passes unchanged.

### AC4: A factorial design with two crossed factors is expressible without hand-editing the runner

Built: `cross_factorial(factors)` in `arms.py` expands crossed factors into the
cartesian product of their levels as the declared arm set. Arm names are
composed from the design (`factor_level` fragments joined by `__`, e.g.
`parent_present__specialist_absent`), so a receipt reader can read the design
off the names. A composed invalid name fails the expansion.

Tests: `TestCrossFactorial::test_two_crossed_factors_expand_to_the_four_cells`
expands the motivating design (parent x specialist, the absent level carrying a
placebo body by path) and checks which bodies land in which cell;
`test_factorial_runs_without_hand_editing_the_runner` runs the four expanded
arms through the stock runner and asserts one arm_samples row per arm;
`test_factorial_expansion_refuses_a_composed_ill_formed_name` pins fail-fast on
a composed invalid name.

Observed: at the pre-change baseline (`f57182e -- src/skill_harness`) pytest
reported `found no collectors ... ImportError while importing test module`; the
expander does not exist there. At `HEAD` all pass.

### AC5: A red demonstration shows the runner refusing a config whose declared arms and receipt arms disagree

Built: `RunConfig.receipt_arm_names()` names the vocabulary a receipt for the
run declares (declared arm names; `("full", "null")` for a per-clause run with
no declared arms, which is what the SERS schema has always accepted for the
per-clause instrument). `assert_receipt_arms_match` is the set-equality check in
both directions, order-insensitive, refusing duplicates and an empty list.
`run_arms` performs it pre-flight on a `receipt_arms` argument, before any run
row or spend.

Tests: `TestReceiptArmsAgreement::test_run_arms_refuses_a_disagreeing_receipt_arm_set`
(declared `{parent_only, both}` vs receipt `{null, full}`; asserts zero run rows
and zero arm_samples rows afterwards),
`test_run_arms_accepts_a_matching_receipt_arm_set`,
`test_string_form_of_a_single_receipt_arm_is_normalized`,
`test_assert_receipt_arms_match_direct`,
`test_default_run_receipt_vocabulary_is_null_full`.

Observed: before the change the five tests failed with
`ImportError: cannot import name 'ReceiptArmsMismatchError'` (and the `run_arms`
cases also failed on the unknown `receipt_arms` parameter). After the change all
pass.

### AC6: An arm declared but never sampled fails the run rather than reporting silently

Built: after the sampling loop and before `completed_at` is stamped,
`run_arms` reads `count_arm_samples_by_arm` back from evidence and refuses to
call the run complete while any declared arm holds zero rows: it writes
`run_progress.state = 'failed'` with error `declared_arm_never_sampled: <names>`,
leaves `runs.completed_at` NULL (the run did not fulfil its plan), and raises
`ArmNeverSampledError` naming the unsampled arms. Evidence is the authority the
gate reads, not the loop's own counter. Budget exhaustion still aborts through
the existing loud path (`BudgetAbortedError`) before this gate.

Tests: `TestDeclaredArmCompleteness::test_declared_but_never_sampled_arm_fails_the_run`
(a `samples_per_arm=0` plan must fail the run, and the test also asserts
`completed_at IS NULL`, progress state `failed`, and the error text) and
`test_every_declared_arm_sampled_passes_the_gate`.

Observed: before the change the zero-sample plan returned `ArmResult`s with
`samples_collected=0`, stamped the run `completed`, and did not raise; the test
failed with `ImportError: cannot import name 'ArmNeverSampledError'` at the
assertion line. The companion test
(`test_every_declared_arm_sampled_passes_the_gate`) passes before and after and
is a regression pin, not the demonstration.

## Storage: the new evidence table

A declared-arm run's unit of comparison has neither a clause nor a closed
condition name, so its subject outputs do not fit `evidence.samples`
(`condition` is CHECK-constrained to `('full','ablated','null')` and `clause_id`
is a NOT NULL FK). Migration `1200_arm_samples.sql` creates `arm_samples`:
sample_id PK, run_id FK, `arm` (NOT NULL, with a SQL CHECK floor mirroring
`ARM_NAME_PATTERN` via GLOB clauses), `sample_index`, subject model and seed,
output text and SHA-256, sampled_at, the A41 per-call cost columns, and
`UNIQUE(run_id, arm, sample_index)` as the idempotency key. Both append-only
triggers raise `append_only_violation: arm_samples`, pinned by
`test_arm_samples_table_is_append_only` and
`test_arm_samples_unique_per_arm_index`. The write model `ArmSampleWrite`
validates the arm name against the shared vocabulary floor
(`test_arm_sample_write_model_refuses_ill_formed_arm`); the runner enforces
membership in the run's declared set. The A41 reconciler sums
`samples.usd` and `arm_samples.usd` together
(`test_reconciler_counts_arm_sample_costs` pins that an in-sync arm run needs no
back-fill row).

## Registered documents updated

`tests/test_assurance_static_analysis_171.py` requires a coverage row for every
module under `src/skill_harness/ablation/`. The first full-suite run failed
exactly there (`StopIteration` for `ablation/arms.py`). `arms.py` now carries a
row in `docs/assurance/coverage-floors.md` (26 branches, 0 uncovered, 100.0%,
measured 2026-09-21 under `tests/ablation/test_arms.py`, the only selection that
reaches it; `grep -rl "ablation.arms"` over `tests/` and `src/` returns that
test, the runner, and the storage vocabulary constant) with a dated paragraph in
the report's later-rows section; the later-row tallies in the `matched_bridge`
paragraph and in the `docs/receipts-index.md` entry were updated to count the
third later row. Mutation reads `absent` (#166 predates the module), so the
attention rule flags the row. The suite failure that first surfaced this miss
was the only red in the full suite run and is fixed by this commit.

## Mutation campaign

The ticket names no mutation receipt, so no `docs/assurance/` receipt was
generated through `scripts/mutation_receipt.py`, whose MUTANTS registry is
populated per receipt. A hand-run campaign of six mutants was applied instead,
each by editing the shipped source, running the named selection, and reverting
(`git status` clean after the pass). Each mutant was killed by the named
assertion:

| Mutant | Change | Killed by |
| --- | --- | --- |
| M1 gate-dropped | `unsampled` forced to `[]` in `run_arms` | `TestDeclaredArmCompleteness::test_declared_but_never_sampled_arm_fails_the_run` |
| M2 receipt-check-skipped | pre-flight `if receipt_arms is not None:` to `if False:` | `TestReceiptArmsAgreement::test_run_arms_refuses_a_disagreeing_receipt_arm_set` |
| M3 one-directional-check | set equality replaced by receipt-subset-of-declared | `TestReceiptArmsAgreement::test_assert_receipt_arms_match_direct` |
| M4 duplicate-assembly-allowed | resolver equality check to `if False:` | `TestResolveArmAssemblies::test_two_arms_resolving_to_the_same_assembly_are_refused` |
| M5 non-first-arm-write-skipped | evidence write skipped for every arm but the first | `TestRunArms::test_run_samples_every_declared_arm` |
| M6 frontmatter-sent | `parsed.body` replaced by a raw file read | `TestArmIncludesForeignBodyByPath::test_path_body_is_read_verbatim_without_frontmatter` |

All six were KILLED by the named assertion. Known limit, stated rather than
hidden: a mutant that reads the completeness counts from the loop's in-memory
counter instead of from evidence survives the zero-sample demonstration, because
the counter and the table agree there. Constructing that divergence from outside
requires patching the write path, which the mutation standard forbids as a
receipt; the happy-path row-count assertions (`counts == {...}`) are what stand
between a skipped write and a green suite.

## Gate

- `ruff check src tests scripts` — pass.
- `ruff format --check src tests scripts` — pass (364 files).
- `mypy --strict src/ tests/` — pass (345 source files).
- `python scripts/drift_check.py` — PASS, all 21 live contracts hold.
- `pre-commit run ban-raw-sqlite-connect --all-files` and
  `ban-raw-oracle-verdicts --all-files` — pass.
- `python scripts/release_gate.py` — PASS (7 of 8 gates ran; tag-match G6
  self-skips on a non-tag local ref).
- Full suite `PYTHONHASHSEED=0 pytest -q -m "not live and not calibration and
  not assurance"` — 3,209 passed, 31 skipped, 2 xfailed, and exactly one
  failure: the #171 coverage-floors registry row for the new module, fixed in
  commit `4c64ed0`; that test file passes 3/3 after the fix.

## Scope boundary

Scoring the declared-arm contrasts (the 2x2 interaction estimate for the
composition study) is a separate ticket; the ticket text states the number as
`#___`, so no claim is made here about which number it is. No CLI wiring was
built: the acceptance criteria name the runner and the receipt, and the CLI
surface is not among them. Resume for declared-arm runs is not built; no
criterion asks for it, and the `UNIQUE(run_id, arm, sample_index)` idempotency
key is in place for whoever does.

Next action owed by this change: the scoring ticket designs the factorial
contrast over `arm_samples`; the runner now records the arm set both in
`runs.config_json` and in `subject_identity.arms` of the receipt, so the
scoring ticket can read the design from evidence.
