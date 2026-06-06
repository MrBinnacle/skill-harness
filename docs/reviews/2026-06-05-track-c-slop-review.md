# Track C ai-slop-sentinel review (2026-06-05)

**Reviewer**: ai-slop-sentinel via general-purpose subagent
**Diff base**: `64896c5` (Track C dispatch brief, pre-Track-C code state)
**Track C tip**: `19d9f79` (after C.4 ship)
**Scope reviewed**: all of `src/skill_harness/oracles/`, migration `0200`, CalibrationEventWrite extension, calibrate CLI, all Track C tests

## Summary

**STATUS: 15_FINDINGS_FOUND · BLOCKERS: 0 · MAJORS: 7 · MINORS: 6 · OBSERVATIONS: 2**

Reviewer's verdict: *"Track C is substantially clean on the high-stakes axes (no migration UPDATE/DELETE, no `errors='replace'`-style silent data corruption, no rationale-as-signal, append-only invariant respected). The κ formula and observed-marginals discipline are correct. The injection regex matches A38 verbatim. The migration adds columns with DEFAULT NULL and relies (correctly per CLAUDE.md doc) on the whole-row triggers. The 9-cell position-swap table is well-structured."*

**Disposition**: All 15 findings dispositioned as `FIX-NEXT-TRACK` (12), `DEFER-V0.2` (2), or `ACCEPT` (1) — **zero FIX-NOW**. Track C ships SLOP-CLEAN per the rubric. Track C MAJORs are quality-of-implementation issues (CLI ergonomics, test discipline truth-claim, deployment-shape) that do not corrupt evidence or violate load-bearing invariants. Contrast Track B (3 FIX-NOW for silent data corruption + Coverage-metric corruption).

## Findings clusters

### CLI ergonomics (TC-SLOP-001, 002, 012)

| ID | Severity | Disposition | One-line |
|---|---|---|---|
| TC-SLOP-001 | MAJOR | FIX-NEXT-TRACK | `unittest.mock.MagicMock()` imported in production CLI dry-run path (`cli/main.py:262-274`) |
| TC-SLOP-002 | MAJOR | FIX-NEXT-TRACK | `JudgeClient()` eagerly instantiated even on dry-run; breaks without `ANTHROPIC_API_KEY` (`cli/main.py:246`) |
| TC-SLOP-012 | MAJOR | FIX-NEXT-TRACK | CLI integration test patches the SUT (`tests/test_calibrate_cli.py:61-113`); the better test in `test_calibrate_dry_run_default.py` does this correctly without mocking |

TC-SLOP-001 + TC-SLOP-002 interact: dry-run promises "no API calls" but eagerly constructs `anthropic.Anthropic()` which requires `ANTHROPIC_API_KEY`. Fix shape: make `evidence_conn`/`runtime_conn` optional in `calibrate()`, move `JudgeClient()` inside `if execute:` branch, delete `tests/test_calibrate_cli.py` (duplicates `test_calibrate_dry_run_default.py` coverage with worse discipline).

### Test discipline truth-claim (TC-SLOP-004, 005, 006, 010, 011, 013)

| ID | Severity | Disposition | One-line |
|---|---|---|---|
| TC-SLOP-004 | MINOR | FIX-NEXT-TRACK | CORPUS `expected` column silently ignored (`_expected` underscore prefix); `3/9` row arithmetically wrong |
| TC-SLOP-005 | MAJOR | FIX-NEXT-TRACK | `test_beta_1_positive_when_longer_wins` body only asserts `isinstance(beta_1, float)` — vacuous |
| TC-SLOP-006 | MAJOR | FIX-NEXT-TRACK | `test_calibrate_n_100_writes_calibrated_with_a37_fields` guards assertions with `if result.state in (...)` — silent pass when premise fails |
| TC-SLOP-010 | MINOR | DEFER-V0.2 | Module-level `_REGISTRY` mutation in tests without autouse cleanup fixture |
| TC-SLOP-011 | MINOR | FIX-NEXT-TRACK | `test_structure_score_one_heading_one_break` weakens from `score == 2/6` to `score > 0.0` with hedging comment |
| TC-SLOP-013 | OBSERVATION | DEFER-V0.2 | `pytest.raises(Exception)` instead of `pydantic.ValidationError` (test_cost_projection.py, test_registry.py) |

