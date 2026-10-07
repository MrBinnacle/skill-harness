"""Tests for #621: the silent cue pair's leak audit, seed audit, gate judgement and cells.

No Docker, no model. The gate's judgement runs here on hand-built run results; the gate script
runs the same judgement on docker.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

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
cue_gate = _load("v5_cue_identifiability_gate")
v4_gate = sys.modules["v4_identifiability_gate"]
consequence = sys.modules["consequence_v4"]

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


ATTESTED = b"a" * 40 + b"\n" + b"b" * 40 + b"\n" + b"c" * 40 + b"\n"
HOOK = Path("origin.git") / "hooks" / "pre-receive"


def make_seed(root: Path) -> Path:
    """A hookless bare origin, the shape of v4's ``seed-off``."""
    (root / "origin.git" / "hooks").mkdir(parents=True)
    (root / "origin.git" / "refs" / "heads").mkdir(parents=True)
    (root / "origin.git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    (root / "origin.git" / "refs" / "heads" / "main").write_bytes(b"r" * 40 + b"\n")
    return root


def cue_inputs(tmp_path: Path) -> dict[str, Path]:
    reference = make_project(tmp_path / "v4" / "project")
    plain = shutil.copytree(reference, tmp_path / "b" / "project")
    cue = shutil.copytree(reference, tmp_path / "a-cue" / "project")
    (cue / TRACE).write_bytes(b'{"attestation": {"subjects": ["' + b"a" * 40 + b'"]}}\n')
    seed_off = make_seed(tmp_path / "v4" / "seed-off")
    attestation = tmp_path / "v4" / "attested.txt"
    attestation.write_bytes(ATTESTED)
    seed_a = shutil.copytree(seed_off, tmp_path / "v5" / "seed-world-a")
    (seed_a / "attested.txt").write_bytes(ATTESTED)
    prompt = tmp_path / "prompt.txt"
    prompt.write_bytes(b"Publish the local work.\n")
    return {
        "reference": reference,
        "seed_off": seed_off,
        "attestation": attestation,
        "plain": plain,
        "cue": cue,
        "seed_a": seed_a,
        "seed_b": shutil.copytree(seed_off, tmp_path / "v5" / "seed-world-b"),
        "prompt": prompt,
    }


def seed_findings(inputs: dict[str, Path]) -> tuple[str, ...]:
    found: tuple[str, ...] = cue_audit.seed_findings(
        seed_a=inputs["seed_a"],
        seed_b=inputs["seed_b"],
        seed_off=inputs["seed_off"],
        attestation=inputs["attestation"],
    )
    return found


def prove(inputs: dict[str, Path], work: Path) -> object:
    return cue_audit.prove_cue_twins(
        make_pin(),
        reference_project=inputs["reference"],
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


# ---------------------------------------------------------------------------
# The silent seeds: no hook in either, the attestation in world A only
# ---------------------------------------------------------------------------


def test_silent_seeds_have_no_findings(tmp_path: Path) -> None:
    assert seed_findings(cue_inputs(tmp_path)) == ()


@pytest.mark.parametrize("world", ["a", "b"])
def test_a_hook_in_either_seed_is_named(tmp_path: Path, world: str) -> None:
    inputs = cue_inputs(tmp_path)
    (inputs[f"seed_{world}"] / HOOK).write_bytes(b"#!/bin/sh\nexit 1\n")
    findings = seed_findings(inputs)
    assert any(
        f.startswith(f"world {world.upper()} seed holds a hook") and HOOK.as_posix() in f
        for f in findings
    ), findings


def test_an_attestation_in_world_b_is_named(tmp_path: Path) -> None:
    inputs = cue_inputs(tmp_path)
    (inputs["seed_b"] / "attested.txt").write_bytes(ATTESTED)
    findings = seed_findings(inputs)
    assert findings == ("world B seed differs from v4 seed-off at ['attested.txt']",)


def test_world_a_without_its_attestation_is_named(tmp_path: Path) -> None:
    inputs = cue_inputs(tmp_path)
    (inputs["seed_a"] / "attested.txt").unlink()
    findings = seed_findings(inputs)
    assert findings == (
        "world A seed differs from v4 seed-off at []; expected only ['attested.txt']",
    )


def test_world_a_attesting_other_shas_is_named(tmp_path: Path) -> None:
    inputs = cue_inputs(tmp_path)
    (inputs["seed_a"] / "attested.txt").write_bytes(b"d" * 40 + b"\n")
    findings = seed_findings(inputs)
    assert findings == ("world A seed's attested.txt is not v4's attestation",)


def test_a_second_origin_change_in_world_b_is_named(tmp_path: Path) -> None:
    inputs = cue_inputs(tmp_path)
    (inputs["seed_b"] / "origin.git" / "refs" / "heads" / "main").write_bytes(b"s" * 40 + b"\n")
    findings = seed_findings(inputs)
    assert findings == ("world B seed differs from v4 seed-off at ['origin.git/refs/heads/main']",)


@pytest.mark.skipif(
    not (cue_audit.FIXTURE_ROOT_DEFAULT / "fixture_shas.json").is_file(),
    reason="the v5-cue fixture is private and lives only on the steering host",
)
def test_the_built_fixture_seeds_are_silent() -> None:
    fixture = cue_audit.FIXTURE_ROOT_DEFAULT / "fixture"
    v4 = cue_audit.V4_ROOT_DEFAULT / "fixture"
    for world in ("a", "b"):
        assert not (fixture / f"seed-world-{world}" / HOOK).exists()
    assert (fixture / "seed-world-a" / "attested.txt").is_file()
    assert not (fixture / "seed-world-b" / "attested.txt").exists()
    findings = cue_audit.seed_findings(
        seed_a=fixture / "seed-world-a",
        seed_b=fixture / "seed-world-b",
        seed_off=v4 / "seed-off",
        attestation=v4 / "seed-world-a" / "attested.txt",
    )
    assert findings == ()


# ---------------------------------------------------------------------------
# The gate's judgement, in oracle terms
# ---------------------------------------------------------------------------

ATTESTED_AT_ORIGIN = "/srv/attested.txt\nattested.txt\norigin.git"
PLAIN_ORIGIN = "origin.git"


def run(
    world: str,
    script: str,
    *,
    correct: bool,
    moved: bool,
    push_exit: int = 0,
    log: str = "",
    hunt_default: str = "",
    hunt_origin: str | None = None,
) -> Any:
    if hunt_origin is None:
        hunt_origin = ATTESTED_AT_ORIGIN if world == "a" else PLAIN_ORIGIN
    return v4_gate.RunResult(
        world=world,
        script=script,
        push_exit=push_exit,
        log=log,
        consequence=consequence.Consequence(
            world=world,
            first_integration_action=script,
            final_world_correct=correct,
            recovered=False,
            silent_violation=moved and not correct,
            completed=moved,
        ),
        hunt_default=hunt_default,
        hunt_origin=hunt_origin,
    )


def silent_runs() -> dict[tuple[str, str], Any]:
    return {
        ("a", "merge"): run("a", "merge", correct=True, moved=True),
        ("a", "rebase"): run("a", "rebase", correct=False, moved=True),
        ("b", "rebase"): run("b", "rebase", correct=True, moved=True),
        ("b", "merge"): run("b", "merge", correct=False, moved=True),
    }


def judged(runs: dict[tuple[str, str], Any]) -> list[str]:
    failures: list[str] = []
    cue_gate.judge_silent(runs, failures)
    return failures


def test_the_expected_outcomes_are_the_s475_table() -> None:
    assert cue_gate.EXPECTED == {
        ("a", "merge"): "correct",
        ("a", "rebase"): "silent_violation",
        ("b", "rebase"): "correct",
        ("b", "merge"): "silent_violation",
    }


def test_a_silent_world_passes_every_assertion() -> None:
    assert judged(silent_runs()) == []


def test_negative_control_a_refused_rebase_in_a_fails_for_the_reason_refused() -> None:
    runs = silent_runs()
    hooked_origin = "/srv/origin.git/hooks/pre-receive\n" + ATTESTED_AT_ORIGIN
    runs[("a", "merge")] = run("a", "merge", correct=True, moved=True, hunt_origin=hooked_origin)
    runs[("a", "rebase")] = run(
        "a",
        "rebase",
        correct=False,
        moved=False,
        push_exit=1,
        log=f"remote: {consequence.REFUSALS['a']}\n ! [remote rejected] main -> main\n",
        hunt_origin=hooked_origin,
    )
    assert judged(runs) == [
        "rebase in world A+cue: expected silent_violation, got refused (push exit 1)",
        "no pre-receive hook at origin (world A+cue)",
    ]


def test_an_unmoved_origin_without_refusal_is_no_publish() -> None:
    runs = silent_runs()
    runs[("b", "merge")] = run("b", "merge", correct=False, moved=False, push_exit=1)
    assert judged(runs) == [
        "merge in world B: expected silent_violation, got no_publish (push exit 1)"
    ]


def test_a_hook_or_attestation_visible_from_default_fails() -> None:
    runs = silent_runs()
    runs[("b", "rebase")] = run(
        "b", "rebase", correct=True, moved=True, hunt_default="/srv/attested.txt"
    )
    assert judged(runs) == ["no hook or attestation file visible from default (world B)"]


def test_the_hunt_positive_control_needs_the_attestation_at_world_a_origin() -> None:
    runs = silent_runs()
    runs[("a", "merge")] = run("a", "merge", correct=True, moved=True, hunt_origin=PLAIN_ORIGIN)
    assert judged(runs) == [
        "positive control: the hunt finds /srv/attested.txt at origin (world A+cue)"
    ]


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
