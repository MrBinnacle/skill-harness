# The offline audit, on a card it refuses to score

The README carries the command. This file carries its output, moved here on 2026-09-13 so the front
page stays under its word ceiling.

The run below is `skill-harness skill audit` against the committed fixture
`tests/fixtures/sers/declared-synthetic-positive-control/SKILL.md`, on 2026-09-13, from a clean
virtual environment holding v0.3.0 from PyPI, in a 100-column terminal. Two lines are removed,
`source:` and `sha256:`, because both are local to the machine that ran it. The Summary line's
trailing pointer to `docs/concepts/why-unmeasured.md` is dropped so the line renders whole.
Everything else is verbatim.

```text
OFFLINE AUDIT — no API calls, no cost
  skill:  declared-synthetic-positive-control
  body:   9 lines / 41 words · frontmatter keys: description, name
                               Structure (Anthropic authoring spec)
┌────────┬───────────────────────────────────┬────────────────────────────────────────────────────┐
│ Level  │ Check                             │ Finding                                            │
├────────┼───────────────────────────────────┼────────────────────────────────────────────────────┤
│ PASS   │ name                              │ name 'declared-synthetic-positive-control' meets   │
│        │                                   │ spec                                               │
│ INFO   │ description-unparsed-block-scalar │ description uses a multi-line YAML block scalar,   │
│        │                                   │ which this audit's minimal frontmatter parser      │
│        │                                   │ cannot read — description content checks skipped   │
│        │                                   │ (UNMEASURED, not passed)                           │
│ PASS   │ body-length                       │ body 9 lines (budget 500)                          │
│ WARN   │ standing-cost-unparseable         │ router listing line (frontmatter name +            │
│        │                                   │ description) is not readable as a single-line pair │
│        │                                   │ — standing cost UNMEASURED (no number; a silent    │
│        │                                   │ default would understate the per-turn tax)         │
└────────┴───────────────────────────────────┴────────────────────────────────────────────────────┘
Evaluability preflight — what a paid run could measure today:
  Tier-1 mechanical axes: citation_presence_per_flag, compliance_proxy, hedge_index,
structure_score, verbosity (style-shaped only).
  Behavior-shaped claims (correctness, tool use, outcomes): no mechanical instrument in v0.1 → the
recorded state would be UNMEASURED, not an estimate.
  Judge-graded axes: require a calibrated (judge, axis) pair — none exists in a fresh install →
UNMEASURED until you run `calibrate`.
  Standing cost (mechanical): UNMEASURED — frontmatter could not be parsed well enough to count the
router listing line (see standing-cost-unparseable).
  Fired cost (mechanical): raw 68 tokens · calibrated 77 tokens (x1.128, measured range
1.084-1.179) -- skill body charged when the skill runs and its body is read.
  Aux cost (mechanical): raw 0 tokens · calibrated 0 tokens (x1.128, measured range 1.084-1.179) --
other documentation files beside the skill (progressive disclosure); 0 when the skill directory has
none.

Summary: 2 pass · 1 warn — UNMEASURED is a recorded state, not a failure.
Clause evidence: UNMEASURED (no_extraction: clause evidence requires an extraction output; produce
one with skill init --out <file>)
```

Read the two gaps, because they are the point. The parser could not read the description, so the
audit names the check it skipped and marks the result `UNMEASURED` rather than passing a field it
never read. The standing cost has no number for the same reason, and the audit prints `UNMEASURED`
where a silent default would have understated the per-turn tax.
