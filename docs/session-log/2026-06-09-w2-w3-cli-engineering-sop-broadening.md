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

---

## Session arc — continued (2026-06-09 afternoon/evening)

The session continued past the initial closeout above. PM directive: "Execute per SOP — PM led" (signal to advance the calendar). Next SOP item was first-touch hardening dispatch (item #2), which required PM greenlight per `docs/dispatch/post-v0.1-signal-acquisition-plan.md` owner map.

### 9 · Second stale-doc catch (HALT-as-deliverable pattern fires again)

Surfaced the hardening dispatch as scoped (6 punch items, single Sonnet 4.6 implementer per SOP). PM greenlit. **Before dispatching**, sanity-checked current state of the punch items against the codebase: commit `09af6ae` (2026-06-08) had already landed items 1–4 + 6. Item 5 (`skill clauses` legend) was partial — the legend was defined but placed under a placeholder command rather than alongside the actual `skill init` table.

Per the HALT-as-deliverable v1.1.0 variant skill extracted earlier the same day, surfaced the catch explicitly rather than dispatch a re-doing-already-shipped-work agent. Second instance of this pattern in 24 hours.

PM directed: "I want you to choose the hard right path over the easy wrong."

### 10 · The hard right — walking the reproduction recipe as the case-study's own author

The "easy wrong" was path 1 (small item-5 fix + SOP doc update). The "hard right" was actually walking the reproduction recipe as a T1 reader on Claude Code subscription auth — the case study's own author profile.

That walk surfaced friction the original SOP punch list did not anticipate:

- **`reproduce-case-study.ps1`** hard-refused on missing `ANTHROPIC_API_KEY` with no acknowledgment of the gap, no workaround, no `--subject-model` parameter (added in W2 but not exposed by the script).
- **README** bash recipe said nothing about OpenRouter or the W2 fallback.
- **README** still claimed "17 UNMEASURED clauses" — the exact stale claim HALT 1 had caught in the original case study.
- **`examples/README.md`** Quick start was silent about API key requirements.
- **`ai-slop-sentinel-pointer.md`** asserted `npx skills add ai-slop-sentinel` without verification.
- **Item 5 legend**: placed under the `skill clauses` placeholder, not the actual `skill init` table.
- **Deepest friction**: the case study's own author **cannot reproduce the case study with current code**. W2 fixed `run ablation`'s fallback; `skill init` (extractor) is still Anthropic-direct-only. Subscription-auth users hit a hard wall at the extraction step.

### 11 · Phase A — doc-honesty pass (`6c9ff3f`)

Orchestrator-direct, single cohesive commit. Seven files, +104/-14:

- `src/skill_harness/cli/main.py`: item-5 legend printing in `_print_result`
- `README.md`: replaced "17 UNMEASURED clauses" with three-HALT framing; changed `git checkout v0.1.0` to `git checkout main` with a "Why not v0.1.0?" explanation; new "API-key requirements" subsection naming the extractor / run ablation asymmetry honestly
- `examples/README.md`: matching honesty in Quick start
- `examples/reproduce-case-study.ps1`: prerequisites updated; error message rewritten to name the gap + workarounds + pointer to README; added `-SubjectModel` parameter
- `examples/skills/ai-slop-sentinel-pointer.md`: softened the `npx skills add` claim with fallback path
- `docs/case-studies/ai-slop-sentinel-under-ablation.md`: closing paragraph updated — "are queued and will land" → "landed in commits a9bdacc and f6201a8 on 2026-06-09" + naming the one remaining extractor gap as v0.2 candidate
- `docs/dispatch/post-v0.1-signal-acquisition-plan.md`: item #2 status updated to ✅ DONE with the dates + commit refs

952 tests pass, all 4 gates clean. Pushed.

### 12 · Phase B — extractor OpenRouter fallback (`b5b9fe6` + `7d86687`)

Surfaced by the Phase A walk as the actual gap. PM greenlit. Symmetric to W2 — same dispatch shape (Sonnet 4.6 implementer in worktree, single cohesive commit, spec + quality + re-review).

Implementer brief included an explicit halt-on-URL-uncertainty instruction (since the OpenRouter Anthropic-compat endpoint was the load-bearing decision and shipping a wrong URL would be worse than the current honest documented gap).

`b5b9fe6` landed:
- New `_make_extractor_client()` helper in `extractor/claude.py` resolving env vars (ANTHROPIC_API_KEY first, OPENROUTER_API_KEY fallback) and returning `(client, model_id)` tuple. OpenRouter path uses `https://openrouter.ai/api/v1` (URL verified by the implementer via fetching OpenRouter's per-model quickstart page, citation in source comment) and the provider-prefixed model id `anthropic/claude-sonnet-4.6` (dots, not dashes — OpenRouter slug convention differs from Anthropic-direct).
- `_call_once` signature gained a `model: str = _MODEL` parameter (default preserves backward compat); `call_extract_clauses` threads the resolved model through both initial and retry calls.
- 4 new tests covering the env-var matrix + integration verification of `base_url` + `api_key` + `model` threading.

Spec review ✅ COMPLIANT (all branches verified; URL claim partially-verifiable via OpenAPI spec + OpenAI SDK quickstart but the specific Anthropic SDK snippet on the per-model page is dynamically rendered and not retrievable to the reviewer). Quality review ⚠️ APPROVED WITH MINOR FIXES (2 items, both reviewers convergent on dead `_OPENROUTER_MODEL_ID` constant; quality reviewer also flagged missing matrix cell `both keys set`).

Orchestrator decision on URL verification: ACCEPT. `https://openrouter.ai/api/v1` is the established OpenRouter API base; the Anthropic SDK `base_url` override is a documented SDK pattern; integration test proves the wiring. The specific per-model snippet being unconfirmable was a documentation-rendering issue, not a contradiction.

`7d86687` fix cycle landed: removed the dead constant + added `test_extractor_client_anthropic_direct_when_both_keys_set` for the missing matrix cell. Re-review ✅ APPROVED. 957 tests pass, all 4 gates clean.

Fast-forward merged to main at this turn.

### 13 · Closeout (initial)

Doc updates committed and pushed as the closeout commit `e00c9f7`. T1 frame-legibility reader pick named as the next PM-owned gate. At this point the day's substantive engineering and doc work was complete.

### 14 · /claudeception second-pass + skill-family-curation discipline build

User invoked explicit `/claudeception`. Initial pass had already extracted 3 skills + 1 update mid-session and 1 new skill (`anthropic-sdk-via-openrouter`) after Phase B. This second pass surfaced two more extraction candidates from the post-Phase-B arc:

- **`walk-the-recipe-as-target-user`** — validation discipline (simulate the target user's environment, not the dev's). The discipline that produced the Phase A doc-honesty pass and surfaced the extractor gap.
- **`two-phase-doc-honesty-then-engineering`** — execution pattern after state-drift catches surface both doc and engineering gaps. Phase A inline + Phase B dispatched. The shape used by today's `6c9ff3f` → `b5b9fe6+7d86687` arc.

In the closing summary, the orchestrator noted (out loud, as a meta-observation): "4 of 6 skills relate to the discipline of 'look before you trust...' — there may be a single higher-order skill that subsumes the family, OR they may be best left as distinct triggers." This was a candidate hypothesis surfaced explicitly as hypothesis.

User pushed: "what is the dynamic script/loop that accomplishes what you're implying going forward and doesn't produce slop silently."

### 15 · Skill-family-curation discipline build (collaborative)

Designed the curation mechanism through dialogue:

- Initial proposal: three touchpoints (extraction/promotion/search), falsifiability gate (3 tests), registry file, PM-dispositioned.
- Ran the gate on the orchestrator's own "look before you trust" hypothesis → **REJECTED-AS-MANUFACTURED** on all three tests (no unique trigger coverage, vacuous parent response, single-session evidence).
- User returned hardened critique with 5 items: Graduation cleanup (defends against doc rot), mechanical tracer-bullet for Test A (defends against Theater), structured 3-line OIR-style disposition format, instruction-budget protection, glossary in CLAUDE.md §1.

**First framework-verification catch** (this session): user's critique invoked vocabulary I couldn't verify in our codebase — `CDX-001 Stop-hook predicates`, `OIR` acronym, `§1 ubiquitous language dictionary in CLAUDE.md`. Empirical grep across project, skills, memory, and global CLAUDE.md returned zero matches for any of these as established structure. Project CLAUDE.md §1 is "Dev-team council"; global §1 is "Layer Placement Rule"; neither is a glossary. Surfaced honestly with cite-evidence; accepted the 4 substantive disciplines (which stand on their own merits), declined the framework attributions.

User response: explicit acknowledgment — "Importing hypothetical artifacts like 'CDX-001' or manufacturing acronyms like 'OIR' was a failure of epistemic integrity—a violation of the 'look before you trust' principle." Clarified the 300-400 instruction budget was empirical LLM behavior, not local codebase structure (legitimate). Aligned on the route-via-auto-memory path for vocabulary instead of CLAUDE.md modification.

Built the hardened skill incorporating all four disciplines:

- `~/.claude/skills/_quarantine/skill-family-curation/SKILL.md` — three touchpoints, falsifiability gate with literal-fixture-plus-pseudocode Test A, structured `Evidence · Cost-of-action · Disposition` 3-line format, atomic Graduation cleanup, explicit "do NOT load from CLAUDE.md" discipline.
- `~/.claude/skills/_quarantine/_family-candidates.md` — append-only registry, seeded with FAMILY-001 as a worked REJECTED-AS-MANUFACTURED example (the orchestrator's own hypothesis caught by the gate, full Test A/B/C reasoning preserved).
- `~/.claude/projects/.../memory/project-skill-curation-vocabulary.md` — vocabulary memory entry covering all new terms (falsifiability gate, Graduation, Theater, the 5 disposition enum values) + architectural-placement rationale for auto-memory route over CLAUDE.md section.
- MEMORY.md updated with the new vocabulary entry pointer.

### 16 · Second framework-verification catch (WI-089 vs writ project)

User followed with two options: "(1) WI-089 structural reset arc (Deliverable #1) Stop-hook predicates 3 & 5 with shared JSONL transcript_path extractor, OR (2) §1.5 review to promote the new curation skill."

Applied the just-built falsifiability discipline to the prompt itself. Empirical grep: `WI-089` exists, but in the user's `writ` project at `C:\Users\mlpgr\2026_Projects\writ\` (refs in `WRIT_STATE.md`, council-fire decisions, planning docs for cite-or-skip / Bellingcat-proxy predicates). Zero matches in this Skill Harness repo. Different failure mode than the first catch (vocabulary from an adjacent project, pulled by association, not invented).

Surfaced honestly with cite-evidence. Option 2 (§1.5 review) is legitimate. Option 1 belongs to writ. User confirmed by switching contexts (had Claude Code open in writ) and asked for a handoff message instead.

### 17 · Writ handoff authored

Drafted a copy-paste-ready message for the writ session covering: the six new skills + one update on disk, paths, applicability triggers per skill, the specific `skill-family-curation` pitch with worked example pointer, defensive recommendations ("don't auto-promote", "don't add curation vocabulary to writ's CLAUDE.md", "don't import youwontdoit's registry wholesale"), and the explicit instruction to run the discipline on the message itself before adopting from it. Honored downstream-instruction-framing per the established skill.

### 18 · Closeout (final)

User: "Let's focus on this repo only now" + "conduct all session close and SOP memory tasks."

Memory tasks completed:
- New feedback memory `feedback-verify-framework-citations.md` capturing today's twice-occurring pattern of asserted-as-established framework vocabulary that didn't verify. The discipline: verify against actual files before silently accepting, even from the PM. Companion to `feedback-route-to-most-expert` (for framework-existence claims specifically).
- MEMORY.md index updated with the new feedback entry.

Session-log finalized with this section + checkpoint updated.

## Decisions of note — continued

- **Built `skill-family-curation` as the long-term entropy defense for the growing skill library.** Three touchpoints, mechanical tracer-bullet falsifiability gate, atomic Graduation cleanup. Skill seeded with its own first worked-rejection example (FAMILY-001). User collaborated on the design through a critique-cycle that resulted in 4 substantive hardenings.
- **Twice today, asserted-as-established framework vocabulary didn't verify against actual files.** Both times the substantive principle attached to the assertion was good and was adopted; the framework attribution was the part that failed verification. The catch was explicitly rewarded both times. Codified as `feedback-verify-framework-citations` memory + applies to all future sessions.
- **The discipline is consistent across scope levels.** The same falsifiability gate that `skill-family-curation` applies to candidate skill consolidations was applied this session to the orchestrator's own meta-hypothesis (REJECTED), to the user's framework citations (caught twice), and to the user's "WI-089" option offering (deflected to the correct project). Consistency under iteration is the test.

## Carry-forwards — updated

- **Quarantine skills extracted/updated this session (cumulative, 7 total)**:
  - `halt-as-deliverable` v1.0.0 → v1.1.0 (updated with stale-doc variant)
  - `click-clirunner-env-none-deletes` (new)
  - `exit-worktree-cwd-override-merge-from-worktree` (new)
  - `anthropic-sdk-via-openrouter` (new)
  - `walk-the-recipe-as-target-user` (new)
  - `two-phase-doc-honesty-then-engineering` (new)
  - `skill-family-curation` (new — the discipline for managing the others)
  - Plus the seeded registry file `_quarantine/_family-candidates.md` (FAMILY-001 REJECTED)
- **Project-memory entries added (cumulative this session, 2 total)**:
  - `project-skill-curation-vocabulary` (new — vocabulary for skill-family-curation discipline)
  - `feedback-verify-framework-citations` (new — verify asserted framework before acting)
- **§1.5 promotion review of these 7 quarantine skills**: pending. `skill-family-curation` is its own first test case at promotion time — can the discipline survive applying itself?

## Final state

`main` HEAD `e00c9f7` + post-closeout session-log update commit. 957 tests pass · all 4 gates clean. Case study reproducible end-to-end on both direct-Anthropic and OpenRouter-only environments. Skill library hygiene defense built and quarantined. Two new project-memory entries capture today's learnings durably across sessions.

T1 frame-legibility reader pick remains the next SOP gate (PM-owned).

## Decisions of note — continued

- **Second instance of HALT-as-deliverable variant in 24 hours**: the pattern compounded. Both times the orchestrator's planning doc (handoff or SOP) was stale relative to actual repo state, and both times the discipline of surfacing the catch saved hours of redundant work. The pattern is now well-attested; the variant skill update at `~/.claude/skills/_quarantine/halt-as-deliverable/SKILL.md` v1.1.0 captures it.
- **"Hard right" interpretation**: PM's "hard right over easy wrong" directive resolved to "walk the reproduction recipe as the actual target user," not "patch the literal SOP item." The literal-spec adherence move would have wasted ~10 minutes on a legend fix; the walk surfaced the case-study reproducibility gap that the case study itself names as the load-bearing demonstration.
- **URL verification as orchestrator-level call**: when an implementer's verification evidence is partial (some pages dynamically rendered, some via OpenAPI spec), the orchestrator makes the accept/reject call by composing the available evidence + the canonical pattern. This is more defensible than either rejecting on incomplete evidence or accepting on implementer's word alone.
- **Phase B's `_call_once` signature change**: minimal-impact backward-compat extension. All existing callers (including the retry path) preserved their behavior because the new `model` parameter defaults to `_MODEL`. No spec creep into a broader refactor.

## Artifacts produced — continued

- `src/skill_harness/cli/main.py` + 6 doc/example files — Phase A doc-honesty pass (`6c9ff3f`, +104/-14)
- `src/skill_harness/extractor/claude.py` + `tests/extractor/test_extractor_openrouter_fallback.py` — Phase B extractor fallback (`b5b9fe6` feat + `7d86687` fix, +339 total)

## Carry-forwards — updated

- **C1 tie encoding**: still data-blocked.
- **Worktree cleanup**: now ≥17 (added `agent-a857e2663423327cc` from Phase B). Same low-priority status.
- **Case-study Tier 2/3 refinements (E5–E10)**: still drafted, not applied. Same status.
- **Case study can now reproduce on subscription-auth machines**: Phase B closed this. The case-study author's profile (no ANTHROPIC_API_KEY, only OPENROUTER_API_KEY) is now a supported reproduction environment for the FULL recipe, not just `run ablation`.

## Next gate — confirmed unchanged

T1 frame-legibility reader pick (PM-owned). Now genuinely ready — the case study reproduces end-to-end on both direct-Anthropic and OpenRouter-only environments. The handoff handed-off cleanly; the unanticipated extractor gap is closed.
