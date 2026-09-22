# #592: asset-pairs freshness check

## What this PR adds

A new drift-check row, DC-19, that refuses when any source-export hash pair in
`assets/asset-pairs.json` drifts. The manifest records the sha256 of both
halves of each pair; either half changing without the other is refused, naming
both file paths and both hashes in the failure.

The shape is copied from `MrBinnacle/skills` `scripts/validate_brand_kit.py`
check 2 (`asset_pairs`), adapted to this repository's drift-check house
pattern: a `LiveRow` in the contract table, a JSON manifest for the recorded
hashes, and synthetic-tree tests that prove the check's red lane and green lane.

## Acceptance criteria

### Criterion 1: a check refuses when `social-preview.svg` changes and `social-preview.png` does not

**What was built.** DC-19 reads `assets/asset-pairs.json`, computes sha256 of
each file named in each pair, and compares against the recorded hashes. When the
SVG source changes its hash no longer matches `source_sha256`, the check refuses
and names both file paths and each path's recorded and actual hash.

**The test that pins it.**
`tests/test_drift_check.py::test_dc19_source_changed_without_export_reddens_dc19`
writes a synthetic tree, mutates the SVG source while leaving the PNG unchanged,
and asserts DC-19 reddens with exit code 1.

**What was observed.** The test fails for the right reason:

```
  FAIL     DC-19  asset pairs: every source-export pair in assets/asset-pairs.json
           matches its recorded sha256 — a stale export or an edited source
           without re-export is refused (#592)
           FAIL DC-19: asset pair 1 has a mismatched source: source
           assets/social-preview.svg: recorded hash 227ace003abf0d07..., file
           on disk c2ac962a0f8ca95e...; export assets/social-preview.png:
           recorded hash 9f94e92886fb4a44..., file on disk
           9f94e92886fb4a44... — one half of a pair was changed without the
           other, or without re-recording both
```

**After the change.** The same test passes (green) when the manifest is
re-recorded with both hashes updated, tested by
`test_dc19_both_changed_together_is_green`.

### Criterion 2: covers `banner-dark.svg`, `banner-light.svg` and `favicon.svg` on the same rule

**What was built.** The check is data-driven: `assets/asset-pairs.json` holds a
`pairs` array. Adding a new pair is a one-line JSON edit, not a code change.
The manifest structure is identical to the sibling repo's `asset_pairs.pairs`
block. Today there is one pair (`social-preview.svg` / `social-preview.png`).
When the banner or favicon exports land, each gains a pair entry in the same
manifest and is covered by the same DC-19 row.

**What pins the extensibility.** The test
`test_dc19_manifest_empty_pairs_blocks` proves a zero-pair manifest is refused
(the vacuity control), so the check cannot be silenced by removing the one pair
without saying why.

### Criterion 3: negative control that is run, not described

**What was built.** Seven tests in `tests/test_drift_check.py`:

| Test | What it proves |
|------|---------------|
| `test_dc19_synthetic_tree_is_green` | Correct hashes → green |
| `test_dc19_source_changed_without_export_reddens_dc19` | SVG changed, PNG unchanged → red |
| `test_dc19_export_changed_without_source_reddens_dc19` | PNG changed, SVG unchanged → red |
| `test_dc19_both_changed_together_is_green` | Both changed + hashes re-recorded → green |
| `test_dc19_manifest_missing_blocks` | Missing manifest → red (refusal, not pass) |
| `test_dc19_manifest_empty_pairs_blocks` | Empty pairs list → red (vacuity) |
| `test_dc19_printed_in_green_listing` | DC-19 appears in the OK listing |

**The verbatim failure message** (produced by the mutation in
`test_dc19_source_changed_without_export_reddens_dc19`):

```
  FAIL     DC-19  asset pairs: every source-export pair in assets/asset-pairs.json
           matches its recorded sha256 — a stale export or an edited source
           without re-export is refused (#592)
           FAIL DC-19: asset pair 1 has a mismatched source: source
           assets/social-preview.svg: recorded hash 227ace003abf0d07..., file
           on disk c2ac962a0f8ca95e...; export assets/social-preview.png:
           recorded hash 9f94e92886fb4a44..., file on disk
           9f94e92886fb4a44... — one half of a pair was changed without the
           other, or without re-recording both
```

**Mutation campaign.** No `scripts/mutation_receipt.py` run: the issue does
not name the #341 standard, a mutation receipt, or its generator. The negative
control above mutates the shipped fixture tree and asserts the CLI's exit code
and refusal text; it does not monkeypatch the checker.

## Files changed

| File | Change |
|------|--------|
| `scripts/drift_check.py` | `AssetPairsContract` dataclass, `_check_asset_pairs` function, DC-19 row in `LIVE_ROWS`, handling in `_run_row` |
| `tests/test_drift_check.py` | DC-19 in `_LIVE_IDS`, assets in `_LIVE_SURFACES`, seven test functions |
| `assets/asset-pairs.json` | New manifest: one pair (social-preview SVG + PNG), sha256 hashes recorded |

## Gate results

```
ruff check src tests scripts/drift_check.py          — All checks passed
ruff format --check src tests scripts/drift_check.py  — 366 files already formatted
mypy --strict scripts/drift_check.py tests/test_drift_check.py — Success: no issues found
```

## What is not in scope

- Uploading the social preview to GitHub repository settings (no API, owner's action per `MrBinnacle/skills#263`).
- Generating the PNG export from the SVG at build time (that closes the gap by construction, and is the better fix if reachable).
