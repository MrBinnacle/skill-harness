"""Tests for #649: the #621 Stage 1A read, its stop rule and the dry-run operating table."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fixture_present() -> bool:
    cue_audit = _load("cue_audit")
    return bool((cue_audit.FIXTURE_ROOT_DEFAULT / "fixture_shas.json").is_file())


@pytest.fixture(scope="module")
def s1a() -> ModuleType:
    return _load("v5_cue_stage1a")


def _null_readout(tmp_path: Path, outcomes: list[int] | None) -> Path:
    rows = [
        {"arm": "null", "world": "a", "epoch": i + 2, "final_world_correct": bool(o), "void": False}
        for i, o in enumerate(outcomes or [])
    ]
    rows.append(
        {"arm": "null", "world": "a", "epoch": 1, "final_world_correct": False, "void": True}
    )
    correct = sum(outcomes) if outcomes is not None else 1
    summary = {"null/a": {"n": 7, "correct": correct}}
    path = tmp_path / "readout.json"
    path.write_text(json.dumps({"rows": rows if outcomes else [], "summary": summary}))
    return path


@pytest.mark.parametrize(
    ("ub_fp", "lb_fp", "lb_fn", "expected"),
    [
        (0.19, -0.5, -0.5, "CUT_NO_LIFT"),
        (0.20, -0.5, -0.5, "UNRESOLVED_CONTINUE"),
        (0.9, 0.20, 0.20, "A_PASSES_EARLY"),
        (0.9, 0.20, 0.19, "UNRESOLVED_CONTINUE"),
        (0.9, 0.19, 0.50, "UNRESOLVED_CONTINUE"),
        (0.19, 0.20, 0.20, "CUT_NO_LIFT"),
    ],
)
def test_stop_rule_on_constructed_bounds(
    s1a: ModuleType, ub_fp: float, lb_fp: float, lb_fn: float, expected: str
) -> None:
    assert s1a.stop_rule(ub_fp=ub_fp, lb_fp=lb_fp, lb_fn=lb_fn) == expected


@pytest.mark.parametrize("value", [0, 1])
@pytest.mark.parametrize("pass_alpha", [0.05, 0.0209])
def test_all_equal_pairs_contain_zero_and_never_pass(
    s1a: ModuleType, value: int, pass_alpha: float
) -> None:
    stream = dict.fromkeys(range(1, 17), value)
    _, xs = s1a.pair_by_launch(stream, stream)
    lb, ub = s1a.fp_bounds(xs, pass_alpha=pass_alpha)
    assert lb <= 0.0 <= ub
    outcome = s1a.stop_rule(ub_fp=ub, lb_fp=lb, lb_fn=lb)
    assert outcome in {"UNRESOLVED_CONTINUE", "CUT_NO_LIFT"}


@pytest.mark.parametrize("pass_alpha", [0.05, 0.0209])
def test_sixteen_of_sixteen_against_zero_clears_the_boundary(
    s1a: ModuleType, pass_alpha: float
) -> None:
    _, xs = s1a.pair_by_launch(dict.fromkeys(range(16), 1), dict.fromkeys(range(16), 0))
    lb, _ = s1a.fp_bounds(xs, pass_alpha=pass_alpha)
    assert lb >= 0.20


def test_fp_bounds_use_pass_alpha_below_and_alpha_above(s1a: ModuleType) -> None:
    xs = (1.0, 0.5, 1.0, 0.0, 1.0, 1.0, 0.5, 1.0)
    lb, ub = s1a.fp_bounds(xs, pass_alpha=0.0209)
    assert lb == pytest.approx(2 * one_sided_betting_bound(xs, alpha=0.0209, side="lower") - 1)
    assert ub == pytest.approx(2 * one_sided_betting_bound(xs, alpha=0.05, side="upper") - 1)


def test_pairing_is_by_epoch_and_drops_a_void_partner(s1a: ModuleType) -> None:
    full = {3: 1, 1: 0, 2: 1}
    placebo = {1: 1, 3: 0}
    keys, xs = s1a.pair_by_launch(full, placebo)
    assert keys == [1, 3]
    assert xs == (0.0, 1.0)


def _install_listing_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, s1a: ModuleType, *, placebo_position: int = 1
) -> None:
    full_path = tmp_path / "full.eval"
    placebo_path = tmp_path / "placebo.eval"
    full_path.touch()
    placebo_path.touch()
    full_text = f"Skills:\n1. pull-rebase: {s1a.FULL_DESC}"
    placebo_text = "\n".join(
        [
            "Skills:",
            *(
                f"{index}. {'parse-csv' if index == placebo_position else 'built-in'}: "
                f"{s1a.PLACEBO_DESC if index == placebo_position else 'built-in description'}"
                for index in range(1, placebo_position + 1)
            ),
        ]
    )
    logs = {
        str(full_path): SimpleNamespace(
            eval=SimpleNamespace(metadata={"cell_arm": "full"}),
            samples=[
                SimpleNamespace(epoch=1, messages=[SimpleNamespace(role="user", content=full_text)])
            ],
        ),
        str(placebo_path): SimpleNamespace(
            eval=SimpleNamespace(metadata={"cell_arm": "placebo"}),
            samples=[
                SimpleNamespace(
                    epoch=1, messages=[SimpleNamespace(role="user", content=placebo_text)]
                )
            ],
        ),
    }
    inspect_ai = ModuleType("inspect_ai")
    inspect_log = ModuleType("inspect_ai.log")
    inspect_log.read_eval_log = lambda path: logs[path]  # type: ignore[attr-defined]
    inspect_ai.log = inspect_log  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "inspect_ai", inspect_ai)
    monkeypatch.setitem(sys.modules, "inspect_ai.log", inspect_log)


def test_listing_position_reads_both_cards_from_the_first_user_message(
    s1a: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_listing_logs(monkeypatch, tmp_path, s1a)
    assert s1a._listing_position(tmp_path) == {("full", 1): 1, ("placebo", 1): 1}


def test_listing_position_refuses_a_nonfirst_card(
    s1a: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_listing_logs(monkeypatch, tmp_path, s1a, placebo_position=2)
    with pytest.raises(ValueError, match="placebo epoch 1: card appears at listing position 2"):
        s1a._listing_position(tmp_path)


def test_worst_fp_is_no_tighter_than_any_single_order(s1a: ModuleType) -> None:
    lb, ub = s1a.worst_fp(12, 3, n=16, pass_alpha=0.0209, shuffles=4, seed=1)
    one_order = s1a.fp_bounds((1.0,) * 12 + (0.5,) + (0.0,) * 3, pass_alpha=0.0209)
    assert lb <= one_order[0]
    assert ub >= one_order[1]


def test_worst_fn_takes_the_highest_null_upper_bound(s1a: ModuleType) -> None:
    worst = s1a.worst_fn(16, n=16, null_correct=1, n_null=7, pass_alpha=0.05, shuffles=0, seed=0)
    lb_f = one_sided_betting_bound([1.0] * 16, alpha=0.025, side="lower")
    ub_n = max(
        one_sided_betting_bound([float(i == k) for i in range(7)], alpha=0.025, side="upper")
        for k in range(7)
    )
    assert worst == pytest.approx(lb_f - ub_n)


def test_epochs_per_arm_flag_replaces_constant(s1a: ModuleType) -> None:
    """Criterion 1: --epochs-per-arm N changes the table size from (N+1)^2."""
    # Default N=16 gives (16+1)^2 = 289 cells
    cells_16 = s1a.operating_table(null_correct=1, n_null=7, pass_alpha=0.0209, n=16, shuffles=0)
    assert len(cells_16) == 289
    # N=10 gives (10+1)^2 = 121 cells
    cells_10 = s1a.operating_table(null_correct=1, n_null=7, pass_alpha=0.0209, n=10, shuffles=0)
    assert len(cells_10) == 121
    assert {(c.correct_f, c.correct_p) for c in cells_10} == {
        (f, p) for f in range(11) for p in range(11)
    }
    # N=3 gives (3+1)^2 = 16 cells
    cells_3 = s1a.operating_table(null_correct=1, n_null=7, pass_alpha=0.0209, n=3, shuffles=0)
    assert len(cells_3) == 16


def test_default_epochs_per_arm_reproduces_289_cell_table(s1a: ModuleType) -> None:
    """Criterion 1: the default N=16 table is byte-for-byte identical to the existing one."""
    cells_default = s1a.operating_table(null_correct=1, n_null=7, pass_alpha=0.0209, shuffles=0)
    cells_explicit = s1a.operating_table(
        null_correct=1, n_null=7, pass_alpha=0.0209, n=16, shuffles=0
    )
    assert len(cells_default) == 289
    assert len(cells_explicit) == 289
    for a, b in zip(cells_default, cells_explicit, strict=True):
        assert a.correct_f == b.correct_f
        assert a.correct_p == b.correct_p
        assert a.ub_fp == pytest.approx(b.ub_fp)
        assert a.lb_fp == pytest.approx(b.lb_fp)
        assert a.lb_fn == pytest.approx(b.lb_fn)
        assert a.outcome == b.outcome


def test_hard_cap_formula(s1a: ModuleType) -> None:
    """Criterion 1: cap = (3*N - n_reused) * PER_SAMPLE_CAP."""
    assert s1a._hard_cap(16, 7) == pytest.approx((48 - 7) * 0.30)
    assert s1a._hard_cap(97, 7) == pytest.approx((291 - 7) * 0.30)
    assert s1a._hard_cap(10, 0) == pytest.approx(30 * 0.30)


def test_render_table_uses_n_not_constant(s1a: ModuleType) -> None:
    """Criterion 1: render_table accepts n parameter."""
    cells = s1a.operating_table(null_correct=1, n_null=7, pass_alpha=0.0209, n=10, shuffles=0)
    rendered = s1a.render_table(cells, pass_alpha=0.0209, n_null=7, n=10)
    assert "10 Full against 7 Null-A" in rendered
    assert "cells: 121" in rendered


def test_read_stage1a_uses_reused_then_new_null_a_order(
    s1a: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 2: Null-A rate is read over reused then new epochs in that order.

    The betting bound depends on observation order (predictable plug-in lambdas).
    This drives the launcher readout rather than checking a separately constructed stream.
    """

    @dataclass(frozen=True)
    class FakeRow:
        arm: str
        world: str
        epoch: int
        final_world_correct: bool
        void: bool = False
        silent_violation: bool = False
        no_publish: bool = False
        usd: float = 0.083

    def row(arm: str, epoch: int, correct: bool) -> FakeRow:
        return FakeRow(arm=arm, world="a", epoch=epoch, final_world_correct=correct)

    rows = [
        *(row("full", epoch, True) for epoch in range(1, 10)),
        *(row("placebo", epoch, False) for epoch in range(1, 10)),
        row("null", 9, False),
    ]
    twin_readout = ModuleType("twin_readout")
    twin_readout.read_rows = lambda _: rows  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "twin_readout", twin_readout)
    monkeypatch.setattr(
        s1a,
        "_manifest_reads",
        lambda _: {(arm, i): True for arm in ("full", "placebo") for i in range(1, 10)},
    )
    monkeypatch.setattr(
        s1a,
        "_listing_position",
        lambda _: {(arm, i): 1 for arm in ("full", "placebo") for i in range(1, 10)},
    )

    reused_outcomes = (1, 0, 1, 0, 1, 0, 1, 0)
    null_a = s1a.NullA(outcomes=reused_outcomes, correct=4, n=8)
    readout = s1a.read_stage1a(tmp_path, null_a, 0.05, n=9)
    expected = one_sided_betting_bound(
        [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0], alpha=0.025, side="upper"
    )
    assert readout["f_minus_n"]["ub_mu_n"] == pytest.approx(expected)
    assert readout["null_a"]["n"] == 9
    assert readout["null_a"]["correct"] == 4

    grouped = (1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    ub_grouped = s1a._bound(grouped, 0.025, "upper")
    assert expected != ub_grouped, "order must change the bound for this test to be meaningful"


def test_operating_table_covers_289_cells(s1a: ModuleType) -> None:
    cells = s1a.operating_table(null_correct=1, n_null=7, pass_alpha=0.0209, shuffles=0)
    assert len(cells) == 289
    assert {(c.correct_f, c.correct_p) for c in cells} == {
        (f, p) for f in range(17) for p in range(17)
    }
    assert all(
        c.outcome == s1a.stop_rule(ub_fp=c.ub_fp, lb_fp=c.lb_fp, lb_fn=c.lb_fn) for c in cells
    )
    by_cell = {(c.correct_f, c.correct_p): c for c in cells}
    assert by_cell[(0, 16)].outcome == "CUT_NO_LIFT"
    assert by_cell[(16, 0)].lb_fp >= 0.20


def test_pass_alpha_moves_only_the_lower_bounds(s1a: ModuleType) -> None:
    loose = s1a.operating_table(null_correct=1, n_null=7, pass_alpha=0.05, shuffles=0)
    strict = s1a.operating_table(null_correct=1, n_null=7, pass_alpha=0.0209, shuffles=0)
    for a, b in zip(loose, strict, strict=True):
        assert a.ub_fp == b.ub_fp
        assert b.lb_fp <= a.lb_fp
        assert b.lb_fn <= a.lb_fn


def test_null_a_reads_rows_in_epoch_order(s1a: ModuleType, tmp_path: Path) -> None:
    null_a = s1a.load_null_a(_null_readout(tmp_path, [0, 0, 0, 0, 0, 1, 0]))
    assert null_a.outcomes == (0, 0, 0, 0, 0, 1, 0)
    assert (null_a.correct, null_a.n) == (1, 7)
    ub, order = s1a.null_upper(null_a, 0.025)
    assert order == "Null-A in epoch order"
    expected = one_sided_betting_bound([0, 0, 0, 0, 0, 1, 0], alpha=0.025, side="upper")
    assert ub == pytest.approx(expected)


def test_null_a_counts_only_uses_the_worst_placement(s1a: ModuleType, tmp_path: Path) -> None:
    null_a = s1a.load_null_a(_null_readout(tmp_path, None))
    assert null_a.outcomes is None
    ub, order = s1a.null_upper(null_a, 0.025)
    assert "worst order" in order
    placed = [
        one_sided_betting_bound([float(i == k) for i in range(7)], alpha=0.025, side="upper")
        for k in range(7)
    ]
    assert ub == pytest.approx(max(placed))


@pytest.mark.skipif(
    not _fixture_present(),
    reason="the v5-cue fixture is private and lives only on the steering host",
)
def test_dry_run_prints_both_tables_and_calls_no_model(
    s1a: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inspect_ai = pytest.importorskip("inspect_ai")

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the dry run called eval")

    monkeypatch.setattr(inspect_ai, "eval", refuse)
    monkeypatch.setattr(s1a, "DRY_RUN_SHUFFLES", 0)
    readout = _null_readout(tmp_path, [0, 0, 0, 0, 0, 1, 0])
    argv = ["--out", str(tmp_path / "logs"), "--null-readout", str(readout), "--dry-run"]
    assert s1a.main(argv) == 0

    out = capsys.readouterr().out
    assert "DRY RUN: no model call." in out
    assert "v5cue-full-world-a-cue" in out and "v5cue-placebo-world-a-cue" in out
    assert "OPERATING TABLE at pass-alpha 0.05 " in out
    assert "OPERATING TABLE at pass-alpha 0.0209 " in out
    assert "pass-alpha=0.0209" in out.splitlines()[1]
    assert "max(p_FN, p_FP) <= 0.0209 against H0: d <= 0.2" in out
    assert out.count("cells: 289") == 2
    assert not (tmp_path / "logs").exists()
    assert pytest.approx(0.30) == s1a.PER_SAMPLE_CAP
    assert s1a.EPOCHS_PER_ARM == 16
    assert s1a.MODEL == "anthropic/claude-sonnet-5"


def test_sequential_stops_at_first_firing_look(s1a: ModuleType) -> None:
    """Criterion 3: a sequential run stops at the first look where the rule fires."""
    full = {i: 1 for i in range(1, 17)}
    placebo = {i: 0 for i in range(1, 17)}
    null_combined = (0.0,) * 16
    outcome, fired_at = s1a.sequential_evaluate(
        full, placebo, null_combined, n=16, pass_alpha=0.0209
    )
    assert (outcome, fired_at) == ("A_PASSES_EARLY", 16)
    assert s1a.sequential_evaluate(full, placebo, null_combined, n=15, pass_alpha=0.0209) == (
        "UNRESOLVED_CONTINUE",
        None,
    )


def test_sequential_never_fires_ends_at_n(s1a: ModuleType) -> None:
    """Criterion 3: a stream that never fires ends at N with UNRESOLVED_CONTINUE."""
    # All pairs tied: Full = Placebo, so F-P = 0 everywhere.
    full = {i: 0 for i in range(1, 17)}
    placebo = {i: 0 for i in range(1, 17)}
    null_combined = (0.5,) * 16  # Null at 0.5 gives moderate UB
    outcome, fired_at = s1a.sequential_evaluate(
        full, placebo, null_combined, n=16, pass_alpha=0.0209
    )
    assert outcome == "UNRESOLVED_CONTINUE"
    assert fired_at is None


def test_sequential_stops_never_later_than_first_firing(s1a: ModuleType) -> None:
    """Criterion 3: once a rule fires, the sequential run stops and never continues."""
    # Construct a stream that fires CUT_NO_LIFT early (high placebo correctness).
    full = {i: 0 for i in range(1, 17)}  # Full always wrong
    placebo = {i: 1 for i in range(1, 17)}  # Placebo always correct
    null_combined = (0.5,) * 16
    outcome, fired_at = s1a.sequential_evaluate(
        full, placebo, null_combined, n=16, pass_alpha=0.0209
    )
    assert (outcome, fired_at) == ("CUT_NO_LIFT", 6)
    assert s1a.sequential_evaluate(full, placebo, null_combined, n=5, pass_alpha=0.0209) == (
        "UNRESOLVED_CONTINUE",
        None,
    )


def test_smallest_look_finds_first_firing_epoch(s1a: ModuleType) -> None:
    """Criterion 4: smallest_look finds the first epoch at which each outcome fires."""
    cells = s1a.operating_table(null_correct=1, n_null=7, pass_alpha=0.0209, n=10, shuffles=0)
    looks = s1a.smallest_look(cells, n=10)
    # CUT_NO_LIFT should fire at some look.
    assert looks["CUT_NO_LIFT"] is not None
    assert 1 <= looks["CUT_NO_LIFT"] <= 10
    # UNRESOLVED_CONTINUE should fire at look 1 (trivial case).
    assert looks["UNRESOLVED_CONTINUE"] is not None
    assert looks["UNRESOLVED_CONTINUE"] == 1
    # A_PASSES_EARLY may not appear with null_correct=1, n_null=7 (lb_fn too low).
    # Verify the function handles missing outcomes by returning None.
    cells_all_cut = [
        s1a.TableCell(0, 0, 0.1, -0.5, -0.5, "CUT_NO_LIFT"),
    ]
    looks_all_cut = s1a.smallest_look(cells_all_cut, n=1)
    assert looks_all_cut["A_PASSES_EARLY"] is None
    delayed_cut = [s1a.TableCell(0, 6, 0.1, -0.5, -0.5, "CUT_NO_LIFT")]
    assert s1a.smallest_look(delayed_cut, n=10)["CUT_NO_LIFT"] == 7


def test_dry_run_at_n97_prints_new_epochs_and_cap(
    s1a: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Criterion 4: dry run at N=97 prints new epochs 284 and cap $85.20."""
    readout = _null_readout(tmp_path, [0, 0, 0, 0, 0, 1, 0])
    argv = [
        "--out",
        str(tmp_path / "logs"),
        "--null-readout",
        str(readout),
        "--epochs-per-arm",
        "97",
        "--dry-run",
    ]

    def table(**kwargs: Any) -> list[Any]:
        assert kwargs["n"] == 97
        return [s1a.TableCell(0, 0, 1.0, -1.0, -1.0, "UNRESOLVED_CONTINUE")]

    monkeypatch.setattr(s1a, "operating_table", table)
    assert s1a.main(argv) == 0
    output = capsys.readouterr().out
    assert "97 Full against 7 Null-A" in output
    assert "new epochs: 284 (3*97 - 7)" in output
    assert "expected: $23.57 at $0.083/epoch; $24.71 at $0.087/epoch" in output
    assert "cap: $85.20 (new epochs * $0.3)" in output


def test_dry_run_price_line_at_n97(s1a: ModuleType, tmp_path: Path) -> None:
    """Criterion 4: price line at N=97 shows new epochs 284 and cap $85.20."""
    # Directly verify the price line formula without running the full dry run.
    null_a = s1a.NullA(outcomes=(0, 0, 0, 0, 0, 1, 0), correct=1, n=7)
    n = 97
    new_epochs = 3 * n - null_a.n
    cap = s1a._hard_cap(n, null_a.n)
    assert new_epochs == 284
    assert cap == pytest.approx(85.20)


def test_main_stops_after_the_first_firing_look(
    s1a: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 3: the launcher does not spend on a second look after a stop."""
    readout = _null_readout(tmp_path, [0, 0, 0, 0, 0, 1, 0])
    pin = SimpleNamespace(fingerprint=lambda: "pin", sandbox_image="image")
    tasks = [
        SimpleNamespace(name="full"),
        SimpleNamespace(name="placebo"),
        SimpleNamespace(name="null"),
    ]
    monkeypatch.setattr(s1a, "stage1a_tasks", lambda *_args, **_kwargs: (pin, tasks))
    stage1 = ModuleType("v5_cue_stage1")
    stage1._model_cost = lambda: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "v5_cue_stage1", stage1)

    calls: list[list[str]] = []

    def evaluate(eval_tasks: list[SimpleNamespace], **kwargs: Any) -> list[SimpleNamespace]:
        calls.append([task.name for task in eval_tasks])
        Path(kwargs["log_dir"]).mkdir(parents=True, exist_ok=True)
        return [
            SimpleNamespace(
                location="log.eval",
                status="success",
                eval=SimpleNamespace(run_id="run"),
            )
            for _ in eval_tasks
        ]

    inspect_ai = ModuleType("inspect_ai")
    inspect_ai.eval = evaluate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "inspect_ai", inspect_ai)
    stopped = {
        "outcome": "CUT_NO_LIFT",
        "sequential": {"fired_at": 1},
    }
    monkeypatch.setattr(s1a, "read_stage1a", lambda *_args, **_kwargs: stopped)

    assert (
        s1a.main(
            [
                "--out",
                str(tmp_path / "logs"),
                "--null-readout",
                str(readout),
                "--epochs-per-arm",
                "8",
            ]
        )
        == 0
    )
    assert calls == [["full", "placebo"]]
