"""Tests for the screen-run supersession path (migration 0900).

A supersession appends a new row carrying corrected admissibility and a pointer
to the row it replaces. The superseded row is never touched. derive_p0_by_skill
and select_stale_pin_skills exclude rows that have been superseded.

See issue #402 and docs/findings/d4-prompt-leak-into-null-arm.md for the problem
this mechanism solves: four disposition-table rows cannot be re-dispositioned
because screen_runs has no supersession path.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from skill_harness.storage.migrations import open_evidence
from skill_harness.storage.repositories.evidence.screens import (
    SupersededScreenRunError,
    derive_p0_by_skill,
    get_screen_run_by_id,
    select_stale_pin_skills,
    supersede_screen_run,
)
from skill_harness.subject.ingest import ParsedEvalLog, ParsedSample
from skill_harness.subject.screen_backfill import supersede_d4_screen_runs
from skill_harness.subject.screen_ingest import write_screen_evidence

PIN_FP = "fp-deadbeef"
FRESH_PIN = "fp-fresh-aaaa"


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_evidence(tmp_path / "evidence.db")
    yield connection
    connection.close()


def make_null_sample(
    epoch: int, score: float, *, skill_name: str = "some-skill", fingerprint: str | None = PIN_FP
) -> ParsedSample:
    return ParsedSample(
        condition="null",
        skill_name=skill_name,
        epoch=epoch,
        scorer_name="command_succeeds",
        score_value=score,
        invoked_skill=False,
        output_text=f"null-output-{epoch}",
        subject_model="anthropic/claude-sonnet-5",
        harness_pin_json=None,
        harness_pin_fingerprint=fingerprint,
        input_tokens=100,
        cache_read_input_tokens=50,
        cache_creation_input_tokens=25,
        output_tokens=10,
        usd=None,
    )


def make_screen_log(
    *scores: float,
    skill_name: str = "some-skill",
    task_id: str = "task-null-1",
    fingerprint: str | None = PIN_FP,
) -> ParsedEvalLog:
    samples = tuple(
        make_null_sample(i, s, skill_name=skill_name, fingerprint=fingerprint)
        for i, s in enumerate(scores, start=1)
    )
    return ParsedEvalLog(
        task_name=f"{skill_name}-null",
        task_id=task_id,
        created="2026-07-10T12:00:00+00:00",
        status="success",
        samples=samples,
    )


def _supersede_as_inadmissible(
    conn: sqlite3.Connection,
    original_id: str,
    *,
    reason: str = "apparatus_void: D4 prompt leak; hit=prompt; searched=prompt",
) -> str:
    original_row = get_screen_run_by_id(conn, original_id)
    assert original_row is not None
    return supersede_screen_run(
        conn,
        superseded_screen_run_id=original_id,
        reason=reason,
        admissibility_state="inadmissible",
        inadmissibility_reason=reason,
        skill_name=original_row["skill_name"],
        subject_model=original_row["subject_model"],
        harness_pin_fingerprint=original_row["harness_pin_fingerprint"],
        source_eval_task_id=original_row["source_eval_task_id"],
        source_eval_sha256=original_row["source_eval_sha256"],
        created_at=original_row["created_at"],
    )


# ---------------------------------------------------------------------------
# Criterion 1: Migration adds the supersession table; triggers unchanged
# ---------------------------------------------------------------------------


class TestCriterion1Migration:
    def test_supersession_table_exists(self, conn: sqlite3.Connection) -> None:
        """The migration adds screen_run_supersessions with the expected columns."""
        cur = conn.execute("PRAGMA table_info(screen_run_supersessions)")
        cols = {row[1] for row in cur.fetchall()}
        assert "restamp_id" in cols
        assert "superseded_screen_run_id" in cols
        assert "superseding_screen_run_id" in cols
        assert "reason" in cols
        assert "recorded_at" in cols

    def test_screen_runs_update_still_aborts(self, conn: sqlite3.Connection) -> None:
        """AC1: the existing no_update trigger on screen_runs is unchanged."""
        conn.execute(
            "INSERT INTO screen_runs "
            "(screen_run_id, skill_name, subject_model, harness_pin_fingerprint, "
            " source_eval_task_id, source_eval_sha256, admissibility_state, "
            " inadmissibility_reason, created_at, ingested_at) "
            "VALUES ('sr-ao-test', 'some-skill', 'm', NULL, 't1', 's1', "
            " 'admissible', NULL, '2026-07-10T12:00:00Z', '2026-07-10T12:00:00Z')"
        )
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation: screen_runs"):
            conn.execute(
                "UPDATE screen_runs SET admissibility_state = 'inadmissible' "
                "WHERE screen_run_id = 'sr-ao-test'"
            )

    def test_screen_runs_delete_still_aborts(self, conn: sqlite3.Connection) -> None:
        """The no_delete trigger on screen_runs is unchanged."""
        conn.execute(
            "INSERT INTO screen_runs "
            "(screen_run_id, skill_name, subject_model, harness_pin_fingerprint, "
            " source_eval_task_id, source_eval_sha256, admissibility_state, "
            " inadmissibility_reason, created_at, ingested_at) "
            "VALUES ('sr-ao-del', 'some-skill', 'm', NULL, 't2', 's2', "
            " 'admissible', NULL, '2026-07-10T12:00:00Z', '2026-07-10T12:00:00Z')"
        )
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation: screen_runs"):
            conn.execute("DELETE FROM screen_runs WHERE screen_run_id = 'sr-ao-del'")

    def test_supersessions_append_only(self, conn: sqlite3.Connection) -> None:
        """The new table itself is append-only."""
        conn.execute(
            "INSERT INTO screen_runs "
            "(screen_run_id, skill_name, subject_model, harness_pin_fingerprint, "
            " source_eval_task_id, source_eval_sha256, admissibility_state, "
            " inadmissibility_reason, created_at, ingested_at) "
            "VALUES ('sr-ao-parent', 'some-skill', 'm', NULL, 't3', 's3', "
            " 'admissible', NULL, '2026-07-10T12:00:00Z', '2026-07-10T12:00:00Z')"
        )
        conn.execute(
            "INSERT INTO screen_runs "
            "(screen_run_id, skill_name, subject_model, harness_pin_fingerprint, "
            " source_eval_task_id, source_eval_sha256, admissibility_state, "
            " inadmissibility_reason, created_at, ingested_at) "
            "VALUES ('sr-ao-child', 'some-skill', 'm', NULL, 't3b', 's3b', "
            " 'inadmissible', 'test', '2026-07-10T12:00:00Z', '2026-07-10T12:00:00Z')"
        )
        conn.execute(
            "INSERT INTO screen_run_supersessions "
            "(superseded_screen_run_id, superseding_screen_run_id, reason) "
            "VALUES ('sr-ao-parent', 'sr-ao-child', 'test')"
        )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="append_only_violation: screen_run_supersessions",
        ):
            conn.execute(
                "UPDATE screen_run_supersessions SET reason = 'changed' "
                "WHERE superseded_screen_run_id = 'sr-ao-parent'"
            )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="append_only_violation: screen_run_supersessions",
        ):
            conn.execute(
                "DELETE FROM screen_run_supersessions "
                "WHERE superseded_screen_run_id = 'sr-ao-parent'"
            )

    def test_supersession_fk_requires_existing_run(self, conn: sqlite3.Connection) -> None:
        """A supersession pointing at a nonexistent screen_run_id is refused by FK."""
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            conn.execute(
                "INSERT INTO screen_run_supersessions "
                "(superseded_screen_run_id, superseding_screen_run_id, reason) "
                "VALUES ('nonexistent-id', 'also-missing', 'test')"
            )


# ---------------------------------------------------------------------------
# Criterion 2: Superseding a run appends a row and leaves the original intact
# ---------------------------------------------------------------------------


class TestCriterion2SupersessionAppends:
    def test_supersede_appends_row_and_original_unchanged(self, conn: sqlite3.Connection) -> None:
        """AC2: a supersession writes a NEW screen_runs row and the old row is
        byte-identical to what it was before."""
        result = write_screen_evidence(
            parsed=make_screen_log(1.0, 1.0, 1.0, task_id="orig-task"),
            source_eval_sha256="sha-orig",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )
        original_id = result.screen_run_id
        original_row = get_screen_run_by_id(conn, original_id)
        assert original_row is not None
        original_snapshot = dict(original_row)

        new_id = _supersede_as_inadmissible(
            conn,
            original_id,
            reason="apparatus_void: D4 prompt leak; hit=prompt; searched=prompt",
        )

        after = get_screen_run_by_id(conn, original_id)
        assert after is not None
        for key, value in original_snapshot.items():
            assert after[key] == value, f"{key} changed"

        new_row = get_screen_run_by_id(conn, new_id)
        assert new_row is not None
        assert new_row["admissibility_state"] == "inadmissible"
        assert new_row["inadmissibility_reason"] is not None
        assert new_row["inadmissibility_reason"].startswith("apparatus_void:")

        supersession = conn.execute(
            "SELECT superseded_screen_run_id, superseding_screen_run_id, reason "
            "FROM screen_run_supersessions"
        ).fetchone()
        assert supersession is not None
        assert supersession[0] == original_id
        assert supersession[1] == new_id
        assert supersession[2].startswith("apparatus_void:")

    def test_supersede_copies_trials(self, conn: sqlite3.Connection) -> None:
        """The new run carries the same trials as the superseded run."""
        result = write_screen_evidence(
            parsed=make_screen_log(1.0, 0.0, 1.0, task_id="trial-copy"),
            source_eval_sha256="sha-tc",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )
        original_id = result.screen_run_id
        original_trials = conn.execute(
            "SELECT epoch, passed FROM screen_trials WHERE screen_run_id = ? ORDER BY epoch",
            (original_id,),
        ).fetchall()

        new_id = _supersede_as_inadmissible(conn, original_id)

        new_trials = conn.execute(
            "SELECT epoch, passed FROM screen_trials WHERE screen_run_id = ? ORDER BY epoch",
            (new_id,),
        ).fetchall()
        assert new_trials == original_trials

    def test_supersede_nonexistent_raises(self, conn: sqlite3.Connection) -> None:
        """AC4 (also tested directly): superseding a nonexistent run is refused."""
        with pytest.raises(SupersededScreenRunError, match="not found"):
            supersede_screen_run(
                conn,
                superseded_screen_run_id="does-not-exist",
                reason="test",
                admissibility_state="inadmissible",
                inadmissibility_reason="test",
                skill_name="some-skill",
                subject_model="m",
                harness_pin_fingerprint=None,
                source_eval_task_id="t",
                source_eval_sha256="s",
                created_at="2026-07-10T12:00:00Z",
            )

    def test_supersede_already_superseded_raises(self, conn: sqlite3.Connection) -> None:
        """A row that is already superseded cannot be superseded again."""
        result = write_screen_evidence(
            parsed=make_screen_log(1.0, task_id="already-super"),
            source_eval_sha256="sha-as",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )
        _supersede_as_inadmissible(conn, result.screen_run_id, reason="first supersession")
        original_row = get_screen_run_by_id(conn, result.screen_run_id)
        assert original_row is not None
        with pytest.raises(SupersededScreenRunError, match="already superseded"):
            supersede_screen_run(
                conn,
                superseded_screen_run_id=result.screen_run_id,
                reason="second supersession",
                admissibility_state="admissible",
                inadmissibility_reason=None,
                skill_name=original_row["skill_name"],
                subject_model=original_row["subject_model"],
                harness_pin_fingerprint=original_row["harness_pin_fingerprint"],
                source_eval_task_id=original_row["source_eval_task_id"],
                source_eval_sha256=original_row["source_eval_sha256"],
                created_at=original_row["created_at"],
            )


# ---------------------------------------------------------------------------
# Criterion 3: derive_p0_by_skill excludes superseded rows
# ---------------------------------------------------------------------------


class TestCriterion3DeriveExcludesSuperseded:
    def test_superseded_run_excluded_from_p0(self, conn: sqlite3.Connection) -> None:
        """AC3: a skill with one superseded admissible run and one superseding
        inadmissible run produces NO p0 row — not a p0 averaged over both."""
        result = write_screen_evidence(
            parsed=make_screen_log(1.0, 1.0, 1.0, task_id="p0-super-orig"),
            source_eval_sha256="sha-p0-orig",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )
        _supersede_as_inadmissible(conn, result.screen_run_id)

        rows = derive_p0_by_skill(conn)
        assert rows == []

    def test_superseded_excluded_with_fresh_pin(self, conn: sqlite3.Connection) -> None:
        """Supersession exclusion works with the fresh_pin filter too."""
        result = write_screen_evidence(
            parsed=make_screen_log(1.0, 1.0, 1.0, fingerprint=PIN_FP, task_id="p0-pin-super"),
            source_eval_sha256="sha-p0-pin",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )
        _supersede_as_inadmissible(conn, result.screen_run_id)

        rows = derive_p0_by_skill(conn, fresh_pin=PIN_FP)
        assert rows == []

    def test_superseded_not_counted_in_unfiltered_p0(self, conn: sqlite3.Connection) -> None:
        """Without fresh_pin, the superseded row still does not enter p0."""
        result = write_screen_evidence(
            parsed=make_screen_log(1.0, 1.0, 1.0, task_id="p0-unfiltered"),
            source_eval_sha256="sha-p0-unf",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )
        _supersede_as_inadmissible(conn, result.screen_run_id)

        rows = derive_p0_by_skill(conn)
        assert rows == []

    def test_stale_pin_query_excludes_superseded_rows(self, conn: sqlite3.Connection) -> None:
        """select_stale_pin_skills must not report a skill whose only stale
        admissible row has been superseded — otherwise screen verdict still
        prints a stale-pin refusal for a row that no longer enters p0."""
        result = write_screen_evidence(
            parsed=make_screen_log(1.0, 1.0, 1.0, fingerprint=PIN_FP, task_id="stale-super"),
            source_eval_sha256="sha-stale-super",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )
        assert select_stale_pin_skills(conn, FRESH_PIN)
        _supersede_as_inadmissible(conn, result.screen_run_id)
        assert select_stale_pin_skills(conn, FRESH_PIN) == []


# ---------------------------------------------------------------------------
# Criterion 4: Negative control — nonexistent screen_run_id is refused
# ---------------------------------------------------------------------------


class TestCriterion4NegativeControl:
    def test_supersede_nonexistent_id_refused(self, conn: sqlite3.Connection) -> None:
        """AC4: a supersession pointing at a nonexistent screen_run_id is refused
        rather than silently creating an orphan."""
        with pytest.raises(SupersededScreenRunError, match="not found"):
            supersede_screen_run(
                conn,
                superseded_screen_run_id="dead-beef-cafe",
                reason="apparatus_void: D4 prompt leak; hit=prompt; searched=prompt",
                admissibility_state="inadmissible",
                inadmissibility_reason=(
                    "apparatus_void: D4 prompt leak; hit=prompt; searched=prompt"
                ),
                skill_name="some-skill",
                subject_model="m",
                harness_pin_fingerprint=None,
                source_eval_task_id="t",
                source_eval_sha256="s",
                created_at="2026-07-10T12:00:00Z",
            )
        assert conn.execute("SELECT count(*) FROM screen_run_supersessions").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Criterion 5: Four disposition-table rows re-dispositioned
# ---------------------------------------------------------------------------


class TestCriterion5D4Redisposition:
    def test_supersede_d4_screen_runs_supersedes_four_disposition_rows(
        self, conn: sqlite3.Connection
    ) -> None:
        """AC5: all four disposition-table skills are re-dispositioned.

        Three D4 voids carry the #401 hit/searched format with the leak site
        named in the finding (gitpull → RELEASING.md; appendonly/bayes → prompt).
        sqlite-tie-break-red-test-trap stands on D4 and is voided on stale-pin
        ground. After re-disposition no skill remains in p0.
        """
        skills = {
            "git-pull-rebase-trap": (1.0, 1.0, 1.0),
            "append-only-evidence-design": (1.0, 1.0, 1.0),
            "bayesian-eval-discipline": (1.0, 1.0, 1.0),
            "sqlite-tie-break-red-test-trap": (1.0, 1.0, 1.0),
        }
        for skill_name, scores in skills.items():
            write_screen_evidence(
                parsed=make_screen_log(*scores, skill_name=skill_name, task_id=f"d4-{skill_name}"),
                source_eval_sha256=f"sha-d4-{skill_name}",
                admissibility_state="admissible",
                inadmissibility_reason=None,
                conn=conn,
            )

        before = {r.skill_name: r for r in derive_p0_by_skill(conn)}
        assert len(before) == 4
        for name in skills:
            assert before[name].p0 == 1.0

        superseded = supersede_d4_screen_runs(conn)
        assert len(superseded) == 4

        after = derive_p0_by_skill(conn)
        assert after == []

        total = conn.execute("SELECT count(*) FROM screen_runs").fetchone()[0]
        assert total == 8  # 4 original + 4 superseding

        by_skill_reason = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT sr.skill_name, ss.reason "
                "FROM screen_run_supersessions ss "
                "JOIN screen_runs sr ON sr.screen_run_id = ss.superseded_screen_run_id"
            ).fetchall()
        }
        assert by_skill_reason["git-pull-rebase-trap"] == (
            "apparatus_void: D4 prompt leak; hit=RELEASING.md; searched=prompt,RELEASING.md"
        )
        assert by_skill_reason["append-only-evidence-design"] == (
            "apparatus_void: D4 prompt leak; hit=prompt; searched=prompt"
        )
        assert by_skill_reason["bayesian-eval-discipline"] == (
            "apparatus_void: D4 prompt leak; hit=prompt; searched=prompt"
        )
        assert by_skill_reason["sqlite-tie-break-red-test-trap"].startswith(
            "apparatus_void: stale harness pin"
        )

        # With a fresh pin, superseded rows must not surface as stale-pin refusals.
        assert select_stale_pin_skills(conn, FRESH_PIN) == []

    def test_supersede_d4_is_idempotent(self, conn: sqlite3.Connection) -> None:
        """Calling supersede_d4_screen_runs twice does not create duplicate supersessions."""
        for skill_name in (
            "git-pull-rebase-trap",
            "append-only-evidence-design",
            "bayesian-eval-discipline",
            "sqlite-tie-break-red-test-trap",
        ):
            write_screen_evidence(
                parsed=make_screen_log(
                    1.0, 1.0, 1.0, skill_name=skill_name, task_id=f"idem-{skill_name}"
                ),
                source_eval_sha256=f"sha-idem-{skill_name}",
                admissibility_state="admissible",
                inadmissibility_reason=None,
                conn=conn,
            )
        supersede_d4_screen_runs(conn)
        first_count = conn.execute("SELECT count(*) FROM screen_run_supersessions").fetchone()[0]
        supersede_d4_screen_runs(conn)
        second_count = conn.execute("SELECT count(*) FROM screen_run_supersessions").fetchone()[0]
        assert first_count == 4
        assert first_count == second_count
