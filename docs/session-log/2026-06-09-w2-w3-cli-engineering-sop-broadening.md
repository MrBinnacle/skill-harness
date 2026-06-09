# Session log — 2026-06-09 · W1 follow-up + W3 SOP broadening + W2 CLI engineering

**Window:** orchestrator session continuing the signal-acquisition cycle locked through 2026-07-08.
**Entered with:** v0.1.0 shipped, three workstreams queued in handoff (`%TEMP%\skill-harness-handoff-2026-06-08-post-t3.md`), case-study rewrite flagged as "PENDING REWRITE" in handoff.
**Exited with:** all three workstreams complete + .gitignore housekeeping precondition + 952 tests passing on `main`. Next gate: T1 frame-legibility reader pick (PM-owned, unblocked).

---

## Session arc

### 0 · Re-entry (session-startup skill)

Sources-of-truth read printed:
`PRD@2767f19 · PLAN@8006cac · COUNCIL_FINDINGS@9cc0fa6 · checkpoint@94ce54d`.

### 1 · Stale-handoff catch (small HALT-as-deliverable moment)

PM directive: "read the handoff and propose the case-study rewrite." Reading the handoff against actual repo state surfaced a state-drift: the case-study rewrite the handoff said was "PENDING" had already landed at `a2c9fd9` (2026-06-08 13:17 EDT), with every Sutherland-framing input the handoff named already in place. The handoff was authored BEFORE that commit.

Surfaced the catch rather than silently proposing a rewrite-from-scratch, per the HALT-as-deliverable instinct extracted yesterday into `~/.claude/skills/_quarantine/halt-as-deliverable/`. PM chose "Propose further revisions" over the alternatives.

### 2 · Case-study craft refinements (W1 follow-up — `ca965e7`)

Diagnosed the existing draft: structurally sound, framing inputs landed, what was left was craft-level. Proposed three tiers (4 high-leverage moves, 3 judgment calls, 3 optional polish). PM chose Tier 1 (E1–E4):

- **E1** · Title pivot to active voice: `"Catching myself: a case study in AI agent self-audit infrastructure"` (was noun-first). New-category claim preserved as subtitle.
- **E2** · Promoted the buried Sutherland-line — *"I had built a framework whose default subject client couldn't run on the machine I built it on"* — from the last line of HALT 2 item 1 to a standalone bold paragraph after the enumeration. The line a T1 reader is most likely to quote.
- **E3** · Hammer-strike paragraph after `"That is the artifact."`, translating the audit-trail frame into a reader-actionable form ("anyone running the same discipline ... would catch some").
- **E4** · Cost-framing attack added to `"What three HALTs amount to"`: converted $0.00-in-vendor-spend from a fact to the question the enterprise reader cannot dismiss.

Net +13/-4 lines. Tiers 2 (reorder, compress, move-not-claim-earlier) and 3 (optional polish) noted as available, not applied.

### 3 · W3 SOP broadening (`b25e6c6`)

Doc-only edit to `.claude/skills/dev-team-council/SKILL.md` "Precondition check" section. Two changes:

- Resource taxonomy expanded from one inline sentence to six bulleted categories: technical infrastructure, monetary (now distinguishing per-work allocation from cumulative-spend awareness), human/relational, PM bandwidth, data/labeling, governance/disclosure.
- Load-bearing epistemic frame added: *"the human knows things about their own life, network, calendar, psychology, and relationships that the LLM categorically cannot. The precondition check is a query to a knower whose domain the LLM cannot reach by introspection — no amount of careful reasoning over repo state will surface a calendar conflict, a soured relationship with a tester, a regulatory window the PM is tracking, or a credit-card cap the PM has not written down. The check is not caution; it is epistemic asymmetry compensation."*

The 2026-06-08 OpenAI/OpenRouter incident is preserved as the falsifying case that drove the original SOP. Broadening generalizes the taxonomy without weakening the specific lesson.

### 4 · `.gitignore` housekeeping precondition (`f13b3fd`)

`.claude/worktrees/` was not in `.gitignore` (only `.claude/state/` and `.claude/cache/` were). Per `superpowers:using-git-worktrees` safety verification step, project-local worktree directories MUST be ignored before creating new worktrees. Added the line and committed. Pushed `b25e6c6..f13b3fd` to origin.

