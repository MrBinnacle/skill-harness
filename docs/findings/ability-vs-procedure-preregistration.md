# Ability-style versus procedure skills versus no skill — pre-registration (REGISTERED, with a Stage 0 feasibility stop)

> **Reader's note.** This document fixes what `skill-harness#850` will test, how, and what each
> answer means, before any data exists. Everything below the status line is the registered
> record. It changes only by dated amendment blocks appended at the end, never by an edit in
> place. House format: `v0.2-preregistration.md` and `class-hypothesis-preregistration.md`.

**Status:** REGISTERED 2026-10-28, session S550 (Fable), from a direct read of issue #850 (body
as rewritten 2026-10-28; comments 6485299185, 6485564705, 6485614594, 6485676422), the two
registered records named above with their amendments, `docs/findings/stage1a-readout-691.md`,
`docs/case-studies/displaced-enforcement-skill-ablation-blind-spot.md`,
`src/skill_harness/aggregation/value_class_registry.py`, and the installed skill surfaces on
the operator's host. **Budget authorised by this document: $0.** The confirmatory run is not
authorised here. It is authorised by a dated amendment after Stage 0 returns GO.

## How to treat this document

This is the prior session's best design, written by a session that read the record and the
installed surfaces but ran nothing. Each decision below is labelled **Revisable** or
**Non-negotiable**. A *Revisit if* names the evidence that can reopen a revisable decision. The
operator owns scope, the registry, and every `[reserved]` item. A later session with better
evidence surfaces disagreement with reasoning; it does not silently deviate.

## 1. Which claim this study tests

**Decision (Non-negotiable; operator correction 6485676422):** #850 tests the **named-skill
effect**: for each selected card, the effect of mounting that card versus mounting no card on
a pre-registered task set, under the treatment-policy estimand of `v0.2-preregistration.md`
Amendment 3 (treatment = exposure; invocation `pi_c` recorded, never a gate). It does **not**
test H1 of the class-hypothesis record. H1 is a claim about an inference rule (what a null
*means* by class). Testing it requires a design that varies class while holding sensitivity,
task mix and liveness fixed. No arm set proposed in #850 does that. A comparison of average
effects across cards of two kinds measures the cards, not the rule.

**Consequence.** This is a separate registration. The class-hypothesis record receives a dated
Amendment 2 that records the construct result below and points here. Its registered text is
unchanged.

## 2. The construct mapping, tested against the registry's written definitions

`value_class_registry.py` defines its classes by where value lands: `trap-discipline` guards
"one specific wrong action"; `calibration` makes "a measurement sound"; `transformative-lift`
is the class the screen "can validly CUT", value arriving as lift on the task outcome.

**Written criteria used here.** A card is **procedure/trap** when its description names one
specific wrong action and the check that prevents or repairs it. A card is **ability-style**
when its description restates a general capability and names no specific failure.

| Card | Description (first clause) | Criterion met | Nearest `value_class` |
|---|---|---|---|
| `pull-rebase` (mrbinnacle-engineering 3.1.0) | "Use before `git pull` where `pull.rebase` may be `true` … Check config first; recover by reflog." | names one wrong action and its check | `trap-discipline` (registered) |
| `mocked-stub` (mrbinnacle-engineering 3.1.0) | "Patching a helper that is itself a production stub turns a test green on a branch that never ran." | names one wrong action | `trap-discipline` (registered) |
| `sqlite-tie-break-red-test-trap` | registry-retired 2026-07-10 | names one wrong action | `trap-discipline`; **ineligible** (retired) |
| `pstack:sharpen` (0.9.102) | "Sharpen a task before starting: the expert approach, what the user is really after…" | general capability, no failure named | would be `transformative-lift` |
| `pstack:principle-foundational-thinking` (0.9.102) | "Get the data structures right so downstream code becomes obvious." | general capability | would be `transformative-lift` |
| `ste-rewrite` (`~/.claude/skills`) | "Rewrite or author text in ASD-STE100-style Simplified Technical English…" | general capability with a named standard | would be `transformative-lift` |

