"""Tests for migration 0300 — Track D ablation schema extensions (A39, A40, A41).

Covers:
- Migration applies cleanly to a fresh evidence DB.
- samples.sample_index column present and NOT NULL.
- UNIQUE(run_id, clause_id, condition, sample_index) enforced (A40 idempotency key).
- Per-call cost columns on samples: input_tokens, cache_read_input_tokens,
  cache_creation_input_tokens, output_tokens, usd (A41).
- oracle_verdicts.ablation_operator_id + ablation_operator_hash columns present (A39).
- Append-only triggers still enforced on samples and oracle_verdicts after migration.
- A22 synchronous=FULL preserved.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from skill_harness.storage.migrations import open_evidence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_skill(conn: sqlite3.Connection, skill_id: str = "sk1") -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256) VALUES (?,?,?,?)",
        (skill_id, "test-skill", "/tmp/test.md", "a" * 64),
    )


def _insert_clause(
    conn: sqlite3.Connection,
    clause_id: str = "cl1",
    skill_id: str = "sk1",
    clause_index: int = 0,
    rendering_index: int = 0,
) -> None:
    conn.execute(
        "INSERT INTO clauses "
        "(clause_id, skill_id, clause_index, rendering_index, "
        "clause_text, axis, comparator, oracle_tier)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (clause_id, skill_id, clause_index, rendering_index, "Do X.", "verbosity", "decrease", 1),
    )


def _insert_run(conn: sqlite3.Connection, run_id: str = "r1", skill_id: str = "sk1") -> None:
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at) VALUES (?,?,?,?,?)",
        (run_id, skill_id, "ablation", "{}", "2026-06-06T00:00:00Z"),
    )


def _insert_metric_version(conn: sqlite3.Connection, metric_id: str = "verbosity") -> None:
    conn.execute(
        "INSERT INTO metric_versions "
        "(metric_id, version, implementation_hash, tier, audited, mechanical_validity_test_passed)"
        " VALUES (?,?,?,?,?,?)",
        (metric_id, "1.0.0", "b" * 64, 1, 1, 1),
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def ev(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Fresh evidence DB with all migrations (including 0300) applied."""
    conn = open_evidence(tmp_path / "evidence.db")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Schema presence tests
# ---------------------------------------------------------------------------


def test_migration_0300_applies_cleanly(ev: sqlite3.Connection) -> None:
    """Migration 0300 applies without error; samples table still exists."""
    cur = ev.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='samples'")
    assert cur.fetchone() is not None


def test_samples_has_sample_index_column(ev: sqlite3.Connection) -> None:
    """samples.sample_index column was added by migration 0300 (A40)."""
    cur = ev.execute("PRAGMA table_info(samples)")
    cols = {row[1] for row in cur.fetchall()}
    assert "sample_index" in cols


def test_samples_has_cost_columns(ev: sqlite3.Connection) -> None:
    """Per-call cost columns present on samples table (A41)."""
    cur = ev.execute("PRAGMA table_info(samples)")
    cols = {row[1] for row in cur.fetchall()}
    expected_cost_cols = {
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "output_tokens",
        "usd",
    }
    missing = expected_cost_cols - cols
    assert not missing, f"Cost columns missing from samples: {missing}"


def test_oracle_verdicts_has_operator_provenance_columns(ev: sqlite3.Connection) -> None:
    """oracle_verdicts.ablation_operator_id and ablation_operator_hash present (A39)."""
    cur = ev.execute("PRAGMA table_info(oracle_verdicts)")
    cols = {row[1] for row in cur.fetchall()}
    assert "ablation_operator_id" in cols
    assert "ablation_operator_hash" in cols


# ---------------------------------------------------------------------------
# UNIQUE constraint test (A40 idempotency key)
# ---------------------------------------------------------------------------


