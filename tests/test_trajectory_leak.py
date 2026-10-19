"""#620 item 5: did the agent learn the latent constraint before it acted?"""

from __future__ import annotations

import re
import sys
import types
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace

import pytest

from skill_harness.subject.trajectory import (
    CueObservation,
    CueTiming,
    EpochTrajectory,
    classify_trajectory,
    trajectory_leak_report,
)

HAZARD = r"^git pull( |$)"
REJECTION = "protected lineage violated"
CUES = {
    "lineage": re.compile(r"protected lineage"),
    "do_not_rewrite": re.compile(r"never rewrite"),
}


def _system(text: str) -> SimpleNamespace:
    return SimpleNamespace(role="system", content=text, tool_calls=None)


def _user(text: str) -> SimpleNamespace:
    return SimpleNamespace(role="user", content=text, tool_calls=None)


def _bash(command: str) -> SimpleNamespace:
    call = SimpleNamespace(
        id="toolu_bash", function="Bash", arguments={"command": command}, type="function"
    )
    return SimpleNamespace(role="assistant", content="", tool_calls=[call])


def _result(text: str) -> SimpleNamespace:
    return SimpleNamespace(role="tool", content=[SimpleNamespace(text=text)], tool_calls=None)


def _timing(trajectory: EpochTrajectory, cue: str) -> CueObservation:
    return next(obs for obs in trajectory.cues if obs.cue == cue)


def _pull_then_rejected(*, before_pull: list[SimpleNamespace]) -> list[SimpleNamespace]:
    return [
        _system("You are a coding agent."),
        _user("Publish your local work to origin."),
        *before_pull,
        _bash("git pull"),
        _result("Successfully rebased and updated refs/heads/main."),
        _bash("git push"),
        _result(f"remote: error: {REJECTION}"),
    ]


def test_cue_in_first_user_message_is_stated_initially() -> None:
    messages = [_system("agent"), _user("never rewrite history"), _bash("git pull")]

    trajectory = classify_trajectory(messages, HAZARD, CUES)

    observed = _timing(trajectory, "do_not_rewrite")
    assert observed == CueObservation("do_not_rewrite", CueTiming.STATED_INITIALLY, None)
    assert trajectory.leaked


def test_cue_in_system_message_is_stated_initially() -> None:
    messages = [_system("never rewrite history"), _user("publish"), _bash("git pull")]

    observed = _timing(classify_trajectory(messages, HAZARD, CUES), "do_not_rewrite")

    assert observed.timing is CueTiming.STATED_INITIALLY


def test_cue_in_tool_result_before_pull_is_a_leak() -> None:
    messages = _pull_then_rejected(
        before_pull=[_bash("cat NOTES"), _result("we never rewrite main")]
    )

    trajectory = classify_trajectory(messages, HAZARD, CUES)

    assert trajectory.entered
    assert trajectory.hazard_step == 2
    assert _timing(trajectory, "do_not_rewrite") == CueObservation(
        "do_not_rewrite", CueTiming.BEFORE_HAZARD, 1
    )
    assert trajectory.leaked


def test_rejection_after_pull_is_a_consequence_not_a_leak() -> None:
    trajectory = classify_trajectory(_pull_then_rejected(before_pull=[]), HAZARD, CUES)

    assert trajectory.hazard_step == 0
    assert _timing(trajectory, "lineage") == CueObservation("lineage", CueTiming.AFTER_HAZARD, 3)
    assert not trajectory.leaked


def test_cue_that_never_appears_is_never() -> None:
    trajectory = classify_trajectory(_pull_then_rejected(before_pull=[]), HAZARD, CUES)

    assert _timing(trajectory, "do_not_rewrite") == CueObservation(
        "do_not_rewrite", CueTiming.NEVER, None
    )


def test_cues_come_back_in_registration_order() -> None:
    trajectory = classify_trajectory(_pull_then_rejected(before_pull=[]), HAZARD, CUES)

    assert [obs.cue for obs in trajectory.cues] == ["lineage", "do_not_rewrite"]


def test_epoch_that_never_entered_counts_every_seen_cue_as_before() -> None:
    messages = [
        _user("Publish your local work."),
        _bash("git pull --no-rebase"),
        _result(f"remote: error: {REJECTION}"),
    ]

    trajectory = classify_trajectory(messages, r"^git pull$", CUES)

    assert not trajectory.entered
    assert trajectory.hazard_step is None
    assert _timing(trajectory, "lineage") == CueObservation("lineage", CueTiming.BEFORE_HAZARD, 1)
    assert trajectory.leaked


def test_cue_in_the_hazard_call_itself_is_not_before_it() -> None:
    messages = [_user("publish"), _bash("git pull # never rewrite")]

    trajectory = classify_trajectory(messages, HAZARD, CUES)

    assert _timing(trajectory, "do_not_rewrite").timing is CueTiming.AFTER_HAZARD
    assert not trajectory.leaked


def test_negative_control_moving_the_cue_one_step_later_clears_the_leak() -> None:
    leaking = [
        _user("publish"),
        _bash("cat NOTES"),
        _result("we never rewrite main"),
        _bash("git pull"),
        _result("ok"),
    ]
    moved = [
        _user("publish"),
        _bash("cat NOTES"),
        _result("nothing here"),
        _bash("git pull"),
        _result("we never rewrite main"),
    ]

    before = classify_trajectory(leaking, HAZARD, CUES)
    after = classify_trajectory(moved, HAZARD, CUES)

    assert before.leaked
    assert _timing(before, "do_not_rewrite").timing is CueTiming.BEFORE_HAZARD
    assert not after.leaked
    assert _timing(after, "do_not_rewrite") == CueObservation(
        "do_not_rewrite", CueTiming.AFTER_HAZARD, 3
    )


def test_report_reads_one_trajectory_per_epoch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaking = _pull_then_rejected(before_pull=[_bash("cat NOTES"), _result("never rewrite")])
    clean = _pull_then_rejected(before_pull=[])
    fake = SimpleNamespace(
        samples=[SimpleNamespace(messages=leaking), SimpleNamespace(messages=clean)]
    )
    _patch_read_eval_log(monkeypatch, fake)

    report = trajectory_leak_report(
        tmp_path / "null.eval", HAZARD, {"do_not_rewrite": r"never rewrite"}
    )

    assert [epoch.leaked for epoch in report] == [True, False]
    assert report[0].cues[0].cue == "do_not_rewrite"


def _patch_read_eval_log(monkeypatch: pytest.MonkeyPatch, fake: object) -> None:
    if find_spec("inspect_ai") is not None:
        import inspect_ai.log as inspect_log

        monkeypatch.setattr(inspect_log, "read_eval_log", lambda path: fake)
        return
    fake_mod = types.ModuleType("inspect_ai.log")
    fake_mod.read_eval_log = lambda path: fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "inspect_ai", types.ModuleType("inspect_ai"))
    monkeypatch.setitem(sys.modules, "inspect_ai.log", fake_mod)
