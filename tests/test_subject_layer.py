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


def test_write_pinned_compose_default_dir_is_private_per_call() -> None:
    """S3: with compose_dir omitted, each call gets its OWN private, unpredictable
    directory (tempfile.mkdtemp) rather than a shared-namespace filename inside
    tempfile.gettempdir() — nothing for a co-tenant to pre-plant a symlink into.

    This intentionally changes the DEFAULT path's idempotency (two no-compose_dir
    calls for the same pin now land in different directories); build_paired_tasks
    and this test suite's other write_pinned_compose tests all pass an explicit
    compose_dir, which keeps the tested idempotent-same-path contract for callers
    who supply their own directory.
    """
    import shutil
    import tempfile
    from pathlib import Path

    from skill_harness.subject.inspect_adapter import write_pinned_compose

    pin = make_pin()
    path1 = write_pinned_compose(pin)
    path2 = write_pinned_compose(pin)
    try:
        assert path1.parent != path2.parent, "each default call must get a private directory"
        assert path1.parent != Path(tempfile.gettempdir())
        assert path1.read_text(encoding="utf-8") == path2.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(path1.parent, ignore_errors=True)
        shutil.rmtree(path2.parent, ignore_errors=True)


def test_write_pinned_compose_default_dir_registered_for_cleanup() -> None:
    """F-6 (S55 hostile review): the default (no compose_dir) path creates a
    private mkdtemp directory per call and, pre-fix, nothing ever removed it --
    every eval() run leaked one directory (the sibling test above works around
    this today with its own manual `shutil.rmtree` in `finally`). The fix
    registers auto-created dirs for atexit cleanup; this test invokes the
    cleanup callback directly rather than waiting on real interpreter exit.
    """
    import shutil

    from skill_harness.subject import inspect_adapter
    from skill_harness.subject.inspect_adapter import write_pinned_compose

    pin = make_pin()
    path = write_pinned_compose(pin)
    try:
        assert path.parent in inspect_adapter._auto_created_compose_dirs, (
            "F-6: the auto-created compose dir must be registered for cleanup"
        )
        assert path.exists()
        inspect_adapter._cleanup_auto_created_compose_dirs()
        assert not path.parent.exists(), "F-6: cleanup must actually remove the directory"
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


