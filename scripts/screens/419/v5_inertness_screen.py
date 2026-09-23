"""#651 inertness screen: Placebo-B against Null-B, 16 vs 8 epochs.

Pre-registered before Stage 1A. Three outcomes (S477):

  Redesign:    one-sided LB(P - N) > 0 at alpha 0.05 -> placebo is active
  Continue:    no such bound -> screen does not certify inertness
  CANT_TELL_YET: fewer than 12 valid Placebo epochs (voids) -> rerun

The screen never passes on "p > 0.05" and a pass never becomes "the placebo
is inert". Unequal arms are read with separate one-sided bounds, no top-up.

Run: PYTHONPATH=src python scripts/screens/419/v5_inertness_screen.py \
         --out DIR --null-readout READOUT.json [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cue_audit import FIXTURE_ROOT_DEFAULT
from twin_digest import LIVE_IMAGE
from v4_cells import FULL_DIR_DEFAULT
from v5_cue_cells import build_cells

from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound
from skill_harness.subject import HarnessPin

ALPHA = 0.05
MIN_VALID_PLACEBO = 12
PLACEBO_EPOCHS = 16
NULL_EPOCHS = 8
PER_SAMPLE_CAP = 0.30
HARD_CAP_USD = PLACEBO_EPOCHS * PER_SAMPLE_CAP
MODEL = "anthropic/claude-sonnet-5"
RETRY_UNCAUGHT_ERRORS = 1


InertnessOutcome = Literal["REDESIGN", "CONTINUE", "CANT_TELL_YET"]


def inertness_screen(
    *, placebo_correct: int, placebo_n: int, null_correct: int, null_n: int
) -> dict[str, Any]:
    """Read the Placebo-B vs Null-B inertness screen.

    Returns a dict with the outcome, bounds, and diagnostic data.
    """
    if not 0 <= placebo_correct <= placebo_n:
        raise ValueError(f"placebo correct must be in [0, {placebo_n}], got {placebo_correct}")
    if not 0 <= null_correct <= null_n:
        raise ValueError(f"null correct must be in [0, {null_n}], got {null_correct}")
    if placebo_n > PLACEBO_EPOCHS:
        raise ValueError(
            f"placebo has {placebo_n} epochs; the registered maximum is {PLACEBO_EPOCHS}"
        )
    if null_n != NULL_EPOCHS:
        raise ValueError(f"Null-B must contain {NULL_EPOCHS} valid epochs, got {null_n}")
    if placebo_n < MIN_VALID_PLACEBO:
        return {
            "outcome": "CANT_TELL_YET",
            "reason": f"fewer than {MIN_VALID_PLACEBO} valid Placebo epochs ({placebo_n})",
            "placebo_n": placebo_n,
            "null_n": null_n,
        }

    # One-sided lower bound on Placebo rate at alpha.
    placebo_xs = tuple([1.0] * placebo_correct + [0.0] * (placebo_n - placebo_correct))
    lb_placebo = one_sided_betting_bound(placebo_xs, alpha=ALPHA, side="lower")

    # One-sided upper bound on Null rate at alpha.
    null_xs = tuple([1.0] * null_correct + [0.0] * (null_n - null_correct))
    ub_null = one_sided_betting_bound(null_xs, alpha=ALPHA, side="upper")

    # LB(P - N) = LB(mu_P) - UB(mu_N).
    lb_diff = lb_placebo - ub_null

    if lb_diff > 0:
        outcome: InertnessOutcome = "REDESIGN"
    else:
        outcome = "CONTINUE"

    return {
        "outcome": outcome,
        "alpha": ALPHA,
        "placebo": {
            "n": placebo_n,
            "correct": placebo_correct,
            "rate": placebo_correct / placebo_n if placebo_n else 0.0,
            "lb_at_alpha": lb_placebo,
        },
        "null": {
            "n": null_n,
            "correct": null_correct,
            "rate": null_correct / null_n if null_n else 0.0,
            "ub_at_alpha": ub_null,
        },
        "lb_diff": lb_diff,
        "min_valid_placebo": MIN_VALID_PLACEBO,
        "placebo_epochs": PLACEBO_EPOCHS,
    }


def _load_null_b(path: Path) -> tuple[int, int]:
    """Load Null-B outcomes from a Stage 1 readout. Returns (correct, n)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data["summary"]["null/b"]
    return int(summary["correct"]), int(summary["n"])


def _load_placebo_b(path: Path) -> tuple[int, int]:
    """Load Placebo-B outcomes from an eval log directory readout.

    Expects the same readout format as Stage 1A: rows with arm/world/epoch/void/final_world_correct.
    Returns (correct, n_valid).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    return _placebo_b_counts(rows)


def _placebo_b_counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Return (correct, n_valid) for the registered Placebo-B cell."""
    valid = [
        row
        for row in rows
        if row.get("arm") == "placebo" and row.get("world") == "b" and not row.get("void")
    ]
    correct = sum(1 for row in valid if row.get("final_world_correct"))
    return correct, len(valid)


def inertness_tasks(compose_dir: Path) -> tuple[HarnessPin, list[Any]]:
    """Return the 16-epoch Placebo-B task. Nothing is evaluated."""
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
        epochs=PLACEBO_EPOCHS,
        compose_dir=compose_dir,
        retry_uncaught_errors=RETRY_UNCAUGHT_ERRORS,
    )
    return pin, [cells[("placebo", "b")]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--null-readout", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run:
        print("DRY RUN: no model call.")
        print(f"  out: {args.out}")
        print(f"  null-readout: {args.null_readout}")
        return 0

    from v5_cue_stage1 import _model_cost

    cost = _model_cost()
    pin, tasks = inertness_tasks(Path(tempfile.mkdtemp(prefix="cue-inertness-")))
    print("pin fingerprint:", pin.fingerprint(), "| image:", pin.sandbox_image)
    print(
        f"tasks={[task.name for task in tasks]} epochs={PLACEBO_EPOCHS} model={MODEL} "
        f"per-sample cost_limit=${PER_SAMPLE_CAP:.3f} total cap=${HARD_CAP_USD:.2f} "
        f"retry_uncaught_errors={RETRY_UNCAUGHT_ERRORS} retry_on_error=0"
    )
    import inspect_ai
    from twin_readout import read_rows, summarise

    logs = inspect_ai.eval(
        tasks,
        log_dir=str(args.out),
        display="plain",
        retry_on_error=0,
        max_sandboxes=1,
        fail_on_error=False,
        cost_limit=PER_SAMPLE_CAP,
        model_cost_config=cost,
    )
    for log in logs:
        print("LOG:", log.location, "STATUS:", log.status, "run_id:", log.eval.run_id)

    null_correct, null_n = _load_null_b(args.null_readout)
    rows = read_rows(args.out)
    row_data = [asdict(row) for row in rows]
    placebo_correct, placebo_n = _placebo_b_counts(row_data)

    result = inertness_screen(
        placebo_correct=placebo_correct,
        placebo_n=placebo_n,
        null_correct=null_correct,
        null_n=null_n,
    )
    readout = {
        "rows": row_data,
        "summary": summarise(rows),
        "inertness_screen": result,
    }
    (args.out / "readout.json").write_text(json.dumps(readout, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"OUTCOME: {result['outcome']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
