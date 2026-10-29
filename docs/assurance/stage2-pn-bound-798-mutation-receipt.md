# Mutation receipt: the #798 P - N bound

**Standard:** #341. **Change:** #798, which adds the P - N bound to the Stage 2 simulator of #718 and #720.
**Generator:** `scripts/mutation_receipt.py --select 798-stage2`.
**Machine-readable record:** `docs/assurance/stage2-pn-bound-798-mutation-receipt.json`.
**Pinned by content, not by commit:** `scripts/screens/419/simulate_stage1a_regime_685_stage2.py` at
`sha256:9e0a049d8785fd7ed1e5545e770db1defff37d305d8b45b1d07eb4ec520951dc`.
**Commit at generation:** `fbd9df8d2696900e6171479702127312497fdf2c`. It is informational only.
`tests/test_mutation_receipt.py` checks currency against the digest above.

Each case ran in its own git worktree at a fixed commit. The clean baseline
passed first with a nonzero collection, and the production tree was unchanged.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-S2-21 | 798-stage2-pn-alpha-025 | the P - N interval uses 0.025 per one-sided bound instead of 0.0125 | **KILLED** | `test_pn_interval_uses_0_0125_per_side_not_0_025` |

## What this receipt refuses to claim

It reports no mutation score. One named case cannot support one. It makes no
claim about the operating characteristics of `p_pn_bounded` on the full grid,
which has not been simulated at full replicates.

*Revisit if:* the Stage 2 simulator's bytes move. Regenerate with
`scripts/mutation_receipt.py --select 798-stage2`.
