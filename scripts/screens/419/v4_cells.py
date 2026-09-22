"""#620 item 8: the six twin-screen cells, Null / Full / Placebo x world A / B. No model call.

A cell is an arm, meaning the skill the agent has installed, crossed with a world, meaning the
origin seed it pushes to. The arm is the skill directory handed to ``build_paired_tasks`` and the
world is its origin sidecar. #554's declared arms are system-prompt assemblies for the ablation
runner: they cannot carry a world, and the resolver refuses two arms with one assembly, which is
what Null in world A and Null in world B are. So the cells are declared here, as subject-layer
tasks.

Run: PYTHONPATH=src python scripts/screens/419/v4_cells.py [--fixture-root DIR] [--full-dir DIR]
Builds all six tasks and prints them. It never calls eval.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from twin_digest import LIVE_IMAGE

from skill_harness.subject import HarnessPin, OriginSidecar, build_paired_tasks

Arm = Literal["null", "full", "placebo"]
World = Literal["a", "b"]
ARMS: tuple[Arm, ...] = ("null", "full", "placebo")
WORLDS: tuple[World, ...] = ("a", "b")
CELLS: tuple[tuple[Arm, World], ...] = tuple(itertools.product(ARMS, WORLDS))

HERE = Path(__file__).resolve().parent
PLACEBO_DIR = HERE / "v4_arms" / "placebo" / "push-secret-scan"
FULL_REFERENCE = HERE / "v4_arms" / "full" / "pull-rebase" / "SKILL.md"
FULL_DIR_DEFAULT = (
    Path.home() / ".claude/plugins/cache/mrbinnacle-skills/mrbinnacle-engineering/3.0.0/pull-rebase"
)
FIXTURE_ROOT_DEFAULT = Path(
    "C:/Users/mlpgr/2026_Projects/skill-harness/.private/microrun/batch1/gitpull/v4"
)
CONSEQUENCE_SH = HERE / "consequence_v4.sh"
SETUP = (
    "git config --global --add safe.directory '*' && "
    "for i in $(seq 1 30); do git ls-remote git://origin/origin.git >/dev/null 2>&1 "
    "&& exit 0; sleep 1; done; exit 1"
)


def project_files(project: Path) -> dict[str, bytes]:
    """Every file under ``project``, ``.git`` included, keyed by its sandbox path."""
    return {
        f"/root/project/{p.relative_to(project).as_posix()}": p.read_bytes()
        for p in sorted(project.rglob("*"))
        if p.is_file() and not p.name.endswith(".sample")
    }


def card_text(path: Path) -> str:
    """A card's text with line endings normalised: the install is CRLF, the repo copy LF."""
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8").rstrip("\n")


def consequence_oracle(shas: dict[str, str]) -> str:
    """``consequence_v4.sh`` with the fixture SHAs bound. It always exits 0.

    The facts it prints are the record, and ``consequence_v4.classify`` scores them per world,
    so a passing ``command_succeeds`` score means only that the facts were collected.
    """
    body = CONSEQUENCE_SH.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    return f"set -- {shas['A']} {shas['B']} {shas['C']} {shas['R']}\n{body}"


def build_cells(
    *,
    fixture_root: Path,
    full_dir: Path,
    pin: HarnessPin,
    epochs: int,
    compose_dir: Path,
) -> dict[tuple[Arm, World], Any]:
    """Build one Inspect task per cell. Nothing is evaluated.

    :raises ValueError: the Full card is not the reviewed copy in ``v4_arms/full``.
    """
    if card_text(full_dir / "SKILL.md") != card_text(FULL_REFERENCE):
        raise ValueError(
            f"{full_dir / 'SKILL.md'} differs from the reviewed copy {FULL_REFERENCE}; "
            "the placebo was matched to that copy"
        )
    from inspect_ai import task_with  # the [inspect] extra; CI installs only [dev]

    shas = json.loads((fixture_root / "fixture_shas.json").read_text(encoding="utf-8"))
    shared: dict[str, Any] = {
        "prompt": (fixture_root / "prompt_v4.txt").read_text(encoding="utf-8"),
        "oracle": "command_succeeds",
        "oracle_arg": consequence_oracle(shas),
        "pin": pin,
        "epochs": epochs,
        "files": project_files(fixture_root / "fixture" / "project"),
        "setup": SETUP,
    }
    cells: dict[tuple[Arm, World], Any] = {}
    for world in WORLDS:
        origin = OriginSidecar.from_seed(fixture_root / "fixture" / f"seed-world-{world}")
        world_dir = compose_dir / f"world-{world}"
        card = build_paired_tasks(
            skill_dir=full_dir, origin=origin, compose_dir=world_dir, **shared
        )
        placebo = build_paired_tasks(
            skill_dir=PLACEBO_DIR, origin=origin, compose_dir=world_dir, **shared
        )
        built: dict[Arm, Any] = {
            "null": card["null"],
            "full": card["full"],
            "placebo": placebo["full"],
        }
        for arm, task in built.items():
            metadata = {**(task.metadata or {}), "cell_arm": arm, "cell_world": world}
            cells[(arm, world)] = task_with(task, name=f"v4-{arm}-world-{world}", metadata=metadata)
    return cells


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture-root", type=Path, default=FIXTURE_ROOT_DEFAULT)
    parser.add_argument("--full-dir", type=Path, default=FULL_DIR_DEFAULT)
    parser.add_argument("--epochs", type=int, default=1)
    args = parser.parse_args(argv)
    pin = HarnessPin.capture(
        agent_version="2.1.197",
        model="none/none",
        sandbox="docker",
        cwd="/root",
        sandbox_image=LIVE_IMAGE,
    )
    compose_dir = Path(tempfile.mkdtemp(prefix="v4-cells-"))
    cells = build_cells(
        fixture_root=args.fixture_root,
        full_dir=args.full_dir,
        pin=pin,
        epochs=args.epochs,
        compose_dir=compose_dir,
    )
    for (arm, world), task in cells.items():
        print(f"cell {arm}/{world}: task {task.name!r}, epochs {task.epochs}")
    print(f"{len(cells)} cells built under {compose_dir}; no eval was run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
