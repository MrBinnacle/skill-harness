"""Tests for #691: the Stage 1A readout screen (inertness, adherence, within-pair correlation).

No model call. The screen reads a readout path (a ``.json`` file, a ``run.log`` whose
tail carries a JSON block, or a directory holding either) and prints three sections.
A synthetic fixture with known counts pins every printed number.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from statistics import NormalDist
from types import ModuleType
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


@pytest.fixture(scope="module")
def screen() -> ModuleType:
    return _load("stage1a_readout_691")


def _evenly_spaced(n: int, k: int) -> list[float]:
    if k <= 0:
        return [0.0] * n
    if k >= n:
        return [1.0] * n
    xs = [0.0] * n
    for i in range(k):
        pos = round((i + 0.5) * n / k)
        pos = min(n - 1, max(0, pos))
        xs[pos] = 1.0
    placed = sum(xs)
    j = 0
    while placed < k and j < n:
        if xs[j] == 0.0:
            xs[j] = 1.0
            placed += 1
        j += 1
    return xs


def _fixture_rows() -> list[dict[str, Any]]:
    """n=10 with known counts and a stated joint structure.

    Full: 7/10 correct (epochs 1-7), manifest_read on epochs 1-5.
      read-to-outcome: 5/5 correct among read, 2/5 among unread.
    Placebo: 4/10 correct (epochs 1-4), manifest_read on epochs 1-3.
      read-to-outcome: 3/3 among read, 1/7 among unread.
    Null-A: 4/10 correct (epochs 1-4), no manifest_read flag.
    Full x Placebo pairs: both=4, full_only=3, placebo_only=0, neither=3.
    phi = (4*3 - 3*0) / sqrt(7*3*4*6) = 12/sqrt(504).
    """
    rows: list[dict[str, Any]] = []
    full_correct = {1, 2, 3, 4, 5, 6, 7}
    full_read = {1, 2, 3, 4, 5}
    placebo_correct = {1, 2, 3, 4}
    placebo_read = {1, 2, 3}
    null_correct = {1, 2, 3, 4}
    for epoch in range(1, 11):
        rows.append(
            {
                "arm": "full",
                "world": "a",
                "epoch": epoch,
                "void": False,
                "final_world_correct": epoch in full_correct,
                "manifest_read": epoch in full_read,
            }
        )
        rows.append(
            {
                "arm": "placebo",
                "world": "a",
                "epoch": epoch,
                "void": False,
                "final_world_correct": epoch in placebo_correct,
                "manifest_read": epoch in placebo_read,
            }
        )
        rows.append(
            {
                "arm": "null",
                "world": "a",
                "epoch": epoch,
                "void": False,
                "final_world_correct": epoch in null_correct,
            }
        )
    return rows


def _write_fixture(tmp_path: Path, *, name: str = "readout.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"rows": _fixture_rows()}), encoding="utf-8")
    return path


def _run(screen: ModuleType, path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    assert screen.main([str(path)]) == 0
    return capsys.readouterr().out


# ---------------------------------------------------------------------------
# Criterion 1 — Placebo inertness interval
# ---------------------------------------------------------------------------


def test_inertness_section_prints_the_anytime_valid_interval(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "Placebo inertness" in out
    placebo_xs = [1.0] * 4 + [0.0] * 6
    null_xs = [1.0] * 4 + [0.0] * 6
    lb_p = one_sided_betting_bound(placebo_xs, alpha=0.025, side="lower")
    ub_p = one_sided_betting_bound(placebo_xs, alpha=0.025, side="upper")
    lb_n = one_sided_betting_bound(null_xs, alpha=0.025, side="lower")
    ub_n = one_sided_betting_bound(null_xs, alpha=0.025, side="upper")
    expected_lo = lb_p - ub_n
    expected_hi = ub_p - lb_n
    assert f"anytime_valid_interval=[{expected_lo:.4f}, {expected_hi:.4f}]" in out


def test_inertness_section_states_the_counts_it_used(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "n_placebo=10 correct_placebo=4" in out
    assert "n_null=10 correct_null=4" in out


def test_inertness_exclusion_statement_is_false_at_this_n(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The n=10 interval is wide; it does not exclude +/-0.20, so inertness is not established."""
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "excludes_plus_minus_0.20=false" in out
    assert "inertness_established=false" in out
    assert "not established" in out


