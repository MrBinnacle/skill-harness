"""Tests for #718: Stage 2 of #685 — stopping design x pairs.

Each acceptance criterion of #718 has at least one named test here. The tests
assert external behaviour of the simulator script under
``scripts/screens/419/simulate_stage1a_regime_685_stage2.py``; they do not
inspect internal branching.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"
_REPO = Path(__file__).resolve().parents[1]
_DATA_DIR = _REPO / "docs" / "findings" / "data" / "stage1a-regime-685-stage2"
_STAGE1_DATA = _REPO / "docs" / "findings" / "data" / "stage1a-regime-685"


def _load(name: str) -> ModuleType:
    """Import a screen module by file path, reusing any already-loaded copy.

    Both this file and tests/test_simulate_stage1a_regime_685.py load
    ``simulate_stage1a_regime_685`` at collection time. A second load under
    the same sys.modules name replaces the module object while the first
    test module keeps a reference to the old one, and ProcessPoolExecutor
    then fails to pickle ``_run`` (the function's ``__module__`` resolves to
    a different object). Reuse keeps every reference on one copy.
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_s685 = _load("simulate_stage1a_regime_685")
_a650 = _load("simulate_a_design")
reg = _load("simulate_stage1a_regime_685_stage2")


def _split_tsv(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.rstrip("\n").split("\n")
    return lines[0].split("\t"), [line.split("\t") for line in lines[1:]]


def _hand_row(
    cell: Any,
    design: Any,
    *,
    p_pass: float,
    p_cut: float,
    p_fp_half: float | None = None,
    p_fn_half: float | None = None,
    replicates: int = 200,
    expected_epochs: float | None = None,
    holds: bool | None = None,
) -> Any:
    look = design.n_pairs
    fp = p_pass if p_fp_half is None else p_fp_half
    fn = p_pass if p_fn_half is None else p_fn_half
    epochs = float(design.total_epochs) if expected_epochs is None else expected_epochs
    row = reg.s685.LookRow(
        look=look,
        p_pass=p_pass,
        p_cut=p_cut,
        p_cant_tell_yet=max(0.0, 1.0 - p_pass - p_cut),
        se_pass=0.0,
        expected_pairs=float(look),
        expected_epochs=epochs,
    )
    if holds is None:
        holds = reg._row_calibration_holds_for_alpha(
            cell=cell,
            p_pass=p_pass,
            p_cut=p_cut,
            pass_alpha=design.pass_alpha,
            replicates=replicates,
        )
    return reg.Row(
        cell=cell,
        design=design,
        replicates=replicates,
        p_fp_half=fp,
        p_fn_half=fn,
        p_joint_pass=p_pass,
        p_cut=p_cut,
        p_cant_tell_yet=max(0.0, 1.0 - p_pass - p_cut),
        se_pass=0.0,
        expected_pairs=float(look),
        expected_epochs=epochs,
        holds_level=holds,
        per_look=(row,),
    )


# ---------------------------------------------------------------------------
# Criterion 1: full grid, no calls, exit non-zero on calibration failure
# ---------------------------------------------------------------------------


def test_script_module_has_no_model_or_network_import() -> None:
    """The simulator imports numpy and local modules only; no client, no HTTP."""
    source = (_SCREEN_DIR / "simulate_stage1a_regime_685_stage2.py").read_text(encoding="utf-8")
    for banned in ("urllib", "requests", "httpx", "openai", "anthropic", "socket"):
        assert banned not in source, f"the stage-2 simulator must not reference {banned}"


def test_main_exits_zero_when_calibration_holds(tmp_path: Path) -> None:
    grid = [
        (
            reg.Cell(0.55, 0.35, 0.35),
            reg.Design(n_pairs=30, null_per_pair=1.0, fn_construction="direct", stopping="anytime"),
        ),
        (
            reg.Cell(0.55, 0.35, 0.35),
            reg.Design(
                n_pairs=30,
                null_per_pair=1.0,
                fn_construction="direct",
                stopping="fixed-n-score",
                pass_alpha=0.0209,
            ),
        ),
    ]
    code = reg.main(
        ["--out", str(tmp_path / "out"), "--replicates", "80", "--workers", "1", "--seed", "685"],
        grid=grid,
    )
    assert code == 0
    assert (tmp_path / "out" / "per_look.tsv").is_file()
    assert (tmp_path / "out" / "summary.md").is_file()


def test_main_exits_non_zero_when_a_non_score_design_fails_calibration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rule loosened past the declared alpha on an anytime-tuned row must fail the run."""
    grid = [
        (
            reg.Cell(0.55, 0.35, 0.35),
            reg.Design(
                n_pairs=30,
                null_per_pair=1.0,
                fn_construction="direct",
                stopping="anytime-tuned",
                pass_alpha=0.0209,
                starting_wealth=1.0,
            ),
        ),
    ]
    original = reg.run_cell

    def _loosened(cell: Any, design: Any, **kwargs: Any) -> Any:
        kwargs["pass_alpha_override"] = 0.60
        return original(cell, design, **kwargs)

    monkeypatch.setattr(reg, "run_cell", _loosened)
    code = reg.main(
        ["--out", str(tmp_path / "out"), "--replicates", "200", "--workers", "1", "--seed", "685"],
        grid=grid,
    )
    assert code == 1


def test_main_rebuild_makes_no_simulation_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    grid = [
        (
            reg.Cell(0.55, 0.35, 0.35),
            reg.Design(n_pairs=30, null_per_pair=0.5, fn_construction="direct", stopping="anytime"),
        ),
    ]
    reg.main(
        ["--out", str(out), "--replicates", "60", "--workers", "1", "--seed", "685"],
        grid=grid,
    )
    written = (out / "summary.md").read_text(encoding="utf-8")

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("rebuild must not call run_cell")

    monkeypatch.setattr(reg, "run_cell", _boom)
    code = reg.main(["--out", str(out), "--rebuild"], grid=grid)
    assert (out / "summary.md").read_text(encoding="utf-8") == written
    assert code in (0, 1)


def test_main_rebuild_reproduces_summary_and_exit_code(tmp_path: Path) -> None:
    out = tmp_path / "out"
    grid = [
        (
            reg.Cell(0.55, 0.35, 0.30),
            reg.Design(n_pairs=30, null_per_pair=0.5, fn_construction="direct", stopping="anytime"),
        ),
        (
            reg.Cell(0.65, 0.25, 0.30),
            reg.Design(
                n_pairs=30,
                null_per_pair=1.0,
                fn_construction="direct",
                stopping="fixed-n-betting",
                pass_alpha=0.0209,
            ),
        ),
    ]
    run_code = reg.main(
        ["--out", str(out), "--replicates", "80", "--workers", "1", "--seed", "685"],
        grid=grid,
    )
    written = (out / "summary.md").read_text(encoding="utf-8")
    rebuild_code = reg.main(["--out", str(out), "--rebuild"], grid=grid)
    rebuilt = (out / "summary.md").read_text(encoding="utf-8")
    assert rebuilt == written
    assert rebuild_code == run_code


# ---------------------------------------------------------------------------
# Criterion 2: calibration covers every row of every design
# ---------------------------------------------------------------------------


def test_calibration_predicate_covers_the_fn_margin_cell() -> None:
    cell = reg.Cell(0.60, 0.30, 0.40)
    assert cell.d == pytest.approx(0.30)
    assert reg.true_fn_diff(cell) == pytest.approx(0.20)
    assert reg.is_pass_calibration_cell(cell)
    assert reg.is_cut_calibration_cell(cell)


def test_calibration_uses_the_rows_own_pass_alpha() -> None:
    cell = reg.Cell(0.55, 0.35, 0.35)
    design = reg.Design(
        n_pairs=97,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-betting",
        pass_alpha=0.005,
    )
    limit = 0.005 + _a650.calibration_tolerance(200, 0.005)
    over = _hand_row(cell, design, p_pass=limit + 0.05, p_cut=0.0)
    under = _hand_row(cell, design, p_pass=limit - 0.01, p_cut=0.0)
    assert reg.row_calibration_holds(over) is False
    assert reg.row_calibration_holds(under) is True


def test_cut_calibration_uses_the_futility_level() -> None:
    cell = reg.Cell(0.75, 0.35, 0.35)
    design = reg.Design(n_pairs=97, stopping="anytime-tuned", pass_alpha=0.0209)
    cut_limit = 0.05 + _a650.calibration_tolerance(200, 0.05)
    over = _hand_row(cell, design, p_pass=0.0, p_cut=cut_limit + 0.05)
    under = _hand_row(cell, design, p_pass=0.0, p_cut=0.0)
    assert reg.row_calibration_holds(over) is False
    assert reg.row_calibration_holds(under) is True


def test_calibration_read_covers_every_declared_design() -> None:
    """Every stopping design's calibration failure is visible to the read."""
    cell = reg.Cell(0.55, 0.35, 0.35)
    for stopping, alpha, w0 in (
        ("anytime", 0.0209, 1.0),
        ("anytime-tuned", 0.0209, 0.5),
        ("fixed-n-betting", 0.0105, 1.0),
        ("fixed-n-score", 0.0209, 1.0),
    ):
        design = reg.Design(
            n_pairs=97,
            null_per_pair=1.0,
            fn_construction="direct",
            stopping=stopping,
            pass_alpha=alpha,
            starting_wealth=w0,
        )
        bad = _hand_row(cell, design, p_pass=0.40, p_cut=0.0)
        assert reg.row_calibration_holds(bad) is False, f"{stopping} must be calibrated"


def test_calibration_exit_code_covers_fixed_n_rows() -> None:
    """Mutant 9 pins: a fixed-n-betting failure must set the exit code to 1."""
    cell = reg.Cell(0.55, 0.35, 0.35)
    design = reg.Design(
        n_pairs=97,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-betting",
        pass_alpha=0.0209,
    )
    bad = _hand_row(cell, design, p_pass=0.40, p_cut=0.0, holds=False)
    ok = _hand_row(cell, design, p_pass=0.0, p_cut=0.0, holds=True)
    assert reg.calibration_exit_code([bad]) == 1
    assert reg.calibration_exit_code([ok]) == 0
    assert reg.calibration_exit_code([bad, ok]) == 1


def test_calibration_set_includes_every_pass_and_cut_error_cell() -> None:
    cells = [
        reg.Cell(round(p_p + d, 10), p_p, p_n)
        for p_p in reg.BASELINES
        for p_n in reg.BASELINES
        for d in (0.00, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
    ]
    pass_cells = {(c.p_placebo, c.p_null, c.d) for c in cells if reg.is_pass_calibration_cell(c)}
    expected_pass = {
        (c.p_placebo, c.p_null, c.d)
        for c in cells
        if c.d <= 0.20 + 1e-9 or reg.true_fn_diff(c) <= 0.20 + 1e-9
    }
    assert pass_cells == expected_pass
    assert (0.30, 0.40, 0.30) in pass_cells
    cut_cells = {(c.p_placebo, c.p_null, c.d) for c in cells if reg.is_cut_calibration_cell(c)}
    expected_cut = {(c.p_placebo, c.p_null, c.d) for c in cells if c.d >= 0.20 - 1e-9}
    assert cut_cells == expected_cut


# ---------------------------------------------------------------------------
# Criterion 3: fixed-n-score level failure is labelled, excluded, non-fatal
# ---------------------------------------------------------------------------


def test_fixed_n_score_calibration_failure_is_labelled_and_non_fatal(tmp_path: Path) -> None:
    cell = reg.Cell(0.55, 0.35, 0.35)
    score_bad = reg.Design(
        n_pairs=30,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    tuned_bad = reg.Design(
        n_pairs=30,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="anytime-tuned",
        pass_alpha=0.0209,
        starting_wealth=1.0,
    )
    bad_score = _hand_row(cell, score_bad, p_pass=0.40, p_cut=0.0, holds=False)
    bad_tuned = _hand_row(cell, tuned_bad, p_pass=0.40, p_cut=0.0, holds=False)
    assert reg.row_calibration_holds(bad_score) is False
    assert reg.row_calibration_holds(bad_tuned) is False
    assert reg.is_nonfatal_calibration_failure(bad_score) is True, (
        "score failures must be labelled, not fatal"
    )
    assert reg.is_nonfatal_calibration_failure(bad_tuned) is False, (
        "non-score failures must be fatal"
    )
    assert reg.headline_includes(bad_score) is False, "failing score rows stay out of the headline"
    assert reg.calibration_exit_code([bad_score]) == 0
    assert reg.calibration_exit_code([bad_tuned]) == 1


def test_headline_excludes_fixed_n_score_rows_that_fail_calibration() -> None:
    """A score row that fails level must not supply the smallest priced config.

    The fixture fills all three diagonal cells at d = 0.30 and at d = 0.10,
    for both the failing 100-pair design and the holding 300-pair design.
    """
    score_bad = reg.Design(
        n_pairs=100,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    score_ok = reg.Design(
        n_pairs=300,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    rows: list[Any] = []
    for design, holds, rate in ((score_bad, False, 0.95), (score_ok, True, 0.85)):
        for p_p, p_n in ((0.30, 0.30), (0.35, 0.35), (0.40, 0.40)):
            rows.append(
                _hand_row(
                    reg.Cell(round(p_p + 0.30, 10), p_p, p_n),
                    design,
                    p_pass=rate,
                    p_cut=0.0,
                    holds=holds,
                )
            )
            rows.append(
                _hand_row(
                    reg.Cell(round(p_p + 0.10, 10), p_p, p_n),
                    design,
                    p_pass=0.0,
                    p_cut=rate,
                    holds=holds,
                )
            )
    assert not reg.headline_includes(rows[0])
    assert reg.headline_includes(rows[6])
    headline = reg.headline_rows(rows)
    row = next(
        h
        for h in headline
        if h.stopping == "fixed-n-score"
        and math.isclose(h.pass_alpha, 0.0209, abs_tol=1e-9)
        and math.isclose(h.target, 0.80, abs_tol=1e-9)
    )
    assert row.reached
    assert row.n_pairs == 300, "the failing 100-pair score row must be excluded"
    assert row.any_row_holds_level is True


def test_headline_excludes_a_configuration_with_a_failed_required_diagonal_row() -> None:
    """A required row that fails calibration cannot supply the headline minimum."""
    design = reg.Design(
        n_pairs=100,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    rows: list[Any] = []
    for d, p_pass, p_cut in ((0.30, 0.95, 0.0), (0.10, 0.0, 0.95)):
        for p_p, p_n in ((0.30, 0.30), (0.35, 0.35), (0.40, 0.40)):
            rows.append(
                _hand_row(
                    reg.Cell(round(p_p + d, 10), p_p, p_n),
                    design,
                    p_pass=p_pass,
                    p_cut=p_cut,
                    holds=not (d == 0.30 and p_p == 0.30),
                )
            )
    headline = reg.headline_rows(rows)
    row = next(
        h
        for h in headline
        if h.stopping == "fixed-n-score" and math.isclose(h.target, 0.80, abs_tol=1e-9)
    )
    assert row.reached is False
    assert row.missing_half == "missing d=0.30 diagonal cell (0.30, 0.30)"


def test_summary_says_score_failures_are_excluded_and_nonfatal() -> None:
    summary = reg.summary_md([], replicates=200, seed=685)
    assert "Rows that fail calibration are excluded." in summary
    assert (
        "fixed-n-score row that\nfails is labelled as not holding its level and does not "
        "fail the run." in summary
    )
    assert "excluded unless they are fixed-n-score" not in summary


# ---------------------------------------------------------------------------
# Criterion 4: regression — anytime cell at seed 685 matches committed #685
# ---------------------------------------------------------------------------


def test_anytime_cell_matches_the_committed_685_row() -> None:
    """100 pairs, null_pp 1.0, direct, d = 0.30, seed 685, 2000 replicates.

    The stage-2 anytime path delegates to the #685 simulator, so the cap-look
    rates must match the committed #685 per_look.tsv exactly. The 400-pair
    diagonal minimum the ticket names (0.2335) is read from the same committed
    file; the re-run uses the cheaper 100-pair family so the suite stays inside
    a CI budget.
    """
    cols, rows = _split_tsv((_STAGE1_DATA / "per_look.tsv").read_text(encoding="utf-8"))
    i = {name: idx for name, idx in ((c, n) for n, c in enumerate(cols))}
    committed_400 = {
        float(row[i["p_pass"]])
        for row in rows
        if row[i["n_full"]] == "400"
        and row[i["null_per_pair"]] == "1.00"
        and row[i["fn_construction"]] == "direct"
        and row[i["stopping"]] == "anytime"
        and row[i["d"]] == "0.30"
        and row[i["p_placebo"]] == row[i["p_null"]]
        and row[i["look"]] == "400"
    }
    assert committed_400, "the committed #685 data must carry the 400-pair diagonal"
    assert min(committed_400) == pytest.approx(0.2335), (
        "the ticket names the 400-pair diagonal minimum as 0.2335"
    )

    committed = {
        (row[i["p_full"]], row[i["p_placebo"]], row[i["p_null"]], row[i["look"]]): (
            float(row[i["p_pass"]]),
            float(row[i["p_cut"]]),
        )
        for row in rows
        if row[i["n_full"]] == "100"
        and row[i["null_per_pair"]] == "1.00"
        and row[i["fn_construction"]] == "direct"
        and row[i["stopping"]] == "anytime"
        and row[i["d"]] == "0.30"
        and row[i["p_placebo"]] == row[i["p_null"]]
        and row[i["look"]] == "100"
    }
    assert committed, "the committed #685 data must carry the 100-pair diagonal d=0.30 cell"

    design = reg.Design(
        n_pairs=100,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="anytime",
        pass_alpha=0.0209,
        starting_wealth=1.0,
    )
    for key, rates in committed.items():
        p_full_s, p_p_s, p_n_s, _look_s = key
        exp_pass, exp_cut = rates
        cell = reg.Cell(float(p_full_s), float(p_p_s), float(p_n_s))
        row = reg.run_cell(cell, design, replicates=2000, seed=685)
        last = row.per_look[-1]
        assert last.look == 100
        assert last.p_pass == pytest.approx(exp_pass, abs=1e-12), (
            f"cell ({p_full_s}, {p_p_s}, {p_n_s}): p_pass {last.p_pass} != committed {exp_pass}"
        )
        assert last.p_cut == pytest.approx(exp_cut, abs=1e-12), (
            f"cell ({p_full_s}, {p_p_s}, {p_n_s}): p_cut {last.p_cut} != committed {exp_cut}"
        )
        assert row.p_joint_pass == pytest.approx(exp_pass, abs=1e-12)
        assert row.replicates == 2000


def test_anytime_stopping_label_agrees_with_the_simulation_path() -> None:
    """Mutant 10: a fixed-n-score row must not be produced by the anytime path."""
    cell = reg.Cell(0.85, 0.25, 0.30)
    anytime = reg.Design(
        n_pairs=20, null_per_pair=1.0, fn_construction="direct", stopping="anytime"
    )
    score = reg.Design(
        n_pairs=20,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    r_any = reg.run_cell(cell, anytime, replicates=80, seed=7)
    r_score = reg.run_cell(cell, score, replicates=80, seed=7)
    assert r_any.design.stopping == "anytime"
    assert r_score.design.stopping == "fixed-n-score"
    assert len(r_any.per_look) == anytime.n_pairs, "anytime records every look"
    assert len(r_score.per_look) == 1, "fixed-n-score reads once at n"
    assert r_score.per_look[0].look == score.n_pairs
    assert r_score.expected_epochs == float(score.total_epochs)
    assert r_any.per_look[0].look == 1


# ---------------------------------------------------------------------------
# Criterion 5: reduced grid in the test suite; committed data holds it
# ---------------------------------------------------------------------------


def test_reduced_grid_covers_every_stopping_design() -> None:
    grid = reg.reduced_grid()
    assert grid, "the reduced grid must not be empty"
    stoppings = {design.stopping for _cell, design in grid}
    assert stoppings == set(reg.STOPPINGS)
    nulls = {design.null_per_pair for _cell, design in grid}
    assert nulls == set(reg.REDUCED_NULL_PER_PAIR)
    pairs = {design.n_pairs for _cell, design in grid}
    assert pairs == set(reg.REDUCED_PAIRS)
    fixed_alphas = {
        design.pass_alpha for _cell, design in grid if design.stopping.startswith("fixed-n")
    }
    assert fixed_alphas == set(reg.FIXED_PASS_ALPHAS)
    wealths = {
        design.starting_wealth for _cell, design in grid if design.stopping == "anytime-tuned"
    }
    assert wealths == set(reg.STARTING_WEALTHS)
    for _cell, design in grid:
        if design.stopping != "anytime":
            assert design.fn_construction == "direct", (
                f"{design.stopping} must use direct F - N only"
            )


def test_reduced_grid_runs_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "reduced"
    code = reg.main(
        ["--out", str(out), "--replicates", "60", "--workers", "1", "--seed", "685", "--reduced"],
    )
    assert code in (0, 1)
    cols, rows = _split_tsv((out / "per_look.tsv").read_text(encoding="utf-8"))
    for name in (*reg.DESIGN_FIELDS, "replicates", *_reg_rate_names(cols)):
        assert name in cols, f"reduced per_look.tsv is missing {name}"
    seen_stoppings = {row[cols.index("stopping")] for row in rows}
    assert seen_stoppings == set(reg.STOPPINGS)
    for row in rows:
        assert len(row) == len(cols)
        assert int(row[cols.index("replicates")]) == 60
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "## Headline" in summary
    assert "Replicates per cell: 60." in summary


def _reg_rate_names(cols: list[str]) -> tuple[str, ...]:
    return tuple(c for c in cols if c.startswith("p_"))


def test_committed_data_holds_the_reduced_grid_with_replicate_counts() -> None:
    """The committed directory must contain at least the reduced grid."""
    path = _DATA_DIR / "per_look.tsv"
    assert path.is_file(), "the stage-2 per_look.tsv must be committed"
    cols, rows = _split_tsv(path.read_text(encoding="utf-8"))
    for name in (*reg.DESIGN_FIELDS, "replicates", *_RATE_NAMES):
        assert name in cols, f"committed per_look.tsv is missing {name}"
    i = {name: idx for name, idx in ((c, n) for n, c in enumerate(cols))}
    assert rows, "the committed per_look.tsv has no data rows"
    replicates_seen: set[str] = set()
    committed_keys: set[tuple[str, ...]] = set()
    for row in rows:
        assert len(row) == len(cols)
        reps = row[i["replicates"]]
        assert reps and int(reps) > 0, "every row must carry a positive replicate count"
        replicates_seen.add(reps)
        committed_keys.add(
            (
                row[i["n_full"]],
                row[i["null_per_pair"]],
                row[i["fn_construction"]],
                row[i["stopping"]],
                row[i["pass_alpha"]],
                row[i["starting_wealth"]],
                row[i["p_full"]],
                row[i["p_placebo"]],
                row[i["p_null"]],
            )
        )
    assert len(replicates_seen) == 1, "the committed run must state one replicate count"
    for cell, design in reg.reduced_grid():
        key = (
            str(design.n_full),
            f"{design.null_per_pair:.2f}",
            design.fn_construction,
            design.stopping,
            f"{design.pass_alpha:.6f}",
            f"{design.starting_wealth:.2f}",
            f"{cell.p_full:.2f}",
            f"{cell.p_placebo:.2f}",
            f"{cell.p_null:.2f}",
        )
        assert key in committed_keys, f"committed data is missing reduced-grid row {key}"
    assert (_DATA_DIR / "summary.md").is_file()
    assert (_DATA_DIR / "run_meta.json").is_file()
    scratch = _REPO / ".scratch" / "issue-718" / "data"
    assert not scratch.exists(), "stage-2 output must not land under .scratch/"


_RATE_NAMES = (
    "p_fp_half",
    "p_fn_half",
    "p_joint_pass",
    "p_cut",
    "p_cant_tell_yet",
    "se_pass",
)


def test_committed_summary_is_what_rebuild_writes(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    for name in ("per_look.tsv", "run_meta.json"):
        (out / name).write_bytes((_DATA_DIR / name).read_bytes())
    assert reg.main(["--out", str(out), "--rebuild"]) in (0, 1)
    committed = (_DATA_DIR / "summary.md").read_text(encoding="utf-8")
    assert (out / "summary.md").read_text(encoding="utf-8") == committed
    assert "## Headline" in committed
    for stopping in reg.STOPPINGS:
        assert stopping in committed


# ---------------------------------------------------------------------------
# Criterion 6: negative control — loosened calibration fails per new design
# ---------------------------------------------------------------------------


def test_negative_control_loosened_rule_fails_anytime_tuned() -> None:
    cell = reg.Cell(0.55, 0.35, 0.30)
    design = reg.Design(
        n_pairs=40,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="anytime-tuned",
        pass_alpha=0.0209,
        starting_wealth=1.0,
    )
    row = reg.run_cell(cell, design, replicates=400, seed=685, pass_alpha_override=0.60)
    limit = reg.PASS_ALPHA + _a650.calibration_tolerance(400)
    assert row.p_joint_pass > limit, "a loosened anytime-tuned rule must over-pass"
    assert row.design.pass_alpha == 0.0209, "the row must still declare the registered alpha"
    assert reg.row_calibration_holds(row) is False
    assert reg.calibration_exit_code([row]) == 1


def test_negative_control_loosened_rule_fails_fixed_n_betting() -> None:
    cell = reg.Cell(0.55, 0.35, 0.30)
    design = reg.Design(
        n_pairs=40,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-betting",
        pass_alpha=0.0209,
    )
    row = reg.run_cell(cell, design, replicates=400, seed=685, pass_alpha_override=0.60)
    limit = reg.PASS_ALPHA + _a650.calibration_tolerance(400)
    assert row.p_joint_pass > limit, "a loosened fixed-n-betting rule must over-pass"
    assert reg.row_calibration_holds(row) is False
    assert reg.calibration_exit_code([row]) == 1


def test_negative_control_loosened_rule_fails_fixed_n_score() -> None:
    """A fixed-n-score row that fails is labelled, but the read still sees it."""
    cell = reg.Cell(0.55, 0.35, 0.30)
    design = reg.Design(
        n_pairs=40,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    row = reg.run_cell(cell, design, replicates=400, seed=685, pass_alpha_override=0.60)
    limit = reg.PASS_ALPHA + _a650.calibration_tolerance(400)
    assert row.p_joint_pass > limit, "a loosened fixed-n-score rule must over-pass"
    assert reg.row_calibration_holds(row) is False
    assert reg.is_nonfatal_calibration_failure(row) is True, (
        "score failures are labelled, not fatal"
    )
    assert reg.headline_includes(row) is False
    assert reg.calibration_exit_code([row]) == 0


# ---------------------------------------------------------------------------
# Mutants 1-3: fixed-n interim look; fixed-n anytime bound; score margin
# ---------------------------------------------------------------------------


def test_fixed_n_designs_read_once_at_n() -> None:
    """Mutant 1: a fixed-n row must not stop at an interim look."""
    cell = reg.Cell(0.85, 0.25, 0.30)
    for stopping in ("fixed-n-betting", "fixed-n-score"):
        design = reg.Design(
            n_pairs=30,
            null_per_pair=1.0,
            fn_construction="direct",
            stopping=stopping,
            pass_alpha=0.0209,
        )
        row = reg.run_cell(cell, design, replicates=120, seed=11)
        assert row.design.stopping == stopping
        assert len(row.per_look) == 1
        assert row.per_look[0].look == 30
        assert row.expected_epochs == float(design.total_epochs)
        assert row.expected_pairs == 30.0


def test_fixed_n_betting_uses_horizon_scaled_bets_not_time_scaled() -> None:
    """Mutant 2: the fixed-n bound must be scaled for n, not for t."""
    n = 20
    rng = np.random.default_rng(3)
    xs = (rng.random((40, n)) < 0.65).astype(np.float64)
    xs = (xs * 2 - 1 + 1) / 2.0  # in [0, 1]
    alpha = 0.0209
    m0 = 0.6
    log_w = reg.fixed_n_log_wealth(xs, alpha, m0, upward=True)
    # Hand path: lambda_t = min(sqrt(2 log(1/alpha)/(n*var_hat_t)), trunc)
    numer = 2.0 * math.log(1.0 / alpha)
    trunc = 0.5 / m0
    for r in range(xs.shape[0]):
        mean_hat, var_hat, acc = 0.5, 0.25, 0.0
        for k in range(n):
            t = float(k + 1)
            lam = min(math.sqrt(numer / (max(var_hat, 1e-6) * n)), trunc)
            acc += math.log1p(lam * (xs[r, k] - m0))
            resid = xs[r, k] - mean_hat
            mean_hat = mean_hat + (xs[r, k] - mean_hat) / (t + 1.0)
            var_hat = max(var_hat + (resid * resid - var_hat) / (t + 1.0), 1e-6)
        assert log_w[r] == pytest.approx(acc, abs=1e-9)
    # The horizon-scaled path differs from a t-scaled path on this fixture.
    t_scaled = np.zeros(xs.shape[0])
    for r in range(xs.shape[0]):
        mean_hat, var_hat, acc = 0.5, 0.25, 0.0
        for k in range(n):
            t = float(k + 1)
            lam = min(math.sqrt(numer / (max(var_hat, 1e-6) * t * math.log(1.0 + t))), trunc)
            acc += math.log1p(lam * (xs[r, k] - m0))
            resid = xs[r, k] - mean_hat
            mean_hat = mean_hat + (xs[r, k] - mean_hat) / (t + 1.0)
            var_hat = max(var_hat + (resid * resid - var_hat) / (t + 1.0), 1e-6)
        t_scaled[r] = acc
    assert not np.allclose(log_w, t_scaled), (
        "horizon-scaled and time-scaled wealth must disagree on this fixture"
    )


def test_fixed_n_betting_run_cell_matches_horizon_scaling_not_anytime_at_n() -> None:
    """Mutant 2, run_cell level: the written row comes from the horizon-scaled bound."""
    cell = reg.Cell(0.65, 0.30, 0.30)
    design = reg.Design(
        n_pairs=80,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-betting",
        pass_alpha=0.0209,
    )
    row = reg.run_cell(cell, design, replicates=400, seed=77)
    # Recompute both constructions on the same draws.
    full, placebo, null_all, null_draws, fn_mask = reg._draw_streams(
        cell, design, replicates=400, seed=77
    )
    _nu, xs_fn = reg._null_used_and_fn_obs(full, placebo, null_all, null_draws, fn_mask)
    xs_fp = (full - placebo + 1) / 2.0
    horizon_pass = reg.fixed_n_rejects(xs_fp, 0.0209, 0.6, upward=True)
    anytime_at_n = (2 * reg.s685._bound(xs_fp, 0.0209, "lower") - 1) >= reg.BOUNDARY
    fn_horizon = (
        reg.fixed_n_rejects(xs_fn, 0.0209, 0.6, upward=True)
        if xs_fn.shape[1] > 0
        else np.zeros(xs_fp.shape[0], dtype=np.bool_)
    )
    horizon_rate = float(np.mean(horizon_pass & fn_horizon))
    anytime_rate = float(np.mean(anytime_at_n & fn_horizon))
    assert horizon_rate != pytest.approx(anytime_rate, abs=1e-9), (
        "the fixture must separate horizon-scaled from anytime-at-n decisions"
    )
    assert row.p_fp_half == pytest.approx(float(np.mean(horizon_pass)), abs=1e-12), (
        "run_cell must report the horizon-scaled F - P half rate"
    )
    assert row.p_joint_pass == pytest.approx(horizon_rate, abs=1e-12)


def test_tango_score_equals_mcnemar_at_delta0_zero() -> None:
    """Mutant 3 pins the margin: at delta0 = 0 the Tango z is McNemar's."""
    for b, c, n in ((10, 4, 40), (20, 20, 50), (30, 5, 60), (0, 0, 30)):
        mcnemar = (b - c) / math.sqrt(b + c) if (b + c) > 0 else 0.0
        assert reg.tango_score_z(b, c, n, 0.0) == pytest.approx(mcnemar, abs=1e-9)


def test_score_tests_use_the_registered_margin_0_20() -> None:
    """Mutant 3: delta0 = 0.20, not 0.0, on a fixture where the two disagree."""
    b, c, n = 40, 10, 80
    z_registered = reg.tango_score_z(b, c, n, 0.20)
    z_dropped = reg.tango_score_z(b, c, n, 0.0)
    assert z_registered != pytest.approx(z_dropped, abs=1e-6)
    mcnemar = (b - c) / math.sqrt(b + c)
    assert z_dropped == pytest.approx(mcnemar, abs=1e-9)
    # Under the registered margin the statistic is smaller: the test demands
    # more than the raw paired difference.
    assert z_registered < z_dropped
    fm_reg = reg.farrington_manning_z(50, 80, 30, 80, 0.20)
    fm_drop = reg.farrington_manning_z(50, 80, 30, 80, 0.0)
    assert fm_reg != pytest.approx(fm_drop, abs=1e-6), (
        "dropping the margin from the F - N score test must change the statistic"
    )


def test_fixed_n_score_run_cell_holds_its_level_at_the_margin_boundary() -> None:
    """Mutant 3, run_cell level: at d = 0.20 the score test must not over-pass.

    With delta0 = 0 the Tango statistic is McNemar's, which tests d = 0 and
    rejects far too often when the true d is 0.20. The registered margin keeps
    P(PASS) near the row's alpha on this cell.
    """
    cell = reg.Cell(0.55, 0.35, 0.35)
    design = reg.Design(
        n_pairs=200,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    row = reg.run_cell(cell, design, replicates=600, seed=685)
    limit = 0.0209 + _a650.calibration_tolerance(600)
    assert row.p_joint_pass <= limit + 1e-9, (
        "a margin-dropped score test would over-pass at the 0.20 boundary"
    )
    assert row.p_joint_pass < 0.15, "the registered margin keeps this cell near its level"


def test_fixed_n_score_applies_the_paired_statistic_to_fp_and_unpaired_to_fn() -> None:
    """Mutant 4: the paired statistic belongs on F - P, not on F - N."""
    cell = reg.Cell(0.70, 0.25, 0.40)  # F-P large, F-N = 0.30
    assert cell.d == pytest.approx(0.45)
    assert reg.true_fn_diff(cell) == pytest.approx(0.30)
    design = reg.Design(
        n_pairs=200,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    row = reg.run_cell(cell, design, replicates=400, seed=21)
    assert row.p_fp_half > 0.5, "the F - P half must clear under a large paired contrast"
    assert row.p_joint_pass <= row.p_fp_half + 1e-12
    # On a cell where F - P is at the margin but F - N is not, joint PASS
    # cannot exceed the F - N half.
    cell2 = reg.Cell(0.55, 0.35, 0.55)
    assert reg.true_fn_diff(cell2) == pytest.approx(0.0)
    row2 = reg.run_cell(cell2, design, replicates=400, seed=22)
    assert row2.p_fn_half < 0.20, "the F - N half must stay low when F - N is 0.00"
    assert row2.p_joint_pass <= row2.p_fn_half + 1e-12


def test_joint_pass_requires_both_halves() -> None:
    """Mutant 5: joint PASS reads F - P and F - N, not F - P alone."""
    cell = reg.Cell(0.70, 0.25, 0.65)  # F-P = 0.45, F-N = 0.05
    assert reg.true_fn_diff(cell) == pytest.approx(0.05)
    design = reg.Design(
        n_pairs=200,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    row = reg.run_cell(cell, design, replicates=400, seed=23)
    assert row.p_fp_half > row.p_fn_half, "the F - P half must outpace the F - N half"
    assert row.p_joint_pass <= row.p_fn_half + 1e-12, "joint PASS cannot exceed the weaker half"


def test_pass_alpha_label_matches_computation() -> None:
    """Mutant 6: a row labelled 0.0105 must be computed at 0.0105."""
    cell = reg.Cell(0.65, 0.30, 0.30)
    tight = reg.Design(
        n_pairs=80,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-betting",
        pass_alpha=0.0105,
    )
    loose = reg.Design(
        n_pairs=80,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-betting",
        pass_alpha=0.0209,
    )
    r_tight = reg.run_cell(cell, tight, replicates=600, seed=31)
    r_loose = reg.run_cell(cell, loose, replicates=600, seed=31)
    assert r_tight.design.pass_alpha == 0.0105
    assert r_loose.design.pass_alpha == 0.0209
    assert r_tight.p_joint_pass < r_loose.p_joint_pass, (
        f"a stricter alpha must pass less often: {r_tight.p_joint_pass} vs {r_loose.p_joint_pass}"
    )
    cols, rows = _split_tsv(reg.per_look_tsv([r_tight, r_loose]))
    i_alpha = cols.index("pass_alpha")
    alphas = {float(row[i_alpha]) for row in rows}
    assert alphas == {0.0105, 0.0209}


def test_starting_wealth_changes_anytime_tuned_decisions() -> None:
    """Mutant 7: starting wealth 0.25 must not behave like 1.0."""
    cell = reg.Cell(0.75, 0.35, 0.35)
    base = reg.Design(
        n_pairs=100,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="anytime-tuned",
        pass_alpha=0.0209,
        starting_wealth=1.0,
    )
    reduced = reg.Design(
        n_pairs=100,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="anytime-tuned",
        pass_alpha=0.0209,
        starting_wealth=0.25,
    )
    r1 = reg.run_cell(cell, base, replicates=400, seed=41)
    r25 = reg.run_cell(cell, reduced, replicates=400, seed=41)
    assert r1.design.starting_wealth == 1.0
    assert r25.design.starting_wealth == 0.25
    assert r1.p_joint_pass > 0.0, "the fixture must produce some PASS at W0 = 1.0"
    assert r25.p_joint_pass < r1.p_joint_pass, (
        f"a lower starting wealth must pass less often: {r25.p_joint_pass} vs {r1.p_joint_pass}"
    )


def test_tuned_lambda_is_fixed_before_the_first_pair() -> None:
    """Mutant 8: the tuned bet may never depend on the outcome it multiplies."""
    assert reg.LAMBDA_FP_PASS > 0.0
    assert reg.LAMBDA_FP_CUT > 0.0
    assert reg.LAMBDA_FP_PASS < 1.0 / reg._TUNED_M0
    assert reg.LAMBDA_FP_CUT < 1.0 / (1.0 - reg._TUNED_M0)
    # The lambda is a property of the declared alternative, not of the data.
    again = reg.tuned_lambda(reg._TUNED_M0, reg._PASS_ALT_DIST, upward=True)
    assert again == pytest.approx(reg.LAMBDA_FP_PASS, abs=1e-12)
    # Wealth with the fixed lambda equals the product form on a hand stream.
    w0 = 1.0
    xs = np.array([1.0, 0.5, 0.0, 0.5, 1.0], dtype=np.float64)
    wealth = reg.TunedWealth(1, w0, reg.LAMBDA_FP_PASS, reg._TUNED_M0, upward=True)
    partials = [math.log(w0)]
    for x in xs:
        wealth.step(np.array([x]))
        partials.append(partials[-1] + math.log1p(reg.LAMBDA_FP_PASS * (x - reg._TUNED_M0)))
    assert float(wealth.log_w[0]) == pytest.approx(partials[-1], abs=1e-12)
    assert float(wealth.running_max[0]) == pytest.approx(max(partials), abs=1e-12)
    # A look-ahead lambda would differ when the first outcome is extreme.
    look_ahead = reg.tuned_lambda(reg._TUNED_M0, reg.x_alt_distribution(0.95, 0.05), upward=True)
    assert look_ahead != pytest.approx(reg.LAMBDA_FP_PASS, abs=1e-9), (
        "the declared-alternative lambda must not equal a data-dependent one"
    )


def test_cut_direction_is_downward() -> None:
    """Mutant 12: CUT rejects for small evidence, not large."""
    design = reg.Design(
        n_pairs=100,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="anytime-tuned",
        pass_alpha=0.0209,
        starting_wealth=1.0,
    )
    low = reg.Cell(0.35, 0.35, 0.35)  # d = 0.00: futility is likely
    high = reg.Cell(0.75, 0.35, 0.35)  # d = 0.40: futility is unlikely
    r_low = reg.run_cell(low, design, replicates=400, seed=51)
    r_high = reg.run_cell(high, design, replicates=400, seed=51)
    assert r_low.p_cut > r_high.p_cut, "CUT must fire more often under a null than a real effect"
    # The score-test CUT direction: reject for small z at 0.05.
    crit = reg._normal_quantile(reg.FUTILITY_ALPHA)
    assert crit < 0.0
    z_big = reg.tango_score_z(50, 10, 80, 0.20)
    z_small = reg.tango_score_z(10, 50, 80, 0.20)
    assert z_big > 0.0 > z_small
    assert not (z_big <= crit), "large positive z must not trigger CUT"
    assert z_small <= crit, "small z must trigger CUT"


# ---------------------------------------------------------------------------
# Mutants 10-11: label vs path; headline pair count
# ---------------------------------------------------------------------------


def test_stopping_column_on_the_tsv_matches_the_path_that_produced_it(tmp_path: Path) -> None:
    """Mutant 10: the written stopping label must match the simulation path.

    A fixed-n row must also spend the full cap: expected_epochs equals
    total_epochs. The anytime path stops early on this cell, so it cannot
    produce that figure.
    """
    out = tmp_path / "out"
    grid = [
        (
            reg.Cell(0.85, 0.25, 0.30),
            reg.Design(
                n_pairs=20,
                null_per_pair=1.0,
                fn_construction="direct",
                stopping="anytime",
            ),
        ),
        (
            reg.Cell(0.85, 0.25, 0.30),
            reg.Design(
                n_pairs=20,
                null_per_pair=1.0,
                fn_construction="direct",
                stopping="fixed-n-score",
                pass_alpha=0.0209,
            ),
        ),
        (
            reg.Cell(0.85, 0.25, 0.30),
            reg.Design(
                n_pairs=20,
                null_per_pair=1.0,
                fn_construction="direct",
                stopping="fixed-n-betting",
                pass_alpha=0.0209,
            ),
        ),
    ]
    reg.main(
        ["--out", str(out), "--replicates", "80", "--workers", "1", "--seed", "685"],
        grid=grid,
    )
    cols, rows = _split_tsv((out / "per_look.tsv").read_text(encoding="utf-8"))
    i_stop = cols.index("stopping")
    i_look = cols.index("look")
    i_epochs = cols.index("expected_epochs")
    i_cap = cols.index("total_epochs")
    by_stop = {row[i_stop]: row for row in rows}
    assert set(by_stop) == {"anytime", "fixed-n-score", "fixed-n-betting"}
    for stopping in ("fixed-n-score", "fixed-n-betting"):
        assert by_stop[stopping][i_look] == "20"
        assert float(by_stop[stopping][i_epochs]) == pytest.approx(
            float(by_stop[stopping][i_cap]), abs=1e-9
        ), f"{stopping} must spend the full cap, not stop early"
    assert float(by_stop["anytime"][i_epochs]) < float(by_stop["anytime"][i_cap]), (
        "the anytime path must stop early on this cell, which distinguishes it"
    )


def test_headline_reads_n_pairs_from_each_row() -> None:
    """Mutant 11: the headline must report the row's own pair count.

    Only the 300-pair configuration meets the target; a stale 100-pair read
    would misreport the cheapest priced config as 100 pairs.
    """
    results = []
    for n_pairs, p_pass in ((100, 0.50), (300, 0.85)):
        design = reg.Design(
            n_pairs=n_pairs,
            null_per_pair=1.0,
            fn_construction="direct",
            stopping="fixed-n-betting",
            pass_alpha=0.0209,
        )
        for p_p, p_n in ((0.30, 0.30), (0.35, 0.35), (0.40, 0.40)):
            results.append(
                _hand_row(
                    reg.Cell(round(p_p + 0.30, 10), p_p, p_n),
                    design,
                    p_pass=p_pass,
                    p_cut=0.0,
                )
            )
            results.append(
                _hand_row(
                    reg.Cell(round(p_p + 0.10, 10), p_p, p_n),
                    design,
                    p_pass=0.0,
                    p_cut=p_pass,
                )
            )
    headline = reg.headline_rows(results)
    row = next(
        h
        for h in headline
        if h.stopping == "fixed-n-betting" and math.isclose(h.target, 0.80, abs_tol=1e-9)
    )
    assert row.reached
    assert row.n_pairs == 300, "only the 300-pair config meets; the headline must say 300"
    assert row.total_epochs == 900


# ---------------------------------------------------------------------------
# Mutant 13: exit code forced to zero
# ---------------------------------------------------------------------------


def test_exit_code_is_not_forced_to_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutant 13: a calibration failure must still return 1."""
    cell = reg.Cell(0.55, 0.35, 0.35)
    design = reg.Design(
        n_pairs=30,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-betting",
        pass_alpha=0.0209,
    )
    bad = _hand_row(cell, design, p_pass=0.50, p_cut=0.0, holds=False)
    assert reg.calibration_exit_code([bad]) == 1
    out = tmp_path / "out"
    original = reg.run_cell

    def _loosened(c: Any, d: Any, **kwargs: Any) -> Any:
        kwargs["pass_alpha_override"] = 0.60
        return original(c, d, **kwargs)

    monkeypatch.setattr(reg, "run_cell", _loosened)
    code = reg.main(
        ["--out", str(out), "--replicates", "300", "--workers", "1", "--seed", "685"],
        grid=[(cell, design)],
    )
    assert code == 1


# ---------------------------------------------------------------------------
# Mutants 14-16: tuned running maximum; score CUT level; joint PASS halves
# ---------------------------------------------------------------------------


def test_anytime_tuned_rejection_uses_running_maximum() -> None:
    """Mutant 14: rejection reads the running max, not the current wealth.

    A constructed sequence whose wealth crosses 1/alpha and then falls back
    below it must still be a rejection: the anytime-valid test rejects when
    the running maximum of the wealth reaches 1/alpha, not when the current
    wealth does.
    """
    w0 = 1.0
    alpha = 0.5
    lam = 0.8
    m0 = 0.6
    threshold = math.log(1.0 / alpha)
    wealth = reg.TunedWealth(1, w0, lam, m0, upward=True)
    assert not wealth.rejects(alpha)[0], "starts below the threshold"
    # Three favourable outcomes cross the threshold.
    for _ in range(3):
        wealth.step(np.array([1.0]))
    assert float(wealth.log_w[0]) > threshold
    assert wealth.rejects(alpha)[0], "the running max must reject once it crosses"
    # A subsequent unfavourable outcome pulls the current wealth back down.
    wealth.step(np.array([0.0]))
    assert float(wealth.log_w[0]) < threshold, "the current wealth falls back"
    # The rejection still stands, because the running max crossed.
    assert wealth.rejects(alpha)[0], "rejection must survive a wealth drawdown"
    assert float(wealth.running_max[0]) > threshold


def test_fixed_n_score_cut_is_decided_at_0_05() -> None:
    """Mutant 15: CUT on a fixed-n-score row is decided at 0.05, not 0.10.

    A z between the 0.10 and 0.05 one-sided critical values is not a CUT at
    the registered 0.05 level. The run_cell-level check puts P(CUT) at the
    d = 0.20 margin near 0.05; a 0.10 CUT level would put it near 0.10.
    """
    crit_05 = reg._normal_quantile(0.05)
    crit_10 = reg._normal_quantile(0.10)
    assert reg.FUTILITY_ALPHA == 0.05
    assert crit_05 < crit_10 < 0.0
    # A real Tango z in the band between the two critical values.
    z_between = reg.tango_score_z(4, 0, 40, 0.20)
    assert crit_05 < z_between < crit_10, "the fixture must land between the critical values"
    assert z_between > crit_05, "a z between the critical values is not a CUT at 0.05"
    # run_cell level: at d = 0.20 the true F-P equals the margin, so CUT is
    # an error at rate 0.05. Under a 0.10 CUT level the rate would be near 0.10.
    cell = reg.Cell(0.55, 0.35, 0.35)
    design = reg.Design(
        n_pairs=200,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    row = reg.run_cell(cell, design, replicates=1500, seed=685)
    assert 0.01 < row.p_cut < 0.085, (
        f"CUT at the margin must stay near 0.05, not 0.10: got {row.p_cut}"
    )


def test_fixed_n_score_joint_pass_requires_both_halves_not_fn_alone() -> None:
    """Mutant 16: joint PASS on a fixed-n-score row requires both halves.

    An input where F-N passes and F-P does not is not a joint PASS. The
    fixture puts F-P at 0.05 (below the margin) and F-N at 0.40 (above it),
    so the F-N half is high and the F-P half is low; joint PASS cannot equal
    the F-N half alone.
    """
    cell = reg.Cell(0.70, 0.65, 0.30)  # F-P = 0.05, F-N = 0.40
    assert reg.true_fn_diff(cell) == pytest.approx(0.40)
    design = reg.Design(
        n_pairs=200,
        null_per_pair=1.0,
        fn_construction="direct",
        stopping="fixed-n-score",
        pass_alpha=0.0209,
    )
    row = reg.run_cell(cell, design, replicates=1500, seed=42)
    assert row.p_fn_half > 0.5, "the F-N half must clear on this cell"
    assert row.p_fp_half < 0.05, "the F-P half must stay low when F-P is 0.05"
    assert row.p_joint_pass <= row.p_fp_half + 1e-12, "joint PASS cannot exceed the F-P half"
    assert row.p_joint_pass < row.p_fn_half - 0.1, (
        f"joint PASS is not the F-N half alone: {row.p_joint_pass} vs {row.p_fn_half}"
    )


# ---------------------------------------------------------------------------
# Structural: grid, prices, design fields
# ---------------------------------------------------------------------------


def test_design_fields_carry_the_stage2_columns() -> None:
    d = reg.Design(
        n_pairs=97,
        null_per_pair=0.5,
        fn_construction="direct",
        stopping="anytime-tuned",
        pass_alpha=0.0209,
        starting_wealth=0.25,
    )
    assert d.n_full == 97
    assert d.n_placebo == 97
    assert d.n_null == 48
    assert d.total_epochs == 242
    assert d.stopping == "anytime-tuned"
    assert d.pass_alpha == 0.0209
    assert d.starting_wealth == 0.25


def test_price_constants_are_the_registered_rates() -> None:
    assert reg._PRICE_LO == 0.083
    assert reg._PRICE_HI == 0.087
    assert reg._PRICE_CAP == 0.30
    assert reg._price(100) == "$8.30-$8.70 (cap $30.00)"


def test_full_grid_structure() -> None:
    grid = reg.stage2_grid()
    assert grid, "the full grid must not be empty"
    stoppings = {design.stopping for _cell, design in grid}
    assert stoppings == set(reg.STOPPINGS)
    union_only_on_anytime = {
        design.fn_construction for _cell, design in grid if design.fn_construction == "union"
    }
    assert union_only_on_anytime == {"union"}
    for _cell, design in grid:
        if design.fn_construction == "union":
            assert design.stopping == "anytime"
        if design.stopping in reg.NEW_DESIGN_STOPPINGS:
            assert design.fn_construction == "direct"
        if design.stopping == "anytime":
            assert design.pass_alpha == 0.0209
            assert design.starting_wealth == 1.0
        if design.stopping == "anytime-tuned":
            assert design.starting_wealth in reg.STARTING_WEALTHS
        if design.stopping in ("fixed-n-betting", "fixed-n-score"):
            assert design.pass_alpha in reg.FIXED_PASS_ALPHAS
            assert design.starting_wealth == 1.0


def test_score_statistics_are_finite_on_the_grid_cells() -> None:
    for p_p in reg.BASELINES:
        for p_n in reg.BASELINES:
            for d in (0.00, 0.20, 0.30):
                cell = reg.Cell(round(p_p + d, 10), p_p, p_n)
                design = reg.Design(
                    n_pairs=50,
                    null_per_pair=1.0,
                    fn_construction="direct",
                    stopping="fixed-n-score",
                    pass_alpha=0.0209,
                )
                row = reg.run_cell(cell, design, replicates=40, seed=5)
                assert 0.0 <= row.p_joint_pass <= 1.0
                assert 0.0 <= row.p_cut <= 1.0
                assert 0.0 <= row.p_fp_half <= 1.0
                assert 0.0 <= row.p_fn_half <= 1.0
                assert row.p_joint_pass + row.p_cut <= 1.0 + 1e-9


def test_farrington_manning_reduces_to_pooled_variance_at_delta0_zero() -> None:
    """At delta0 = 0 the constrained MLE is the pooled proportion.

    H0: p_F = p_N forces one common p; the Farrington-Manning variance uses
    that constrained value, not the two observed proportions separately.
    """
    z = reg.farrington_manning_z(50, 80, 30, 80, 0.0)
    p_f, p_n = 50 / 80, 30 / 80
    pooled = (50 + 30) / (80 + 80)
    raw = p_f - p_n
    se = math.sqrt(pooled * (1 - pooled) / 80 + pooled * (1 - pooled) / 80)
    assert z == pytest.approx(raw / se, abs=1e-9)
    # The unconstrained (separate-proportions) z differs, which is the point.
    se_unpooled = math.sqrt(p_f * (1 - p_f) / 80 + p_n * (1 - p_n) / 80)
    assert z != pytest.approx(raw / se_unpooled, abs=1e-6)


def test_tuned_betting_path_is_available_and_uses_starting_wealth(tmp_path: Path) -> None:
    cell = reg.Cell(0.60, 0.30, 0.30)
    grid = [
        (
            cell,
            reg.Design(
                n_pairs=40,
                null_per_pair=1.0,
                fn_construction="direct",
                stopping="anytime-tuned",
                pass_alpha=0.0209,
                starting_wealth=0.5,
            ),
        ),
    ]
    out = tmp_path / "out"
    code = reg.main(
        ["--out", str(out), "--replicates", "100", "--workers", "1", "--seed", "9"],
        grid=grid,
    )
    assert code in (0, 1)
    cols, rows = _split_tsv((out / "per_look.tsv").read_text(encoding="utf-8"))
    i_w0 = cols.index("starting_wealth")
    assert {row[i_w0] for row in rows} == {"0.50"}
