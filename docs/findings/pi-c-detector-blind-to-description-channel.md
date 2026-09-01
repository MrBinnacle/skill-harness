# The invocation detector is blind to the description channel: a mounted skill moved the Full arm with zero recorded invocations

**Measured 2026-09-01.** A paired k=8 run on `git-pull-rebase-trap`, both arms
under one harness pin, returned a Full arm at 6/8 and a Null arm at 0/8 on the
de-leaked prompt. The write-time gate refused the pair with `ZeroInvocationError`:
the v1 invocation detector counted zero Skill tool calls across the eight Full-arm
epochs. The refusal is correct under the contract that #46 bound. The contract does
not cover the channel that produced the effect.

## What ran

| Field (registered Stage-1 template, `docs/findings/v0.2-preregistration.md`) | Value |
| --- | --- |
| Skill | `git-pull-rebase-trap`, `skill_id` `387989fe…` (SHA-256 of `SKILL.md`) |
| Prompt | `prompt_v2_deleaked.txt`, SHA-256 `2289ee87…` (the D4-clean version) |
| Oracle | `command_succeeds` over `oracle/oracle_template.sh`, SHA-256 `9d410193…`; pure git plumbing against planted SHAs |
| Pin | `5324feef…`, identical to the 2026-09-01 screen that justified this run |
| Subject route | `openrouter/anthropic/claude-sonnet-4.5` (see Deviation below) |
| Paired epochs analyzed | 8 (Full 8/8 success, Null 8/8 success) |
| Discordant epochs x | **6**, d̂ = 0.75, Jeffreys 95% interval **[0.408, 0.944]** |
| GO/NO-GO (pre-stated x ≥ 5 at k=8) | **GO** |
| Null pass rate p0 (hardness check) | **0/8** |
| Tokens | Full 1,426,324; Null 1,421,282; cache reads 86% of both |
| Spend | ≈ $2.07 token-computed at the model's list price |
| Evidence store | **not written**: `write_paired_evidence` raised `ZeroInvocationError` before the `runs` row |
| Wall time | 6:37 Full, 6:18 Null, `max_sandboxes=3` |

Logs: `.private/microrun/batch1/gitpull/logs-stage1-paired/` (two `.eval` files,
one per arm). Runner: `.private/microrun/batch1/gitpull/stage1_gitpull_paired.py`.

Receipt: `docs/sers/receipts/gitpull-paired-k8-2026-09-01.json`. It supersedes
`docs/sers/receipts/superseded/reclass-git-pull-rebase-trap.json` (2026-07-20),
whose `p0=1.00` screen row ran on the D4-leaked prompt. The site publishes one
receipt per skill, so the older file moved out of the published directory and
stays in the tree unedited.

The registered template carries no win-direction field, and this table does not
add one. The section below is an instrument finding and needs trajectory facts
that carry direction. That tension is stated rather than hidden.

## What the trajectories show

Every epoch in both arms used the Bash tool only. No epoch in either arm called
the Skill tool. No epoch read `SKILL.md` or any path containing
`git-pull-rebase-trap`.

| Arm | Epochs that ran `git pull --rebase` or `git rebase` | Epochs that merged | Oracle pass |
| --- | --- | --- | --- |
| Null | 8 of 8 | 0 of 8 | 0 of 8 |
| Full | 2 of 8 | 6 of 8 | 6 of 8 |

The two Full epochs that rebased are the two that failed. The mechanism the
card names is the mechanism observed: a rebase rewrites the commits the planted
ledger references, and the oracle's ancestry check fails.

## What the detector measures, and what it cannot

`src/skill_harness/subject/ingest.py` documents the contract:

> v1 detector = branch (a) only: a Skill tool-call whose arguments name the
> skill under test. Branch (b) (a visible SKILL.md file-read) is DEAD CODE under
> the inspect_swe.claude_code solver (the Skill tool loads SKILL.md internally)
> and stays excluded until a non-claude_code solver exists.

Under the `claude_code` solver a mounted skill reaches the model through two
channels. The body of `SKILL.md` reaches it only when the Skill tool fires,
which is branch (a). The frontmatter `description` reaches it on every turn, as
one line in the skill listing inside the system prompt, whether or not the tool
ever fires. Call that channel (c). Branch (a) saw nothing here. Channel (c) is
the only one left that distinguishes the arms, and the arms differ by 6/8.

So the detector's construct, "the skill was invoked", and the ablation's
treatment, "the skill was mounted", are not the same variable. The gate is
written as if a mounted skill with no invocation has delivered nothing. This run
is a counterexample. The `git-pull-rebase-trap` description is one sentence that
names the hazard, and one sentence was enough to change the git command the
model chose in six of eight epochs.

## Consequence

The write-time refusal is a delivery-failure guard, and it fired on a delivery
success. The cost lands on the skill: the collection's first paired run that
cleared the discordance gate has no store row, no admissible verdict, and a
receipt that says CANT_TELL_YET. A reader who trusts the receipt concludes the
card is unmeasured. The trajectories say the card moved the model through its
description alone.

The finding generalises. Any skill whose description already carries its
operative rule will show the same signature: a mounted effect, zero invocations,
a refused pair. Trap-discipline cards are the class most likely to be built that
way, because a trap card exists to name a hazard in one line.

## What this establishes

- A mounted skill changed the Full arm's behaviour with zero Skill tool calls
  and zero file reads of its body. The description channel is real and the v1
  detector does not observe it.
- The paired run cleared the pre-stated GO threshold: x = 6 ≥ 5.
- Every Null epoch fell into the trap. The de-leaked prompt is hard, and the D4
  finding's A/B result reproduces at n = 8.
- The refusal is a property of the detector contract, not a defect in the gate's
  code. The gate did what #46 and #52 specified.

## Refuses to claim

- That `git-pull-rebase-trap` is KEEP. No admissible store row exists, the
  registered micro-run report carries no direction field, and the sized run has
  not run. The receipt says CANT_TELL_YET with `unmeasured_sub_reason`
  `inadmissible`.
- That the subject is the registered one. The registration names the direct
  Anthropic API and excludes OpenRouter; this host has no Anthropic key, so the
  run used the same OpenRouter route as the screen that justified it. The
  registration's stated concern is that router backend heterogeneity inflates
  discordance. Both arms shared the route and the pin, so any inflation is
  common to both, and the 0/8 Null arm leaves no room for it to have helped the
  Null side.
- That the 6/8 Full arm is the skill's ceiling. Two epochs rebased with the
  description present. Whether a fired body would have closed those two is not
  measured.
- That channel (c) can be detected from the transcript. A description-only
  effect leaves no tool call and no file read. Detecting it needs a design
  change, not a regex.

## Deviation from the registration

The registration's launch configuration names the direct Anthropic API with a
pinned model id and excludes OpenRouter. This run used OpenRouter. The reason is
environmental (no Anthropic key at any scope on the host) and the deviation was
declared before launch in the runner's docstring. No threshold, count or
analysis rule was changed. A dated correction block in the registration is owed
if a sized run is to proceed on this route.

## Next action

Ticket on this repository: decide whether pi_c should measure invocation
(branch a, the current contract) or exposure (the treatment the ablation
applies), and if exposure, what a channel (c) detector looks like. Candidate:
record the description's presence in the system prompt as exposure at the
solver seam and keep branch (a) as a separate, narrower field. That decision
sets what the #46 refusal means and is not settled here. Until it is, the pair
stays refused and the receipt stays CANT_TELL_YET.

The sized run on the registered route needs an Anthropic key on the host. That
is the operator's.
