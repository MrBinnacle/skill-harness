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
import itertools
import json
import sys
import tempfile
from collections.abc import Sequence
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
    *,
    placebo_correct: int,
    placebo_n: int,
    null_correct: int,
    null_n: int,
    placebo_outcomes: Sequence[int] | None = None,
    null_outcomes: Sequence[int] | None = None,
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
    if placebo_outcomes is not None:
        _validate_outcomes(placebo_outcomes, correct=placebo_correct, n=placebo_n)
    if null_outcomes is not None:
        _validate_outcomes(null_outcomes, correct=null_correct, n=null_n)
    if placebo_n < MIN_VALID_PLACEBO:
        return {
            "outcome": "CANT_TELL_YET",
            "reason": f"fewer than {MIN_VALID_PLACEBO} valid Placebo epochs ({placebo_n})",
            "placebo_n": placebo_n,
            "null_n": null_n,
        }

    placebo_xs, placebo_order = _bound_outcomes(
        outcomes=placebo_outcomes,
        correct=placebo_correct,
        n=placebo_n,
        side="lower",
    )
    lb_placebo = one_sided_betting_bound(placebo_xs, alpha=ALPHA, side="lower")

    null_xs, null_order = _bound_outcomes(
        outcomes=null_outcomes,
        correct=null_correct,
        n=null_n,
        side="upper",
    )
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
            "order": placebo_order,
        },
        "null": {
            "n": null_n,
            "correct": null_correct,
            "rate": null_correct / null_n if null_n else 0.0,
            "ub_at_alpha": ub_null,
            "order": null_order,
        },
        "lb_diff": lb_diff,
        "min_valid_placebo": MIN_VALID_PLACEBO,
        "placebo_epochs": PLACEBO_EPOCHS,
    }


def _bound_outcomes(
    *, outcomes: Sequence[int] | None, correct: int, n: int, side: Literal["lower", "upper"]
) -> tuple[tuple[float, ...], str]:
    """Use recorded epoch order, or the least favorable order when only counts remain."""
    if outcomes is not None:
        return _validate_outcomes(outcomes, correct=correct, n=n), "epoch order"

    candidates = []
    for positions in itertools.combinations(range(n), correct):
        stream = [0.0] * n
        for position in positions:
            stream[position] = 1.0
        candidates.append(tuple(stream))

    def bound(stream: tuple[float, ...]) -> float:
        return one_sided_betting_bound(stream, alpha=ALPHA, side=side)

    selected = min(candidates, key=bound) if side == "lower" else max(candidates, key=bound)
    return selected, "counts only: least favorable epoch order"


def _validate_outcomes(outcomes: Sequence[int], *, correct: int, n: int) -> tuple[float, ...]:
    stream = tuple(float(value) for value in outcomes)
    if len(stream) != n or sum(stream) != correct or not set(stream) <= {0.0, 1.0}:
        raise ValueError("outcomes disagree with their recorded count")
    return stream


def _cell_outcomes(rows: Sequence[dict[str, Any]], arm: str, world: str) -> tuple[int, ...]:
    """Return valid cell outcomes in launch order and refuse duplicate epoch records."""
    valid = [
        row
        for row in rows
        if row.get("arm") == arm and row.get("world") == world and not row.get("void")
    ]
    valid.sort(key=lambda row: int(row["epoch"]))
    epochs = [int(row["epoch"]) for row in valid]
    if len(epochs) != len(set(epochs)):
        raise ValueError(f"duplicate {arm}/{world} epoch in readout")
    return tuple(int(bool(row["final_world_correct"])) for row in valid)


def _load_null_b(path: Path) -> tuple[tuple[int, ...] | None, int, int]:
    """Load Null-B outcomes in epoch order, or counts when historical rows are unavailable."""
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data["summary"]["null/b"]
    correct, n = int(summary["correct"]), int(summary["n"])
    if "rows" not in data:
        return None, correct, n
    outcomes = _cell_outcomes(data["rows"], "null", "b")
    if len(outcomes) != n or sum(outcomes) != correct:
        raise ValueError(f"{path}: Null-B rows disagree with the summary")
    return outcomes, correct, n


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
    outcomes = _cell_outcomes(rows, "placebo", "b")
    return sum(outcomes), len(outcomes)


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

    null_outcomes, null_correct, null_n = _load_null_b(args.null_readout)
    rows = read_rows(args.out)
    row_data = [asdict(row) for row in rows]
    placebo_outcomes = _cell_outcomes(row_data, "placebo", "b")
    placebo_correct, placebo_n = sum(placebo_outcomes), len(placebo_outcomes)

    result = inertness_screen(
        placebo_correct=placebo_correct,
        placebo_n=placebo_n,
        null_correct=null_correct,
        null_n=null_n,
        placebo_outcomes=placebo_outcomes,
        null_outcomes=null_outcomes,
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
