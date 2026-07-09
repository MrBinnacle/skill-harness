"""Tests for the v0.2 subject layer (HarnessPin + inspect adapter surface).

The [inspect] extra is NOT installed in the default dev/CI environment, so
these tests cover exactly what must hold without it: pin semantics, the typed
not-installed error, and input validation. The full agentic path is verified
behaviorally in an inspect-equipped venv (see v0.2-preregistration.md).
"""

from __future__ import annotations

from importlib.util import find_spec

import pytest
from pydantic import ValidationError

from skill_harness.subject.pin import HarnessPin

INSPECT_INSTALLED = find_spec("inspect_ai") is not None


def make_pin(**overrides: str) -> HarnessPin:
    kwargs: dict[str, str] = {
        "agent_version": "2.1.197",
        "model": "openrouter/anthropic/claude-haiku-4.5",
        "sandbox": "docker",
        "cwd": "/root",
    }
    kwargs.update(overrides)
    return HarnessPin.capture(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# HarnessPin
# ---------------------------------------------------------------------------


def test_capture_refuses_auto_agent_version() -> None:
    with pytest.raises(ValueError, match="auto"):
        make_pin(agent_version="auto")


def test_capture_reads_live_environment_not_hand_typed_values() -> None:
    pin = make_pin()
    # dev env does not have the extra installed; the pin must SAY so rather
    # than omit the field or invent a version.
    expected = "NOT-INSTALLED" if not INSPECT_INSTALLED else pin.inspect_ai_version
    assert pin.inspect_ai_version == expected
    assert pin.inspect_ai_version != ""


def test_fingerprint_is_stable_and_discriminates() -> None:
    a, b = make_pin(), make_pin()
    assert a.fingerprint() == b.fingerprint()
    assert make_pin(cwd="/work").fingerprint() != a.fingerprint()


def test_pin_is_frozen() -> None:
    pin = make_pin()
    with pytest.raises(ValidationError):
        pin.model = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Adapter surface without the optional extra
# ---------------------------------------------------------------------------


@pytest.mark.skipif(INSPECT_INSTALLED, reason="extra installed; error path unreachable")
def test_build_paired_tasks_raises_typed_error_without_extra(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from skill_harness.subject.inspect_adapter import (
        SubjectLayerNotInstalledError,
        build_paired_tasks,
    )

    skill = tmp_path / "some-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: some-skill\n---\nbody\n", encoding="utf-8")
    with pytest.raises(SubjectLayerNotInstalledError, match=r"skill-harness\[inspect\]"):
        build_paired_tasks(
            skill_dir=skill,
            prompt="do a thing",
            oracle="file_contains",
            oracle_arg="out.txt",
            oracle_target="ok",
            pin=make_pin(),
        )
