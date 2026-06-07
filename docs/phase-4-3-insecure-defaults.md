# Phase 4.3 — Insecure Defaults Sweep

**Date**: 2026-06-07
**Scope**: `src/skill_harness/` (all modules), `migrations/`, `.github/workflows/`, `pyproject.toml`
**Out of scope**: `tests/`, `docs/` (per task brief)
**Sweep method**: `insecure-defaults` skill (Trail of Bits, v1.0.0)
**PRD threat-model reference**: PRD §17a; `SECURITY.md` "Threat model (informal)"; `docs/COUNCIL_FINDINGS.md` §A23 + §A4

---

## Summary Table

| Severity  | Total | PRE-DEFERRED | NEW |
|-----------|-------|-------------|-----|
| CRITICAL  | 0     | 0           | 0   |
| HIGH      | 0     | 0           | 0   |
| MEDIUM    | 3     | 3           | 0   |
| LOW       | 2     | 2           | 0   |
| **TOTAL** | **5** | **5**       | **0** |

**v0.1 blocker count: 0**

---

## CRITICAL findings

None.

---

## HIGH findings

None.

---

## MEDIUM findings (PRE-DEFERRED, carry-forward v0.2)

### MED-1 · Filesystem-substitution boundary — whole-DB replacement not detected

- **File**: `src/skill_harness/storage/migrations.py` (open_db / apply_pending)
- **Severity**: MEDIUM
- **PRE-DEFERRED**: YES — explicitly documented at PRD §17a, `SECURITY.md` "Filesystem substitution boundary", and `docs/COUNCIL_FINDINGS.md` §A4 + §D6
- **Description**: The SHA-256 tamper-evidence ledger records migration file hashes inside the same `evidence.db` being protected. A filesystem-adjacent attacker who replaces the entire `evidence.db` file supplies both the forged data and the forged baseline simultaneously. In-process write protection (BEFORE UPDATE/DELETE triggers) is intact; only whole-file replacement escapes it.
- **Fix shape**: v0.2 candidate D6 `db_identity` row + cross-DB identity check (UUID generated at first open, cross-referenced on subsequent opens). Already in the deferred backlog.
- **Threat-model alignment**: v0.1 assumes filesystem integrity (local-trust, single operator). Out of v0.1 scope by explicit council decision (§D6).

---

### MED-2 · `run_is_complete` fail-open on non-sqlite3.Error exceptions

- **File**: `src/skill_harness/storage/recovery.py:118-126`
- **Severity**: MEDIUM
- **PRE-DEFERRED**: YES — this was finding S1 in the Phase 3.4 code-review-sentinel fire. The fix-brief at `docs/dispatch/phase-3-4-code-review-fix-brief.md` scoped S1 as a narrowing from `except Exception` → `except sqlite3.Error`; the fix-loop commit (`722cd2f`) resolved it in `recovery.py:54-55, 74-75` but `run_is_complete` at line 122 retains `except Exception` returning `False`. The rationale for the remaining `except Exception` at line 122 is that `run_is_complete` is a read-only precondition guard: returning `False` on any unexpected exception causes the caller (freeze precondition, evaluate-skill entry gate) to refuse to proceed — i.e., it fails towards refusal, not towards permitting. However the broad except catches non-DB errors (e.g., `MemoryError`, `KeyboardInterrupt`) which could mask real failures.
- **Fix shape**: Narrow to `except sqlite3.Error`; re-raise anything else. This tightens the fail-closed shape without changing behavior on normal DB errors.
- **Threat-model alignment**: Local-trust model — exploit path requires a non-DB exception at exactly this point in a single-operator tool. Low-impact but hygiene gap.

---

### MED-3 · `DAILY_CAP_HARD_CEILING_USD` bypass via env var with no audit trail

- **File**: `src/skill_harness/oracles/calibration/cost_projection.py:241`
- **Severity**: MEDIUM
- **PRE-DEFERRED**: YES — the override mechanism (`SKILL_HARNESS_DAILY_CAP_OVERRIDE=1`) is intentional per PRD §18 / A36 budget-ceiling doctrine. The env var is documented in the module docstring. However the override does not emit a structured warning or log entry, meaning a session that overrides the $100 ceiling leaves no observable audit trace in `cost_ledger`.
- **Fix shape**: Emit a `warnings.warn(f"DAILY_CAP_HARD_CEILING_USD override active; cap={requested:.2f}", stacklevel=2)` (or structured log) when the override env var is set. Does not change the override semantics.
- **Threat-model alignment**: Local-trust; the operator who sets the env var is the same operator running the tool. Low-impact but the cost ledger should be authoritative.

---

## LOW findings (PRE-DEFERRED, carry-forward v0.2)

### LOW-1 · `run_is_complete` broad `except Exception` → False (aggregation gate)

