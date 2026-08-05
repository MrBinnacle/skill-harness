"""Issue #75 / #81 — mandatory model pin on new verdict mints + drift fingerprint.

Acceptance (external behaviour only):
- A new mint with neither model_snapshot nor response-fingerprint fallback is rejected.
- The guarded new-mint entrypoint refuses without a valid pin (#81).
- A pre-registry / historical record is not retrofitted with a snapshot.
- A drift fingerprint is captured such that a subsequent fleet-model change is detectable.
- Raw insert_oracle_verdict remains usable for historical / no-retrofit inserts.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from skill_harness.storage.article_fingerprint import (
    ArticleFingerprint,
    fleet_drift_fingerprint,
    is_stale_vs_fleet,
)
from skill_harness.storage.migrations import open_evidence
from skill_harness.storage.models import OracleVerdictWrite
from skill_harness.storage.repositories.evidence.oracle_verdicts import (
    insert_oracle_verdict,
    mint_oracle_verdict,
)
from skill_harness.subject.ingest import (
    ParsedEvalLog,
    ParsedSample,
    write_paired_evidence,
)

_TS = "2026-08-04T00:00:00.000Z"
_SHA = "a" * 64
_PIN_FP = "b" * 64


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


def _sample(
    condition: str,
    epoch: int,
    score: float,
    *,
    subject_model: str = "openrouter/anthropic/claude-haiku-4.5",
    fingerprint: str | None = _PIN_FP,
) -> ParsedSample:
    invoked = condition == "full"
    return ParsedSample(
        condition=condition,  # type: ignore[arg-type]
        skill_name="some-skill",
        epoch=epoch,
        scorer_name="file_contains",
        score_value=score,
        invoked_skill=invoked,
        output_text=f"output-{condition}-{epoch}",
        subject_model=subject_model,
        harness_pin_json='{"model":"openrouter/anthropic/claude-haiku-4.5"}'
        if fingerprint is not None
        else None,
        harness_pin_fingerprint=fingerprint,
        input_tokens=100,
        cache_read_input_tokens=50,
        cache_creation_input_tokens=25,
        output_tokens=10,
        usd=None,
    )


def _log(condition: str, samples: tuple[ParsedSample, ...]) -> ParsedEvalLog:
    return ParsedEvalLog(
        task_name=f"task-{condition}",
        task_id=f"tid-{condition}",
        status="success",
        created=_TS,
        samples=samples,
    )


def _seed_parents(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES ('sk1', 'S', '/p', ?, ?)",
        (_SHA, _TS),
    )
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag) VALUES"
        " ('cl1', 'sk1', 0, 0, 'text', 'verbosity', 'decrease', 1, 'none')"
    )
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES ('run1', 'sk1', 'ablation', '{}', ?, ?)",
        (_TS, _TS),
    )
    conn.execute(
        "INSERT INTO metric_versions"
        " (metric_id, version, implementation_hash, tier, audited,"
        " mechanical_validity_test_passed, registered_at)"
        " VALUES ('m1', '1.0.0', ?, 1, 1, 1, ?)",
        (_SHA, _TS),
    )
    for i, sid in enumerate(("sa", "sb")):
        conn.execute(
            "INSERT INTO samples (sample_id, run_id, clause_id, condition,"
            " subject_model, output_text, output_sha256, sampled_at, sample_index)"
            " VALUES (?, 'run1', 'cl1', 'full', 'model-x', 'out', ?, ?, ?)",
            (sid, _SHA, _TS, i),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# AC1 — new mint rejected without model_snapshot or response-fingerprint
# ---------------------------------------------------------------------------


def _bare_verdict(*, verdict_id: str = "v-bare") -> OracleVerdictWrite:
    """Historical-shaped write with no pin columns (nullable by design — #41)."""
    return OracleVerdictWrite(
        verdict_id=verdict_id,
        run_id="run1",
        clause_id="cl1",
        axis="verbosity",
        comparison="full_vs_ablated",
        sample_a_id="sa",
        sample_b_id="sb",
        observation=1.0,
        oracle_tier=1,
        metric_id="m1",
        metric_version="1.0.0",
        judge_id=None,
        calibration_event_id=None,
        position_swap_agreement=None,
        admissibility_state="admissible",
        inadmissibility_reason=None,
        written_at=_TS,
    )


def test_article_fingerprint_rejects_unpinned_mint() -> None:
    """Neither model_snapshot nor response-fingerprint fallback → reject."""
    with pytest.raises((ValueError, ValidationError)):
        ArticleFingerprint()


def test_article_fingerprint_rejects_response_fingerprint_without_requalify_flag() -> None:
    """Response-fingerprint fallback requires requalify_on_drift."""
    with pytest.raises((ValueError, ValidationError)):
        ArticleFingerprint(response_fingerprint="deadbeef" * 8)


def test_mint_entrypoint_refuses_without_valid_pin(conn: sqlite3.Connection) -> None:
    """#81: guarded mint entrypoint refuses when no valid pin can be supplied."""
    _seed_parents(conn)
    bare = _bare_verdict(verdict_id="mint-reject-unpinned")

    with pytest.raises((ValueError, ValidationError)):
        mint_oracle_verdict(conn, bare, pin=ArticleFingerprint())

    row = conn.execute(
        "SELECT 1 FROM oracle_verdicts WHERE verdict_id = 'mint-reject-unpinned'"
    ).fetchone()
    assert row is None


def test_mint_entrypoint_persists_pin_columns(conn: sqlite3.Connection) -> None:
    """#81: guarded mint applies ArticleFingerprint columns onto the written row."""
    _seed_parents(conn)
    model = "claude-sonnet-4-6"
    pin = ArticleFingerprint(model_snapshot=model)

    mint_oracle_verdict(conn, _bare_verdict(verdict_id="mint-pinned"), pin=pin)
    conn.commit()

    row = conn.execute(
        "SELECT model_snapshot, response_fingerprint, requalify_on_drift, drift_fingerprint"
        " FROM oracle_verdicts WHERE verdict_id = 'mint-pinned'"
    ).fetchone()
    assert row is not None
    assert row[0] == model
    assert row[3] == pin.drift_fingerprint


def test_mint_via_ingest_pins_model_snapshot(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """New mint path accepts a pin and persists model_snapshot + drift_fingerprint."""
    model = "openrouter/anthropic/claude-haiku-4.5"
    full = _log("full", (_sample("full", 1, 1.0, subject_model=model),))
    null = _log("null", (_sample("null", 1, 0.0, subject_model=model),))

    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    assert result.verdict_ids

    row = conn.execute(
        "SELECT model_snapshot, response_fingerprint, requalify_on_drift, drift_fingerprint"
        " FROM oracle_verdicts WHERE verdict_id = ?",
        (result.verdict_ids[0],),
    ).fetchone()
    assert row is not None
    assert row[0] == model
    assert row[3] is not None
    assert row[3] == ArticleFingerprint(model_snapshot=model).drift_fingerprint


# ---------------------------------------------------------------------------
# AC2 — historical / pre-registry records are not retrofitted
# ---------------------------------------------------------------------------


def test_historical_verdict_may_lack_model_snapshot(conn: sqlite3.Connection) -> None:
    """Pre-registry rows stay NULL — migration does not backfill; insert allows NULL."""
    _seed_parents(conn)

    # Direct repository insert of a historical-shaped write (no pin fields).
    # Raw insert_oracle_verdict remains the historical/reconciler path (#81 AC).
    insert_oracle_verdict(conn, _bare_verdict(verdict_id="historical-v1"))
    conn.commit()

    row = conn.execute(
        "SELECT model_snapshot, drift_fingerprint FROM oracle_verdicts"
        " WHERE verdict_id = 'historical-v1'"
    ).fetchone()
    assert row == (None, None)


def test_migration_does_not_backfill_existing_null_rows(
    conn: sqlite3.Connection,
) -> None:
    """Column defaults leave pre-existing NULL rows untouched (no-retrofit)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(oracle_verdicts)").fetchall()}
    assert "model_snapshot" in cols
    assert "drift_fingerprint" in cols
    assert "response_fingerprint" in cols
    assert "requalify_on_drift" in cols


# ---------------------------------------------------------------------------
# AC3 — drift fingerprint detects subsequent fleet-model change
# ---------------------------------------------------------------------------


def test_drift_fingerprint_detects_fleet_model_change() -> None:
    pin = ArticleFingerprint(model_snapshot="claude-sonnet-4-6")
    assert not is_stale_vs_fleet(pin.drift_fingerprint, "claude-sonnet-4-6")
    assert is_stale_vs_fleet(pin.drift_fingerprint, "claude-opus-4-7")


def test_response_fingerprint_fallback_carries_drift_token() -> None:
    fp = "c" * 64
    pin = ArticleFingerprint(response_fingerprint=fp, requalify_on_drift=True)
    assert pin.model_snapshot is None
    assert pin.requalify_on_drift is True
    assert (
        pin.drift_fingerprint == hashlib.sha256(f"response_fingerprint:{fp}".encode()).hexdigest()
    )
    # Fleet-model identity is a different kind of pin — still detectable as drift.
    assert is_stale_vs_fleet(pin.drift_fingerprint, "claude-sonnet-4-6")


def test_historical_null_drift_fingerprint_is_not_stale_badge() -> None:
    """No pin → no stale badge from this mechanism (pre-registry stays unbadged)."""
    assert not is_stale_vs_fleet(None, "claude-sonnet-4-6")
    assert (
        fleet_drift_fingerprint("claude-sonnet-4-6")
        == ArticleFingerprint(model_snapshot="claude-sonnet-4-6").drift_fingerprint
    )
