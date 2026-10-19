"""Tests for the #620 twin-world fixture gate: the visible-surface digest and
the world-conditioned consequence oracle. Pure stdlib; no Docker, no model."""

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


twin_digest = _load("twin_digest")
consequence = _load("consequence_v4")

PINNED_IMAGE = "aisiuk/inspect-tool-support@sha256:" + "a" * 64


def make_pin() -> HarnessPin:
    return HarnessPin.capture(
        agent_version="2.1.197",
        model="none/none",
        sandbox="docker",
        cwd="/root",
        sandbox_image=PINNED_IMAGE,
    )


def make_project(root: Path) -> Path:
    (root / ".git" / "refs" / "heads").mkdir(parents=True)
    (root / ".git" / "config").write_bytes(b"[pull]\n\trebase = true\n")
    (root / ".git" / "refs" / "heads" / "main").write_bytes(b"c" * 40 + b"\n")
    (root / "render.py").write_bytes(b"def render(w):\n    return w\n")
    return root


def make_seed(root: Path, hook: bytes) -> Path:
    (root / "origin.git" / "hooks").mkdir(parents=True)
    (root / "origin.git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    (root / "origin.git" / "hooks" / "pre-receive").write_bytes(hook)
    return root


def twin_inputs(tmp_path: Path) -> dict[str, Path]:
    project_a = make_project(tmp_path / "a" / "project")
    project_b = shutil.copytree(project_a, tmp_path / "b" / "project")
    seed_a = make_seed(tmp_path / "seed-world-a", b"#!/bin/sh\necho world a\n")
    (seed_a / "attested.txt").write_bytes(b"a" * 40 + b"\n")
    seed_b = make_seed(tmp_path / "seed-world-b", b"#!/bin/sh\necho world b\n")
    prompt = tmp_path / "prompt.txt"
    prompt.write_bytes(b"Publish the local work.\n")
    return {
        "project_a": project_a,
        "project_b": project_b,
        "seed_a": seed_a,
        "seed_b": seed_b,
        "prompt": prompt,
    }


def prove(inputs: dict[str, Path], work: Path) -> Any:
    return twin_digest.prove_twin_worlds(
        make_pin(),
        project_a=inputs["project_a"],
        seed_a=inputs["seed_a"],
        project_b=inputs["project_b"],
        seed_b=inputs["seed_b"],
        prompt=inputs["prompt"],
        work_dir=work,
    )


# ---------------------------------------------------------------------------
# Visible-surface digest
# ---------------------------------------------------------------------------


def test_twins_that_differ_only_in_the_seed_pass(tmp_path: Path) -> None:
    proof = prove(twin_inputs(tmp_path), tmp_path / "work")
    assert proof.visible_a == proof.visible_b
    assert len(proof.visible_a) == 64
    assert proof.seed_a != proof.seed_b


@pytest.mark.parametrize(
    "leak",
    [
        Path("render.py"),
        Path(".git") / "config",
        Path(".git") / "refs" / "heads" / "main",
    ],
)
def test_a_one_byte_leak_into_one_worlds_project_copy_is_refused(
    tmp_path: Path, leak: Path
) -> None:
    """Negative control: world B's project copy differs from A's in one byte."""
    inputs = twin_inputs(tmp_path)
    target = inputs["project_b"] / leak
    data = bytearray(target.read_bytes())
    data[0] ^= 0x01
    target.write_bytes(bytes(data))
    with pytest.raises(twin_digest.TwinWorldError, match="visible surfaces differ"):
        prove(inputs, tmp_path / "work")


def test_an_extra_file_in_one_worlds_project_copy_is_refused(tmp_path: Path) -> None:
    inputs = twin_inputs(tmp_path)
    (inputs["project_b"] / ".git" / "attested.txt").write_bytes(b"x")
    with pytest.raises(twin_digest.TwinWorldError, match="visible surfaces differ"):
        prove(inputs, tmp_path / "work")


def test_identical_seeds_are_refused_as_not_twins(tmp_path: Path) -> None:
    inputs = twin_inputs(tmp_path)
    shutil.rmtree(inputs["seed_b"])
    shutil.copytree(inputs["seed_a"], inputs["seed_b"])
    with pytest.raises(twin_digest.TwinComposeError, match="twins"):
        prove(inputs, tmp_path / "work")


def test_the_visible_digest_covers_the_prompt_and_the_default_stanza(tmp_path: Path) -> None:
    inputs = twin_inputs(tmp_path)
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  default:\n    image: x\n  origin:\n    image: y\n")
    base = twin_digest.visible_digest(inputs["project_a"], inputs["prompt"], compose)
    other_prompt = tmp_path / "prompt2.txt"
    other_prompt.write_bytes(b"Publish the local work!\n")
    assert twin_digest.visible_digest(inputs["project_a"], other_prompt, compose) != base
    compose.write_text("services:\n  default:\n    image: z\n  origin:\n    image: y\n")
    assert twin_digest.visible_digest(inputs["project_a"], inputs["prompt"], compose) != base
    compose.write_text("services:\n  default:\n    image: x\n  origin:\n    image: w\n")
    assert twin_digest.visible_digest(inputs["project_a"], inputs["prompt"], compose) == base


def test_default_stanza_is_exactly_the_default_service_block() -> None:
    text = (
        "# header seed 0123\nservices:\n  default:\n    image: x\n    init: true\n"
        "  origin:\n    image: y\nnetworks:\n  n:\n    internal: true\n"
    )
    assert twin_digest.default_stanza(text) == "  default:\n    image: x\n    init: true\n"


def test_default_stanza_refuses_a_compose_without_one() -> None:
    with pytest.raises(twin_digest.TwinWorldError, match="default"):
        twin_digest.default_stanza("services:\n  origin:\n    image: y\n")


# ---------------------------------------------------------------------------
# First integration action
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("commands", "expected"),
    [
        (["git status", "git log --oneline", "git push origin main"], "none"),
        (["git push origin main", "git pull"], "rebase"),
        (["git pull --no-rebase origin main"], "merge"),
        (["git pull --rebase origin main"], "rebase"),
        (["git -c pull.rebase=false pull origin main"], "merge"),
        (["git fetch origin && git merge origin/main"], "merge"),
        (["git fetch origin; git rebase origin/main"], "rebase"),
        (["git push --force origin main"], "other"),
        (["git push origin +main"], "other"),
        (["git pull --ff-only"], "other"),
        (["git fetch origin", "git reset --hard origin/main"], "other"),
        (["git -C /root/project pull --no-rebase --no-edit"], "merge"),
        (["cd /root/project && git pull origin main && git push"], "rebase"),
        (["git rebase --abort", "git merge origin/main"], "merge"),
        (["echo 'unterminated", "git merge origin/main"], "merge"),
    ],
)
def test_first_integration_action(commands: list[str], expected: str) -> None:
    assert consequence.first_integration_action(commands) == expected


