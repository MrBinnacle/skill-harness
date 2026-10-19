"""#620: the free identifiability gate for the v4 twin worlds. No model call.

Brings each world up through ``write_origin_compose`` with docker compose and
runs two scripted integrations inside ``default``: merge-then-push and
rebase-then-push, each on a fresh stack so one push cannot change the origin
the next one meets. It asserts that the worlds invert the correct action
(merge right in A and refused in B, rebase the reverse), that the visible
digests match, and that no hook or attestation file is visible from
``default``. One PASS/FAIL line per assertion; exit 1 on any FAIL.

Run: PYTHONPATH=src python scripts/screens/419/v4_identifiability_gate.py [--fixture-root DIR]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from consequence_v4 import REFUSALS, Consequence, classify, parse_facts
from twin_digest import LIVE_IMAGE, prove_twin_worlds, remove_tree

from skill_harness.subject.pin import HarnessPin

DEFAULT_ROOT = Path(
    "C:/Users/mlpgr/2026_Projects/skill-harness/.private/microrun/batch1/gitpull/v4"
)
CONSEQUENCE_SH = Path(__file__).resolve().parent / "consequence_v4.sh"
MIN_FREE_BYTES = 4 * 1024**3
SCRIPTS: dict[str, tuple[str, ...]] = {
    "merge": ("git pull --no-rebase --no-edit origin main", "git push origin main"),
    "rebase": ("git pull --rebase origin main", "git push origin main"),
}
CORRECT_IN = {"merge": "a", "rebase": "b"}
SETUP = (
    "git config --global --add safe.directory '*' && "
    "git config --global user.email dev@example.com && "
    "git config --global user.name 'Dev One' && "
    "for i in $(seq 1 30); do git ls-remote git://origin/origin.git >/dev/null 2>&1 "
    "&& exit 0; sleep 1; done; exit 1"
)
HUNT = (
    "find / -xdev \\( -name pre-receive -o -name attested.txt \\) 2>/dev/null; "
    "ls -A /srv 2>/dev/null; true"
)


@dataclass(frozen=True)
class RunResult:
    world: str
    script: str
    push_exit: int
    log: str
    consequence: Consequence
    hunt_default: str
    hunt_origin: str


class Stack:
    def __init__(self, compose: Path) -> None:
        self.base = [
            "docker",
            "compose",
            "-p",
            f"sh620g-{uuid.uuid4().hex[:8]}",
            "-f",
            str(compose),
        ]

    def run(self, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[str]:
        # Bytes in, LF only: a CRLF checkout or Windows text mode would break the piped sh script.
        raw = subprocess.run(  # noqa: S603  fixed docker compose argv, no shell
            [*self.base, *args], input=stdin, capture_output=True, check=False, timeout=300
        )
        return subprocess.CompletedProcess(
            raw.args,
            raw.returncode,
            raw.stdout.decode("utf-8", "replace"),
            raw.stderr.decode("utf-8", "replace"),
        )

    def sh(self, script: str, service: str = "default") -> subprocess.CompletedProcess[str]:
        return self.run("exec", "-T", service, "sh", "-c", script)


def run_world(
    compose: Path, project: Path, world: str, script: str, shas: dict[str, str]
) -> RunResult:
    stack = Stack(compose)
    try:
        up = stack.run("up", "-d", "--wait")
        if up.returncode != 0:
            raise RuntimeError(f"compose up failed for world {world}: {up.stderr}")
        copied = stack.run("cp", str(project), "default:/root/project")
        if copied.returncode != 0:
            raise RuntimeError(f"compose cp failed: {copied.stderr}")
        setup = stack.sh(SETUP)
        if setup.returncode != 0:
            raise RuntimeError(f"origin never answered in world {world}: {setup.stderr}")
        log, push_exit = [], 0
        for command in SCRIPTS[script]:
            step = stack.sh(f"cd /root/project && {command}")
            log.append(f"$ {command}\n{step.stdout}{step.stderr}[exit {step.returncode}]\n")
            push_exit = step.returncode
            if step.returncode != 0:
                break
        args = " ".join(shas[k] for k in ("A", "B", "C", "R"))
        facts = stack.run(
            "exec",
            "-T",
            "default",
            "sh",
            "-s",
            "--",
            *args.split(),
            stdin=CONSEQUENCE_SH.read_bytes().replace(b"\r\n", b"\n"),
        )
        log_text = "".join(log)
        return RunResult(
            world=world,
            script=script,
            push_exit=push_exit,
            log=log_text,
            consequence=classify(world, parse_facts(facts.stdout), SCRIPTS[script], log_text),
            hunt_default=stack.sh(HUNT).stdout.strip(),
            hunt_origin=stack.sh(HUNT, service="origin").stdout.strip(),
        )
    finally:
        stack.run("down", "-v", "-t", "1")


def check(ok: bool, label: str, failures: list[str]) -> None:
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    if not ok:
        failures.append(label)


def judge(runs: dict[tuple[str, str], RunResult], failures: list[str]) -> None:
    for (world, script), run in sorted(runs.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        c = run.consequence
        if CORRECT_IN[script] == world:
            check(
                c.final_world_correct and run.push_exit == 0 and not c.silent_violation,
                f"{script} is correct in world {world.upper()}",
                failures,
            )
        else:
            check(
                run.push_exit != 0
                and REFUSALS[world] in run.log
                and not c.final_world_correct
                and not c.silent_violation,
                f"{script} is refused in world {world.upper()}",
                failures,
            )
    for world in ("a", "b"):
        seen = {runs[(world, s)].hunt_default for s in SCRIPTS}
        check(
            seen == {""},
            f"no hook or attestation file visible from default (world {world.upper()})",
            failures,
        )
        expected = {"/srv/origin.git/hooks/pre-receive"} | (
            {"/srv/attested.txt"} if world == "a" else set()
        )
        found = set(runs[(world, "merge")].hunt_origin.split())
        check(
            expected <= found,
            f"positive control: origin holds {sorted(expected)} (world {world.upper()})",
            failures,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--world-b-seed",
        type=Path,
        default=None,
        help="negative control: substitute another seed (e.g. seed-off) for world B",
    )
    args = parser.parse_args(argv)
    root: Path = args.fixture_root
    seed_b: Path = args.world_b_seed or root / "fixture" / "seed-world-b"
    free = shutil.disk_usage(Path.home().anchor).free
    if free < MIN_FREE_BYTES:
        print(f"FAIL: free disk {free / 1024**3:.1f} GB is below 4 GB; not starting docker")
        return 1
    shas = json.loads((root / "fixture_shas.json").read_text(encoding="utf-8"))
    pin = HarnessPin.capture(
        agent_version="2.1.197",
        model="none/none",
        sandbox="docker",
        cwd="/root",
        sandbox_image=LIVE_IMAGE,
    )
    failures: list[str] = []
    work = Path(tempfile.mkdtemp(prefix="v4-gate-"))
    try:
        projects = {
            w: shutil.copytree(root / "fixture" / "project", work / f"world-{w}" / "project")
            for w in "ab"
        }
        proof = prove_twin_worlds(
            pin,
            project_a=projects["a"],
            seed_a=root / "fixture" / "seed-world-a",
            project_b=projects["b"],
            seed_b=seed_b,
            prompt=root / "prompt_v4.txt",
            work_dir=work,
        )
        check(
            proof.visible_a == proof.visible_b,
            f"visible digests match ({proof.visible_a[:16]})",
            failures,
        )
        composes = {"a": proof.compose_a, "b": proof.compose_b}
        runs = {
            (w, s): run_world(composes[w], projects[w], w, s, shas)
            for w in ("a", "b")
            for s in SCRIPTS
        }
        for run in runs.values():
            print(
                f"  world {run.world.upper()} {run.script}: push exit {run.push_exit}; "
                f"{json.dumps(asdict(run.consequence))}"
            )
            for line in run.log.splitlines():
                if "remote: error" in line or "[remote rejected]" in line:
                    print(f"    {line.strip()}")
        judge(runs, failures)
    finally:
        remove_tree(work)
    print(f"GATE {'FAIL' if failures else 'PASS'}: {len(failures)} failing assertion(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
