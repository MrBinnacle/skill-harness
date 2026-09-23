"""Tests for #651: the inertness-screen launcher. No model."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

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


def test_dry_run_prints_no_model(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    screen = _load("v5_inertness_screen")
    argv = [
        "--placebo-readout",
        str(tmp_path / "p.json"),
        "--null-readout",
        str(tmp_path / "n.json"),
        "--dry-run",
    ]
    assert screen.main(argv) == 0
    out = capsys.readouterr().out
    assert "DRY RUN: no model call." in out
