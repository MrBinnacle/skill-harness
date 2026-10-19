# Step 4. Reveal

Root seed, disclosed after the commitment in `ebmom-peel-confirmatory-run-2026-09-05.md` step 3
landed as commit `6d6835a` on `agent/issue-360` and was pushed:

```
root = f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a
```

Check against the commitment:

```
python -c "import hashlib; print(hashlib.sha256(b'f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a').hexdigest())"
# expected: eb46d0ded40b42b22580f0fe107fa7ab3acf7c500d6ea2845800f13b6d256e97
```

The harness runs ONCE, next, from the worktree at `4bd4633` with the reveal commits on top (they
touch `docs/assurance/` only; the harness and estimator digests in step 1 are unchanged):

```
PYTHONPATH=src PYTHONHASHSEED=0 python scripts/ebmom_acceptance_matrix.py \
  --root-seed f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a \
  --out docs/assurance/ebmom-peel-confirmatory-run-2026-09-05.json
```

Step 5 and step 6 (the run's output, its manifest hash and the verification of the published root
against the commitment) are appended by the commit that lands the JSON.
