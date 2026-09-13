# Fix #485: Remove retired paper surface from design snapshot

## Summary

The `.impeccable/design.json` snapshot of DESIGN.md still declares six `receipt-*` colour tokens, four `receipt-*` typography faces, and component CSS that uses serif families and paper ground. DESIGN.md retired these at #308. This change brings the snapshot into agreement with DESIGN.md.

## Acceptance Criterion 1: No retired receipt-* tokens survive in the snapshot

**What was built:** Three tests in `tests/test_impeccable_design_snapshot_485.py`:

- `TestReceiptTokensRemoved::test_no_receipt_color_tokens` — iterates `extensions.colorMeta` and asserts no key starts with `receipt-`.
- `TestReceiptTokensRemoved::test_no_receipt_typography_tokens` — iterates `extensions.typographyMeta` and asserts no key starts with `receipt-`.
- `TestReceiptTokensRemoved::test_no_receipt_anywhere_in_snapshot_json` — reads the raw JSON file and searches for any `"receipt-*"` string in keys or values.

**Test pinned before change:** `test_all_colour_tokens_are_bench` failed with `AssertionError: non-bench colour token: receipt-ink`. `test_no_receipt_color_tokens` also failed, listing all six receipt-* keys.

**Test after change:** All three tests pass. The snapshot's colour metadata contains only `bench-*` keys. The typography metadata contains only `bench-*` keys. No `receipt-*` string exists anywhere in the JSON file.

**Change applied:** Removed six entries from `extensions.colorMeta`: `receipt-ink`, `receipt-paper`, `receipt-rule`, `receipt-thead`, `receipt-accent`, `receipt-refusal-edge`. Removed four entries from `extensions.typographyMeta`: `receipt-body`, `receipt-h1`, `receipt-h2`, `receipt-figure`.

## Acceptance Criterion 2: Site Header declares no serif family and no paper ground

**What was built:** Two tests:

- `TestSiteHeader::test_no_serif_family` — searches the Site Header component's CSS for `font-family` declarations containing `serif`, `Georgia`, or `Times`. Asserts none match.
- `TestSiteHeader::test_no_paper_ground` — searches the Site Header component's CSS for `#fbfbf9` or `var(--receipt-paper)`. Asserts none match.

**Test pinned before change:** `test_no_serif_family` failed with `Site Header declares a serif family: matched 'font-family\\s*:\\s*[^;]*Georgia' in CSS`. `test_no_paper_ground` failed with `Site Header declares a paper ground: matched '#fbfbf9' in CSS`.

