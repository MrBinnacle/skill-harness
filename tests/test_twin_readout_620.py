"""Tests for the #620 twin-screen read-out summary. No model, no logs."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pytest.importorskip("inspect_ai")
readout = _load("twin_readout")


def row(
    world: str,
    action: str,
    *,
    correct: bool = True,
    moved: bool = True,
    void: bool = False,
    usd: float = 0.1,
) -> Any:
    return readout.EpochRow(
        arm="null",
        world=world,
        epoch=1,
        first_action=action,
        final_world_correct=correct,
        refused=False,
        recovered=False,
        silent_violation=moved and not correct,
        no_publish=not moved,
        completed=correct,
        skill_invoked=False,
        usd=0.0 if void else usd,
        void=void,
    )


def test_a_void_epoch_is_listed_and_left_out_of_the_cell_counts() -> None:
    summary = readout.summarise(
        [row("b", "rebase"), row("b", "merge"), row("b", "none", correct=False, void=True)]
    )
    assert summary["null/b"]["n"] == 2
    assert summary["null/b"]["correct"] == 2
    assert summary["null/b"]["first_action"] == {"rebase": 1, "merge": 1}
    assert summary["void_epochs"] == ["null/b#1"]


def test_cells_are_kept_apart_by_world_and_cost_is_summed() -> None:
    summary = readout.summarise([row("a", "merge", usd=0.25), row("b", "merge", usd=0.5)])
    assert summary["null/a"]["n"] == 1
    assert summary["null/b"]["n"] == 1
    assert summary["total_usd"] == 0.75


def test_y_zero_is_split_into_silent_violation_and_no_publish_per_cell() -> None:
    summary = readout.summarise(
        [
            row("a", "merge"),
            row("a", "rebase", correct=False),
            row("a", "rebase", correct=False),
            row("a", "none", correct=False, moved=False),
            row("b", "merge", correct=False),
        ]
    )
    cell = summary["null/a"]
    counts = (cell["n"], cell["correct"], cell["silent_violation"], cell["no_publish"])
    assert counts == (4, 1, 2, 1)
    assert summary["null/b"]["silent_violation"] == 1
    assert summary["null/b"]["no_publish"] == 0
