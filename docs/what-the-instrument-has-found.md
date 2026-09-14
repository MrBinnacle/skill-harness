# What the instrument has found

Moved off the front page on 2026-09-13, with every figure and receipt path intact. The README
carries one sentence and a link to here.

## Zero production-skill KEEPs

What the keep lane has returned, once, end to end, is a KEEP on a *declared synthetic positive
control*: a skill written on 2026-07-27 to carry an invented fact, so the effect exists by
construction. It scored 8 of 8 with the skill against 0 of 8 without, posterior probability of a
win 0.99
([SERS receipt](https://github.com/MrBinnacle/skill-harness/blob/main/docs/sers/receipts/synthetic-control-keep-2026-07-27.json),
which carries `declared_synthetic_control: true`). That run shows the instrument fires when an
effect is present. It says nothing about whether any real skill is worth its slot.

## The usual outcome is a ceiling

The model already does the task without a skill. On two deliberately hardened tasks a frontier
agent passed 14 of 14 no-skill epochs, which left nothing for a skill to improve and so nothing to
measure. That is a finding about the task, written up in
[the double-ceiling case study](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/double-ceiling-structurally-unmeasured.md).

The paired run in that study, July 2026, cost about $6.17 and returned the pre-registered NO-GO: an
apparatus check, not a measurement of benefit. The receipt records it as one
([`double-ceiling-nogo-2026-07-09.json`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/sers/receipts/double-ceiling-nogo-2026-07-09.json)).

Scheduling explains none of that: a sized benefit run launches only when a screen returns a sub-1
pass rate, and every production skill screened so far ceilings at 1. The model passes every attempt
without it
([observation ledger](https://github.com/MrBinnacle/skill-harness/blob/main/docs/observations/README.md)).

## The value-class guard moved two verdicts

A skill can exist to stop one specific wrong move. A model that passes without such a skill has
shown that the trap did not come up, which is a different finding from the skill being useless. So
`subsumed` is a CUT only for skills registered `TRANSFORMATIVE_LIFT`, the class whose whole claim
is lift above the bar. Every other class reclassifies to CAN'T-TELL-YET, on the ground that this is
the wrong instrument for that kind of skill rather than a verdict on it.

Two skills from the collection moved that way when the guard landed:
`append-only-evidence-design` (calibration) and a hardened `git-pull-rebase-trap`
(trap-discipline). Under the pre-guard rule both returned **CUT (subsumed)**, each at a no-skill
pass rate of 1.00; the value-class guard reclassified both to CAN'T-TELL-YET
([receipts](https://github.com/MrBinnacle/skill-harness/tree/main/docs/sers/receipts/)). The
pre-guard CUTs stay in the record as dated output, not edited into agreement.

## The one sized paired run refused

On 2026-09-03, `git-pull-rebase-trap` ran at n = 32 under `RAT-0001`. Exposure held at 32 of 32
Full epochs and the body was invoked in 24 of 32, a rate of 0.75. Both arms passed every epoch,
signed delta 0.000 with a 95% interval of [-0.107, 0.107], and the recorded verdict is
`CANT_TELL_YET`
([receipt](https://github.com/MrBinnacle/skill-harness/blob/main/docs/sers/receipts/gitpull-paired-n32-2026-09-03-sized.json)).

The interval is not the reason the run carries no information. None of the 64 epochs ran `git
pull`: every one fetched and merged instead, so the armed `pull.rebase=true` configuration was
never exercised, and the ancestry oracle cannot tell an avoided hazard apart from a hazard the run
never entered. The run measured whether the subject rebases by habit, not whether the card's guard
changes an outcome. That refusal then became code: `evaluate-paired` now refuses a run in that
shape by name, as `HAZARD_NOT_MET` (`src/skill_harness/cli/paired_gate2.py`).