- **File**: `src/skill_harness/storage/recovery.py:122`
- Already described in MED-2 above; listed separately here because the aggregate-entry-gate use (evaluate-skill refusing when `run_is_complete` returns `False`) is a distinct code path from the freeze precondition path. Same fix shape.

### LOW-2 · `except Exception` swallowing in `_score_primary_axis` returns 0.0

- **File**: `src/skill_harness/ablation/runner.py:1206`
- **Severity**: LOW
- **PRE-DEFERRED**: YES — the broad-except-returns-zero pattern was a deliberate design choice to prevent a scorer crash from crashing the whole run. The caller (`_run_clause`) already gates on `_is_tier1_measurable`, and a 0.0 score means the Full-minus-Ablated delta is zero → `observation = 0.5` (Tie), which becomes inadmissible if it causes confound flagging. The observation goes to the posterior either way; it does not silently escalate to PASSED.
- **Fix shape**: v0.2: catch `Exception` but log the scorer name + error via structured logging before returning 0.0, so scorer bugs surface in the audit trail rather than being invisible.
- **Threat-model alignment**: Impact is score-noise (inadmissible ties), not security escalation. Acceptable for v0.1.

---

## Verified-SAFE patterns (not findings)

The following patterns were inspected and confirmed fail-secure or explicitly designed:

| Pattern | Location | Disposition |
|---|---|---|
| `anthropic.Anthropic()` (no explicit key) | `subject.py:179`, `judge.py:182` | SDK reads `ANTHROPIC_API_KEY` from env; raises `anthropic.AuthenticationError` if absent — fail-secure (app crashes, not runs with empty key). CLI pre-flight at `main.py:744` additionally guards the execute path. |
| `open_db(synchronous="NORMAL")` default | `migrations.py:218` | NORMAL is only the parameter default; `open_evidence()` always passes `synchronous="FULL"` explicitly. Whitelist validation at line 239 prevents `synchronous="OFF"`. Fail-secure. |
| `DAILY_CAP_OVERRIDE_ENV` ceiling check | `cost_projection.py:241` | Raises `ValueError` unless override env var is set. Not a fallback secret — caller gets an error, not a permissive default. |
| `ANTHROPIC_API_KEY` env check | `cli/main.py:744-748` | Empty string → `ClickException` before any DB write. No hardcoded fallback. Fail-secure. |
| `sqlite3.connect()` in production | `migrations.py:243` only | The one sanctioned call inside `open_db()`. All other callers route through `open_db()`. CI grep ban enforced by pre-commit hook (`PRD §17a`). |
| DB path defaults (`./evidence.db`, `./runtime.db`) | `cli/main.py:82-93` | Operator-controlled paths; no security implication. CWD-relative paths are documented behavior. |
| `except BaseException` in transaction / context managers | `transaction.py:43`, `context.py:45`, `migrations.py:261,274` | All are ROLLBACK / connection-close paths that re-raise — correct use of `BaseException` for cleanup handlers. |
| `except Exception` in dual_write | `dual_write.py:94,131,172` | Evidence-first pattern: evidence commit already succeeded; runtime failure emits structured `dual_write_partial` log and does not re-raise (by design, reconciler-eligible). Not a fail-open — the audit row is already written. |
| `.github/workflows/ci.yml` | CI | `permissions: contents: read` (least-privilege); no secrets used in test job (no `ANTHROPIC_API_KEY` needed for `not live` tests). CodeQL enabled. No `pull_request_target` workflow. |
| Pydantic models | `storage/models.py` | `strict=True, extra='forbid', frozen=True` on all write models. NUL/control-char validation on all text fields. Size caps enforced. |

---

## v0.1 blocker count: **0**

Zero unaddressed CRITICAL or HIGH findings. All MEDIUM and LOW items are PRE-DEFERRED per existing council decisions (§A4, §D6, Phase 3.4 S1 partial, §A12 budget doctrine) or hygiene carry-forwards.

---

## Carry-forwards for v0.2

| ID    | Location | Description | v0.2 action |
|-------|----------|-------------|-------------|
| MED-1 | `storage/migrations.py` | Whole-DB filesystem substitution not detected | D6 `db_identity` row + cross-DB identity check |
| MED-2 | `storage/recovery.py:122` | `run_is_complete` broad `except Exception` returns `False` | Narrow to `except sqlite3.Error`; re-raise other exceptions |
| MED-3 | `cost_projection.py:241` | `DAILY_CAP_OVERRIDE_ENV` bypass leaves no audit trace | Add `warnings.warn` when override is active |
| LOW-2 | `ablation/runner.py:1206` | `_score_primary_axis` swallows scorer exceptions silently | Log scorer error via structured logging before returning 0.0 |
