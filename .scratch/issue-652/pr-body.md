# PR body for #652: cross-card audit screen

## What this PR builds

A comparative screen across all published cards in `skills` (measured via
`git ls-files "skills/*/*/SKILL.md"`), so the choice of which card gets
confirmation spend is made by a screen, not by precedent.

Source: skills_research S476 framing audit and its cross-family review. Both
reviewers converged: the program has no comparative screen, and its first proof
card was never ranked against the other published cards.

## Acceptance criteria and evidence

### Criterion 1: Run `skill-harness skill audit` on every published card

**What was built:** `scripts/cross_card_audit.py` — a script that enumerates
published SKILL.md cards via `git ls-files` (with fallback to known paths),
calls `audit_skill_artifact()` from `skill_harness.preflight` on each, and
produces structured output.

**Test that pins it:** `tests/test_cross_card_audit.py::TestCrossCardAuditScript::test_script_exits_cleanly`
asserts the script exits with code 0 and produces non-empty output.
`test_every_published_card_has_a_row` asserts that all three known published
cards (`pull-rebase`, `push-secret-scan`, `declared-synthetic-positive-control`)
appear in the ranked table.

**Observation:** Before the change, no script existed to run the audit across
all cards. After the change, the script runs deterministically (offline, zero
cost) and produces the complete ranked table. The test that checks for card
presence failed before the script existed (module not found) and passes after.

### Criterion 2: Tabulate standing cost, measurable claims, and claim class

**What was built:** The ranked table in `docs/findings/cross-card-audit-screen.md`
columns: Standing (raw), Standing (cal), Fired (raw), Claim class. The claim
class is assigned by `_claim_class()` which checks whether Tier-1 mechanical axes
are available.

**Test that pins it:** `test_output_has_ranked_table` asserts the ranked table
header exists. `test_finding_has_ranked_table` asserts the committed finding
document contains the same table.

**Observation:** The `declared-synthetic-positive-control` card has UNMEASURED
standing cost because its description uses a YAML block scalar the minimal
parser cannot read — exactly the typed refusal the harness requires.

### Criterion 3: For each card, assess hazard-qualified task family plausibility

**What was built:** The `Hazard task family` column in the ranked table.
`_hazard_task_family_exists()` checks whether the card is under an existing
screen directory. Cards under `scripts/screens/419/` are flagged as having an
existing hazard task family; test fixtures are flagged as not production cards.

**Test that pins it:** The ranked table output contains the hazard family
column for every row, visible in both the script output and the committed
finding.

**Observation:** Both `pull-rebase` and `push-secret-scan` are part of the
#419 screen and have existing hazard task families. The synthetic control is a
test fixture and has no production task family.

### Criterion 4: Ranked table in `docs/findings/` with every card getting a row

**What was built:** `docs/findings/cross-card-audit-screen.md` — the committed
finding document containing the ranked table and per-card detail sections.

**Test that pins it:** `test_finding_exists` asserts the file exists at the
expected path. `test_finding_has_claims_and_refuses` asserts it contains both
`**Claims:**` and `**Refuses to claim:**` lines.

**Observation:** The file was absent before this change (test failed) and
present after (test passes).

### Criterion 5: "out of reach, because …" for cards that cannot be evaluated

**What was built:** The `Out of reach?` column in the ranked table. The
`declared-synthetic-positive-control` card is marked "test fixture — not a
production card". Other cards show "no".

**Test that pins it:** The column is present in every row of the ranked table,
visible in both script output and committed finding.

### Criterion 6: receipts-index.md updated

**What was built:** Entry added to `docs/receipts-index.md` under the Findings
section, with Claims and Refuses lines.

**Test that pins it:** `test_index_includes_finding` asserts the string
`cross-card-audit-screen` appears in the index.

**Observation:** The existing `tests/test_receipts_index.py` suite (18 tests)
passes without regression, confirming the population integrity of the index.

## Files changed

- `scripts/cross_card_audit.py` — new script, the audit screen
- `tests/test_cross_card_audit.py` — 9 tests (5 script, 3 finding, 1 index)
- `docs/findings/cross-card-audit-screen.md` — the ranked table finding
- `docs/receipts-index.md` — new entry for the finding

## Stage 1 gate

Stage 1 (Null-only qualification screens on top candidates) is priced at the
realised $0.083 per epoch. It is not run without an operator gate. This PR
completes Stage 0 only.
