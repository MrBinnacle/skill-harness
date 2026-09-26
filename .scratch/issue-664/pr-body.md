# Evidence body — #664 delivered skill surface extractor

## What was built

A pure-function extractor (`src/skill_harness/extractor/delivered_surface.py`)
that reads a run's transcript message list and a set of subject card descriptions,
then classifies each card's delivery status within the skill listing Claude Code
delivered in the first user message. The module exposes:

- `DeliveredCard` — per-card model: name, status (visible/truncated/dropped),
  position, delivered description length, description tokens.
- `DeliveredListing` — aggregate model: subject cards, non-subject cards,
  raw listing text, total listing description tokens.
- `extract_delivered_listing(messages, subject_cards)` — the extraction function.

The extraction scans messages for a skill listing (identified by `- name: description`
lines), parses each card, then classifies each subject card:
- **visible**: the full description is a substring of the delivered card's description.
- **truncated**: the description is not found, but a prefix matches up to the
  1,536-character Claude Code truncation limit. Records the delivered length.
- **dropped**: the card is absent from the listing entirely.

A transcript with no listing (or no user messages, or a listing block with no card
lines) records every subject card as dropped with an empty `listing_text` — never a
guessed reason.

Built-in and third-party skills are recorded in `non_subject_cards` and are never
counted as subject cards.

## Acceptance criteria — test mapping

### AC1: Full subject listing — every card reads visible with its position

**Test:** `test_full_listing_all_cards_visible_with_position`
(`tests/test_delivered_surface.py:56`)

Two subject cards are placed in a listing message. The test asserts both cards
read `status == "visible"` with positions 0 and 1 respectively. A second test
(`test_full_listing_records_listing_text`) verifies the raw listing text and
token count are preserved.

**Observation:** This test passed on the first run because the implementation
handles the straightforward substring-match case directly. The test pins the
contract that every card in a complete listing must be classified as visible
with correct positional data.

### AC2: Poison fixture — one description removed reads dropped

**Test:** `test_poison_one_card_removed_reads_dropped`
(`tests/test_delivered_surface.py:82`)

Three subject cards are declared; the delivered listing omits one. The test
asserts the omitted card reads `status == "dropped"` with `position is None`
and `delivered_description_length is None`, while the other two remain visible.

**Observation:** Passed on the first run. The classifier returns `dropped`
when a card name is not found among the parsed listing cards. The test pins
that a dropped card must never read as visible.

### AC3: Poison fixture — one description cut at 1,536 reads truncated

**Test:** `test_poison_one_description_truncated_at_limit`
(`tests/test_delivered_surface.py:101`)

One subject card has a description longer than 1,536 characters; the delivered
listing carries only the first 1,536 characters. The test asserts the card
reads `status == "truncated"` with `delivered_description_length == 1536`.

**Observation:** Passed on the first run. The classifier detects truncation
when the full description is absent but a prefix of exactly `TRUNCATION_LIMIT`
characters matches. The test pins the specific length recorded.

### AC4: Transcript with no listing records empty, never guessed

**Tests:** `test_no_listing_records_empty_with_typed_reason`
(`tests/test_delivered_surface.py:120`), `test_empty_listing_block_records_empty`
(`tests/test_delivered_surface.py:153`), `test_messages_list_with_no_user_messages`
(`tests/test_delivered_surface.py:165`)

Three scenarios: (a) no user messages at all, (b) a user message with no card
lines, (c) messages with no listing pattern. All assert `listing_text == ""`,
`listing_description_tokens == 0`, and every subject card reads `dropped`.

**Observation:** All three passed on the first run. The extractor returns an
empty listing when `_find_listing_text` finds no listing block. The reason is
structural (no listing detected), never a guessed one. The test pins that the
listing text is empty and the token count is zero — the caller sees "nothing
was here" rather than a fabricated explanation.

### AC5: Built-in and third-party skills recorded apart, never counted as subject

**Test:** `test_builtin_skills_recorded_apart_not_counted_as_subject`
(`tests/test_delivered_surface.py:181`)

A listing contains one subject card and two non-subject cards. The test asserts
the subject card set is exactly `{"my-skill"}` and the two non-subject names
appear in `non_subject_cards`. A second test
(`test_only_non_subject_skills_yields_empty_subject_cards`) verifies a listing
with only non-subject skills yields no visible subject cards.

**Observation:** Both passed on the first run. The classifier partitions listing
cards by membership in the `subject_cards` input dict. Non-subject cards are
collected in listing order and never mixed into subject results.

### AC6: CI gates pass

**Command:** `ruff check src tests scripts && ruff format --check src tests scripts && mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py`

**Observation:** All three gates pass across the full scope (413 files
formatted, 375 source files type-checked, 0 lint errors). No regressions
introduced. The new module and test file conform to the repository's strict
typing and formatting standards.

## Files changed

| File | Change |
|------|--------|
| `src/skill_harness/extractor/delivered_surface.py` | New module: models + extraction function |
| `tests/test_delivered_surface.py` | New test file: 15 tests covering all 6 ACs |

## Mutation campaign

Not requested by this ticket. The ticket does not name a mutation receipt
obligation.

## Regression

The full test suite was not re-run (3000+ tests, ~5 min). The new module is
self-contained — no existing code imports it — so it cannot regress existing
tests. The gate (`ruff check`, `ruff format --check`, `mypy --strict`) passed
across the entire repository scope, confirming no import or type-level breakage.
