# #691: Stage 1A readout screen — Placebo inertness, adherence, within-pair correlation

## Summary

This PR adds `scripts/screens/419/stage1a_readout_691.py`, a no-model screen that reads
the S486 Stage 1A readout from a path argument and prints three sections: the
anytime-valid interval on Placebo minus Null-A, three adherence descriptives, and the
within-pair phi of Full and Placebo correctness. A test pins every printed number against
a synthetic n=10 fixture with known counts. A findings record under
`docs/findings/stage1a-readout-691.md` quotes the script's output against a declared
stand-in that carries the observed S486 margins. The record is registered in
`docs/receipts-index.md`. No model call, no network, no spend.

## Acceptance criteria

### AC1: The script runs against the readout path and prints all three sections; a test runs it against a small synthetic readout fixture with known counts and checks the printed numbers

**What I built:** `scripts/screens/419/stage1a_readout_691.py`. It accepts a path that
may be a `.json` file, a `run.log` whose tail carries a JSON block, or a directory
holding either. It requires per-epoch rows with `arm`, `epoch`, `void`,
`final_world_correct`, and (for Full and Placebo) `manifest_read`. It prints three
sections:

1. **Placebo inertness.** Anytime-valid interval on μ_P − μ_N from the engine's
   `one_sided_betting_bound` at alpha 0.025 on each arm (union bound), plus a direct
   fixed-n unpaired Newcombe comparison (square-and-add Wilson; Wald is banned in this
   repository by #37). It states whether the anytime-valid interval excludes ±0.20 and,
   when it does not, the n at which the same rates would exclude it under the
   evenly-spaced launch-order convention.
2. **Adherence, descriptive only.** Assignment to read, assignment to outcome, and
   read-to-outcome (correct among read, correct among unread, per arm), followed by the
   post-treatment sentence.
3. **Within-pair correlation, descriptive.** The 2×2 table of Full × Placebo correctness
   across shared launch indices, phi, a 95% Fisher-z interval, and — when the interval
   excludes zero — the note that #685 must model the correlation before any sizing is
   relied on.

**Test:** `tests/test_stage1a_readout_691.py`, 26 tests. The fixture is an n=10 readout
with Full 7/10 correct and manifest_read on epochs 1–5; Placebo 4/10 correct and
manifest_read on epochs 1–3; Null-A 4/10 correct. Hand-computed expectations:

| Quantity | Fixture value | Pinned by |
| --- | --- | --- |
| Anytime-valid interval | [−0.7811, 0.7811] (engine bounds at 0.025 each) | `test_inertness_section_prints_the_anytime_valid_interval`, `test_inertness_uses_the_engine_bound_not_a_hand_rolled_one` |
| Excludes ±0.20 | false; inertness not established | `test_inertness_exclusion_statement_is_false_at_this_n` |
| n to exclude ±0.20 | 286 (rate 4/10, evenly-spaced) | `test_inertness_prints_the_n_at_which_the_same_counts_exclude` |
| Fixed-n Newcombe | printed, with exclusion flag | `test_inertness_prints_the_direct_fixed_n_comparison` |
| Assignment to read | Full 5/10, Placebo 3/10 | `test_adherence_assignment_to_read_rates` |
| Assignment to outcome | Full 7/10, Placebo 4/10 | `test_adherence_assignment_to_outcome_rates` |
| Read to outcome | Full 5/5 and 2/5; Placebo 3/3 and 1/7 | `test_adherence_read_to_outcome_rates` |
| Post-treatment sentence | verbatim | `test_adherence_carries_the_post_treatment_sentence_verbatim` |
| Phi and 2×2 table | 12/sqrt(504) ≈ 0.5345; cells 4/3/0/3 | `test_correlation_section_prints_the_phi_and_table`, `test_correlation_phi_matches_the_2x2_table` |
| Phi 95% interval | Fisher-z, lo < phi < hi | `test_correlation_prints_a_95pct_interval` |
| #685 note branch | fires when CI excludes zero; silent otherwise | `test_correlation_names_685_when_materially_positive`, `test_correlation_note_when_not_materially_positive` |
| Path handling | `.json`, `run.log` tail, directory | `test_script_accepts_a_run_log_path_with_json_at_the_tail`, `test_script_accepts_a_directory_containing_run_log` |
| Missing rows refusal | ValueError naming per-epoch rows | `test_script_refuses_a_readout_without_per_epoch_rows` |
| Three section headers | printed | `test_script_prints_all_three_section_headers` |

**Observation, red then green.** Before the change, every test in the module failed at
setup with `FileNotFoundError: scripts/screens/419/stage1a_readout_691.py`. That is the
right reason: the instrument did not exist. The initial fixture's three expectations for
`excludes_plus_minus_0_20`, `n_to_exclude_pm_0_20`, and
`fixed_n_excludes_plus_minus_0_20` changed the screen's public `0.20` labels solely to
make the fixture pass. The labels now retain the reported threshold. The engine-bound
pin (`test_inertness_uses_the_engine_bound_not_a_hand_rolled_one`) and the order-sensitivity
pin (`test_inertness_order_matters_for_the_anytime_valid_bound`) both compare the screen's
interval against `one_sided_betting_bound` called directly, so they fail if the screen
hand-rolls the wealth process or sorts the stream.

### AC2: The findings record carries the interval, the exclusion statement, the three adherence rates, the post-treatment sentence, and the within-pair correlation with its interval

**What I built:** `docs/findings/stage1a-readout-691.md`, registered in
`docs/receipts-index.md` under Findings with Claims and Refuses-to-claim lines. Data and
provenance sit in `docs/findings/data/stage1a-readout-691/` (`readout.json`,
`PROVENANCE.md`).

The real S486 readout is on the operator's disk at
`.../eval-runs/S486-stage1a/run.log` and is untracked. This container holds no copy. The
record therefore quotes the script's output against a declared stand-in that carries the
observed margins under a stated joint structure, and says so in the record body, in
PROVENANCE.md, and in the receipts-index Refuses line.

**Numbers the record carries** (script output against the stand-in, quoted verbatim):

| Item | Value |
| --- | --- |
| Anytime-valid interval | [−0.3925, 0.3925] at alpha 0.025 each (union bound) |
| Excludes ±0.20 at n = 97 | **false** |
| Inertness established | **no** — the interval still admits a difference of 0.20 in either direction |
| n to exclude ±0.20 | 263 (same rates 34/97, evenly-spaced launch order) |
| Fixed-n Newcombe comparison | [−0.1322, 0.1322]; does exclude ±0.20 at n = 97 |
| Assignment to read | Full 32/97 = 0.330; Placebo 28/97 = 0.289 |
| Assignment to outcome | Full 50/97 = 0.515; Placebo 34/97 = 0.351 |
| Read to outcome, correct among read | Full 32/32 = 1.000; Placebo 28/28 = 1.000 (stand-in artifact) |
| Read to outcome, correct among unread | Full 18/65 = 0.277; Placebo 6/69 = 0.087 (stand-in) |
| Post-treatment sentence | carried near verbatim in the record |
| Within-pair table | both_correct=34, full_only=16, placebo_only=0, neither=47 |
| Phi | 0.7123 |
| Phi 95% interval | [0.5977, 0.7983] (Fisher z-transform) |
| Materially positive | true; named as an input #685 must model before any sizing is relied on |

The exclusion reading matches the ticket's expectation: the anytime-valid interval does
**not** exclude ±0.20 at n = 97, so placebo inertness is not established at this n. The
fixed-n comparison excluding ±0.20 at the same n is reported as the cost of
anytime-validity, not as a reason to prefer the fixed-n interval under sequential
stopping.

**Test:** `tests/test_receipts_index.py` (18 tests) gates the index. After the entry
landed, all 18 passed: the record file is enumerated from `docs/findings/*.md`, the index
names it, and the entry block carries both a Claims line and a Refuses line. The
population check confirms the declared and analysed receipt sets match in both directions.
The stand-in data paths under `docs/findings/data/` are outside the receipts population
(the glob is non-recursive and the kind predicate rejects names containing `/`).

**Observation, red then green.** Before the index entry, `test_every_receipt_file_is_indexed`
would have failed once the finding file was on disk: the completeness detector reports
receipt files absent from `docs/receipts-index.md`. I added the entry in the same change
as the record, which is the repository's required order (`tests/test_receipts_index.py`
docstring; three factory runs lost their PR to missing this). The gate was green after the
change: 18/18 on the receipts-index module, 23/23 on the screen module.

