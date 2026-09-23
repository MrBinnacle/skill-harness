"""#621 Stage 1A (#649): 16 Full-A + 16 Placebo-A on the silent-origin cue pair, read once.

Authorised by the operator on the Binnacle Board, gate `cue-stage2`, answered 2026-09-22: "Only
the $2.66 first stage". Design record: the steering repo's
docs/research/stage2-lean-design-answer-S475.md, Stage 1A row. Only the Full-A and Placebo-A
cells run. The Null-A comparison reuses the 7 valid Null-A epochs of Stage 1 (#639), read from
``--null-readout``.

Each valid epoch scores 1 when the world ends correct and 0 otherwise; void epochs are excluded
and reported. The registered stop rule:

  UB(F - P) < 0.20, one-sided at alpha 0.05                           -> CUT_NO_LIFT
  LB(F - P) >= 0.20 and LB(F - N) >= 0.20, one-sided at --pass-alpha  -> A_PASSES_EARLY
  anything else                                                       -> UNRESOLVED_CONTINUE

F - P pairs Full and Placebo by launch index, the epoch number, never by completion order:
runtime can correlate with outcome, and the betting argument needs an order fixed before the
outcomes are seen. A pair is dropped when either epoch is void. The pair's x = (F - P + 1) / 2
is bounded by ``one_sided_betting_bound`` and mapped back by d = 2x - 1.

F - N has 16 Full against 7 Null epochs, so it is not paired. LB(F - N) is the lower bound on
the Full rate at pass-alpha/2 minus the upper bound on the Null rate at pass-alpha/2 (a union
bound), each on the raw 0/1 outcomes in epoch order.

The pass is the card-level test p = max(p_FN, p_FP) <= pass-alpha against the shifted null
H0: d <= 0.20, run as both one-sided lower bounds at level pass-alpha clearing 0.20.
``--pass-alpha`` defaults to the public ledger's LORDdep level for the first card tested,
0.0209, because the ledger controls false KEEPs. CUT_NO_LIFT is a separate futility boundary
at alpha 0.05. The launcher mints no verdict and writes no SERS receipt.

``--dry-run`` makes no model call. It prints the operating table for every (correct_F,
correct_P) in 0..16 x 0..16, each bound in the worst order found for it, once at pass-alpha 0.05
and once at 0.0209, whatever ``--pass-alpha`` says.

Run: PYTHONPATH=src python scripts/screens/419/v5_cue_stage1a.py --out DIR \
         --null-readout READOUT.json [--pass-alpha A] [--dry-run]
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cue_audit import FIXTURE_ROOT_DEFAULT, TRACE
from twin_digest import LIVE_IMAGE
from v4_cells import FULL_DIR_DEFAULT
from v5_cue_cells import build_cells

from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound
from skill_harness.subject import HarnessPin

EPOCHS_PER_ARM = 16
PER_SAMPLE_CAP = 0.30
HARD_CAP_USD = 2 * EPOCHS_PER_ARM * PER_SAMPLE_CAP
MODEL = "anthropic/claude-sonnet-5"
RETRY_UNCAUGHT_ERRORS = 1
ALPHA = 0.05
BOUNDARY = 0.20
LEDGER_PASS_ALPHA = 0.0209
DRY_RUN_SHUFFLES = 24
DRY_RUN_SEED = 649

Outcome = Literal["CUT_NO_LIFT", "A_PASSES_EARLY", "UNRESOLVED_CONTINUE"]
Side = Literal["lower", "upper"]


def stop_rule(*, ub_fp: float, lb_fp: float, lb_fn: float) -> Outcome:
    """The registered Stage 1A rule. ``ub_fp`` is at alpha 0.05; the two lower bounds are at
    the pass alpha."""
    if ub_fp < BOUNDARY:
        return "CUT_NO_LIFT"
    if lb_fp >= BOUNDARY and lb_fn >= BOUNDARY:
        return "A_PASSES_EARLY"
    return "UNRESOLVED_CONTINUE"


def pass_test_name(pass_alpha: float) -> str:
    return (
        f"card-level p = max(p_FN, p_FP) <= {pass_alpha} against H0: d <= {BOUNDARY}, "
        f"tested as both one-sided lower bounds at level {pass_alpha} clearing {BOUNDARY}"
    )


@cache
def _bound(xs: tuple[float, ...], alpha: float, side: Side) -> float:
    return one_sided_betting_bound(xs, alpha=alpha, side=side)


def fp_bounds(xs: Sequence[float], *, pass_alpha: float) -> tuple[float, float]:
    """(LB at pass-alpha, UB at 0.05) of F - P on the d scale, from paired x values."""
    key = tuple(xs)
    return 2 * _bound(key, pass_alpha, "lower") - 1, 2 * _bound(key, ALPHA, "upper") - 1


def pair_by_launch(
    full: dict[int, int], placebo: dict[int, int]
) -> tuple[list[int], tuple[float, ...]]:
    """Pair by epoch number. Returns the pairing keys and x = (F - P + 1) / 2 in key order."""
    keys = sorted(full.keys() & placebo.keys())
    return keys, tuple((full[k] - placebo[k] + 1) / 2 for k in keys)


def _fewest_ties(correct_f: int, correct_p: int, n: int) -> dict[float, int]:
    """The F - P pairing with the most disagreements, which gives the widest interval."""
    wins = min(correct_f, n - correct_p)
    losses = wins - (correct_f - correct_p)
    return {1.0: wins, 0.0: losses, 0.5: n - wins - losses}


def _search_orders(
    counts: dict[float, int], shuffles: int, seed: int
) -> Iterator[tuple[float, ...]]:
    """Every block order of the counts, then ``shuffles`` seeded shuffles."""
    for block in itertools.permutations(counts):
        yield tuple(v for v in block for _ in range(counts[v]))
    pool = [v for v, k in counts.items() for _ in range(k)]
    rng = random.Random(seed)  # noqa: S311 - a reproducible order search, not a secret
    for _ in range(shuffles):
        rng.shuffle(pool)
        yield tuple(pool)


def _placements(n: int, correct: int) -> Iterator[tuple[float, ...]]:
    for bits in itertools.product((0.0, 1.0), repeat=n):
        if sum(bits) == correct:
            yield bits


def worst_fp(
    correct_f: int, correct_p: int, *, n: int, pass_alpha: float, shuffles: int, seed: int
) -> tuple[float, float]:
    """The lowest LB and the highest UB of F - P over the searched orders of the fewest-ties
    pairing. Not an exhaustive search over every order."""
    orders = _search_orders(_fewest_ties(correct_f, correct_p, n), shuffles, seed)
    bounds = [fp_bounds(xs, pass_alpha=pass_alpha) for xs in orders]
    return min(lo for lo, _ in bounds), max(hi for _, hi in bounds)


def worst_fn(
    correct_f: int,
    *,
    n: int,
    null_correct: int,
    n_null: int,
    pass_alpha: float,
    shuffles: int,
    seed: int,
) -> float:
    """The lowest LB(F - N): Full over the searched orders, Null over every placement."""
    half = pass_alpha / 2
    full_orders = _search_orders({1.0: correct_f, 0.0: n - correct_f}, shuffles, seed)
    lb_f = min(_bound(xs, half, "lower") for xs in full_orders)
    ub_n = max(_bound(bits, half, "upper") for bits in _placements(n_null, null_correct))
    return lb_f - ub_n


@dataclass(frozen=True)
class TableCell:
    correct_f: int
    correct_p: int
    ub_fp: float
    lb_fp: float
    lb_fn: float
    outcome: Outcome


def operating_table(
    *,
    null_correct: int,
    n_null: int,
    pass_alpha: float,
    n: int = EPOCHS_PER_ARM,
    shuffles: int = DRY_RUN_SHUFFLES,
    seed: int = DRY_RUN_SEED,
) -> list[TableCell]:
    """Every (correct_F, correct_P) outcome, each bound at its own worst case."""
    search: dict[str, Any] = {"n": n, "pass_alpha": pass_alpha, "shuffles": shuffles, "seed": seed}
    lb_fn = {
        cf: worst_fn(cf, null_correct=null_correct, n_null=n_null, **search) for cf in range(n + 1)
    }
    cells: list[TableCell] = []
    for cf, cp in itertools.product(range(n + 1), repeat=2):
        lb, ub = worst_fp(cf, cp, **search)
        outcome = stop_rule(ub_fp=ub, lb_fp=lb, lb_fn=lb_fn[cf])
        cells.append(TableCell(cf, cp, ub, lb, lb_fn[cf], outcome))
    return cells


def render_table(cells: Sequence[TableCell], *, pass_alpha: float, n_null: int) -> str:
    lines = [
        f"=== OPERATING TABLE at pass-alpha {pass_alpha} (UB(F-P) one-sided at alpha {ALPHA}; "
        f"boundary {BOUNDARY}) ===",
        "pass = " + pass_test_name(pass_alpha),
        "correct_F correct_P  UB(F-P)  LB(F-P)  LB(F-N)  outcome",
    ]
    lines += [
        f"{c.correct_f:9d} {c.correct_p:9d}  {c.ub_fp:7.3f}  {c.lb_fp:7.3f}  {c.lb_fn:7.3f}  "
        f"{c.outcome}"
        for c in cells
    ]
    lines.append(
        f"LB(F-N) = LB(mu_F) - UB(mu_N), each one-sided at {pass_alpha / 2}, "
        f"{EPOCHS_PER_ARM} Full against {n_null} Null-A, worst order:"
    )
    seen: dict[int, float] = {c.correct_f: c.lb_fn for c in cells}
    lines += [f"  correct_F={cf:2d}  LB(F-N)={lb:7.3f}" for cf, lb in sorted(seen.items())]
    lines += _summary_lines(cells)
    return "\n".join(lines)


def _summary_lines(cells: Sequence[TableCell]) -> list[str]:
    def listed(pred: Any) -> str:
        found = [f"({c.correct_f},{c.correct_p})" for c in cells if pred(c)]
        return " ".join(found) if found else "none"

    fn_min = [c.correct_f for c in cells if c.lb_fn >= BOUNDARY]
    return [
        f"cells: {len(cells)}",
        "CUT_NO_LIFT: " + listed(lambda c: c.outcome == "CUT_NO_LIFT"),
        "A_PASSES_EARLY: " + listed(lambda c: c.outcome == "A_PASSES_EARLY"),
        "LB(F-P) >= boundary (the F-P half of the pass): " + listed(lambda c: c.lb_fp >= BOUNDARY),
        "minimum correct_F with LB(F-N) >= boundary: " + (str(min(fn_min)) if fn_min else "none"),
    ]


@dataclass(frozen=True)
class NullA:
    outcomes: tuple[int, ...] | None
    correct: int
    n: int


def load_null_a(path: Path) -> NullA:
    """Valid Null-A outcomes in epoch order, or counts only when the read-out has no rows."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [
        r
        for r in data.get("rows", [])
        if r["arm"] == "null" and r["world"] == "a" and not r["void"]
    ]
    summary = data["summary"]["null/a"]
    if not rows:
        return NullA(outcomes=None, correct=int(summary["correct"]), n=int(summary["n"]))
    rows.sort(key=lambda r: int(r["epoch"]))
    outcomes = tuple(int(bool(r["final_world_correct"])) for r in rows)
    if len(outcomes) != summary["n"] or sum(outcomes) != summary["correct"]:
        raise ValueError(f"{path}: Null-A rows disagree with the summary")
    return NullA(outcomes=outcomes, correct=sum(outcomes), n=len(outcomes))


