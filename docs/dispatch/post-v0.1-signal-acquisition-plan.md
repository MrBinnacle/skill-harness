# Post-v0.1 Signal-Acquisition Plan

The operational sequence following the "drive on" authorization. The frame is:
the v0.1 frame-break shipped; it isn't legible yet; the next cycle is a
**signal-acquisition cycle**, not a feature cycle. Lock on v0.2 commitment
until World-pull signal arrives.

Companion to the outward-facing case study at
`docs/case-studies/ai-slop-sentinel-under-ablation.md`.

## Sequence

| # | Item | Owner | Calendar | Status |
|---|---|---|---|---|
| 1 | Case study draft | orchestrator | landed 2026-06-08 | ✅ committed |
| 2 | First-touch hardening punch list | orchestrator → dispatched | week 1 (target land by 2026-06-15) | ✅ landed 2026-06-08 (`09af6ae`, items 1-4 + 6) + 2026-06-09 ([this commit] item-5 legend placement fix + doc-honesty pass) |
| 3 | Targeted-send list shape | orchestrator surfaces persona; PM picks names | 2026-06-08, before sends begin | ⏳ this doc |
| 3.5 | **One-reader frame-legibility tracer (T1)** | PM picks ONE reader from persona profile | 2026-06-15 → 2026-06-18 window | tracer gate before batch |
| 4 | Targeted sends (batch of 5-10) | PM | 2026-06-18 → 2026-06-22 window (only AFTER T1 passes) | PM-owned |
| 5 | Reaction collection | PM + orchestrator | 2026-06-22 → 2026-07-08 | PM-owned |
| 6 | v0.2-commitment re-eval | PM | **2026-07-08** | calendared |

## #2 · First-touch hardening punch list

The friction set between `git clone` and "I see the demonstration on my own
machine running against my own skill." Not features. The specific reasons a
smart skeptic, given 30 minutes, would put the project down before reaching
the demonstration.

**Status (2026-06-09)**: ✅ substantially landed. Items 1-4 and 6 landed
in commit `09af6ae` (2026-06-08). Item 5 (legend placement) and a
doc-honesty pass on the extractor / OpenRouter API-key asymmetry — surfaced
by walking the reproduction recipe as a T1 reader on Claude Code
subscription auth, the case study's own author profile — landed in [this
commit] (2026-06-09). One follow-on engineering item surfaced by that
walk: extractor OpenRouter fallback (currently `skill init` requires
`ANTHROPIC_API_KEY`; v0.2 backlog candidate, symmetric to the W2 work that
fixed the same gap on `run ablation`).

### Punch items