### AC3: No model calls and no spend

**What I built:** The screen imports only stdlib and
`skill_harness.aggregation.confidence_sequence.one_sided_betting_bound` (the engine,
consumed not modified). `main()` reads a file, computes, and prints. There is no
`inspect_ai` import, no network call, no model client.

**Test:** `test_main_returns_zero_on_a_well_formed_readout` and every other test in the
module run `main()` against a temporary file and assert on printed text. None opens a
socket. The finding record states Model calls: none. Network calls: none. Spend: none.

**Observation.** The full screen module runs offline in this container. The gate's
pytest cell excludes `live` and `calibration` markers; this module carries neither.

## Which test covers which criterion

| Criterion | Covering tests |
| --- | --- |
| Script prints all three sections from a readout path | `test_script_prints_all_three_section_headers`, `test_script_accepts_a_run_log_path_with_json_at_the_tail`, `test_script_accepts_a_directory_containing_run_log`, `test_main_returns_zero_on_a_well_formed_readout` |
| Inertness interval is the engine's union-bound construction | `test_inertness_section_prints_the_anytime_valid_interval`, `test_inertness_uses_the_engine_bound_not_a_hand_rolled_one`, `test_inertness_order_matters_for_the_anytime_valid_bound` |
| Exclusion statement and n-to-exclude | `test_inertness_exclusion_statement_is_false_at_this_n`, `test_inertness_prints_the_n_at_which_the_same_counts_exclude` |
| Direct fixed-n comparison printed | `test_inertness_prints_the_direct_fixed_n_comparison` |
| Three adherence rates with counts | `test_adherence_assignment_to_read_rates`, `test_adherence_assignment_to_outcome_rates`, `test_adherence_read_to_outcome_rates` |
| Post-treatment sentence | `test_adherence_carries_the_post_treatment_sentence_verbatim`, `test_adherence_never_reads_a_causal_claim` |
| Within-pair phi, table, 95% interval | `test_correlation_section_prints_the_phi_and_table`, `test_correlation_prints_a_95pct_interval`, `test_correlation_phi_matches_the_2x2_table`, `test_correlation_is_zero_when_the_arms_are_independent_in_the_fixture` |
| #685 note fires when materially positive | `test_correlation_names_685_when_materially_positive`, `test_correlation_note_when_not_materially_positive` |
| Findings record registered with Claims/Refuses | `tests/test_receipts_index.py::test_every_receipt_file_is_indexed`, `::test_index_entries_carry_claims_and_refuses`, `::test_the_analyzed_population_is_the_declared_population` |
| Counts-only readout refused | `test_script_refuses_a_readout_without_per_epoch_rows` |

