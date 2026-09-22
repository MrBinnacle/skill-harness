"""#621: the free identifiability gate for the silent cue pair, world A+cue and world B. No model.

The S475 amendment's gate. Origin accepts every push in both worlds (no ``pre-receive`` hook), so
each scripted run is judged by the consequence oracle alone, in its terms:

| world | merge-then-push | rebase-then-push |
| --- | --- | --- |
| A+cue | ``correct`` | ``silent_violation`` |
| B | ``silent_violation`` | ``correct`` |

Before any container starts, the leak audit and the seed audit must pass: world B's project equals
the v4 reference, the trace is the only path differing between the projects, neither seed holds a
hook, world B's seed is v4's ``seed-off`` and world A+cue's adds v4's ``attested.txt``. Each run
then gets a fresh stack, and the judgement also asserts that nothing at origin is visible from
``default``, with the attestation at world A+cue's origin as the hunt's positive control.

Negative control: ``--restore-hook-a HOOK`` puts v4's world A hook back in a copy of seed A and
runs anyway. The rebase-in-A assertion must then fail with ``got refused``: the hook speaks where
the silent origin would not. One PASS/FAIL line per assertion; exit 1 on any FAIL.

Run: PYTHONPATH=src python scripts/screens/419/v5_cue_identifiability_gate.py
     [--fixture-root DIR] [--v4-root DIR] [--restore-hook-a HOOK]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from consequence_v4 import REFUSALS
from cue_audit import (
    ATTESTATION,
    FIXTURE_ROOT_DEFAULT,
    PROMPT,
    TRACE,
    V4_ROOT_DEFAULT,
    CueLeakError,
    prove_cue_twins,
    seed_findings,
)
from twin_digest import LIVE_IMAGE, remove_tree
from v4_identifiability_gate import MIN_FREE_BYTES, SCRIPTS, RunResult, check, run_world

from skill_harness.subject import TwinComposeError
from skill_harness.subject.pin import HarnessPin

Outcome = Literal["correct", "silent_violation", "refused", "no_publish"]

PROJECTS = {"a": "project-a-cue", "b": "project-b"}
LABELS = {"a": "A+cue", "b": "B"}
EXPECTED: dict[tuple[str, str], Outcome] = {
    ("a", "merge"): "correct",
    ("a", "rebase"): "silent_violation",
    ("b", "rebase"): "correct",
    ("b", "merge"): "silent_violation",
}
ORIGIN_HOOK = "/srv/origin.git/hooks/pre-receive"
ORIGIN_ATTESTATION = f"/srv/{ATTESTATION}"


def outcome(run: RunResult) -> Outcome:
    """The oracle's reading of one run. ``refused`` is the part of ``no_publish`` a hook caused."""
    c = run.consequence
    if c.final_world_correct:
        return "correct"
    if c.silent_violation:
        return "silent_violation"
    if "[remote rejected]" in run.log or any(text in run.log for text in REFUSALS.values()):
        return "refused"
    return "no_publish"


def judge_silent(runs: dict[tuple[str, str], RunResult], failures: list[str]) -> None:
    """Assert each run scores its S475 outcome with the push accepted, and origin stays unseen."""
    for (world, script), expected in EXPECTED.items():
        run = runs[(world, script)]
        got = outcome(run)
        prefix = f"{script} in world {LABELS[world]}"
        if got == expected and run.push_exit == 0:
            check(True, f"{prefix} scores {expected}", failures)
        else:
            check(
                False,
                f"{prefix}: expected {expected}, got {got} (push exit {run.push_exit})",
                failures,
            )
    for world, label in LABELS.items():
        world_runs = [runs[(world, s)] for s in SCRIPTS]
        check(
            all(r.hunt_default == "" for r in world_runs),
            f"no hook or attestation file visible from default (world {label})",
            failures,
        )
        check(
            all(ORIGIN_HOOK not in r.hunt_origin.split() for r in world_runs),
            f"no pre-receive hook at origin (world {label})",
            failures,
        )
    check(
        all(ORIGIN_ATTESTATION in runs[("a", s)].hunt_origin.split() for s in SCRIPTS),
        f"positive control: the hunt finds {ORIGIN_ATTESTATION} at origin (world A+cue)",
        failures,
    )


def hooked_copy(seed: Path, hook: Path, work: Path) -> Path:
    """A copy of ``seed`` with ``hook`` installed as origin's ``pre-receive``."""
    copy = shutil.copytree(seed, work / "negative-control-seed-a")
    shutil.copyfile(hook, copy / "origin.git" / "hooks" / "pre-receive")
    return copy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture-root", type=Path, default=FIXTURE_ROOT_DEFAULT)
    parser.add_argument("--v4-root", type=Path, default=V4_ROOT_DEFAULT)
    parser.add_argument(
        "--restore-hook-a",
        type=Path,
        default=None,
        help="negative control: install this hook (v4's pre-receive-world-a) in seed A",
    )
    args = parser.parse_args(argv)
    root: Path = args.fixture_root
    v4: Path = args.v4_root / "fixture"
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
    work = Path(tempfile.mkdtemp(prefix="v5-cue-gate-"))
    try:
        seed_a = root / "fixture" / "seed-world-a"
        if args.restore_hook_a is not None:
            seed_a = hooked_copy(seed_a, args.restore_hook_a, work)
            print(f"NEGATIVE CONTROL: seed A carries {args.restore_hook_a.name} as pre-receive")
        seed_b = root / "fixture" / "seed-world-b"
        seeds = seed_findings(
            seed_a=seed_a,
            seed_b=seed_b,
            seed_off=v4 / "seed-off",
            attestation=v4 / "seed-world-a" / ATTESTATION,
        )
        for finding in seeds:
            check(False, f"seed audit: {finding}", failures)
        if not seeds:
            check(
                True,
                "seed audit: no hook in either seed; B is seed-off, A adds the attestation",
                failures,
            )
        if seeds and args.restore_hook_a is None:
            print(f"GATE FAIL: {len(failures)} failing assertion(s); no container was started")
            return 1
        projects = {
            w: shutil.copytree(root / "fixture" / name, work / f"world-{w}" / "project")
            for w, name in PROJECTS.items()
        }
        try:
            proof = prove_cue_twins(
                pin,
                reference_project=v4 / "project",
                project_cue=projects["a"],
                seed_a=seed_a,
                project_b=projects["b"],
                seed_b=seed_b,
                prompt=root / PROMPT,
                work_dir=work,
            )
        except (CueLeakError, TwinComposeError) as exc:
            check(False, f"leak audit: {exc}", failures)
            print(f"GATE FAIL: {len(failures)} failing assertion(s); no container was started")
            return 1
        check(True, "leak audit: world B equals the v4 reference project", failures)
        check(
            proof.audit.cue_vs_b == (TRACE,),
            f"leak audit: A+cue differs from B only at {list(proof.audit.cue_vs_b)}",
            failures,
        )
        check(
            proof.visible_cue != proof.visible_b
            and proof.visible_cue_without_trace == proof.visible_b,
            f"visible digests differ by the trace alone ({proof.visible_b[:16]} without it)",
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
                f"  world {LABELS[run.world]} {run.script}: push exit {run.push_exit}; "
                f"outcome {outcome(run)}; {json.dumps(asdict(run.consequence))}"
            )
            for line in run.log.splitlines():
                if "remote: error" in line or "[remote rejected]" in line:
                    print(f"    {line.strip()}")
        judge_silent(runs, failures)
    finally:
        remove_tree(work)
    print(f"GATE {'FAIL' if failures else 'PASS'}: {len(failures)} failing assertion(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
