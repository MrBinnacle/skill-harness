# #500 — state the current Path B facts in the verdict docstrings

## What was wrong

`src/skill_harness/aggregation/verdict.py` stated two things about Path B
(paired Full-vs-Null) that no longer describe the program:

- the module docstring (Path B paragraph) said Path B "Has NEVER fired to
  date" and that the mapping was "unexercised on live paired data";
- `paired_verdict()`'s own docstring repeated "Path B has never fired to
  date".

A sized paired run landed on 2026-09-03
(`docs/sers/receipts/gitpull-paired-n32-2026-09-03-sized.json`, RAT-0001,
git-pull-rebase-trap), so live paired data now exists. Its verdict is
CANT_TELL_YET: both arms passed all 32 epochs, the hazard was never met, and
the verdict was hand-encoded under the #403 hazard-not-met ruling — it came
through neither `paired_verdict` nor the matched Gate-2 path. `paired_verdict`
still has no production caller under `src/`.

The literal sentence "Path B has NEVER fired" was true in the narrow sense
(the function has no caller), but paired with "unexercised on live paired
data" it described a program that no longer matches reality. The correction
folded into the ticket body (S445) established this: state both facts rather
than the blanket sentence. Whether to wire `paired_verdict` to a caller or
remove it is a separate decision; this ticket only makes the docstring true.

## What I built

Rewrote the two passages in `src/skill_harness/aggregation/verdict.py`:

1. **Module docstring, Path B paragraph** — replaced "Has NEVER fired to date
   ... unexercised on live paired data" with: `paired_verdict()` has no
   production caller under `src/` (naming the verdict layer's actual live
   callers: `screen_verdict` from `cli/main.py` and `matched_gate2_verdict`
   from `cli/paired_gate2.py` and `aggregation/matched_bridge.py`); live
   paired data exists (the sized receipt, decided 2026-09-03 under RAT-0001)
   but its CANT_TELL_YET was hand-encoded under the #403 hazard-not-met
   ruling, not minted by `paired_verdict`, and came through neither Path B
   nor Path C; the mapping is coded and $0-validated but has produced no live
   KEEP or CUT. Kept the FIRING TRIGGER text verbatim. Pointed at
   `docs/sers/receipts/gitpull-paired-n32-2026-09-03-sized.json` rather than
   quoting a run count a later run would make stale.
2. **`paired_verdict()` docstring** — replaced "Path B has never fired to
   date; this mapping is prospective" with: this function has no production
   caller under `src/`; live paired data exists but its CANT_TELL_YET was
   hand-encoded under the #403 ruling rather than produced here, so the
   mapping is prospective and $0-validated only.

Also refreshed two stale prose comments in tests that cited the old docstring
wording (`tests/test_subject_ingest.py`, `tests/test_paired_halfupdate_vs_gate2_lattice.py`).
Prose only; no assertion changed, weakened, skipped, or renamed.

No source-code behaviour changed. No new receipt, registry entry, or docs/
file was added, so `docs/receipts-index.md` and `tests/test_receipts_index.py`
are unaffected.

## Acceptance criteria, each pinned by a test

