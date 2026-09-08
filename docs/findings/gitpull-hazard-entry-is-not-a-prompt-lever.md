# Hazard entry on the gitpull task is not purchasable at the prompt layer

**Date:** 2026-09-08. **Ticket:** `#419`, item 2 only. **Prior records:**
`docs/findings/d4-prompt-leak-into-null-arm.md`, `RAT-0001` Amendment 2 (`#418`), the `#403`
ruling, and the drafting pass at `.private/microrun/batch1/gitpull/task-v3-candidates-S414.md`
(gitignored; local only).

## Finding first

`#419` item 2 asks for a task version under which a stock agent actually runs the hazard action,
so that the untreated arm meets the trap the card describes. The drafting pass produced three
candidates. Read against the two criteria the item actually imposes, **the criteria are not
jointly satisfiable at the prompt layer.**

Every prompt-level route to hazard entry works by naming the action. The card's description
begins ``Use before `git pull` ``, so a prompt containing that token hands the treated arm the
card's own retrieval cue. Buying hazard entry in the prompt therefore does not remove
contamination; it **moves it from the untreated arm to the treated arm**, where the shipped D4
check does not look and where it inflates the measured effect rather than suppressing it.

One candidate escapes this, and only by declining to buy hazard entry in the prompt at all.
**v3a moves the lever out of the prompt and into the environment**: it asks for a push, the stale
tracking ref makes the push reject, and git's own rejection text names the hazard action. Both
arms stay clean. Nothing is guaranteed.

**v3a is what ships**, as `.private/microrun/batch1/gitpull/prompt_v3a_pushdiv.txt`
(sha256 `6fa18e5b9950e6f5e416554e3e7ac440d1a438a1d19e41818a59ff430c86cc94`, 316 bytes, LF).
Whether it forces the pull is **unmeasured**, and two facts measured for this record point
against it. That question belongs to item 3's qualification screen, which is spend and is not
authorised.

## 1. The two criteria, and why they pull against each other

Item 2 imposes two requirements at once:

- **(A) Hazard entry.** The untreated arm must actually run the trap-form pull, rather than
  satisfying the task with `fetch` + `merge`. Without this the lattice is zero-discordant for an
  uninformative reason, which is what the sized run measured: 32 of 32 untreated epochs merged,
  none pulled.
- **(B) No strategy leak.** The prompt must not supply the rule the card exists to supply. This
  is the D4 discipline, and `prompt_v2_deleaked.txt` carries "deleaked" in its name because the
  v1 prompt failed it — one hop, via `RELEASING.md`.

The repository's own recorded position is that these are compatible: `RAT-0001` Amendment 2 says
"naming the action is not leaking the rule; the rule is 'check `pull.rebase` first'", and `#403`
section 8 endorses manufactured encounters as the way to place an agent in front of a hazard.
**That position is correct about D4 and incomplete about the estimand.**

Naming the action does not tell the untreated arm the rule. It does something else. The card's
front matter reads:

> `description: Use before` `git pull` `where` `pull.rebase` `may be` `true` `...`

The trigger phrase *is* the hazard action. A prompt that names the action to raise entry in the
untreated arm simultaneously hands the treated arm its retrieval cue. The treated arm then
retrieves the card because the prompt quoted its trigger, not because the model recognised the
situation — and recognising the situation unaided is a large part of what the card must do in
deployment. The result is a measurement of "does this card help when its trigger is handed to
the model", which is narrower than the registered estimand and biased toward the card.

This is not a D4 leak, and the shipped `check_d4_prompt_leak` cannot see it: that check reads the
prompt and the fixture files a prompt names, searching for the operative rule. It does not model
treatment-side retrieval. So the failure mode is invisible to the instrument that exists to catch
prompt contamination, which is the reason it is written down here.

## 2. The three candidates against both criteria

| candidate | lever | (A) entry | (B) leak | trigger token in prompt | fixture |
|---|---|---|---|---|---|
| **v3a** push-divergence | environment (push rejection) | weak, unmeasured | clean | absent | unchanged |
| **v3c** teammate's note | prompt ("Pull it in") | moderate | clean under D4 | **present**, quoted speech | unchanged |
| **v3b** runbook | prompt + `CONTRIBUTING.md` | strongest | clean under D4 | **present**, twice | rebuilt |

