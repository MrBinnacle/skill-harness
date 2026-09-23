"""Tests for #651: the inertness-screen launcher. No model."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_continue_when_lb_diff_not_positive() -> None:
    screen = _load("v5_inertness_screen")
    result = screen.inertness_screen(placebo_correct=8, placebo_n=16, null_correct=5, null_n=8)
    assert result["outcome"] == "CONTINUE"
    assert result["lb_diff"] <= 0


def test_redesign_when_lb_diff_positive() -> None:
    screen = _load("v5_inertness_screen")
    result = screen.inertness_screen(placebo_correct=16, placebo_n=16, null_correct=1, null_n=8)
    assert result["outcome"] == "REDESIGN"
    assert result["lb_diff"] > 0


def test_cant_tell_yet_when_too_few_placebo_epochs() -> None:
    screen = _load("v5_inertness_screen")
    result = screen.inertness_screen(placebo_correct=5, placebo_n=10, null_correct=5, null_n=8)
    assert result["outcome"] == "CANT_TELL_YET"
    assert "fewer than" in result["reason"]


def test_screen_refuses_a_null_b_count_other_than_eight() -> None:
    screen = _load("v5_inertness_screen")
    with pytest.raises(ValueError, match="Null-B must contain 8 valid epochs"):
        screen.inertness_screen(placebo_correct=8, placebo_n=16, null_correct=4, null_n=7)


def test_screen_refuses_more_than_the_registered_placebo_epochs() -> None:
    screen = _load("v5_inertness_screen")
    with pytest.raises(ValueError, match="registered maximum is 16"):
        screen.inertness_screen(placebo_correct=17, placebo_n=17, null_correct=4, null_n=8)


def test_screen_never_passes_on_p_gt_005() -> None:
    """The screen never uses p > 0.05 as a pass criterion."""
    screen = _load("v5_inertness_screen")
    # Even when placebo and null are equal, the outcome is CONTINUE, not PASS.
    result = screen.inertness_screen(placebo_correct=8, placebo_n=16, null_correct=4, null_n=8)
    assert result["outcome"] == "CONTINUE"


def test_null_b_loader_reads_summary(tmp_path: Path) -> None:
    screen = _load("v5_inertness_screen")
    readout = {
        "summary": {"null/b": {"n": 8, "correct": 5}},
        "rows": [],
    }
    path = tmp_path / "readout.json"
    path.write_text(json.dumps(readout))
    correct, n = screen._load_null_b(path)
    assert (correct, n) == (5, 8)


def test_placebo_b_loader_reads_rows(tmp_path: Path) -> None:
    screen = _load("v5_inertness_screen")
    readout = {
        "summary": {},
        "rows": [
            {
                "arm": "placebo",
                "world": "b",
                "epoch": 1,
                "void": False,
                "final_world_correct": True,
            },
            {
                "arm": "placebo",
                "world": "b",
                "epoch": 2,
                "void": False,
                "final_world_correct": False,
            },
            {
                "arm": "placebo",
                "world": "b",
                "epoch": 3,
                "void": True,
                "final_world_correct": False,
            },
            {
                "arm": "full",
                "world": "a",
                "epoch": 1,
                "void": False,
                "final_world_correct": True,
            },
        ],
    }
    path = tmp_path / "readout.json"
    path.write_text(json.dumps(readout))
    correct, n = screen._load_placebo_b(path)
    assert (correct, n) == (1, 2)


def test_inertness_tasks_launches_only_the_sixteen_epoch_placebo_b_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    screen = _load("v5_inertness_screen")
    pin = SimpleNamespace()
    captured: dict[str, object] = {}

    def capture(**kwargs: object) -> SimpleNamespace:
        captured["pin"] = kwargs
        return pin

    def build(**kwargs: object) -> dict[tuple[str, str], SimpleNamespace]:
        captured["build"] = kwargs
        return {("placebo", "b"): SimpleNamespace(name="v5cue-placebo-world-b")}

    monkeypatch.setattr(screen.HarnessPin, "capture", staticmethod(capture))
    monkeypatch.setattr(screen, "build_cells", build)
    actual_pin, tasks = screen.inertness_tasks(tmp_path)

    assert actual_pin is pin
    assert [task.name for task in tasks] == ["v5cue-placebo-world-b"]
    assert captured["build"] == {
        "fixture_root": screen.FIXTURE_ROOT_DEFAULT,
        "full_dir": screen.FULL_DIR_DEFAULT,
        "pin": pin,
        "epochs": 16,
        "compose_dir": tmp_path,
        "retry_uncaught_errors": 1,
    }


def test_dry_run_prints_no_model(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    screen = _load("v5_inertness_screen")
    argv = [
        "--out",
        str(tmp_path / "logs"),
        "--null-readout",
        str(tmp_path / "n.json"),
        "--dry-run",
    ]
    assert screen.main(argv) == 0
    out = capsys.readouterr().out
    assert "DRY RUN: no model call." in out
    assert str(tmp_path / "logs") in out
