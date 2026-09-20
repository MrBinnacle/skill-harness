# Class-hypothesis pre-registration — does `value_class` condition how a null is read? (REGISTERED)

> **Reader's note.** This document locks what will be tested, and what each possible answer
> means, *before* the data exists. It was written to discharge one blocker: `skill-harness#104`
> was declined five times because the class hypothesis had never been registered, and Gate 2's
> guardrail forbids running first and deciding afterwards what the result meant. Everything below
> the status line is the registered record and changes only by dated amendment blocks appended at
> the end, never by an edit in place.

**Status:** REGISTERED 2026-09-20, session S465. Registered **with a pre-stated NO-GO on the
run that prompted it.** The corpus-wide clause extraction `#104` contemplates cannot test this
hypothesis, and the reason is not power or money. It is that one of the two arms is empty on
disk and nothing purchasable fills it. That finding is registered here as the primary result,
because a pre-registration that discovers its own contrast is unrunnable has done its job.

## The hypothesis, stated so it can fail

**H1 (the class hypothesis).** A skill's `value_class` conditions how a null result about that
skill should be interpreted. A null on a `trap-discipline` skill means something different from
a null on a `calibration` skill, and the difference is large enough to change a verdict.

H1 is what every type-conditional reading of a null in this instrument silently assumes.
`aggregation/verdict.py` already branches on it: `CUT` is withheld unless the class is
`TRANSFORMATIVE_LIFT`, and `TRAP_DISCIPLINE` takes its own path when `outcome_type` is
`invariant`. `tests/test_value_class_call_sites_static.py` refuses any call site that omits the
argument. So H1 is not a proposal. Shipped code already depends on it, and it has never been
tested.

**The precondition H1 requires.** Between-class variance must exceed within-class variance. If
two skills of the same class differ more than two skills of different classes, the class label
carries no information a verdict may lean on, and every branch above is reading noise.

**H0.** `value_class` is not associated with measurability beyond what within-class spread
already explains.

## Gate fields

