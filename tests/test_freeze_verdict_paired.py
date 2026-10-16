"""Paired-path (full_vs_null) freeze tests — A-prime arm-aware paired freeze branch.

Design provenance: the S86 frozen-case design council record (private research
notes; operator-ratified A-prime). Implemented under the record's pre-registered
fallback eligibility — `observation == 1.0 AND metric registered as binary` —
because the subject-path Tier-1 metrics (`subject:file_contains`,
`subject:command_succeeds`) score SANDBOX state inside the Inspect sandbox,
which no longer exists at freeze time; a freeze-time re-run of the metric on
`samples.output_text` (the model completion) is semantically invalid. The
freeze-time re-verify is pre-registered as the follow-on for graded/Tier-2
paired freezing (needs per-arm scores persisted — D22 lane).

Red tests (council record, adapted):
  1. Winning paired epoch (obs=1.0, binary metric) freezes; stored
     failing_input_text == the Null-arm sample's output_text.
  2. Winning ABLATION epoch still refuses — the branch is paired-only and the
     ablation path is byte-unchanged.
  3. r3-shaped fixture: p_win >= 0.95 + one paired frozen case → Rule 6
     PASSED → KEEP (closes the S83/r3 gap end-to-end).
  4. Frozen row inherits metric provenance and stale-flips on metric bump
     (D24 preserved on the paired path).
  5. Paired tie (obs=0.5) and paired loss (obs=0.0) are REFUSED — obs=0.5
     cannot distinguish a both-fail tie from a both-pass tie without per-arm
     scores, and freezing a both-pass tie would store a PASSING Null sample
     as a falsifying case (the live hazard the council record confirmed).
  6. Paired win under a metric NOT registered as binary is REFUSED explicitly
     (never silently frozen): under a graded metric, full > null does not
     entail the Null sample failed absolutely (referee's poisoned-artifact
     attack, hub-confirmed).
"""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from skill_harness.aggregation.status import (
    ClauseStatus,
    ClauseStatusInput,
    UnmeasuredSubReason,
    derive_clause_status,
)
from skill_harness.aggregation.verdict import KeepCutVerdict, paired_verdict
from skill_harness.storage.repositories.evidence.frozen_cases import freeze_verdict

_TS = "2026-07-27T10:00:00.000Z"
_TS_LATER = "2026-07-27T11:00:00.000Z"
_SHA = "c" * 64
_SHA_BUMPED = "d" * 64

_BINARY_METRIC = "subject:file_contains"
_GRADED_METRIC = "subject:graded_rubric"
_METRIC_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Helpers — paired (full_vs_null) evidence shapes
# ---------------------------------------------------------------------------


def _insert_skill(conn: sqlite3.Connection, skill_id: str = "sk1") -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'S', '/p', ?, ?)",
        (skill_id, _SHA, _TS),
    )


def _insert_clause(conn: sqlite3.Connection, clause_id: str = "cl1") -> None:
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag) VALUES"
        " (?, 'sk1', -1, -1, 'WHOLE-SKILL', 'outcome', 'increase', 1, 'none')",
        (clause_id,),
    )


def _insert_metric(
    conn: sqlite3.Connection,
    metric_id: str = _BINARY_METRIC,
    version: str = _METRIC_VERSION,
    implementation_hash: str = _SHA,
    audited: int = 1,
    registered_at: str = _TS,
) -> None:
    conn.execute(
        "INSERT INTO metric_versions (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at) VALUES (?, ?, ?, 1, ?, 1, ?)",
        (metric_id, version, implementation_hash, audited, registered_at),
    )


def _insert_run(conn: sqlite3.Connection, run_id: str = "run1", completed: bool = True) -> None:
    completed_at = _TS if completed else None
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, 'sk1', 'evaluate_skill', '{}', ?, ?)",
        (run_id, _TS, completed_at),
    )


