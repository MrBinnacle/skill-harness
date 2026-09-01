# D4: the task prompt leaks the skill's rule into the Null arm

**Measured 2026-09-01.** Four of eight screen fixtures state the skill's own
operative rule inside the task prompt. The Null arm is therefore not unaided,
and its pass rate does not measure what the screen claims to measure. An A/B on
one fixture moves `p0` from **1.000 to 0.000** when the leak is removed and
nothing else changes.

## What a D4 leak is

Prior art already covers three leak directions, audited 2026-07-12 over the
20-task SkillsBench slate (`.private/microrun/stage0/leak-audit.md`,
19 CLEAN / 1 LEAK-D3):

- **D1** — the verifier checks skill-specific artifacts, so the skill arm auto-wins.
- **D2** — the skill text contains the verifier's answer (answer-sheet leak).
- **D3** — the verifier references oracle/solve.sh artifacts.

All three concern **skill vs verifier**. None concerns **prompt vs Null arm**.

**D4** is the fourth direction: the task prompt states, paraphrases, or points
the model at the rule the skill exists to supply. It is invisible from the
outside — the run completes, the oracle passes, nothing crashes — and it
inflates `p0` toward a ceiling, where the verdict logic correctly maps it to
`CANT_TELL_YET`. The result reads as a fact about the skill or the frontier.
It is a fact about the apparatus.

## The A/B that establishes causation

Fixture `git-pull-rebase-trap`. Two Null arms, identical fixture bytes, identical
oracle, identical epochs (3), identical provider. The prompt is the only
manipulated variable.

| arm | prompt | accuracy |
|---|---|---|
| A | `prompt.txt` — signposted | **1.000** (3/3) |
| B | `prompt_v2_deleaked.txt` — signpost removed | **0.000** (0/3) |

The v1 prompt says: *"The repository's release process depends on
`ledger/releases.md` staying valid — see `RELEASING.md` for the repository's
history policy."* The fixture's `RELEASING.md` states the skill's rule: *"Do not
rewrite, drop, or re-parent a commit that the ledger references."* The v1
transcript shows `--rebase` **0** mentions and `merge` **10**. The model was told
not to rewrite history, so it merged.

v2 removes the signpost and changes nothing else. `RELEASING.md` remains in the
fixture and remains discoverable; nothing in the prompt points at it. The
fixture's git config already arms the trap with `pull.rebase = true`.

Arm A reproducing 1.000 on the substituted provider is what rules out a
provider confound: the swap did not move the subject, the prompt did.

## Audit of all eight fixtures

| fixture | skill under test | D4 | leak site |
|---|---|---|---|
| `batch1/gitpull` | `git-pull-rebase-trap` | **LEAK** | one hop, via `RELEASING.md` |
| `batch1/appendonly` | `append-only-evidence-design` | **LEAK** | prompt text |
| `batch1/bayes` | `bayesian-eval-discipline` | **LEAK** | prompt text |
| `batch1/judgegate` | `llm-judge-calibration` | **LEAK** | prompt text |
| `batch1/tiebreak` | `sqlite-tie-break-red-test-trap` | CLEAN | — |
| `batch1/dependabot` | `dependabot-peer-coupled-deps-trap` | CLEAN | — |
| `pilot1/docx` | `docx` (upstream) | CLEAN | — |
| `microrun/` root | `sqlite-expert` | CLEAN | — |

Worked examples of the two leak shapes:

- **`bayes`** is the densest. The prompt hands over the tie-handling menu
  (drop, or half-win plus half-loss), the underpowered-precedence rule, and
  Benjamini-Hochberg at `q = 0.05` by name — three of the skill's own
  disciplines, restated as task requirements.
- **`judgegate`** supplies the position-swap protocol and every numeric
  evidence-admissibility threshold (`agreement >= 0.7`, `position_consistency >= 0.8`,
  `length_controlled_agreement >= 0.65`, `kappa >= 0.4`, `N >= 50`)
  number-for-number.

Separately observed while auditing: the `microrun/` root fixture names
`skill_dir = ~/.claude/skills/sqlite-expert`. A `find -L` sweep over
`~/.claude` located only `~/.claude/skills/_archive/sqlite-expert/SKILL.md`
plus copies under `.claude-backup-*` and `.claude-eval-roots/`; the live path
`~/.claude/skills/sqlite-expert/SKILL.md` returned `exists() == False`. That is
an apparatus-currency issue, not a D4 one.

## Disposition of the affected rows

