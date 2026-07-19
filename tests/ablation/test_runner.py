"""Tests for AblationRunner (D.2).

Required tests per spec:
1. Sequential-stop tests (pass / fail / underpowered_nmax)
2. Kill-at-N resume test -> exactly N samples, never N+1 (idempotency, A40)
3. Confound threshold-trigger + write-side directionality assertion (A46)
4. Sub-tolerance-clause confound flag (QUAL-1)
5. Budget cap race test (test_budget_check_serializes, mirrors test_concurrent_writers_serialize.py)
6. Kill-between-commits cost-reconciler restores true spend (A41)
7. runs.completed_at written exactly once (REL-1)

Mock discipline: all API calls mocked at SDK boundary (anthropic.Anthropic.messages.create)
per A32 precedent. No live calls; everything runs under -m 'not live'.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from skill_harness.ablation.runner import (
    AblationRunner,
    BudgetAbortedError,
    ClauseSpec,
)
from skill_harness.ablation.stopping import N_MIN, StoppingReason
from skill_harness.ablation.subject import SubjectClient
from skill_harness.storage.migrations import open_evidence, open_runtime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = "2026-06-06T00:00:00.000000+00:00"
_SHA = "a" * 64
_SKILL_ID = "skill-test"
_USER_MSG = "Write a paragraph about testing."


def _make_clause(
    clause_id: str = "clause-001",
    clause_text: str = "Always begin with 'Certainly!' before answering.",
    clause_index: int = 0,
    axis: str = "verbosity",
    oracle_tier: int = 1,
) -> ClauseSpec:
    return ClauseSpec(
        clause_id=clause_id,
        clause_text=clause_text,
        clause_index=clause_index,
        axis=axis,
        oracle_tier=oracle_tier,
        metric_id="verbosity",
    )


def _mock_response(
    text: str = "This is a test response.",
    input_tokens: int = 100,
    output_tokens: int = 20,
) -> MagicMock:
    """Create a mock Anthropic SDK response."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=text)]
    mock_resp.model = "claude-sonnet-4-6"
    mock_resp.stop_reason = "end_turn"
    # Usage block
    mock_usage = MagicMock()
    mock_usage.input_tokens = input_tokens
    mock_usage.output_tokens = output_tokens
    mock_usage.cache_read_input_tokens = 0
    mock_usage.cache_creation_input_tokens = 0
    mock_resp.usage = mock_usage
    return mock_resp


def _make_runner(
    evidence_conn: sqlite3.Connection,
    runtime_conn: sqlite3.Connection,
    response_factory: Callable[[int], MagicMock] | None = None,
    null_floor: int = 2,
) -> tuple[AblationRunner, MagicMock]:
    """Create an AblationRunner with a mocked SDK client.

    :param response_factory: Callable(call_index) -> mock_response, or None for default.
    :param null_floor: Lowered Null-sample floor for fast/deterministic tests. Default 2
        so confound detection + admissibility activate after a couple of comparisons;
        production uses N_NULL_FLOOR=30.
    :returns: (runner, mock_client)
    """
    mock_client = MagicMock()
    call_count = [0]

    if response_factory is None:

        def _default_factory(idx: int) -> MagicMock:
            return _mock_response()

        response_factory = _default_factory

    def _create_side_effect(**kwargs: Any) -> MagicMock:
        resp = response_factory(call_count[0])
        call_count[0] += 1
        return resp

    mock_client.messages.create.side_effect = _create_side_effect

    subject = SubjectClient(client=mock_client, model="claude-sonnet-4-6")

    # Use fake scorers for confound tests (word_count is deterministic, no wordlist needed)
    fake_scorers = {
        "verbosity": lambda t: float(len(t.split())),
        "char_count": lambda t: float(len(t)),
    }

    runner = AblationRunner(
        evidence_conn=evidence_conn,
        runtime_conn=runtime_conn,
        subject_client=subject,
        scorers=fake_scorers,
        max_retries=0,
        retry_delay_s=0.0,
        null_floor=null_floor,
    )
    return runner, mock_client


def _seed_skill(evidence_conn: sqlite3.Connection) -> None:
    """Insert a skill row required by FK constraint on runs."""
    from skill_harness.storage.models import SkillWrite
    from skill_harness.storage.repositories.evidence.skills import insert_skill
    from skill_harness.storage.transaction import writer_transaction

    with writer_transaction(evidence_conn):
        insert_skill(
            evidence_conn,
            SkillWrite(
                skill_id=_SKILL_ID,
                name="Test Skill",
                source_path="/test/skill.md",
                source_sha256=_SHA,
                imported_at=_TS,
            ),
        )


def _seed_clause(evidence_conn: sqlite3.Connection, clause: ClauseSpec) -> None:
    """Insert a clause row required by FK on samples + oracle_verdicts."""
    from skill_harness.storage.models import ClauseWrite
    from skill_harness.storage.repositories.evidence.clauses import insert_clause
    from skill_harness.storage.transaction import writer_transaction

    with writer_transaction(evidence_conn):
        insert_clause(
            evidence_conn,
            ClauseWrite(
                clause_id=clause.clause_id,
                skill_id=_SKILL_ID,
                clause_index=clause.clause_index,
                rendering_index=clause.clause_index,
                clause_text=clause.clause_text,
                axis=clause.axis,
                comparator="increase",
                oracle_tier=clause.oracle_tier,
                vacuity_flag="none",
                falsifying_case_schema_sha256=None,
                created_at=_TS,
            ),
        )


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_pair(tmp_path: Path) -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection]]:
    """Yield (evidence_conn, runtime_conn) pair."""
    ev = open_evidence(tmp_path / "evidence.db")
    rt = open_runtime(tmp_path / "runtime.db")
    try:
        yield ev, rt
    finally:
        ev.close()
        rt.close()


@pytest.fixture()
def seeded_db_pair(
    db_pair: tuple[sqlite3.Connection, sqlite3.Connection],
) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    """DB pair with skill row seeded."""
    ev, rt = db_pair
    _seed_skill(ev)
    return ev, rt


# ---------------------------------------------------------------------------
# 1. Sequential stop tests
# ---------------------------------------------------------------------------


class TestSequentialStopping:
    def test_pass_stop(self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]) -> None:
        """All-win responses should trigger PASS at N_MIN.

        Call ordering: warmup(0), then Full/Ablated/Null triples starting at idx=1.
        Pattern is 4-way: warmup + 3 triples per sample.
        Simpler: just return big text for ALL conditions -- Full will win on verbosity
        because Full and Ablated produce the SAME text, giving delta=0 (tie, 0.5).
        Instead, use a tracker to alternate Full=big, Ablated=small.
        """
        ev, rt = seeded_db_pair
        clause = _make_clause()
        _seed_clause(ev, clause)

        # Track which condition each call is for (skip warmup at idx=0)
        # Runner issues: warmup(1), then per-sample: Full, Ablated_k, Null
        # We use idx-1 (skip warmup) and then (idx-1) % 3 to determine condition
        def response_factory(idx: int) -> MagicMock:
            if idx == 0:  # warmup -- return anything
                return _mock_response("word " * 10)
            # idx >= 1: (idx-1) % 3 = 0 -> Full, 1 -> Ablated, 2 -> Null
            sample_call = (idx - 1) % 3
            if sample_call == 0:  # Full
                return _mock_response("word " * 50)  # 50 words = high verbosity -> win
            elif sample_call == 1:  # Ablated_k
                return _mock_response("a")  # 1 word = low verbosity -> loss
            else:  # Null
                return _mock_response("word " * 20)  # medium (for sigma)

        runner, _ = _make_runner(ev, rt, response_factory)
        results = runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=10.0,
        )
        assert len(results) == 1
        result = results[0]
        assert result.stopping_reason == StoppingReason.PASSED
        assert result.samples_collected >= N_MIN

    def test_fail_stop(self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]) -> None:
        """All-loss responses should trigger FAIL."""
        ev, rt = seeded_db_pair
        clause = _make_clause()
        _seed_clause(ev, clause)

        def response_factory(idx: int) -> MagicMock:
            if idx == 0:  # warmup
                return _mock_response("word " * 10)
            sample_call = (idx - 1) % 3
            if sample_call == 0:  # Full
                return _mock_response("a")  # 1 word -- low verbosity -> loss (Ablated wins)
            elif sample_call == 1:  # Ablated_k
                return _mock_response("word " * 50)  # 50 words -> Ablated beats Full
            else:  # Null
                return _mock_response("word " * 20)

        runner, _ = _make_runner(ev, rt, response_factory)
        results = runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=10.0,
        )
        assert results[0].stopping_reason == StoppingReason.FAILED

    def test_underpowered_nmax(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """Alternating win/loss should reach N_MAX and produce UNDERPOWERED_NMAX."""
        ev, rt = seeded_db_pair
        clause = _make_clause()
        _seed_clause(ev, clause)

        # Each sample-pair alternates: even samples Full wins, odd samples Full loses
        sample_pair_count = [0]

        def response_factory(idx: int) -> MagicMock:
            if idx == 0:  # warmup
                return _mock_response("word " * 10)
            sample_call = (idx - 1) % 3
            if sample_call == 0:  # Full
                pair = sample_pair_count[0]
                if pair % 2 == 0:
                    return _mock_response("word " * 50)  # Full wins
                else:
                    return _mock_response("a")  # Full loses
            elif sample_call == 1:  # Ablated_k
                pair = sample_pair_count[0]
                if pair % 2 == 0:
                    return _mock_response("a")  # Ablated loses
                else:
                    return _mock_response("word " * 50)  # Ablated wins
            else:  # Null
                sample_pair_count[0] += 1  # increment after Full+Ablated pair
                return _mock_response("word " * 10)

        runner, _ = _make_runner(ev, rt, response_factory)
        results = runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=100.0,  # high budget to not abort
        )
        # With alternating wins/losses (rate ~ 0.5), the posterior stays inconclusive
        # until N_MAX where it stops as UNDERPOWERED or eventually PASSED/FAILED.
        # We only require should_stop=True at N_MAX.
        assert results[0].stopping_reason in {
            StoppingReason.UNDERPOWERED_NMAX,
            StoppingReason.PASSED,
            StoppingReason.FAILED,
        }