def _insert_sample(
    conn: sqlite3.Connection,
    sample_id: str,
    condition: str,
    output_text: str,
    run_id: str = "run1",
    clause_id: str = "cl1",
    sample_index: int = 0,
) -> None:
    sha = hashlib.sha256(output_text.encode()).hexdigest()
    conn.execute(
        "INSERT INTO samples (sample_id, run_id, clause_id, condition,"
        " subject_model, output_text, output_sha256, sampled_at, sample_index)"
        " VALUES (?, ?, ?, ?, 'model-x', ?, ?, ?, ?)",
        (sample_id, run_id, clause_id, condition, output_text, sha, _TS, sample_index),
    )


def _insert_paired_verdict(
    conn: sqlite3.Connection,
    verdict_id: str,
    sample_a_id: str,
    sample_b_id: str,
    observation: float,
    run_id: str = "run1",
    clause_id: str = "cl1",
    metric_id: str = _BINARY_METRIC,
    metric_version: str = _METRIC_VERSION,
    admissibility_state: str = "admissible",
) -> None:
    conn.execute(
        "INSERT INTO oracle_verdicts ("
        " verdict_id, run_id, clause_id, axis, comparison,"
        " sample_a_id, sample_b_id, observation, oracle_tier,"
        " metric_id, metric_version, judge_id, calibration_event_id,"
        " position_swap_agreement, admissibility_state, written_at"
        ") VALUES (?, ?, ?, 'outcome', 'full_vs_null',"
        " ?, ?, ?, 1, ?, ?, NULL, NULL, NULL, ?, ?)",
        (
            verdict_id,
            run_id,
            clause_id,
            sample_a_id,
            sample_b_id,
            observation,
            metric_id,
            metric_version,
            admissibility_state,
            _TS,
        ),
    )


def _seed_paired_win(
    conn: sqlite3.Connection,
    verdict_id: str = "vrd-paired-win",
    metric_id: str = _BINARY_METRIC,
    null_output: str = "null-arm output (Null failed the outcome oracle)",
) -> None:
    """One winning paired epoch: full passed, null failed, obs=1.0."""
    _insert_skill(conn)
    _insert_clause(conn)
    _insert_metric(conn, metric_id=metric_id)
    _insert_run(conn, completed=True)
    _insert_sample(conn, "samp-full", condition="full", output_text="full-arm output (passed)")
    _insert_sample(conn, "samp-null", condition="null", output_text=null_output)
    _insert_paired_verdict(
        conn,
        verdict_id,
        sample_a_id="samp-full",
        sample_b_id="samp-null",
        observation=1.0,
        metric_id=metric_id,
    )


# ---------------------------------------------------------------------------
# Red test 1 — winning paired epoch freezes; stored text == Null-arm output
# ---------------------------------------------------------------------------


