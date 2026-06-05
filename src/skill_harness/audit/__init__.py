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
