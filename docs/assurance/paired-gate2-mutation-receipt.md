# Mutation receipt: the ratification binding and count-mismatch refusal (#389)

**Standard:** #341. **Build:** #389, the paired-lane Gate-2 read surface.
**Generator:** `scripts/mutation_receipt.py --select 389`. **Machine-readable record:**
`docs/assurance/paired-gate2-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/cli/paired_gate2.py` at
`sha256:8abfb41bd9b9cb469e87e10c9d63b003a8f517dd2522ceaad9bf1607ee6eebec`.
**Commit at generation:** `be86b77f22e3ecf94100ea63f4e61138096c287b` — informational only. A rebase
rewrites it and later commits move HEAD past it, so currency is checked against the digest
above by `tests/test_mutation_receipt.py`. **Python:** 3.13.15.

**Regenerated 2026-09-03 for #421.** Commit `be86b77` added the `#403`-amendment hazard
refusal (registered `hazard_floor`, two-arm block, Full arm printed and never gated) to
`paired_gate2.py`, which moved the file's bytes and made the `#417` receipt's digest pin
stale. The hazard refusal is a separate control with its own pinning tests
(`TestHazardNotRecorded`, `TestHazardNotMet`, `TestHazardPositivePath`); it is not a mutant
in this receipt, which attests only to the two `#389` guards. Both `#389` mutants were
re-run by the same generator; both anchors were still present and both kills held, by the
same detectors. The results table below was re-measured, not carried.

**Regenerated 2026-09-03 for #417 (#391).** The first generation (commit `a2ed8cb`, digest
`c15e52b2338d`) attested to the module before #417 replaced the `runs.skill_id` comparison with
the runner-declared identity check. Both mutants were re-run by the same generator; both anchors
were still present and both kills held, by the same detectors. The results table below was
re-measured, not carried.

Each case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. `PYTHONPATH` pins every case to its own sources, because the editable install would
otherwise resolve `skill_harness` to the main repository and each case would silently test
another tree's code.

Per case the generator records and asserts: the worktree HEAD, the `module.__file__` actually
imported, the clean and mutant source digests, that those digests differ, that the clean
baseline **passes first** with **nonzero collection**, the failing test node under the mutant,
that the mutant **imports** (a stillborn mutant is not a kill), and that the production tree is
byte-unchanged afterwards. Both cases resolved `skill_harness.cli.paired_gate2` inside their
own worktree, and the production digest was identical before and after.

## What the predicates are

The paired-lane Gate-2 read (`paired_gate2_read`) enforces two invariants:

- **Ratification binding:** the command refuses a design that is not backed by a RATIFIED
  record. A DRAFT record, a missing record, or a field mismatch is a typed refusal naming
  the field.
- **Count-mismatch refusal:** `pair_count != design.n_pairs` returns `COUNT_MISMATCH` (the
  matched-bridge `MatchedRefusalReason.COUNT_MISMATCH` name). The pilot run (k=8) produces
  exactly this refusal against the Amendment 4 recommended row (n=32).

## Results

| mutant | obligation | mutation | verdict | killing tests |
|---|---|---|---|---|
| M-R1 | 389-ratification-binding | Replace `record.status != "RATIFIED"` with `False`: a DRAFT record is accepted and the command proceeds to read the design | **KILLED** | `test_cli_paired_gate2.py::TestUnratifiedDesign::test_draft_record_refused` |
| M-R2 | 389-count-mismatch | Replace `total_pairs != design.n_pairs` with `False`: k=8 pairs are read against n=32 design without refusal | **KILLED** | `test_cli_paired_gate2.py::TestCountMismatch::test_pilot_k8_vs_design_n32` |

Two hand-chosen mutants. **No mutation score is reported**, because two cases cannot support
one; each case is a named obligation, not a sample.

## Why each mutant is shaped this way

Both mutants remove a guard by forcing the condition false, rather than by deleting the
exception class or its message. Forcing the condition leaves the refusal infrastructure in
place, so the mutant compiles and imports, and the only behaviour that changes is that the
guard can no longer fire. A mutant that deleted the entire block would also remove the only
use of the error path and risk a lint-shaped kill rather than a behavioural one.

M-R1 is deliberately narrow: only the status check is removed, not the file-existence check
or the field-mismatch checks. This shows the RATIFIED gate is load-bearing independently of
the other checks.

M-R2 is deliberately narrow: only the count comparison is removed, not the paired_cells
lookup or the design construction. This shows the count-mismatch guard is load-bearing
independently of the data-reading path.

## What this receipt refuses to claim

A mutation score — two hand-chosen mutants cannot support one. Adequacy of the paired Gate-2
test suite as a whole. That the ratification-record field-mismatch path is covered here (it
is covered by `test_cli_paired_gate2.py::TestMissingDesignFields` and
`TestSkillIdMismatch`). That every CLI output format is tested here (formatting is pinned by
the tests in `test_cli_paired_gate2.py`).

## The generator refuses rather than exiting green

A case whose verdict is `ANCHOR_ABSENT`, `INVALID_BASELINE`, `INVALID_ISOLATION`, `NO_OP`,
`STILLBORN` or `UNKNOWN` measured nothing, so the generator exits non-zero and names it.
`SURVIVED` is deliberately not in that set: a preserved survivor is a finding.

*Revisit if:* the paired read moves off `paired_gate2_read`, or a third load-bearing guard
lands at the seam without a case here.