### 5 · W2 CLI engineering (`a9bdacc`, on `worktree-w2-cli-engineering` branch)

EnterWorktree (native tool) created `.claude/worktrees/w2-cli-engineering` on branch `worktree-w2-cli-engineering`. Baseline tests green (938 pass + 1 live-deselected, matching `main`).

Dispatched a Sonnet 4.6 implementer subagent with a fully self-contained brief (verbatim spec, exact file/line references, TDD discipline, halt-on-ambiguity instruction). The implementer addressed both gaps as one cohesive commit (they're tightly coupled — adding `--subject-model` without fixing the pre-flight check would BREAK the CLI for any non-Anthropic model).

What landed in `a9bdacc`:

- **Change 1** · `--subject-model <id>` Click option on `run ablation`, default `claude-sonnet-4-6`, help text covering direct/OpenRouter/fallback forms.
- **Change 2** · `subject_model` threaded through `run_ablation` → `_cmd_execute` → `_execute_ablation_run`. `subject = SubjectClient()` replaced with `subject = make_subject_client(subject_model)`. Unused `SubjectClient` import dropped.
- **Change 3** · New module-level `_resolve_subject_model_with_fallback(subject_model)` replaces the unconditional `ANTHROPIC_API_KEY` pre-flight. Resolver rules: `claude-*` ⇒ ANTHROPIC then OpenRouter fallback; `gpt-*` / `o<digit>-*` ⇒ OPENAI then OpenRouter fallback; explicit `<provider>/<model>` ⇒ OPENROUTER only. Warnings via `click.echo(..., err=True)` per PRD §16.1 pipeline discipline. Refusals name BOTH env vars the operator could set.
- **Tests** · 11 new tests in `tests/ablation/test_subject_model_flag.py` covering the resolver matrix + CLI plumbing + factory wiring. All offline.

Gates clean (mypy --strict authoritative; pyright worktree diagnostics stale per checkpoint).

Implementer surfaced one concrete trap during self-review (noted as a finding):

- **CliRunner `env` override semantics**: passing a key as ABSENT from the env dict does NOT delete it — you must pass `{key: None}` to trigger deletion. An existing test (`test_cli_d3_fixes.py::TestM3ApiKeyPreflight::test_missing_api_key_refused_before_db_write`) built `clean_env` by omitting `ANTHROPIC_API_KEY`. On a machine with `OPENROUTER_API_KEY` set in the real env (i.e., this one), the new resolver would rewrite the model and proceed to a 12-minute live API call. Fixed by explicitly passing `{key: None}` for both keys.

### 6 · Fan-out for spec + quality review

PM directive: "fan out subagents to be proactive and prep final tasks." Dispatched spec compliance reviewer + code quality reviewer in BACKGROUND (parallel) so prep work (drafting this log + checkpoint to TEMP) could run inline.

Outcomes:

- **Spec compliance review** (Sonnet 4.6, fresh context) — ✅ SPEC COMPLIANT, all 13 verification checks passed line-by-line. No missing requirements, no scope creep.
- **Code quality review** (Sonnet 4.6, fresh context) — ⚠️ APPROVED WITH MINOR FIXES. Two Important findings flagged:
  1. **o-series regex divergence**: resolver used `^o[0-9]+-` (dash required) while factory accepts `model[1].isdigit()` (no dash). Bare `o4` would fall through resolver's unrecognized-model branch, miss the OpenRouter rewrite contract.
  2. **Missing test cells**: `gpt-* + no keys → raise` and `o-series + no keys → raise` paths exercised only indirectly via CliRunner; no direct unit tests mirroring `test_resolver_claude_with_no_keys_raises`.
- Three Minor findings explicitly deferred (inline-import style, factory-as-probe pattern, test-file placement).

### 7 · Fix cycle (`f6201a8`)

Resumed the same implementer via SendMessage (preserves context, no re-briefing cost). Two Important findings fixed exactly as specified + one optional bonus test (`test_resolver_o_series_bare_with_only_openrouter_rewrites`) added as regression guard for the regex alignment. Single follow-up commit, +73/-2 across the same 2 files. Inline comment added at the regex line documenting the alignment-with-factory rationale.

Re-review (Sonnet 4.6, fresh context, narrow scope) — ✅ APPROVED. Regex change exact, 3 new tests follow the established pattern, no out-of-scope changes, 952 tests passing, all 4 gates clean.

### 8 · Merge + push + closeout

- ExitWorktree refused (session has cwd-override semantics post-EnterWorktree); used `git -C "<main>" merge --ff-only worktree-w2-cli-engineering` from the worktree directory instead. Fast-forward; main advanced f13b3fd → f6201a8 (2 commits, +521 insertions).
- Drafted session-log + checkpoint applied from TEMP scratch files; placeholders filled with actual SHAs post-merge.
- This commit is the closeout doc commit. Worktree cleanup deferred per carry-forward (not urgent).

---

## Decisions of note

- **State-drift catch over silent fix**: the case-study handoff said PENDING; reality was DONE. Surfaced it explicitly rather than proposing a rewrite-from-scratch. Anti-instance: would have wasted ~30 minutes producing a draft of work already shipped.
- **W2 tasks 1 + 2 collapsed into one implementer dispatch**: SDD per-task review pattern would have been wrong here because the two gaps are tightly coupled (adding the flag without fixing the pre-flight breaks the CLI). Single cohesive commit per handoff guidance.
- **mypy --strict authoritative over pyright LSP**: per checkpoint, pyright worktree diagnostics are documented stale. After the W2 dispatch, pyright showed 4 "missing parameter" errors that were stale-cache false positives — verified by `grep -n` on the source plus `mypy --strict` returning clean. Did not chase.
- **W3 + .gitignore + W2 → one push each, not one bundled push**: per "per-milestone gesture" handoff pattern. Three pushes today (1 for case-study refinements, 1 for W3+gitignore, 1 pending for W2 merge + this log).
- **Reviewers dispatched in background, not foreground**: explicit PM directive to be proactive + prep final tasks. Single-agent parallelism = backgrounded subagents + inline drafting.

## Carry-forwards

- **C1 tie encoding**: still data-blocked.
- **Case-study Tier 2 + Tier 3 refinements (E5–E10)**: drafted, not applied. Available if T1 reader pick surfaces friction the existing draft doesn't address.
- **Worktree cleanup**: now ≥16 subsumed worktrees (added `w2-cli-engineering` today). Manual unlock+remove path documented in prior handoff; mechanical, low-priority. PM has not indicated urgency.
- **CF-4.1-A/B/C** + **Windows cp1252** + **Extractor stochasticity** + **Tier-1 scorer registry expansion** + **tests/ mypy cleanup** + **Phase 3.3-bis mutation sweep**: all v0.2 deferred per 2026-06-07 session-log.
- **Pre-existing evidence.db state**: 5 incomplete + 3 completed prior ablation runs. Untouched this session.

## Open questions / values decisions queued

- **T1 frame-legibility reader (PM picks)**: unblocked. Case-study draft is now in shippable form (E1–E4 landed); CLI gaps fixed; SOP broadened. Per the signal-acquisition calendar, this is the next gate (target window 2026-06-15 → 2026-06-18).
- **T4 cheap-friendly tester (PM picks)**: still gated on T1 outcome.
- **C1 tie encoding**: data-blocked carry-forward.

## Artifacts produced

- `docs/case-studies/ai-slop-sentinel-under-ablation.md` — refinements (commit `ca965e7`, +13/-4)
- `.claude/skills/dev-team-council/SKILL.md` — SOP broadening (commit `b25e6c6`, +36/-8)
- `.gitignore` — `.claude/worktrees/` line (commit `f13b3fd`, +1)
- `src/skill_harness/cli/main.py` + `tests/ablation/test_subject_model_flag.py` + `tests/ablation/test_cli_d3_fixes.py` — W2 CLI engineering: `a9bdacc` (feat) + `f6201a8` (fix follow-up after quality re-review). Fast-forward merged to main.
- `.claude/state/checkpoint.md` — this update
- This file

## Next gate (fresh session)

T1 frame-legibility tracer: PM picks ONE reader, 72-hour reaction window. Case-study + CLI are shippable; pre-flight check now demonstrates the broadened SOP discipline in code. Targeted-send batch (gated on T1) follows 2026-06-18 → 2026-06-22.