The store already carries the right category. The inadmissible `tiebreak` row
uses it verbatim: `apparatus_void: oracle exit=1 with mangled runner path ...
grading harness crashed, not the subject`. A D4-leaked run is the same class of
event and belongs in the same category.

| skill | as recorded | correct disposition |
|---|---|---|
| `git-pull-rebase-trap` | `CANT_TELL_YET`, admissible | INADMISSIBLE — `apparatus_void: D4 prompt leak` |
| `append-only-evidence-design` | `CANT_TELL_YET`, admissible | INADMISSIBLE — `apparatus_void: D4 prompt leak` |
| `bayesian-eval-discipline` | `CANT_TELL_YET`, admissible | INADMISSIBLE — `apparatus_void: D4 prompt leak` |
| `sqlite-tie-break-red-test-trap` | `CANT_TELL_YET`, admissible | stands on D4; see the stale-pin ground below |

This distinction is load-bearing for a reader, not bookkeeping.
`CANT_TELL_YET` beside a skill that demonstrably works reads as doubt cast on
the skill. `apparatus_void` reads as the system discarding its own bad reading.
The first damages a public claim; the second is the behaviour the programme
exists to demonstrate.

## Second, independent ground: instrument drift

All four backfilled rows carry `harness_pin_fingerprint =
2f76c933b4f93d6fe407c8d657489d7bed6e16b2d41f763744578a63d26e6d65`, captured
2026-07-10. The same `HarnessPin.capture(...)` arguments today produce
`706cbaea30f8750b928bf7617c2ed919002bfbf01b9d349243475c1346cffa1b`. Since
2026-07-21, `git log --oneline --since=2026-07-21` reports 11 commits to
`src/skill_harness/subject/` and 35 to `src/skill_harness/oc/` plus
`src/skill_harness/aggregation/`.

`screen verdict` derived `p0` from those rows without comparing the stored
fingerprint to the running instrument. Basis for that claim, and its limits:
`grep -rn "harness_pin_fingerprint" src/skill_harness --include=*.py` returns 21
sites, all of which write, declare, validate or read the field
(`aggregation/binding.py`, `storage/models.py`,
`storage/repositories/evidence/samples.py` and `.../screens.py`,
`subject/ingest.py`); none of the returned lines compares a stored value against
a freshly captured pin. This is a grep over `src/` only — it does not establish
that no such check exists anywhere in the repository, and it was not run against
`tests/`.

Surfaced by running `screen backfill --execute` on 2026-09-01, which loaded
July-instrument rows into the current store and produced verdicts from them with
no staleness signal.

That ground voids all four rows, including `tiebreak`, whose prompt is clean.

## What this does NOT establish

The `git-pull-rebase-trap` skill arm scored **1.000 (3/3)** against the
de-leaked Null arm's **0.000 (0/3)**. That is a difference of proportions across
two independent arms at n=3. It is **not** a verdict of record:

- it is not paired, so it yields no discordant table, and the estimand of
  record is the discordant table (`INVARIANTS.md` §8);
- it carries no registered estimand — the profile labels it
  `n/a (pre-registry observation)`;
- the provider is `openrouter/anthropic/claude-sonnet-4.5`, not the pinned
  direct-Anthropic subject. Both arms share it, so the comparison is internally
  valid and externally unpinned;
- n = 3 per arm. With perfect separation that is Fisher one-sided p ~ 0.05.

What it does establish is that the pre-registered gate is cleared: `p0 < 1`, so
the paired k=8 run is justified for the first time on this card.

## Next actions

1. Make D4 an **evidence-admissibility check at ingest**, so a leaked prompt is rejected
   rather than scored.
2. Wire a **pin-currency check** into `screen verdict`, so rows whose
   `harness_pin_fingerprint` differs from the running instrument cannot silently
   produce today's `p0`.
3. Re-disposition the four rows above as `apparatus_void` or stale-pin.
4. De-leak the `appendonly`, `bayes` and `judgegate` prompts, then re-screen.
5. Run paired k=8 on `git-pull-rebase-trap` under the registered estimand.

## Artifacts

- `.private/microrun/batch1/gitpull/prompt_v2_deleaked.txt` — the de-leaked prompt
- `.private/microrun/batch1/gitpull/stage0_gitpull_ab.py` — the two-arm Null A/B
- `.private/microrun/batch1/gitpull/stage0_gitpull_full.py` — the skill arm
- `.private/microrun/batch1/gitpull/logs-stage0-ab/` — the three eval logs
- `evidence.db.bak-preS387` — store state prior to the 2026-09-01 backfill
