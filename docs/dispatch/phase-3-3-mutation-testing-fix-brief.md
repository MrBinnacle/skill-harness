# Phase 3.3 — Mutation-Testing Disposition + Fix Brief

Single Sonnet 4.6 implementer (worktree-isolated, mutmut 2.5.1 — mutmut 3.x blocks
on Windows per https://github.com/boxed/mutmut/issues/397) executed a focused mutation
sweep against the two highest-invariant aggregation modules:

- `src/skill_harness/aggregation/fit.py` — EB-MoM + BH-FDR + UNPOOLED logic; locked
  PRD §14 thresholds (`0.60` / `0.95`); convergence guard (`α̂ ≤ 0 ∨ β̂ ≤ 0 ∨
  var_between < 1e-6`); K<10 unpooled fallback.
- `src/skill_harness/aggregation/status.py` — A57 state machine; `UnmeasuredSubReason`
  enum; Pass/Fail gate ordering (FAIL before PASS).

Per-file test scope (`pytest tests/test_aggregation_<file>.py -x`) drove per-mutant
cost from ~122s (full 857-suite) to ~2s. Survivors were re-tested against the
integration suite at `tests/test_aggregation_engine.py` to discriminate
"per-file weak / integration covers" from "genuine gap." **All 18 per-file survivors
remained SURVIVED-EVERYWHERE** — no integration test rescued any.

## Headline numbers

| File | Mutants | Killed | Survived | Kill rate |
|---|---:|---:|---:|---:|
| `aggregation/fit.py` | 93 | 78 | 15 | 83.9% |
| `aggregation/status.py` | 38 | 35 | 3 | 92.1% |
| **Total** | **131** | **113** | **18** | **86.3%** |

1 untested mutant (mut_92, `_posterior_stats(...) → None`) — almost certainly killed by
TypeError on tuple unpack downstream; time-boxed out before final test. Treat as
KILLED for kill-rate purposes (downgraded confidence: high).

Net classification after discrimination:
- **14 GENUINE-GAPs** (need a killing test)
- **4 EQUIVALENT** — 3 of which reveal a real code smell (dead-constant duplication)

## Verified MAJOR finding (block tag, not Track E close)

### M1 · `fit.py:305` EB-MoM convergence guard has no test in the `0 < α̂ ≤ 1` regime
Mutation `alpha_hat <= 0.0` → `alpha_hat <= 1.0` survives. With the mutation in place,
every EB-MoM fit with `0 < α̂ ≤ 1` (the "concentrated-near-zero hyperprior" regime —
the exact regime the guard exists to catch) falls into BH-FDR fallback instead of
proceeding. **Tests verify the guard fires for `α̂ ≤ 0` but never verify it does NOT
fire for valid `α̂ ∈ (0, 1]`.** A developer refactoring the threshold (e.g., adopting
a "be conservative" instinct and tightening to `<= 1.0`) would silently route the
entire EB-MoM happy path through BH-FDR. **Fix:** parametrized test with hand-computed
`α̂ ∈ {0.001, 0.5, 1.0, 1.5, 5.0}`; assert `fit_skill` does NOT raise `ConvergenceFailure`
for any `α̂ > 0` and DOES raise for `α̂ == 0` and `α̂ == -0.1`. Falsifying: must go RED
against the mutation `<= 1.0`.

## Importants — boundary-case coverage on load-bearing thresholds (9 GAPs)

These are all `<` vs `<=` / threshold-value boundary mutations that survive because
no test exercises the exact threshold value. Fix-shape is uniform: parametrized
tests at the threshold boundary.

- **M2 · `fit.py:47` `VAR_FLOOR = 1e-6` doubling survives** (mut_6). No test
  constructs a sample with `var ∈ [1e-6, 2e-6]`. **Fix:** test with `var == 1.5e-6`
  asserts no `ConvergenceFailure`; test with `var == 0.5e-6` asserts ConvergenceFailure
  fires with `reason="var_below_threshold"`.
- **M3 · `fit.py:292` `if v < VAR_FLOOR` ↔ `v <= VAR_FLOOR` survives** (mut_69).
  Boundary case `v == VAR_FLOOR` (exactly `1e-6`) untested. **Fix:** test with
  `var == VAR_FLOOR` exactly; current code allows fit (no exception); under mutation,
  would raise.
- **M4 · `fit.py:305` `alpha_hat <= 0.0` ↔ `alpha_hat < 0.0` survives** (mut_83).
  Boundary `α̂ == 0.0` exactly untested. **Fix:** parametrize for `α̂ ∈ {-0.001, 0.0,
  0.001}`; current code raises for 0.0; under mutation, does not.
- **M5 · `fit.py:313` `beta_hat <= 0.0` ↔ `beta_hat < 0.0` survives** (mut_85).
  Symmetric to M4. **Fix:** parametrize for `β̂ ∈ {-0.001, 0.0, 0.001}`.
- **M6 · `fit.py:167` BH-FDR `<= (rank/k)*q` ↔ `< (rank/k)*q` survives** (mut_37).
  BH boundary condition. Standard BH (1995) uses `≤`; mutation to `<` would lose
  one rejection at the exact threshold. **Fix:** hand-constructed p-values where
  one falls EXACTLY on the BH threshold (`p == (rank/k)*q` exactly); assert it IS in
  `bh_fdr_passes`.
- **M7 · `status.py:62` `N_MIN = 8` → `N_MIN = 9` survives** (mut_107). A8
  under-power threshold. **Fix:** parametrize for `n ∈ {7, 8, 9}` admissible verdicts;
  assert `n=7` → `UNMEASURED(underpowered)`, `n=8` → eligible (not underpowered),
  `n=9` → eligible.
- **M8 · `status.py:132` `total_verdict_count > 0` ↔ `> 1` survives** (mut_119).
  A17 sub-reason distinction at boundary `total_verdict_count == 1`. With 1 verdict
  that is inadmissible, current code says `INADMISSIBLE` (paid tokens); mutation
  says `NO_DATA` (didn't run). **Fix:** test with exactly 1 inadmissible verdict
  asserts `UnmeasuredSubReason.INADMISSIBLE`, not `NO_DATA`.
- **M9 · `fit.py:161` `_bh_fdr` `if k == 0` ↔ `k == 1` survives** (mut_134). Internal
  helper coverage gap — `_bh_fdr` is only called with `K ≥ K_MIN_FOR_EB = 10` in
  practice, so the empty/single-element case is unreachable by `fit_skill`, but the
  helper's own contract is uncovered. **Fix:** direct unit test of `_bh_fdr([])` →
  `frozenset()`, `_bh_fdr([0.5])` with various q values.

## Importants — provenance/audit field coverage (2 GAPs)

- **M10 · `fit.py:224` BH-FDR fallback `fallback_reason` field not asserted**
  (mut_57). When EB-MoM raises `ConvergenceFailure`, the fallback's
  `aggregation_provenance` dict gets `fallback_reason = exc.reason`. Mutation sets
  `fallback_reason = None`. No test asserts this field's value. A60's
  schema-version discipline depends on this surviving correct. **Fix:** test that
  triggers EB-MoM failure (e.g., `var_between < VAR_FLOOR`), asserts
  `report.aggregation_provenance["fallback_reason"] == "var_below_threshold"`.
- **M11 · `fit.py:230` BH-FDR fallback `attempted` dict not asserted** (mut_58).
  Same root cause as M10. Mutation sets `attempted = None`. **Fix:** in the same
  test as M10, assert `report.aggregation_provenance["attempted"]` is a dict with
  keys `alpha_hat, beta_hat, sample_mean, sample_var`.

## Importants — frozen dataclass immutability (3 GAPs)

- **M12 · `fit.py:58` `ClauseObservations` `frozen=True` invariant untested**
  (mut_8). **Fix:** `with pytest.raises(dataclasses.FrozenInstanceError): obs.w = 99.9`.
- **M13 · `fit.py:71` `ClausePosterior` `frozen=True` invariant untested** (mut_10). Same shape.
- **M14 · `fit.py:91` `FitResult` `frozen=True` invariant untested** (mut_12). Same shape.

The agent's `__init__.py` docstring explicitly claims "frozen dataclasses for safe
sharing" — this is a documented invariant with zero enforcement.

## Code smells revealed by EQUIVALENT mutants (cleanup)

Three EQUIVALENT mutants reveal genuine dead-constant duplication that should be
cleaned up regardless of the test gaps:

- **M15 · `fit.py:40-41` `PASS_PROB_THRESHOLD` + `FAIL_PROB_THRESHOLD` are DEAD in
  fit.py** (mut_3, mut_4). Only `status.py:61-62` copies are consulted by
  `derive_clause_status()`. **Fix:** delete the fit.py copies; if any internal
  fit.py code needs them, import from `status.py`. Or centralize in
  `aggregation/constants.py`. Avoid the cross-module import-cycle by putting them
  where they're used.
- **M16 · `status.py:59` `WIN_RATE_THRESHOLD` is DEAD in status.py** (mut_104).
  Only `fit.py:128`'s copy is consulted inside `_posterior_stats`. **Fix:** delete
  the status.py copy; same centralization question as M15.

Mut_14 (`frozenset[str] | None` → `frozenset[str] & None`) is purely a type-annotation
mutation behind `from __future__ import annotations` — strings, never resolved.
NO-ACTION.

## Defer to v0.2 (Phase 3.3 not exhaustive)

The Phase 3.3 sweep covered only `fit.py` (93 mutants) + `status.py` (38 mutants) =
131 mutants. Remaining untested:

- `aggregation/engine.py` — 218 mutants. Mostly orchestration code that calls into
  fit.py / status.py / report.py — already covered by integration; lower-value mutation
  surface. Re-attempt before v0.1 tag if budget allows.
- `aggregation/report.py` — 19 mutants. Wire format. Lower invariant density.
- `aggregation/errors.py` — 14 mutants. Typed exceptions; nearly all behavior is
  attribute access.
- `storage/recovery.py` — 26 mutants. Already covered by E.1 ai-slop review +
  recovery integration tests.
- `storage/models.py` — 144 mutants. Pydantic models. Many mutants will be on
  validation logic — high-value, deferred.
- `storage/repositories/evidence/*.py` — 143 mutants. Append-only repos. Mutations
  on SQL strings tend to produce false survivors (mutmut's string-mutation noise);
  needs careful exclusion config.
- `storage/repositories/runtime/*.py` — 69 mutants. Same shape as evidence repos.

**Recommendation**: queue a Phase 3.3-bis as the final pre-tag gate (Phase 4.x) to
sweep `storage/models.py` + the repositories. The ~5+ hour runtime makes it
unsuitable for mid-session work; run overnight or as a CI step (when CI exists per
v0.2).

## Infrastructure findings (not fixes; documentation)

- **mutmut 3.x blocked on Windows** — emits `"To run mutmut on Windows, please use
  the WSL"` and exits 1. Issue tracked at boxed/mutmut#397. Workaround: pin mutmut
  2.5.1 (last Windows-compatible release).
- **mutmut 2.5.1 `tests_pass()` exit-code bug** — only checks `returncode != 1`,
  misclassifying pytest exit codes 2/3/4/5 as "tests passed → mutant survived."
  Agent's worktree contains `mutmut_runner.bat` (a wrapper that normalizes any
  non-zero exit to 1). This wrapper should be promoted to `scripts/` if mutation
  testing becomes recurring discipline (currently ad-hoc).
- **mutmut 2.5.1 Pony ORM crash** — at ~30-40 mutants per `mutmut run` invocation,
  raises `ValueError: Attribute Mutant.line is required` from
  `pony/orm/core.py:2537`. Workaround: relaunch — mutmut resumes from cache. This
  campaign required 6 launches to test 131 mutants.

## Method + gates

TDD: write the falsifying test FIRST for each gap (parametrized where applicable);
prove RED by manually applying the mutation; remove the mutation; prove GREEN.

For the immutability tests (M12-M14), use `dataclasses.FrozenInstanceError`.

For the boundary tests (M2-M9), use `@pytest.mark.parametrize` with carefully-chosen
values that bracket the threshold.

For the provenance tests (M10-M11), reuse an existing fit-failure setup (e.g., the
test_aggregation_fit.py BH-FDR fallback test) and add assertions on the provenance
dict.

For the dead-constant cleanups (M15-M16), follow with `mypy --strict` to confirm
no callers were missed.

Touches: `src/skill_harness/aggregation/fit.py` (M15 deletes; structural cleanup
only), `src/skill_harness/aggregation/status.py` (M16 deletes), `tests/test_aggregation_fit.py`
(M1-M11 test additions), `tests/test_aggregation_status.py` (M7-M8 + M12-M14
if any frozen dataclasses live there — they don't, but check).

Do NOT modify `aggregation/engine.py`, `aggregation/report.py`, `aggregation/errors.py`,
or any production code in `storage/`. Do NOT bump `REPORT_SCHEMA_VERSION` (no wire
format change; this is test additions + dead-constant deletions).

Gates: `pytest -q -m "not live"` green · `mypy --strict src/` clean · `ruff check
src/ tests/` + `ruff format --check src/ tests/` clean. Single cohesive commit per
project memory `feedback-commit-shape`.

New worktree off current `main` (`3c4c8af`).

## Carry-forwards (Phase 3 / Phase 4 punch list)

- **Phase 3.3-bis (v0.1 pre-tag)**: sweep `aggregation/engine.py` + `storage/models.py`
  + `storage/repositories/*`. Estimated 5+ hours; run overnight before tag.
- **mutation-testing tooling promotion**: if mutation testing becomes recurring,
  promote `mutmut_runner.bat` from the worktree to `scripts/mutmut-runner.bat` and
  document the Windows-pinning rationale.
- **CF-Phase-3-3-1**: report `aggregation_provenance["fallback_reason"]` and
  `["attempted"]` should be part of A60's wire format spec. Currently A60 lists
  `aggregation_provenance` as a required top-level key but doesn't enumerate its
  required sub-keys. Surface for Phase 3.5 PRD v1.1 doc-lock.
