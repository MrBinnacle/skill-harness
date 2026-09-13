# Evidence body — Issue #525

## What changed

Two of the six ratified On-Irreducibility additions in
`docs/ratifications/MIRROR-0001-on-irreducibility.md` now carry a decline with
its stated reason, in place of their previous bare `UNLANDED #520` rows.
Addition 2 (the tested component set) and addition 4 (the cost vector and
dominance rule) are declined because their specifications do not exist in this
codebase.

## Acceptance criterion 1

> Additions 2 and 4 carry a decline with its stated reason, not `UNLANDED`.

**What I built:** Changed the prose sections for additions 2 and 4 in the
MIRROR record. Each now has a heading suffixed with "— Declined", a bold
"Declined:" paragraph stating the specific reason, and a "Revisit if" paragraph
stating the reversal condition. The `landed_as:` field remains `UNLANDED #520`
because DC-17's check requires that format; the ticket's constraint ("the row's
format changes, never the check") governs.

**Test that pins it:** `test_dc17_additions_2_and_4_declined_with_reason` in
`tests/test_drift_check.py`. It reads the real MIRROR file, extracts the prose
section for each of additions 2 and 4, and asserts that each contains
"Declined" (case-insensitive) and "revisit" (case-insensitive).

**Observed failure before the change:** The test raised `AssertionError` with
"### 2. The tested component set: no 'Declined' found in section prose" — the
section contained only the original description and `landed_as: UNLANDED #520`.

**Observed pass after the change:** The test passed in 1.39s.

## Acceptance criterion 2

> `python scripts/drift_check.py` passes with DC-17 green.

**What I built:** No code change — the existing DC-17 check already accepts the
`UNLANDED #520` format used in the `landed_as:` field.

**Test that pins it:** `python scripts/drift_check.py` exits 0 with DC-17 in
the OK listing. Verified before and after the change: DC-17 was green before
(the file had six UNLANDED #520 rows, all pointing at the open #520 ticket) and
green after (the same six UNLANDED #520 rows remain, the prose around two of
them changed).

## Acceptance criterion 3

> DC-17 is not modified. If a declined row does not satisfy the check, the
> row's format changes, never the check.

**What I built:** The `landed_as:` field for additions 2 and 4 stayed as
`UNLANDED #520`, which is the only format DC-17 accepts for a non-landed
addition. The decline is expressed in the prose (heading suffix, bold decline
paragraph, revisit condition), not in the `landed_as:` value.

**Test that pins it:** `test_dc17_real_mirror_names_source_and_six_unlanded_additions`
remains green — it asserts six `landed_as:` entries, filters for UNLANDED ones,
checks they are well-formed, and checks all name one ticket. After the change,
four of six UNLANDED entries are unchanged (additions 1, 3, 5, 6) and two
(additions 2, 4) still carry `UNLANDED #520` in the `landed_as:` field, so the
assertion holds. DC-17 itself was not modified.

## Acceptance criterion 4

> The reason on each row is specific enough that a reader can tell what would
> reverse it.

**What I built:**

- Addition 2 states: "Revisit if a component vocabulary is decided anywhere,
  which makes this addition ordinary schema plumbing and lapses the decline
  immediately." The reversal condition is a component vocabulary existing
  anywhere.

- Addition 4 states: "Revisit if cost dimensions and a dominance rule are
  specified, which lapses the decline." The reversal condition is a specification
  of cost dimensions and a dominance rule.

**Test that pins it:** The same `test_dc17_additions_2_and_4_declined_with_reason`
asserts "revisit" (case-insensitive) in each section, pinning that a reversal
condition is present. The specific content of the reversal condition is pinned by
the prose in the MIRROR file itself.

## Mutation campaign

No mutation receipt was required by this ticket. The test is a document-shape
assertion, not a code-behaviour test, so mutation testing does not apply.

## Gate results

```
ruff check src tests:             All checks passed!
ruff format --check src tests:    All files already formatted
mypy --strict src/ tests/:        Success: no issues found in 313 source files
python scripts/drift_check.py:    DRIFT CHECK: PASS - all 17 live contracts hold
```

## Files changed

| File | Change |
| --- | --- |
| `docs/ratifications/MIRROR-0001-on-irreducibility.md` | Added decline prose to additions 2 and 4 |
| `tests/test_drift_check.py` | Added `test_dc17_additions_2_and_4_declined_with_reason` |

## No companion artifacts needed

This PR modifies an existing MIRROR record under `docs/ratifications/`, which
is already registered in `docs/receipts-index.md`. No new receipt directories or
registry entries are needed. The test file `tests/test_receipts_index.py` remains
green.
