# Run-to-run noise, and the rule it produced

Moved off the front page on 2026-09-13, with its figures and receipt intact.

Comparing a skill against nothing is noisier than it looks. On a 60-trial arc of identical agentic
coding tasks, run-to-run output-token variation measured a coefficient of variation of about 17.6%
(RMS across cells; mean-of-cells 14.6%, median 10.4%) on an Opus-class model
([findings record](https://github.com/MrBinnacle/skill-harness/blob/main/docs/findings/why-naive-skill-benchmarks-mislead.md)).
At that coefficient of variation, a three-runs-a-side comparison cannot separate differences under
roughly 30% to 40% from noise, and three runs a side is what most published guides recommend.
Hand-picked tasks tilt the result before anything runs. Pass/fail test banks price what a skill
*costs* and skip what it *does*. Each claim in the findings record carries its own evidence grade.

## The design rule

**Where no measurement exists, the field prints `UNMEASURED`.** No placeholder zero, no free-typed
excuse, no estimate standing in for a measurement.

Three consequences follow.

- Every paid comparison has a control arm: with the skill and without it, never a score in a
  vacuum, because a score in a vacuum cannot show that the model did not need the skill.
- Where the evidence cannot carry a call, the recorded state is `UNMEASURED` with a reason drawn
  from a fixed list of eight (`src/skill_harness/aggregation/status.py`, defined in
  [docs/concepts/why-unmeasured.md](https://github.com/MrBinnacle/skill-harness/blob/main/docs/concepts/why-unmeasured.md)).
  Which kind of not-knowing applies is more information than not-knowing alone.
- Evidence passes a gate before it enters an aggregate, and the append-only store snapshots the
  gate result at write time. The store keeps data that fails the evidence-admissibility gate and
  never counts it. A judge-graded result counts only where that judge has been calibrated on that
  axis first. Calibration swaps answer order to cancel position bias, controls for length, defends
  against injection, and measures agreement with a human.
