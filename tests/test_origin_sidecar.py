"""Tests for the #620 origin sidecar: a git origin the agent cannot see.

Everything except the one ``live`` test is pure stdlib and runs without
Docker or the optional inspect extra.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import uuid
from collections.abc import Iterator
from importlib.util import find_spec
from pathlib import Path

import pytest

from skill_harness.subject import (
    OriginSidecar,
    SeedTwinProof,
    TwinComposeError,
    prove_seed_only_twins,
)
from skill_harness.subject.origin_sidecar import write_origin_compose
from skill_harness.subject.pin import HarnessPin

INSPECT_INSTALLED = find_spec("inspect_ai") is not None
PINNED_IMAGE = "aisiuk/inspect-tool-support@sha256:" + "a" * 64
LIVE_IMAGE = (
    "aisiuk/inspect-tool-support@sha256:"
    "fb045da8203aea656785c758f7147b003cfe21f213e9048a38be0a33242a5b3d"
)
HOOK = (
    "#!/bin/sh\n"
    "while read old new ref; do\n"
    '  [ "$ref" = refs/heads/main ] || continue\n'
    "  for sha in $(cat /srv/protected.txt); do\n"
    '    if ! git merge-base --is-ancestor "$sha" "$new" 2>/dev/null; then\n'
    '      echo "error: protected lineage violated" >&2; exit 1\n'
    "    fi\n"
    "  done\n"
    "done\n"
)


def make_pin(image: str = PINNED_IMAGE, **overrides: object) -> HarnessPin:
    kwargs: dict[str, object] = {
        "agent_version": "2.1.197",
        "model": "openrouter/anthropic/claude-haiku-4.5",
        "sandbox": "docker",
        "cwd": "/root",
        "sandbox_image": image,
    }
    kwargs.update(overrides)
    return HarnessPin.capture(**kwargs)  # type: ignore[arg-type]


def make_seed(root: Path, *, hook: bool) -> Path:
    """A minimal seed: a fake bare-repo directory, an optional hook, a SHA list."""
    (root / "origin.git" / "hooks").mkdir(parents=True)
    (root / "origin.git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    (root / "protected.txt").write_bytes(b"0" * 40 + b"\n")
    if hook:
        (root / "origin.git" / "hooks" / "pre-receive").write_bytes(HOOK.encode())
    return root


def expected_compose_text(digest12: str) -> str:
    return (
        "# skill-harness pinned compose (generated from the harness pin)\n"
        "# Mirrors inspect_ai's auto-compose; image is digest-pinned for admissibility.\n"
        f"# origin sidecar: seed digest {digest12}\n"
        "services:\n"
        "  default:\n"
        f'    image: "{PINNED_IMAGE}"\n'
        '    command: "tail -f /dev/null"\n'
        "    init: true\n"
        "    networks: [skill-harness-origin]\n"
        "    depends_on: [origin]\n"
        "    stop_grace_period: 1s\n"
        "  origin:\n"
        f'    image: "{PINNED_IMAGE}"\n'
        '    command: ["sh", "-c", "cp -a /seed/. /srv/ && chmod -R +x /srv/*.git/hooks'
        " 2>/dev/null; exec git daemon --reuseaddr --export-all --enable=receive-pack"
        ' --base-path=/srv /srv"]\n'
        "    init: true\n"
        f'    volumes: ["./origin-seed-{digest12}:/seed:ro"]\n'
        "    networks: [skill-harness-origin]\n"
        "    stop_grace_period: 1s\n"
        "networks:\n"
        "  skill-harness-origin:\n"
        "    internal: true\n"
    )


# ---------------------------------------------------------------------------
# OriginSidecar.from_seed
# ---------------------------------------------------------------------------


def test_from_seed_digest_is_stable_across_calls_and_copies(tmp_path: Path) -> None:
    seed = make_seed(tmp_path / "a", hook=True)
    twin = shutil.copytree(seed, tmp_path / "b")
    assert OriginSidecar.from_seed(seed).digest == OriginSidecar.from_seed(seed).digest
    assert OriginSidecar.from_seed(seed).digest == OriginSidecar.from_seed(twin).digest
    assert len(OriginSidecar.from_seed(seed).digest) == 64


def test_from_seed_digest_changes_when_one_byte_changes(tmp_path: Path) -> None:
    seed = make_seed(tmp_path / "s", hook=True)
    before = OriginSidecar.from_seed(seed).digest
    head = seed / "origin.git" / "HEAD"
    head.write_bytes(head.read_bytes().replace(b"main", b"mair"))
    assert OriginSidecar.from_seed(seed).digest != before


def test_from_seed_digest_changes_when_a_file_is_added(tmp_path: Path) -> None:
    on = OriginSidecar.from_seed(make_seed(tmp_path / "on", hook=True))
    off = OriginSidecar.from_seed(make_seed(tmp_path / "off", hook=False))
    assert on.digest != off.digest


def test_from_seed_digest_ignores_mode_bits(tmp_path: Path) -> None:
    seed = make_seed(tmp_path / "s", hook=True)
    before = OriginSidecar.from_seed(seed).digest
    target = seed / "protected.txt"
    os.chmod(target, stat.S_IREAD)
    try:
        assert OriginSidecar.from_seed(seed).digest == before
    finally:
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)


def test_from_seed_refuses_a_seed_with_no_bare_repo(tmp_path: Path) -> None:
    seed = tmp_path / "s"
    seed.mkdir()
    (seed / "protected.txt").write_bytes(b"x\n")
    with pytest.raises(ValueError, match=r"\.git"):
        OriginSidecar.from_seed(seed)


def test_from_seed_refuses_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a directory"):
        OriginSidecar.from_seed(tmp_path / "nope")


# ---------------------------------------------------------------------------
# write_origin_compose
# ---------------------------------------------------------------------------


def test_write_origin_compose_renders_the_two_service_text(tmp_path: Path) -> None:
    origin = OriginSidecar.from_seed(make_seed(tmp_path / "seed", hook=True))
    path = write_origin_compose(make_pin(), origin, compose_dir=tmp_path / "out")
    text = path.read_text(encoding="utf-8")
    assert text == expected_compose_text(origin.digest[:12])
    assert path.name.startswith("skill-harness-compose-") and path.suffix == ".yaml"
    assert "network_mode" not in text


def test_write_origin_compose_copies_the_seed_beside_the_compose(tmp_path: Path) -> None:
    seed = make_seed(tmp_path / "seed", hook=True)
    origin = OriginSidecar.from_seed(seed)
    path = write_origin_compose(make_pin(), origin, compose_dir=tmp_path / "out")
    copy = path.parent / f"origin-seed-{origin.digest[:12]}"
    assert (copy / "origin.git" / "hooks" / "pre-receive").read_bytes() == HOOK.encode()
    assert OriginSidecar.from_seed(copy).digest == origin.digest


def test_write_origin_compose_is_idempotent_for_one_compose_dir(tmp_path: Path) -> None:
    origin = OriginSidecar.from_seed(make_seed(tmp_path / "seed", hook=True))
    first = write_origin_compose(make_pin(), origin, compose_dir=tmp_path / "out")
    assert write_origin_compose(make_pin(), origin, compose_dir=tmp_path / "out") == first


def test_write_origin_compose_refuses_a_symlink_at_the_compose_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = OriginSidecar.from_seed(make_seed(tmp_path / "seed", hook=True))
    pin = make_pin()
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda self: self.suffix == ".yaml" or real_is_symlink(self)
    )
    with pytest.raises(RuntimeError, match="symlink"):
        write_origin_compose(pin, origin, compose_dir=tmp_path / "out")


def test_write_origin_compose_refuses_a_symlink_at_the_seed_copy_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulated like the compose-path test: creating a real symlink needs
    elevated privilege on Windows. Only the copy target reports as a link."""
    origin = OriginSidecar.from_seed(make_seed(tmp_path / "seed", hook=True))
    pin = make_pin()
    target = tmp_path / "out" / f"origin-seed-{origin.digest[:12]}"
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == target or real_is_symlink(self))
    with pytest.raises(RuntimeError, match="refusing to copy origin seed"):
        write_origin_compose(pin, origin, compose_dir=tmp_path / "out")
    assert not target.exists()


