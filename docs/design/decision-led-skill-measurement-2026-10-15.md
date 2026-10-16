# Measure the author's decision, not a task chosen to produce KEEP

**2026-10-15 · Recommendation and local apparatus repair, not a preregistration.**
Sources: skill-harness `49a77f6`; the owner's private research repository at `3d1b77d`.

## Decision

**What changes when I add this skill to the setup where I intend to use it, and what does
it cost?** The author decides whether to ship, revise, restrict use or leave benefit unresolved.
[ADR 0002](../adr/0002-reader-facing-record-cost-grade-scoped-verdict.md) reconciles the earlier
cost-only destination with [PRODUCT.md](../../PRODUCT.md): publish cost, evidence grade and a
scoped verdict together; the reader decides deployment. A research milestone of one KEEP or
CUT does not supersede the product's acceptance of `CANT_TELL_YET`.

## Evidence and corrections to the framing

- [v3a screens](../findings/gitpull-v3a-null-qualification-screen.md): both tested subjects
  completed 8/8 with zero hazard entries after the required hand-read. This is subject/fixture
  evidence, not a comparative CUT or proof about every subject. If intended users normally
  have the repository policy, keep it in both arms. Removing it defines a policy-absent
  population; it does not automatically repair an invalid experiment.
- [Displaced enforcement](../case-studies/displaced-enforcement-skill-ablation-blind-spot.md):
  text ablation cannot measure a hook absent from both arms. Standalone text effect is still
  a legitimate narrower question, not evidence for the whole deployed discipline.
- [Stage 1A](../findings/stage1a-readout-691.md): Full 50/97, Placebo 34/97, Null 34/97 remains
  unresolved. Equal Placebo/Null counts do not establish placebo inertness. Manifest-read
  splits describe post-assignment behavior; they do not identify its causal effect.
- Research `docs/research/framework.md`, Gate 2: cost decomposes where benefit may not.
  Clause-by-clause testing does not automatically escape the whole-skill ceiling. Conversely,
  its “strongest trim signal” language for three successful Null trials overstates what those
  trials establish: they are not a comparative estimate.
- Research `stage1a-next-design-adjudication-S493.md` and
  `stage2-design-adjudication-S508.md`: more N is not the only lever; joint conditions,
  assumed rates and evidence history matter. No post-result switch of test or reset of
  prior evidence is licensed here. Statistical and retest-accounting choices remain reserved.

The research files are under `docs/research/` in the owner's private research repository.
Frozen source records are unchanged; the corrections above are forward interpretations, not
rewritten history.

## Recommended design

Use the existing scope, arms and outcome fields with a short prospective decision brief:

| Fix before confirmation | Evidence required and allowed inference |
|---|---|
| Deployment population: model, runtime, skill version, policies, workflow | Tasks justified by intended use, not selected only for eliciting failures. Distinguish ordinary workload, a named hazard-prone stratum and instrument validation; do not silently generalize or pool them |
| Intervention: baseline plus available skill versus the same baseline without it | Total availability effect, including the listing description. Keep assigned observations when the body was not invoked. To estimate a guard's contribution, vary that guard in a separate approved design |
| Outcomes and costs | Task completion and, where relevant, invariant violations and failures introduced. Avoid crediting refusal to work as successful protection. Report standing/fired/auxiliary cost separately, with its evidence basis |
| Smallest necessary comparison | Full versus Null answers total availability effect. Placebo serves an additional attribution question and needs justification. Do not remove it from Stage 1A's existing registered joint rule |
| Qualification and feasibility | For hazard-dependent designs, examine exact subject/task traces and detector controls. Oracle pass rate is not hazard entry; a small pilot's observed rate is not a guaranteed future rate. Other claims need not have hazard floors |
| Analysis, cost and unresolved branch | Separate exploration from confirmation; freeze tasks, outcomes, analysis and search/retest accounting before confirmation. Use existing operating characteristics on both benefit and no-useful-lift alternatives, showing expected spend and cap. Keep current thresholds; if evidence is unavailable or unaffordable, stop with the scoped refusal |

For pull-rebase on Pi the choice was **ordinary guarded deployment, isolated text, or the
guard itself**. The owner delegated it on 2026-10-15. Selected: **isolated text, in the
stratum where the repository states no history policy.** Three reasons. The skill text is
the artifact the author ships and revises. The current adapter isolates exactly that, with
`--no-context-files --no-extensions`. And both v3a subjects showed that a repository which
states the policy makes the card redundant in that environment, so a policy-present task
cannot show what the text adds. This result is scoped to that stratum, and the scope line must
say so. It does not measure the guarded setup or the guard. Those two stay deferred until an
approved design needs them.

Before any spend, three things are still needed. First, a task family whose policy-absent
repositories are justified by real use, not chosen because they make the hazard fire.
Second, an oracle that does not credit a refusal to push as protection. Third, a ratified
analysis and cost record. Spend, caps and thresholds remain the operator's call. An author
may deploy under uncertainty without relabeling that decision measured benefit.

