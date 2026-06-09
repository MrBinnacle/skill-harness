---
name: dev-team-council
description: >
  Multi-seat parallel council review pattern for the skill-harness project,
  fired as the DEFAULT mechanism for architectural decisions, storage-touching
  changes, new external surfaces, and pre-tag launches. Names the 9-seat
  roster (5 CORE + 4 SPECIALIST), explicit trigger conditions, four standard
  council templates, and delegates dispatch mechanics to the global
  cross-talk-council-dispatch and parallel-review-disposition-schema skills.
---

# Dev-Team Council

This skill codifies the project's standing review body. The first council fire
(2026-06-03, documented in `docs/COUNCIL_FINDINGS.md`) produced 17 adopted
decisions that gate every Phase 2 track. This skill exists so the pattern is
repo-resident infrastructure, not a thing the assistant happens to remember.

## Orchestrator (always-on meta-role)

The orchestrator is the role the main agent assumes by default. It is NOT a
review seat — it dispatches the council. The 9 review seats produce findings;
the orchestrator decides what to do with them. Pinned to Opus 4.7 per the
project CLAUDE.md model-pinning section (synthesis, sequencing, gate
decisions). Tracks A–E execution dispatches to Sonnet 4.6.

### Contract

The orchestrator owns:

- **Build coherence** — `PRD.md` ↔ `PLAN.md` ↔ `docs/COUNCIL_FINDINGS.md` ↔
  `.claude/state/checkpoint.md` are mutually consistent. Drift between them is
  the orchestrator's bug.
- **Track sequencing** — which worktree fires when, per `PLAN.md` "Named
  council fire points." Track D blocked until A+C green; Track E blocked
  until A+D green.
- **Council fire decisions** — fire-or-proceed per the trigger table below.
  Decision is recorded in the session log as "Council fired [seats] for
  [reason]" or "Routine — no fire, decision A_N applies."
- **Exit-gate adjudication** — a track is done when its `PLAN.md` exit
  criteria are met AND its declared council fire produced no unresolved
  BLOCKER. Self-claims of "done" are not enough.
- **PRD amendment shipping** — the 16-amendment queue in `COUNCIL_FINDINGS.md`
  ships as a single v1.1 doc-lock PR. Not piecemeal.
- **Scope discipline** — surface `[values decision]` only when a competent
  role default doesn't exist (CLAUDE.md global §0.6). Defer to v0.2 when
  scope conflicts with `PLAN.md` "Out of scope" list.
- **Cross-worktree merge order** — when parallel tracks land, decide merge
  sequence; reconcile interface conflicts before integration.

### Session-start protocol (falsifiable)

Every session begins with the orchestrator invoking `session-startup` (see
companion skill). The first line of the orchestrator's first user-facing
output MUST be:

```
Sources of truth read: PRD@<sha7> · PLAN@<sha7> · COUNCIL_FINDINGS@<sha7> · checkpoint@<sha7>
```

This is the observable check that the role was performed. A session that
proceeds without printing this line has skipped re-entry; correct by aborting
the action and starting over.

### Session-end protocol

Before the session closes, the orchestrator writes:

1. `.claude/state/checkpoint.md` — updated current-state snapshot, next-gate entry
2. `docs/session-log/<YYYY-MM-DD>-<slug>.md` — append-only entry capturing:
   - phase entered, phase completed
   - council fires (with seat list + finding IDs + archive path)
   - decisions made (with rationale and PRD/COUNCIL_FINDINGS anchors)
   - open questions / values decisions queued
   - artifacts produced (paths + SHAs)

### Not the orchestrator's lane

- Reviewing code — that's the review seats
- Implementing code — that's the track subagents
- Owning the PRD's product intent — that's the user (surface via `[values decision]`)
- Adversarial review — that's `ai-slop-sentinel` + `adversarial-spec`

## When to fire

Triggers:

- New PRD section or scope change
- New ADR-worthy architectural decision
- New external surface (CLI command, API endpoint, evidence/runtime schema table)
- Any change crossing a load-bearing invariant listed in CLAUDE.md
- Pre-merge for changes touching `migrations/`, `src/skill_harness/storage/`, or judge-prompt code paths
- Pre-launch for any version tag (v0.1, v0.2, ...) — full council with all 9 seats
- Disagreement between two prior reviewers on an architectural call (escalation)

