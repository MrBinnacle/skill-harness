# Track D — End-of-Track ai-slop-sentinel Review: Disposition + Fix Brief

3 fresh-context ai-slop-sentinel reviewers (opus, read-only) on landed Track D:
D.1 foundations (`render.py`/`operator.py`/migration 0300), D.2 orchestration
(`runner.py` et al.), D.3 CLI (`cli/main.py`/`open_evidence_readonly`). Findings
synthesized below; the 2 Criticals were **hub-verified by direct code read** before
this disposition.

## Verified CRITICALs (block Track E — fix before aggregation)

### C1 · D.1 length-axis contamination via marker in the wire prompt
`render.py:195-199` builds the ablated block text as `f"{marker}\n{placeholder}"` where
`marker = ABLATED_CLAUSE_MARKER.format(k=k)` (`"[CLAUSE k — ABLATED]"`); `:201` includes it
in `system_blocks`; `runner.py:635-638` sends `system_blocks` to the subject — **the model
receives the marker** (ablated side only; Full has no marker). `:212-214` rebuilds
`system_text` WITHOUT the marker, and the verbosity guard test measures `system_text` →
passes blind (probe: model sees Full=41 vs Ablated=50 tokens, +9). This is exactly the
length-axis contamination A39's matched-length operator exists to prevent; every
length/verbosity-axis delta on every run is biased. **Verified by read.**

Also (D.1 reviewer Critical-2, same root): `system_text` is not a faithful serialization of
`system_blocks` (different order/content, no marker) — persisting/auditing it as the
prompt-of-record would corrupt the audit trail.

**Fix:** remove the marker from the block text the subject receives (the placeholder alone is
the ablation per A39). If a marker is needed for inspection, return it as a SEPARATE field in
the conditions dict, never inside `system_blocks` text. Make `system_text` the faithful
concatenation of the actual block texts (so it equals the wire prompt) OR rename it to signal
it is a normalized test artifact. **Test fix (falsifying):** the verbosity/length test must
measure the concatenated `system_blocks` text (what the model sees), and assert Full vs
Ablated within the matched-length tolerance — it must go RED against the current marker-in-block code.

### C2 · D.2 resume recomputes admissibility instead of reading the persisted snapshot
`runner.py:805-808` recomputes `observation`; `:836-839` recomputes `admissibility_state` via
`_snapshot_admissibility(confounded, null_floor_met)` every iteration; `:843` skips only the
verdict WRITE for an existing comparison index, but `:859` feeds the **recomputed**
admissibility to the stopping posterior (`acc.add`). `null_floor_met`/confound state is
rebuilt within the resume pass and is order/N-dependent, so a verdict persisted `admissible`
can recompute `inadmissible` (or vice-versa) on resume — diverging the runner posterior from
the persisted audit trail. Violates CLAUDE.md Evidence model: "admissibility state recorded
at write time and **never recomputed**." The module's own docstring (`:678`, "re-build the
posterior from prior verdicts") describes the correct design; the code does not. **Verified by read.**

**Fix:** on resume, for comparison indexes that already have a persisted verdict, rebuild
`acc` by READING the persisted `observation` + `admissibility_state` from `oracle_verdicts`
(authoritative); only score / snapshot / write for genuinely-new comparisons. **Test
(falsifying):** seed a persisted verdict whose stored `admissibility_state` differs from what
a fresh recompute would yield (e.g. manipulate null-floor state), resume, assert the posterior
used the PERSISTED value — RED against current recompute-from-samples code.

## Importants (fix in the same loop)

- **I1 · D.3 `_check_daily_cap` fails OPEN on read error** (`main.py:737-738`,
  `except Exception: return`). A spend guard must fail CLOSED. Narrow the except to the
  legit "ledger absent / not yet created" case (→ 0 trailing spend, allow); any other error
  must refuse with a clear message, not silently permit a billed run. The "conservative"
  comment is false-confidence slop — fix the comment too.
- **I2 · D.2 budget gate aborts a zero-spend resume** (`runner.py:710-717`): `_check_budget`
  runs before the existing-sample short-circuit, so a near-cap resume that issues no new calls
  can `BudgetAbortedError`. Skip the pre-call gate when all three condition samples for the
  comparison are already in `existing_samples`. Test: near-cap resume with all samples present completes.
- **I3 · D.2 `samples_planned` false-gate language** (`runner.py:19, 463-468`): completion is
  stamped unconditionally after the loop, but the docstring/comment claim it's "gated on
  samples_collected == samples_planned" (fiction; the ceiling is rarely reached under early
  stop). Delete the false gate language; document completion = natural stop per clause.
- **I4 · D.3 footer over-claims** (`main.py:837-841`): prints caps but no actual spend, while
  framing implies "spent $X / cap $Y". Relabel honestly (caps only) OR compute real run spend
  from `cost_ledger`. The M4 test only asserts `cap`/`$` substrings — strengthen if you compute spend.

## Test-quality fixes (the project's recurring lesson — fold in)

- **T1 · D.1 overlapping-clause test is non-falsifying** (`test_render.py:157-189`): would pass
  against a naive `str.replace` too. Make the fixture a TRUE collision (two identical clause
  texts, or one an exact substring of another) and assert the surviving copy remains.
- **T2 · D.2 sub-tolerance QUAL-1 test near-vacuous** (`test_runner.py:889-927` +
  `test_confound.py` sibling): the length-confounded assertion is fully guarded by
  `if result.length_confounded:`. Force the sub-tolerance branch (deterministically
  out-of-tolerance clause or monkeypatch the operator) and assert `length_confounded is True`
  + 0 samples UNCONDITIONALLY.

## Minors (optional — only if cheap, do not expand scope)
- D.1 comment slop: `operator.py:29-30` (irrelevant PYTHONHASHSEED claim), `:56-65/112-117`
  (QUAL-2 over-narration). D.2: `runner.py:430-433/882` redundant `samples_collected` list-ref;
  `confound.py:323-325` re-instantiates tiktoken per call (lru_cache). D.3: `main.py:543-619`
  stream-of-consciousness comments in `_find_incomplete_run`; bare `except Exception` at
  `:366/396/508` (narrow to `sqlite3.Error`/`BootstrapError`).

## Clean (no action) — explicitly verified by the reviewers
migration 0300; operator algorithm in isolation; `stopping.py`, `subject.py`, `reconciler.py`,
`confound.detect_confounds`/`NullAccumulator`; `open_evidence_readonly` contract; D.3 safety
branches (A52/A42/API-key) all exercised by UNPATCHED tests against real state; D.3 overall = nominal.

## Method + gates
TDD: write the falsifying test FIRST for C1, C2, I1, I2, T1, T2; prove RED; then GREEN. Touches
`ablation/render.py`, `ablation/runner.py`, `cli/main.py`, and their tests. Do NOT modify
`migrations/` or the storage schema. Gates: `pytest -q -m "not live"` green · `mypy --strict`
clean · `ruff check src/ tests/` + `ruff format --check src/ tests/` clean. Invariants unchanged
(deterministic control flow; append-only; never-recompute-provenance; A39 matched-length;
A42 spend safety). New worktree off current `main` (`6771d0f`).

## Carry-forward
CF-D3-1 (skill-accurate `_find_incomplete_run`) still deferred — confirmed genuinely
conservative (over-warns, never silent fresh-start) by the D.3 reviewer.
