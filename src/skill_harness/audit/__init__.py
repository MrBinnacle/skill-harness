"""Audit-only access to raw oracle_verdicts (A29 structural defense).

The admissible_verdicts SQL VIEW (migrations/evidence/0003) is the canonical
aggregation surface. Raw oracle_verdicts access — which can return rows that
must NOT enter aggregation (inadmissible or confounded) — is permitted ONLY
in this directory. The A.4 CI grep ban whitelists src/skill_harness/audit/
for raw `oracle_verdicts` SELECT references; any reference outside this
directory fails CI.

Use audit_all_verdicts() for cross-reference checks (skill audit, D7),
provenance walks, or test-time inspection. NEVER for aggregation.
"""

from __future__ import annotations

import sqlite3
from typing import Any

# ---------------------------------------------------------------------------
# Audit functions (raw oracle_verdicts access — permitted only in this module)
# ---------------------------------------------------------------------------


def audit_all_verdicts(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return ALL oracle_verdict rows for a run (including inadmissible/confounded).

    Per A29: this function is the canonical home for raw oracle_verdicts access.
    The _for_audit convention is replaced by the module boundary: being in
    skill_harness.audit/ makes the intent explicit and is enforced by the A.4
    CI grep ban.

    Use for:
      - Skill audit / cross-reference checks (D7)
      - Provenance walks
      - Test-time inspection of all verdicts regardless of admissibility

    NEVER use for aggregation — use get_admissible_verdicts() in
    skill_harness.storage.repositories.evidence.oracle_verdicts instead.
    """
    cur = conn.execute(
        """
        SELECT verdict_id, run_id, clause_id, axis, comparison,
               sample_a_id, sample_b_id, observation, oracle_tier,
               metric_id, metric_version, judge_id, calibration_event_id,
               position_swap_agreement, admissibility_state, inadmissibility_reason, written_at
        FROM oracle_verdicts WHERE run_id = ? ORDER BY written_at
        """,
        (run_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def get_verdict_by_id(conn: sqlite3.Connection, verdict_id: str) -> dict[str, Any] | None:
    """Return the oracle_verdict row as a dict, or None if not found.

    Moved from oracle_verdicts.py (A.4 audit-module finalization per A29).
    SELECTs from raw oracle_verdicts — belongs in audit/ per the CI grep ban.
    """
    cur = conn.execute(
        """
        SELECT verdict_id, run_id, clause_id, axis, comparison,
               sample_a_id, sample_b_id, observation, oracle_tier,
               metric_id, metric_version, judge_id, calibration_event_id,
               position_swap_agreement, admissibility_state, inadmissibility_reason, written_at
        FROM oracle_verdicts WHERE verdict_id = ?
        """,
        (verdict_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_verdicts_for_clause(conn: sqlite3.Connection, clause_id: str) -> list[dict[str, Any]]:
    """Return all verdicts for a clause, ordered by written_at.

    Moved from oracle_verdicts.py (A.4 audit-module finalization per A29).
    SELECTs from raw oracle_verdicts — belongs in audit/ per the CI grep ban.
    """
    cur = conn.execute(
        """
        SELECT verdict_id, run_id, clause_id, axis, comparison,
               sample_a_id, sample_b_id, observation, oracle_tier,
               metric_id, metric_version, judge_id, calibration_event_id,
               position_swap_agreement, admissibility_state, inadmissibility_reason, written_at
        FROM oracle_verdicts WHERE clause_id = ? ORDER BY written_at
        """,
        (clause_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_verdicts_by_admissibility(
    conn: sqlite3.Connection, admissibility_state: str
) -> list[dict[str, Any]]:
    """Return all verdicts with a given admissibility_state.

    Moved from oracle_verdicts.py (A.4 audit-module finalization per A29).
    SELECTs from raw oracle_verdicts — belongs in audit/ per the CI grep ban.
    """
    cur = conn.execute(
        """
        SELECT verdict_id, run_id, clause_id, axis, comparison,
               sample_a_id, sample_b_id, observation, oracle_tier,
               metric_id, metric_version, judge_id, calibration_event_id,
               position_swap_agreement, admissibility_state, inadmissibility_reason, written_at
        FROM oracle_verdicts WHERE admissibility_state = ? ORDER BY written_at
        """,
        (admissibility_state,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