def test_write_origin_compose_refuses_non_docker_or_undigested_pin(tmp_path: Path) -> None:
    origin = OriginSidecar.from_seed(make_seed(tmp_path / "seed", hook=True))
    with pytest.raises(ValueError, match="docker"):
        write_origin_compose(make_pin(sandbox="local"), origin, compose_dir=tmp_path)
    undigested = make_pin().model_copy(update={"sandbox_image": "aisiuk/inspect-tool-support"})
    with pytest.raises(ValueError, match="digest"):
        write_origin_compose(undigested, origin, compose_dir=tmp_path)


def test_write_origin_compose_refuses_a_seed_edited_after_from_seed(tmp_path: Path) -> None:
    """Negative control: the digest names the seed that was read, so a seed that
    changed before the write must not ship under the old digest."""
    seed = make_seed(tmp_path / "seed", hook=True)
    origin = OriginSidecar.from_seed(seed)
    (seed / "protected.txt").write_bytes(b"1" * 40 + b"\n")
    with pytest.raises(RuntimeError, match="digest"):
        write_origin_compose(make_pin(), origin, compose_dir=tmp_path / "out")


# ---------------------------------------------------------------------------
# prove_seed_only_twins
# ---------------------------------------------------------------------------


def _twin_paths(tmp_path: Path) -> tuple[Path, OriginSidecar, Path, OriginSidecar]:
    off = OriginSidecar.from_seed(make_seed(tmp_path / "seed-off", hook=False))
    on = OriginSidecar.from_seed(make_seed(tmp_path / "seed-on", hook=True))
    path_off = write_origin_compose(make_pin(), off, compose_dir=tmp_path / "compose-off")
    path_on = write_origin_compose(make_pin(), on, compose_dir=tmp_path / "compose-on")
    return path_off, off, path_on, on


