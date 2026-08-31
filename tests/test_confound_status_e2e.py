"""E2E test for confound status: runner-shaped write → VIEW → engine → status.

When confound events exist for a clause, the status must be CONFOUNDED — not a
silent understatement as UNMEASURED(inadmissible) or UNMEASURED(no_data).  The
runner's _snapshot_admissibility writes verdicts as inadmissible/confounded; the
engine's confound-counting query JOINs on admissibility_state = 'admissible',
which is mutually exclusive with the runner's write.  all_confounded_flag is
therefore always false, and derive_clause_status never returns CONFOUNDED.

This test registers that structural defect.  It asserts the end-to-end
property the falsification plan (item 6) names: when confound events exist,
the status is CONFOUNDED and not a silent understatement, and aggregation
never sees primary-tainted rows.  affected_clause_id VIEW filtering remains
an open research question (migration 0003); this ticket does not settle it.

Severity: WRONG_NUMBER
Finding: docs/findings/confound-status-silent-understatement.md
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from skill_harness.aggregation import (
    aggregate_skill,
)
from skill_harness.aggregation.report import SkillReport
from skill_harness.aggregation.status import (
    ClauseStatus,
)
from skill_harness.storage.migrations import open_runtime

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_TS = "2026-06-06T10:00:00.000Z"
_TS2 = "2026-06-06T11:00:00.000Z"
_SHA = "a" * 64
_GEN_AT = "2026-06-06T12:00:00.000Z"
_HARNESS_VER = "0.1.0a0"

SKILL_ID = "skill-confound-e2e"
RUN_ID = "run-confound-e2e"
CLAUSE_ID = "clause-confound-e2e"
AXIS = "verbosity"

N_WINS = 9
N_LOSSES = 1
N_VERDICTS = N_WINS + N_LOSSES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_confound_scenario(
    ev: sqlite3.Connection,
    rt: sqlite3.Connection,
) -> None:
    """Seed a scenario where confound events exist for a clause.

    The runner would write verdicts as inadmissible/confounded, so every
    verdict gets admissibility_state='inadmissible'.  A confound_events
    row is inserted for the same (run_id, primary_clause_id).
    """
    # Skills
    ev.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'Confounded Skill', '/path/to/skill.md', ?, ?)",
        (SKILL_ID, _SHA, _TS),
    )

    # Clauses
    ev.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag)"
        " VALUES (?, ?, 0, 0, 'Require citations.', ?, 'decrease', 1, 'none')",
        (CLAUSE_ID, SKILL_ID, AXIS),
    )

    # Metric versions
    ev.execute(
        "INSERT INTO metric_versions"
        " (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES ('verbosity', '1.0.0', ?, 1, 1, 1, ?)",
        (_SHA, _TS),
    )

    # Run (completed)
    config = json.dumps(
        {
            "run_id": RUN_ID,
            "skill_id": SKILL_ID,
            "clauses": [{"clause_id": CLAUSE_ID, "axis": AXIS}],
            "subject_model": "claude-sonnet-4-6",
            "user_message": "test confound e2e",
            "family_size": 1,
            "stopping_reasons": {},
        },
        sort_keys=True,
    )
    ev.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, ?, 'ablation', ?, ?, ?)",
        (RUN_ID, SKILL_ID, config, _TS, _TS2),
    )

    # Run progress (completed)
    rt.execute(
        "INSERT INTO run_progress"
        " (run_id, state, samples_planned, samples_collected, last_heartbeat)"
        " VALUES (?, 'completed', 10, 10, ?)",
        (RUN_ID, _TS2),
    )

    # Samples: full + ablated pairs (needed for FK)
    for i in range(N_VERDICTS):
        sa = f"sa-{i}"
        sb = f"sb-{i}"
        for sid, cond, sha in [(sa, "full", _SHA), (sb, "ablated", "b" * 64)]:
            ev.execute(
                "INSERT INTO samples"
                " (sample_id, run_id, clause_id, condition,"
                " subject_model, output_text, output_sha256, sampled_at, sample_index)"
                " VALUES (?, ?, ?, ?, 'claude-sonnet-4-6', ?, ?, ?, ?)",
                (sid, RUN_ID, CLAUSE_ID, cond, f"output-{sid}", sha, _TS, i),
            )

    # Verdicts — ALL inadmissible (runner's write for confounded clauses)
    for i in range(N_VERDICTS):
        obs = 1.0 if i < N_WINS else 0.0
        ev.execute(
            """INSERT INTO oracle_verdicts (
                verdict_id, run_id, clause_id, axis, comparison,
                sample_a_id, sample_b_id, observation, oracle_tier,
                metric_id, metric_version,
                admissibility_state, written_at
            ) VALUES (
                ?, ?, ?, ?, 'full_vs_ablated', ?, ?, ?, 1,
                'verbosity', '1.0.0', 'inadmissible', ?
            )""",
            (
                f"v-conf-{i}",
                RUN_ID,
                CLAUSE_ID,
                AXIS,
                f"sa-{i}",
                f"sb-{i}",
                obs,
                _TS,
            ),
        )

    # Confound events — for every verdict on this clause
    for i in range(N_VERDICTS):
        ev.execute(
            """INSERT INTO confound_events (
                confound_event_id, run_id, primary_clause_id, affected_clause_id,
                axis, delta, null_sigma, k_threshold, delta_kind, detected_at
            ) VALUES (?, ?, ?, ?, ?, 0.35, 0.10, 2.0, 'confound_flagged', ?)""",
            (
                f"conf-{i}",
                RUN_ID,
                CLAUSE_ID,
                CLAUSE_ID,  # same clause as primary and affected
                AXIS,
                _TS,
            ),
        )

    # Frozen case (needed for no_instantiated_frozen_cases precondition)
    failing_text = "failing-input-fc-conf"
    ev.execute(
        """INSERT INTO frozen_cases (
            frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
            oracle_source, metric_id, metric_version, implementation_hash,
            run_id, axis
        ) VALUES (?, ?, ?, ?, 'mechanical', 'verbosity', '1.0.0', ?, ?, ?)""",
        (
            "fc-conf-001",
            CLAUSE_ID,
            failing_text,
            "d" * 64,
            _SHA,
            RUN_ID,
            AXIS,
        ),
    )


def _aggregate(
    evidence_db: sqlite3.Connection, tmp_path: Path
) -> tuple[SkillReport, sqlite3.Connection]:
    rt = open_runtime(tmp_path / "runtime.db")
    _seed_confound_scenario(evidence_db, rt)
    report = aggregate_skill(
        SKILL_ID,
        evidence_conn_ro=evidence_db,
        runtime_conn=rt,
        harness_version=_HARNESS_VER,
        generated_at_utc=_GEN_AT,
    )
    return report, rt


# ---------------------------------------------------------------------------
# E2E detector: confound status
# ---------------------------------------------------------------------------


class TestConfoundStatusE2E:
    """End-to-end: confound events → CONFOUNDED status (not silent understatement).

    The runner writes verdicts as inadmissible/confounded.  The engine's
    confound-counting query JOINs on admissibility_state='admissible', which
    is mutually exclusive with the runner's write.  all_confounded_flag is
    always false, and derive_clause_status never returns CONFOUNDED.

    This test asserts the property the falsification plan (item 6) requires:
    when confound events exist, the status is CONFOUNDED and not a silent
    understatement, and aggregation never sees primary-tainted rows.
    """

    def test_primary_confounded_rows_do_not_enter_aggregation(
        self, evidence_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Primary-tainted rows stay out of the admissible VIEW and the fit.

        Pins the half of the plan property that holds on main today: the VIEW
        excludes primary_clause_id matches, so n_verdicts stays 0 and no
        observation mass enters the posterior.
        """
        rt: sqlite3.Connection | None = None
        try:
            report, rt = _aggregate(evidence_db, tmp_path)
            assert len(report.clauses) == 1
            clause = report.clauses[0]

            view_n = evidence_db.execute(
                "SELECT COUNT(*) FROM admissible_verdicts WHERE run_id = ? AND clause_id = ?",
                (RUN_ID, CLAUSE_ID),
            ).fetchone()[0]
            assert view_n == 0, (
                f"admissible_verdicts leaked {view_n} primary-tainted row(s) "
                f"for clause {CLAUSE_ID!r}; aggregation must not see them."
            )
            assert clause.n_verdicts == 0, (
                f"aggregate_skill fit saw n_verdicts={clause.n_verdicts} for "
                f"primary-confounded clause {CLAUSE_ID!r}; expected 0."
            )
            assert clause.w_observation_sum == 0.0, (
                f"aggregate_skill fit saw w_observation_sum={clause.w_observation_sum} "
                f"for primary-confounded clause {CLAUSE_ID!r}; expected 0."
            )
        finally:
            if rt is not None:
                rt.close()

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "finding: docs/findings/confound-status-silent-understatement.md "
            "(engine all_confounded_flag always false; derive_clause_status "
            "never returns CONFOUNDED; confounded work understates as "
            "UNMEASURED(inadmissible))"
        ),
    )
    def test_confound_events_produce_confounded_status(
        self, evidence_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When confound events exist for a clause, status is CONFOUNDED.

        Asserts the end-to-end property: runner-shaped writes mark verdicts
        inadmissible/confounded, confound_events rows exist, and
        aggregate_skill returns CONFOUNDED — not UNMEASURED(inadmissible)
        or UNMEASURED(no_data).
        """
        rt: sqlite3.Connection | None = None
        try:
            report, rt = _aggregate(evidence_db, tmp_path)

            assert len(report.clauses) == 1
            clause = report.clauses[0]

            # On main the engine never counts confounds (query requires
            # admissibility_state='admissible' while the runner wrote
            # 'inadmissible'), so all_confounded_flag is false and
            # derive_clause_status returns UNMEASURED(inadmissible).
            assert clause.status == ClauseStatus.CONFOUNDED, (
                f"confound events exist for clause {CLAUSE_ID!r} but status is "
                f"{clause.status!r} sub_reason={clause.sub_reason!r} "
                f"(expected CONFOUNDED). The runner writes verdicts as "
                f"inadmissible/confounded; the engine's confound query requires "
                f"admissibility_state='admissible' (mutually exclusive); "
                f"all_confounded_flag is always false; derive_clause_status "
                f"never returns CONFOUNDED."
            )
            assert clause.sub_reason is None, (
                f"CONFOUNDED status must carry no unmeasured sub_reason; "
                f"got sub_reason={clause.sub_reason!r}."
            )
        finally:
            if rt is not None:
                rt.close()
