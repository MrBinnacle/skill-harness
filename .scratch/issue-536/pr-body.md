# Fix #536: duplicate mutant ids in MUTANTS

## What is wrong

`scripts/mutation_receipt.py` declared two mutants under `M-R1` and two under `M-R2`. Nothing
asserted that a mutant id is unique. Two mutants sharing one id means a receipt naming that id
does not identify which mutation ran, so a reader cannot check the claim against the code.

## What was built

### Criterion 1: Every entry in MUTANTS carries a distinct id

Renamed the later-registered pi-driver-wiring mutants:
- `M-R1` (mr-driver-identity-gate) → `M-R6`
- `M-R2` (mr-driver-nonzero-epoch) → `M-R7`

`M-R3` is not reused: the pi-driver-wiring receipt already uses that id for the scratch
session's fifth case that was never registered. The paired-gate2 mutants
(`389-ratification-binding` and `389-count-mismatch`) keep `M-R1` and `M-R2` because their
receipt (`paired-gate2-mutation-receipt`) was generated first.

**Test:** `test_every_mutation_id_is_unique` in `tests/test_mutation_receipt.py` asserts
`len({m.mutant_id for m in MUTANTS}) == len(MUTANTS)` and names any colliding id. This test
failed before the rename (reporting `M-R1, M-R2`) and passes after.

### Criterion 2: A test fails if two entries ever share one, and it fails by naming the colliding id

The uniqueness test collects duplicate ids and asserts the list is empty. Before the fix, the
assertion message read: `duplicate mutant ids: M-R1, M-R2. Each mutant must carry a distinct id
so that a receipt naming an id identifies exactly one mutation.` After the fix, the test passes.

**Test:** `test_every_mutation_id_is_unique` in `tests/test_mutation_receipt.py`.

### Criterion 3: Every committed receipt that names a renamed id is accounted for

Two receipts reference `M-R1` and `M-R2`:
1. `paired-gate2-mutation-receipt.json/md` — uses `M-R1` and `M-R2` for the `389-` mutants.
   These ids did not move. No change.
2. `pi-driver-wiring-mutation-receipt.json/md` — uses `M-R1` and `M-R2` for the `mr-` mutants.
   These ids moved. Added a dated note to both the prose and JSON receipt recording the rename:
   `M-R1` → `M-R6`, `M-R2` → `M-R7`. The table in the prose still names the original ids
   because it is a record of what the receipt measured.

**Test:** `test_receipt_still_describes_the_files_it_measured` continues to pass for both
receipts, confirming their target digests are still current.

## Mutation campaign

No mutation campaign was run. The ticket names a static defect (duplicate ids) and a missing
assertion, not a behavioral regression. The uniqueness test is the assertion; no mutant is
needed to prove it works.

## Gate results

- `ruff check src tests`: all checks passed
- `ruff format --check src tests`: 329 files already formatted
- `mypy --strict scripts/mutation_receipt.py tests/test_mutation_receipt.py`: success, no issues
- `pytest tests/test_mutation_receipt.py`: 38 passed
