"""Tests for #798: the P - N bound as a fifth Stage 2 operating characteristic.

Each acceptance criterion of #798 has one named test here. The fixture
``tests/fixtures/stage2_798/per_look_pre_798.tsv`` was written by the
simulator at ``origin/main`` ff0f557, before this change, on the grid that
``_GOLDEN_GRID`` rebuilds.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

_REPO = Path(__file__).resolve().parents[1]
_SCREEN_DIR = _REPO / "scripts" / "screens" / "419"
_GOLDEN = _REPO / "tests" / "fixtures" / "stage2_798" / "per_look_pre_798.tsv"


def _load(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load("simulate_stage1a_regime_685")
reg = _load("simulate_stage1a_regime_685_stage2")

_DESIGNS = (
    ("anytime", "union", 0.0209),
    ("anytime-tuned", "direct", 0.0209),
    ("fixed-n-betting", "direct", 0.0105),
    ("fixed-n-score", "direct", 0.0209),
)


def _golden_grid() -> list[tuple[Any, Any]]:
    return [
        (cell, reg.Design(30, npp, fn, stopping, alpha, 1.0))
        for cell in (reg.Cell(0.65, 0.35, 0.35), reg.Cell(0.35, 0.35, 0.30))
        for npp in (1.0, 0.5)
        for stopping, fn, alpha in _DESIGNS
    ]


def _table(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.rstrip("\n").split("\n")
    return lines[0].split("\t"), [line.split("\t") for line in lines[1:]]


def test_every_row_carries_p_pn_bounded_and_its_mc_se() -> None:
    rows = [reg.run_cell(c, d, replicates=60, seed=685) for c, d in _golden_grid()]
    for row in rows:
        assert 0.0 <= row.p_pn_bounded <= 1.0, row.design
        expected_se = math.sqrt(row.p_pn_bounded * (1.0 - row.p_pn_bounded) / row.replicates)
        assert math.isclose(row.se_pn_bounded, expected_se), row.design
    header, body = _table(reg.per_look_tsv(rows))
    assert header[-2:] == ["p_pn_bounded", "se_pn_bounded"]
    assert all(cells[-2] != "NA" and cells[-1] != "NA" for cells in body)


def test_pn_interval_uses_0_0125_per_side_not_0_025() -> None:
    rng = np.random.default_rng(798)
    placebo = (rng.random((3, 120)) < 0.35).astype(np.int64)
    null = (rng.random((3, 90)) < 0.35).astype(np.int64)
    lo, hi = reg.pn_interval(placebo, null)
    for r in range(3):
        p, n = placebo[r].tolist(), null[r].tolist()

        def at(alpha: float, p: list[int] = p, n: list[int] = n) -> tuple[float, float]:
            return (
                one_sided_betting_bound(p, alpha=alpha, side="lower")
                - one_sided_betting_bound(n, alpha=alpha, side="upper"),
                one_sided_betting_bound(p, alpha=alpha, side="upper")
                - one_sided_betting_bound(n, alpha=alpha, side="lower"),
            )

        lo_0125, hi_0125 = at(0.0125)
        lo_025, hi_025 = at(0.025)
        assert math.isclose(lo[r], lo_0125, abs_tol=1e-9)
        assert math.isclose(hi[r], hi_0125, abs_tol=1e-9)
        assert lo[r] < lo_025 and hi[r] > hi_025, "the 0.0125 interval must be the wider one"


def test_p_pn_bounded_holds_its_level_where_p_minus_n_is_0_20() -> None:
    assert {round(c.p_placebo - c.p_null, 10) for c in reg.PN_CALIBRATION_CELLS} == {-0.2, 0.2}
    rows = reg.pn_calibration_rows([(400, 1.0), (400, 0.5)], replicates=400, seed=685)
    assert len(rows) == 2 * len(reg.PN_CALIBRATION_CELLS)
    for row in rows:
        limit = reg.PN_ALPHA_TOTAL + 3.0 * row.se_pn_bounded
        assert row.p_pn_bounded <= limit, row
        assert row.holds_level


def test_pn_calibration_flags_a_row_above_its_limit() -> None:
    cell = reg.PN_CALIBRATION_CELLS[0]
    assert reg.pn_calibration_holds(0.04, replicates=400)
    assert not reg.pn_calibration_holds(0.10, replicates=400)
    assert cell.p_full == cell.p_placebo


def test_no_pre_existing_column_changes() -> None:
    rows = [reg.run_cell(c, d, replicates=60, seed=685) for c, d in _golden_grid()]
    new_header, new_body = _table(reg.per_look_tsv(rows))
    old_header, old_body = _table(_GOLDEN.read_text(encoding="utf-8"))
    assert new_header == [*old_header, "p_pn_bounded", "se_pn_bounded"]
    assert [cells[: len(old_header)] for cells in new_body] == old_body


def test_main_writes_the_headline_column_and_the_pn_calibration_file(tmp_path: Path) -> None:
    out = tmp_path / "out"
    grid = [(c, d) for c, d in _golden_grid() if d.stopping == "fixed-n-betting"][:1]
    reg.main(
        ["--out", str(out), "--replicates", "60", "--workers", "1", "--seed", "685"], grid=grid
    )
    headline = (out / "headline_by_accounting.md").read_text(encoding="utf-8")
    assert "P(P - N bounded) |" in headline
    assert "P(P - N bounded)" not in (out / "summary.md").read_text(encoding="utf-8")
    header, body = _table((out / "pn_calibration.tsv").read_text(encoding="utf-8"))
    assert header[-3:] == ["p_pn_bounded", "se_pn_bounded", "holds_level"]
    assert len(body) == len(reg.PN_CALIBRATION_CELLS)


def test_rebuild_reads_a_per_look_file_without_the_new_columns(tmp_path: Path) -> None:
    (tmp_path / "per_look.tsv").write_text(_GOLDEN.read_text(encoding="utf-8"), encoding="utf-8")
    rows, _ = reg.rows_from_output_dir(tmp_path)
    assert rows and all(math.isnan(r.p_pn_bounded) for r in rows)
