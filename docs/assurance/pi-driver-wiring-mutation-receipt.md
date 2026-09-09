# Mutation receipt: the Pi driver's wiring, not its helpers

**Standard:** #341. **Build:** the Pi paired lane's production driver
(`src/skill_harness/subject/pi/runner.py`) and the container-boundary fix in
`launcher.py`. **Generator:** `scripts/mutation_receipt.py --select mr-`.
**Machine-readable record:** `docs/assurance/pi-driver-wiring-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/subject/pi/runner.py`
at `sha256:d9d583a165399631b19485ac260fb952dd8608b3772f83dd7446b0a8b5fabb3c` and
`src/skill_harness/subject/pi/launcher.py` at
`sha256:e2c59a26358834052978e07f58ebb66f69dd98105a74f33ed9331e27730bad7e`.
**Commit at generation:** `310466a` — informational only; currency is checked
against the digests above by `tests/test_mutation_receipt.py`. The runner
digest moved from the first generation's `8fcda34f8f60` by a line-ending
normalization; no content changed. First-generation pin: `b19793c`,
superseded with the M-R1 correction recorded below.

## Why this receipt exists

The driver commit said "five hand mutations confirm they bind to the wiring."
Those mutations ran in a scratch tree, were restored afterwards, and were
attested by nothing durable: a reader could not verify a single one. That is
exactly the shape of claim the #341 standard exists to retire. This receipt
converts the four receiptable cases to the standard's form.

The distinction the receipt attests: the adapter's controls were unit-tested
as HELPERS before the driver existed, and helpers nobody calls are dead code
with a docstring. Each case below mutates the DRIVER'S CALL, or the one
helper mechanism (the container version probe) that is only meaningful
through the call. The helpers' own predicates are attested separately by
`pi-adapter-refusal-mutation-receipt.md`; the two receipts are disjoint.

## Results

| mutant | obligation | mutation | verdict | killing tests |
|---|---|---|---|---|
| M-R1 | mr-driver-identity-gate | replace the driver's gate call with its measure-only form `verify_parser_identity(None)` — the declared identity is never compared, so an undeclared evidence pipeline passes the pre-spend gate and reaches spend | **KILLED** | `test_subject_pi_runner.py::test_parser_identity_mismatch_blocks_spend` (fails with DID NOT RAISE `ParserIdentityMismatchError` — the right assertion; the valid-path test passes under the mutant, as it must) |
| M-R2 | mr-driver-nonzero-epoch | drop the nonzero-returncode refusal — a crashed epoch is parsed and ingested as if it had run | **KILLED** | `test_subject_pi_runner.py::test_nonzero_epoch_refuses_before_evidence` |
| M-R4 | mr-container-version-probe | stop wrapping the container prefix in `measure_pi_version` — the pin names the host binary's version while the epoch runs the container's copy | **KILLED** | `test_subject_pi_runner.py::test_runtime_version_is_measured_across_the_container_boundary`; `test_container_version_mismatch_refuses_before_any_epoch` |
| M-R5 | mr-driver-container-wiring | the driver stops passing its `container=` to the version probe — the helper stays correct and the measured version still names the host | **KILLED** | the same two container tests as M-R4 |

Four hand-chosen mutants. **No mutation score is reported** — four cases
cannot support one; each is a named obligation, not a sample.

## What happened to M-R3

The scratch session's fifth case removed the driver's gate call entirely,
helper intact. Receipted form subsumes it: against the same two killing
tests, deleting the call and replacing the call with a bare measure are the
same obligation (the driver must COMPARE the declared identity, not merely
have a gate available). M-R1 covers it; M-R3 is not registered separately.

## How the mutants are shaped

M-R1's mutant is the helper's own documented apparatus-smoke posture:
`verify_parser_identity(None)` measures the live identity and compares
nothing. The name is already in runner.py's namespace, so the mutant
compiles, imports, runs, and reaches the spend boundary — the obligation it
attests is exercised, not merely crashed into.

**First-generation defect (2026-09-09, corrected same day):** the originally
registered M-R1 replaced the gate call with `parser_identity()`, a name that
was never imported in runner.py (the commit that claimed to add the import
only reflowed the import block; an import existing solely for the mutant
would have failed F401, which is likely why it silently did not land). That
mutant raised `NameError` at the call site, the registered tests went red
for the wrong reason, and the first-generation receipt attested a kill of an
obligation that was never exercised. The generator's import-check could not
catch it: the module imports fine; the failure is at call time. The
correction above was verified by hand before the mutant was re-registered:
the identity-mismatch test fails with DID NOT RAISE
`ParserIdentityMismatchError`, which is the assertion the obligation names.
The JSON was regenerated after the corrected mutant landed (`310466a`).

M-R4 and M-R5 pair deliberately: M-R4 mutates the helper and M-R5 mutates
only the argument at the driver's call site, so the pair attests that both
the mechanism AND the wiring to it matter, not one or the other.