def test_prove_seed_only_twins_passes_for_hook_on_and_hook_off(tmp_path: Path) -> None:
    path_off, off, path_on, on = _twin_paths(tmp_path)
    proof = prove_seed_only_twins(path_off, off, path_on, on)
    assert isinstance(proof, SeedTwinProof)
    assert (proof.digest_a, proof.digest_b) == (off.digest, on.digest)
    assert len(proof.masked_sha256) == 64


def test_prove_seed_only_twins_raises_on_a_one_character_difference(tmp_path: Path) -> None:
    path_off, off, path_on, on = _twin_paths(tmp_path)
    text = path_on.read_text(encoding="utf-8")
    path_on.write_text(text.replace("stop_grace_period: 1s", "stop_grace_period: 2s", 1))
    with pytest.raises(TwinComposeError, match="differ"):
        prove_seed_only_twins(path_off, off, path_on, on)


def test_prove_seed_only_twins_raises_for_equal_digests(tmp_path: Path) -> None:
    path_off, off, _, _ = _twin_paths(tmp_path)
    with pytest.raises(TwinComposeError, match="twins"):
        prove_seed_only_twins(path_off, off, path_off, off)


def test_prove_seed_only_twins_raises_when_a_compose_omits_its_digest(tmp_path: Path) -> None:
    path_off, off, path_on, on = _twin_paths(tmp_path)
    path_on.write_text(path_off.read_text(encoding="utf-8"))
    with pytest.raises(TwinComposeError, match="does not name"):
        prove_seed_only_twins(path_off, off, path_on, on)


# ---------------------------------------------------------------------------
# build_paired_tasks(origin=...)
# ---------------------------------------------------------------------------


def _skill(tmp_path: Path) -> Path:
    skill = tmp_path / "some-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: some-skill\ndescription: a test skill\n---\nbody\n", encoding="utf-8"
    )
    return skill


@pytest.mark.skipif(not INSPECT_INSTALLED, reason="requires the optional inspect extra")
def test_build_paired_tasks_without_origin_keeps_the_pinned_compose(tmp_path: Path) -> None:
    from skill_harness.subject import build_paired_tasks
    from skill_harness.subject.inspect_adapter import write_pinned_compose

    (tmp_path / "c").mkdir()
    tasks = build_paired_tasks(
        skill_dir=_skill(tmp_path),
        prompt="p",
        oracle="command_succeeds",
        oracle_arg="true",
        pin=make_pin(),
        compose_dir=tmp_path / "c",
    )
    expected = str(write_pinned_compose(make_pin(), tmp_path / "c"))
    for task in tasks.values():
        assert task.sandbox is not None and task.sandbox.config == expected


@pytest.mark.skipif(not INSPECT_INSTALLED, reason="requires the optional inspect extra")
def test_build_paired_tasks_with_origin_points_both_arms_at_one_sidecar(tmp_path: Path) -> None:
    from skill_harness.subject import build_paired_tasks

    origin = OriginSidecar.from_seed(make_seed(tmp_path / "seed", hook=True))
    tasks = build_paired_tasks(
        skill_dir=_skill(tmp_path),
        prompt="p",
        oracle="command_succeeds",
        oracle_arg="true",
        pin=make_pin(),
        compose_dir=tmp_path / "c",
        origin=origin,
    )
    expected = str(write_origin_compose(make_pin(), origin, compose_dir=tmp_path / "c"))
    configs = {t.sandbox.config for t in tasks.values() if t.sandbox is not None}
    assert configs == {expected}


