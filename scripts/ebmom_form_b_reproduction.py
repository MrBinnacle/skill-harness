"""Reproduce a prototype column's per-path cells against the BUILT fit_skill.

Specification: docs/assurance/ebmom-peel-preregistration-amendment-v2.md sections 3
and 4 (FROZEN 2026-09-05, S414). Reference implementation: the prototype columns of
rescore405.py and proto_pb.py in docs/assurance/reference/ebmom-class2-S414/, which
computed both the refused-path form and the admitted-path mechanism OUTSIDE
production, on top of a frozen copy of fit.py. This script computes the same cells
from production itself.

Why the comparison is worth making. The prototypes import fit-branch.py, a vendored
copy of fit.py as it stood before either was built, and apply the estimator in the
harness. The build moves the estimator INTO fit_skill. If the two disagree, the
numbers v2 section 0 records were produced by a procedure production does not run,
and every per-path rate in that section is about something else. The comparison is a
script rather than a reading for the same reason: eyeballing four cells is how a
disagreement in the fifth survives.

A caveat that belongs on the admitted-path column and not on the refused one. The
prototype seeds its draws from the world it drew (`<root>|<regime>|<world>|pb`) and
fit_skill cannot: it sees clauses and nothing else, so the frozen derivation gives it
`<canonical clause encoding>|pb`. The two are different integers and draw different
streams, so the admitted-path cells are reproduced up to Monte Carlo error in the
DECISIONS, not bit for bit in the probabilities. A disagreement in an admitted cell is
therefore a finding to read, not automatically a defect; the bit-level identity of the
mechanism is pinned separately, under the prototype's own seed, in
tests/test_aggregation_fit_admitted_bootstrap.py.

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
        --column cand_bpB \
        --out docs/assurance/ebmom-form-b-reproduction-R40-SMOKE_NO.json

The column defaults to cand_bpB so the receipt already committed under that name
reproduces from the same command line it was generated with.

Exit code 0 when every compared cell agrees, 1 otherwise. ASCII only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, cast

# scripts/ is not a package. Run as `python scripts/ebmom_form_b_reproduction.py`,
# which puts this directory on sys.path[0] and resolves the harness beside it.
from ebmom_acceptance_matrix import (
    FAIL_P,
    PASS_P,
    REGIMES,
    V2_CANDIDATE_COLUMN,
    V2_COLUMNS,
    V2_PATHS,
    V2_ROWS,
    WIN_RATE_THRESHOLD,
    Regime,
    decision,
    derive_seed,
    draw_world,
    oracle_self_check,
    score_regime_v2,
    v2_regime_report,
)

from skill_harness.aggregation import fit as fit_module
from skill_harness.aggregation.fit import ClauseObservations, fit_skill

DEFAULT_ROOT = "SMOKE_NOT_CONFIRMATORY"

# The column of the prototype dumps this script reproduces. cand_bpB is form B:
# the admitted path as the branch already had it, and on refusal the bounded
# pooling at the admission test's own critical order statistic.
DEFAULT_COLUMN = "cand_bpB"

# The columns this script knows how to reproduce from production, and what each
# one means. A free-text column name is refused rather than compared: a typo
# would otherwise read as "absent from the expected file" on every row and be
# reported as a disagreement about the numbers.
COLUMNS: dict[str, str] = {
    # Form B on refusal, admitted path on the plug-in. The column production
    # reproduced when the refused path landed (#441).
    "cand_bpB": "form B on refusal, plug-in on the admitted path",
    # Form B on refusal, mechanism class 2 on the admitted path. The candidate
    # v2 section 4 freezes (#442). The refused-path cells of the two columns are
    # identical BY CONSTRUCTION -- the mechanism is admitted-path-only -- so a
    # run of this column that reproduces the refused cells as well as the
    # admitted ones is also the evidence that the admitted-path work left the
    # refused path alone.
    "cand_pb": "form B on refusal, admission-conditioned bootstrap on the admitted path",
}

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


class PrototypeSeed:
    """DIAGNOSTIC ONLY: drive production's draws from the PROTOTYPE's seed.

    Not a configuration, and never a production path. proto_pb.py seeds its
    draws from `<root>|<regime>|<world>|pb`, which a harness can compute because
    it knows which world it drew. fit_skill cannot: it sees clauses and nothing
    else, so the frozen derivation gives it `<canonical clause encoding>|pb`.
    The two are different integers, so the admitted-path cells of a production
    run and of the prototype differ by Monte Carlo error even when the mechanism
    is identical.

    That leaves a question a plain comparison cannot answer: is a differing cell
    the seed, or the port? Installing this makes production consume the
    prototype's stream, so a run that AGREES under it and disagrees without it
    has isolated the seed as the whole of the difference. The receipt records
    which mode produced it, because the two are not the same claim: only the
    unpatched run says anything about the code that ships.
    """

    def __init__(self, root: str, regime_name: str) -> None:
        self.root = root
        self.regime_name = regime_name
        self.world = 0

    def set_world(self, world: int) -> None:
        """Point the seeder at the world about to be scored.

        The world is not derivable from the clauses, which is the whole reason
        the two seeds differ, so the caller has to say which world it drew
        before the fit runs.
        """
        self.world = world

    def __call__(self, _clauses: list[ClauseObservations]) -> int:
        material = f"{self.root}|{self.regime_name}|{self.world}|pb"
        return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")


def score_regime(
    regime: Regime, replicates: int, root: str, prototype_seed: bool = False
) -> tuple[dict[str, object], int, int]:
    """Score one regime with the BUILT fit_skill. Returns (rows, admitted, reverts)."""
    cells = Cells()
    seeder = PrototypeSeed(root, regime.name) if prototype_seed else None
    original_seeder = fit_module._admitted_bootstrap_seed
    try:
        if seeder is not None:
            fit_module._admitted_bootstrap_seed = seeder  # type: ignore[assignment]
        return _score_worlds(regime, replicates, root, cells, seeder)
    finally:
        fit_module._admitted_bootstrap_seed = original_seeder  # type: ignore[assignment]


def _score_worlds(
    regime: Regime,
    replicates: int,
    root: str,
    cells: Cells,
    seeder: PrototypeSeed | None,
) -> tuple[dict[str, object], int, int]:
    admitted = 0
    reverts = 0
    for world in range(replicates):
        if seeder is not None:
            seeder.world = world
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


def compare(built: dict[str, object], expected_regime: dict[str, object], column: str) -> list[str]:
    """Return one line per differing cell. An empty list is agreement."""
    expected_cells = expected_regime["estimators"][column]
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


# --- the v2 reproduction: parts (a), (b) and (c) of the S417 amendment -------
#
# Amendment of record: skill-harness#442, the S417 comment, and the "Ruled
# S417" paragraph at the end of v2 section 9. For every reproduction against a
# prototype dump:
#
#   (a) PORT IDENTITY, FROZEN. Under --prototype-seed production reproduces the
#       dump with zero differing cells. One differing cell is a port defect.
#   (b) PRODUCTION-SEED REPORT, required and reported, never a kill. The cells
#       under the seed production is obliged to use, beside the dump, with every
#       differing cell listed and its direction, and the per-clause flip listing
#       at that R.
#   (c) THE FREEZE CONDITION of v2 section 4, evaluated once under the
#       production seed on the same pre-committed worlds, with section 4's own
#       consequence and no new one. A rejection is REPORTED with its cell, G and
#       g; this script does not decide its consequence.
#
# Why (a) and (b) are two different claims and not one softened claim. The
# prototype seeds each world's admitted-path draws from
# `<root>|<regime>|<world>|pb`, which a harness can compute because it knows
# which world it drew. `fit_skill` never receives the world and, under the
# frozen v1 section 3 rule, seeds from `<canonical clause encoding>|pb`.
# Different integers draw different streams, so a clause whose averaged tail
# sits near 0.05 or 0.95 lands on either side. (a) holds the stream fixed and
# therefore says something about the ARITHMETIC; (b) says what the code that
# ships actually does. Only (a) can be a kill, because only (a) is about the
# port.

FLIP_BAND = 0.03  # near-cut band the S417 flip diagnostic reports against

# Dump field -> cell field. The dumps name the four compared quantities as
# rescore405.py printed them; the harness names them as v2 section 2.2 does.
DUMP_FIELDS: dict[str, str] = {
    "count": "false",
    "of": "decisions",
    "worlds": "G",
    "false_worlds": "g",
}


class FlipRecorder:
    """Per-clause decisions under one seed, kept only for the admitted worlds.

    Refused worlds cannot flip: the admitted-path seed is the only thing that
    moves between the two runs and the refused path does not draw from it. The
    recorder asserts that rather than assuming it, by keeping the path it saw.
    """

    def __init__(self) -> None:
        self.tails: dict[int, list[float]] = {}
        self.paths: dict[int, str] = {}
        self.clause_ids: dict[int, list[str]] = {}
        self.truths: dict[int, list[float]] = {}

    def __call__(
        self,
        world: int,
        path: str,
        clauses: list[ClauseObservations],
        truths: list[float],
        tails: list[float],
    ) -> None:
        self.paths[world] = path
        if path != "admitted":
            return
        self.tails[world] = list(tails)
        self.clause_ids[world] = [clause.clause_id for clause in clauses]
        self.truths[world] = list(truths)


def flip_listing(production: FlipRecorder, prototype: FlipRecorder) -> dict[str, object]:
    """Every admitted clause whose DECISION differs between the two seeds.

    Reports both tails, the truth, and the clause's distance to the nearer cut
    under the production seed, which is the reading the cross-family seat asked
    for: a flip that sits at 0.0021 from a cut is the Monte Carlo error of an
    averaged tail landing on the other side, and a flip far from either cut
    would be a different finding entirely.
    """
    flips: list[dict[str, object]] = []
    near_cut = 0
    admitted_clauses = 0
    max_gap = 0.0
    for world in sorted(production.tails):
        if production.paths[world] != prototype.paths[world]:
            raise AssertionError(
                f"world {world} reached {production.paths[world]!r} under the production "
                f"seed and {prototype.paths[world]!r} under the prototype's. Admission "
                "must not depend on the admitted-path seed; the reproduction is invalid."
            )
        clause_ids = production.clause_ids[world]
        truths = production.truths[world]
        for clause_id, truth, production_tail, prototype_tail in zip(
            clause_ids, truths, production.tails[world], prototype.tails[world], strict=True
        ):
            admitted_clauses += 1
            max_gap = max(max_gap, abs(production_tail - prototype_tail))
            distance = min(abs(production_tail - FAIL_P), abs(production_tail - PASS_P))
            if distance <= FLIP_BAND:
                near_cut += 1
            production_decision = decision(production_tail)
            prototype_decision = decision(prototype_tail)
            if production_decision == prototype_decision:
                continue
            flips.append(
                {
                    "world": world,
                    "clause": clause_id,
                    "truth": round(float(truth), 4),
                    "truth_exceeds_threshold": bool(truth > WIN_RATE_THRESHOLD),
                    "production": {
                        "tail": round(production_tail, 6),
                        "decision": production_decision,
                    },
                    "prototype": {
                        "tail": round(prototype_tail, 6),
                        "decision": prototype_decision,
                    },
                    "distance_to_cut_production": round(distance, 6),
                }
            )
    return {
        "admitted_worlds": len(production.tails),
        "admitted_clauses": admitted_clauses,
        "near_cut_band": FLIP_BAND,
        "near_cut_clauses": near_cut,
        "flips": len(flips),
        "max_abs_tail_gap": round(max_gap, 6),
        "flip_detail": flips,
    }


# The per-clause flip table is the largest thing this script produces -- 2,836
# rows at R = 1000 -- and it lives in a SIDECAR file beside the report, for the
# same reason proto_pb.py keeps its per-world table out of its summary: a report
# a reader opens should not be mostly one table, and the repository's
# check-added-large-files hook refuses a 500 KB artefact. Rows rather than
# objects, with the field order declared once, is the encoding the prototype
# dumps already use.
FLIP_FIELDS: tuple[str, ...] = (
    "world",
    "clause",
    "truth",
    "truth_exceeds_threshold",
    "production_tail",
    "production_decision",
    "prototype_tail",
    "prototype_decision",
    "distance_to_cut_production",
)


def _flip_row(flip: dict[str, Any]) -> list[Any]:
    return [
        flip["world"],
        flip["clause"],
        flip["truth"],
        flip["truth_exceeds_threshold"],
        flip["production"]["tail"],
        flip["production"]["decision"],
        flip["prototype"]["tail"],
        flip["prototype"]["decision"],
        flip["distance_to_cut_production"],
    ]


def split_flip_details(report: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    """Move every regime's per-clause flip rows out of the report into a sidecar.

    Returns (report without the rows, sidecar document). The report keeps the
    whole aggregate -- flip count, admitted clauses, near-cut count, the band and
    the largest tail movement -- and gains the sidecar's filename, so nothing a
    reader needs in order to interpret part (b) leaves the report.

    A pure function of the report. That is what lets it be applied to a run's
    output after the fact and give exactly the bytes a fresh run would write.
    """
    regimes = cast("dict[str, dict[str, Any]]", report["regimes"])
    sidecar_regimes: dict[str, object] = {}
    for name, entry in regimes.items():
        listing = entry["production_seed"]["flip_listing"]
        detail = listing.pop("flip_detail", [])
        sidecar_regimes[name] = [_flip_row(flip) for flip in detail]
        listing["flip_rows_in_sidecar"] = len(detail)
    sidecar: dict[str, object] = {
        "root_seed": report["root_seed"],
        "replicates": report["replicates"],
        "is_confirmatory": False,
        "expected_file": report["expected_file"],
        "flip_fields": list(FLIP_FIELDS),
        "note": (
            "Every admitted clause whose DECISION differs between the production "
            "seed and the injected prototype seed. Part (b) of the S417 amendment; "
            "reported, never a kill."
        ),
        "regimes": sidecar_regimes,
    }
    return report, sidecar


def cells_against_dump(
    report: dict[str, object], expected_regime: dict[str, Any]
) -> tuple[dict[str, object], list[str]]:
    """Compare every column's per-path cells and the vs-oracle excesses against a dump.

    Returns (built cells keyed as the dump keys them, one line per difference).
    A difference line carries the DIRECTION as well as the two values, because
    "five cells differ" and "five cells differ by one decision each, all
    upward" are not the same finding.
    """
    built: dict[str, object] = {}
    differences: list[str] = []
    estimators = cast("dict[str, dict[str, Any]]", report["estimators"])
    for column in V2_COLUMNS:
        rows = estimators[column]
        expected_column = expected_regime["estimators"].get(column)
        column_cells: dict[str, object] = {}
        for path in (*V2_PATHS, "pooled"):
            for row in V2_ROWS:
                name = f"row{row}_{'false_pass' if row == '5c' else 'false_fail'}_{path}"
                cell = rows[name]
                column_cells[name] = {
                    dump_field: cell[cell_field] for dump_field, cell_field in DUMP_FIELDS.items()
                }
                if expected_column is None:
                    continue
                want = expected_column.get(name)
                if want is None:
                    differences.append(f"{column}.{name}: absent from the expected file")
                    continue
                for dump_field, cell_field in DUMP_FIELDS.items():
                    got = cell[cell_field]
                    if got != want[dump_field]:
                        direction = "+" if got > want[dump_field] else "-"
                        differences.append(
                            f"{column}.{name}.{dump_field}: built={got} "
                            f"expected={want[dump_field]} ({direction}"
                            f"{abs(got - want[dump_field])})"
                        )
        built[column] = column_cells

    excess = cast("dict[str, list[int]]", report["excess_over_main_vs_oracle"])
    expected_excess = expected_regime.get("excess_over_main_vs_oracle", {})
    for column in V2_COLUMNS:
        want_excess = expected_excess.get(column)
        if want_excess is None:
            continue
        if list(excess[column]) != list(want_excess):
            differences.append(
                f"{column}.excess_over_main_vs_oracle: built={excess[column]} "
                f"expected={list(want_excess)}"
            )
    if "admitted" in expected_regime and report["admitted"] != expected_regime["admitted"]:
        differences.append(
            f"admitted: built={report['admitted']} expected={expected_regime['admitted']}"
        )
    return built, differences


def freeze_condition(report: dict[str, object], world_range: tuple[int, int]) -> dict[str, object]:
    """Part (c): v2 section 4's condition on the pre-committed worlds, production seed.

    Reported, not decided. v2 section 4 owns the consequence of a rejection and
    section 9's S417 ruling says so in terms: a rejection here resumes section
    4's sequence; it is not a new kill and this script does not invent one.
    """
    cells: dict[str, object] = {}
    rejecting: list[str] = []
    estimators = cast("dict[str, dict[str, Any]]", report["estimators"])
    for column in V2_COLUMNS:
        for path in V2_PATHS:
            for row in V2_ROWS:
                name = f"row{row}_{'false_pass' if row == '5c' else 'false_fail'}_{path}"
                cell = estimators[column][name]
                cells[f"{column}.{name}"] = {
                    "false": cell["false"],
                    "decisions": cell["decisions"],
                    "G": cell["G"],
                    "g": cell["g"],
                    "selected_false": cell["selected_false"],
                    "rejects_at": cell.get("rejects_at"),
                    "p_value": cell["p_value"],
                    "testable": cell["testable"],
                    "verdict": (
                        "not testable"
                        if not cell["testable"]
                        else ("REJECTS" if cell["rejects"] else "passes")
                    ),
                    "world_block_bound": cell["world_block_bound"]["bound_lower_99"],
                }
                if column == V2_CANDIDATE_COLUMN and cell["rejects"]:
                    rejecting.append(name)
    return {
        "world_range": list(world_range),
        "seed_mode": "production",
        "cells": cells,
        "candidate_rejecting_cells": rejecting,
        "oracle_self_check": oracle_self_check([report]),
        "consequence": (
            "v2 section 4 owns the consequence. A rejection resumes that section's "
            "sequence; it is not a new kill and nothing here decides it."
        ),
    }


def run_v2_reproduction(
    expected_path: Path,
    root_seed: str,
    replicates: int,
    regimes: list[str],
    freeze_range: tuple[int, int] | None,
) -> dict[str, object]:
    """Score every wanted regime twice and assemble parts (a), (b) and (c)."""
    expected_bytes = expected_path.read_bytes()
    expected = json.loads(expected_bytes.decode("utf-8"))
    if expected.get("root_seed") != root_seed:
        raise SystemExit(
            f"REFUSE: {expected_path.name} was produced under root "
            f"{expected.get('root_seed')!r}, not {root_seed!r}. Comparing cells across "
            "roots compares two different sets of worlds."
        )
    if expected.get("replicates") != replicates:
        raise SystemExit(
            f"REFUSE: {expected_path.name} has R={expected.get('replicates')!r}, "
            f"not {replicates!r}."
        )

    report: dict[str, object] = {
        "specification": "docs/assurance/ebmom-peel-preregistration-amendment-v2.md",
        "amendment_of_record": "skill-harness#442, the S417 comment; v2 section 9",
        "root_seed": root_seed,
        "replicates": replicates,
        "is_confirmatory": False,
        "expected_file": expected_path.name,
        "expected_sha256": hashlib.sha256(expected_bytes).hexdigest(),
        "compared_fields": sorted(DUMP_FIELDS),
        "python": sys.version.split()[0],
        "regimes": {},
    }

    port_differences = 0
    production_differences = 0
    for regime in REGIMES:
        if regime.name not in regimes:
            continue
        started = time.time()
        production_flips = FlipRecorder()
        production_scored = score_regime_v2(
            regime, root_seed, replicates, after_world=production_flips
        )
        production_report = v2_regime_report(production_scored)

        seeder = PrototypeSeed(root_seed, regime.name)
        prototype_flips = FlipRecorder()
        original = fit_module._admitted_bootstrap_seed
        try:
            fit_module._admitted_bootstrap_seed = seeder  # type: ignore[assignment]
            prototype_scored = score_regime_v2(
                regime,
                root_seed,
                replicates,
                before_world=seeder.set_world,
                after_world=prototype_flips,
            )
        finally:
            fit_module._admitted_bootstrap_seed = original  # type: ignore[assignment]
        prototype_report = v2_regime_report(prototype_scored)

        expected_regime = expected["regimes"][regime.name]
        port_cells, port_diffs = cells_against_dump(prototype_report, expected_regime)
        production_cells, production_diffs = cells_against_dump(production_report, expected_regime)
        port_differences += len(port_diffs)
        production_differences += len(production_diffs)

        # Wall time goes to stdout, never into the JSON: a committed receipt has
        # to be byte-reproducible from the same tree, and a timing field makes
        # every re-run differ for a reason that is not about the measurement.
        # The v1 single-column path in main() carries the same comment verbatim
        # and has always obeyed it; #452 is where v2 had regressed it, with the
        # rule and its violation twelve lines apart in one file.
        # tests/test_ebmom_reproduction_receipt_determinism.py now enforces it,
        # because stating it only as a comment is what let the regression
        # through.
        elapsed = time.time() - started

        entry: dict[str, object] = {
            "port_identity_prototype_seed": {
                "cells": port_cells,
                "differences": port_diffs,
                "reproduces": not port_diffs,
            },
            "production_seed": {
                "cells": production_cells,
                "differences": production_diffs,
                "agrees_with_dump": not production_diffs,
                "flip_listing": flip_listing(production_flips, prototype_flips),
            },
            "acceptance_matrix_production_seed": production_report,
        }
        if freeze_range is not None:
            low, high = freeze_range
            if low >= replicates:
                entry["freeze_condition"] = {
                    "world_range": [low, high],
                    "note": (
                        f"the range starts at world {low} and this run scored "
                        f"{replicates}; the condition is not evaluated here"
                    ),
                }
            else:
                entry["freeze_condition"] = freeze_condition(
                    v2_regime_report(production_scored, low, min(high, replicates)),
                    (low, min(high, replicates)),
                )
        cast("dict[str, object]", report["regimes"])[regime.name] = entry

        print(
            f"[{regime.name}] admitted {production_scored.admitted}/{replicates} "
            f"in {elapsed:.1f}s  port diffs {len(port_diffs)}  "
            f"production diffs {len(production_diffs)}",
            flush=True,
        )
        for line in port_diffs:
            print(f"   PORT DIFF {line}", flush=True)
        for line in production_diffs:
            print(f"   PRODUCTION-SEED DIFF {line}", flush=True)

    report["port_identity_differences"] = port_differences
    report["port_identity_holds"] = port_differences == 0
    report["production_seed_differences"] = production_differences
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reproduce a prototype column from production.")
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
    parser.add_argument(
        "--prototype-seed",
        action="store_true",
        help=(
            "DIAGNOSTIC: drive the admitted-path draws from the prototype's seed "
            "instead of production's. Isolates a differing admitted cell as seed "
            "rather than port. A run under this flag says nothing about the code "
            "that ships and the receipt records that it was used."
        ),
    )
    parser.add_argument(
        "--column",
        default=DEFAULT_COLUMN,
        choices=sorted(COLUMNS),
        help="prototype column to reproduce; see COLUMNS for what each one is.",
    )
    parser.add_argument(
        "--v2",
        action="store_true",
        help=(
            "run the full v2 reproduction instead of the single-column compare: "
            "every column's per-path cells under BOTH seeds, the flip listing, "
            "and the freeze condition. Parts (a), (b) and (c) of the S417 "
            "amendment. Exit code 0 when part (a) holds, 1 otherwise -- (b) and "
            "(c) are reported and never gate the exit code."
        ),
    )
    parser.add_argument(
        "--freeze-range",
        default=None,
        help=(
            "LO:HI, half-open, absolute world numbers. Part (c) of the S417 "
            "amendment: 500:1000 for a R = 1000 run, 1000:4000 for the "
            "low_heterogeneity R = 4000 run. --v2 only."
        ),
    )
    args = parser.parse_args(argv)

    if args.v2:
        return _main_v2(args)

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
        "prototype_seed_injected": bool(args.prototype_seed),
        "expected_column": args.column,
        "expected_column_meaning": COLUMNS[args.column],
        "compared_fields": list(COMPARED_FIELDS),
        "python": sys.version.split()[0],
        "regimes": {},
    }

    total_differences = 0
    for regime in REGIMES:
        if regime.name not in wanted:
            continue
        started = time.time()
        rows, admitted, reverts = score_regime(
            regime, args.replicates, args.root_seed, prototype_seed=args.prototype_seed
        )
        differences = compare(rows, expected["regimes"][regime.name], args.column)
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
    print(f"reproduces {expected_path.name} on {len(wanted)} regime(s), column {args.column}")
    return 0


def _main_v2(args: argparse.Namespace) -> int:
    """Parts (a), (b) and (c) against one prototype dump.

    The exit code carries part (a) and nothing else. (b) is required and
    reported and is never a kill, and (c)'s consequence belongs to v2 section 4;
    folding either into the exit code would turn a reported finding into a gate
    the amendment does not authorise.
    """
    freeze_range: tuple[int, int] | None = None
    if args.freeze_range is not None:
        low, high = (int(part) for part in args.freeze_range.split(":"))
        freeze_range = (low, high)

    report = run_v2_reproduction(
        expected_path=Path(args.expected),
        root_seed=args.root_seed,
        replicates=args.replicates,
        regimes=args.regime or [regime.name for regime in REGIMES],
        freeze_range=freeze_range,
    )

    report, sidecar = split_flip_details(report)
    if args.out != "-":
        sidecar_path = Path(args.out).with_name(Path(args.out).stem + "-flips.json")
        report["flip_detail_file"] = sidecar_path.name
        sidecar_path.write_text(
            json.dumps(sidecar, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {sidecar_path}")

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out == "-":
        print(payload)
    else:
        Path(args.out).write_text(payload + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")

    if not report["port_identity_holds"]:
        print(
            f"REFUSE: part (a) failed. {report['port_identity_differences']} cell(s) "
            f"differ from {report['expected_file']} under the injected prototype seed. "
            "That is a PORT DEFECT, not a seed difference."
        )
        return 1
    print(
        f"part (a) holds: zero differing cells against {report['expected_file']} under "
        f"the injected prototype seed. Part (b) reports "
        f"{report['production_seed_differences']} differing cell(s) under the "
        "production seed, which is reported and is not a kill."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
