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


# Digest-pinned reference: capture() accepts it as-is (content-addressed),
# so no Docker daemon is needed in the dev/CI environment.
PINNED_IMAGE = "aisiuk/inspect-tool-support@sha256:" + "a" * 64


def make_pin(**overrides: object) -> HarnessPin:
    kwargs: dict[str, object] = {
        "agent_version": "2.1.197",
        "model": "openrouter/anthropic/claude-haiku-4.5",
        "sandbox": "docker",
        "cwd": "/root",
        "sandbox_image": PINNED_IMAGE,
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
        pin.model = "other"


# ---------------------------------------------------------------------------
# HarnessPin — sandbox image / env / disallowed_tools (pre-reg pin row)
# ---------------------------------------------------------------------------


def test_capture_accepts_digest_reference_without_docker() -> None:
    # content-addressed reference — no daemon consulted, used verbatim
    assert make_pin().sandbox_image == PINNED_IMAGE


def test_capture_refuses_unresolvable_floating_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    import skill_harness.subject.pin as pin_mod

    def no_daemon(cmd: list[str], *, timeout: int) -> object:
        raise ValueError("docker unavailable while resolving the sandbox image")

    monkeypatch.setattr(pin_mod, "_run_docker", no_daemon)
    with pytest.raises(ValueError, match="docker unavailable"):
        make_pin(sandbox_image="aisiuk/inspect-tool-support")


def test_capture_resolves_floating_tag_via_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    import skill_harness.subject.pin as pin_mod

    def fake_docker(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        assert cmd[:3] == ["docker", "image", "inspect"]
        return subprocess.CompletedProcess(cmd, 0, stdout=PINNED_IMAGE + "\n", stderr="")

    monkeypatch.setattr(pin_mod, "_run_docker", fake_docker)
    pin = make_pin(sandbox_image="aisiuk/inspect-tool-support")
    assert pin.sandbox_image == PINNED_IMAGE


def test_disallowed_tools_sorted_for_canonical_fingerprint() -> None:
    a = make_pin(disallowed_tools=("WebSearch", "Bash"))
    b = make_pin(disallowed_tools=("Bash", "WebSearch"))
    assert a.disallowed_tools == ("Bash", "WebSearch")
    assert a.fingerprint() == b.fingerprint()


def test_env_and_disallowed_tools_discriminate_fingerprints() -> None:
    base = make_pin()
    assert make_pin(env={"FOO": "1"}).fingerprint() != base.fingerprint()
    assert make_pin(disallowed_tools=("Bash",)).fingerprint() != base.fingerprint()
    assert make_pin(sandbox_image=PINNED_IMAGE.replace("a" * 64, "b" * 64)).fingerprint() != (
        base.fingerprint()
    )


# ---------------------------------------------------------------------------
# Pinned compose generation (pure — no extra required)
# ---------------------------------------------------------------------------


def test_write_pinned_compose_injects_digest_and_mirrors_generic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from skill_harness.subject.inspect_adapter import write_pinned_compose

    path = write_pinned_compose(make_pin(), compose_dir=tmp_path)
    content = path.read_text(encoding="utf-8")
    assert f'image: "{PINNED_IMAGE}"' in content
    # mirror inspect_ai's generic compose knobs exactly
    for line in ('command: "tail -f /dev/null"', "init: true", "network_mode: none"):
        assert line in content
    # content-hashed name → rewrites are idempotent
    assert path == write_pinned_compose(make_pin(), compose_dir=tmp_path)


def test_write_pinned_compose_refuses_unpinned_or_nondocker(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from skill_harness.subject.inspect_adapter import write_pinned_compose

    with pytest.raises(ValueError, match="only 'docker'"):
        write_pinned_compose(make_pin(sandbox="local"), compose_dir=tmp_path)
    unpinned = HarnessPin(
        inspect_ai_version="x",
        inspect_swe_version="x",
        agent_version="2.1.197",
        model="m",
        sandbox="docker",
        sandbox_image="aisiuk/inspect-tool-support",  # floating tag
        cwd="/root",
    )
    with pytest.raises(ValueError, match="not digest-pinned"):
        write_pinned_compose(unpinned, compose_dir=tmp_path)


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


# ---------------------------------------------------------------------------
# files_as_data_uris (pure stdlib — the sandbox-files delivery guard)
# ---------------------------------------------------------------------------


def test_files_as_data_uris_round_trips_contents() -> None:
    import base64

    from skill_harness.subject.inspect_adapter import files_as_data_uris

    files = {"/root/repo/a.py": "print('hi')\n", "/root/repo/pkg/__init__.py": ""}
    encoded = files_as_data_uris(files)

    assert set(encoded) == set(files)
    for dest, uri in encoded.items():
        prefix = "data:text/plain;base64,"
        assert uri.startswith(prefix)
        assert base64.b64decode(uri[len(prefix) :]).decode("utf-8") == files[dest]


def test_files_as_data_uris_empty_string_never_resolves_as_a_path() -> None:
    # Regression: Inspect resolves Sample.files values against the local
    # filesystem first; a raw "" names the cwd and pulls the entire working
    # directory into the sandbox. The encoded form must not be a valid path.
    from pathlib import Path

    from skill_harness.subject.inspect_adapter import files_as_data_uris

    encoded = files_as_data_uris({"/root/repo/pkg/__init__.py": ""})
    (uri,) = encoded.values()
    assert uri == "data:text/plain;base64,"
    assert not Path(uri).exists()
