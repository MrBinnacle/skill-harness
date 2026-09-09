# Mutation receipt: the Pi driver's wiring, not its helpers

**Standard:** #341. **Build:** the Pi paired lane's production driver
(`src/skill_harness/subject/pi/runner.py`) and the container-boundary fix in
`launcher.py`. **Generator:** `scripts/mutation_receipt.py --select mr-`.
**Machine-readable record:** `docs/assurance/pi-driver-wiring-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/subject/pi/runner.py`
at `sha256:8fcda34f8f60c4915d7d8f1fd155920ea29865162684b3c338ae4cdeeea451dc` and
`src/skill_harness/subject/pi/launcher.py` at
`sha256:e2c59a26358834052978e07f58ebb66f69dd98105a74f33ed9331e27730bad7e`.
**Commit at generation:** `b19793c` — informational only; currency is checked
against the digests above by `tests/test_mutation_receipt.py`.

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
| M-R1 | mr-driver-identity-gate | replace the driver's `verify_parser_identity` gate call with a bare measure — an undeclared evidence pipeline passes the pre-spend gate | **KILLED** | `test_subject_pi_runner.py::test_parser_identity_mismatch_blocks_spend`; `test_valid_pair_runs_and_reaches_ingest` |
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

M-R1 needs `parser_identity` importable in runner.py so the mutant compiles
— the import was added in `b19793c`; the live call site is unchanged.
M-R4 and M-R5 pair deliberately: M-R4 mutates the helper and M-R5 mutates
only the argument at the driver's call site, so the pair attests that both
the mechanism AND the wiring to it are load-bearing, not one or the other.
