"""#764: the Full arm is the pull-rebase tree at tag v3.0.0 of MrBinnacle/skills, vendored here."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCREEN_DIR = _REPO / "scripts" / "screens" / "419"
_VENDORED = _SCREEN_DIR / "v4_arms" / "full" / "pull-rebase"

# `git ls-tree -r v3.0.0 skills/engineering/pull-rebase` in MrBinnacle/skills (commit 4c00b0e).
_TAG_V3_0_0_BLOBS = {
    "EVIDENCE.md": "94a21c159797fd56ac7fcf1dae18e9f4d6a192a4",
    "SKILL.md": "58e1c498d5d348439fce9f640e6fd114e6fd6a87",
    "evals/evals.json": "ca385d6df409c9a1b24600f59735f65bcfb24c39",
    "gotchas.md": "8adc163f5876e7ee23ab0196aef32cf02f7e57c4",
    "preventive-recipes.md": "cdc790ba07f6409b715da8602eb2fe72b69072b2",
}


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_the_default_full_dir_is_the_vendored_tree() -> None:
    assert _load("v4_cells").FULL_DIR_DEFAULT == _VENDORED


def test_the_vendored_tree_is_byte_identical_to_the_tag() -> None:
    assert _load("v4_cells").tree_blobs(_VENDORED) == _TAG_V3_0_0_BLOBS


def test_the_pinned_tree_is_the_tag() -> None:
    assert _load("v4_cells").FULL_TREE_BLOBS == _TAG_V3_0_0_BLOBS


@pytest.mark.parametrize("module", ["v4_cells", "v5_cue_cells"])
def test_a_drifted_sibling_file_is_refused(module: str, tmp_path: Path) -> None:
    drifted = tmp_path / "pull-rebase"
    shutil.copytree(_VENDORED, drifted)
    with (drifted / "gotchas.md").open("ab") as f:
        f.write(b"\nOne more line.\n")
    with pytest.raises(ValueError, match=r"differs from tag v3\.0\.0 in: gotchas\.md;"):
        _load(module).build_cells(
            fixture_root=tmp_path / "absent",
            full_dir=drifted,
            pin=None,
            epochs=1,
            compose_dir=tmp_path,
        )


def test_an_extra_or_missing_file_is_refused(tmp_path: Path) -> None:
    drifted = tmp_path / "pull-rebase"
    shutil.copytree(_VENDORED, drifted)
    (drifted / "evals" / "evals.json").unlink()
    (drifted / "notes.md").write_bytes(b"extra\n")
    with pytest.raises(ValueError, match=r"in: evals/evals\.json, notes\.md;"):
        _load("v4_cells").build_cells(
            fixture_root=tmp_path / "absent",
            full_dir=drifted,
            pin=None,
            epochs=1,
            compose_dir=tmp_path,
        )


def test_no_screen_launcher_reads_the_plugin_cache() -> None:
    readers = [
        p.name for p in sorted(_SCREEN_DIR.glob("*.py")) if "plugins/cache" in p.read_text("utf-8")
    ]
    assert readers == []
