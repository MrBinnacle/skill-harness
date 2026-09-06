"""Reproduce the prototype's refused-path cand_bpB cells against the BUILT fit_skill.

Specification: docs/assurance/ebmom-peel-preregistration-amendment-v2.md section 3
(FROZEN 2026-09-05, S414). Reference implementation: the cand_bpB column of
rescore405.py in docs/assurance/reference/ebmom-class2-S414/, which computed form B
OUTSIDE production, on top of a frozen copy of fit.py. This script computes the same
cells from production itself.

Why the comparison is worth making. rescore405.py imports fit-branch.py, a vendored
copy of fit.py as it stood before form B was built, and applies form B in the harness.
The build moves form B INTO fit_skill. If the two disagree, the numbers v2 section 0
records were produced by a procedure production does not run, and every per-path rate
in that section is about something else. The comparison is a script rather than a
reading for the same reason: eyeballing four cells is how a disagreement in the fifth
survives.

What is compared. Per regime, per path, the false-PASS (5c) and false-FAIL (6c) cells:
the false count, the decision count, the cluster count G, and the false-bearing world
count g. Truth is the true encoded clause mean the generator returns and the v1 harness
discards.

NOT CONFIRMATORY. The default root is SMOKE_NOT_CONFIRMATORY, a development smoke, and
the expected file it is compared against was produced under that same root. Nothing
this script prints may be cited as a confirmatory result.

Usage:

    python scripts/ebmom_form_b_reproduction.py \
        --expected <path to proto-pb-all-R40-SMOKE_NO.json> \
        --replicates 40 \
        --regime low_heterogeneity --regime tie_heavy_null \
        --out docs/assurance/ebmom-form-b-reproduction-R40-SMOKE_NO.json

Exit code 0 when every compared cell agrees, 1 otherwise. ASCII only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

# scripts/ is not a package. Run as `python scripts/ebmom_form_b_reproduction.py`,
# which puts this directory on sys.path[0] and resolves the harness beside it.
from ebmom_acceptance_matrix import (
    REGIMES,
    WIN_RATE_THRESHOLD,
    Regime,
    decision,
    derive_seed,
    draw_world,
)

from skill_harness.aggregation.fit import fit_skill

DEFAULT_ROOT = "SMOKE_NOT_CONFIRMATORY"

# The column of the prototype dumps this script reproduces. cand_bpB is form B:
# the admitted path as the branch already had it, and on refusal the bounded
# pooling at the admission test's own critical order statistic.
EXPECTED_COLUMN = "cand_bpB"

# The four fields compared per cell. The p-value and the pass/fail flag are
# derived from these, so comparing the counts compares everything that is not a
# restatement.
COMPARED_FIELDS = ("count", "of", "worlds", "false_worlds")


class Cells:
    """Per-path false-decision tallies for one regime, as rescore405.py counts them.

    A world is one cluster. `worlds` counts the distinct replicates that
    contributed a decision of the kind, and `false_worlds` the distinct
    replicates that contributed a FALSE one, because a cell of four decisions
    drawn from one world is not four independent observations.
    """

    def __init__(self) -> None:
        self.pass_n = {"admitted": 0, "refused": 0}
        self.pass_false = {"admitted": 0, "refused": 0}
        self.fail_n = {"admitted": 0, "refused": 0}
        self.fail_false = {"admitted": 0, "refused": 0}
        self.pass_worlds: dict[str, set[int]] = {"admitted": set(), "refused": set()}
        self.fail_worlds: dict[str, set[int]] = {"admitted": set(), "refused": set()}
        self.pass_false_worlds: dict[str, set[int]] = {"admitted": set(), "refused": set()}
        self.fail_false_worlds: dict[str, set[int]] = {"admitted": set(), "refused": set()}

    def add(self, decisions: list[str], truths: list[float], path: str, world: int) -> None:
        for verdict, truth in zip(decisions, truths, strict=True):
            if verdict == "PASS":
                self.pass_n[path] += 1
                self.pass_worlds[path].add(world)
                if truth <= WIN_RATE_THRESHOLD:
                    self.pass_false[path] += 1
                    self.pass_false_worlds[path].add(world)
            elif verdict == "FAIL":
                self.fail_n[path] += 1
                self.fail_worlds[path].add(world)
                if truth > WIN_RATE_THRESHOLD:
                    self.fail_false[path] += 1
                    self.fail_false_worlds[path].add(world)

    def rows(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for path in ("admitted", "refused"):
            out[f"row5c_false_pass_{path}"] = {
                "count": self.pass_false[path],
                "of": self.pass_n[path],
                "worlds": len(self.pass_worlds[path]),
                "false_worlds": len(self.pass_false_worlds[path]),
            }
            out[f"row6c_false_fail_{path}"] = {
                "count": self.fail_false[path],
                "of": self.fail_n[path],
                "worlds": len(self.fail_worlds[path]),
                "false_worlds": len(self.fail_false_worlds[path]),
            }
        return out


def score_regime(regime: Regime, replicates: int, root: str) -> tuple[dict[str, object], int, int]:
    """Score one regime with the BUILT fit_skill. Returns (rows, admitted, reverts)."""
    cells = Cells()
    admitted = 0
    reverts = 0
    for world in range(replicates):
        clauses, truths = draw_world(regime, derive_seed(root, regime.name, world))
        result = fit_skill(clauses)
        is_admitted = result.aggregation_method == "ebmom_hierarchical"
        if is_admitted:
            admitted += 1
        else:
            pooling = result.aggregation_provenance.get("bounded_pooling", {})
            reverts += int(pooling.get("unpooled_revert_count", 0))
        decisions = [decision(post.p_win_gt_threshold) for post in result.posteriors]
        cells.add(decisions, truths, "admitted" if is_admitted else "refused", world)
    return dict(cells.rows()), admitted, reverts


def compare(built: dict[str, object], expected_regime: dict[str, object]) -> list[str]:
    """Return one line per differing cell. An empty list is agreement."""
    expected_cells = expected_regime["estimators"][EXPECTED_COLUMN]
    differences: list[str] = []
    for row_name, got in built.items():
        want = expected_cells.get(row_name)
        if want is None:
            differences.append(f"{row_name}: absent from the expected file")
            continue
        for field in COMPARED_FIELDS:
            if got[field] != want[field]:
                differences.append(f"{row_name}.{field}: built={got[field]} expected={want[field]}")
    return differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reproduce cand_bpB cells from production.")
    parser.add_argument(
        "--expected",
        required=True,
        help="prototype dump to compare against (proto-pb-all-R<N>-<root>.json)",
    )
    parser.add_argument("--replicates", type=int, default=40)
    parser.add_argument("--root-seed", default=DEFAULT_ROOT)
    parser.add_argument(
        "--regime",
        action="append",
        default=None,
        help="regime to score; repeatable. Default: every registered regime.",
    )
    parser.add_argument("--out", default="-")
    args = parser.parse_args(argv)

    expected_path = Path(args.expected)
    expected_bytes = expected_path.read_bytes()
    expected = json.loads(expected_bytes.decode("utf-8"))

    if expected.get("root_seed") != args.root_seed:
        print(
            "REFUSE: the expected file was produced under root "
            f"{expected.get('root_seed')!r}, not {args.root_seed!r}. Comparing cells "
            "across roots compares two different sets of worlds.",
            file=sys.stderr,
        )
        return 1
    if expected.get("replicates") != args.replicates:
        print(
            f"REFUSE: the expected file has R={expected.get('replicates')!r}, "
            f"not {args.replicates!r}.",
            file=sys.stderr,
        )
        return 1

    wanted = args.regime or [r.name for r in REGIMES]
    report: dict[str, object] = {
        "root_seed": args.root_seed,
        "replicates": args.replicates,
        "is_confirmatory": False,
        "expected_file": expected_path.name,
        "expected_sha256": hashlib.sha256(expected_bytes).hexdigest(),
        "expected_column": EXPECTED_COLUMN,
        "compared_fields": list(COMPARED_FIELDS),
        "python": sys.version.split()[0],
        "regimes": {},
    }

    total_differences = 0
    for regime in REGIMES:
        if regime.name not in wanted:
            continue
        started = time.time()
        rows, admitted, reverts = score_regime(regime, args.replicates, args.root_seed)
        differences = compare(rows, expected["regimes"][regime.name])
        total_differences += len(differences)
        report["regimes"][regime.name] = {
            "built": rows,
            "admitted": admitted,
            "unpooled_reverts": reverts,
            "differences": differences,
            "agrees": not differences,
        }
        # Wall time goes to stdout, never into the JSON: a committed receipt has
        # to be byte-reproducible from the same tree, and a timing field makes
        # every re-run differ for a reason that is not about the measurement.
        print(f"   scored in {time.time() - started:.0f}s", flush=True)
        status = "AGREES" if not differences else f"{len(differences)} DIFFER"
        print(f"[{regime.name}] admitted {admitted}/{args.replicates}  {status}", flush=True)
        for row_name, row in rows.items():
            print(
                f"   {row_name:28s} {row['count']:>6}/{row['of']:<7}"
                f"(worlds {row['false_worlds']}/{row['worlds']})",
                flush=True,
            )
        for line in differences:
            print(f"   DIFF {line}", flush=True)

    report["total_differences"] = total_differences
    report["reproduces"] = total_differences == 0

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out == "-":
        print(payload)
    else:
        Path(args.out).write_text(payload + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")

    if total_differences:
        print(f"REFUSE: {total_differences} cell(s) differ from {expected_path.name}")
        return 1
    print(f"reproduces {expected_path.name} on {len(wanted)} regime(s), column {EXPECTED_COLUMN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