Pattern: tests that promise more than they verify. Track A SLOP-CLEAN caught similar patterns (TA-SLOP-003). Discipline: test names + docstrings must be falsifiable by the test body.

### Structural / deployment-shape (TC-SLOP-003, 008, 009, 015)

| ID | Severity | Disposition | One-line |
|---|---|---|---|
| TC-SLOP-003 | MAJOR | FIX-NEXT-TRACK | Production `hedge_index.py` reads wordlist from `tests/oracles/tier1/fixtures/` — breaks wheel install |
| TC-SLOP-008 | MAJOR | FIX-NEXT-TRACK | `command.py:432-439` silently skips length regression if `isinstance(v, _JudgeVerdict)` filter loses any verdict — TB-SLOP-010 echo (theoretical in v0.1) |
| TC-SLOP-009 | MINOR | FIX-NEXT-TRACK | `_PARA_BREAK_PATTERN = r"\n\n"` won't match CRLF-encoded text (`structure_score.py:40`) — Windows blind spot per `windows-claude-code-env` skill |
| TC-SLOP-015 | MINOR | FIX-NEXT-TRACK | `hedge_index` docstring says "count remaining words" but implementation counts ORIGINAL words — doc/code drift |

TC-SLOP-003 fix shape per reviewer: move `hedge_wordlist.json` to `src/skill_harness/oracles/tier1/data/`, use `importlib.resources.files()`, add to `pyproject.toml` package-data manifest.

TC-SLOP-008 mirrors Track B TB-SLOP-010 (silent partial-failure) but theoretical: in production the real `JudgeClient` always returns concrete `JudgeVerdict`. The `_JudgeProtocol` was introduced to avoid circular imports — a future judge implementation returning protocol-compatible-but-different-type silently loses length regression. Fix shape: tighten `_JudgeProtocol` to require `.length_a/.length_b/.raw_observation`, drop the isinstance filter.

### Naming / fixture (TC-SLOP-007, 014)

| ID | Severity | Disposition | One-line |
|---|---|---|---|
| TC-SLOP-007 | MINOR | FIX-NEXT-TRACK | `CostProjection.t_in_cached` field name contradicts its meaning (the field IS the uncached unique-tail tokens) |
| TC-SLOP-014 | OBSERVATION | ACCEPT | `tests/oracles/tier2/fixtures/injection_negative.txt` line 15 borderline-confusing if regex loosens later |

## Comparison to prior reviews

| Review | Findings | BLOCKERs | MAJORs | FIX-NOW applied | Pattern |
|---|---|---|---|---|---|
| Track A (`a4f3b29`) | 4 | 0 | 4 | 4 | All storage-layer concerns; applied as SLOP-CLEAN commit |
| Track B (`720efc0`) | 12 | 0 | 3 | 4 (3 + 1 free fold-in) | Silent data corruption + Coverage corruption + dead helpers; cleanup commit |
| Track C (this review) | 15 | 0 | 7 | 0 | Quality-of-implementation only; no SLOP-CLEAN cleanup commit needed |

Track C's review density (15 vs A's 4 and B's 12) is higher because Track C has ~3-4× the surface area of either prior track (+270 tests; ~25 new modules; new package + 3 sub-packages + migration). Severity profile is shallower — no load-bearing invariant violations.

## FIX-NEXT-TRACK queue

The 12 FIX-NEXT-TRACK findings + 2 DEFER-V0.2 + 1 ACCEPT compose into a future Track C housekeeping commit OR roll into Track E read-models work (which already inherits TB-SLOP-002 + TB-SLOP-006 from Track B). Recommended batch:
- **Pre-Track-D housekeeping** (optional): TC-SLOP-001, 002, 003, 012 — the CLI/packaging issues that affect first-user-experience.
- **Track E batch**: TC-SLOP-004, 005, 006, 008, 011 — test discipline + the silent-skip in length regression.
- **Polish batch (deferred)**: TC-SLOP-007, 009, 010, 013, 014, 015 — naming, CRLF, registry pollution, exception specificity, fixture clarity, docstring drift.

## Cross-reference

- Track B SLOP-CLEAN (`720efc0`) — sibling precedent for SLOP review + cleanup commit pattern
- Track A SLOP-CLEAN (`a4f3b29`) — original precedent
- `ai-slop-sentinel` skill — rubric authority
- `parallel-review-disposition-schema` skill — output contract
- COUNCIL_FINDINGS Appendix D — Pre-Track-C council (A31-A38) the implementation followed