def null_upper(null_a: NullA, alpha: float) -> tuple[float, str]:
    """UB(mu_N) at ``alpha``: epoch order when read, else the worst placement of the counts."""
    if null_a.outcomes is not None:
        return _bound(tuple(map(float, null_a.outcomes)), alpha, "upper"), "Null-A in epoch order"
    worst = max(_bound(bits, alpha, "upper") for bits in _placements(null_a.n, null_a.correct))
    return worst, "counts only: Null-A outcomes placed in the worst order for the bound"


def stage1a_tasks(compose_dir: Path) -> tuple[HarnessPin, list[Any]]:
    """Return the pin and the two A tasks, Full first. Nothing is evaluated."""
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
        epochs=EPOCHS_PER_ARM,
        compose_dir=compose_dir,
        retry_uncaught_errors=RETRY_UNCAUGHT_ERRORS,
    )
    return pin, [cells[("full", "a")], cells[("placebo", "a")]]


def _manifest_reads(log_dir: Path) -> dict[tuple[str, int], bool]:
    """(arm, epoch) -> whether any tool call named the trace file."""
    from inspect_ai.log import read_eval_log

    found: dict[tuple[str, int], bool] = {}
    for path in sorted(log_dir.glob("*.eval")):
        log = read_eval_log(str(path))
        arm = str((log.eval.metadata or {})["cell_arm"])
        for sample in log.samples or []:
            found[(arm, int(sample.epoch))] = any(
                TRACE in json.dumps(call.arguments)
                for message in sample.messages
                for call in getattr(message, "tool_calls", None) or []
            )
    return found