All pins live in `tests/test_verdict_path_b_docstring_500.py`. Substring
checks use a whitespace-normalized, lowercased view of the docstring (the
same convention as `scripts/drift_check.py`'s `_normalized`), so a check does
not depend on where a line happens to wrap.

### AC1 — neither docstring says the path has never fired

Pinned by `test_neither_docstring_says_path_b_has_never_fired`.

- **Before:** failed. The module docstring contained "has never fired to date"
  and `paired_verdict`'s docstring contained "Path B has never fired to date".
- **After:** passes. Neither normalized docstring contains "never fired".

### AC2 — the docstrings state the current facts (no production caller; live paired data hand-encoded under #403)

Pinned by three tests:

- `test_module_docstring_states_paired_verdict_has_no_production_caller` —
  module docstring contains "no production caller". **Before:** failed
  (absent). **After:** passes.
- `test_paired_verdict_docstring_states_it_is_uncalled_and_prospective` —
  `paired_verdict` docstring states no production caller / prospective AND
  names #403. **Before:** failed (no #403). **After:** passes.
- `test_module_docstring_names_the_sized_receipt_and_403_ruling` — module
  docstring points at `docs/sers/receipts/`, names the sized receipt path,
  and names #403. **Before:** failed (absent). **After:** passes.

### AC3 — the FIRING TRIGGER text is retained

Pinned by `test_module_docstring_retains_the_firing_trigger_text` (asserts
"FIRING TRIGGER" and "p0 < 1" survive). This is a retention guard: it passed
before and after, because the change deliberately keeps the trigger. It is
not a fail-before pin; it exists so an over-edit that drops the trigger is
caught.

### AC4 — no prose run count that a later run makes stale; point at docs/sers/receipts/

Pinned by `test_no_docstring_quotes_a_run_count_that_goes_stale`
(parametrized over both docstrings): neither contains "has fired once" or
"has fired " (the "fired N times" shape that rots). The module docstring
points at `docs/sers/receipts/` and names the specific receipt (asserted in
AC2). Retention guard — passed before and after, since the new wording never
uses that shape.

### AC5 — the "no production caller" claim is mechanically true

Pinned by `test_paired_verdict_has_no_production_caller_under_src`: walks
`src/` with `ast`, finds every `Call` node naming `paired_verdict` outside
its own definition file, and asserts the list is empty. This makes the
docstring's claim checkable against the tree rather than trusted on prose.
It passed before and after (no caller existed before either), so it is a
durability guard: a future wiring fails this test and prompts a docstring
update rather than letting it drift again.

### AC6 — the cited receipt is real and carries the claimed verdict

Pinned by `test_the_cited_receipt_is_a_real_cant_tell_yet_hazard_not_met_record`:
the receipt path the docstring names exists on disk and has
`verdict == "CANT_TELL_YET"` and `value_class == "trap-discipline"`. Ties the
docstring's citation to its actual referent. Passed before and after (the
receipt pre-dates this change); a durability guard.

## Mutation campaign

The ticket names no mutation-receipt obligation, and no `--select` prefix is
given. The change is docstring text and prose comments with no behavioural
code path to mutate, so no mutation receipt applies. The one mechanical claim
added ("no production caller under `src/`") is pinned by an AST scan of the
tree (`test_paired_verdict_has_no_production_caller_under_src`), not by
monkeypatching the function it describes.

## Gate

Run before each commit, in order:

- `ruff check src tests` — All checks passed.
- `ruff format --check src tests` — 318 files already formatted.
- `mypy --strict src/ tests/` — Success: no issues found in 314 source files.
- `python scripts/drift_check.py` — DRIFT CHECK: PASS, all 17 live contracts
  hold.

Suite: the affected-area set
(`tests/test_verdict_path_b_docstring_500.py`,
`tests/test_aggregation_verdict.py`, `tests/test_freeze_verdict_paired.py`,
`tests/test_freeze_verdict_repo.py`,
`tests/test_paired_halfupdate_vs_gate2_lattice.py`,
`tests/test_subject_ingest.py`, `tests/test_receipts_index.py`,
`tests/test_ablation_report_verdict_id.py`, `tests/test_drift_check.py`,
`tests/test_structural_bans.py`) — 269 passed. The full CI suite
(`pytest -m "not live and not calibration and not assurance"`) exceeds this
container's shell timeout; CI's 25-minute cell runs it. No assertion in the
existing suite depended on the removed "never fired" sentence — the only
references were two prose comments (refreshed above).

## Out of scope

Whether `paired_verdict` should be wired to a caller or removed is a separate
decision, stated in the ticket and not taken here. No issue was changed.

## Named references

- Ticket: MrBinnacle/skill-harness #500.
- Receipt cited in the docstring:
  `docs/sers/receipts/gitpull-paired-n32-2026-09-03-sized.json` (exists,
  indexed in `docs/receipts-index.md`).
- Rulings named in the docstring: #403 (hazard-not-met), RAT-0001
  (`docs/ratifications/RAT-0001-git-pull-rebase-trap.md`, exists). The #384
  and #421 references already present in the `paired_verdict` docstring are
  unchanged.
- No new ticket, report, or doc path is introduced by this change.