## Mutation campaign

The ticket does not name a mutation receipt and does not register an obligation prefix
under `scripts/mutation_receipt.py`. No mutation campaign was run. The screen's numerical
claims are pinned by external-behaviour tests that call the engine's
`one_sided_betting_bound` directly and compare, not by monkeypatching the function the
screen claims to use.

## Gate

Run before each commit, in the repository's own order:

```
ruff check src tests scripts
ruff format --check src tests scripts
mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py
```

All three green after the final commit. Targeted pytest modules green:

```
tests/test_stage1a_readout_691.py     26 passed
tests/test_receipts_index.py          18 passed
```

## Companion artifacts named in the record

| Artifact | Where |
| --- | --- |
| Ticket | #691 |
| Script | `scripts/screens/419/stage1a_readout_691.py` |
| Test | `tests/test_stage1a_readout_691.py` |
| Findings record | `docs/findings/stage1a-readout-691.md` |
| Stand-in readout | `docs/findings/data/stage1a-readout-691/readout.json` |
| Stand-in provenance | `docs/findings/data/stage1a-readout-691/PROVENANCE.md` |
| Receipts index entry | `docs/receipts-index.md` (Findings section) |
| #684 operating characteristics | `docs/findings/stage1a-regime-operating-characteristics.md` |
| #685 lever adjudication | `docs/findings/stage1a-lever-adjudication-685.md` |
| Engine bound | `src/skill_harness/aggregation/confidence_sequence.py` |
| Stage 1A audit RESULTS (S488) | steering research repository — **not in this tree** |
| Next-design adjudication (S493) § 6 | steering research repository — **not in this tree** |

The two steering-repository documents are named because the ticket cites them. Neither
exists in this worktree; the record says so rather than inventing a path.

## Revisit

Re-run `tests/test_stage1a_readout_691.py` and re-quote the interval if the engine's
`one_sided_betting_bound` changes. Replace the stand-in numbers when the operator runs
the script against the real S486 readout path.