**Finding.** "Ability versus procedure" is a **mechanism axis** (restated capability versus
named-failure guard). It is not a new `value_class`. Procedure cards map onto `trap-discipline`
by the registry's own text. Ability cards map onto `transformative-lift`, the class that has had
**zero members** since the registry was written. None of the three class definitions turns on
whether the model already holds the capability, which is the ability-style claim's content, so
the mapping is defensible but not an identity: a card can be ability-style and still fail to be
a valid `transformative-lift` member if its value never lands on the outcome at all.

**Registry write `[reserved]` (operator).** Recording an ability card under `TRANSFORMATIVE_LIFT`
makes the screen path's `CUT` reachable for it. #850 forbids a KEEP or CUT verdict. The mapping
is recorded here; whether any card enters the registry is the operator's value call (registry
docstring: "the operator owns the value call"). *Revisit if:* the operator records an entry; then
this study's cards are read against the registry as well as this table.

## 3. Arms and eligibility

**Eligibility rule (Non-negotiable; issue body):** every confirmatory card is live, installed and
in active use at selection. Evidence recorded per card, with date: (a) present in the Claude Code
session skill listing on the selection day; (b) absent from any `RETIRED.md`, `_quarantine/`,
`_archive/` or backup root, and not marked retired in the registry; (c) the delivered tree pinned
by git blob ids in the launcher, on the `v4_cells.FULL_TREE_BLOBS` pattern. A cache directory
label is not a pin (S536). **On disk is not live:** `zoom-out` sits in `~/.claude/skills` and is
absent from the 2026-10-28 session listing, so it fails (a).

