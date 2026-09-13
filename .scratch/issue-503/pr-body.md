# #503 — Persist the refusal reason; one closed vocabulary names it

Closes #503. Two defects stopped a refusal from being auditable: the reason
was never persisted to storage, and the runner's two refusal literals lived
outside the declared `UnmeasuredSubReason` enumeration. This change fixes
both.

## Modelling decision (criterion 4)

The runner's two existing literals each map to a NEW member of
`UnmeasuredSubReason` (`aggregation/status.py`). I did not fold them onto
existing members, because none genuinely covers the condition:

- `tier2_uncalibrated` -> `TIER2_UNCALIBRATED`. The runner's BLOCKER-1 gate
  fires on `oracle_tier != 1 OR axis not in self._scorers` — a pre-sampling
  condition. The existing `MECHANICAL_VACUOUS` member names an axis-registry
  scoreability property recomputed at aggregation; it does NOT cover a
  tier-2 clause whose axis IS registered (the scorer can see the axis, the
  tier is what blocks). A test pins that the two are distinct members.
- `length_confounded` -> `LENGTH_CONFOUNDED`. The runner's QUAL-1 gate fires
  when the operator cannot meet length tolerance before sampling. No
  existing member names an operator-tolerance refusal.

The enum stays the single source of truth: the write model validates against
the live enumeration, and the runner now assigns members (not free-form
strings). Same string values keep the existing
`result.unmeasured_reason == "tier2_uncalibrated"` assertions passing
(StrEnum compares by value).

## Criterion 4 — the two literals map to named members

What I built: added `TIER2_UNCALIBRATED` and `LENGTH_CONFOUNDED` to
`UnmeasuredSubReason`; replaced the runner's string literals with the enum
members.

Test that pins it: `tests/test_issue_503_unmeasured_reason.py::
TestRunnerLiteralsAreEnumMembers` — asserts each member exists, equals the
literal's value, and that `TIER2_UNCALIBRATED` is distinct from
`MECHANICAL_VACUOUS`.

Observed fail-before / pass-after: before the change the class had no
`TIER2_UNCALIBRATED`/`LENGTH_CONFOUNDED` attributes, so the tests raised
`AttributeError` (confirmed in the run log). After, the three tests pass.

## Criterion 2 — one population, not two

What I built: the runner's `ClauseResult.unmeasured_reason` now carries
`UnmeasuredSubReason` members (the runner assigns
`UnmeasuredSubReason.TIER2_UNCALIBRATED` / `LENGTH_CONFOUNDED`, never a
free-form string). A reader grouping refusals by sub-reason gets one
vocabulary shared with aggregation.

Note on the static type: the dataclass field stays annotated `str | None`.
An existing test (`tests/test_ablation_report_verdict_id.py:264`) constructs a
real `ClauseResult` with the literal string `"tier2_uncalibrated"`, which
`mypy --strict` rejects under a narrowed `UnmeasuredSubReason | None`
annotation. The constraint says existing tests are not mine to edit and, when
one blocks a change, to change my code; so the field's static annotation was
left `str | None` while the runner narrows the VALUES to enum members. The
vocabulary is enforced where it bites: the runner emits only members, and
the write model rejects a non-member at the storage boundary (criterion 3).
This satisfies the acceptance criterion ("grouping returns one population")
because the runner and the store produce values drawn from the one
enumeration.

Test that pins it: `TestRunnerYieldsEnumNotString` — runs a tier-2 refusal
and a length-confounded refusal and asserts
`isinstance(result.unmeasured_reason, UnmeasuredSubReason)` and the exact
member.

Observed fail-before / pass-after: before the change the runner assigned the
bare string `"tier2_uncalibrated"`, which is not an `UnmeasuredSubReason`
instance, so `isinstance(...)` failed. After, both refusal paths yield enum
members and the tests pass.

## Criterion 1 — readable from storage without re-running

What I built:

