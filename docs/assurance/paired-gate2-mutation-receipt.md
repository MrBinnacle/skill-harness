# Mutation receipt: the ratification binding and count-mismatch refusal (#389)

**Standard:** #341. **Build:** #389, the paired-lane Gate-2 read surface.
**Generator:** manual (hand-chosen mutants following #341 protocol). **Machine-readable record:**
`docs/assurance/paired-gate2-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/cli/paired_gate2.py` at
`sha256:<to-be-filled-at-merge>`.
**Python:** 3.13.1.

Each case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. Per case the generator records and asserts: the worktree HEAD, the `module.__file__`
actually imported, the clean and mutant source digests, that those digests differ, that the
clean baseline **passes first** with **nonzero collection**, the failing test node under the
mutant, that the mutant **imports** (a stillborn mutant is not a kill), and that the
production tree is byte-unchanged afterwards.

## What the predicates are

The paired-lane Gate-2 read (`paired_gate2_read`) enforces two invariants:

- **Ratification binding:** the command refuses a design that is not backed by a RATIFIED
  record. A DRAFT record, a missing record, or a field mismatch is a typed refusal naming
  the field.
- **Count-mismatch refusal:** `pair_count != design.n_pairs` returns `COUNT_MISMATCH`. The
  pilot run (k=8) produces exactly this refusal against the Amendment 4 recommended row
  (n=32).

## Results

| mutant | obligation | mutation | verdict | killing tests |
|---|---|---|---|---|
| M-R1 | 389-ratification-binding | Remove the `record.status != "RATIFIED"` check: a DRAFT record is accepted and the command proceeds to read the design | **KILLED** | `test_cli_paired_gate2.py::TestUnratifiedDesign::test_draft_record_refused` |
| M-R2 | 389-count-mismatch | Remove the `total_pairs != design.n_pairs` check: k=8 pairs are read against n=32 design without refusal | **KILLED** | `test_cli_paired_gate2.py::TestCountMismatch::test_pilot_k8_vs_design_n32` |

Two hand-chosen mutants. **No mutation score is reported**, because two cases cannot support
one; each case is a named obligation, not a sample.

## Why each mutant is shaped this way

Both mutants remove a guard by deleting the condition that triggers the refusal, rather than
by deleting the exception class or its message. Deleting the condition leaves the refusal
infrastructure in place, so the mutant compiles and imports, and the only behaviour that
changes is that the guard can no longer fire. A mutant that deleted the entire block would
also remove the only use of the error class and risk a lint-shaped kill rather than a
behavioural one.

M-R1 is deliberately narrow: only the status check is removed, not the file-existence check
or the field-mismatch check. This shows the RATIFIED gate is load-bearing independently of
the other two checks.

M-R2 is deliberately narrow: only the count comparison is removed, not the paired_cells
lookup or the design construction. This shows the count-mismatch guard is load-bearing
independently of the data-reading path.

## What this receipt refuses to claim

A mutation score — two hand-chosen mutants cannot support one. Adequacy of the paired Gate-2
test suite as a whole. That the ratification-record field-mismatch path is covered here (it
is covered by `test_ratification.py`'s scope-mismatch tests). That the CLI output format is
tested here (formatting is pinned by the eight passing tests in `test_cli_paired_gate2.py`).
