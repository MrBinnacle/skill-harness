# Mutation receipt: the Path C discordant route (#368)

**Standard:** #341. **Build:** #368 (Path C), under the estimand ruled 2026-08-31.
**Invariant:** `docs/INVARIANTS.md` §8. **Finding:**
`docs/findings/halfupdate-tie-sensitivity.md` (severity WRONG_NUMBER, filed from
the item 5 detector, #347).
**Generator:** `scripts/mutation_receipt.py --select 368-`.
**Machine-readable record:** `docs/assurance/path-c-tie-encoding-mutation-receipt.json`.
**Pinned by content, not by commit:**
`src/skill_harness/ablation/stopping.py` at `sha256:fc85702bb73904f95aca14910871cbe546f507720ce28a0e41827a97650b3a8a`,
`src/skill_harness/ablation/path_c.py` at `sha256:4af1162c84634ca7daa5454a5fb5859babd8e8071938f197a80d92449199ae20`.
**Commit at generation:** `24c1cdc` — informational only. A rebase rewrites it and
later commits move HEAD past it, so currency is checked against the digests above by
`tests/test_mutation_receipt.py`. **Python:** 3.13.1.

Each case runs in its **own git worktree** at a fixed commit. Production is never
mutated in place. `PYTHONPATH` pins every case to its own sources, because the
editable install would otherwise resolve `skill_harness` to the main repository and
each case would silently test another tree's code. That is not a theoretical
concern here: this migration was built in a worktree, and its first test run
imported the shared clone's sources and reported the old behaviour as if it were
the new one.

Per case the generator records and asserts: the worktree HEAD, the `module.__file__`
actually imported, the clean and mutant source digests, that those digests differ,
that the clean baseline **passes first** with **nonzero collection**, the failing
test node under the mutant, that the mutant **imports** (a stillborn mutant is not
a kill), and that the production tree is byte-unchanged afterwards. All four cases
resolved their module inside their own worktree, and the production digests were
identical before and after.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-T1 | discordant posterior | `_posterior` returns the half-update pair `Beta(1+w, 1+n-w)` again | **KILLED** | `test_halfupdate_tie_sensitivity.py::test_stopping_decision_agreement[win-heavy-few-ties]`, `[win-heavy-many-ties]`, and `::test_production_accumulator_no_longer_dilutes` |
| M-T2 | evidence bar | the N_MIN gate reads `self.n` (total) instead of `self.n_discordant` | **KILLED** | `tests/ablation/test_stopping.py::test_ties_cannot_buy_a_clause_past_the_evidence_bar` |
| M-T3 | effect-size floor | the Gate-2 design is sized by the discordant count, discarding the tie cell | **KILLED** | `test_ablation_path_c.py::test_ties_reach_the_decision_rather_than_being_discarded` and `::test_tie_heavy_win_is_held_below_the_effect_floor` |
| M-T4 | thresholds by reference | a record omitting a threshold is accepted rather than refused | **KILLED** | `test_ablation_path_c.py::test_missing_threshold_refuses_rather_than_defaulting` |

Four hand-chosen mutants. **No mutation score is reported**, because four cases
cannot support one; each case is a named obligation, not a sample.

## What M-T1 measures

It restores the defect exactly. `Beta(1+w, 1+n-w)` with the blended weight is the
superseded encoding, and under it the win-heavy fixtures return to disagreeing with
their drop-ties recompute — which is what the seven strict xfails recorded before
this build removed them. The kill is the direct evidence that those marks came off
because the behaviour changed, and not because the assertions were weakened. The
bounds in that file are unchanged, so a mutant that reintroduces the old arithmetic
has nothing to hide behind.

Note the mutation is written against `_posterior`, the single place the posterior is
formed. That is deliberate: if a later refactor spreads the posterior across two
sites, this mutant stops applying and the generator refuses with `ANCHOR_ABSENT`
rather than reporting a stale kill.

## What M-T2 measures, and why it is a separate obligation from M-T1

M-T1 covers *what the posterior is made of*. M-T2 covers *when the posterior is
allowed to decide*. They are independent, and only the second is about spend.

Pointing N_MIN at the total comparison count looks harmless — the number is still
eight — but it lets three ties stand in for three directional comparisons. The
killing test is the fixture where that matters: 5 wins, 0 losses, 3 ties gives
`Beta(6, 1)` and `P(q > 0.60) = 0.9533`, over the PASS threshold, on five
directional comparisons. Under the mutant the clause passes. Under the shipped rule
the run continues.

## What M-T3 measures, and why Path C is not decoration

This is the case that distinguishes Path C from a plain drop-ties recompute, and it
is the one worth reading if only one is read.

Conditioning on the discordant table is correct and is the ruled estimand, but `q`
alone cannot see how often a direction occurs at all. Sizing the Gate-2 design by
the discordant count throws the tie cell away, and the decision then depends on
`(x_f, x_n)` only — so a clause that won eight of eight discordant comparisons
certifies BENEFIT whether it tied nothing or tied twenty-four. The killing test
holds `(x_f, x_n)` fixed and varies only the tie count, which is precisely the
comparison a drop-ties recompute cannot make.

The second killing test is the tie-heavy fixture from the finding: 7 wins, 1 loss,
30 ties, `Beta(8, 2)`, net lift 0.158 against a registered `delta_min` of 0.20.

## What M-T4 measures

The by-reference requirement is an acceptance criterion of #368, and a criterion
nothing tests is a criterion that decays. Accepting a record that omits `delta_min`
does not crash: the frozen dataclass takes `None` and the decision proceeds under
whatever the downstream comparison does with it. The result renders as a registered
decision and is not one. The refusal is the whole mechanism, so the refusal is what
is mutated.

`tests/test_ablation_path_c.py` also carries a static guard asserting that no
threshold literal appears in `path_c.py`. That guard and this mutant cover the two
directions: the guard catches a threshold written into the code, and the mutant
catches the code declining to notice one missing from the record.

## What this receipt refuses to claim

It does not claim a mutation score, or adequacy of the test suite as a whole. It
does not claim the migration is correct — only that four specific defects are
detected, in isolated worktrees, against baselines that passed first.

It makes **no claim about operating characteristics**. The ablation lane applies the
registered Gate-2 decision rule to a realised, sequentially-stopped table; the error
rates of the registered fixed-N design do not transfer to it, and nothing here was
measured against them. §8 records that limit.

It makes **no empirical claim about the effect of the migration on any real skill**.
No paid measurement was run. Whether any shipped verdict changes is #419's and
#420's question, not this receipt's.

## The generator refuses rather than exiting green

A case whose verdict is `ANCHOR_ABSENT`, `INVALID_BASELINE`, `INVALID_ISOLATION`,
`NO_OP`, `STILLBORN` or `UNKNOWN` measured nothing, so the generator exits non-zero
and names it. `SURVIVED` is deliberately not in that set: a preserved survivor is a
finding, and folding it into an exit code would create pressure to delete it rather
than report it.

*Revisit if:* the ablation lane acquires a fixed-N design, at which point `n_pairs`
should come from the ratification record and M-T3's anchor moves; or `_posterior`
stops being the single site where the posterior is formed, which retires M-T1's
anchor.
