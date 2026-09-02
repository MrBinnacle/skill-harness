# Mutation receipt: the non-finite score refusal (#363)

**Standard:** #341. **Repair:** #363, filed from the item 8 detector (#350, PR #364).
**Finding:** `docs/findings/paired-ingest-nan-score-silent-tie.md`.
**Generator:** `scripts/mutation_receipt.py`. **Machine-readable record:**
`docs/assurance/nan-score-refusal-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/subject/ingest.py` at
`sha256:1eaefbaed5e14369a7c192c9737532228e419bd9016067a853abafe743374bdc`.
**Commit at generation:** `ae9ab3c` — informational only. A rebase rewrites it and later
commits move HEAD past it, so currency is checked against the digest above by
`tests/test_mutation_receipt.py`. **Python:** 3.13.1.

**Regenerated 2026-09-01 for #387.** The first generation (commit `210ac93`, digest
`abf32c6e6427`) attested to the ingest module before #387 rewrote it (treatment = exposure,
invocation = stratifier). Regenerated again after the config_json exposure shape fix
(`value`/`passes`/`epochs` for the #388 delivery reader). The three mutants were re-run
by the same generator; all three anchors were still present and all three kills held. The
results table below is unchanged in substance and was re-measured, not carried.

Each case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. `PYTHONPATH` pins every case to its own sources, because the editable install would
otherwise resolve `skill_harness` to the main repository and each case would silently test
another tree's code.

Per case the generator records and asserts: the worktree HEAD, the `module.__file__` actually
imported, the clean and mutant source digests, that those digests differ, that the clean
baseline **passes first** with **nonzero collection**, the failing test node under the mutant,
that the mutant **imports** (a stillborn mutant is not a kill), and that the production tree is
byte-unchanged afterwards. All three cases resolved `skill_harness.subject.ingest` inside their
own worktree, and the production digest was identical before and after.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-N1 | model layer | remove `allow_inf_nan=False` from `ParsedSample.score_value` | **KILLED** | `test_paired_arm_epoch_adversarial.py::test_nan_score_is_refused_or_fails_closed` and `test_subject_ingest.py::test_parsed_sample_refuses_non_finite_score_at_the_model_layer` |
| M-N2 | parse path | disable the `math.isfinite` guard in `_score_to_float` | **KILLED** | `test_subject_ingest.py::test_score_to_float_refuses_non_finite_scores` |
| M-N3 | parse path | narrow the guard to NaN only, letting an infinite score through | **KILLED** | `test_subject_ingest.py::test_score_to_float_refuses_non_finite_scores` |

Three hand-chosen mutants. **No mutation score is reported**, because three cases cannot support
one; each case is a named obligation, not a sample.

## What M-N1 measures, and why the fix is not in the parse helper

PR #364's receipt recorded M4 as an honest survivor: adding a NaN guard to `_score_to_float`
did not turn the item 8 detector red, because that detector constructs `ParsedSample` directly
and the write path never calls the helper. M-N1 is the converse case, and it kills. Removing the
model-layer constraint while leaving the parse-path guard in place restores exactly the PR #364
configuration, and the paired detector goes red again with `NAN_SCORE_BECOMES_TIE`
(`observations=[0.5, 1.0, 1.0]`).

Read together, the two cases locate the enforcing surface by measurement rather than by
preference: the parse-path guard is necessary for logs arriving through `parse_eval_log`, and it
is not sufficient for anything that builds the model itself.

M-N1 was re-measured after code review tightened the detector. The detector now guards only the
NaN-carrying construction and requires the refusal to name `score_value`, rather than catching
any `ValidationError` from either log. The kill is unchanged, which is what makes the tightening
a narrowing of the claim rather than a loss of one.

## What the parse-path cases measure

M-N2 removes the guard entirely. M-N3 keeps it but narrows it to NaN, so a positive or negative
infinity passes. M-N3 exists because the helper's test asserts on all three non-finite values and
a test that only ever exercised NaN would leave the `inf` clause decorative. Both kills come from
the same named test, and its message names the value that got through.

## What this receipt refuses to claim

It does not claim a mutation score, adequacy of the test suite as a whole, or that non-finite
scores have ever appeared in a production `.eval` log. No historical re-scan of stored logs was
run. It says three specific defects are detected, in isolated worktrees, against a baseline that
passed first.

## The generator refuses rather than exiting green

A case whose verdict is `ANCHOR_ABSENT`, `INVALID_BASELINE`, `INVALID_ISOLATION`, `NO_OP`,
`STILLBORN` or `UNKNOWN` measured nothing, so the generator exits non-zero and names it. A
receipt containing such a case attests to nothing while still rendering as a table of verdicts.
`SURVIVED` is deliberately not in that set: a preserved survivor is a finding, and folding it
into an exit code would create pressure to delete it rather than report it.

*Revisit if:* a caller reaches `oracle_verdicts.observation` by a third path that constructs
neither `ParsedSample` nor calls `_score_to_float`, which would put a third surface in scope.
