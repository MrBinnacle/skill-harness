# Mutation receipt: starting wealth in the #685 engine (#868)

**Standard:** #341. **Repair:** #868. **Generator:** `scripts/mutation_receipt.py --select 868-`.
**Machine-readable record:** `docs/assurance/stage2-starting-wealth-868-mutation-receipt.json`.
**Pinned by content, not by commit:**
`scripts/screens/419/simulate_stage1a_regime_685.py` at
`sha256:ddf29746026bcd6bde8435fd0f0cc12aa1e6942b5ed65235f39f033313e62429` and
`scripts/screens/419/simulate_stage1a_regime_685_stage2.py` at
`sha256:9e0a049d8785fd7ed1e5545e770db1defff37d305d8b45b1d07eb4ec520951dc`.

Each case runs in its own git worktree at a fixed commit. Every clean baseline passed first
with nonzero collection, and the production digests were identical before and after.

## Results

| mutant | obligation | mutation | verdict |
|---|---|---|---|
| M-868-1 | 868-engine-grid-ignores-wealth | online F-P PASS grid starts at wealth 1 | **KILLED** |
| M-868-2 | 868-engine-exact-ignores-wealth | exact-bound fallback starts at wealth 1 | **KILLED** |
| M-868-3 | 868-engine-terminal-ignores-wealth | direct F-N terminal bound starts at wealth 1 | **KILLED** |
| M-868-4 | 868-anytime-ignores-wealth | Stage 2 anytime path drops the row's wealth | **KILLED** |
| M-868-5 | 868-tuned-cut-bypasses-rule | anytime-tuned CUT reads W0, not the CUT rule | **KILLED** |
| M-868-6 | 868-anytime-sweep-dropped | STAGE2_SWEEP keeps anytime rows at 1.0 | **KILLED** |
| M-868-7 | 868-header-prints-constants | header prints module constants, not the sweep | **KILLED** |

The killing tests for each case are recorded in the JSON.

## What this receipt refuses to claim

It does not claim a mutation score or adequacy of either suite. It does not claim any
operating characteristic of the new anytime rows; the full grid has not been run. It does
not claim the CUT rule's value is decided: it pins that both anytime paths read one rule.

*Revisit if:* the #868 deliverable changes. Regenerate with
`scripts/mutation_receipt.py --select 868-`.