| Arm | Slot | Candidate measured 2026-10-28 | Status |
|---|---|---|---|
| A1 | Public ability-style card, first-principles family | `/first-principles` (prodmgmt.world): **not installed** on the host (`find ~/.claude -iname '*first-principles*'` returns only pstack's `principle-redesign-from-first-principles`, whose description is narrow: "integrating a new requirement into an existing design"). | **Slot open.** The operator picks the card `[reserved]`; many public first-principles cards exist, and one qualifies once installed and listed before selection. Fallback if none is installed by selection day: `pstack:sharpen` 0.9.102 (installed, listed). |
| A2 | In-house ability-style card | `ste-rewrite` (listed 2026-10-28); `self-documenting-code` (listed) | eligible; `ste-rewrite` preferred for the shorter description |
| N | No card | stock agent environment, as the v0.2 Null-arm definition | — |
| P | Procedure/trap positive control | `pull-rebase` 3.1.0 (listed through `mrbinnacle-engineering`; registry `trap-discipline`; vendored and blob-pinned at `scripts/screens/419/v4_arms/full/pull-rebase/`) | eligible; the only card in the record with a measured non-null (Stage 1A: Full 50/97 vs Null-A 34/97) |

**Displaced-enforcement note (Revisable).** `pull-rebase`'s production reliability comes from a
`PreToolUse` hook. The sandbox has no hook, so arm P measures the card text standing alone. That
is acceptable for a sensitivity check and is stated so a reader does not read P as the
discipline's verdict. *Revisit if:* a hook-present arm is registered by amendment.

## 4. The positive-control gate

**Non-negotiable (sharpening comment item 1).** No result for A1 or A2 is read unless P − N
separates first: the lower anytime-valid bound on μ_P − μ_N exceeds 0 at the adopted alpha
reading B (0.0125 per one-sided bound, 0.05 in total; `stage1a-readout-691.md` Amendment 2).
If P does not separate, A1 and A2 are reported **UNINTERPRETABLE**, not null, with the P − N
interval beside them. If P separates, that establishes sensitivity to an effect of P's size on
this task set and nothing larger.

## 5. Gate fields

| Field | Value |
|---|---|
| Hypothesis | **H_A (ability):** mounting an ability-style card changes the world-correct rate on tasks its description claims, relative to N. **H_P (control):** mounting `pull-rebase` raises the world-correct rate on the #419 cue task relative to N. Prior art predicts H_A near zero for a frontier model (section 8). The registered expectation is stated and carries no directional weight in any rule. |
| Pending decision | Whether a skill that restates a general ability is worth the standing tokens it costs, reported per card and per clause with cost, per #96. **No KEEP or CUT verdict is issued** (Non-negotiable). |
| Primary contrast | Two primary contrasts, A1 − N and A2 − N, ITT on exposure, paired by launch index as in Stage 1A. Family of 2: alpha 0.05 split per the Stage 1A accounting, then Bonferroni across the two (0.025 per contrast, allocated over its one-sided bounds). P − N is a gate (section 4), not a primary. |
| Task source | Deterministic-oracle tasks only. First candidate: the #419 release-manifest cue task (`scripts/screens/419/v5_cue_*`), the only family in the record with a non-ceiling Null (0.351 at n=97) and a measured P effect. **Scope check (Non-negotiable):** before any run, a written check that each ability card's description names the demand the task makes (reading the trace before acting; stating what the user is after). Recorded per card with the quoted clause. If an eligible ability card fails the scope check, its arm needs a new task family, a v0.2 Stage-0 Null screen (p0 < 1), and a dated amendment. |
| Oracle set | The #419 world-correct oracle, binary, deterministic, pristine at score time. No judge: PRD §3.1 admits a Tier-2 judge only after calibration, and none exists. A judge-graded axis anywhere in this study is UNMEASURED. |
| Subject layer | As Stage 1A: `inspect_ai` + `inspect_swe.claude_code()`, Docker sandbox, cards delivered by the `build_paired_tasks` tree copy. Exposure detector v2 on every epoch; Null-arm exposure or invocation refuses the pair (Amendment 3 ruling 3). |
| Harness pin | One `HarnessPin` for all four arms: agent version, model id, sandbox image digest, `env`, `disallowed_tools`, compose file hash. Card trees blob-pinned. A pin mismatch across arms makes the epoch inadmissible. |
| Differentiation vs field | Zheng et al. v2 and Meincke et al. tested personas and chain-of-thought instructions on question answering, not skill cards on agentic tasks with a no-card control and a positive-control gate. This study adds the gate, the exposure/invocation split, and per-card standing and fired token cost. |
| MDE and sizing | **Not computed here, and bounded.** Stage 1A's +0.164 (P − N) did not clear the anytime-valid bounds at n = 97 (lb μ_F 0.385 < ub μ_N 0.463). Amendment 4's registered Gate-2 row (n = 32, δ_min = 0.20) targets 0.6 → 0.9 and would not detect +0.16 either. The n at which P separates is therefore larger than any run in the record. Sizing is routed to the Stage 2 simulator (#719, #720, #798), zero spend, as Stage 0 below. |
| Stopping rule | Per-arm one-sided betting bounds (`aggregation/confidence_sequence.one_sided_betting_bound`) at alpha reading B, n_max from Stage 0, deterministic curtailment. No peeking rule beyond the anytime-valid bounds. |
| Leak audit | Static grep of every subject-visible artifact for each card's name and distinctive vocabulary, both directions; fresh-context reviewer pass; post-run transcript grep. Null-arm exposure detector must read 0/n. |
| Budget | **$0 authorised here.** Stage 0 is zero-spend. The confirmatory cap is set by the dated amendment that registers n, and may not exceed the operator's stated cap at that time. |

## 6. Stage 0 — the feasibility stop (registered before any spend)

1. **Sizing.** Run the Stage 2 simulator against the Stage 1A arm rates (N 0.351, P 0.515) under
   alpha reading B and find the smallest n per arm at which P − N separates with power ≥ 0.80.
   Price it at the Stage 1A per-epoch cost. **GO** iff four arms at that n fit the operator's cap.
   **NO-GO** otherwise, and the NO-GO is published: under the house invariants the four-arm study
   is not runnable at an affordable n, which is a result about the instrument.
2. **Eligibility and scope.** Fill the A1 slot; record the eligibility evidence and the scope
   check for A1 and A2 per sections 3 and 5.
3. **Instrument challenge (issue "measurement dossier" item 4).** Run the launcher, detector,
   oracle and readout on the Stage 1A `.eval` logs as real-format input; recompute 50/97 and 34/97;
   inject one planted fault per class (a Null epoch with the card listed; a swapped pair; a void
   epoch) and show each is refused or counted as registered.
4. **Freeze.** A dated amendment records n, cap, the A1 card, the scope-check text and the
   challenge results. Only then is the confirmatory run authorised.

## 7. Clause-level reporting

Whole-card arms do not identify clause effects. Each card's clause token costs (`standing_tokens`,
`fired_tokens`, per-clause extractor counts) are reported mechanically. Behavioural contribution
per clause is labelled **UNMEASURED** unless a clause-removal arm is registered by amendment with
its own estimand, multiplicity and power statement (#96 double-ceiling warning).

## 8. Prior art, as context

- Zheng et al., arXiv 2311.10054 **v2** ("When 'A Helpful Assistant' Is Not Really Helpful"):
  personas in system prompts did not improve over a no-persona control across model families on
  factual questions. v1 reported the opposite for interpersonal roles and is not cited.
- Meincke, Mollick, Mollick, Shapiro, arXiv 2506.07142 (2025): chain-of-thought instructions give
  marginal or no gain on reasoning models at higher token cost. Effect sizes not verified against
  the full text; no number from it enters any rule here.

Both predict H_A near zero. Neither tested agentic tasks or skill cards. They set the
expectation; they are not evidence for this study.

## 9. Done when

Stage 0 items 1 to 4 are recorded in a dated amendment, or Stage 0 returns NO-GO and the NO-GO is
recorded. Either is a complete outcome of this registration.

*Revisit if:* a calibrated pairwise judge exists for an axis an ability card claims (then a
judge-graded task family becomes admissible by amendment); a second trap card shows a measured
effect on a deterministic task (then P has an alternative); or the operator records a registry
entry for an ability card (section 2).

---

## Correction 1 — 2026-10-28: arm P's bytes, and two overstated phrases (same session, before any run)

This block is dated and appended under the amendment rule. Nothing above it is changed. The
SHA-256 posted on #850 and PR #851 for the first commit (`bf87f1c`) names the file without this
block; the hash of the file with it is in the commit that adds it.

**1. Arm P names one version and the pin names another.** Section 3 reads "`pull-rebase` 3.1.0
… vendored and blob-pinned at `scripts/screens/419/v4_arms/full/pull-rebase/`". Measured
2026-10-28 with a CRLF-normalised `diff`: the vendored tree is the tag `v3.0.0` card text, and the
installed 3.1.0 card differs from it in the description and in seven further hunks (dated source
citations, a measured `--ff-only` exit, a `git range-diff` recovery step, a hooks note). The
launcher's `v4_cells.FULL_TREE_BLOBS` refuses any tree but the vendored one
(`stage1a-readout-691.md` Amendment 1).

**Decision (Revisable).** Arm P delivers the **installed 3.1.0 card**, blob-pinned fresh at
selection. The eligibility rule in section 3 is the issue's non-negotiable, and the study exists to
stop category from standing in for liveness; delivering the 2026-09 bytes would reintroduce the
proxy. Two consequences follow and are stated: (a) Stage 1A's P − N of +0.164 was measured on the
`v3.0.0` text, so for sizing it is a **prior**, not P's expected effect, and Stage 0 item 1 sizes
on it as such; (b) the launcher needs a `FULL_TREE_BLOBS` entry for the 3.1.0 tree, a code change
ticketed under Stage 0, with the 3.1.0 tree vendored byte for byte beside the `v3.0.0` one. A result
on 3.1.0 is not pooled with Stage 1A. *Revisit if:* the operator rules that comparability with
Stage 1A outranks liveness for the control arm; P then delivers the vendored `v3.0.0` tree and
section 3 says the live version is the card, not the bytes.

**2. "The only family in the record with a non-ceiling Null" (section 5) is too strong.** The
record also holds `cue-v5-stage1-null-screen.md` (Null(A+cue) Y 1/7, Null(B) Y 5/8, n = 7 and 8)
and the 2026-09-01 gitpull k = 8 pilot (Null 0/8; v0.2 Amendment 3). Both are ancestors of the #419
cue task and both are small. Read section 5 as: the #419 cue task is **the best-characterised
non-ceiling Null in the record** (0.351 at n = 97). `twin-v4-stage1-null-screen.md` records Null(A)
correctness 8/8, a ceiling, and is not a candidate.

**3. "Measured non-null" (sections 3 and 5) reads loosely.** The literal form: Stage 1A recorded a
+0.164 point difference, Full 50/97 against Null-A 34/97, **not established** at alpha reading B
(verdict CANT_TELL_YET at n_max = 97). No sentence above should be read as a claim that P has an
established effect.
