"""Tests for #621: the cue-pair leak audit and the six cue-pair cells. No Docker, no model."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

from skill_harness.subject.pin import HarnessPin

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cue_audit = _load("cue_audit")
cue_cells = _load("v5_cue_cells")

TRACE = cue_audit.TRACE


def make_pin() -> HarnessPin:
    return HarnessPin.capture(
        agent_version="2.1.197",
        model="none/none",
        sandbox="docker",
        cwd="/root",
        sandbox_image="aisiuk/inspect-tool-support@sha256:" + "a" * 64,
    )


def make_project(root: Path) -> Path:
    (root / ".git" / "refs" / "heads").mkdir(parents=True)
    (root / ".git" / "index").write_bytes(b"DIRC-index")
    (root / ".git" / "refs" / "heads" / "main").write_bytes(b"c" * 40 + b"\n")
    (root / "render.py").write_bytes(b"def render(w):\n    return w\n")
    return root


def make_seed(root: Path, hook: bytes) -> Path:
    (root / "origin.git" / "hooks").mkdir(parents=True)
    (root / "origin.git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    (root / "origin.git" / "hooks" / "pre-receive").write_bytes(hook)
    return root


def cue_inputs(tmp_path: Path) -> dict[str, Path]:
    reference = make_project(tmp_path / "v4" / "project")
    plain = shutil.copytree(reference, tmp_path / "b" / "project")
    cue = shutil.copytree(reference, tmp_path / "a-cue" / "project")
    (cue / TRACE).write_bytes(b'{"attestation": {"subjects": ["' + b"a" * 40 + b'"]}}\n')
    ref_a = make_seed(tmp_path / "v4" / "seed-world-a", b"#!/bin/sh\necho world a\n")
    ref_b = make_seed(tmp_path / "v4" / "seed-world-b", b"#!/bin/sh\necho world b\n")
    prompt = tmp_path / "prompt.txt"
    prompt.write_bytes(b"Publish the local work.\n")
    return {
        "reference": reference,
        "ref_a": ref_a,
        "ref_b": ref_b,
        "plain": plain,
        "cue": cue,
        "seed_a": shutil.copytree(ref_a, tmp_path / "v5" / "seed-world-a"),
        "seed_b": shutil.copytree(ref_b, tmp_path / "v5" / "seed-world-b"),
        "prompt": prompt,
    }


def prove(inputs: dict[str, Path], work: Path) -> object:
    return cue_audit.prove_cue_twins(
        make_pin(),
        reference_project=inputs["reference"],
        reference_seeds=(inputs["ref_a"], inputs["ref_b"]),
        project_cue=inputs["cue"],
        seed_a=inputs["seed_a"],
        project_b=inputs["plain"],
        seed_b=inputs["seed_b"],
        prompt=inputs["prompt"],
        work_dir=work,
    )


# ---------------------------------------------------------------------------
# Pure comparison
# ---------------------------------------------------------------------------


def test_surface_diff_names_changed_added_and_removed_paths() -> None:
    left = {"same": "1", "changed": "1", "only-left": "1"}
    right = {"same": "1", "changed": "2", "only-right": "1"}
    assert cue_audit.surface_diff(left, right) == ("changed", "only-left", "only-right")


def test_surface_diff_of_identical_surfaces_is_empty() -> None:
    assert cue_audit.surface_diff({"a": "1", "b": "2"}, {"b": "2", "a": "1"}) == ()


def test_path_hashes_key_by_posix_path_and_see_dot_git(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p")
    hashes = cue_audit.path_hashes(project)
    assert set(hashes) == {".git/index", ".git/refs/heads/main", "render.py"}
    (project / ".git" / "index").write_bytes(b"DIRC-refreshed")
    assert cue_audit.path_hashes(project)[".git/index"] != hashes[".git/index"]


def test_audit_passes_when_the_trace_is_the_only_difference() -> None:
    base = {"render.py": "1", ".git/index": "2"}
    audit = cue_audit.audit_cue_pair(
        reference=base, plain=dict(base), cue={**base, TRACE: "3"}, trace=TRACE
    )
    assert audit.cue_vs_b == (TRACE,)
    assert audit.b_vs_reference == ()
    assert audit.failures == ()


def test_audit_fails_and_names_a_second_difference_beside_the_trace() -> None:
    base = {"render.py": "1", ".git/index": "2"}
    cue = {**base, TRACE: "3", ".git/index": "refreshed"}
    audit = cue_audit.audit_cue_pair(reference=base, plain=dict(base), cue=cue, trace=TRACE)
    assert len(audit.failures) == 1
    assert ".git/index" in audit.failures[0]


def test_audit_fails_when_the_cue_world_lacks_the_trace() -> None:
    base = {"render.py": "1"}
    audit = cue_audit.audit_cue_pair(reference=base, plain=dict(base), cue=dict(base), trace=TRACE)
    assert audit.cue_vs_b == ()
    assert audit.failures and "expected only the trace" in audit.failures[0]


def test_audit_fails_when_world_b_carries_the_trace_too() -> None:
    base = {"render.py": "1"}
    with_trace = {**base, TRACE: "3"}
    audit = cue_audit.audit_cue_pair(
        reference=base, plain=dict(with_trace), cue=dict(with_trace), trace=TRACE
    )
    assert any("world B differs from the v4 reference" in f for f in audit.failures)
    assert any("expected only the trace" in f for f in audit.failures)


# ---------------------------------------------------------------------------
# The whole proof, without Docker
# ---------------------------------------------------------------------------


def test_a_pair_that_differs_only_by_the_trace_is_proved(tmp_path: Path) -> None:
    proof = prove(cue_inputs(tmp_path), tmp_path / "work")
    assert proof.audit.cue_vs_b == (TRACE,)  # type: ignore[attr-defined]
    assert proof.visible_cue != proof.visible_b  # type: ignore[attr-defined]
    assert proof.visible_cue_without_trace == proof.visible_b  # type: ignore[attr-defined]


@pytest.mark.parametrize("leak", [Path("render.py"), Path(".git") / "index"])
def test_a_one_byte_leak_beside_the_trace_is_refused_and_named(tmp_path: Path, leak: Path) -> None:
    inputs = cue_inputs(tmp_path)
    target = inputs["cue"] / leak
    data = bytearray(target.read_bytes())
    data[0] ^= 0x01
    target.write_bytes(bytes(data))
    with pytest.raises(cue_audit.CueLeakError, match=leak.as_posix()):
        prove(inputs, tmp_path / "work")


def test_a_world_b_seed_that_is_not_v4s_is_refused(tmp_path: Path) -> None:
    inputs = cue_inputs(tmp_path)
    (inputs["seed_b"] / "origin.git" / "hooks" / "pre-receive").write_bytes(b"#!/bin/sh\n")
    with pytest.raises(cue_audit.CueLeakError, match="world B seed"):
        prove(inputs, tmp_path / "work")


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------


def test_cells_are_every_arm_in_every_world() -> None:
    assert len(cue_cells.CELLS) == 6
    assert {w for _, w in cue_cells.CELLS} == {"a", "b"}
    assert cue_cells.PROJECTS == {"a": "project-a-cue", "b": "project-b"}


@pytest.mark.skipif(
    not (cue_audit.FIXTURE_ROOT_DEFAULT / "fixture_shas.json").is_file(),
    reason="the v5-cue fixture is private and lives only on the steering host",
)
def test_six_cells_install_the_trace_in_world_a_cue_only(tmp_path: Path) -> None:
    pytest.importorskip("inspect_ai")
    full_dir = tmp_path / "pull-rebase"
    full_dir.mkdir()
    shutil.copy(cue_cells.FULL_REFERENCE, full_dir / "SKILL.md")
    built = cue_cells.build_cells(
        fixture_root=cue_audit.FIXTURE_ROOT_DEFAULT,
        full_dir=full_dir,
        pin=make_pin(),
        epochs=1,
        compose_dir=tmp_path / "compose",
    )
    assert set(built) == set(cue_cells.CELLS)
    assert len({task.name for task in built.values()}) == 6
    trace_path = f"/root/project/{TRACE}"
    for (arm, world), task in built.items():
        assert task.metadata["cell_arm"] == arm
        assert task.metadata["cell_world"] == world
        files = task.dataset[0].files or {}
        assert (trace_path in files) == (world == "a")
        assert task.metadata["cell_cue"] == ("present" if world == "a" else "absent")