class TestPairedWinFreezes:
    def test_winning_paired_epoch_freezes(self, evidence_db: sqlite3.Connection) -> None:
        _seed_paired_win(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd-paired-win", oracle_source="mechanical")
        assert isinstance(fid, str)
        assert len(fid) > 0

    def test_frozen_text_is_null_arm_output(self, evidence_db: sqlite3.Connection) -> None:
        null_text = "null-arm output (Null failed the outcome oracle)"
        _seed_paired_win(evidence_db, null_output=null_text)
        fid = freeze_verdict(evidence_db, "vrd-paired-win", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT failing_input_text, failing_input_sha256 FROM frozen_cases"
            " WHERE frozen_case_id = ?",
            (fid,),
        ).fetchone()
        assert row[0] == null_text
        assert row[1] == hashlib.sha256(null_text.encode()).hexdigest()

    def test_frozen_row_keys_clause_and_axis(self, evidence_db: sqlite3.Connection) -> None:
        """The frozen row must key against the currency VIEW's (clause_id, axis)."""
        _seed_paired_win(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd-paired-win", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT clause_id, axis, verdict_id, run_id FROM frozen_cases WHERE frozen_case_id = ?",
            (fid,),
        ).fetchone()
        assert row == ("cl1", "outcome", "vrd-paired-win", "run1")


# ---------------------------------------------------------------------------
# Red test 2 — ablation path byte-unchanged: winning ablation epoch refuses
# ---------------------------------------------------------------------------


class TestAblationPathUnchanged:
    def test_winning_ablation_epoch_still_refuses(self, evidence_db: sqlite3.Connection) -> None:
        _insert_skill(evidence_db)
        _insert_clause(evidence_db)
        _insert_metric(evidence_db)
        conn = evidence_db
        conn.execute(
            "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
            " VALUES ('run-abl', 'sk1', 'ablation', '{}', ?, ?)",
            (_TS, _TS),
        )
        _insert_sample(conn, "samp-f", condition="full", output_text="full", run_id="run-abl")
        _insert_sample(conn, "samp-a", condition="ablated", output_text="abl", run_id="run-abl")
        conn.execute(
            "INSERT INTO oracle_verdicts ("
            " verdict_id, run_id, clause_id, axis, comparison,"
            " sample_a_id, sample_b_id, observation, oracle_tier,"
            " metric_id, metric_version, judge_id, calibration_event_id,"
            " position_swap_agreement, admissibility_state, written_at"
            ") VALUES ('vrd-abl-win', 'run-abl', 'cl1', 'outcome', 'full_vs_ablated',"
            " 'samp-f', 'samp-a', 1.0, 1, ?, ?, NULL, NULL, NULL, 'admissible', ?)",
            (_BINARY_METRIC, _METRIC_VERSION, _TS),
        )
        with pytest.raises(ValueError, match="observation"):
            freeze_verdict(evidence_db, "vrd-abl-win", oracle_source="mechanical")


# ---------------------------------------------------------------------------
# Red test 3 — r3-shaped end-to-end: p_win >= 0.95 + paired frozen case
#              → Rule 6 PASSED → KEEP
# ---------------------------------------------------------------------------


class TestR3ShapedKeepEndToEnd:
    def _seed_r3_shape(self, conn: sqlite3.Connection) -> None:
        """8 winning paired epochs, one audited binary metric — the r3 shape."""
        _insert_skill(conn)
        _insert_clause(conn)
        _insert_metric(conn)
        _insert_run(conn, completed=True)
        for epoch in range(8):
            _insert_sample(
                conn,
                f"samp-full-{epoch}",
                condition="full",
                output_text=f"full-{epoch}",
                sample_index=epoch,
            )
            _insert_sample(
                conn,
                f"samp-null-{epoch}",
                condition="null",
                output_text=f"null-{epoch}",
                sample_index=epoch,
            )
            _insert_paired_verdict(
                conn,
                f"vrd-{epoch}",
                sample_a_id=f"samp-full-{epoch}",
                sample_b_id=f"samp-null-{epoch}",
                observation=1.0,
            )

    def _current_frozen_count(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) FROM frozen_cases_with_currency"
            " WHERE clause_id = 'cl1' AND axis = 'outcome' AND currency_state = 'current'"
        ).fetchone()
        return int(row[0])

    def _status_input(self, current_frozen: int) -> ClauseStatusInput:
        # r3 measured posterior: Full 8/8 vs Null 0/8 → Beta(9,1), p_win 0.9899
        return ClauseStatusInput(
            axis="verbosity",
            admissible_verdict_count=8,
            total_verdict_count=8,
            confounded_verdict_count=0,
            n_verdicts=8,
            p_win_gt_threshold=0.9899,
            current_frozen_case_count=current_frozen,
            any_stale_frozen_case=False,
        )

    def test_without_freeze_gap_reproduces(self, evidence_db: sqlite3.Connection) -> None:
        """Pre-fix behavior: threshold cleared but nothing frozen → the r3 label."""
        self._seed_r3_shape(evidence_db)
        current = self._current_frozen_count(evidence_db)
        status, sub = derive_clause_status(self._status_input(current))
        assert status is ClauseStatus.UNMEASURED
        assert sub is UnmeasuredSubReason.FALSIFYING_CASE_MISSING
        assert paired_verdict(status).verdict is KeepCutVerdict.CANT_TELL_YET

    def test_freeze_then_rule6_passed_then_keep(self, evidence_db: sqlite3.Connection) -> None:
        self._seed_r3_shape(evidence_db)
        freeze_verdict(evidence_db, "vrd-0", oracle_source="mechanical")
        current = self._current_frozen_count(evidence_db)
        assert current >= 1
        status, sub = derive_clause_status(self._status_input(current))
        assert status is ClauseStatus.PASSED
        assert sub is None
        assert paired_verdict(status).verdict is KeepCutVerdict.KEEP