- **README.md is currently the deck for v0.1 internals, not the on-ramp for v1
  evaluator.** Replace top-of-README narrative with a 90-second flow:
  (a) the one-sentence claim (deterministic eval that refuses to lie when it
  can't measure), (b) the one-paragraph "what's different from MMLU / G-Eval /
  pairwise-preference," (c) the 5-line bash recipe to reproduce the case
  study, (d) one link to the case study, (e) one link to the PRD for
  depth-seekers. Push current README contents to `docs/internals/README.md`.

- **Install path on Windows leaks the `PYTHONUTF8=1` / `PYTHONHASHSEED=0`
  requirement to the user.** Resolve by either: (a) auto-set in a `skill-harness`
  CLI entrypoint when missing on Windows + emit one-line stderr advisory, OR
  (b) document in the on-ramp with the precise 1-line PowerShell snippet.
  Choice (a) requires touching the CLI surface (Phase 3.4-bis scope check);
  choice (b) is doc-only and ships today. Default to (b) for the
  signal-acquisition window; revisit (a) only if 2+ readers hit the trap.

- **`skill init` transient-failure path** (extractor returned `"clauses field
  of unexpected type: str"` on first call per the dogfooding gotcha) is a
  documented operational gotcha but a first-touch killer. Two options:
  (a) add a single retry with backoff inside `skill init`'s extractor call
  (~15 LOC + test), (b) document as known issue with "retry once if you see
  this" line. Choice (a) is small enough to ship in the signal-acquisition
  window; recommended.

- **"What does UNMEASURED mean and why isn't it a failure?" is a doc gap.**
  A reader who reaches the result and sees `unmeasured: 17` will read it as
  failure unless the framework's intent has been made plain BEFORE they ran
  it. Two-paragraph addition to README + a longer reference at
  `docs/concepts/why-unmeasured.md`. The case study now covers part of this,
  but the reader needs the same explanation BEFORE the case study, not as
  the case study itself.

- **The clause inventory the extractor produces is opaque to a first-time
  reader.** `skill clauses <skill_id>` shows the table but doesn't explain
  what `axis`, `oracle_tier`, `vacuity_flag` mean operationally. Add a brief
  legend to the CLI's `skill clauses` output footer.

- **No example skill that ships with the repo.** A reader who wants to
  reproduce the case study has to find / write an `ai-slop-sentinel/SKILL.md`
  file. Ship a minimal `examples/` directory with: (a) `ai-slop-sentinel.md`
  copy (or pointer + license), (b) `bayesian-eval-discipline.md`, (c) the
  one-shot bash script that produces the full case-study output.

### Out of scope for this punch list

- Tier-1 scorer registry expansion (the load-bearing v0.2 question; do NOT
  pre-empt the PM signal cycle)
- Tier-2 judge calibration (same reason)
- v0.2 features broadly
- `tests/` mypy cleanup (119 errors; tracked separately)
- Phase 3.3-bis mutation sweep (overnight CI candidate)

### Dispatch shape

Single Sonnet 4.6 implementer in a worktree. Single cohesive commit per
`feedback-commit-shape`. Target land: 2026-06-15. Estimated 4-6 hours of
agent work + orchestrator review.

## #3.5 · One-reader frame-legibility tracer (T1)

Before the batch of 5-10 sends goes out, send the case study to **one** credible-skeptic reader as a tracer round. Their feedback either confirms the frame is legible or surfaces a specific failure point. Cheap, fast, falsifiable. The cost of skipping this step is the batch lands and 5 readers bounce off the same problem one would have told us about.

### The tracer reader

Same persona profile as the batch (§#3 below), but one person specifically chosen for two extra qualities:

- **Will give a real reaction within 72 hours.** A delayed-reaction tracer is a magazine round, not a tracer. Pick someone who responds quickly when they engage at all.
- **Will tell us where they got lost, not just whether they liked it.** "Reads well" is not a tracer outcome. The valuable outputs are "I lost the thread at section X" or "I don't believe claim Y because Z."

### What we're testing

The case study's frame is: "three skills, three mechanisms, same UNMEASURED verdict, here's why this is the honest answer." We are NOT testing whether the frame is persuasive. We are testing whether it is **legible** — whether a credibly-skeptical reader can follow the argument enough to either accept or reject it on its actual merits.

### Pass / fail

- **Pass**: the reader understands the case study's claim, can name the three mechanisms back, and reacts substantively (agrees, disagrees, asks pointed questions). Batch send (§#4) proceeds.
- **Fail (frame-illegible)**: the reader bounces off the framing without engaging substance. Stop. Rewrite the case study using their specific failure point. Re-tracer with a different reader.
- **Fail (substance-rejected)**: the reader engages and tells us we're wrong, with a reason that stands up. Stop. Either update the case study with the rebuttal-and-response, or — if the rebuttal invalidates the frame — pause the entire signal-acquisition cycle and re-evaluate the thesis.

### What we don't do with the T1 reader

- Don't argue. Listen. Adjust.
- Don't treat their reaction as the final answer for the batch. T1 calibrates the case study; T1 is not the audience verdict.
- Don't make them part of the batch later. They've burned their first-touch surprise; their batch reaction would be contaminated.

## #3 · Targeted-send list shape

Persona profile — NOT names. The PM picks names from their network; the
orchestrator surfaces the criteria.

### Who counts as a credible reader

A credible reader for this case study is someone who:

1. **Has hands-on familiarity with LLM evaluation pipelines as practitioners,
   not as commentators.** They have written eval rubrics, calibrated judges,
   shipped benchmarks, or run eval ops at scale. They know the gap between
   "the number a judge produces" and "what the judge actually measured."
2. **Has shown public skepticism toward holistic / pairwise-only eval
   methods.** Twitter/X threads, blog posts, conference talks, GitHub
   issues on eval frameworks. They have already noticed something is wrong;
   they just may not have named it the way Skill Harness does.
3. **Is willing to actually run the artifact.** Reading without reproducing
   produces low-fidelity reactions. Filter for people who will spend the 30
   minutes.
4. **Has standing to be uncomfortable in public.** Not all of them will be —
   but the ones who do are worth more than 100 quiet nods.

### Who does NOT count

- Marketing/comms-oriented "AI safety thought leaders" who quote
  first-principles as jargon. Their reactions are not signal.
- Customers of existing eval framework vendors (LangSmith, Helicone, etc.)
  who have aligned incentives to not see the asymmetry. Their reactions
  are not signal.
- People who would react primarily to the framing rather than the artifact.
  We do not need framing wins. We need artifact wins.

### Volume

**5-10 sends.** Not 50. Not 500. The cost of premature broadcast is the
reaction batch gets dominated by people whose reactions don't count; the
real signal gets buried. The cost of waiting one cycle to broaden is small.

### Send shape

Not a "blog post URL"-style send. Specifically:

- One paragraph framing what the recipient is being asked to do (reproduce
  the case study; tell us what's wrong with it; tell us what's missing).
- A link to the case study + the PRD.
- A repository link + the git clone + checkout + reproduction command.
- A one-line offer: "happy to walk through it on a call if useful."

### What we listen for (post-send)

The high-signal reactions, in order of value:

1. **"I tried to reproduce and X broke."** Operational signal. Fix X.
2. **"The case study is wrong because Y."** Substantive disagreement.
   Highest-value. Update the case study or update the framework. Either is
   acceptable; pretending the disagreement away is not.
3. **"This is interesting but I would use it for Z" where Z is unexpected.**
   World-pull signal about adjacent use cases.
4. **"I tried it on my own skill and got the same UNMEASURED result and
   here's what I want."** This is the v0.2 prioritization signal — what
   they want is the scorer registry expansion we deferred. But it has to
   come from them, not from us.
5. **No reaction at all.** Itself a signal. Different conclusions depending
   on volume — 0 of 10 silent is "wrong audience or wrong artifact"; 3 of
   10 silent is "normal."

### What we do NOT do

- Argue with reactions in real-time. Listen. Note. Synthesize at the end of
  the window.
- Treat one strong reaction (positive or negative) as the answer. Wait for
  the batch.
- Send v2 of the case study before the first batch's reactions are in.

## #4 · Re-eval date

**2026-07-08** is the calendared v0.2-commitment re-eval date. One month
from the v0.1 tag (2026-06-08).

Rationale:
- First two weeks (2026-06-08 → 2026-06-22): first-touch hardening + send
  preparation + sends go out. No reaction collection yet.
- Next two weeks (2026-06-22 → 2026-07-08): reaction window. Most reactions
  will arrive in the first 7 days post-send; the second week is for late
  arrivals + reflection.
- 2026-07-08: re-eval. By then we have: (a) some real-world reactions, or
  (b) the silence itself as signal.

### What happens at the re-eval

The orchestrator surfaces:
- The N reactions received, summarized by signal class (operational / 
  substantive / use-case / volume of silence).
- Updated case study draft if any reactions warranted it.
- Updated first-touch friction list if reproducibility issues surfaced.

The PM decides:
- Whether the reaction set is enough to commit to a v0.2 scope. If yes,
  what scope.
- Whether the reaction set is insufficient and another cycle is warranted
  (longer wait, broader send, refined case study).
- Whether the artifact's frame turned out to be wrong, in which case the
  conversation is no longer "what's v0.2" but "is the thesis still right."

### What the re-eval is NOT

- A status check (status checks are continuous; the re-eval is a decision
  point).
- A vote-counting exercise. Two strong substantive reactions from the right
  people outweigh 8 silent recipients.
- A self-grading exercise on the team's behalf. The whole frame is that the
  team's own assessment is Team-push signal; the re-eval consumes
  World-pull signal.

## Out of scope for this whole plan (explicitly)

- v0.2 feature commitments before 2026-07-08
- Tier-1 scorer registry expansion before clear World-pull signal that
  asks for it
- Public marketing (blog posts, HN submissions, Twitter announcements)
  before the targeted-send batch has produced its first reactions. The
  cost of premature broadcast is enormous in this case; defer until at
  least 2026-07-08.
- Promotional language anywhere in the artifact. The frame is "the
  discipline is uncomfortable; come look at the uncomfortable thing." If
  it sounds like marketing, rewrite it.

## Owner map (so it doesn't drift into "the PM should…" recursion)

| Workstream | Orchestrator (LLM) | PM (user) |
|---|---|---|
| Case study draft | ✅ wrote v1 (landed) | reviews + greenlights |
| First-touch hardening punch list | ✅ wrote scope (this doc); will dispatch implementer when authorized | greenlights dispatch + scope |
| Targeted-send persona | ✅ wrote persona profile | picks specific names + sends |
| Sends themselves | — | PM-owned |
| Reaction collection | helps with summarization at end of window | PM curates |
| Re-eval on 2026-07-08 | surfaces reaction-class summary + open-question list | makes the v0.2 call |

The orchestrator does not surface "what's the next feature?" to the PM
between now and 2026-07-08. The orchestrator's job is to execute the
operational items above and stay quiet on prioritization questions until
the calendared re-eval.