# ---------------------------------------------------------------------------
# Live: the hook refuses from a container the agent cannot read
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(work: Path, name: str) -> str:
    (work / name).write_bytes(name.encode() + b"\n")
    _git(work, "add", name)
    _git(work, "commit", "-q", "-m", name)
    return _git(work, "rev-parse", "HEAD")


def _build_live_fixture(root: Path) -> tuple[Path, Path]:
    """Origin holds base->teammate; the agent's project holds base->local.

    Both teammate and local are protected, so a rebase (drops local) and a
    force push (drops teammate) violate lineage and only a merge keeps both."""
    work = root / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    base = _commit(work, "base")
    teammate = _commit(work, "teammate")
    seed = root / "seed"
    seed.mkdir()
    _git(root, "clone", "-q", "--bare", str(work), str(seed / "origin.git"))
    _git(work, "reset", "-q", "--hard", base)
    local = _commit(work, "local")
    _git(work, "remote", "add", "origin", "git://origin/origin.git")
    _git(work, "update-ref", "refs/remotes/origin/main", base)
    _git(work, "tag", "agent-start", local)
    hook = seed / "origin.git" / "hooks" / "pre-receive"
    hook.write_bytes(HOOK.encode())
    (seed / "protected.txt").write_bytes(f"{teammate}\n{local}\n".encode())
    return seed, work


class _Compose:
    def __init__(self, path: Path) -> None:
        self.base = ["docker", "compose", "-p", f"sh620-{uuid.uuid4().hex[:8]}", "-f", str(path)]

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*self.base, *args], capture_output=True, text=True, check=check, timeout=300
        )

    def sh(self, script: str, service: str = "default") -> subprocess.CompletedProcess[str]:
        return self.run("exec", "-T", service, "sh", "-c", script, check=False)


@pytest.fixture
def live_stack(tmp_path: Path) -> Iterator[_Compose]:
    if shutil.which("docker") is None:
        pytest.skip("docker is not installed")
    seed, work = _build_live_fixture(tmp_path)
    origin = OriginSidecar.from_seed(seed)
    path = write_origin_compose(make_pin(LIVE_IMAGE), origin, compose_dir=tmp_path / "compose")
    stack = _Compose(path)
    stack.run("up", "-d", "--wait")
    try:
        stack.run("cp", str(work), "default:/root/project")
        setup = stack.sh(
            "git config --global --add safe.directory '*' && "
            "git config --global user.email a@example.invalid && "
            "git config --global user.name agent && "
            "for i in $(seq 1 30); do git ls-remote git://origin/origin.git >/dev/null "
            "2>&1 && exit 0; sleep 1; done; exit 1"
        )
        assert setup.returncode == 0, setup.stderr
        yield stack
    finally:
        stack.run("down", "-v", "-t", "1", check=False)


def _attempt(stack: _Compose, label: str, script: str) -> subprocess.CompletedProcess[str]:
    result = stack.sh(f"cd /root/project && git reset -q --hard agent-start && {script}")
    print(f"--- {label}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    return result


@pytest.mark.live
def test_live_hook_refuses_rebase_and_force_and_is_invisible(live_stack: _Compose) -> None:
    rebase = _attempt(
        live_stack,
        "rebase push",
        "git pull -q --rebase origin main && git push origin HEAD:main",
    )
    assert rebase.returncode != 0 and "protected lineage violated" in rebase.stderr
    force = _attempt(
        live_stack,
        "force push",
        "git push --force origin HEAD:main",
    )
    assert force.returncode != 0 and "protected lineage violated" in force.stderr
    merge = _attempt(
        live_stack,
        "merge push",
        "git pull -q --no-rebase --no-edit origin main && git push origin HEAD:main",
    )
    assert merge.returncode == 0, merge.stderr
    hunt = "find / -xdev -name pre-receive 2>/dev/null; ls -A /srv 2>/dev/null; true"
    in_default = live_stack.sh(hunt)
    in_origin = live_stack.sh(hunt, service="origin")
    print(f"--- hook hunt in default: {in_default.stdout!r}")
    print(f"--- same hunt in origin (positive control): {in_origin.stdout!r}")
    assert "/srv/origin.git/hooks/pre-receive" in in_origin.stdout
    assert in_default.stdout.strip() == ""