def test_samples_unique_run_clause_condition_index(ev: sqlite3.Connection) -> None:
    """Duplicate (run_id, clause_id, condition, sample_index) raises IntegrityError (A40)."""
    _insert_skill(ev)
    _insert_clause(ev)
    _insert_run(ev)

    ev.execute(
        "INSERT INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
        "output_sha256, sampled_at, sample_index) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("s1", "r1", "cl1", "full", "gpt-test", "hello", "c" * 64, "2026-06-06T00:00:00Z", 0),
    )

    with pytest.raises(sqlite3.IntegrityError):
        ev.execute(
            "INSERT INTO samples "
            "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
            "output_sha256, sampled_at, sample_index) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "s2",
                "r1",
                "cl1",
                "full",
                "gpt-test",
                "world",
                "d" * 64,
                "2026-06-06T00:01:00Z",
                0,  # same index — must fail
            ),
        )


def test_samples_different_index_same_run_clause_condition_allowed(
    ev: sqlite3.Connection,
) -> None:
    """Different sample_index values on same (run_id, clause_id, condition) are allowed."""
    _insert_skill(ev)
    _insert_clause(ev)
    _insert_run(ev)

    for idx in range(3):
        ev.execute(
            "INSERT INTO samples "
            "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
            "output_sha256, sampled_at, sample_index) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                f"s{idx}",
                "r1",
                "cl1",
                "full",
                "gpt-test",
                f"output {idx}",
                ("e" * 63 + str(idx)),
                "2026-06-06T00:00:00Z",
                idx,
            ),
        )
    cur = ev.execute("SELECT COUNT(*) FROM samples WHERE run_id='r1'")
    assert cur.fetchone()[0] == 3


# ---------------------------------------------------------------------------
# sample_index NOT NULL test
# ---------------------------------------------------------------------------


def test_sample_index_not_null(ev: sqlite3.Connection) -> None:
    """sample_index NOT NULL constraint enforced (A40)."""
    _insert_skill(ev)
    _insert_clause(ev)
    _insert_run(ev)

    with pytest.raises(sqlite3.IntegrityError):
        ev.execute(
            "INSERT INTO samples "
            "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
            "output_sha256, sampled_at, sample_index) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "s_null",
                "r1",
                "cl1",
                "full",
                "gpt-test",
                "out",
                "f" * 64,
                "2026-06-06T00:00:00Z",
                None,
            ),
        )


# ---------------------------------------------------------------------------
# Append-only trigger tests (still enforced after migration)
# ---------------------------------------------------------------------------


def test_samples_append_only_still_enforced(ev: sqlite3.Connection) -> None:
    """After migration 0300, samples UPDATE/DELETE still raise (A1 preserved)."""
    _insert_skill(ev)
    _insert_clause(ev)
    _insert_run(ev)

    ev.execute(
        "INSERT INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
        "output_sha256, sampled_at, sample_index) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("s_ao", "r1", "cl1", "full", "gpt-test", "out", "g" * 64, "2026-06-06T00:00:00Z", 0),
    )

    with pytest.raises(sqlite3.IntegrityError, match="append_only_violation: samples"):
        ev.execute("UPDATE samples SET output_text='changed' WHERE sample_id='s_ao'")

    with pytest.raises(sqlite3.IntegrityError, match="append_only_violation: samples"):
        ev.execute("DELETE FROM samples WHERE sample_id='s_ao'")


def test_oracle_verdicts_append_only_still_enforced(ev: sqlite3.Connection) -> None:
    """After migration 0300, oracle_verdicts UPDATE/DELETE still raise (A1 preserved)."""
    _insert_skill(ev)
    _insert_clause(ev)
    _insert_run(ev)
    _insert_metric_version(ev)

    ev.execute(
        "INSERT INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
        "output_sha256, sampled_at, sample_index) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("sa", "r1", "cl1", "full", "gpt-test", "out_a", "h" * 64, "2026-06-06T00:00:00Z", 0),
    )
    ev.execute(
        "INSERT INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
        "output_sha256, sampled_at, sample_index) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("sb", "r1", "cl1", "ablated", "gpt-test", "out_b", "i" * 64, "2026-06-06T00:00:00Z", 0),
    )

    ev.execute(
        "INSERT INTO oracle_verdicts "
        "(verdict_id, run_id, clause_id, axis, comparison, sample_a_id, sample_b_id, "
        "observation, oracle_tier, metric_id, metric_version, admissibility_state, written_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "v1",
            "r1",
            "cl1",
            "verbosity",
            "full_vs_ablated",
            "sa",
            "sb",
            1.0,
            1,
            "verbosity",
            "1.0.0",
            "admissible",
            "2026-06-06T00:00:00Z",
        ),
    )

    with pytest.raises(sqlite3.IntegrityError, match="append_only_violation: oracle_verdicts"):
        ev.execute("UPDATE oracle_verdicts SET observation=0.0 WHERE verdict_id='v1'")