# ---------------------------------------------------------------------------
# Red test 4 — provenance inheritance + stale-flip on metric bump (D24)
# ---------------------------------------------------------------------------


class TestPairedProvenanceAndStaleFlip:
    def test_frozen_row_inherits_metric_provenance(self, evidence_db: sqlite3.Connection) -> None:
        _seed_paired_win(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd-paired-win", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT metric_id, metric_version, implementation_hash FROM frozen_cases"
            " WHERE frozen_case_id = ?",
            (fid,),
        ).fetchone()
        assert row == (_BINARY_METRIC, _METRIC_VERSION, _SHA)

    def test_stale_flip_on_metric_bump(self, evidence_db: sqlite3.Connection) -> None:
        _seed_paired_win(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd-paired-win", oracle_source="mechanical")
        before = evidence_db.execute(
            "SELECT currency_state FROM frozen_cases_with_currency WHERE frozen_case_id = ?",
            (fid,),
        ).fetchone()
        assert before[0] == "current"
        # Register a newer audited+valid version of the same metric → bump.
        _insert_metric(
            evidence_db,
            version="0.3.0",
            implementation_hash=_SHA_BUMPED,
            registered_at=_TS_LATER,
        )
        after = evidence_db.execute(
            "SELECT currency_state FROM frozen_cases_with_currency WHERE frozen_case_id = ?",
            (fid,),
        ).fetchone()
        assert after[0] == "stale"


# ---------------------------------------------------------------------------
# Red test 5 — paired ties and losses are refused
# ---------------------------------------------------------------------------


class TestPairedTieAndLossRefused:
    def _seed_paired(self, conn: sqlite3.Connection, verdict_id: str, observation: float) -> None:
        _insert_skill(conn)
        _insert_clause(conn)
        _insert_metric(conn)
        _insert_run(conn, completed=True)
        _insert_sample(conn, "samp-full", condition="full", output_text="full out")
        _insert_sample(conn, "samp-null", condition="null", output_text="null out")
        _insert_paired_verdict(
            conn,
            verdict_id,
            sample_a_id="samp-full",
            sample_b_id="samp-null",
            observation=observation,
        )

    def test_paired_tie_refused(self, evidence_db: sqlite3.Connection) -> None:
        """obs=0.5 covers both-fail AND both-pass ties; without per-arm scores a
        both-pass tie would freeze a PASSING Null sample — refuse the class."""
        self._seed_paired(evidence_db, "vrd-tie", observation=0.5)
        with pytest.raises(ValueError, match="paired"):
            freeze_verdict(evidence_db, "vrd-tie", oracle_source="mechanical")
        count = evidence_db.execute("SELECT COUNT(*) FROM frozen_cases").fetchone()[0]
        assert count == 0

    def test_paired_loss_refused(self, evidence_db: sqlite3.Connection) -> None:
        """obs=0.0 means the Null arm WON — sample_b is a passing sample."""
        self._seed_paired(evidence_db, "vrd-loss", observation=0.0)
        with pytest.raises(ValueError, match="paired"):
            freeze_verdict(evidence_db, "vrd-loss", oracle_source="mechanical")
        count = evidence_db.execute("SELECT COUNT(*) FROM frozen_cases").fetchone()[0]
        assert count == 0


# ---------------------------------------------------------------------------
# Red test 6 — non-binary metric: explicit refusal, never silent
# ---------------------------------------------------------------------------


class TestNonBinaryMetricRefused:
    def test_graded_metric_paired_win_refused(self, evidence_db: sqlite3.Connection) -> None:
        """Under a graded metric, full > null does NOT entail the Null sample
        failed absolutely (e.g. full=0.8 > null=0.6) — freezing would mint a
        poisoned artifact. Must refuse explicitly."""
        _seed_paired_win(evidence_db, verdict_id="vrd-graded", metric_id=_GRADED_METRIC)
        with pytest.raises(ValueError, match="binary"):
            freeze_verdict(evidence_db, "vrd-graded", oracle_source="mechanical")
        count = evidence_db.execute("SELECT COUNT(*) FROM frozen_cases").fetchone()[0]
        assert count == 0