def test_write_pinned_compose_explicit_compose_dir_not_tracked(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """F-6 regression guard: a caller-supplied compose_dir is caller-owned --
    the cleanup registry must never track (and therefore never later delete)
    a directory the caller passed in explicitly.
    """
    from skill_harness.subject import inspect_adapter
    from skill_harness.subject.inspect_adapter import write_pinned_compose

    pin = make_pin()
    write_pinned_compose(pin, compose_dir=tmp_path)
    assert tmp_path not in inspect_adapter._auto_created_compose_dirs, (
        "F-6: caller-supplied compose_dir must not be tracked for auto-cleanup"
    )


def test_write_pinned_compose_refuses_existing_symlink(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S3: refuses to write through a pre-existing symlink at the target path
    rather than following it (write_text() would otherwise overwrite whatever
    the symlink points at). Simulated via monkeypatch rather than a real
    os.symlink() call — symlink creation needs elevated privilege on Windows
    CI runners, but the guard's is_symlink() check behaves identically either
    way."""
    from pathlib import Path

    from skill_harness.subject.inspect_adapter import write_pinned_compose

    pin = make_pin()  # built BEFORE patching — capture() itself reads files via Path
    monkeypatch.setattr(Path, "is_symlink", lambda self: True)
    with pytest.raises(RuntimeError, match="symlink"):
        write_pinned_compose(pin, compose_dir=tmp_path)


def test_write_pinned_compose_refuses_content_mismatch_after_write(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S3: if the file on disk doesn't match what was just written when read
    back, refuse rather than return a path whose content may belong to a
    racing writer. Simulated by forcing read_text() to return different bytes
    than write_text() just wrote (stands in for a same-UID writer racing this
    call between the write and the read-back)."""
    from pathlib import Path

    from skill_harness.subject.inspect_adapter import write_pinned_compose

    pin = make_pin()  # built BEFORE patching — capture() itself reads files via Path
    monkeypatch.setattr(Path, "read_text", lambda self, encoding=None: "tampered content")
    with pytest.raises(RuntimeError, match="mismatch"):
        write_pinned_compose(pin, compose_dir=tmp_path)


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
# C6 — oracle_target validation + infra-failure/wrong-answer split
#
# Regression coverage for a hostile-review finding: ``oracle_target``
# defaulting to "" made the ``file_contains`` substring check vacuously true
# (any existing file passes), and a bare ``except Exception`` around
# ``sandbox().read_file`` mapped ANY sandbox/infra failure (docker hiccup,
# timeout, OOM) to an admissible ``Score(INCORRECT)`` — an apparatus outage
# recorded as evidence the skill under test failed. The validation check is
# pure Python and runs before the lazy ``inspect_ai`` import, so it is
# testable regardless of whether the optional extra is installed. The
# scorer-body checks need the real ``inspect_ai`` scorer/sandbox types.
# ---------------------------------------------------------------------------


def test_build_paired_tasks_refuses_empty_oracle_target_for_file_contains(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from skill_harness.subject.inspect_adapter import build_paired_tasks

    skill = tmp_path / "some-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: some-skill\ndescription: a test skill\n---\nbody\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="oracle_target"):
        build_paired_tasks(
            skill_dir=skill,
            prompt="do a thing",
            oracle="file_contains",
            oracle_arg="out.txt",
            # oracle_target omitted — must not default to a vacuous check
            pin=make_pin(),
        )


def test_build_paired_tasks_refuses_nul_byte_in_oracle_arg(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """S6 defense-in-depth: oracle_arg reaches a shell string / f-string
    sandbox path with no escaping (see the TRUST BOUNDARY docstring note on
    build_paired_tasks). A NUL byte is never valid in either, so rejecting it
    costs nothing for legitimate operator-authored oracle_arg values."""
    from skill_harness.subject.inspect_adapter import build_paired_tasks

    skill = tmp_path / "some-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: some-skill\ndescription: a test skill\n---\nbody\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="NUL byte"):
        build_paired_tasks(
            skill_dir=skill,
            prompt="do a thing",
            oracle="command_succeeds",
            oracle_arg="pytest -q\x00; rm -rf /",
            pin=make_pin(),
        )


def test_build_paired_tasks_refuses_nul_byte_in_oracle_target(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from skill_harness.subject.inspect_adapter import build_paired_tasks

    skill = tmp_path / "some-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: some-skill\ndescription: a test skill\n---\nbody\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="NUL byte"):
        build_paired_tasks(
            skill_dir=skill,
            prompt="do a thing",
            oracle="file_contains",
            oracle_arg="out.txt",
            oracle_target="expected\x00value",
            pin=make_pin(),
        )


def test_build_paired_tasks_allows_empty_oracle_target_for_command_succeeds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # command_succeeds never reads oracle_target in the scorer (only exit
    # code matters) — the validation must be scoped to file_contains, not
    # a blanket "oracle_target always required".
    from skill_harness.subject.inspect_adapter import build_paired_tasks

    skill = tmp_path / "some-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: some-skill\ndescription: a test skill\n---\nbody\n", encoding="utf-8"
    )
    tasks = build_paired_tasks(
        skill_dir=skill,
        prompt="do a thing",
        oracle="command_succeeds",
        oracle_arg="pytest -q",
        pin=make_pin(),
    )
    assert set(tasks) == {"full", "null"}


@pytest.mark.skipif(not INSPECT_INSTALLED, reason="requires the optional inspect extra")
def test_file_contains_scorer_missing_file_scores_incorrect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A genuinely missing file is a wrong answer, not an apparatus fault —
    # this must keep scoring INCORRECT (not crash, not go admissible-void).
    import asyncio

    import inspect_ai.util as inspect_util
    from inspect_ai.scorer import INCORRECT

    from skill_harness.subject.inspect_adapter import _build_scorer

    class MissingFileSandbox:
        async def read_file(self, path: str) -> str:
            raise FileNotFoundError(f"no such file: {path}")

    monkeypatch.setattr(inspect_util, "sandbox", lambda: MissingFileSandbox())

    score_fn = _build_scorer("file_contains", "out.txt", "ok", "/root")
    result = asyncio.run(score_fn(None, None))  # type: ignore[arg-type]
    assert result.value == INCORRECT


@pytest.mark.skipif(not INSPECT_INSTALLED, reason="requires the optional inspect extra")
def test_file_contains_scorer_propagates_infra_failure_instead_of_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # RED regression for the C6 finding: an infra/apparatus failure (docker
    # stall, timeout, OOM) reading the sandbox file must propagate as an
    # exception — never be converted into an admissible Score in either
    # direction. Inspect's own eval() harness then marks the run as errored,
    # which the ingest write path (write_paired_evidence) already refuses
    # to admit (EvalLogNotSuccessError) rather than silently scoring it.
    import asyncio

    import inspect_ai.util as inspect_util

    from skill_harness.subject.inspect_adapter import _build_scorer

    class FlakySandbox:
        async def read_file(self, path: str) -> str:
            raise TimeoutError("docker daemon unresponsive")

    monkeypatch.setattr(inspect_util, "sandbox", lambda: FlakySandbox())

    score_fn = _build_scorer("file_contains", "out.txt", "ok", "/root")
    with pytest.raises(TimeoutError, match="docker daemon unresponsive"):
        asyncio.run(score_fn(None, None))  # type: ignore[arg-type]


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


def test_files_as_data_uris_round_trips_binary_contents() -> None:
    # Binary fixtures (e.g. OOXML zip archives) must survive delivery
    # byte-for-byte; UTF-8 text encoding would corrupt them.
    import base64

    from skill_harness.subject.inspect_adapter import files_as_data_uris

    payload = bytes(range(256)) + b"PK\x03\x04"
    encoded = files_as_data_uris({"/root/fixture.docx": payload})
    (uri,) = encoded.values()
    prefix = "data:application/octet-stream;base64,"
    assert uri.startswith(prefix)
    assert base64.b64decode(uri[len(prefix) :]) == payload


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
