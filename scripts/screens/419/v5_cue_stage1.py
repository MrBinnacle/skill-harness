"""#621 Stage 1 (#639): the Null headroom screen on the silent-origin cue pair, 8 epochs per world.

Authorised by the operator on the Binnacle Board, gate `cue-stage1`, answered
2026-09-22T20:05:00Z: "$12 approved (typed APPROVE in session S475, 22 Sep)". Hard cap $12.00.
Record: the steering repo's docs/research/keep-endpoint-ruling-621-S475.md. Only the two Null
cells run, world A+cue and world B; no card is installed.

Inspect's ``cost_limit`` is per sample, so 16 samples at $0.75 bound the run at $12.00. A void
epoch (the Claude Code binary exits 1 with empty stderr) retries once in place through
``retry_uncaught_errors``, inside the same sample and so inside the same cost limit. Sample-level
``retry_on_error`` stays 0: a retried sample carries a fresh cost limit and could pass the cap.

Run: PYTHONPATH=src python scripts/screens/419/v5_cue_stage1.py --out DIR [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cue_audit import FIXTURE_ROOT_DEFAULT
from inspect_ai.model import ModelCost, ModelInfo, set_model_info
from twin_digest import LIVE_IMAGE
from v4_cells import FULL_DIR_DEFAULT
from v5_cue_cells import build_cells

from skill_harness.ablation.subject import PRICE_PER_MTOK
from skill_harness.subject import HarnessPin

EPOCHS_PER_WORLD = 8
HARD_CAP_USD = 12.00
PER_SAMPLE_CAP = HARD_CAP_USD / (2 * EPOCHS_PER_WORLD)
MODEL = "anthropic/claude-sonnet-5"
RETRY_UNCAUGHT_ERRORS = 1


def stage1_tasks(compose_dir: Path) -> tuple[HarnessPin, list[Any]]:
    """Return the pin and the two Null tasks, world A+cue first. Nothing is evaluated."""
    pin = HarnessPin.capture(
        agent_version="2.1.197",
        model=MODEL,
        sandbox="docker",
        cwd="/root",
        sandbox_image=LIVE_IMAGE,
    )
    cells = build_cells(
        fixture_root=FIXTURE_ROOT_DEFAULT,
        full_dir=FULL_DIR_DEFAULT,
        pin=pin,
        epochs=EPOCHS_PER_WORLD,
        compose_dir=compose_dir,
        retry_uncaught_errors=RETRY_UNCAUGHT_ERRORS,
    )
    return pin, [cells[("null", "a")], cells[("null", "b")]]


def _model_cost() -> dict[str, ModelCost]:
    price = PRICE_PER_MTOK["claude-sonnet-5"]
    # cost_limit needs a price for the task's default "none" provider, which makes no call (S471).
    set_model_info(
        "none/none",
        ModelInfo(cost=ModelCost(input=0, output=0, input_cache_write=0, input_cache_read=0)),
    )
    return {
        MODEL: ModelCost(
            input=price["input"],
            output=price["output"],
            input_cache_write=price["cache_write"],
            input_cache_read=price["cache_read"],
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    cost = _model_cost()
    pin, tasks = stage1_tasks(Path(tempfile.mkdtemp(prefix="cue-stage1-")))
    print("pin fingerprint:", pin.fingerprint(), "| image:", pin.sandbox_image)
    print(
        f"tasks={[t.name for t in tasks]} epochs/world={EPOCHS_PER_WORLD} model={MODEL} "
        f"per-sample cost_limit=${PER_SAMPLE_CAP:.3f} total cap=${HARD_CAP_USD:.2f} "
        f"retry_uncaught_errors={RETRY_UNCAUGHT_ERRORS} retry_on_error=0"
    )
    if args.dry_run:
        print("DRY RUN: no model call.")
        return 0

    import inspect_ai

    logs = inspect_ai.eval(
        tasks,
        log_dir=str(args.out),
        display="plain",
        retry_on_error=0,
        max_sandboxes=2,
        fail_on_error=False,
        cost_limit=PER_SAMPLE_CAP,
        model_cost_config=cost,
    )
    for log in logs:
        print("LOG:", log.location, "STATUS:", log.status, "run_id:", log.eval.run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