**Test after change:** Both tests pass. The Site Header CSS now uses `border-bottom: 2px solid #e6edf3` (Ink), `padding: 1.5rem 0 0.5rem` (matches DESIGN.md's spec), and `color: inherit` for links. No serif family and no paper ground.

**Change applied:** Rewrote the Site Header component's CSS to remove `background: #fbfbf9`, `font-family: Georgia, "Times New Roman", serif`, `color: #16181d`, and `color: #1f4f82`. Replaced border colour with `#e6edf3` (Ink, the heaviest line on the page per DESIGN.md).

## Acceptance Criterion 3: Absent Marker declares no serif family and retains italic

**What was built:** Three tests:

- `TestAbsentMarker::test_no_serif_family` — searches for serif font-family declarations. Asserts none match.
- `TestAbsentMarker::test_retains_italic` — searches for `font-style: italic`. Asserts it is present.
- `TestAbsentMarker::test_not_coloured` — searches for explicit `color` declarations. Asserts none match.

**Test pinned before change:** `test_no_serif_family` failed with `Absent Marker declares a serif family: matched 'font-family\\s*:\\s*[^;]*Georgia' in CSS`. `test_not_coloured` failed with `Absent Marker has an explicit colour: matched 'color\\s*:\\s*#[0-9a-f]+' in CSS`.

**Test after change:** All three tests pass. The Absent Marker CSS is `.ds-absent { font-style: italic; }`. It retains italic. It has no serif family and no explicit colour.

**Change applied:** Replaced the Absent Marker CSS from `font-style: italic; font-family: Georgia, "Times New Roman", serif; color: #16181d;` to `font-style: italic;`. This matches DESIGN.md's spec: italic, unbordered, uncoloured.

## Acceptance Criterion 4: impeccable's own conformance run passes against the edited snapshot

**What was built:** Two tests in `TestBenchTokensOnly`:

- `test_all_colour_tokens_are_bench` — iterates all colour keys, asserts each starts with `bench-`.
- `test_all_typography_tokens_are_bench` — iterates all typography keys, asserts each starts with `bench-`.

**Test pinned before change:** `test_all_colour_tokens_are_bench` failed with `non-bench colour token: receipt-ink`. `test_all_typography_tokens_are_bench` failed with `non-bench typography token: receipt-body`.

**Test after change:** Both tests pass. The snapshot's palette is bench-* only, matching what the tree draws.

**Change applied:** The same token removals that satisfied criterion 1. The snapshot now declares only what DESIGN.md declares: the bench-* palette and the bench-command / bench-verdict typography.

## Additional changes beyond the minimum

The ticket says "the Site Header and Absent Marker components need to be re-deriving against DESIGN.md's current spec at the same time." The component CSS for Refusal Block, Rule Block, Data Table, and Definition Grid also used retired receipt-* tokens. These were re-derived:

- **Refusal Block:** edge colour changed from `#8a5a00` (Refusal Ochre) to `#58a6ff` (Can't-Tell Blue, `bench-cant-tell`), serif family and paper ground removed.
- **Rule Block:** edge colour changed from `#16181d` (Document Ink) to `#e6edf3` (Ink), serif family and paper ground removed.
- **Data Table:** `font-family: Georgia, serif`, `color: #16181d`, `background: #fbfbf9` removed; cell borders use `#30363d` (Hairline), table head fill uses `#010409` (Void).
- **Definition Grid:** `font-family: Georgia, serif`, `color: #16181d` removed.

The narrative was also updated:

- `narrative.overview`: replaced the claim of "two distinct visual systems" with the resolved single-system state. DESIGN.md records this as resolved 2026-08-30.
- `narrative.dos`: removed "Refusal Ochre" reference and "receipt surfaces" reference; updated to match DESIGN.md's Do's.
- `narrative.donts`: updated to match DESIGN.md's Don'ts, removing receipt-surface references.

## Review corrections

The first implement pass removed the retired tokens and re-derived components, but left three holes the ticket's "Done when" clause and the tree both require:

1. **`bench-cant-tell` was missing from `colorMeta`.** The Refusal Block CSS drew `#58a6ff` after the ochre retirement, and Site Header focus uses the same literal, but the palette did not name the token. Declared now (`#58a6ff`, Can't-Tell Blue).
2. **Site type faces were not added when `receipt-*` faces left.** DESIGN.md's replacements are `bench-prose`, `bench-h1`, `bench-h2`, `bench-figure`. Added to `typographyMeta`.
3. **`The Mono-Carries-The-Claim Rule` still said "Serif is for prose only" and "both surfaces".** Rewritten to match DESIGN.md: mono for claims, system sans for prose.
4. **Site Header links** now underline and carry a Can't-Tell Blue focus ring, matching `style.css` and DESIGN.md's Site Header rule.
5. **Tests** now pin (a) every component CSS hex is in `colorMeta`, (b) no component draws serif or paper ground, (c) site faces and `bench-cant-tell` are present, (d) narrative no longer claims two systems or endorses serif.

## Gate

```
ruff check src tests       — passed
ruff format --check src tests — passed
mypy --strict src/ tests/   — passed
```

## Files changed

- `.impeccable/design.json` — removed receipt-* tokens, declared bench-cant-tell and site faces, re-derived components, updated narrative
- `tests/test_impeccable_design_snapshot_485.py` — tests pinning all 4 acceptance criteria plus the review corrections
