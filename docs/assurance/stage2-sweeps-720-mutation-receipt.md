# Mutation receipt: the #720 Stage 2 sweep extension

**Standard:** #341. **Change:** #720, which extends the Stage 2 sweep of #718.
**Generator:** `scripts/mutation_receipt.py --select 720-stage2`.
**Machine-readable record:** `docs/assurance/stage2-sweeps-720-mutation-receipt.json`.
**Pinned by content, not by commit:** `scripts/screens/419/simulate_stage1a_regime_685_stage2.py` at
`sha256:b3f01a9567e391b6843a5359185dbc9ea408b518cb2b32aa7fe1927aeb09ca09`.
**Commit at generation:** `248f3f3e97fbe293c0e4ad3615c6ade45683c307`. It is
informational only. `tests/test_mutation_receipt.py` checks currency against
the digest above.

Each case ran in its own git worktree at a fixed commit. The clean baseline
passed first with a nonzero collection, and the production tree was unchanged.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-S2-17 | 720-stage2-betting-cut-level-010 | the fixed-n-betting CUT test runs at 0.10 instead of 0.05 (X1) | **KILLED** | `test_fixed_n_betting_cut_is_decided_at_the_registered_0_05` |
| M-S2-18 | 720-stage2-tuned-cut-level-010 | the anytime-tuned CUT test runs at 0.10 instead of 0.05 (X2) | **KILLED** | `test_anytime_tuned_cut_is_decided_at_the_registered_0_05` |
| M-S2-19 | 720-stage2-tuned-joint-pass-fp-half | an anytime-tuned row reports its F - P half as the joint PASS (X4) | **KILLED** | `test_anytime_tuned_joint_pass_is_not_the_fp_half` |
| M-S2-20 | 720-stage2-fn-null-count-pairs | the fixed-n-score F - N test is given pairs with a Null draw, not Null draws | **KILLED** | `test_fixed_n_score_fn_test_counts_null_draws_not_pairs`, `test_fixed_n_score_fn_pass_at_the_margin_does_not_collapse_at_null_per_pair_2` |

X1, X2 and X4 each left every test passing at #718's head before this change,
per the independent check of #718. Each is now killed by a test written for it.

## What this receipt refuses to claim

It reports no mutation score. Four named cases cannot support one. It makes no
claim about the operating characteristics of the extended grid, which has not
been simulated at full replicates.

*Revisit if:* the Stage 2 simulator's bytes move. Regenerate with
`scripts/mutation_receipt.py --select 720-stage2`.