When NOT to fire:

- Routine implementation following an already-decided invariant
- Dependency bumps with no API surface change
- Documentation-only edits
- Test-only refactors

## Roster

The roster has two tiers. The 5 CORE seats fire on every architectural
decision. The 4 SPECIALIST seats fire when their domain trigger condition is
met. All seats default to READ-ONLY per CLAUDE.md global §4 unless the main
agent escalates per-segment.

### CORE seats (fire on every architectural decision)

| # | Seat | Scope | Subagent | Cross-talk partners |
|---|---|---|---|---|
| 1 | **TEST-ARCH** | Falsifiability gate, vacuity detection, confound symmetry, clause status state machine. Owns PRD §3.4, §7, §8, §11, §15, §20. | `Plan` | STAT, SCHEMA, EVAL-RESEARCH |
| 2 | **STAT** | Beta-Binomial conjugacy, multiplicity correction, variance budgeting, sample-size floors, sequential stopping. Owns PRD §14. | `general-purpose` (WebSearch) | TEST-ARCH, EVAL-RESEARCH, COST |
| 3 | **SCHEMA** | Append-only enforcement, two-DB partition, write-time snapshot, schema migration tamper-evidence, index design. Owns PRD §6, §9, §10, §17. | `general-purpose` | TEST-ARCH, RELIABILITY, SECURITY |
| 4 | **EVAL-RESEARCH** | Prior art across LLM eval literature, judge calibration protocols (κ, ICC, pairwise-preference accuracy, position-swap), Tier-3 realizability. Owns PRD §5 Tier 2/3, §13. | `general-purpose` (WebSearch + WebFetch heavy) | STAT, TEST-ARCH, SECURITY |
| 5 | **COST** | Token economics, prompt-cache placement, sampling strategy, hard-cap enforcement, dry-run shape. Owns PRD §18 cost surface, `runtime.run_budget` table. | `general-purpose` | STAT, RELIABILITY, OPERATOR-DX |

### SPECIALIST seats (fire when domain triggered)

| # | Seat | Scope | Fires when | Subagent | Cross-talk partners |
|---|---|---|---|---|---|
| 6 | **SECURITY** | Adversarial input handling (judge outputs are attacker-influenced), prompt injection in evaluated outputs, API key surface, supply-chain mitigations. | new external input surface; key-handling code; judge prompt design; dep changes; public visibility flip | `general-purpose` | SCHEMA, EVAL-RESEARCH, RELIABILITY |
| 7 | **RELIABILITY** | Partial-run recovery, crash safety, observability, single-writer queue backpressure, retry policy, idempotency. | long-running operations; crash-recovery code; write-queue design; run state machine | `general-purpose` | SCHEMA, COST, OPERATOR-DX |
| 8 | **OPERATOR-DX** | CLI shape, error messages, dry-run UX, progress reporting, naming, exit codes. | CLI surface changes; new commands; error-path changes; public-facing config keys | `general-purpose` | COST, DOCS-DX, RELIABILITY |
| 9 | **DOCS-DX** | Onboarding clarity, README accuracy vs reality, surface drift, CHANGELOG entries, public API renames. | user-facing doc changes; release prep; public API renames | `general-purpose` | OPERATOR-DX, EVAL-RESEARCH |

## Dispatch protocol

- Every seat dispatched in **PARALLEL** using the Agent tool. Multiple Agent tool uses in ONE message run concurrently; multiple messages run serially. A council fired one seat per turn is sequentially scheduled and loses the cross-talk synthesis quality.
- Each seat's prompt MUST include the `cross-talk-council-dispatch` mandatory cross-talk block (predict what each OTHER firing seat will be RIGHT about, WRONG about, MISS).
- Each seat's prompt MUST use the `parallel-review-disposition-schema` output contract: fixed `BLOCKER / MAJOR / MINOR / OBSERVATION` decision vocabulary; per-item block with `ID / Title / Severity / PRD anchor / Claim / Evidence / Recommendation / Cross-seat`; mandatory status line as the last line of the response.
- Seats are READ-ONLY by default per CLAUDE.md global §4. Lift the read-only default per segment with bounded, audited escalation if needed.
- Each seat's prompt embeds: the question(s) being asked verbatim, locked decisions to NOT relitigate, the names + scopes of the OTHER firing seats (for cross-talk grounding), and file paths it may need to read.
- Post-return: synthesize via the `parallel-review-disposition-schema` mechanical pattern. Verify every external citation per `subagent-research-reliability` discipline before adopting any finding.
- Adopted decisions append to `docs/COUNCIL_FINDINGS.md` with seat-finding IDs as provenance. PRD amendments queue for v(N+1) doc lock, NOT piecemeal edits.

