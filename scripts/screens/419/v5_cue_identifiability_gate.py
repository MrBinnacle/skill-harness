"""#621: the free identifiability gate for the cue pair, world A+cue and world B. No model call.

The v4 gate's scripted runs and judgement, applied to the v5-cue fixture. World A+cue pushes to
v4's world A origin from a project that carries the trace; world B is v4's world B unchanged.
Before any container starts, the leak audit must pass: world B equals the v4 reference, the only
path that differs between the two projects is the trace, and with the trace removed the visible
digests match. Then merge-then-push and rebase-then-push run on a fresh stack each, and the v4
judgement asserts that the worlds invert the correct action and that no hook or attestation file
is visible from ``default``. One PASS/FAIL line per assertion; exit 1 on any FAIL.

Run: PYTHONPATH=src python scripts/screens/419/v5_cue_identifiability_gate.py [--fixture-root DIR]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cue_audit import (
    FIXTURE_ROOT_DEFAULT,
    PROMPT,
    TRACE,
    V4_ROOT_DEFAULT,
    CueLeakError,
    prove_cue_twins,
)
from twin_digest import LIVE_IMAGE, remove_tree
from v4_identifiability_gate import MIN_FREE_BYTES, SCRIPTS, check, judge, run_world

from skill_harness.subject import TwinComposeError
from skill_harness.subject.pin import HarnessPin

PROJECTS = {"a": "project-a-cue", "b": "project-b"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture-root", type=Path, default=FIXTURE_ROOT_DEFAULT)
    parser.add_argument("--v4-root", type=Path, default=V4_ROOT_DEFAULT)
    args = parser.parse_args(argv)
    root: Path = args.fixture_root
    v4: Path = args.v4_root
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
        projects = {
            w: shutil.copytree(root / "fixture" / name, work / f"world-{w}" / "project")
            for w, name in PROJECTS.items()
        }
        try:
            proof = prove_cue_twins(
                pin,
                reference_project=v4 / "fixture" / "project",
                reference_seeds=(
                    v4 / "fixture" / "seed-world-a",
                    v4 / "fixture" / "seed-world-b",
                ),
                project_cue=projects["a"],
                seed_a=root / "fixture" / "seed-world-a",
                project_b=projects["b"],
                seed_b=root / "fixture" / "seed-world-b",
                prompt=root / PROMPT,
                work_dir=work,
            )
        except (CueLeakError, TwinComposeError) as exc:
            check(False, f"leak audit: {exc}", failures)
            print(f"GATE FAIL: {len(failures)} failing assertion(s); no container was started")
            return 1
        check(True, "leak audit: world B equals the v4 reference project and seeds", failures)
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
            label = "A+cue" if run.world == "a" else "B"
            print(
                f"  world {label} {run.script}: push exit {run.push_exit}; "
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