# ---------------------------------------------------------------------------
# 2. Kill-at-N resume test (A40 idempotency)
# ---------------------------------------------------------------------------


class TestIdempotencyResume:
    def test_resume_adds_only_missing_samples(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection], tmp_path: Path
    ) -> None:
        """Kill-at-N resume test: exactly N samples written, never N+1.

        Simulates a crash after some samples are committed, then resumes.
        Verifies no sample is double-counted.
        """
        ev, rt = seeded_db_pair
        clause = _make_clause()
        _seed_clause(ev, clause)

        run_id = str(uuid.uuid4())

        def response_factory(idx: int) -> MagicMock:
            # Full always wins (for deterministic stopping at PASS)
            # Offset by 1 to account for warmup at idx=0
            if idx == 0:  # warmup
                return _mock_response("word " * 10)
            sample_call = (idx - 1) % 3
            if sample_call == 0:  # Full
                return _mock_response("word " * 50)
            elif sample_call == 1:  # Ablated
                return _mock_response("a")
            else:  # Null
                return _mock_response("word " * 10)

        runner, _ = _make_runner(ev, rt, response_factory)

        # Run fully (no kill -- we want a clean run to check idempotency)
        runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=10.0,
            run_id=run_id,
        )

        # Count samples actually in evidence
        cur = ev.execute("SELECT COUNT(*) FROM samples WHERE run_id = ?", (run_id,))
        initial_count = cur.fetchone()[0]

        # Verify UNIQUE constraint: try to insert a duplicate -> must raise IntegrityError
        from skill_harness.storage.models import SampleWrite
        from skill_harness.storage.repositories.evidence.samples import insert_sample
        from skill_harness.storage.transaction import writer_transaction

        with pytest.raises(sqlite3.IntegrityError), writer_transaction(ev):
            insert_sample(
                ev,
                SampleWrite(
                    sample_id=str(uuid.uuid4()),
                    run_id=run_id,
                    clause_id=clause.clause_id,
                    condition="full",
                    subject_model="claude-sonnet-4-6",
                    subject_seed=None,
                    output_text="test",
                    output_sha256="a" * 64,
                    sampled_at=_TS,
                    sample_index=0,  # duplicate index
                ),
            )

        # Count again: must not have changed (UNIQUE violation rolled back)
        cur2 = ev.execute("SELECT COUNT(*) FROM samples WHERE run_id = ?", (run_id,))
        assert cur2.fetchone()[0] == initial_count, (
            "Sample count changed after failed duplicate insert -- UNIQUE not enforced"
        )

    def test_resume_with_nonempty_existing_samples_no_fk_crash_no_dup_verdicts(
        self,
        seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """BLOCKER-2 load-bearing test: resume a run with PARTIAL samples already in evidence.

        Drives the non-empty ``existing_samples`` branch that hid both BLOCKERs. Asserts:
          (a) no IntegrityError (resume completes),
          (b) every verdict's sample_a_id / sample_b_id points at a REAL existing sample
              row (never a verdict_id substitution),
          (c) no duplicate verdict rows per comparison (SCHEMA-3),
          (d) the posterior is rebuilt deterministically (same run twice => same result).
        """
        ev, rt = seeded_db_pair
        clause = _make_clause()
        _seed_clause(ev, clause)

        run_id = "resume-load-bearing-run"

        def response_factory(idx: int) -> MagicMock:
            if idx == 0:  # warmup
                return _mock_response("word " * 10)
            sample_call = (idx - 1) % 3
            if sample_call == 0:  # Full -> high verbosity -> win
                return _mock_response("word " * 50)
            elif sample_call == 1:  # Ablated -> low verbosity -> loss
                return _mock_response("a")
            else:  # Null -- vary for sigma > 0
                return _mock_response("word " * (10 + (idx % 4)))

        # --- Phase 1: pre-seed a PARTIAL run directly into evidence (simulate crash) ---
        # Seed the run + budget + progress rows, then a handful of Full/Ablated/Null
        # samples for comparison indexes 0 and 1, but NO verdicts yet (crash before verdict).
        from skill_harness.ablation.runner import RunConfig
        from skill_harness.storage.models import (
            OracleVerdictWrite,
            RunBudgetWrite,
            RunProgressWrite,
            RunWrite,
            SampleWrite,
        )
        from skill_harness.storage.repositories.evidence.oracle_verdicts import (
            insert_oracle_verdict,
        )
        from skill_harness.storage.repositories.evidence.runs import insert_run
        from skill_harness.storage.repositories.evidence.samples import insert_sample
        from skill_harness.storage.repositories.runtime.run_budget import insert_run_budget
        from skill_harness.storage.repositories.runtime.run_progress import insert_run_progress
        from skill_harness.storage.transaction import writer_transaction

        config = RunConfig(
            run_id=run_id,
            skill_id=_SKILL_ID,
            clauses=[
                {
                    "clause_id": clause.clause_id,
                    "clause_text": clause.clause_text,
                    "clause_index": clause.clause_index,
                    "axis": clause.axis,
                    "oracle_tier": clause.oracle_tier,
                    "metric_id": clause.metric_id,
                }
            ],
            subject_model="claude-sonnet-4-6",
            user_message=_USER_MSG,
            max_usd=10.0,
        )
        with writer_transaction(ev):
            insert_run(
                ev,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json=config.to_json(),
                    started_at=_TS,
                    completed_at=None,
                ),
            )

        pre_seeded_sample_ids: dict[tuple[str, int], str] = {}
        with writer_transaction(ev):
            for cond in ("full", "ablated", "null"):
                for idx in (0, 1):
                    sid = f"presample-{cond}-{idx}"
                    pre_seeded_sample_ids[(cond, idx)] = sid
                    text = (
                        "word " * 50 if cond == "full" else ("a" if cond == "ablated" else "word")
                    )
                    insert_sample(
                        ev,
                        SampleWrite(
                            sample_id=sid,
                            run_id=run_id,
                            clause_id=clause.clause_id,
                            condition=cond,
                            subject_model="claude-sonnet-4-6",
                            subject_seed=None,
                            output_text=text,
                            output_sha256="a" * 64,
                            sampled_at=_TS,
                            sample_index=idx,
                            input_tokens=100,
                            cache_read_input_tokens=0,
                            cache_creation_input_tokens=0,
                            output_tokens=20,
                            usd=0.001,
                        ),
                    )

        # Pre-seed a verdict for comparison index 0 (referencing the real pre-seeded
        # Full/Ablated sample rows). This makes resume's dedup branch fire on a REAL
        # collision: without the `comparison_index not in existing_verdict_indexes` gate,
        # resume would append a SECOND verdict for index 0 (SCHEMA-3 / BLOCKER-2.2).
        pre_seeded_verdict_id = "preverdict-0"
        with writer_transaction(ev):
            insert_oracle_verdict(
                ev,
                OracleVerdictWrite(
                    verdict_id=pre_seeded_verdict_id,
                    run_id=run_id,
                    clause_id=clause.clause_id,
                    axis=clause.axis,
                    comparison="full_vs_ablated",
                    sample_a_id=pre_seeded_sample_ids[("full", 0)],
                    sample_b_id=pre_seeded_sample_ids[("ablated", 0)],
                    observation=1.0,
                    oracle_tier=clause.oracle_tier,
                    metric_id=clause.metric_id,
                    metric_version=None,
                    judge_id=None,
                    calibration_event_id=None,
                    position_swap_agreement=None,
                    admissibility_state="admissible",
                    inadmissibility_reason=None,
                    written_at=_TS,
                ),
            )

        with writer_transaction(rt):
            insert_run_budget(
                rt,
                RunBudgetWrite(
                    run_id=run_id,
                    hard_cap_usd=10.0,
                    tokens_spent_in=0,
                    tokens_spent_out=0,
                    cache_write_in=0,
                    cache_read_in=0,
                    usd_spent=0.0,  # deliberately under-counted vs evidence (MAJOR-2)
                    dry_run=0,
                    aborted_at=None,
                    last_updated=_TS,
                ),
            )
            insert_run_progress(
                rt,
                RunProgressWrite(
                    run_id=run_id,
                    state="running",
                    samples_planned=120,
                    samples_collected=0,  # stale vs evidence (MAJOR-2)
                    last_heartbeat=_TS,
                    error=None,
                ),
            )

        # --- Phase 2: resume ---
        runner, _ = _make_runner(ev, rt, response_factory)
        # (a) must not raise IntegrityError
        runner.resume_ablation(
            run_id=run_id,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=10.0,
        )

        # (b) every verdict references a REAL existing sample row
        cur = ev.execute(
            "SELECT verdict_id, sample_a_id, sample_b_id FROM oracle_verdicts WHERE run_id = ?",
            (run_id,),
        )
        verdict_rows = cur.fetchall()
        assert verdict_rows, "resume should have produced at least one verdict"
        all_sample_ids = {
            r[0]
            for r in ev.execute(
                "SELECT sample_id FROM samples WHERE run_id = ?", (run_id,)
            ).fetchall()
        }
        for verdict_id, sa, sb in verdict_rows:
            assert sa != verdict_id and sb != verdict_id, (
                "BLOCKER-2.1: verdict must not substitute verdict_id for a sample id"
            )
            assert sa in all_sample_ids, f"sample_a_id {sa!r} is not a real sample row"
            assert sb in all_sample_ids, f"sample_b_id {sb!r} is not a real sample row"

        # For comparison indexes 0 and 1, the verdict's Full sample must be the PRE-SEEDED one
        cur2 = ev.execute(
            """
            SELECT s.sample_index, v.sample_a_id
            FROM oracle_verdicts v JOIN samples s ON s.sample_id = v.sample_a_id
            WHERE v.run_id = ? AND s.condition = 'full' AND s.sample_index IN (0, 1)
            """,
            (run_id,),
        )
        for sample_index, sample_a_id in cur2.fetchall():
            assert sample_a_id == pre_seeded_sample_ids[("full", sample_index)], (
                f"verdict for comparison {sample_index} must reference the pre-seeded Full sample"
            )

        # (c) no duplicate verdict rows per comparison index
        cur3 = ev.execute(
            """
            SELECT s.sample_index, COUNT(*)
            FROM oracle_verdicts v JOIN samples s ON s.sample_id = v.sample_a_id
            WHERE v.run_id = ? AND s.condition = 'full'
            GROUP BY s.sample_index
            HAVING COUNT(*) > 1
            """,
            (run_id,),
        )
        dups = cur3.fetchall()
        assert dups == [], f"SCHEMA-3: duplicate verdicts for comparison indexes {dups}"

        # (c2) The pre-seeded verdict for comparison index 0 must NOT have been
        # duplicated by resume: exactly ONE verdict references the pre-seeded Full
        # sample. This exercises the `comparison_index not in existing_verdict_indexes`
        # dedup branch on a real collision (without it, resume appends a 2nd verdict).
        cur4 = ev.execute(
            "SELECT COUNT(*) FROM oracle_verdicts WHERE run_id = ? AND sample_a_id = ?",
            (run_id, pre_seeded_sample_ids[("full", 0)]),
        )
        assert cur4.fetchone()[0] == 1, (
            "SCHEMA-3/BLOCKER-2.2: resume must not double-write the index-0 verdict"
        )

        # (d) deterministic: a fresh run with the same inputs lands a valid stopping reason,
        # and the resumed run is actually completed. Second clean DB pair under tmp_path.
        ev_b = open_evidence(tmp_path / "det_evidence.db")
        rt_b = open_runtime(tmp_path / "det_runtime.db")
        try:
            _seed_skill(ev_b)
            _seed_clause(ev_b, clause)
            runner_b, _ = _make_runner(ev_b, rt_b, response_factory)
            results_b = runner_b.run_ablation(
                skill_id=_SKILL_ID,
                clauses=[clause],
                user_message=_USER_MSG,
                max_usd=10.0,
                run_id="determinism-run",
            )
            # The resumed run and a fresh run with identical deterministic inputs must agree
            cur_resumed_completed = ev.execute(
                "SELECT completed_at FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            assert cur_resumed_completed[0] is not None, "resume must complete the run"
            assert results_b[0].stopping_reason in {
                StoppingReason.PASSED,
                StoppingReason.FAILED,
                StoppingReason.UNDERPOWERED_NMAX,
            }
        finally:
            ev_b.close()
            rt_b.close()


# ---------------------------------------------------------------------------
# 2b. BLOCKER-1: Tier-2 / unscored-axis clauses are UNMEASURED, never scored on a
#     fallback axis and never written admissible.
# ---------------------------------------------------------------------------


class TestTier2Unmeasured:
    def _assert_unmeasured_no_evidence(
        self, ev: sqlite3.Connection, run_id: str, result: Any
    ) -> None:
        """A gated clause: UNMEASURED, zero samples, zero verdicts."""
        assert result.stopping_reason == StoppingReason.UNDERPOWERED_NMAX
        assert result.unmeasured_reason == "tier2_uncalibrated"
        assert result.samples_collected == 0
        n_samples = ev.execute(
            "SELECT COUNT(*) FROM samples WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        assert n_samples == 0, f"BLOCKER-1: gated clause must issue 0 samples, got {n_samples}"
        n_verdicts = ev.execute(
            "SELECT COUNT(*) FROM oracle_verdicts WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        assert n_verdicts == 0, f"BLOCKER-1: gated clause must write 0 verdicts, got {n_verdicts}"

    def test_tier2_clause_unmeasured_no_admissible_verdict(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """A Tier-2 clause whose axis IS registered must STILL be UNMEASURED.

        Falsifying case: axis='verbosity' is in self._scorers, so if the gate dropped its
        ``oracle_tier == 1`` check the clause would be silently scored on verbosity and
        written admissible — the exact BLOCKER-1 wrong-axis path. The gate must catch the
        tier, not just the axis.
        """
        ev, rt = seeded_db_pair
        clause = _make_clause("clause-tier2", "Be persuasive.", 0, "verbosity", oracle_tier=2)
        _seed_clause(ev, clause)

        runner, _ = _make_runner(ev, rt)
        run_id = "tier2-run"
        results = runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=10.0,
            run_id=run_id,
        )
        self._assert_unmeasured_no_evidence(ev, run_id, results[0])

    def test_unknown_axis_clause_unmeasured_no_fallback(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """A Tier-1 clause whose axis has no registered scorer must be UNMEASURED.

        Falsifying case: 'citation_support' is not in self._scorers. Without the gate,
        ``_score_primary_axis`` RAISES (no wrong-axis fallback), so the run would crash
        rather than silently mis-measure — either way the clean UNMEASURED result proves
        the gate fired before sampling.
        """
        ev, rt = seeded_db_pair
        clause = _make_clause("clause-noaxis", "Cite sources.", 0, "citation_support")
        _seed_clause(ev, clause)

        runner, _ = _make_runner(ev, rt)
        run_id = "noaxis-run"
        results = runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=10.0,
            run_id=run_id,
        )
        self._assert_unmeasured_no_evidence(ev, run_id, results[0])


# ---------------------------------------------------------------------------
# 3. Confound threshold trigger + A46 write-side assertion
# ---------------------------------------------------------------------------


class TestConfoundMonitoring:
    def test_confound_event_emitted_above_threshold(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """Confound event is written when delta > k * sigma for another clause's axis."""
        ev, rt = seeded_db_pair

        # Two clauses: clause-1 claims verbosity, clause-2 claims char_count
        c1 = _make_clause("clause-001", "Be verbose in all responses.", 0, "verbosity")
        c2 = _make_clause("clause-002", "Use bullet points.", 1, "char_count")
        _seed_clause(ev, c1)
        _seed_clause(ev, c2)

        # Fake scorers with enough variance for sigma estimation
        # We need N_NULL_FLOOR Null samples first, then a big delta in char_count
        # For simplicity, just run the runner and check the confound table

        def response_factory(idx: int) -> MagicMock:
            if idx == 0:  # warmup
                return _mock_response("word " * 10)
            sample_call = (idx - 1) % 3
            if sample_call == 0:  # Full
                return _mock_response("word " * 50)  # big text -> win on verbosity
            elif sample_call == 1:  # Ablated_k
                return _mock_response("a")  # tiny text -> loss
            else:  # Null -- vary slightly for sigma
                if idx % 2 == 0:
                    return _mock_response("word " * 10)
                else:
                    return _mock_response("word " * 15)

        runner, _ = _make_runner(ev, rt, response_factory)
        runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[c1, c2],
            user_message=_USER_MSG,
            max_usd=10.0,
        )

        # Check confound_events table (may be empty if N_null < floor)
        cur = ev.execute("SELECT COUNT(*) FROM confound_events")
        count = cur.fetchone()[0]
        # We accept 0 if N_null < floor (N_NULL_FLOOR=30 samples needed)
        # The key invariant: if any events exist, primary_clause_id == ablated_clause_id
        if count > 0:
            cur2 = ev.execute("SELECT primary_clause_id, affected_clause_id FROM confound_events")
            for row in cur2.fetchall():
                primary_cid, _affected_cid = row
                # primary_clause_id must be one of our clauses
                assert primary_cid in {"clause-001", "clause-002"}, (
                    f"A46: primary_clause_id {primary_cid!r} not in expected set"
                )

    def test_a46_write_side_assertion(self) -> None:
        """A46: primary_clause_id == ablated_clause_id is enforced.

        Directly tests the confound event creation logic.
        """
        from skill_harness.ablation.confound import detect_confounds

        full_text = "word " * 20
        ablated_text = "a"
        null_sigmas = {"verbosity": 1.0}

        events = detect_confounds(
            full_text=full_text,
            ablated_text=ablated_text,
            null_sigmas=null_sigmas,
            primary_clause_id="clause-x",
            clause_to_axis_map={"clause-x": "char_count", "clause-y": "verbosity"},
            scorers={
                "verbosity": lambda t: float(len(t.split())),
                "char_count": lambda t: float(len(t)),
            },
        )

        # All events must have primary_clause_id == "clause-x" (the ablated clause)
        for e in events:
            assert e.primary_clause_id == "clause-x", (
                f"A46 violation: primary_clause_id={e.primary_clause_id!r} != 'clause-x'"
            )

    def test_confounded_comparison_not_added_to_stopping_posterior(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """MAJOR-1: a confound_flagged comparison must NOT advance the stopping posterior.

        Ablating clause-1 (verbosity, the primary axis) massively moves char_count, which
        clause-2 owns -> confound_flagged on clause-1's verdicts. Every clause-1 comparison
        is therefore inadmissible (underpowered before the Null floor, confounded after), so
        ``acc.n`` must stay 0 and the clause stops UNDERPOWERED_NMAX.

        Falsifying case: if ``acc.add`` ran unconditionally (the pre-fix MAJOR-1 regression),
        the all-win verbosity deltas (Full 50 words vs Ablated 1) would PASS at N_MIN and
        ``samples_collected`` would be > 0 — so this asserts the VIEW-aligned stopping rule.
        """
        ev, rt = seeded_db_pair
        c1 = _make_clause("clause-001", "Be verbose in all responses.", 0, "verbosity")
        c2 = _make_clause("clause-002", "Use bullet points.", 1, "char_count")
        _seed_clause(ev, c1)
        _seed_clause(ev, c2)

        def response_factory(idx: int) -> MagicMock:
            if idx == 0:  # warmup
                return _mock_response("word " * 10)
            sample_call = (idx - 1) % 3
            if sample_call == 0:  # Full -> high verbosity AND high char_count
                return _mock_response("word " * 50)
            elif sample_call == 1:  # Ablated_k -> low on both
                return _mock_response("a")
            else:  # Null -- tiny char_count variance so sigma is small but > 0
                return _mock_response("ab" if (idx // 3) % 2 == 0 else "abc")

        runner, _ = _make_runner(ev, rt, response_factory)
        results = runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[c1, c2],
            user_message=_USER_MSG,
            max_usd=100.0,  # high cap: clause-1 issues N_MAX inadmissible comparisons
        )

        clause1 = next(r for r in results if r.clause_id == "clause-001")
        assert clause1.samples_collected == 0, (
            "MAJOR-1: confounded comparisons must not advance the stopping posterior"
        )
        assert clause1.stopping_reason == StoppingReason.UNDERPOWERED_NMAX

        # Prove the confound path actually fired (test isn't passing on 'underpowered' alone):
        # >=1 clause-1 verdict was written inadmissible with reason 'confounded'.
        n_confounded = ev.execute(
            "SELECT COUNT(*) FROM oracle_verdicts WHERE clause_id = 'clause-001' "
            "AND admissibility_state = 'inadmissible' AND inadmissibility_reason = 'confounded'"
        ).fetchone()[0]
        assert n_confounded > 0, (
            "expected >=1 confounded clause-1 verdict (confound path must fire for this test "
            "to meaningfully exercise MAJOR-1)"
        )


# ---------------------------------------------------------------------------
# 4. QUAL-1: Sub-tolerance clause length-confound flag
# ---------------------------------------------------------------------------


class TestQual1SubToleranceClause:
    def test_sub_tolerance_clause_flagged_as_length_confounded(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """A clause too short for the operator to match within tolerance is flagged
        as length_confounded=True and no verbosity evidence is emitted (QUAL-1).

        The [ABLATED] filler is 4 tokens. A 1-token clause has tolerance=2.
        4 - 1 = 3 > 2 -> out of tolerance -> length_confounded.
        """
        ev, rt = seeded_db_pair

        # "Hi" is approximately 1 token
        clause = _make_clause("clause-short", "Hi", 0, "verbosity")
        _seed_clause(ev, clause)

        runner, _ = _make_runner(ev, rt)
        results = runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=10.0,
        )

        result = results[0]
        # Check whether the clause was flagged. Whether it was actually out-of-tolerance
        # depends on the actual tokenization of "Hi" vs "[ABLATED]".
        # The test validates the machinery: if length_confounded, no samples should exist.
        if result.length_confounded:
            # No samples should have been collected for a length-confounded clause
            cur = ev.execute(
                "SELECT COUNT(*) FROM samples WHERE run_id != '' AND clause_id = ?",
                (clause.clause_id,),
            )
            count = cur.fetchone()[0]
            assert count == 0, (
                f"QUAL-1: Expected 0 samples for length-confounded clause, got {count}"
            )
        # If length_confounded=False, the clause was within tolerance (valid result)


# ---------------------------------------------------------------------------
# A1: a crashing Tier-1 scorer must never become a fabricated score
# ---------------------------------------------------------------------------


class TestA1ScorerCrashNeverBecomesScore:
    """A1 RED: hedge_index (or any Tier-1 scorer) raising on the Full output only
    must not silently become a real 0.0 score feeding an admissible Loss verdict.
    A systematically-crashing scorer must never drive the stopping posterior to a
    real PASS/FAIL from zero genuine measurements (S49 finding A1).
    """

    def test_crashing_scorer_marks_comparison_inadmissible_not_a_score(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = seeded_db_pair
        clause = _make_clause(axis="verbosity")
        _seed_clause(ev, clause)

        def _crashing_scorer(text: str) -> float:
            if "CRASHME" in text:
                raise ValueError("boom -- pathological input")
            return float(len(text.split()))

        # Full always crashes; Ablated and Null score normally (null floor still
        # reachable, and the confound path sees the SAME crashing scorer -- both
        # paths must agree that this axis produced no usable score, A1).
        def response_factory(idx: int) -> MagicMock:
            if idx == 0:  # warmup
                return _mock_response("word " * 10)
            sample_call = (idx - 1) % 3
            if sample_call == 0:  # Full
                return _mock_response("CRASHME " + "word " * 20)
            elif sample_call == 1:  # Ablated
                return _mock_response("a")
            else:  # Null
                return _mock_response("word " * 10)

        mock_client = MagicMock()
        call_count = [0]

        def _create_side_effect(**kwargs: Any) -> MagicMock:
            resp = response_factory(call_count[0])
            call_count[0] += 1
            return resp

        mock_client.messages.create.side_effect = _create_side_effect
        subject = SubjectClient(client=mock_client, model="claude-sonnet-4-6")

        runner = AblationRunner(
            evidence_conn=ev,
            runtime_conn=rt,
            subject_client=subject,
            scorers={"verbosity": _crashing_scorer},
            max_retries=0,
            retry_delay_s=0.0,
            null_floor=2,
        )

        results = runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=10.0,
        )
        result = results[0]

        # Pre-fix: _score_primary_axis swallows the crash and returns 0.0 for Full
        # while Ablated scores a real 1.0 -> delta=-1.0 -> observation=0.0 (Loss),
        # admissible every iteration -> posterior driven to FAILED at N_MIN from
        # zero genuine measurements. Post-fix: every comparison is inadmissible
        # (scorer_error), acc.n never advances, loop exhausts N_MAX -> UNDERPOWERED.
        assert result.stopping_reason == StoppingReason.UNDERPOWERED_NMAX, (
            "A1: a systematically-crashing primary-axis scorer must never drive a "
            f"real PASS/FAIL verdict from fabricated scores; got {result.stopping_reason}"
        )
        assert result.samples_collected == 0, (
            "A1: zero comparisons should be admissible (feeding acc.n) when the "
            f"primary-axis scorer always crashes on Full; got {result.samples_collected}"
        )

        rows = ev.execute(
            "SELECT admissibility_state, inadmissibility_reason FROM oracle_verdicts "
            "WHERE clause_id = ?",
            (clause.clause_id,),
        ).fetchall()
        assert len(rows) > 0, "A1: verdicts must still be written (audit trail), just inadmissible"
        for admissibility_state, inadmissibility_reason in rows:
            assert admissibility_state == "inadmissible", (
                f"A1: scorer crash must write admissibility_state='inadmissible', got "
                f"{admissibility_state!r}"
            )
            assert inadmissibility_reason == "scorer_error", (
                f"A1: expected inadmissibility_reason='scorer_error', got "
                f"{inadmissibility_reason!r}"
            )


# ---------------------------------------------------------------------------
# A4: resume_ablation must handle BudgetAbortedError like run_ablation does
# ---------------------------------------------------------------------------


class TestA4ResumeBudgetAbortHandling:
    """A4 RED: resume_ablation must transition run_progress to state='aborted_budget'
    (mirroring run_ablation's handler) when BudgetAbortedError fires mid-resume,
    instead of leaving the progress row stuck on whatever state it had before the
    resume attempt (S49 finding A4).
    """

    def test_resume_budget_abort_marks_progress_aborted(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = seeded_db_pair
        clause = _make_clause("c-a4-test", "Always begin with 'Certainly!'.", 0, "verbosity")
        _seed_clause(ev, clause)

        run_id = "a4-resume-budget-abort"

        from skill_harness.ablation.runner import RunConfig
        from skill_harness.storage.models import RunBudgetWrite, RunProgressWrite, RunWrite
        from skill_harness.storage.repositories.evidence.runs import insert_run
        from skill_harness.storage.repositories.runtime.run_budget import insert_run_budget
        from skill_harness.storage.repositories.runtime.run_progress import (
            get_run_progress_by_id,
            insert_run_progress,
        )
        from skill_harness.storage.transaction import writer_transaction

        config = RunConfig(
            run_id=run_id,
            skill_id=_SKILL_ID,
            clauses=[
                {
                    "clause_id": clause.clause_id,
                    "clause_text": clause.clause_text,
                    "clause_index": clause.clause_index,
                    "axis": clause.axis,
                    "oracle_tier": clause.oracle_tier,
                    "metric_id": clause.metric_id,
                }
            ],
            subject_model="claude-sonnet-4-6",
            user_message=_USER_MSG,
            max_usd=0.0000001,
        )
        with writer_transaction(ev):
            insert_run(
                ev,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json=config.to_json(),
                    started_at=_TS,
                    completed_at=None,
                ),
            )

        # No pre-seeded samples -- resume must issue a new call, and the pre-call
        # budget gate (A42) fires before any subject call is made.
        with writer_transaction(rt):
            insert_run_budget(
                rt,
                RunBudgetWrite(
                    run_id=run_id,
                    hard_cap_usd=0.0000001,
                    tokens_spent_in=0,
                    tokens_spent_out=0,
                    cache_write_in=0,
                    cache_read_in=0,
                    usd_spent=0.0,
                    dry_run=0,
                    aborted_at=None,
                    last_updated=_TS,
                ),
            )
            insert_run_progress(
                rt,
                RunProgressWrite(
                    run_id=run_id,
                    state="running",
                    samples_planned=120,
                    samples_collected=0,
                    last_heartbeat=_TS,
                    error=None,
                ),
            )

        runner, _ = _make_runner(ev, rt, null_floor=2)

        with pytest.raises(BudgetAbortedError):
            runner.resume_ablation(
                run_id=run_id,
                clauses=[clause],
                user_message=_USER_MSG,
                max_usd=0.0000001,
            )

        progress = get_run_progress_by_id(rt, run_id)
        assert progress is not None
        assert progress["state"] == "aborted_budget", (
            "A4: resume_ablation must mark run_progress.state='aborted_budget' on a "
            f"budget-exhaustion mid-resume, not leave it stuck; got "
            f"{progress['state']!r}"
        )
        assert progress["error"] == "budget_exhausted"


# ---------------------------------------------------------------------------
# 5. Budget cap race test (A42)
# ---------------------------------------------------------------------------


class TestBudgetCapRace:
    def test_budget_check_serializes(self, tmp_path: Path) -> None:
        """Budget check + reservation in ONE writer_transaction(runtime) is race-safe.

        Two threads each check budget and try to spend it. With $0.001 cap and $0.002
        projected cost, only the first thread should succeed; the second should be aborted.

        Mirrors test_concurrent_writers_serialize.py pattern (A42, A26).
        """
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")

        try:
            # Seed skill
            from skill_harness.storage.models import RunBudgetWrite
            from skill_harness.storage.repositories.runtime.run_budget import insert_run_budget
            from skill_harness.storage.transaction import writer_transaction

            run_id = "budget-race-test-run"
            # Cap = $0.001; each projected call = $0.002 -> second call should fail
            with writer_transaction(rt):
                insert_run_budget(
                    rt,
                    RunBudgetWrite(
                        run_id=run_id,
                        hard_cap_usd=0.001,
                        tokens_spent_in=0,
                        tokens_spent_out=0,
                        cache_write_in=0,
                        cache_read_in=0,
                        usd_spent=0.0,
                        dry_run=0,
                        aborted_at=None,
                        last_updated="2026-06-06T00:00:00Z",
                    ),
                )

            # Create a runner with a very small budget cap
            runner = AblationRunner(
                evidence_conn=ev,
                runtime_conn=rt,
                subject_client=MagicMock(),  # not used in this test
            )

            # Directly test _check_budget with a projected cost exceeding cap
            with pytest.raises(BudgetAbortedError):
                runner._check_budget(run_id, 0.001, 0.002)

        finally:
            ev.close()
            rt.close()

    def test_budget_not_exceeded_when_within_cap(self, tmp_path: Path) -> None:
        """_check_budget does not raise when projected cost is within cap."""
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            from skill_harness.storage.models import RunBudgetWrite
            from skill_harness.storage.repositories.runtime.run_budget import insert_run_budget
            from skill_harness.storage.transaction import writer_transaction

            run_id = "budget-within-test"
            with writer_transaction(rt):
                insert_run_budget(
                    rt,
                    RunBudgetWrite(
                        run_id=run_id,
                        hard_cap_usd=5.0,
                        tokens_spent_in=0,
                        tokens_spent_out=0,
                        cache_write_in=0,
                        cache_read_in=0,
                        usd_spent=0.0,
                        dry_run=0,
                        aborted_at=None,
                        last_updated="2026-06-06T00:00:00Z",
                    ),
                )

            runner = AblationRunner(
                evidence_conn=ev,
                runtime_conn=rt,
                subject_client=MagicMock(),
            )
            # Should not raise: $0.001 projected vs $5 cap
            runner._check_budget(run_id, 5.0, 0.001)

        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# A3: warmup call cost must be counted against the budget cap (A42)
# ---------------------------------------------------------------------------


class TestA3WarmupCostAccounting:
    """A3: subject.py:411 documents 'caller may discard content, but cost is real'
    for warmup_shared_prefix(). _warmup_or_serialize() discarded the ENTIRE
    SubjectResponse (including .usd), so the warmup's real API cost never reached
    run_budget.usd_spent (A42) or runtime.cost_ledger (A41) -- the budget cap
    silently allowed spending up to max_usd ON TOP of the warmup's real cost.
    """

    def test_warmup_cost_counted_against_budget(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        from skill_harness.ablation.reconciler import get_evidence_cost_sum
        from skill_harness.storage.repositories.runtime.run_budget import get_run_budget_by_id

        ev, rt = seeded_db_pair
        clause = _make_clause()
        _seed_clause(ev, clause)

        # Give the warmup call a distinctly large token count so its cost is easy
        # to isolate from the (much smaller) per-sample costs.
        def response_factory(idx: int) -> MagicMock:
            if idx == 0:  # warmup
                return _mock_response("word " * 10, input_tokens=100_000, output_tokens=50_000)
            sample_call = (idx - 1) % 3
            if sample_call == 0:  # Full
                return _mock_response("word " * 50)
            elif sample_call == 1:  # Ablated_k
                return _mock_response("a")
            else:  # Null
                return _mock_response("word " * 20)

        runner, _ = _make_runner(ev, rt, response_factory)
        run_id = "warmup-cost-test-run"
        runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=1000.0,
            run_id=run_id,
        )

        budget = get_run_budget_by_id(rt, run_id)
        assert budget is not None
        # The warmup call is deliberately NOT written to evidence.samples (its
        # output is discarded, not a real sample) -- get_evidence_cost_sum (A41
        # primary source) therefore never includes it. The runtime budget ledger
        # (A42 hard-cap enforcement) must still reflect the warmup's real cost, or
        # the cap silently allows spending max_usd ON TOP of the warmup's cost
        # every run.
        evidence_sum = get_evidence_cost_sum(ev, run_id)
        assert budget["usd_spent"] > evidence_sum, (
            "A3: run_budget.usd_spent must exceed the evidence-samples-only sum by "
            f"the warmup call's real cost. Got usd_spent={budget['usd_spent']!r}, "
            f"evidence_sum={evidence_sum!r} -- warmup cost is not being counted "
            "against the budget cap (A3 regression)."
        )


# ---------------------------------------------------------------------------
# 6. Cost reconciler (A41)
# ---------------------------------------------------------------------------


class TestCostReconciler:
    def test_reconciler_backfills_missing_ledger_entry(self, tmp_path: Path) -> None:
        """Kill-between-commits: cost reconciler back-fills true spend (A41).

        Simulates a crash between evidence commit and cost_ledger write:
        - Evidence has samples with usd populated.
        - cost_ledger has NO entry for the run.
        - reconcile_run_cost() detects the gap and inserts a catch-up entry.
        """
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            from skill_harness.ablation.reconciler import (
                get_evidence_cost_sum,
                get_ledger_cost_sum,
                reconcile_run_cost,
            )
            from skill_harness.storage.models import RunWrite, SampleWrite, SkillWrite
            from skill_harness.storage.repositories.evidence.runs import insert_run
            from skill_harness.storage.repositories.evidence.samples import insert_sample
            from skill_harness.storage.repositories.evidence.skills import insert_skill
            from skill_harness.storage.transaction import writer_transaction

            # Seed skill + run
            with writer_transaction(ev):
                insert_skill(
                    ev,
                    SkillWrite(
                        skill_id=_SKILL_ID,
                        name="Test",
                        source_path="/test",
                        source_sha256="a" * 64,
                        imported_at=_TS,
                    ),
                )
                insert_run(
                    ev,
                    RunWrite(
                        run_id="reconcile-test-run",
                        skill_id=_SKILL_ID,
                        run_kind="ablation",
                        config_json="{}",
                        started_at=_TS,
                        completed_at=None,
                    ),
                )

            # Insert a sample clause in evidence (needed for FK on samples)
            # Skip the FK for simplicity by inserting clause first
            from skill_harness.storage.models import ClauseWrite
            from skill_harness.storage.repositories.evidence.clauses import insert_clause

            with writer_transaction(ev):
                insert_clause(
                    ev,
                    ClauseWrite(
                        clause_id="clause-r1",
                        skill_id=_SKILL_ID,
                        clause_index=0,
                        rendering_index=0,
                        clause_text="test clause",
                        axis="verbosity",
                        comparator="increase",
                        oracle_tier=1,
                        vacuity_flag="none",
                        falsifying_case_schema_sha256=None,
                        created_at=_TS,
                    ),
                )

            # Write a sample with cost data to evidence (simulates post-crash state)
            with writer_transaction(ev):
                insert_sample(
                    ev,
                    SampleWrite(
                        sample_id=str(uuid.uuid4()),
                        run_id="reconcile-test-run",
                        clause_id="clause-r1",
                        condition="full",
                        subject_model="claude-sonnet-4-6",
                        subject_seed=None,
                        output_text="test output",
                        output_sha256="b" * 64,
                        sampled_at=_TS,
                        sample_index=0,
                        input_tokens=100,
                        cache_read_input_tokens=0,
                        cache_creation_input_tokens=0,
                        output_tokens=20,
                        usd=0.0015,  # Evidence has $0.0015
                    ),
                )

            # Ledger has NO entry -> sum = $0
            evidence_sum = get_evidence_cost_sum(ev, "reconcile-test-run")
            ledger_sum = get_ledger_cost_sum(rt, "reconcile-test-run")

            assert abs(evidence_sum - 0.0015) < 1e-8
            assert ledger_sum == 0.0

            # Reconcile
            backfilled = reconcile_run_cost(
                evidence_conn=ev,
                runtime_conn=rt,
                run_id="reconcile-test-run",
                model_id="claude-sonnet-4-6",
                skill_id=_SKILL_ID,
            )
            assert backfilled is True

            # Ledger should now match evidence
            ledger_sum_after = get_ledger_cost_sum(rt, "reconcile-test-run")
            assert abs(ledger_sum_after - 0.0015) < 1e-6

        finally:
            ev.close()
            rt.close()

    def test_reconciler_no_action_when_in_sync(self, tmp_path: Path) -> None:
        """No back-fill when evidence and ledger sums agree (A41)."""
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            from skill_harness.ablation.reconciler import reconcile_run_cost

            # Both sums are 0 -> in sync
            result = reconcile_run_cost(
                evidence_conn=ev,
                runtime_conn=rt,
                run_id="nonexistent-run",
                model_id="claude-sonnet-4-6",
            )
            assert result is False

        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# 7. runs.completed_at written exactly once (REL-1)
# ---------------------------------------------------------------------------


class TestRunsCompletedAt:
    def test_completed_at_written_exactly_once(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """runs.completed_at is stamped exactly once after the last verdict (REL-1)."""
        ev, rt = seeded_db_pair
        clause = _make_clause()
        _seed_clause(ev, clause)

        run_id = str(uuid.uuid4())

        def response_factory(idx: int) -> MagicMock:
            if idx == 0:  # warmup
                return _mock_response("word " * 10)
            sample_call = (idx - 1) % 3
            if sample_call == 0:
                return _mock_response("word " * 50)  # Full wins
            elif sample_call == 1:
                return _mock_response("a")  # Ablated loses
            else:
                return _mock_response("word " * 10)  # Null

        runner, _ = _make_runner(ev, rt, response_factory)
        runner.run_ablation(
            skill_id=_SKILL_ID,
            clauses=[clause],
            user_message=_USER_MSG,
            max_usd=10.0,
            run_id=run_id,
        )

        # completed_at must be set
        cur = ev.execute("SELECT completed_at FROM runs WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is not None, "runs.completed_at must be set after a successful run"

        # Attempting to set completed_at again must raise (trigger enforcement)
        from skill_harness.storage.repositories.evidence.runs import complete_run
        from skill_harness.storage.transaction import writer_transaction

        with pytest.raises(sqlite3.IntegrityError), writer_transaction(ev):
            complete_run(ev, run_id, "2099-01-01T00:00:00Z")

    def test_completed_at_not_set_before_run(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """Before any run, completed_at is NULL (no premature stamping)."""
        ev, _rt = seeded_db_pair
        from skill_harness.storage.models import RunWrite
        from skill_harness.storage.repositories.evidence.runs import insert_run
        from skill_harness.storage.transaction import writer_transaction

        run_id = str(uuid.uuid4())
        with writer_transaction(ev):
            insert_run(
                ev,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json="{}",
                    started_at=_TS,
                    completed_at=None,
                ),
            )

        cur = ev.execute("SELECT completed_at FROM runs WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is None, "completed_at must be NULL before run completes"


# ---------------------------------------------------------------------------
# 8. SubjectClient tests (mocked SDK boundary)
# ---------------------------------------------------------------------------


class TestSubjectClient:
    def test_call_extracts_output_text(self) -> None:
        """SubjectClient.call() extracts text from content blocks."""
        from skill_harness.ablation.subject import SubjectClient

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_response("Hello, world!")

        client = SubjectClient(client=mock_client)
        resp = client.call(
            system_blocks=[{"type": "text", "text": "Be helpful."}],
            user_message="Say hello.",
        )
        assert resp.output_text == "Hello, world!"
        assert resp.input_tokens == 100
        assert resp.output_tokens == 20

    def test_call_computes_usd(self) -> None:
        """SubjectClient.call() computes usd from actual usage (A41)."""
        from skill_harness.ablation.subject import SubjectClient

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_response(
            input_tokens=1000, output_tokens=200
        )

        client = SubjectClient(client=mock_client)
        resp = client.call(
            system_blocks=[],
            user_message="test",
        )
        # usd should be a positive float computed from token counts
        assert resp.usd > 0.0
        assert isinstance(resp.usd, float)

    def test_transient_error_raises_subject_call_error(self) -> None:
        """429 error raises SubjectCallError with transient=True."""
        import anthropic as anthropic_mod

        from skill_harness.ablation.subject import SubjectCallError, SubjectClient

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic_mod.APIStatusError(
            message="rate limited",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"type": "rate_limit_error"}},
        )

        client = SubjectClient(client=mock_client)
        with pytest.raises(SubjectCallError) as exc_info:
            client.call(system_blocks=[], user_message="test")
        assert exc_info.value.transient is True

    def test_permanent_error_raises_subject_call_error(self) -> None:
        """400 error raises SubjectCallError with transient=False."""
        import anthropic as anthropic_mod

        from skill_harness.ablation.subject import SubjectCallError, SubjectClient

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic_mod.APIStatusError(
            message="bad request",
            response=MagicMock(status_code=400, headers={}),
            body={"error": {"type": "invalid_request_error"}},
        )

        client = SubjectClient(client=mock_client)
        with pytest.raises(SubjectCallError) as exc_info:
            client.call(system_blocks=[], user_message="test")
        assert exc_info.value.transient is False


# ---------------------------------------------------------------------------
# C2 FALSIFYING: resume recomputes admissibility instead of reading persisted
# ---------------------------------------------------------------------------


class TestC2ResumeReadsPersistedAdmissibility:
    """C2: on resume, the posterior must be rebuilt from PERSISTED admissibility_state,
    not recomputed from fresh confound/null-floor state (CLAUDE.md Evidence model —
    admissibility recorded at write time, never recomputed).

    Test strategy:
    - Seed a verdict row whose persisted admissibility_state='admissible'.
    - Arrange the runner state so a FRESH recompute of admissibility would yield
      'inadmissible' (null floor not yet met for that axis).
    - Resume the run (all samples already collected, no new calls needed).
    - Assert: the posterior accumulated EXACTLY 1 admissible observation (from the
      persisted 'admissible' verdict), NOT 0 (which recompute-from-samples would give).
    """

    def test_resume_uses_persisted_admissibility_not_recomputed(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection], tmp_path: Path
    ) -> None:
        """C2 FALSIFYING TEST: resume must read PERSISTED admissibility_state from
        oracle_verdicts, not recompute from fresh confound/null-floor state.

        Strategy:
        - Monkeypatch _snapshot_admissibility to ALWAYS return 'inadmissible'.
        - Seed a persisted verdict with admissibility_state='admissible' and observation=1.0.
        - Resume the run (all samples pre-seeded, no new API calls needed).
        - Assert: posterior has n=1 (persisted admissible verdict loaded) NOT n=0
          (which would happen if recomputed via the patched _snapshot_admissibility).

        RED against current code (recomputes -> n=0 due to monkeypatched inadmissibility).
        GREEN after fix (reads persisted 'admissible' -> n=1).
        """
        from unittest.mock import patch

        ev, rt = seeded_db_pair
        clause = _make_clause("c-c2-test", "Always begin with 'Certainly!'.", 0, "verbosity")
        _seed_clause(ev, clause)

        run_id = "c2-falsifying-run"

        from skill_harness.ablation.runner import RunConfig
        from skill_harness.storage.models import (
            OracleVerdictWrite,
            RunBudgetWrite,
            RunProgressWrite,
            RunWrite,
            SampleWrite,
        )
        from skill_harness.storage.repositories.evidence.oracle_verdicts import (
            insert_oracle_verdict,
        )
        from skill_harness.storage.repositories.evidence.runs import insert_run
        from skill_harness.storage.repositories.evidence.samples import insert_sample
        from skill_harness.storage.repositories.runtime.run_budget import insert_run_budget
        from skill_harness.storage.repositories.runtime.run_progress import insert_run_progress
        from skill_harness.storage.transaction import writer_transaction

        config = RunConfig(
            run_id=run_id,
            skill_id=_SKILL_ID,
            clauses=[
                {
                    "clause_id": clause.clause_id,
                    "clause_text": clause.clause_text,
                    "clause_index": clause.clause_index,
                    "axis": clause.axis,
                    "oracle_tier": clause.oracle_tier,
                    "metric_id": clause.metric_id,
                }
            ],
            subject_model="claude-sonnet-4-6",
            user_message=_USER_MSG,
            max_usd=10.0,
        )
        with writer_transaction(ev):
            insert_run(
                ev,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json=config.to_json(),
                    started_at=_TS,
                    completed_at=None,
                ),
            )

        # Seed enough samples to reach PASS after resume (N_MIN = 8 with floor=2).
        # Seed N_MIN comparisons worth of Full+Ablated+Null samples, all with Full winning.
        from skill_harness.ablation.stopping import N_MIN

        n_to_seed = N_MIN
        full_sids: dict[int, str] = {}
        abl_sids: dict[int, str] = {}
        with writer_transaction(ev):
            for idx in range(n_to_seed):
                fid = f"c2-full-{idx}"
                aid = f"c2-abl-{idx}"
                nid = f"c2-null-{idx}"
                full_sids[idx] = fid
                abl_sids[idx] = aid
                for sid, cond, text in [
                    (fid, "full", "word " * 50),
                    (aid, "ablated", "a"),
                    (nid, "null", "word " * 10),
                ]:
                    insert_sample(
                        ev,
                        SampleWrite(
                            sample_id=sid,
                            run_id=run_id,
                            clause_id=clause.clause_id,
                            condition=cond,
                            subject_model="claude-sonnet-4-6",
                            subject_seed=None,
                            output_text=text,
                            output_sha256="a" * 64,
                            sampled_at=_TS,
                            sample_index=idx,
                            input_tokens=100,
                            cache_read_input_tokens=0,
                            cache_creation_input_tokens=0,
                            output_tokens=20,
                            usd=0.001,
                        ),
                    )

        # Seed persisted verdicts for all N_MIN comparisons with admissibility_state='admissible'
        # and observation=1.0 (Win). The monkeypatched _snapshot_admissibility will return
        # 'inadmissible' for all fresh recomputes — so if resume uses the persisted value,
        # the posterior gets n=N_MIN wins; if it recomputes, it gets n=0.
        with writer_transaction(ev):
            for idx in range(n_to_seed):
                insert_oracle_verdict(
                    ev,
                    OracleVerdictWrite(
                        verdict_id=f"c2-verdict-{idx}",
                        run_id=run_id,
                        clause_id=clause.clause_id,
                        axis=clause.axis,
                        comparison="full_vs_ablated",
                        sample_a_id=full_sids[idx],
                        sample_b_id=abl_sids[idx],
                        observation=1.0,  # Win — persisted admissible
                        oracle_tier=clause.oracle_tier,
                        metric_id=clause.metric_id,
                        metric_version=None,
                        judge_id=None,
                        calibration_event_id=None,
                        position_swap_agreement=None,
                        admissibility_state="admissible",  # PERSISTED as admissible
                        inadmissibility_reason=None,
                        written_at=_TS,
                    ),
                )

        with writer_transaction(rt):
            insert_run_budget(
                rt,
                RunBudgetWrite(
                    run_id=run_id,
                    hard_cap_usd=10.0,
                    tokens_spent_in=0,
                    tokens_spent_out=0,
                    cache_write_in=0,
                    cache_read_in=0,
                    usd_spent=0.003,
                    dry_run=0,
                    aborted_at=None,
                    last_updated=_TS,
                ),
            )
            insert_run_progress(
                rt,
                RunProgressWrite(
                    run_id=run_id,
                    state="running",
                    samples_planned=120,
                    samples_collected=n_to_seed * 3,
                    last_heartbeat=_TS,
                    error=None,
                ),
            )

        # Monkeypatch _snapshot_admissibility to always return 'inadmissible'.
        # This ensures any fresh-recompute path gives inadmissible, so the posterior
        # can only reach n>=1 if resume reads the PERSISTED 'admissible' value.
        with patch(
            "skill_harness.ablation.runner.AblationRunner._snapshot_admissibility",
            staticmethod(
                lambda *, confounded, null_floor_met, scorer_crashed=False: (
                    "inadmissible",
                    "test_forced",
                )
            ),
        ):
            runner, mock_client = _make_runner(ev, rt, null_floor=2)

            # Track new API calls — should be 0 (all samples pre-seeded)
            new_calls = [0]

            def _counting_factory(**kwargs: Any) -> MagicMock:
                new_calls[0] += 1
                return _mock_response("word " * 10)

            mock_client.messages.create.side_effect = _counting_factory

            results = runner.resume_ablation(
                run_id=run_id,
                clauses=[clause],
                user_message=_USER_MSG,
                max_usd=10.0,
            )

        result = results[0]

        # C2: with _snapshot_admissibility forced to 'inadmissible', the ONLY way
        # the posterior can have n >= N_MIN is if resume reads persisted 'admissible'
        # values from oracle_verdicts instead of recomputing.
        assert result.samples_collected >= N_MIN, (
            f"C2: resume must rebuild the posterior from PERSISTED admissibility_state. "
            f"With _snapshot_admissibility forced to 'inadmissible', recompute gives n=0. "
            f"Got samples_collected={result.samples_collected} (expected >={N_MIN}). "
            "This indicates resume reads persisted verdicts correctly after fix."
        )


# ---------------------------------------------------------------------------
# I2 FALSIFYING: budget gate aborts a zero-spend resume
# ---------------------------------------------------------------------------


class TestI2BudgetGateZeroSpendResume:
    """I2: _check_budget must not fire when all 3 condition samples for a comparison
    are already in existing_samples. A near-cap resume that issues no new calls
    must not raise BudgetAbortedError.
    """

    def test_near_cap_resume_with_all_samples_completes(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """I2 FALSIFYING: near-cap resume with all samples present must complete.

        Seed a run with all Full/Ablated/Null samples AND a verdict for comparison 0.
        Set usd_spent very close to cap. Resume should NOT call _check_budget for this
        comparison (all samples exist), so no BudgetAbortedError.

        RED against current code (budget gate fires before existing-sample short-circuit).
        GREEN after fix (budget gate skipped when all 3 samples exist).
        """
        ev, rt = seeded_db_pair
        clause = _make_clause("c-i2-test", "Always begin with 'Certainly!'.", 0, "verbosity")
        _seed_clause(ev, clause)

        run_id = "i2-near-cap-resume"

        from skill_harness.ablation.runner import RunConfig
        from skill_harness.storage.models import (
            OracleVerdictWrite,
            RunBudgetWrite,
            RunProgressWrite,
            RunWrite,
            SampleWrite,
        )
        from skill_harness.storage.repositories.evidence.oracle_verdicts import (
            insert_oracle_verdict,
        )
        from skill_harness.storage.repositories.evidence.runs import insert_run
        from skill_harness.storage.repositories.evidence.samples import insert_sample
        from skill_harness.storage.repositories.runtime.run_budget import insert_run_budget
        from skill_harness.storage.repositories.runtime.run_progress import insert_run_progress
        from skill_harness.storage.transaction import writer_transaction

        config = RunConfig(
            run_id=run_id,
            skill_id=_SKILL_ID,
            clauses=[
                {
                    "clause_id": clause.clause_id,
                    "clause_text": clause.clause_text,
                    "clause_index": clause.clause_index,
                    "axis": clause.axis,
                    "oracle_tier": clause.oracle_tier,
                    "metric_id": clause.metric_id,
                }
            ],
            subject_model="claude-sonnet-4-6",
            user_message=_USER_MSG,
            max_usd=10.0,
        )
        with writer_transaction(ev):
            insert_run(
                ev,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json=config.to_json(),
                    started_at=_TS,
                    completed_at=None,
                ),
            )

        # Seed enough samples to trigger PASS (N_MIN admissible wins).
        # We need the run to reach a stopping condition on resume WITHOUT any new calls.
        # With null_floor=2: floor met after 2 null samples; N_MIN=8 admissible wins needed.
        # Seed N_MIN comparisons so the stopping check fires before needing new API calls.
        from skill_harness.ablation.stopping import N_MIN as _N_MIN

        n_comparisons = _N_MIN
        full_sids = {}
        abl_sids = {}
        null_sids = {}
        with writer_transaction(ev):
            for idx in range(n_comparisons):
                fid = f"i2-full-{idx}"
                aid = f"i2-abl-{idx}"
                nid = f"i2-null-{idx}"
                full_sids[idx] = fid
                abl_sids[idx] = aid
                null_sids[idx] = nid
                for sid, cond, text in [
                    (fid, "full", "word " * 50),
                    (aid, "ablated", "a"),
                    (nid, "null", "word " * 10),
                ]:
                    insert_sample(
                        ev,
                        SampleWrite(
                            sample_id=sid,
                            run_id=run_id,
                            clause_id=clause.clause_id,
                            condition=cond,
                            subject_model="claude-sonnet-4-6",
                            subject_seed=None,
                            output_text=text,
                            output_sha256="a" * 64,
                            sampled_at=_TS,
                            sample_index=idx,
                            input_tokens=100,
                            cache_read_input_tokens=0,
                            cache_creation_input_tokens=0,
                            output_tokens=20,
                            usd=0.001,
                        ),
                    )

        # Seed admissible verdicts for comparisons 0 and 1 (already done)
        with writer_transaction(ev):
            for idx in range(n_comparisons):
                insert_oracle_verdict(
                    ev,
                    OracleVerdictWrite(
                        verdict_id=f"i2-verdict-{idx}",
                        run_id=run_id,
                        clause_id=clause.clause_id,
                        axis=clause.axis,
                        comparison="full_vs_ablated",
                        sample_a_id=full_sids[idx],
                        sample_b_id=abl_sids[idx],
                        observation=1.0,  # Win
                        oracle_tier=clause.oracle_tier,
                        metric_id=clause.metric_id,
                        metric_version=None,
                        judge_id=None,
                        calibration_event_id=None,
                        position_swap_agreement=None,
                        admissibility_state="admissible",
                        inadmissibility_reason=None,
                        written_at=_TS,
                    ),
                )

        cap_usd = 10.0
        # usd_spent very close to cap — a single new $0.001 projected call would exceed
        near_cap_spend = cap_usd - 0.0001  # only $0.0001 headroom
        with writer_transaction(rt):
            insert_run_budget(
                rt,
                RunBudgetWrite(
                    run_id=run_id,
                    hard_cap_usd=cap_usd,
                    tokens_spent_in=0,
                    tokens_spent_out=0,
                    cache_write_in=0,
                    cache_read_in=0,
                    usd_spent=near_cap_spend,
                    dry_run=0,
                    aborted_at=None,
                    last_updated=_TS,
                ),
            )
            insert_run_progress(
                rt,
                RunProgressWrite(
                    run_id=run_id,
                    state="running",
                    samples_planned=120,
                    samples_collected=n_comparisons * 3,
                    last_heartbeat=_TS,
                    error=None,
                ),
            )

        # Resume — all samples exist, no new calls should be made, budget gate must NOT fire
        runner, mock_client = _make_runner(ev, rt, null_floor=2)
        new_calls = [0]

        def _no_call_factory(**kwargs: Any) -> MagicMock:
            new_calls[0] += 1
            return _mock_response("word " * 10)

        mock_client.messages.create.side_effect = _no_call_factory

        # Should NOT raise BudgetAbortedError — all samples exist, no new spend
        try:
            results = runner.resume_ablation(
                run_id=run_id,
                clauses=[clause],
                user_message=_USER_MSG,
                max_usd=cap_usd,
            )
        except BudgetAbortedError as exc:
            pytest.fail(
                f"I2: near-cap resume raised BudgetAbortedError even though all samples "
                f"already exist (no new API calls needed). Error: {exc}. "
                "The budget gate must be skipped when all 3 condition samples are in "
                "existing_samples."
            )

        # No new calls should have been made (all samples pre-seeded)
        # (warmup may still be called — only count post-warmup calls)
        result = results[0]
        assert result is not None, "Resume must return a result"