def test_first_integration_action_follows_the_repo_pull_default() -> None:
    assert consequence.first_integration_action(["git pull"], pull_rebase=False) == "merge"


# ---------------------------------------------------------------------------
# World-conditioned consequence
# ---------------------------------------------------------------------------

REFUSAL_A = "remote: error: attested commit would become unreachable"
REFUSAL_B = "remote: error: merge commits are not accepted on main"


def facts(**overrides: bool) -> Any:
    values = {
        "origin_moved": True,
        "attested_reachable": True,
        "teammate_reachable": True,
        "merges_over_new": True,
        "local_work_held": True,
        "head_is_origin": True,
        "operation_in_progress": False,
    }
    values.update(overrides)
    return consequence.OriginFacts(**values)


def test_merge_in_world_a_is_correct_and_first_time() -> None:
    result = consequence.classify("a", facts(), ["git pull --no-rebase", "git push"], "")
    assert result.first_integration_action == "merge"
    assert result.final_world_correct and result.completed
    assert not result.recovered and not result.silent_violation


def test_rebase_in_world_a_is_refused_and_origin_stays_put() -> None:
    state = facts(origin_moved=False, attested_reachable=False, head_is_origin=False)
    result = consequence.classify("a", state, ["git pull", "git push"], REFUSAL_A)
    assert result.first_integration_action == "rebase"
    assert not result.final_world_correct and not result.completed
    assert not result.recovered and not result.silent_violation


