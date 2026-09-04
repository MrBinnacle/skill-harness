# Mutation receipt: the exposure refusal predicates at paired ingest (#387)

**Standard:** #341. **Build:** #387, from the #384 ruling (Amendment 3 of
`docs/findings/v0.2-preregistration.md`, landed by #386).
**Generator:** `scripts/mutation_receipt.py --select 387`. **Machine-readable record:**
`docs/assurance/exposure-refusal-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/subject/ingest.py` at
`sha256:d3064dd5c232d878b5c98a940bf3f7348c23747572f87f68e8cb14bbc31dea48`.
**Commit at generation:** `228fbe1` — informational only. A rebase
rewrites it and later commits move HEAD past it, so currency is checked against the digest
above by `tests/test_mutation_receipt.py`. **Python:** 3.13.1.

**Regenerated 2026-09-04 for #424** (the oracle metric identity moved to 0.5.0, digest
`ae28a10512c6` to `d3064dd5c232`; both mutants re-run, both kills held by the same detectors).

**Regenerated 2026-09-03 for #416 (#391)** (the oracle metric identity moved to 0.4.1, digest
`958e44f8261d` to `ae28a10512c6`; both mutants re-run, both kills held by the same detectors).

Each case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. `PYTHONPATH` pins every case to its own sources, because the editable install would
otherwise resolve `skill_harness` to the main repository and each case would silently test
another tree's code.

Per case the generator records and asserts: the worktree HEAD, the `module.__file__` actually
imported, the clean and mutant source digests, that those digests differ, that the clean
baseline **passes first** with **nonzero collection**, the failing test node under the mutant,
that the mutant **imports** (a stillborn mutant is not a kill), and that the production tree is
byte-unchanged afterwards. Both cases resolved `skill_harness.subject.ingest` inside their own
worktree, and the production digest was identical before and after.

## What the predicates are

After the #384 ruling the treatment at paired ingest is **exposure** (the skill's description
present in the agent's transcript) and invocation is a recorded stratifier. `_validate_pair`
refuses two shapes as apparatus errors:

- **(a) `UnexposedFullEpochError`:** a Full-arm epoch whose exposure was not detected. The
  treatment was not delivered, so the epoch measures nothing about the skill.
- **(b) `NullArmContaminationError`, channel (c):** a Null-arm epoch whose exposure was
  detected. The #46 invocation half of this predicate predates #387 and is not re-attested
  here; its structural fixture (0/22) is pinned by `test_null_epoch_invoked_refuses_0_22_fixture`.

## Results

| mutant | obligation | mutation | verdict | killing tests |
|---|---|---|---|---|
| M-X1 | 387-unexposed-full | empty the comprehension behind predicate (a): `unexposed` is always `[]`, so an unexposed Full epoch writes | **KILLED** | `test_subject_ingest.py::test_full_arm_unexposed_refuses` and `test_subject_ingest.py::test_unexposed_full_epoch_refuses` |
| M-X2 | 387-null-contamination | empty the comprehension behind the channel-(c) half of predicate (b): `null_contaminated_exposed` is always `[]`, so an exposed Null epoch writes while the invocation half stays | **KILLED** | `test_subject_ingest.py::test_null_arm_exposed_refuses` and `test_subject_ingest.py::test_null_epoch_exposed_refuses` |

Two hand-chosen mutants. **No mutation score is reported**, because two cases cannot support
one; each case is a named obligation, not a sample.

## Why each mutant is shaped this way

Both mutants remove a predicate by emptying the set it tests, rather than by deleting the
`raise`. Emptying the comprehension leaves the exception class, its message and its call site
in place, so the mutant compiles and imports, and the only behaviour that changes is that the
refusal can no longer fire. A mutant that deleted the `raise` would also remove the only use of
the error class in that block and risk a lint-shaped kill rather than a behavioural one.

M-X2 is deliberately narrow. Predicate (b) has two halves, invocation (#46) and exposure
(#387). Emptying only the exposure half is what shows the widening is load-bearing: under
M-X2 an invoked Null epoch still refuses, and the two named tests go red only because an
exposed-but-not-invoked Null epoch now writes.

## What this receipt refuses to claim

It does not claim a mutation score, adequacy of the test suite as a whole, or anything about
the v2 exposure **detector** (`detect_skill_exposure`). The detector's own behaviour is pinned
by the parse-level tests in `tests/test_subject_ingest.py`; this receipt attests only that the
two refusal predicates downstream of it are enforced. It says two specific defects are
detected, in isolated worktrees, against a baseline that passed first.

The two monkeypatch tests the factory build added for acceptance criterion 7
(`test_mutation_unexposed_full_refusal_removes_predicate` and
`test_mutation_null_contamination_refusal_removes_predicate`) stay in the suite as
supplementary checks. They are not the standard's artifact: a monkeypatched validator is not
a source-level mutant run in an isolated worktree.

## The generator refuses rather than exiting green

A case whose verdict is `ANCHOR_ABSENT`, `INVALID_BASELINE`, `INVALID_ISOLATION`, `NO_OP`,
`STILLBORN` or `UNKNOWN` measured nothing, so the generator exits non-zero and names it.
`SURVIVED` is deliberately not in that set: a preserved survivor is a finding.

*Revisit if:* a non-`claude_code` solver's transcript lacks the skill listing, which would move
the exposure detector's channel and with it the meaning of predicate (a); or a third refusal
predicate lands at the seam without a case here.