## Precondition check (mandatory pre-fire step)

Before firing the subject-matter seats in any template below, the orchestrator
verifies that PM-owned resources required by the proposed work are accessible.

PM-owned resources include, but are not limited to:

- **Technical infrastructure**: API keys for any external service the work
  touches, network/access tokens, third-party account permissions,
  hardware/runtime not in the orchestrator's environment, CI/infra capacity.
- **Monetary**: budget allocation for the specific work, AND cumulative
  spend awareness (where the work sits against any rolling or absolute cap
  the PM is tracking).
- **Human / relational**: testers, reviewers, authors, peers, recipients of
  outbound communication; whether the PM has the network or audience access
  required by any "send" or "publish" step in the work.
- **PM bandwidth**: calendar availability for review checkpoints, attention
  budget for synchronous discussion, deadline conflicts with other
  commitments the PM is carrying.
- **Data / labeling**: human-labeled calibration sets (e.g., for the v0.2
  Tier-1 scorer registry expansion), evaluation corpora, golden datasets,
  or any other artifact that must exist before the work is reproducible.
- **Governance / disclosure**: timing constraints from external commitments
  — regulatory windows, embargo dates, partner notification cadences,
  pre-registered analysis plans, public-disclosure sequencing.

If any required resource is unverified, surface to PM as a **single
closed-form question** BEFORE dispatching subject-matter seats. Do not
dispatch on the assumption that resources are available; subject-matter
seats are expensive to run and their findings are wasted if the work
cannot be executed.

**The load-bearing reason this check exists**: the human knows things about
their own life, network, calendar, psychology, and relationships that the
LLM categorically cannot. The precondition check is a query to a knower
whose domain the LLM cannot reach by introspection — no amount of careful
reasoning over repo state will surface a calendar conflict, a soured
relationship with a tester, a regulatory window the PM is tracking, or a
credit-card cap the PM has not written down. The check is not caution; it
is epistemic asymmetry compensation.

This step exists because skipping it has caused real wasted-fire incidents
(2026-06-08: T3 tracer dispatched Tier 1 + Tier 2 against `openai` SDK before
verifying PM had OpenAI access; PM had OpenRouter instead, requiring the
fire to be re-scoped after both subject-matter seats had completed). The
discipline of *checking access before checking correctness* is load-bearing
regardless of how minor the work feels.

## Standard council templates

Four named templates so common fires don't require re-thinking the roster.
ALL templates run the precondition check first.

- **PRD pressure-test (pre-build)** — 5 CORE + SECURITY + RELIABILITY. The expanded original (the first fire's 5-seat roster + the two specialist seats it under-covered).
- **Storage-touching change** — SCHEMA + RELIABILITY + SECURITY + TEST-ARCH. 4 seats.
- **CLI / surface change** — OPERATOR-DX + DOCS-DX + COST + SECURITY. 4 seats.
- **External-vendor / API-surface change** — precondition check (PM resource availability) + COST + SECURITY + RELIABILITY. 3 seats after the precondition. Use when the work adds a new external service dependency (vendor SDK, API gateway, third-party service). Distinct from "CLI / surface change" because the load-bearing pre-fire question is "does the PM have access?" not "is the CLI shape right?"
- **Pre-tag launch council** — all 9 seats.

## Antecedents

- `docs/COUNCIL_FINDINGS.md` — the first council fire output (5-seat synthesis, 2026-06-03)
- `~/.claude/skills/cross-talk-council-dispatch/` — cross-talk dispatch mechanics
- `~/.claude/skills/parallel-review-disposition-schema/` — output contract / synthesis pattern
- `~/.claude/skills/subagent-research-reliability/` — citation verification discipline
- `~/.claude/skills/verbatim-content-subagent-dispatch/` — for content-producing dispatch