def read_stage1a(log_dir: Path, null_a: NullA, pass_alpha: float) -> dict[str, Any]:
    from twin_readout import read_rows

    rows = read_rows(log_dir)
    manifest = _manifest_reads(log_dir)
    arms: dict[str, Any] = {}
    outcomes: dict[str, dict[int, int]] = {}
    for arm in ("full", "placebo"):
        valid = sorted((r for r in rows if r.arm == arm and not r.void), key=lambda r: r.epoch)
        outcomes[arm] = {r.epoch: int(r.final_world_correct) for r in valid}
        arms[arm] = {
            "n": len(valid),
            "correct": sum(outcomes[arm].values()),
            "silent_violation": sum(r.silent_violation for r in valid),
            "no_publish": sum(r.no_publish for r in valid),
            "manifest_read": sum(manifest[(arm, r.epoch)] for r in valid),
        }
    keys, xs = pair_by_launch(outcomes["full"], outcomes["placebo"])
    lb_fp, ub_fp = fp_bounds(xs, pass_alpha=pass_alpha)
    full_stream = tuple(float(outcomes["full"][e]) for e in sorted(outcomes["full"]))
    lb_f = _bound(full_stream, pass_alpha / 2, "lower")
    ub_n, null_order = null_upper(null_a, pass_alpha / 2)
    return {
        "arms": arms,
        "null_a": {"n": null_a.n, "correct": null_a.correct, "order": null_order},
        "alpha": ALPHA,
        "pass_alpha": pass_alpha,
        "boundary": BOUNDARY,
        "pass_test": pass_test_name(pass_alpha),
        "pairing_key": "epoch number (launch index); a pair is dropped when either epoch is void",
        "pairs": keys,
        "f_minus_p": {"lb_at_pass_alpha": lb_fp, "ub_at_alpha": ub_fp, "n_pairs": len(keys)},
        "f_minus_n": {
            "lb_at_pass_alpha": lb_f - ub_n,
            "lb_mu_f": lb_f,
            "ub_mu_n": ub_n,
            "each_at": pass_alpha / 2,
            "n_full": len(full_stream),
            "n_null": null_a.n,
        },
        "outcome": stop_rule(ub_fp=ub_fp, lb_fp=lb_fp, lb_fn=lb_f - ub_n),
        "void_epochs": [f"{r.arm}/{r.world}#{r.epoch}" for r in rows if r.void],
        "total_usd": round(sum(r.usd for r in rows), 4),
    }


