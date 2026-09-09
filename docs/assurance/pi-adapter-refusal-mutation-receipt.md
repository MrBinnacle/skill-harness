# Mutation receipt: the Pi adapter's own refusal predicates

**Standard:** #341. **Build:** the Pi paired subject lane
(`src/skill_harness/subject/pi/`), the thin adapter into the existing
`ParsedEvalLog` seam. **Generator:** `scripts/mutation_receipt.py --select pi-`.
**Machine-readable record:** `docs/assurance/pi-adapter-refusal-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/subject/pi/launcher.py`
at `sha256:e2c59a26358834052978e07f58ebb66f69dd98105a74f33ed9331e27730bad7e` and
`src/skill_harness/subject/pi/parser.py` at
`sha256:f6d6f070736a7af2308cff48ddb9baed79d188aab93be2dec5a049f036c80f36`.
**Commit at generation:** `9dc7a4e` — informational only; currency is checked
against the digests above by `tests/test_mutation_receipt.py`.

Each case ran in its **own git worktree** at the recorded commit. Production was
never mutated in place; the generator asserts the production tree is
byte-unchanged afterwards, that the clean baseline passes first with nonzero
collection, that the mutant imports, and that the named test fails under it.

## What the predicates are

The adapter owns three refusals that fire BEFORE any model spend or any ingest.
They are apparatus validation; the scientific refusal predicates
(`UnexposedFullEpochError`, `NullArmContaminationError`) live downstream in
`subject/ingest.py` and are attested by the #387 receipt, not here.

- **Roster symmetry** (`verify_pair_symmetry`): the Full roster must equal the
  Null roster plus exactly the treatment entry. A baseline that differs across
  arms breaks the contrast before the first epoch launches.
- **Parser identity** (`verify_parser_identity`): the live parser/capture
  pipeline's version, content hash and AST semantic digest must equal the
  declared identity. An undeclared evidence pipeline must not spend.
- **Mid-epoch identity** (`_verify_identity`): a second `model_change` session
  entry means the subject changed mid-epoch. That is an apparatus error, not
  metadata; the epoch is refused before ingest.

## Results

| mutant | obligation | mutation | verdict | killing tests |
|---|---|---|---|---|
| M-P1 | pi-roster-symmetry | empty the cross-arm baseline check in `verify_pair_symmetry` | **KILLED** | `test_subject_pi.py::test_pair_symmetry_checks` |
| M-P2 | pi-parser-identity | skip the declared-vs-live comparison in `verify_parser_identity` | **KILLED** | `test_subject_pi.py::test_verify_parser_identity_refuses_mismatch` |
| M-P3 | pi-mid-epoch-identity | drop the second-`model_change` count guard in `_verify_identity` | **KILLED** | `test_subject_pi.py::test_parse_refuses_mid_epoch_model_change` |

Three hand-chosen mutants. **No mutation score is reported** — three cases
cannot support one; each case is a named obligation, not a sample.

## Why the mutants are shaped this way

Each mutant disables exactly one guard by replacing its condition with `False`,
leaving the exception class, message and call site in place so the mutant
compiles and imports and the only behaviour that changes is that the refusal
can no longer fire — the same shaping the #387 receipt used. M-P3's fixture is
deliberately discriminating: the synthetic second `model_change` entry carries
the SAME subject as the launch identity, so only the count guard can fire; a
subject-mismatch guard mutation would survive against it and falsely read as a
gap in the receipt.