- Migration `1100_clause_run_outcomes.sql` — append-only evidence table
  `clause_run_outcomes(run_id, clause_id, unmeasured_sub_reason, written_at)`,
  PRIMARY KEY `(run_id, clause_id)`, with `BEFORE UPDATE`/`BEFORE DELETE`
  triggers raising `append_only_violation` (the structural test in
  `test_store_bricking_deadlock.py` requires both on every evidence table).
  A SQL CHECK names the enumeration literals as a defence-in-depth floor.
- `storage/models.py:ClauseRunOutcomeWrite` — the write shape, validated
  against the live enum (see criterion 3).
- `storage/repositories/evidence/runs.py` — `insert_clause_run_outcome` /
  `list_clause_run_outcomes_for_run` / `get_clause_run_outcome`. The
  repository lives in `runs.py` (outcomes are children of a run) so the
  evidence-repo module count stays pinned at 13
  (`test_evidence_repo_surface.test_expected_module_count`). Insert uses
  `INSERT OR IGNORE` so a refused clause re-refuses deterministically on
  resume (A40 idempotency) without a PRIMARY KEY conflict.
- `ablation/runner.py:_persist_refusal_sub_reason` — writes one row per
  refused clause, called from both `run_ablation` and `resume_ablation`. A
  measured clause writes NO row (scope: no back-fill; a run that recorded no
  reason keeps none).

Tests that pin it: `TestSubReasonReadableFromStorage` — after a tier-2
refusal and a length-confounded refusal, reads the sub-reason back from
storage via `list_clause_run_outcomes_for_run` and asserts the persisted
value; a measured run asserts NO outcome row is written.

Observed fail-before / pass-after: before the change there was no
`clause_run_outcomes` table, model, or repository, so the read-back test
raised `ImportError` / `OperationalError` (confirmed in the run log). After,
the refusal writes a row readable without re-running, and the measured-clause
test confirms refusals-only persistence.

Companion change: `docs/sers/sers.schema.json` — the SERS
`unmeasured_sub_reason` enum claims to mirror `UnmeasuredSubReason` exactly,
and `test_schema_unmeasured_sub_reason_enum_matches_code` enforces that. The
two new members were added to the schema in the same change so the drift
guard stays green.

## Criterion 3 — out-of-enum rejected rather than stored

What I built: `ClauseRunOutcomeWrite.known_sub_reason` validates
`unmeasured_sub_reason` against `{member.value for member in
UnmeasuredSubReason}` (the live enumeration — single source of truth) and
raises `ValueError` on a non-member, before any DB write. The migration's SQL
CHECK is a second, independent floor.

Tests that pin it: `TestOutOfEnumRejected` —
`test_write_model_rejects_value_outside_enumeration` constructs a write with
`"not_a_real_sub_reason"` and asserts `ValueError` matching
`unmeasured_sub_reason`; `test_write_model_accepts_every_enum_member` asserts
every current member is accepted.

Observed fail-before / pass-after: before the change `ClauseRunOutcomeWrite`
did not exist, so the rejection test raised `ImportError`. After, an
out-of-enum value is rejected by the write model, and a manual probe against
a fresh DB confirmed the SQL CHECK also rejects `bogus` and the append-only
trigger blocks `UPDATE`.

## Mutation campaign

No mutation receipt was named by the ticket, so `scripts/mutation_receipt.py`
was not run. The pinning tests were written to assert external behaviour
(read-back from storage, `isinstance` of an enum member, a `ValueError` on a
non-member), not internal branching; none monkeypatch the function it claims
to test.

## Scope

The refusal reason only. No change to verdicts, the paired gate, aggregation
semantics, or the oracle metric version. The aggregation state machine
(`derive_clause_status`) is unchanged; its existing `UnmeasuredSubReason`
members are untouched. No historical run was back-filled.

## Gate

`ruff check src tests`, `ruff format --check src tests`, and
`mypy --strict src/ tests/` are green on the committed tree. The test lane
`-m "not live and not calibration and not assurance"` passes
(`test_issue_503_unmeasured_reason.py` plus the ablation, storage,
SERS-conformance, evidence-repo-surface, and store-bricking suites).