## Critique and selected remedy

A fresh-context, read-only GPT Astra reviewer read product intent and both ADRs before
PR #475's proposal, then the primary records and current execution code. Runtime status records
medium effort; high was requested but was not the effective setting. It challenged
universal hazard qualification, selection for detectability, and duplication of existing
semantics. Those objections are accepted. This was independent context, not a cross-family
panel or PR #475's required T1 landing review.

**Do not build new scientific infrastructure yet.** A qualification receipt can establish
recorded identities and counts, not workload relevance, oracle adequacy or identifiability.
PR #475's universal preflight proposal is therefore not the implementation specification.
[ADR 0001](../adr/0001-architecture-admitted-on-demonstrated-decision-requirement.md) requires a
demonstrated decision before adding structures. A universal activation contract, new receipt
store or validation-token registry has not met that requirement. Simply enlarging Stage 1A
would not address intervention fit and would require reserved policy choices anyway.

**Fix the demonstrated execution mismatch.** `run_paired_evaluation` formerly accepted any
supplied `PreSpendValidation` and skipped validation of its actual spec. Execution now reruns
the existing parser/runtime/roster checks before workspace materialization or the first epoch.
The keyword that let a caller pass an earlier result is removed. The Pi CLI report names
the contrast and disclaims scientific qualification and spend authorization. This
preserves the identity needed to interpret the comparison;
it is not a new scientific gate. Exposure-without-invocation remains admissible.

Limits: no atomic filesystem/runtime snapshot, no new binding of task contents or every mutable
dependency to a registration, and no protection against changes after this check. Low-level
`run_epoch` callers and historical Inspect scripts are not newly guarded. The legacy RAT path
still prints prior screens. Workload relevance, oracle validity, placebo inertness, mediation,
transportability and the acceptable evidence price still require scientific or operator judgment.

## Verification and authority

Acceptance pass, same date. `run_paired_evaluation` no longer takes a `validated` argument.
The argument had been kept but ignored, which kept a dead parameter in the public API. No
caller in this or the sibling repositories passes it, and `runner.py` has shipped in no tag
(added in `9dc7a4e`, after v0.3.0). The direct cached-validation tests went with it.
`test_cli_rechecks_the_runtime_at_execution` stays: it changes the runtime after the dry-run
report and asserts refusal with zero epochs, oracle calls, runs and samples. Against the
`49a77f6` source it fails: the pair is written. The existing roster and container tests
cover the spec-side refusals.

The full non-live suite ran on the CI partition (`-n 4`, `-m "not live and not calibration
and not assurance"`, random ordering off). Before the edits in this pass: 619 s, 3906 passed,
16 skipped, 2 xfailed, 2 failed. On the final tree: 597 s, 3902 passed, 16 skipped,
2 xfailed, 1 failed. The difference of five is the five removed test cases. The failures:

- `test_receipt_still_describes_the_files_it_measured[pi-driver-wiring...]`: the committed
  mutation receipt hashes `runner.py`, so any edit makes it stale. The generator refuses a
  dirty tree. In a scratch commit of this diff, `mutation_receipt.py --select mr-` killed
  M-R4, M-R5, M-R6 and M-R7. The scratch worktree is removed. Regenerate
  `docs/assurance/pi-driver-wiring-mutation-receipt.json` after the commit; until then this
  test fails, as it should.
- `test_v5_cue_stage1a.py::test_dry_run_prints_both_tables_and_calls_no_model` also fails at
  clean `49a77f6`, so this diff did not cause it. `a1dd143` (#662) moved task construction
  below the dry-run return on purpose, so a dry run no longer prints the task names or the
  launch header. The test still asserted both. It is skipped wherever the private fixture
  is absent, which includes CI, so the drift went unseen. The two stale assertions are
  removed. The table, alpha, cap and no-model-call assertions remain. The dry run prints
  tables at both fixed alphas and ignores `--pass-alpha`; that is #662's design and is not
  changed here.

Pi runner, Pi adapter, Stage 1A tests, Ruff and strict mypy pass after these edits. The
synthetic-capture tests establish apparatus behaviour, not a skill effect.

The operator explicitly allowed local implementation despite the #709/#611 hold. PR #475
was still open at `811300a`, with no reviews. Its normal review/landing/re-scoping prerequisites
remain unsatisfied. The owner approved committing this change locally.
No publication, paid experiments, schema, product policy, statistical thresholds or budgets
changed. Other repositories' existing work is preserved.

**Next:** draft the policy-absent task family and its oracle at zero spend, then bring the
analysis and cost record to the operator for ratification.
The operator owns policy, budgets, statistical amendments and paid-run permission. Revisit
new infrastructure only when an approved concrete design demonstrates an unmet measurement
need. Regenerate the Pi driver mutation receipt after the commit.
