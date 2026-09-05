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
