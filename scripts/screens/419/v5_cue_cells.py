"""#621 item 5: the six cue-pair cells, Null / Full / Placebo x world A+cue / B. No model call.

The v4 cells with two changes: each world installs its own project, and both origins are silent
(S475): no hook, so every push lands. World A+cue's project is v4's plus the trace, and its origin
is v4's ``seed-off`` plus ``attested.txt``; world B's project is v4's, and its origin is
``seed-off``. ``cell_world`` names the world's definition of correct, ``a`` or ``b``, so
``consequence_v4.classify`` and ``twin_readout`` score these cells unchanged; ``cell_cue`` records
whether the trace was present.
The Full arm is the reviewed ``pull-rebase`` copy and the placebo is v4's, both unchanged.

Run: PYTHONPATH=src python scripts/screens/419/v5_cue_cells.py [--fixture-root DIR] [--full-dir DIR]
Builds all six tasks and prints them. It never calls eval.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cue_audit import FIXTURE_ROOT_DEFAULT, PROMPT
from twin_digest import LIVE_IMAGE
from v4_cells import (
    ARMS,
    FULL_DIR_DEFAULT,
    FULL_REFERENCE,
    PLACEBO_DIR,
    SETUP,
    WORLDS,
    Arm,
    World,
    card_text,
    consequence_oracle,
    project_files,
)

from skill_harness.subject import HarnessPin, OriginSidecar, build_paired_tasks

CELLS: tuple[tuple[Arm, World], ...] = tuple(itertools.product(ARMS, WORLDS))
PROJECTS: dict[World, str] = {"a": "project-a-cue", "b": "project-b"}
WORLD_LABELS: dict[World, str] = {"a": "a-cue", "b": "b"}


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
        "prompt": (fixture_root / PROMPT).read_text(encoding="utf-8"),
        "oracle": "command_succeeds",
        "oracle_arg": consequence_oracle(shas),
        "pin": pin,
        "epochs": epochs,
        "setup": SETUP,
    }
    cells: dict[tuple[Arm, World], Any] = {}
    for world in WORLDS:
        fixture = fixture_root / "fixture"
        origin = OriginSidecar.from_seed(fixture / f"seed-world-{world}")
        files = project_files(fixture / PROJECTS[world])
        world_dir = compose_dir / f"world-{WORLD_LABELS[world]}"
        per_world = {**shared, "files": files, "origin": origin, "compose_dir": world_dir}
        card = build_paired_tasks(skill_dir=full_dir, **per_world)
        placebo = build_paired_tasks(skill_dir=PLACEBO_DIR, **per_world)
        built: dict[Arm, Any] = {
            "null": card["null"],
            "full": card["full"],
            "placebo": placebo["full"],
        }
        for arm, task in built.items():
            metadata = {
                **(task.metadata or {}),
                "cell_arm": arm,
                "cell_world": world,
                "cell_cue": "present" if world == "a" else "absent",
            }
            name = f"v5cue-{arm}-world-{WORLD_LABELS[world]}"
            cells[(arm, world)] = task_with(task, name=name, metadata=metadata)
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
    compose_dir = Path(tempfile.mkdtemp(prefix="v5-cue-cells-"))
    cells = build_cells(
        fixture_root=args.fixture_root,
        full_dir=args.full_dir,
        pin=pin,
        epochs=args.epochs,
        compose_dir=compose_dir,
    )
    for (arm, world), task in cells.items():
        print(f"cell {arm}/{WORLD_LABELS[world]}: task {task.name!r}, epochs {task.epochs}")
    print(f"{len(cells)} cells built under {compose_dir}; no eval was run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