v3b and v3c are both clean under D4 by reading, and the drafting pass is right about that. They
are not clean on trigger salience, and v3b is worst: the token appears in the prompt and again in
a file the prompt points at. v3b additionally rebuilds the fixture, which regenerates every SHA,
requires oracle re-validation, and re-prices the task under `#420` section 4 — breaking the
sequence in which `#420` re-measures the basis on the repaired task.

v3a is the only candidate whose treated-arm exposure is comparable with the v2 runs, because its
prompt never says the word.

## 3. The trade accepted

**Chosen: v3a, verbatim as drafted, with no edit.**

The trade, stated plainly: **v3a buys measurement validity and buys no hazard entry.** It keeps
both arms uncontaminated and accepts that the untreated arm may simply not enter the trap, in
which case the screen fails the candidate and item 2 is still open. v3c and v3b buy hazard entry
and pay for it in treated-arm exposure that no shipped check will report.

That trade is the right way round for this programme. A screen that returns `h0 = 0` on v3a
costs under five dollars and tells the truth. A paired run on v3c returns a number that looks
like lift and cannot be separated from the prompt having quoted the card's trigger.

Two edits were considered against v3a and rejected:

- **A force-push prohibition.** v3a does not disclose that the remote has moved, so an agent may
  satisfy "publish my commits" with `git push --force`, destroying R and failing oracle check 3.
  That is an oracle failure that is not a trap entry. A clause forbidding `--force` would remove
  it, but it also signals that the remote holds something worth destroying, which restores the
  divergence disclosure that drove the sized run's fetch-and-inspect behaviour. Rejected: the
  drafting pass already instruments this per epoch (record whether the agent force-pushed; the
  completion oracle fails, the invariant oracle holds), so the mode is visible rather than
  confounding.
- **Neutralising the commit-message signpost.** The fixture's messages
  `base: scaffold + release policy` and `C: record shipped commits in release ledger` appear on
  the agent's first `git log`, and 26 of 32 sized untreated epochs read the rule-carrying
  `RELEASING.md` before integrating. Rewriting them is a fixture rebuild with v3b's consequences.
  Rejected as out of item 2's scope; carried below as a known non-guarantee and a fork for
  whoever runs `#420`.

## 4. Verified for this record, at zero cost

Four checks were run. No model was invoked and no money was spent.

**1. The pinned image's git names the hazard action — and the drafting pass quoted the wrong
version's wording.** v3a rests entirely on git's rejection text, so the text was read from the
digest-pinned sandbox image
(`aisiuk/inspect-tool-support@sha256:fb045da8203aea656785c758f7147b003cfe21f213e9048a38be0a33242a5b3d`,
**git 2.39.5**), reproducing the fixture's shape — bare remote, a second clone pushing ahead, a
stale tracking ref, `pull.rebase=true`, then a push with no fetch:

```
 ! [rejected]        main -> main (fetch first)
error: failed to push some refs to '/root/origin.git'
hint: Updates were rejected because the remote contains work that you do
hint: not have locally. This is usually caused by another repository pushing
hint: to the same ref. You may want to first integrate the remote changes
hint: (e.g., 'git pull ...') before pushing again.
```

The candidates file quotes a different sentence — *"If you want to integrate the remote changes,
use 'git pull' before pushing again."* That is the wording of a **modern** git; it was reproduced
on the host's git 2.55.0 during this check, and it is not what the sandbox emits. The correction
matters in the direction that hurts v3a: **the pinned image's suggestion is hedged** ("You may
want to", "e.g.", an elided argument list) where the modern one is imperative and copyable. The
recorded witness string for the screen is the 2.39.5 text above.

**2. The environment names both actions, and the competing one wins today.** The rejection line
itself reads `(fetch first)`. So the untreated agent is handed `fetch` as a bare instruction and
the hazard action as a hedged parenthetical — and the sized run established that this subject
already prefers fetch, 32 times out of 32. This is the strongest evidence available that v3a's
`h0` may come back at or near zero, and it was not available to the drafting pass.

