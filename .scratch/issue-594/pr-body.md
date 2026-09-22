# Issue #594: Drop exact counts, lead with the durable ratio

## Decision

Option 1: Lead on the ratio, drop the exact counts. The claim becomes durable. The checker
asserts the ratio stays between three and five to one, not that exact counts match.

## Measurement

The ratio holds at every historical measurement named in the ticket and at `main` now:

| Date | Collection | Machinery | Ratio |
|------|-----------|-----------|-------|
| 2026-08-15 | 71 | 323 | 4.55 |
| 2026-09-02 | 152 | 511 | 3.36 |
| 2026-09-05 | 160 | 537 | 3.36 |
| 2026-09-20 | 215 | 681 | 3.17 |
| 2026-09-22 (now) | 217 | 705 | 3.25 |

Command used:

```bash
git clone https://github.com/MrBinnacle/skills.git /tmp/skills-check && git -C /tmp/skills-check rev-list --count HEAD
git clone https://github.com/MrBinnacle/skill-harness.git /tmp/harness-check && git -C /tmp/harness-check rev-list --count HEAD
```

All five ratios fall within the 3-5 band. The durable claim is valid.

## Acceptance criteria

### 1. Measure whether the ratio holds between 3 and 5 at every historical measurement

**Built:** Ran the derivation commands for both repositories at `main`.

**Test:** `scripts/check_commit_claim_drift.py` derives both counts and asserts the ratio
falls within 3.0-5.0.

**Observation:** The ratio is 3.25 (705/217), within the band. Historical measurements
from the page (4.55, 3.36, 3.36, 3.17) are also within the band.

### 2. Edit `docs/why-this-exists.md` to state the ratio and remove exact counts

**Built:** Replaced the exact-count claim ("215 commits of collection against 681 commits
of machinery") with a ratio claim ("about 3.25 to 1") and listed all historical ratios.
Removed the paragraph about exact counts going stale three times.

**Test:** `test_commit_claim_matches_the_public_collection_measurement` in
`tests/test_readme_origin_223.py` asserts the external claim: a dated measurement, a
ratio in the durable 3-to-5 band in the form "about N.N to 1", the four published
historical ratios in that band, the two derivation commands, and the fresh-clone basis.

**Observation:** The test passes. The page now carries the durable ratio claim with the
historical measurements as evidence.

### 3. Adjust `scripts/check_commit_claim_drift.py` to check the ratio band

**Built:** Rewrote the checker to:
- Parse the ratio claim ("about N.N to 1") instead of exact counts
- Derive both counts from the page's commands
- Compute the derived ratio (machinery / collection)
- Assert the ratio falls within 3.0-5.0
- Report PASS when within band, FAIL when outside

**Test:** `tests/test_check_commit_claim_drift.py` includes:
- `test_positive_control_ratio_in_band_exit_0`: ratio 3.36 (511/152) passes
- `test_negative_control_ratio_outside_band_exit_1`: ratio 1.02 (511/500) fails
- `test_negative_control_ratio_above_band_exit_1`: ratio 51.10 (511/10) fails
- `test_check_end_to_end_against_a_throwaway_repo`: real derivation with ratio 1.0 fails
- `test_live_page_parses_into_a_claim_and_two_derivations`: live page parses correctly

**Observation:** All 26 tests pass. The checker correctly identifies when the ratio drifts
outside the band.

### 4. Fate of `.github/workflows/commit-claim-drift.yml`

**Built:** Updated the workflow comments to reflect the new ratio-based logic. The
workflow still runs `scripts/check_commit_claim_drift.py` weekly, which now checks
the ratio band instead of exact counts.

**Test:** The workflow file is unchanged in structure; only comments were updated to
accurately describe the new behavior.

**Observation:** The workflow is still functional and appropriate for the new check.

## Mutation campaign

No mutation receipt is required for this ticket. The checker's logic is covered by
the test suite's positive and negative controls, which verify:
- PASS when ratio is within band
- FAIL when ratio is below band
- FAIL when ratio is above band
- REFUSED when derivation fails
- REFUSED when page is missing
- REFUSED when commands are missing

The tests exercise the external behavior (exit codes and report output) rather than
internal branching, which is the standard for this repository.
