"""Tests for aggregate_cost_by_skill (runtime.cost_ledger fired-tax rollup).

Seeds a temp runtime DB through the repo's normal open/insert path (never raw
sqlite3.connect) and asserts the per-skill token + usd sums, NULL skill_id
skipped, and empty-ledger -> {}.
"""

from __future__ import annotations

from pathlib import Path

from skill_harness.storage.migrations import open_runtime
from skill_harness.storage.models import CostLedgerWrite
from skill_harness.storage.repositories.runtime.cost_ledger import (
    aggregate_cost_by_skill,
    insert_cost_ledger_entry,
)

_TS = "2026-07-01T10:00:00.000Z"


def _entry(
    skill_id: str | None,
    *,
    input_tok: int = 0,
    cache_write_tok: int = 0,
    cache_read_tok: int = 0,
    output_tok: int = 0,
    usd: float = 0.0,
) -> CostLedgerWrite:
    return CostLedgerWrite(
        ts=_TS,
        run_id="run-1",
        skill_id=skill_id,
        model_id="claude-sonnet-4-6",
        call_kind="subject",
        input_tok=input_tok,
        cache_write_tok=cache_write_tok,
        cache_read_tok=cache_read_tok,
        output_tok=output_tok,
        usd=usd,
    )


def test_empty_ledger_returns_empty_dict(tmp_path: Path) -> None:
    conn = open_runtime(tmp_path / "runtime.db")
    try:
        assert aggregate_cost_by_skill(conn) == {}
    finally:
        conn.close()


def test_sums_all_four_token_columns_and_usd_per_skill(tmp_path: Path) -> None:
    conn = open_runtime(tmp_path / "runtime.db")
    try:
        insert_cost_ledger_entry(
            conn,
            _entry(
                "alpha-skill",
                input_tok=100,
                cache_write_tok=10,
                cache_read_tok=5,
                output_tok=20,
                usd=0.5,
            ),
        )
        insert_cost_ledger_entry(
            conn,
            _entry(
                "alpha-skill",
                input_tok=1,
                cache_write_tok=2,
                cache_read_tok=3,
                output_tok=4,
                usd=0.25,
            ),
        )
        insert_cost_ledger_entry(
            conn,
            _entry("beta-skill", input_tok=7, output_tok=3, usd=0.1),
        )

        result = aggregate_cost_by_skill(conn)
    finally:
        conn.close()

    # alpha: total_tok = (100+10+5+20) + (1+2+3+4) = 135 + 10 = 145; usd = 0.75
    assert result["alpha-skill"]["total_tok"] == 145
    assert result["alpha-skill"]["total_usd"] == 0.75
    # beta: total_tok = 7+3 = 10; usd = 0.1
    assert result["beta-skill"]["total_tok"] == 10
    assert result["beta-skill"]["total_usd"] == 0.1


def test_null_skill_id_rows_are_skipped(tmp_path: Path) -> None:
    conn = open_runtime(tmp_path / "runtime.db")
    try:
        insert_cost_ledger_entry(conn, _entry(None, input_tok=999, usd=9.9))
        insert_cost_ledger_entry(conn, _entry("gamma-skill", input_tok=5, usd=0.05))
        result = aggregate_cost_by_skill(conn)
    finally:
        conn.close()

    assert None not in result
    assert "" not in result
    assert set(result) == {"gamma-skill"}
    assert result["gamma-skill"]["total_tok"] == 5