**3. D4 receipt on the new prompt.** `check_d4_prompt_leak` was run against v2 and v3a for three
candidate rule strings — the `RELEASING.md` rule, the card's operative rule, and the card's
"Check config first". **v3a is clean prompt-only on all three, identically to v2.** Both prompts
report a one-hop hit when `RELEASING.md` is supplied as a named fixture file; neither prompt names
it, so that condition does not arise at ingest. It is recorded because it is the same
signpost-moved-not-removed fact as item 5 below, seen through the instrument.

**4. The card's trigger has not been rewritten, so `#419`'s Revisit-if has not fired.** The card
was renamed `git-pull-rebase-trap` → `pull-rebase` in the collection. Its `description` is
unchanged and still begins ``Use before `git pull` ``. The rename does not change what entering
the trap means; the trigger-salience argument in section 1 stands on the current card.

## 5. What v3a does NOT guarantee

Stated so that a green screen is not read as more than it is, and a failed one is not read as a
surprise.

1. **It does not guarantee the agent pulls.** This is the whole open question. v3a offers an
   affordance, not a compulsion, and check 2 above shows the competing affordance is stated more
   plainly than the hazard one. A careful agent fetches after a rejection exactly as it fetched
   after being told about divergence.
2. **It does not neutralise the two-hop signpost.** The commit messages still carry "release
   policy" and "release ledger" onto the agent's first `git log`, and `RELEASING.md` remains
   discoverable. That path depresses hazard entry and is invisible to the D4 check, which reads
   prompts and manifest-named files, not commit messages.
3. **It does not remove the force-push failure mode.** See section 3. The oracle catches it, but
   as a completion failure rather than as a trap entry, so it must be read per epoch and not
   folded into the hazard count.
4. **It does not make the hazard count correct on its own.** The registered pattern still has to
   exclude explicit-strategy pulls; `git\s+pull` counts `--rebase` as an entry. That is `#438`,
   which is not this work and which `#419`'s own sequencing puts first.
5. **It changes the prompt, so it is not free of `#420`'s question.** The fixture bytes and SHAs
   are untouched and the oracle is unchanged, which is why v3a was preferred, but the prompt is
   shorter than v2's and the per-pair token basis is therefore not identical to the measured
   539,011.
6. **Nothing here is a measurement of the card.** No run was performed. This document selects a
   fixture; it makes no claim about the card's disposition.

## 6. What remains

Item 2's deliverable exists. Whether it works does not, and cannot be settled without spend.

1. `#438` registers the hazard-excluding pattern. `#419`'s own comment puts it first, because the
   screen's read-out depends on it.
2. Oracle re-validation on v3a through `validate_oracle.py`. The fixture and oracle are unchanged,
   so this is a confirmation at zero cost, and its output should be kept — no record of that
   matrix running lives in the fixture directory today.
3. The small-k untreated screen on the priced subject. Pre-stated read-out, unchanged from the
   drafting pass: at k = 8, 4 of 8 or more qualifies at the registered frontier; 3 of 8 forces a
   lower H1 point and a frontier re-run; **0 of 8 fails the candidate**, and on the evidence in
   section 4 that outcome is live. This is spend and needs its own dated authorisation.
4. **If v3a fails the screen, the next lever is the fixture, not the prompt.** That is this
   document's finding restated as a direction: strengthen the environment's push toward the
   hazard, or remove the fixture's pull away from it — neutralising the commit messages is the
   cheapest such move — rather than reaching for v3c, which buys entry with treated-arm exposure.

## Artifacts

- `.private/microrun/batch1/gitpull/prompt_v3a_pushdiv.txt` — the task version that ships
  (sha256 `6fa18e5b9950e6f5e416554e3e7ac440d1a438a1d19e41818a59ff430c86cc94`)
- `.private/microrun/batch1/gitpull/prompt_v2_deleaked.txt` — superseded for this task family
  (sha256 `2289ee87959b603b5a249430efbe80f998e16831b75772ebc99c5d725c80338c`)
- `.private/microrun/batch1/gitpull/task-v3-candidates-S414.md` — the drafting pass, unmodified
- `docs/findings/d4-prompt-leak-into-null-arm.md` — the leak discipline this selection is checked
  against
