# Mutation receipt: the Gate-2 discordant stopping migration (#368)

**Standard:** #341. **Build:** #368, Path C migration (Gate-2 discordant stopping for the ablation lane).
**Machine-readable record:**
`docs/assurance/halfupdate-tie-migration-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/ablation/gate2_stopping.py` at
`sha256:b6b9e5c04b705ebf0e02cab01f42cd1391333d23d0d5af184f3153044cf3c99a`.
**Commit at generation:** `36bf46a` — informational only. A rebase
rewrites it and later commits move HEAD past it, so currency is checked against the digest
above by `tests/test_mutation_receipt.py`. **Python:** 3.13.15.

Each case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. `PYTHONPATH` pins every case to its own sources, because the editable install would
otherwise resolve `skill_harness` to the main repository and each case would silently test
another tree's code.

Per case the generator records and asserts: the worktree HEAD, the `module.__file__` actually
imported, the clean and mutant source digests, that those digests differ, that the clean
baseline **passes first** with **nonzero collection**, the failing test node under the mutant,
that the mutant **imports** (a stillborn mutant is not a kill), and that the production tree is
byte-unchanged afterwards. All cases resolved `skill_harness.ablation.gate2_stopping` inside
their own worktree, and the production digest was identical before and after.

## What the predicates are

The Gate-2 discordant stopping wrapper (`gate2_stopping_decision`) enforces three invariants:

- **Scalar fallback is load-bearing:** when Gate-2 returns UNRESOLVED, the scalar thresholds
  on the discordant-only `Beta(1+w, 1+l)` determine the stop decision. Removing the fallback
  causes tie-heavy scenarios that should pass to return inconclusive.
- **Threshold correctness:** the pass/fail probability thresholds (0.95/0.05) determine
  whether the scalar fallback certifies a stop. Swapping them inverts the decision for
  high-probability scenarios.
- **Posterior correctness:** the posterior parameters are derived from the discordant-only
  `Beta(1+w, 1+l)`, matching the drop-ties recompute. Zeroing them breaks the parameter
  agreement with drop-ties.

## Results

| mutant | obligation | mutation | verdict | killing tests |
|---|---|---|---|---|
| M-G1 | 368-scalar-fallback | Remove the scalar fallback: replace the `elif p >= PASS_PROB_THRESHOLD:` / `elif p <= FAIL_PROB_THRESHOLD:` branches with `else: should_stop = False; reason = None`. Tie-heavy scenarios that should pass (P >= 0.95) now return inconclusive | **KILLED** | `test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[win-heavy-many-ties]` |
| M-G2 | 368-threshold-correctness | Swap the pass and fail thresholds: replace `p >= PASS_PROB_THRESHOLD` with `p <= PASS_PROB_THRESHOLD`. High-probability scenarios (P=0.99) now fail the wrong condition and return inconclusive | **KILLED** | `test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[win-heavy-many-ties]` |
| M-G3 | 368-posterior-correctness | Zero the posterior parameters: replace `alpha = 1.0 + wins` / `beta_param = 1.0 + losses` with `alpha = 1.0` / `beta_param = 1.0`. The posterior no longer matches the drop-ties recompute | **KILLED** | `test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_migration_collapses_divergence_on_extreme_fixture` |

Three hand-chosen mutants. **No mutation score is reported**, because three cases cannot support
one; each case is a named obligation, not a sample.

## Why each mutant is shaped this way

M-G1 removes the scalar fallback by collapsing the elif branches into an else. This is the
most direct test of the fallback's load-bearing status: without it, Gate-2 UNRESOLVED always
returns inconclusive, regardless of the scalar probability.

M-G2 swaps the pass/fail thresholds in the scalar fallback. This tests that the thresholds
are applied in the correct direction: P >= 0.95 should trigger PASSED, not P <= 0.95.

M-G3 zeros the posterior parameters. This tests that the posterior is computed from the
discordant-only Beta(1+w, 1+l) and not from a fixed or incorrect distribution.

## What this receipt refuses to claim

A mutation score — three hand-chosen mutants cannot support one. Adequacy of the full
`test_halfupdate_tie_sensitivity.py` test suite as a whole. That the Gate-2 decision rule
(gamma, delta_min, q_min) is tested here (it is tested by `tests/test_oc_gate2.py`). That
the zero-tie scalar path is tested here (it is tested by the existing `stopping.py` seam
tests). That the runner wiring itself is mutated here (pinned by
`test_runner_imports_discordant_accumulator` and `test_runner_config_records_ratification_thresholds`).

## The generator refuses rather than exiting green

A case whose verdict is `ANCHOR_ABSENT`, `INVALID_BASELINE`, `INVALID_ISOLATION`, `NO_OP`,
`STILLBORN` or `UNKNOWN` measured nothing, so the generator exits non-zero and names it.
`SURVIVED` is deliberately not in that set: a preserved survivor is a finding.

*Revisit if:* the Gate-2 stopping wrapper moves off `gate2_stopping.py`, or a third
load-bearing guard lands at the seam without a case here.