# ---------------------------------------------------------------------------
# Durability test (A22 synchronous=FULL preserved)
# ---------------------------------------------------------------------------


def test_synchronous_full_preserved_after_0300(ev: sqlite3.Connection) -> None:
    """A22: synchronous=FULL still in effect after migration 0300 applies (returns 2)."""
    value = ev.execute("PRAGMA synchronous").fetchone()[0]
    assert value == 2, f"Expected synchronous=FULL (2) after migration 0300, got {value}"


# ---------------------------------------------------------------------------
# Operator provenance write test
# ---------------------------------------------------------------------------


def test_operator_provenance_writable_on_verdicts(ev: sqlite3.Connection) -> None:
    """ablation_operator_id and ablation_operator_hash can be written on oracle_verdicts (A39)."""
    _insert_skill(ev)
    _insert_clause(ev)
    _insert_run(ev)
    _insert_metric_version(ev)

    ev.execute(
        "INSERT INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
        "output_sha256, sampled_at, sample_index) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("sa2", "r1", "cl1", "full", "gpt-test", "out_a2", "j" * 64, "2026-06-06T00:00:00Z", 1),
    )
    ev.execute(
        "INSERT INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
        "output_sha256, sampled_at, sample_index) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("sb2", "r1", "cl1", "ablated", "gpt-test", "out_b2", "k" * 64, "2026-06-06T00:00:00Z", 1),
    )

    ev.execute(
        "INSERT INTO oracle_verdicts "
        "(verdict_id, run_id, clause_id, axis, comparison, sample_a_id, sample_b_id, "
        "observation, oracle_tier, metric_id, metric_version, admissibility_state, written_at, "
        "ablation_operator_id, ablation_operator_hash) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "v2",
            "r1",
            "cl1",
            "verbosity",
            "full_vs_ablated",
            "sa2",
            "sb2",
            1.0,
            1,
            "verbosity",
            "1.0.0",
            "admissible",
            "2026-06-06T00:00:00Z",
            "neutral-filler-v1",
            "l" * 64,
        ),
    )

    cur = ev.execute(
        "SELECT ablation_operator_id, ablation_operator_hash "
        "FROM oracle_verdicts WHERE verdict_id='v2'"
    )
    row = cur.fetchone()
    assert row[0] == "neutral-filler-v1"
    assert row[1] == "l" * 64


def test_cost_columns_writable_on_samples(ev: sqlite3.Connection) -> None:
    """Per-call cost columns can be written on samples rows (A41)."""
    _insert_skill(ev)
    _insert_clause(ev)
    _insert_run(ev)

    ev.execute(
        "INSERT INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
        "output_sha256, sampled_at, sample_index, "
        "input_tokens, cache_read_input_tokens, cache_creation_input_tokens, output_tokens, usd) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "s_cost",
            "r1",
            "cl1",
            "full",
            "gpt-test",
            "hello world",
            "m" * 64,
            "2026-06-06T00:00:00Z",
            2,
            1000,
            500,
            0,
            50,
            0.00125,
        ),
    )

    cur = ev.execute(
        "SELECT input_tokens, cache_read_input_tokens, cache_creation_input_tokens, "
        "output_tokens, usd FROM samples WHERE sample_id='s_cost'"
    )
    row = cur.fetchone()
    assert row[0] == 1000
    assert row[1] == 500
    assert row[2] == 0
    assert row[3] == 50
    assert abs(row[4] - 0.00125) < 1e-10
