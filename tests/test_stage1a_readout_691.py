"""Tests for #691: the Stage 1A readout screen (inertness, adherence, within-pair correlation).

No model call. Seams: the CLI ``main`` over a synthetic tree of real ``.eval`` logs in the
on-disk Stage 1A shape (look directories, per-arm logs, a tool call naming the trace file for
a read, a void sample with no model usage); ``build_report`` over world-A epochs, the entry
point the CLI computes through; and the pure interval functions.

The real-stream literals below come from the non-author verifier's independent recompute on
the S486 logs (skill-harness #691, "Rework requirements, round 1"), not from this script.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from collections.abc import Sequence
from math import isnan
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"

# Launch-order streams, epoch 1 to 97, from the issue's expected-values table.
REAL_P = (
    "00000010001000100101100110110111110100000011011000"
    "00011000000100101010111010000011000010010000000"
)
REAL_N = (
    "00000100000001000110001001000000100000000100110101"
    "11010000010000101110110101111110011000101001000"
)
REAL_F = (
    "11101111011100100011100011000011111100100100000111"
    "01010110011111001000011101000101011000110100011"
)
REUSED = 7


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def screen() -> ModuleType:
    """The screen, with the n-to-exclude scan capped low: a full scan takes minutes.

    The real n values come from the host run on the S486 logs; the scan itself is tested
    below on cases small enough to run.
    """
    module = _load("stage1a_readout_691")
    setattr(module, "N_SEARCH_CAP", 12)  # noqa: B010 - ModuleType has no typed attribute
    return module


def _epochs(
    screen: ModuleType,
    full: str,
    placebo: str,
    null_new: str,
    *,
    reused: int,
    full_reads: Sequence[int] = (),
    placebo_reads: Sequence[int] = (),
) -> list[Any]:
    """Epochs at launch 1..n for Full and Placebo, and reused+1..n for new Null-A."""
    out = []
    for i, bit in enumerate(full, start=1):
        out.append(screen.Epoch("full", i, bit == "1", False, i in full_reads))
    for i, bit in enumerate(placebo, start=1):
        out.append(screen.Epoch("placebo", i, bit == "1", False, i in placebo_reads))
    for i, bit in enumerate(null_new, start=reused + 1):
        out.append(screen.Epoch("null", i, bit == "1", False, None))
    return out


def _real_epochs(screen: ModuleType) -> tuple[list[Any], tuple[int, ...]]:
    reused = tuple(int(b) for b in REAL_N[:REUSED])
    return _epochs(screen, REAL_F, REAL_P, REAL_N[REUSED:], reused=REUSED), reused


@pytest.fixture(scope="module")
def real_report(screen: ModuleType) -> dict[str, Any]:
    epochs, reused = _real_epochs(screen)
    report: dict[str, Any] = screen.build_report(epochs, reused)
    return report


# n=10 fixture with known counts. Full 7/10 correct (1-7), reads on 1-5.
# Placebo 4/10 correct (1-4), reads on 1-3. Null-A: reused (1, 0), new 3..10 = 1,1,1,0,0,0,0,0.
SMALL_F, SMALL_P, SMALL_N_NEW, SMALL_REUSED = "1111111000", "1111000000", "11100000", (1, 0)


def _small(screen: ModuleType) -> list[Any]:
    return _epochs(
        screen,
        SMALL_F,
        SMALL_P,
        SMALL_N_NEW,
        reused=2,
        full_reads=range(1, 6),
        placebo_reads=range(1, 4),
    )


# ---------------------------------------------------------------------------
# The real streams reproduce the verifier's table
# ---------------------------------------------------------------------------


def test_real_streams_give_both_alpha_readings_and_their_exclusion_statements(
    screen: ModuleType, real_report: dict[str, Any]
) -> None:
    out = screen.render(real_report)
    assert "point_estimate=0.0000" in out
    first = out.index("[alpha reading: 0.025 per one-sided bound: each endpoint at 0.05")
    second = out.index("[alpha reading: 0.0125 per one-sided bound: 0.05 in total")
    assert out.index("anytime_valid_interval=[-0.2818, 0.3601]") > first
    assert second > out.index("anytime_valid_interval=[-0.2818, 0.3601]")
    assert out.index("anytime_valid_interval=[-0.3042, 0.3825]") > second
    assert out.count("the interval does not exclude +/-0.20") == 2
    assert "fixed_n_newcombe_interval=[-0.1322, 0.1322]" in out


def test_real_streams_name_two_conventions_for_n_to_exclude_under_each_reading(
    screen: ModuleType, real_report: dict[str, Any]
) -> None:
    out = screen.render(real_report)
    assert out.count("(convention: same rates at evenly-spaced launch indices)") == 2
    assert out.count("(convention: real launch order repeated to length n)") == 2
    assert out.count("n_to_exclude_pm_0.20=not reached by 12 (convention:") == 4
    assert "a property of the convention, not of the data" in out


def test_real_streams_give_the_within_pair_table_and_phi(
    screen: ModuleType, real_report: dict[str, Any]
) -> None:
    out = screen.render(real_report)
    assert "table: both_correct=18 full_only=32 placebo_only=16 neither=31" in out
    assert "phi=0.0205" in out
    assert "phi_95_ci=[-0.1797, 0.2191]" in out
    assert "materially_positive=false" in out
    assert "not contradicted" in out


def test_null_stream_is_the_reused_outcomes_then_the_new_ones(
    screen: ModuleType, real_report: dict[str, Any]
) -> None:
    out = screen.render(real_report)
    assert f"N {REAL_N}" in out
    assert f"P {REAL_P}" in out
    assert f"F {REAL_F}" in out


def test_rows_out_of_launch_order_give_the_launch_order_interval(screen: ModuleType) -> None:
    """M3: the anytime-valid bound depends on order; rows arriving shuffled must be sorted."""
    epochs, reused = _real_epochs(screen)
    random.Random(691).shuffle(epochs)
    report = screen.build_report(epochs, reused)
    reading = report["inertness"]["readings"][0]
    assert (round(reading["lo"], 4), round(reading["hi"], 4)) == (-0.2818, 0.3601)


# ---------------------------------------------------------------------------
# Void epochs, adherence, correlation on the small fixture
# ---------------------------------------------------------------------------


def test_a_void_epoch_is_excluded_from_every_count_and_from_the_pairing(
    screen: ModuleType,
) -> None:
    """M7: void epochs leave every stream, count, rate and pair."""
    epochs = _small(screen)
    epochs.append(screen.Epoch("full", 11, True, True, True))
    epochs.append(screen.Epoch("placebo", 11, True, True, True))
    epochs.append(screen.Epoch("placebo", 12, True, True, True))
    epochs.append(screen.Epoch("null", 11, True, True, None))
    report = screen.build_report(epochs, SMALL_REUSED)
    iner = report["inertness"]
    assert (iner["n_placebo"], iner["correct_placebo"]) == (10, 4)
    assert (iner["n_null"], iner["correct_null"]) == (10, 4)
    assert report["adherence"]["full"]["assignment_to_read"] == "5/10 = 0.500"
    assert report["adherence"]["placebo"]["assignment_to_outcome"] == "4/10 = 0.400"
    assert report["correlation"]["pairs"] == list(range(1, 11))
    assert report["correlation"]["table"] == (4, 3, 0, 3)
    assert report["void"] == ["full#11", "null#11", "placebo#11", "placebo#12"]


def test_adherence_prints_the_three_rates_with_counts(screen: ModuleType) -> None:
    out = screen.render(screen.build_report(_small(screen), SMALL_REUSED))
    read = out.index("assignment_to_read:")
    outcome = out.index("assignment_to_outcome:")
    split = out.index("read_to_outcome:")
    assert out.index("full: 5/10 = 0.500") > read
    assert out.index("placebo: 3/10 = 0.300") > read
    assert out.index("full: 7/10 = 0.700") > outcome
    assert out.index("placebo: 4/10 = 0.400") > outcome
    assert out.index("full_correct_among_read: 5/5 = 1.000") > split
    assert "full_correct_among_unread: 2/5 = 0.400" in out
    assert "placebo_correct_among_read: 3/3 = 1.000" in out
    assert "placebo_correct_among_unread: 1/7 = 0.143" in out


def test_adherence_carries_the_post_treatment_sentence_verbatim(screen: ModuleType) -> None:
    out = screen.render(screen.build_report(_small(screen), SMALL_REUSED))
    assert (
        "Manifest-read happens after assignment. "
        "Splitting outcomes by it conditions on a post-treatment variable. "
        "These are adherence descriptives, not a mechanism."
    ) in out


def test_an_epoch_without_a_read_flag_refuses(screen: ModuleType) -> None:
    epochs = _small(screen)
    epochs[0] = screen.Epoch("full", 1, True, False, None)
    with pytest.raises(ValueError, match="manifest_read"):
        screen.build_report(epochs, SMALL_REUSED)


def test_a_duplicate_launch_index_refuses(screen: ModuleType) -> None:
    epochs = [*_small(screen), screen.Epoch("placebo", 3, False, False, False)]
    with pytest.raises(ValueError, match="duplicate placebo"):
        screen.build_report(epochs, SMALL_REUSED)


def test_correlation_on_the_small_fixture(screen: ModuleType) -> None:
    out = screen.render(screen.build_report(_small(screen), SMALL_REUSED))
    # a=4, b=3, c=0, d=3 -> phi = 12 / sqrt(7*3*4*6) = 0.5345; Fisher z at n=10.
    assert "table: both_correct=4 full_only=3 placebo_only=0 neither=3" in out
    assert "phi=0.5345" in out
    assert "phi_95_ci=[-0.1433, 0.8710]" in out
    assert "materially_positive=false" in out


def test_correlation_names_685_when_materially_positive(screen: ModuleType) -> None:
    epochs = _epochs(screen, "1111111110", "1111111100", "11000000", reused=2)
    epochs = [
        screen.Epoch(e.arm, e.launch, e.correct, e.void, False if e.arm != "null" else None)
        for e in epochs
    ]
    out = screen.render(screen.build_report(epochs, (1, 1)))
    assert "materially_positive=true" in out
    assert "an input #685 must model before any sizing is relied on" in out


# ---------------------------------------------------------------------------
# Pure interval functions, against worked literals
# ---------------------------------------------------------------------------


def test_newcombe_matches_a_worked_literal(screen: ModuleType) -> None:
    lo, hi = screen.newcombe_unpaired(34, 97, 34, 97)
    assert (round(lo, 4), round(hi, 4)) == (-0.1322, 0.1322)


def test_phi_interval_is_nan_with_a_zero_margin(screen: ModuleType) -> None:
    lo, hi = screen.phi_interval(5, 5, 0, 0)
    assert isnan(lo) and isnan(hi)


def test_the_n_scan_returns_the_smallest_n_when_exclusion_is_not_monotone(
    screen: ModuleType,
) -> None:
    """A doubling-and-bisection search from 4 would probe 8 (yes) and return 7, not 5."""
    excluding = {5, 7, 8, 9, 10}
    assert screen._first_excluding_n(lambda n: n in excluding, 4, 10) == 5
    assert screen._first_excluding_n(lambda n: False, 4, 10) is None


def test_both_conventions_find_the_first_excluding_n_on_all_zero_streams(
    screen: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

    monkeypatch.setattr(screen, "N_SEARCH_CAP", 60)
    zeros = [0.0] * 10
    n_even = screen.n_to_exclude_even(zeros, zeros, alpha_arm=0.025)
    n_repeat = screen.n_to_exclude_repeated(zeros, zeros, alpha_arm=0.025)
    assert n_even == n_repeat
    assert n_even is not None and 10 < n_even <= 60

    def ub(n: int) -> float:
        return one_sided_betting_bound([0.0] * n, alpha=0.025, side="upper")

    assert ub(n_even) < 0.20 <= ub(n_even - 1)


def test_repeated_cycles_the_real_order(screen: ModuleType) -> None:
    assert screen.repeated([1.0, 0.0, 0.0], 7) == [1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0]


# ---------------------------------------------------------------------------
# Cross-check against the run's recorded summary
# ---------------------------------------------------------------------------


def _recorded(report: dict[str, Any]) -> dict[str, Any]:
    from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

    xs = report["streams"]
    return {
        "arms": {
            "full": {"correct": 7, "manifest_read": 5},
            "placebo": {"correct": 4, "manifest_read": 3},
        },
        "null_a": {
            "n": 10,
            "correct": 4,
            "order": "Null-A reused epochs then new epochs in launch order",
        },
        "pairs": list(range(1, 11)),
        "void_epochs": [],
        "f_minus_n": {
            "each_at": 0.01045,
            "lb_mu_f": one_sided_betting_bound(xs["full"], alpha=0.01045, side="lower"),
            "ub_mu_n": one_sided_betting_bound(xs["null"], alpha=0.01045, side="upper"),
        },
    }


def test_cross_check_agrees_with_a_matching_summary(screen: ModuleType) -> None:
    report = screen.build_report(_small(screen), SMALL_REUSED)
    lines = screen.cross_check(report, _recorded(report))
    assert len(lines) == 11
    assert all(line.endswith("logs agree") for line in lines)


def test_cross_check_refuses_a_disagreeing_summary(screen: ModuleType) -> None:
    report = screen.build_report(_small(screen), SMALL_REUSED)
    recorded = _recorded(report)
    recorded["null_a"]["correct"] = 5
    with pytest.raises(ValueError, match="cross-check failed: null-a correct"):
        screen.cross_check(report, recorded)


# ---------------------------------------------------------------------------
# CLI over real .eval logs in the on-disk Stage 1A shape
# ---------------------------------------------------------------------------


def test_omitting_the_reused_null_readout_is_a_usage_error(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        screen.main([str(tmp_path)])
    assert exc.value.code == 2
    assert "--null-readout" in capsys.readouterr().err


_FACTS = "exit=0: origin_main=abc\norigin_moved=1\nattested_reachable={ok}\nteammate_reachable=1\n"
_FACTS += "merges_over_new=0\nlocal_work_held=1\nhead_is_origin=1\noperation_in_progress=0\n"


def _write_log(path: Path, arm: str, samples: list[tuple[bool, bool, bool]]) -> None:
    """One per-arm ``.eval`` log; each sample is (correct, read the trace file, void)."""
    from inspect_ai.log import (
        EvalConfig,
        EvalDataset,
        EvalLog,
        EvalSample,
        EvalSpec,
        write_eval_log,
    )
    from inspect_ai.model import ChatMessageAssistant, ChatMessageUser, ModelUsage
    from inspect_ai.scorer import Score
    from inspect_ai.tool import ToolCall

    built = []
    for epoch, (correct, read, void) in enumerate(samples, start=1):
        target = "/root/release-manifest.json" if read else "/root/README.md"
        call = ToolCall(id=f"t{epoch}", function="Read", arguments={"file_path": target})
        built.append(
            EvalSample(
                id=1,
                epoch=epoch,
                input="integrate",
                target="",
                messages=[
                    ChatMessageUser(content="integrate"),
                    ChatMessageAssistant(content="", tool_calls=[call]),
                ],
                scores={
                    "command_succeeds": Score(value="C", explanation=_FACTS.format(ok=int(correct)))
                },
                model_usage={}
                if void
                else {"anthropic/claude-sonnet-5": ModelUsage(input_tokens=1)},
            )
        )
    spec = EvalSpec(
        created="2026-09-28T00:00:00+00:00",
        task=f"v5cue-{arm}-world-a-cue",
        dataset=EvalDataset(),
        model="anthropic/claude-sonnet-5",
        config=EvalConfig(),
        metadata={"cell_arm": arm, "cell_world": "a", "cell_cue": "present"},
    )
    write_eval_log(EvalLog(eval=spec, samples=built, status="success"), str(path))


def _eval_tree(tmp_path: Path) -> tuple[Path, Path]:
    """Four looks: Full and Placebo in each, Null-A from look 3 (looks 1-2 reused)."""
    looks = {
        1: {"full": (True, True, False), "placebo": (True, True, False)},
        2: {"full": (True, False, False), "placebo": (False, False, False)},
        3: {
            "full": (False, False, False),
            "placebo": (True, False, True),
            "null": (True, False, False),
        },
        4: {
            "full": (True, True, False),
            "placebo": (False, True, False),
            "null": (False, False, False),
        },
    }
    log_dir = tmp_path / "S486-stage1a" / "run"
    for look, arms in looks.items():
        look_dir = log_dir / f"look-{look:03d}"
        look_dir.mkdir(parents=True)
        for arm, sample in arms.items():
            _write_log(look_dir / f"2026-09-28_v5cue-{arm}-world-a-cue_{look}.eval", arm, [sample])
    rows = [
        {"arm": "null", "world": "a", "epoch": 1, "final_world_correct": False, "void": False},
        {"arm": "null", "world": "a", "epoch": 2, "final_world_correct": True, "void": False},
    ]
    readout = tmp_path / "S475-readout.json"
    readout.write_text(json.dumps({"rows": rows, "summary": {"null/a": {"n": 2, "correct": 1}}}))
    return log_dir.parent, readout


def test_cli_reads_the_eval_logs_in_the_real_on_disk_shape(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("inspect_ai")
    run_dir, readout = _eval_tree(tmp_path)
    assert screen.main([str(run_dir), "--null-readout", str(readout)]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[1] == "P 100"
    assert out.splitlines()[2] == "N 0110"
    assert out.splitlines()[3] == "F 1101"
    assert "void_epochs: placebo#3" in out
    assert "n_placebo=3 correct_placebo=1" in out
    assert "n_null=4 correct_null=2" in out
    assert "  full: 2/4 = 0.500" in out
    assert "  placebo: 2/3 = 0.667" in out
    assert "full_correct_among_read: 2/2 = 1.000" in out
    assert "placebo_correct_among_unread: 0/1 = 0.000" in out
    assert "n_pairs=3" in out
    assert "table: both_correct=1 full_only=2 placebo_only=0 neither=0" in out
    assert "cross_check: skipped (no run.log beside the logs)" in out


def test_resolve_run_accepts_the_run_dir_its_run_log_and_the_log_dir(
    screen: ModuleType, tmp_path: Path
) -> None:
    log_dir = tmp_path / "run"
    (log_dir / "look-001").mkdir(parents=True)
    run_log = tmp_path / "run.log"
    run_log.write_text("noise\n{}\n")
    assert screen.resolve_run(tmp_path) == (log_dir, run_log)
    assert screen.resolve_run(run_log) == (log_dir, run_log)
    assert screen.resolve_run(log_dir) == (log_dir, None)
    with pytest.raises(ValueError, match="no look-"):
        screen.resolve_run(tmp_path / "run" / "look-001")