| Field | Value |
|---|---|
| Pending decision | Whether `aggregation/verdict.py` may keep branching on `value_class`, and whether `#104`'s corpus-wide extraction should be paid for to settle it. |
| Primary contrast | Between-class vs within-class spread in per-skill mechanical measurability (the fraction of a skill's extracted clauses whose axis appears in the Tier-1 axis registry). One test. Measurability is deterministic arithmetic over local text, so it carries no judge and no sampling error — unlike the vacuity rate, which the live pin leaves unlabelled. |
| Task source | The extractor's own corpus enumeration, `scripts/extract-corpus-clauses.py`, resolved with `--dry-scope` before any call. The class labels come from `aggregation/value_class_registry.py`, which is pinned against a fixed `(skill_name, value_class, retired_on)` triple list (#422). Labels are frozen before extraction; no skill is classified after its clauses are seen. |
| Oracle set | `classify_axis()` against the Tier-1 axis registry. Deterministic, zero-network, byte-reproducible. No judge, no LLM in the scoring path. |
| Subject layer | Not applicable. This contrast is arithmetic over already-extracted text; no agent runs. |
| Harness pin | Extractor model pin `claude-opus-5`, recorded per row in the JSONL header. The pin is part of the instrument's identity: clause sets from different pins are not poolable. Registry state is pinned by its test. |
| Differentiation vs field | A prior sweep recorded, as a verified precondition, that no literature supports letting intervention *type* determine the *interpretation* of a null, and that the nearest analogue is a cautionary tale about construct validity. H1 is therefore this project's own claim, unsupported from outside, which is exactly why it needs registering rather than assuming. |
| MDE + sizing | Not computed, and deliberately so. See the NO-GO below: one arm has n=0 reachable members, and no sample size is defined on an empty arm. Sizing becomes meaningful only after the corpus-construction precondition is met. |
| Stopping rule | Single deterministic pass over the corpus. Nothing sequential, nothing to stop early. |
| Leak audit | Not applicable in the usual sense — no subject reads anything. The analogous risk is label leakage, and it is closed by freezing the registry before extraction and by the registry's own pinning test. |
| Budget | **$0 registered.** This document authorises no spend. The run it was written to authorise is refused below on evidence, not on cost. |

## The measurement that produced the NO-GO

Every figure below was measured on 2026-09-20 by running the command in its own row. None is
carried from a checkpoint, a ticket, or a prior session's summary.

| What was measured | Command | Result |
|---|---|---|
| Corpus size | `python scripts/extract-corpus-clauses.py --dry-scope` | **82 entries** (73 local, 9 fable), not the 71 carried across `#104`, the S194 facts and the checkpoint. |
| Registry size | parse of `value_class_registry.py` | **12 entries: 9 `trap-discipline`, 3 `calibration`, 0 `transformative-lift`**, not the 11 (8 + 3) those same surfaces state. |
| Already extracted | `docs/research/corpus-clauses-S184.jsonl` | 6 skills, the first six alphabetically. Two carry a class, both `calibration`. |
| How many classified skills the extractor can reach | `--dry-scope --slugs-file` over all 12 registry slugs | **4 of 12 resolve.** Three `calibration`, one `trap-discipline`. |
| Where the unreachable eight live | `find -L` across `~/.claude`, the plugin cache, and `git ls-files` in the `skills` clone | Seven exist **only inside dated backup directories** (`skills-backup-20260728-210643/`, `_retired-quarantine-backup-2026-08-25/`). One, `subagent-research-reliability`, exists only inside plugin `_quarantine/`. None is a live card on any surface the extractor walks. |

**The one `trap-discipline` skill the extractor can reach is `sqlite-tie-break-red-test-trap`,
and the registry itself marks it retired 2026-07-10.**

## What this means, decided before the data, and unchanged by it

**The contrast is not underpowered. It is undefined.** A between-class comparison needs two
arms. The `trap-discipline` arm contains one reachable member and that member is retired. Paying
for the other 76 skills changes nothing here, because the missing eight are not among them — they
are not on disk at all. This is the first time the obstacle has been stated as a property of the
corpus rather than of the budget, and it is why `#104` kept coming back: every previous pass
priced the run and none asked whether the run could answer the question.

**The class variable is confounded with liveness.** All three `calibration` skills are live
cards. Eight of nine `trap-discipline` skills are backups or quarantine residue, and the ninth is
retired. Any number this comparison produced would separate live cards from dead ones at least as
well as it separated classes, and a reader could not tell which. That is precisely the construct
validity failure the prior sweep flagged as the nearest analogue, arriving here by a route nobody
planned.

**Registered outcome rules, binding on whoever runs this later.**

- A **non-zero, non-uniform** measurability spread that is larger *between* classes than *within*
  them supports H1, and only then may `verdict.py`'s branches be called evidenced.
- A spread larger **within** a class than between classes refutes H1. Publish it. The 6-skill
  sample already shows a 6.4x within-class spread at Fisher two-sided p = 0.041, so this outcome
  is the one currently favoured by the only data that exists, and it must not be quietly reframed
  as "inconclusive" when the full run agrees with it.
- A **corpus-wide uniform** result publishes as a finding about the *instrument's reach*, not
  about the corpus, on the same terms `#104` already registered for the vacuity rate.
- **Publish either way.** An absence census that publishes only when it finds absences is not
  evidence. This clause is the reason the document exists.

**What would make a later run interesting.** Not money. A corpus in which both arms have
members. Two routes exist and both are cheap:

1. Enumerate the backup and quarantine roots the extractor already supports through
   `--extra-root ROOT:PROVENANCE`, recording provenance per row so a reader can see that the
   `trap-discipline` arm is made of retired cards. This makes the comparison runnable and keeps
   the confound visible instead of hiding it.
2. Classify live skills that have never been given a `value_class`. The registry covers 12 of 82.
   The binding constraint on this whole question is **classification coverage, not extraction
   coverage**, and classification is free.

Route 2 is the one worth taking, because route 1 buys a comparison whose confound cannot be
removed afterwards.

## What is refused, and what is released

**Refused: the corpus-wide extraction as an instrument for H1.** It cannot reach the missing
arm. Registering this refusal is what closes `#104`'s carried decision — not a ruling that the
sweep is worthless, but a finding that it is the wrong instrument for the question that was
blocking it.

**Released: the extraction as a means to other ends.** `#104`'s own Revisit-if anticipated this
exactly — *"a means-to-an-end run is a different authorisation than a census, and it may not need
the same pre-registration."* Anything that needs more clauses for a reason unrelated to
`value_class` is governed by its own ticket and is untouched by this document.

## Provenance

Written at session S465 from a direct read of `skill-harness#104` and its resolution comment, the
S194 fact sheet's facts 13 through 17, `aggregation/value_class_registry.py`,
`tests/test_value_class_call_sites_static.py`, and fourteen zero-spend measurements listed above.
House format follows `docs/findings/v0.2-preregistration.md`, including its amendment rule:
append a dated block, never edit registered text.
