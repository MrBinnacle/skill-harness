# Step 4. Reveal

Root seed, disclosed after the commitment in `ebmom-peel-confirmatory-run-v2-2026-09-13.md` step 3
landed as commit `122185f` on `agent/issue-360` and was pushed:

```text
root = d77c7cd1f9daab006397b20330988074bc24b34c98ffa2827eebfc7195f7500f
```

Check against the commitment. Both encodings, because step 3 recorded both:

```text
python -c "import hashlib; print(hashlib.sha256(b'd77c7cd1f9daab006397b20330988074bc24b34c98ffa2827eebfc7195f7500f').hexdigest())"
# expected: 5a37629960f9d90bb7eed52dab47ee34f7a74ac6de8916ad2995b362125dc0da

python -c "import hashlib; print(hashlib.sha256(bytes.fromhex('d77c7cd1f9daab006397b20330988074bc24b34c98ffa2827eebfc7195f7500f')).hexdigest())"
# expected: 4ac62ed4782b9d9d0e3ed28c65c40b3e8b00e1989bb6e9eb66b81c00ce4ad29f
```

Both were recomputed at reveal time and both matched. The root is 64 characters.

The harness runs ONCE, next, from the worktree at `681824d` with the reveal commits on top. Those
commits touch `docs/assurance/` only, so the harness and estimator digests recorded in step 1 are
unchanged:

```text
PYTHONPATH=src PYTHONHASHSEED=0 python scripts/ebmom_acceptance_matrix.py \
  --root-seed d77c7cd1f9daab006397b20330988074bc24b34c98ffa2827eebfc7195f7500f \
  --out docs/assurance/ebmom-peel-confirmatory-run-v2-2026-09-13.json
```

No `--replicates`, `--regime` or `--world-range` argument is passed. The harness's defaults are
`R_REPLICATES = 1000` and every registered regime, and it computes `complete` from exactly those
two conditions. v2 section 5 states that a run reporting a subset is not a confirmatory run, so the
arguments are omitted rather than restated, and the harness decides completeness for itself.

Step 5 and step 6, the run's output, its manifest hash, and the verification of the published root
against the commitment, are appended by the commit that lands the JSON.
