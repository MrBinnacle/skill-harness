# Evidence body — Issue #525

## What changed

Two of the six ratified On-Irreducibility additions in
`docs/ratifications/MIRROR-0001-on-irreducibility.md` now carry a decline with
its stated reason, in place of their previous bare `UNLANDED #520` rows.
Addition 2 (the tested component set) and addition 4 (the cost vector and
dominance rule) are declined because their specifications do not exist in this
codebase. Their `landed_as: UNLANDED #520` rows are removed: a decline is a
landed decision, not open work, so DC-17 has two fewer rows pointing at #520.

## Acceptance criterion 1

> Additions 2 and 4 carry a decline with its stated reason, not `UNLANDED`.

**What I built:** Changed the prose sections for additions 2 and 4 in the
MIRROR record. Each has a heading suffixed with "— Declined", a bold
"Declined:" paragraph stating the specific reason, and a "Revisit if" paragraph
stating the reversal condition. The `landed_as: UNLANDED #520` line is gone
from both sections. The mirror intro states that a declined addition carries a
decline instead of an `UNLANDED` row.

**Test that pins it:** `test_dc17_additions_2_and_4_declined_with_reason` in
`tests/test_drift_check.py`. It reads the real MIRROR file, extracts the prose
section for each of additions 2 and 4, and asserts: "Declined" present,
"Revisit if" present, no `landed_as: UNLANDED`, no `landed_as:` at all, and
reason phrases that name the missing specification (component vocabulary /
`delivery.channel`; cost dimensions / dominance rule).

**Observed failure before the change:** The implement seat left
`landed_as: UNLANDED #520` on both declined sections. AC1 and S445 require the
opposite: a decline clears the UNLANDED row so closing #520 does not re-break
DC-17. The review seat removed those two rows and strengthened the pin.

**Observed pass after the change:** The test passed.

## Acceptance criterion 2

> `python scripts/drift_check.py` passes with DC-17 green.

**What I built:** No DC-17 code change. Clearing two UNLANDED rows leaves four
`UNLANDED #520` rows for additions 1, 3, 5 and 6. DC-17 still accepts that
format against the open #520 ticket.

**Test that pins it:** `python scripts/drift_check.py` exits 0 with DC-17 in
the OK listing (verified with the ticket-state seam offline and against the
live path).

## Acceptance criterion 3

> DC-17 is not modified. If a declined row does not satisfy the check, the
> row's format changes, never the check.

**What I built:** `scripts/drift_check.py` is untouched. The format change is
the absence of `landed_as` on declined additions: DC-17 only iterates
`landed_as:` matches, so two fewer open-work rows is the row-format change the
criterion names. Pointing `landed_as` at a string that merely appears under
`docs/sers/` or `src/skill_harness/` would be a false landing; that path was
refused.

**Test that pins it:** `test_dc17_real_mirror_names_source_and_six_unlanded_additions`
still requires six addition headings and well-formed UNLANDED rows that name
one ticket. It now expects four `landed_as` entries (the still-open additions),
not six. DC-17 itself was not modified. All thirteen DC-17 tests pass.

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

**Test that pins it:** The same
`test_dc17_additions_2_and_4_declined_with_reason` asserts "Revisit if" in each
section and pins the reason phrases that name what is missing.

## Mutation campaign

No mutation receipt was required by this ticket. The test is a document-shape
assertion, not a code-behaviour test, so mutation testing does not apply.

## Gate results

```
ruff check src tests:             All checks passed!
ruff format --check src tests:    All files already formatted
mypy --strict src/ tests/:        Success: no issues found in 313 source files
python scripts/drift_check.py:    DRIFT CHECK: PASS - all 17 live contracts hold
DC-17 pytest (-k dc17):           13 passed
```

## Files changed

| File | Change |
| --- | --- |
| `docs/ratifications/MIRROR-0001-on-irreducibility.md` | Decline prose on additions 2 and 4; cleared their UNLANDED rows; intro notes decline format |
| `tests/test_drift_check.py` | Pin decline-without-UNLANDED; shape test expects four open landed_as rows |

## No companion artifacts needed

This PR modifies an existing MIRROR record under `docs/ratifications/`, which
is already registered in `docs/receipts-index.md`. No new receipt directories or
registry entries are needed.