def test_inertness_prints_the_n_at_which_the_same_counts_exclude(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    # Same rate 4/10 under the evenly-spaced launch-order convention.
    assert "n_to_exclude_pm_0.20=286" in out


def test_n_to_exclude_retains_each_arm_rate(screen: ModuleType) -> None:
    """The projection must not replace the Null-A rate with the Placebo rate."""
    rows = _fixture_rows()
    for row in rows:
        if row["arm"] == "null" and row["epoch"] == 4:
            row["final_world_correct"] = False
    report = screen.render(screen.build_report({"rows": rows}))
    assert "n_to_exclude_pm_0.20=1463" in report


def test_inertness_prints_the_direct_fixed_n_comparison(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    z = NormalDist().inv_cdf(0.975)
    p = 0.4
    wilson_center = (4 + z * z / 2.0) / (10 + z * z)
    wilson_half_width = z * (4 * 6 / 10 + z * z / 4.0) ** 0.5 / (10 + z * z)
    wilson_lo, wilson_hi = wilson_center - wilson_half_width, wilson_center + wilson_half_width
    expected_half_width = ((p - wilson_lo) ** 2 + (wilson_hi - p) ** 2) ** 0.5
    assert (
        f"fixed_n_newcombe_interval=[{-expected_half_width:.4f}, {expected_half_width:.4f}]" in out
    )
    assert "fixed_n_excludes_plus_minus_0.20=false" in out


def test_inertness_uses_the_engine_bound_not_a_hand_rolled_one(screen: ModuleType) -> None:
    """The printed interval equals the engine's one_sided_betting_bound at 0.025 each."""
    placebo_xs = [1.0] * 4 + [0.0] * 6
    null_xs = [0.0] * 3 + [1.0] * 7  # a different order, same count
    result = screen.placebo_inertness(placebo_xs, null_xs)
    lb_p = one_sided_betting_bound(placebo_xs, alpha=0.025, side="lower")
    ub_p = one_sided_betting_bound(placebo_xs, alpha=0.025, side="upper")
    lb_n = one_sided_betting_bound(null_xs, alpha=0.025, side="lower")
    ub_n = one_sided_betting_bound(null_xs, alpha=0.025, side="upper")
    assert result["anytime_valid_lo"] == pytest.approx(lb_p - ub_n)
    assert result["anytime_valid_hi"] == pytest.approx(ub_p - lb_n)


def test_inertness_order_matters_for_the_anytime_valid_bound(screen: ModuleType) -> None:
    """The betting bound is order-sensitive; the screen must use launch order, not a sort."""
    first = screen.placebo_inertness([1.0] * 4 + [0.0] * 6, [1.0] * 4 + [0.0] * 6)
    shuffled = screen.placebo_inertness([0.0] * 3 + [1.0] * 4 + [0.0] * 3, [1.0] * 4 + [0.0] * 6)
    assert first["anytime_valid_lo"] != pytest.approx(shuffled["anytime_valid_lo"])


# ---------------------------------------------------------------------------
# Criterion 2 — Adherence, descriptive only
# ---------------------------------------------------------------------------


def test_adherence_assignment_to_read_rates(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "assignment_to_read" in out
    assert "full: 5/10 = 0.500" in out
    assert "placebo: 3/10 = 0.300" in out


def test_adherence_assignment_to_outcome_rates(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "assignment_to_outcome" in out
    assert "full: 7/10 = 0.700" in out
    assert "placebo: 4/10 = 0.400" in out


def test_adherence_read_to_outcome_rates(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "read_to_outcome" in out
    assert "full_correct_among_read: 5/5 = 1.000" in out
    assert "full_correct_among_unread: 2/5 = 0.400" in out
    assert "placebo_correct_among_read: 3/3 = 1.000" in out
    assert "placebo_correct_among_unread: 1/7 = 0.143" in out


def test_adherence_carries_the_post_treatment_sentence_verbatim(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    sentence = (
        "Manifest-read happens after assignment. "
        "Splitting outcomes by it conditions on a post-treatment variable. "
        "These are adherence descriptives, not a mechanism."
    )
    assert sentence in out


def test_adherence_never_reads_a_causal_claim(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "not a mechanism" in out
    assert (
        "causal" not in out.lower() or "no causal" in out.lower() or "not a causal" in out.lower()
    )


# ---------------------------------------------------------------------------
# Criterion 3 — Within-pair correlation
# ---------------------------------------------------------------------------


def test_correlation_section_prints_the_phi_and_table(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "Within-pair correlation" in out
    assert "n_pairs=10" in out
    assert "both_correct=4" in out
    assert "full_only=3" in out
    assert "placebo_only=0" in out
    assert "neither=3" in out
    # phi = 12 / sqrt(504)
    expected_phi = 12.0 / (504.0**0.5)
    assert f"phi={expected_phi:.4f}" in out


def test_correlation_prints_a_95pct_interval(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "phi_95_ci=[" in out
    from math import atanh, sqrt, tanh

    phi = 12.0 / sqrt(504.0)
    n = 10
    z = atanh(phi)
    se = 1.0 / sqrt(n - 3)
    zcrit = NormalDist().inv_cdf(0.975)
    lo = tanh(z - zcrit * se)
    hi = tanh(z + zcrit * se)
    assert f"phi_95_ci=[{lo:.4f}, {hi:.4f}]" in out
    assert lo < phi < hi


def test_correlation_names_685_when_materially_positive(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A high-concordance table yields a CI above zero, so the #685 note fires."""
    rows: list[dict[str, Any]] = []
    # a=8, b=1, c=0, d=1 -> phi = 8/12, Fisher-z CI lower bound > 0 at n=10.
    for epoch in range(1, 11):
        full_ok = epoch <= 9
        placebo_ok = epoch <= 8
        rows.append(
            {
                "arm": "full",
                "world": "a",
                "epoch": epoch,
                "void": False,
                "final_world_correct": full_ok,
                "manifest_read": epoch <= 5,
            }
        )
        rows.append(
            {
                "arm": "placebo",
                "world": "a",
                "epoch": epoch,
                "void": False,
                "final_world_correct": placebo_ok,
                "manifest_read": epoch <= 3,
            }
        )
        rows.append(
            {
                "arm": "null",
                "world": "a",
                "epoch": epoch,
                "void": False,
                "final_world_correct": epoch <= 4,
            }
        )
    path = tmp_path / "concordant.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    out = _run(screen, path, capsys)
    assert "materially_positive=true" in out
    assert "#685" in out
    assert "sizing" in out
    assert "phi_95_ci=[" in out


def test_correlation_note_when_not_materially_positive(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The n=10 fixture's phi CI includes zero; the screen says so and does not blame #685."""
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "materially_positive=false" in out
    assert "not contradicted" in out


def test_correlation_phi_matches_the_2x2_table(screen: ModuleType) -> None:
    result = screen.within_pair_correlation(_fixture_rows())
    assert result["both_correct"] == 4
    assert result["full_only"] == 3
    assert result["placebo_only"] == 0
    assert result["neither"] == 3
    expected_phi = (4 * 3 - 3 * 0) / ((7 * 3 * 4 * 6) ** 0.5)
    assert result["phi"] == pytest.approx(expected_phi)


def test_correlation_is_zero_for_a_balanced_independent_fixture(
    screen: ModuleType,
) -> None:
    """A balanced 2x2 table yields phi zero, so the screen can distinguish it from dependence."""
    rows: list[dict[str, Any]] = []
    # a=b=c=d=3, so ad-bc=0.
    full_bits = [1] * 6 + [0] * 6
    placebo_bits = [1] * 3 + [0] * 3 + [1] * 3 + [0] * 3
    for epoch, (f, p) in enumerate(zip(full_bits, placebo_bits, strict=True), start=1):
        rows.append(
            {
                "arm": "full",
                "world": "a",
                "epoch": epoch,
                "void": False,
                "final_world_correct": bool(f),
                "manifest_read": False,
            }
        )
        rows.append(
            {
                "arm": "placebo",
                "world": "a",
                "epoch": epoch,
                "void": False,
                "final_world_correct": bool(p),
                "manifest_read": False,
            }
        )
    result = screen.within_pair_correlation(rows)
    assert (
        result["both_correct"],
        result["full_only"],
        result["placebo_only"],
        result["neither"],
    ) == (
        3,
        3,
        3,
        3,
    )
    assert result["phi"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Script surface — path handling and printed structure
# ---------------------------------------------------------------------------


def test_script_accepts_a_run_log_path_with_json_at_the_tail(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.dumps({"rows": _fixture_rows()})
    log_path = tmp_path / "run.log"
    log_path.write_text("launcher noise\nmore noise\n" + payload + "\n", encoding="utf-8")
    out = _run(screen, log_path, capsys)
    assert "Placebo inertness" in out
    assert "Adherence" in out
    assert "Within-pair correlation" in out


def test_script_reads_the_last_json_object_from_a_run_log(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log_path = tmp_path / "run.log"
    log_path.write_text(
        '{"launcher": {"status": "complete"}}\n' + json.dumps({"rows": _fixture_rows()}) + "\n",
        encoding="utf-8",
    )
    out = _run(screen, log_path, capsys)
    assert "n_placebo=10 correct_placebo=4" in out


def test_script_uses_only_world_a_rows(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _fixture_rows()
    rows.extend(
        {
            "arm": arm,
            "world": "b",
            "epoch": 1,
            "void": False,
            "final_world_correct": False,
            "manifest_read": False,
        }
        for arm in ("full", "placebo", "null")
    )
    path = tmp_path / "both-worlds.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    out = _run(screen, path, capsys)
    assert "n_placebo=10 correct_placebo=4" in out
    assert "n_null=10 correct_null=4" in out


def test_script_accepts_a_directory_containing_run_log(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = tmp_path / "S486-stage1a"
    run_dir.mkdir()
    payload = json.dumps({"rows": _fixture_rows()})
    (run_dir / "run.log").write_text("noise\n" + payload + "\n", encoding="utf-8")
    out = _run(screen, run_dir, capsys)
    assert "Placebo inertness" in out


def test_script_refuses_a_readout_without_per_epoch_rows(
    screen: ModuleType, tmp_path: Path
) -> None:
    path = tmp_path / "counts_only.json"
    path.write_text(json.dumps({"arms": {"full": {"n": 10, "correct": 7}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="per-epoch rows"):
        screen.main([str(path)])


def test_script_prints_all_three_section_headers(
    screen: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(screen, _write_fixture(tmp_path), capsys)
    assert "=== Placebo inertness" in out
    assert "=== Adherence" in out
    assert "=== Within-pair correlation" in out


def test_main_returns_zero_on_a_well_formed_readout(screen: ModuleType, tmp_path: Path) -> None:
    assert screen.main([str(_write_fixture(tmp_path))]) == 0