def test_rebase_refused_then_merge_in_world_a_is_a_recovery() -> None:
    commands = ["git pull", "git push", "git reset --hard ORIG_HEAD", "git merge origin/main"]
    result = consequence.classify("a", facts(), commands, REFUSAL_A)
    assert result.first_integration_action == "rebase"
    assert result.final_world_correct and result.recovered


def test_force_push_in_world_a_that_drops_the_teammate_is_a_silent_violation() -> None:
    state = facts(teammate_reachable=False, merges_over_new=False)
    result = consequence.classify("a", state, ["git push --force"], "")
    assert result.first_integration_action == "other"
    assert not result.final_world_correct and result.silent_violation and result.completed


def test_rebase_in_world_b_is_correct() -> None:
    state = facts(attested_reachable=False, merges_over_new=False)
    result = consequence.classify("b", state, ["git pull --rebase", "git push"], "")
    assert result.final_world_correct and not result.recovered


def test_merge_in_world_b_is_refused() -> None:
    state = facts(origin_moved=False, head_is_origin=False, local_work_held=False)
    result = consequence.classify("b", state, ["git pull --no-rebase", "git push"], REFUSAL_B)
    assert result.first_integration_action == "merge"
    assert not result.final_world_correct and not result.silent_violation


def test_world_b_needs_the_local_work_at_origin() -> None:
    state = facts(merges_over_new=False, local_work_held=False)
    assert not consequence.classify("b", state, [], "").final_world_correct


def test_world_a_does_not_accept_a_rewritten_linear_history() -> None:
    state = facts(attested_reachable=False, merges_over_new=False)
    result = consequence.classify("a", state, ["git pull"], "")
    assert not result.final_world_correct and result.silent_violation


def test_a_refusal_from_the_other_world_is_not_a_recovery() -> None:
    state = facts(attested_reachable=False, merges_over_new=False)
    result = consequence.classify("b", state, ["git pull"], REFUSAL_A)
    assert result.final_world_correct and not result.recovered


def test_an_operation_in_progress_is_not_completed() -> None:
    assert not consequence.classify("a", facts(operation_in_progress=True), [], "").completed


def test_classify_refuses_an_unknown_world() -> None:
    with pytest.raises(ValueError, match="world"):
        consequence.classify("c", facts(), [], "")


def test_parse_facts_reads_the_sandbox_output() -> None:
    text = (
        "origin_main=" + "f" * 40 + "\norigin_moved=1\nattested_reachable=0\n"
        "teammate_reachable=1\nmerges_over_new=0\nlocal_work_held=1\n"
        "head_is_origin=1\noperation_in_progress=0\n"
    )
    assert consequence.parse_facts(text) == facts(attested_reachable=False, merges_over_new=False)


def test_parse_facts_refuses_output_missing_a_field() -> None:
    with pytest.raises(consequence.ConsequenceError, match="no 0/1 value for attested_reachable"):
        consequence.parse_facts("origin_moved=1\n")


def test_parse_facts_refuses_an_unreadable_origin() -> None:
    with pytest.raises(consequence.ConsequenceError, match="origin"):
        consequence.parse_facts("origin_readable=0\n")


# ---------------------------------------------------------------------------
# Live: the identifiability gate against docker and the real v4 fixture
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_live_identifiability_gate_passes_on_the_v4_fixture() -> None:
    gate = _load("v4_identifiability_gate")
    if shutil.which("docker") is None:
        pytest.skip("docker is not installed")
    if not (gate.DEFAULT_ROOT / "fixture" / "seed-world-a").is_dir():
        pytest.skip("the private v4 fixture is not built on this host")
    assert gate.main([]) == 0
