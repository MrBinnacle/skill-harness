"""Tests for #639: the #621 Stage 1 launcher dry run builds two Null tasks and calls no model."""

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


def _fixture_present() -> bool:
    cue_audit = _load("cue_audit")
    return bool((cue_audit.FIXTURE_ROOT_DEFAULT / "fixture_shas.json").is_file())


@pytest.mark.skipif(
    not _fixture_present(),
    reason="the v5-cue fixture is private and lives only on the steering host",
)
def test_dry_run_builds_the_two_null_tasks_and_calls_no_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inspect_ai = pytest.importorskip("inspect_ai")
    stage1 = _load("v5_cue_stage1")

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the dry run called eval")

    monkeypatch.setattr(inspect_ai, "eval", refuse)
    seen: dict[str, Any] = {}
    real_build = stage1.build_cells

    def record(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return real_build(**kwargs)

    monkeypatch.setattr(stage1, "build_cells", record)

    assert stage1.main(["--out", str(tmp_path / "logs"), "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "DRY RUN: no model call." in out
    assert "v5cue-null-world-a-cue" in out and "v5cue-null-world-b" in out
    assert not (tmp_path / "logs").exists()
    assert seen["epochs"] == 8
    assert seen["retry_uncaught_errors"] == 1
    assert pytest.approx(0.75) == stage1.PER_SAMPLE_CAP
    assert pytest.approx(12.00) == stage1.HARD_CAP_USD
    assert stage1.MODEL == "anthropic/claude-sonnet-5"


@pytest.mark.skipif(
    not _fixture_present(),
    reason="the v5-cue fixture is private and lives only on the steering host",
)
def test_stage1_tasks_are_null_in_both_worlds_at_eight_epochs(tmp_path: Path) -> None:
    pytest.importorskip("inspect_ai")
    stage1 = _load("v5_cue_stage1")
    _, tasks = stage1.stage1_tasks(tmp_path / "compose")
    assert [t.name for t in tasks] == ["v5cue-null-world-a-cue", "v5cue-null-world-b"]
    assert [t.metadata["cell_arm"] for t in tasks] == ["null", "null"]
    assert [t.metadata["cell_world"] for t in tasks] == ["a", "b"]
    assert [t.epochs for t in tasks] == [8, 8]