def dry_run(null_a: NullA) -> None:
    print(
        f"Null-A: {null_a.correct} correct of {null_a.n} valid "
        f"({'per-epoch order read' if null_a.outcomes is not None else 'counts only'}); "
        "the table uses counts only."
    )
    print(
        "F-P: launch-index pairs, the fewest-ties pairing in its 6 block orders plus "
        f"{DRY_RUN_SHUFFLES} shuffles (seed {DRY_RUN_SEED}); not an exhaustive order search. "
        "F-N: Full in its 2 block orders plus the same shuffles; Null over every placement."
    )
    for pass_alpha in (ALPHA, LEDGER_PASS_ALPHA):
        cells = operating_table(
            null_correct=null_a.correct,
            n_null=null_a.n,
            pass_alpha=pass_alpha,
            shuffles=DRY_RUN_SHUFFLES,
        )
        print(render_table(cells, pass_alpha=pass_alpha, n_null=null_a.n))
    print("DRY RUN: no model call.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--null-readout", type=Path, required=True)
    parser.add_argument("--pass-alpha", type=float, default=LEDGER_PASS_ALPHA)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    null_a = load_null_a(args.null_readout)
    from v5_cue_stage1 import _model_cost  # imports the [inspect] extra

    cost = _model_cost()
    pin, tasks = stage1a_tasks(Path(tempfile.mkdtemp(prefix="cue-stage1a-")))
    print("pin fingerprint:", pin.fingerprint(), "| image:", pin.sandbox_image)
    print(
        f"tasks={[t.name for t in tasks]} epochs/arm={EPOCHS_PER_ARM} model={MODEL} "
        f"per-sample cost_limit=${PER_SAMPLE_CAP:.3f} total cap=${HARD_CAP_USD:.2f} "
        f"retry_uncaught_errors={RETRY_UNCAUGHT_ERRORS} retry_on_error=0 "
        f"pass-alpha={args.pass_alpha}"
    )
    if args.dry_run:
        dry_run(null_a)
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
    readout = read_stage1a(args.out, null_a, args.pass_alpha)
    (args.out / "readout.json").write_text(json.dumps(readout, indent=2), encoding="utf-8")
    print(json.dumps(readout, indent=2))
    print("OUTCOME:", readout["outcome"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
