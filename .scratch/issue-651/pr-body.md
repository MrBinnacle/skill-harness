# #651: Replace #621 placebo with off-domain parse-csv card

## What this PR does

Replaces the same-domain `push-secret-scan` placebo (a git card that biases
Full minus Placebo in an unknown direction) with `parse-csv`, an off-domain
card matching the real `pull-rebase` card's structural shape. Adds a
surface-match check, a listing-position assertion on the readout, and the
inertness-screen launcher with three typed outcomes.

## Acceptance criteria

### 1. New placebo card: parse-csv

**Built:** `scripts/screens/419/v5_arms/placebo/parse-csv/SKILL.md` — 7 H2
sections, 8 fenced code blocks, 4 numbered steps, 10 bullet points. Name
`parse-csv` (two-token kebab, verb-noun, like `pull-rebase`). Description 182
chars / 31 words against the real card's 190 / 28 (4.2% char diff, within 10%
tolerance). Every imperative in the body names a `.csv`, `.tsv` or `.xlsx`
file; the fixture tree holds none (13 `.py`, 2 `.md`, 1 `.yaml`, 1 `.sh`), so
no instruction has an object the agent can act on in world A.

**Test:** `test_placebo_matches_the_card_section_for_section` — asserts
identical H2 count, fenced-block count, step count, and bullet count between
the placebo and the real card. `test_placebo_length_and_description_are_within_the_match_band`
— asserts body word count within 10% and description character count within 10%.
`test_placebo_is_silent_on_domain_terms` — asserts the placebo contains no
git/rebase/manifest/push/commit/SHA/config terms. `test_placebo_name_matches_its_directory`
— asserts the frontmatter name equals the directory name.

**Before/after:** Before the change, `test_placebo_matches_the_card_section_for_section`
passed with the old `push-secret-scan` card (same structure, same domain). After
replacing the card, the same test passes with `parse-csv` (same structure,
different domain). `test_placebo_is_silent_on_domain_terms` failed with the old
card (it contained `git`, `push`, `config` terms) and passes with the new one.

### 2. Surface-match check

**Built:** `scripts/screens/419/v5_surface_match.py` — prints both
descriptions' character, word and token counts and both bodies' line counts
and section headings. Refuses a placebo description or body containing banned
terms (`git`, `rebase`, `manifest`, `push`, `commit`, `SHA`, `config`). Refuses
when the fixture tree contains file types the placebo names (`.csv`, `.tsv`,
`.xlsx`). Description length tolerance 10%.

**Test:** `test_surface_match_check_passes` — runs `check()` and asserts exit
code 0. `test_surface_match_check_refuses_a_poison_placebo` — creates a
poison fixture (a placebo naming `git`), patches `PLACEBO_SKILL`, and asserts
`check()` returns exit code 1. `test_placebo_names_no_fixture_file_types` —
asserts the placebo file types do not intersect the fixture tree's types.

**Before/after:** Before the change, no surface-match check existed. The
poison-fixture test confirms the check fires on a contaminated placebo.

### 3. Listing position assertion

**Built:** `_listing_position()` in `v5_cue_stage1a.py` — reads each eval
log's first user message, counts numbered listing entries, records the card's
1-indexed position. The readout now carries `listing_positions` and
`listing_position_violations` alongside the existing bounds data. A position
other than 1 in any epoch surfaces in `listing_position_violations`.

**Test:** `test_listing_position_regex_matches_numbered_entries` — asserts the
`_LISTING_NUMBERED_RE` regex matches `1. parse-csv: Use before` and does not
match `Skills:` or `- a bullet`. `test_placebo_desc_constant_matches_card` —
asserts the `PLACEBO_DESC` constant equals the card's frontmatter description.

**Before/after:** Before the change, no listing-position assertion existed.
The regex test pins the parsing logic; the full assertion is exercised when
real eval logs are read (requires the private fixture).

### 4. PLACEBO_DIR update

**Built:** Updated `PLACEBO_DIR` in `v4_cells.py` from
`v4_arms/placebo/push-secret-scan` to `v5_arms/placebo/parse-csv`. Updated
the docstring in `v5_cue_cells.py` to reference the new card.

**Test:** All 7 existing tests in `test_v4_cells_620.py` pass with the new
placebo (verified: shape match, length band, silent on domain terms, name
matches directory, lint catches the card it guards against).

**Before/after:** Before the change, `PLACEBO_DIR` pointed at the old
`push-secret-scan` card. After the change, it points at `parse-csv`. The
entire downstream chain (`v5_cue_cells.py` -> `v5_cue_stage1a.py`) inherits
the new path through the import.

### 5. Inertness-screen launcher

**Built:** `scripts/screens/419/v5_inertness_screen.py` — Placebo-B against
Null-B, 16 vs 8 epochs, one-sided bounds per arm at alpha 0.05. Three typed
outcomes (S477):
- `REDESIGN`: LB(P - N) > 0 — placebo is active, replace before Stage 1A
- `CONTINUE`: no such bound — screen does not certify inertness
- `CANT_TELL_YET`: fewer than 12 valid Placebo epochs — rerun

Screen never passes on p > 0.05.

**Test:** `test_redesign_when_lb_diff_positive` — 16/16 vs 1/8 yields REDESIGN.
`test_continue_when_lb_diff_not_positive` — 8/16 vs 5/8 yields CONTINUE.
`test_cant_tell_yet_when_too_few_placebo_epochs` — 5/10 yields CANT_TELL_YET.
`test_screen_never_passes_on_p_gt_005` — equal rates yield CONTINUE, never PASS.
`test_null_b_loader_reads_summary` and `test_placebo_b_loader_reads_rows` — pin
the data loaders. `test_dry_run_prints_no_model` — pins the dry-run path.

**Before/after:** Before the change, no inertness-screen launcher existed.
All three outcome paths are exercised by the tests.

### 6. Evidence body

**Built:** This file (`.scratch/issue-651/pr-body.md`), committed on the
branch before merge.

## Mutation campaign

No mutation receipt was requested for this ticket.

## Gate

All modified and new files pass `ruff check`, `ruff format --check`, and
`mypy --strict`. Pre-existing mypy errors in `consequence_v4.py` and
`twin_readout.py` are unrelated to this change.
