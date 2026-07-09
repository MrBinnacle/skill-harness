"""Tests for the v0.2 evidence-store write path (paired .eval → samples/verdicts).

These are also the MECHANICAL VALIDITY TESTS for the ``subject:*`` outcome
oracle registered by the write path (metric_versions row, tier 1): score
decoding, pairing, and the {0, 0.5, 1} observation mapping are fully
deterministic and covered here offline. Parsing (which needs the ``[inspect]``
extra) is exercised only for its typed not-installed error, matching
tests/test_subject_layer.py.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from importlib.util import find_spec
from pathlib import Path

import pytest

from skill_harness.storage.migrations import open_evidence
from skill_harness.subject.ingest import (
    ORACLE_METRIC_VERSION,
    WHOLE_SKILL_CLAUSE_INDEX,
    AlreadyIngestedError,
    EvalLogIngestError,
    EvalLogNotSuccessError,
    PairedLogMismatchError,
    ParsedEvalLog,
    ParsedSample,
    _derived_run_id,
    _observation,
    _score_to_float,
    write_paired_evidence,
)

INSPECT_INSTALLED = find_spec("inspect_ai") is not None

PIN_FP = "a" * 64
PIN_JSON = json.dumps({"model": "openrouter/anthropic/claude-haiku-4.5"}, sort_keys=True)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_evidence(tmp_path / "evidence.db")
    yield connection
    connection.close()


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    d = tmp_path / "some-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: some-skill\n---\nbody\n", encoding="utf-8")
    return d


def make_sample(
    condition: str,
    epoch: int,
    score: float,
    *,
    fingerprint: str | None = PIN_FP,
    skill_name: str = "some-skill",
    scorer_name: str = "file_contains",
) -> ParsedSample:
    return ParsedSample(
        condition=condition,  # type: ignore[arg-type]
        skill_name=skill_name,
        epoch=epoch,
        scorer_name=scorer_name,
        score_value=score,
        output_text=f"output-{condition}-{epoch}",
        subject_model="openrouter/anthropic/claude-haiku-4.5",
        harness_pin_json=PIN_JSON if fingerprint is not None else None,
        harness_pin_fingerprint=fingerprint,
        input_tokens=100,
        cache_read_input_tokens=50,
        cache_creation_input_tokens=25,
        output_tokens=10,
        usd=None,
    )


def make_log(
    condition: str,
    samples: tuple[ParsedSample, ...],
    *,
    task_id: str | None = None,
    status: str = "success",
) -> ParsedEvalLog:
    return ParsedEvalLog(
        task_name=f"some-skill-{condition}",
        task_id=task_id or f"task-{condition}",
        created="2026-07-09T21:26:43+00:00",
        status=status,
        samples=samples,
    )


# ---------------------------------------------------------------------------
# Mechanical validity: score decoding + observation mapping (deterministic)
# ---------------------------------------------------------------------------


def test_observation_mapping_is_the_stat_f4_encoding() -> None:
    assert _observation(1.0, 0.0) == 1.0  # Full passed, Null failed
    assert _observation(0.0, 1.0) == 0.0  # Null passed, Full failed
    assert _observation(1.0, 1.0) == 0.5  # tie (both passed)
    assert _observation(0.0, 0.0) == 0.5  # tie (both failed)


def test_score_to_float_decodes_inspect_values() -> None:
    p = Path("x.eval")
    assert _score_to_float("C", p) == 1.0
    assert _score_to_float("I", p) == 0.0
    assert _score_to_float(True, p) == 1.0
    assert _score_to_float(0.0, p) == 0.0
    assert _score_to_float(1, p) == 1.0
    with pytest.raises(EvalLogIngestError, match="unmappable"):
        _score_to_float("P", p)
    with pytest.raises(EvalLogIngestError, match="unmappable"):
        _score_to_float(None, p)


def test_derived_run_id_is_deterministic_and_order_sensitive() -> None:
    assert _derived_run_id("a", "b") == _derived_run_id("a", "b")
    assert _derived_run_id("a", "b") != _derived_run_id("b", "a")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_writes_run_samples_and_admissible_verdicts(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0), make_sample("full", 2, 1.0)))
    null = make_log("null", (make_sample("null", 1, 0.0), make_sample("null", 2, 1.0)))

    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    assert result.admissibility_state == "admissible"
    assert result.inadmissibility_reason is None
    assert len(result.sample_ids) == 4
    assert len(result.verdict_ids) == 2

    run = conn.execute(
        "SELECT run_kind, completed_at, config_json FROM runs WHERE run_id = ?",
        (result.run_id,),
    ).fetchone()
    assert run[0] == "evaluate_skill"
    assert run[1] is not None
    config = json.loads(run[2])
    assert config["contrast"] == "full_vs_null"
    assert config["harness_pin_fingerprint"] == PIN_FP

    rows = conn.execute(
        """
        SELECT condition, sample_index, harness_pin_fingerprint, harness_pin_json
        FROM samples WHERE run_id = ? ORDER BY condition, sample_index
        """,
        (result.run_id,),
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        ("full", 1),
        ("full", 2),
        ("null", 1),
        ("null", 2),
    ]
    assert all(r[2] == PIN_FP and r[3] == PIN_JSON for r in rows)

    verdicts = conn.execute(
        """
        SELECT observation, oracle_tier, metric_id, metric_version,
               admissibility_state, comparison, axis
        FROM oracle_verdicts WHERE run_id = ? ORDER BY written_at
        """,
        (result.run_id,),
    ).fetchall()
    # epoch 1: full 1.0 / null 0.0 → 1.0; epoch 2: both 1.0 → 0.5
    assert sorted(v[0] for v in verdicts) == [0.5, 1.0]
    assert all(
        v[1] == 1
        and v[2] == "subject:file_contains"
        and v[3] == ORACLE_METRIC_VERSION
        and v[4] == "admissible"
        and v[5] == "full_vs_null"
        and v[6] == "outcome"
        for v in verdicts
    )


def test_verdict_sample_ids_pair_full_with_null_per_epoch(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    row = conn.execute(
        """
        SELECT sa.condition, sb.condition
        FROM oracle_verdicts v
        JOIN samples sa ON sa.sample_id = v.sample_a_id
        JOIN samples sb ON sb.sample_id = v.sample_b_id
        WHERE v.run_id = ?
        """,
        (result.run_id,),
    ).fetchone()
    assert row == ("full", "null")


def test_whole_skill_sentinel_clause_and_metric_registered_once(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full1 = make_log("full", (make_sample("full", 1, 1.0),), task_id="f1")
    null1 = make_log("null", (make_sample("null", 1, 0.0),), task_id="n1")
    r1 = write_paired_evidence(full=full1, null=null1, skill_dir=skill_dir, conn=conn)

    # second, distinct pair for the SAME skill must reuse skill/clause/metric rows
    full2 = make_log("full", (make_sample("full", 1, 1.0),), task_id="f2")
    null2 = make_log("null", (make_sample("null", 1, 1.0),), task_id="n2")
    r2 = write_paired_evidence(full=full2, null=null2, skill_dir=skill_dir, conn=conn)

    assert r1.skill_id == r2.skill_id
    assert r1.clause_id == r2.clause_id
    clause = conn.execute(
        "SELECT clause_index, axis, oracle_tier FROM clauses WHERE clause_id = ?",
        (r1.clause_id,),
    ).fetchone()
    assert clause == (WHOLE_SKILL_CLAUSE_INDEX, "outcome", 1)
    n_metrics = conn.execute(
        "SELECT COUNT(*) FROM metric_versions WHERE metric_id = 'subject:file_contains'"
    ).fetchone()[0]
    assert n_metrics == 1


# ---------------------------------------------------------------------------
# Harness-pin admissibility (write-time snapshot)
# ---------------------------------------------------------------------------


def test_pin_mismatch_writes_inadmissible_verdicts(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0, fingerprint="b" * 64),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    assert result.admissibility_state == "inadmissible"
    assert result.inadmissibility_reason == "harness_pin_mismatch"
    row = conn.execute(
        "SELECT admissibility_state, inadmissibility_reason FROM oracle_verdicts WHERE run_id = ?",
        (result.run_id,),
    ).fetchone()
    assert row == ("inadmissible", "harness_pin_mismatch")


def test_pin_missing_writes_inadmissible_verdicts(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0, fingerprint=None),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    assert result.admissibility_state == "inadmissible"
    assert result.inadmissibility_reason == "harness_pin_missing"


def test_inadmissible_verdicts_are_excluded_from_the_admissible_view(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0, fingerprint="b" * 64),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    n = conn.execute(
        "SELECT COUNT(*) FROM admissible_verdicts WHERE run_id = ?", (result.run_id,)
    ).fetchone()[0]
    assert n == 0


# ---------------------------------------------------------------------------
# Structural refusals (apparatus errors, not evidence)
# ---------------------------------------------------------------------------


def test_non_success_status_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0),), status="error")
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(EvalLogNotSuccessError, match="error"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_wrong_condition_in_log_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("null", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(PairedLogMismatchError, match="condition"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_unpaired_epochs_refuse(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0), make_sample("full", 2, 1.0)))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(PairedLogMismatchError, match="unpaired epochs"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_skill_disagreement_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0, skill_name="other-skill"),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(PairedLogMismatchError, match="disagree on the skill"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_missing_skill_md_refuses(conn: sqlite3.Connection, tmp_path: Path) -> None:
    empty = tmp_path / "empty-skill"
    empty.mkdir()
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(FileNotFoundError, match=r"SKILL\.md"):
        write_paired_evidence(full=full, null=null, skill_dir=empty, conn=conn)


def test_reingest_of_same_task_pair_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    with pytest.raises(AlreadyIngestedError, match="already ingested"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_refused_write_leaves_no_rows_behind(conn: sqlite3.Connection, skill_dir: Path) -> None:
    # a structural refusal happens BEFORE the transaction opens; nothing lands
    full = make_log("full", (make_sample("full", 1, 1.0),), status="error")
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(EvalLogNotSuccessError):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Parsing surface without the optional extra
# ---------------------------------------------------------------------------


@pytest.mark.skipif(INSPECT_INSTALLED, reason="extra installed; error path unreachable")
def test_parse_eval_log_raises_typed_error_without_extra(tmp_path: Path) -> None:
    from skill_harness.subject.ingest import parse_eval_log
    from skill_harness.subject.inspect_adapter import SubjectLayerNotInstalledError

    with pytest.raises(SubjectLayerNotInstalledError, match=r"skill-harness\[inspect\]"):
        parse_eval_log(tmp_path / "whatever.eval")
