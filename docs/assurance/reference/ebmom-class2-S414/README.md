# Reference implementation of mechanism class 2, as measured

These six files are the prototype that produced every number in amendment v2 sections 0.3 to
0.7, copied verbatim from the steering repository on 2026-09-05 (S414) at the freeze. They are
the thing the build must reproduce. They are not production code and are outside the CI gate's
`src/` and `tests/` paths on purpose.

| file | role |
|---|---|
| `proto_pb.py` | mechanism class 2: admission-conditioned parametric bootstrap, `S = 200` kept draws, form B on refusal; per-world dump |
| `rescore405.py` | the per-path re-score harness the prototype builds on: columns, tallies, form A and form B, the plug-in |
| `clustered_bound.py` | both kill tests per cell (the exact one-per-world test and the world-block bound), seed-dependence, the world-range option |
| `extension_control.py` | the rule-1 control for a world-range extension |
| `fit-branch.py` | byte-identical copy of this branch's `src/skill_harness/aggregation/fit.py`, loaded by path |
| `matrix.py` | byte-identical copy of this branch's `scripts/ebmom_acceptance_matrix.py`, loaded by path |

Run from this directory. `rescore405.py` loads the two vendored copies by path so the numbers
stay tied to the code that produced them even if the branch moves.

```
python proto_pb.py regime <root> low_heterogeneity 1000
python clustered_bound.py proto-pb-low_heterogeneity-R1000-<root8>.json
python clustered_bound.py proto-pb-low_heterogeneity-R1000-<root8>.json 500:1000
```

**Build acceptance that uses this directory.** The built candidate, run through the harness at
R = 1000 on the burned root `f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a`,
reproduces the per-path cells of `proto-pb-all-R1000-f95e4de5.json` in the steering repository
(all five regimes, both paths, both rows, and the `cand_bpB` plug-in column), and its
`low_heterogeneity` R = 4000 table reproduces `proto-pb-low_heterogeneity-R4000-f95e4de5.json`.
A build that does not reproduce the prototype is not the mechanism that was measured.

---

## Correction, recorded rather than silently fixed (2026-09-08, sh#458)

Everything above this line is the S414 freeze text, left as written. This block corrects it
forward, per the house convention that a registered record changes by dated correction block
and never by edit (`docs/findings/v0.2-preregistration.md`).

### The directory could not run, and never could

The table above lists six files. `rescore405.py` loads a seventh, `errors-branch.py`, by path:

```
_load("skill_harness.aggregation.errors", HERE / "errors-branch.py")
```

That file was not vendored at the freeze. It is not a regression -- `git log --all
--diff-filter=A -- "*errors-branch.py"` returns nothing, so the path was never added on any
ref, and `rescore405.py` has exactly one commit (`e322876`) with no repair after it. **The
directory shipped unable to execute and stayed that way from 2026-09-05 to 2026-09-08.**

This matters more than a missing file usually would. A frozen reference exists to be the fixed
thing later work is measured against; one that cannot execute has quietly stopped being an
oracle, because every consumer must assemble its own runnable copy and no two are guaranteed to
assemble the same one. The #442 build did exactly that, checking its reproduction against a
locally assembled directory rather than against what this repository ships.

`errors-branch.py` was vendored on 2026-09-08 from the same freeze commit as its siblings, and
the directory now runs. `tests/test_ebmom_class2_reference_smoke.py` executes it and asserts
its per-world output, so the next such rot fails a gate instead of waiting to be tripped over.

**The repaired directory reproduces what it was frozen to produce.** This was checked rather
than assumed, because a directory that merely executes is not yet an oracle. Running `python
proto_pb.py all SMOKE_NOT_CONFIRMATORY 40` regenerates the dump that
`docs/assurance/ebmom-form-b-reproduction-R40-SMOKE_NO.json` names as its expected input (that
dump is not itself committed). Comparing that receipt's recorded `built` block -- production at
`d39440d`, which the receipt records as agreeing with the #441 prototype -- against the
regenerated `cand_bpB` column gives **32 of 32 compared fields equal, 0 differing**, across
both regimes, all four cells and all four compared fields. The vendored `errors-branch.py` is
therefore the right bytes, not merely bytes that let the imports resolve.

### What each vendored copy is pinned to

The freeze text says each copy is "byte-identical to this branch's" file. That was true when
written and names no commit, so it could not stay checkable once the branch moved. The pins:

| vendored file | is byte-identical to | at commit | git blob id |
|---|---|---|---|
| `errors-branch.py` | `src/skill_harness/aggregation/errors.py` | `8df6710` (2026-08-05) | `a32f891f954121c18c9b3625f637d4bf057e16f9` |
| `fit-branch.py` | `src/skill_harness/aggregation/fit.py` | `b9099fe` (2026-09-02) | `ce472ac540d00778a9b76eff671968edf269ccdb` |
| `matrix.py` | `scripts/ebmom_acceptance_matrix.py` | `e260c6f` (2026-09-01) | `d473b29ebfb3d6251e728cf4943558f84c8bc543` |

All three are the state those paths carried at the freeze commit `e322876` (2026-09-05); the
per-file commits above are simply the last commit to touch each path before it. Check any row
by hand with `git rev-parse <commit>:<path>`, or against the file with `git hash-object`.
`tests/test_ebmom_class2_reference_smoke.py` asserts the blob ids from file content alone, so
the pins stay falsifiable in a depth-1 CI checkout with no history.

**The branch has since moved on two of the three, by design, and the copies deliberately have
not.** `fit.py` changed at `60a6548` (#442, the admission-conditioned bootstrap replacing the
plug-in on the admitted path) and `ebmom_acceptance_matrix.py` at `85ed54b` and `9d381c8`
(#443). Divergence is the point: these copies are the code that produced amendment v2's
numbers. `errors.py` has not changed since `8df6710`, well before the freeze.

### Correction to the usage block

The usage block above documents only `regime` mode. The two other entry points, which its
reader needs and which the acceptance paragraph relies on, are:

```
python proto_pb.py worlds <root> <regime> <world> [<world> ...]
python proto_pb.py all <root> <R>
```

`all` writes `proto-pb-all-R<R>-<root8>.json` and reads its arguments from positions 2 and 3,
so the mode token must be present: invoking it as `python proto_pb.py <root> <R>` raises
`IndexError`, which is how this was found.
