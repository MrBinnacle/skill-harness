"""#651 inertness screen: Placebo-B against Null-B, 16 vs 8 epochs.

Pre-registered before Stage 1A. Three outcomes (S477):

  Redesign:    one-sided LB(P - N) > 0 at alpha 0.05 -> placebo is active
  Continue:    no such bound -> screen does not certify inertness
  CANT_TELL_YET: fewer than 12 valid Placebo epochs (voids) -> rerun

The screen never passes on "p > 0.05" and a pass never becomes "the placebo
is inert". Unequal arms are read with separate one-sided bounds, no top-up.

Run: PYTHONPATH=src python scripts/screens/419/v5_inertness_screen.py \
         --placebo-readout READOUT.json --null-readout READOUT.json [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

ALPHA = 0.05
MIN_VALID_PLACEBO = 12
PLACEBO_EPOCHS = 16


InertnessOutcome = Literal["REDESIGN", "CONTINUE", "CANT_TELL_YET"]


def inertness_screen(
    *, placebo_correct: int, placebo_n: int, null_correct: int, null_n: int
) -> dict[str, Any]:
    """Read the Placebo-B vs Null-B inertness screen.

    Returns a dict with the outcome, bounds, and diagnostic data.
    """
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
    valid = [
        r for r in rows if r.get("arm") == "placebo" and r.get("world") == "b" and not r.get("void")
    ]
    correct = sum(1 for r in valid if r.get("final_world_correct"))
    return correct, len(valid)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--placebo-readout", type=Path, required=True)
    parser.add_argument("--null-readout", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run:
        print("DRY RUN: no model call.")
        print(f"  placebo-readout: {args.placebo_readout}")
        print(f"  null-readout: {args.null_readout}")
        return 0

    null_correct, null_n = _load_null_b(args.null_readout)
    placebo_correct, placebo_n = _load_placebo_b(args.placebo_readout)

    result = inertness_screen(
        placebo_correct=placebo_correct,
        placebo_n=placebo_n,
        null_correct=null_correct,
        null_n=null_n,
    )
    print(json.dumps(result, indent=2))
    print(f"OUTCOME: {result['outcome']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
