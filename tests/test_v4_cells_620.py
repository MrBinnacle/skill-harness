"""Tests for #620 item 8: the matched placebo card and the six twin-screen cells. No model."""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

from skill_harness.extractor.parser import parse_skill_file

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cells = _load("v4_cells")

PLACEBO = cells.PLACEBO_DIR / "SKILL.md"
FULL = cells.FULL_REFERENCE
INTEGRATION_TERMS = re.compile(
    r"\b(pull|pulls|pulling|rebase\w*|merg\w*|force|--force\w*|reflog|fetch\w*|amend\w*|"
    r"reset|rewrit\w*|ancestor\w*|fast-forward\w*|--ff\w*|history|origin|upstream|"
    r"cherry-pick\w*|diverg\w*|linear)\b",
    re.IGNORECASE,
)


def shape(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    return {
        "h2": len(re.findall(r"^## ", text, re.M)),
        "fences": text.count("```"),
        "steps": len(re.findall(r"^\d+\. ", text, re.M)),
        "bullets": len(re.findall(r"^- ", text, re.M)),
    }


def test_cells_are_every_arm_in_every_world() -> None:
    assert len(cells.CELLS) == 6
    assert set(cells.CELLS) == {(a, w) for a in ("null", "full", "placebo") for w in ("a", "b")}


def test_placebo_matches_the_card_section_for_section() -> None:
    assert shape(PLACEBO) == shape(FULL)


def test_placebo_length_and_description_are_within_the_match_band() -> None:
    placebo, full = parse_skill_file(PLACEBO), parse_skill_file(FULL)
    words_p, words_f = len(placebo.body.split()), len(full.body.split())
    assert abs(words_p - words_f) / words_f <= 0.10, (words_p, words_f)
    desc_p = len(str(placebo.frontmatter["description"]))
    desc_f = len(str(full.frontmatter["description"]))
    assert abs(desc_p - desc_f) / desc_f <= 0.15, (desc_p, desc_f)


def test_placebo_is_silent_on_integration_strategy() -> None:
    hits = INTEGRATION_TERMS.findall(PLACEBO.read_text(encoding="utf-8"))
    assert hits == []


def test_the_lint_catches_the_card_it_guards_against() -> None:
    hits = {h.lower() for h in INTEGRATION_TERMS.findall(FULL.read_text(encoding="utf-8"))}
    assert {"pull", "rebase", "merge", "reflog"} <= hits


def test_placebo_name_matches_its_directory() -> None:
    assert parse_skill_file(PLACEBO).frontmatter["name"] == cells.PLACEBO_DIR.name


def test_a_drifted_full_card_is_refused_before_anything_is_built(tmp_path: Path) -> None:
    drifted = tmp_path / "pull-rebase"
    drifted.mkdir()
    (drifted / "SKILL.md").write_bytes(FULL.read_bytes() + b"\nOne more line.\n")
    with pytest.raises(ValueError, match="differs from the reviewed copy"):
        cells.build_cells(
            fixture_root=tmp_path / "absent",
            full_dir=drifted,
            pin=None,
            epochs=1,
            compose_dir=tmp_path,
        )


@pytest.mark.skipif(
    not (cells.FIXTURE_ROOT_DEFAULT / "fixture_shas.json").is_file(),
    reason="the v4 fixture is private and lives only on the steering host",
)
def test_six_distinct_tasks_build_from_the_private_fixture(tmp_path: Path) -> None:
    pytest.importorskip("inspect_ai")
    from skill_harness.subject.pin import HarnessPin

    full_dir = tmp_path / "pull-rebase"
    full_dir.mkdir()
    shutil.copy(FULL, full_dir / "SKILL.md")
    pin = HarnessPin.capture(
        agent_version="2.1.197",
        model="none/none",
        sandbox="docker",
        cwd="/root",
        sandbox_image="aisiuk/inspect-tool-support@sha256:" + "a" * 64,
    )
    built = cells.build_cells(
        fixture_root=cells.FIXTURE_ROOT_DEFAULT,
        full_dir=full_dir,
        pin=pin,
        epochs=1,
        compose_dir=tmp_path / "compose",
    )
    assert set(built) == set(cells.CELLS)
    assert len({task.name for task in built.values()}) == 6
    for (arm, world), task in built.items():
        assert task.metadata["cell_arm"] == arm
        assert task.metadata["cell_world"] == world
