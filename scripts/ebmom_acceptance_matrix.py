"""Acceptance-matrix harness for the EB-MoM peel and heterogeneity gate (#360).

Runs the frozen acceptance matrix in
``docs/assurance/ebmom-peel-preregistration-amendment.md`` section 5.

The harness derives EVERY regime seed and replicate seed from a single root
seed supplied on the command line. It refuses to invent one. That is the whole
control: the session that wrote the specification and built this file does not
choose the confirmatory worlds, so it cannot have tuned anything to them.

    python scripts/ebmom_acceptance_matrix.py --root-seed <64 hex chars>

Baseline and candidate are evaluated on the SAME generated worlds, world for
world, so rows 5 and 6 are paired differences on identical inputs rather than
two independent samples.

ASCII only, per the repository's cp1252 console constraint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]
from scipy.stats import binomtest

from skill_harness.aggregation.fit import (
    HETEROGENEITY_TEST_ALPHA,
    VAR_FLOOR,
    WIN_RATE_THRESHOLD,
    ClauseObservations,
    fit_skill,
)
from skill_harness.aggregation.fit import _decompose as decompose

# --- frozen protocol constants (amendment sections 4, 5, 7) -----------------

R_REPLICATES = 1000
PASS_P = 0.95
FAIL_P = 0.05
BIAS_TOL = 0.10  # absolute relative bias bound, nonzero-variance regimes
CALIBRATION_TEST_LEVEL = 0.01  # exact binomial test level for row 1


@dataclass(frozen=True)
class Regime:
    """One registered synthetic world.

    tie_rate = 0 means a tie-free (Bernoulli) regime, where the hyperprior is
    Beta(a_true, b_true) on the clause rate directly.

    tie_rate > 0 means the encoded observation is 0.5 with that probability and
    otherwise decisive at p_k ~ Beta(a_true, b_true). The encoded clause mean is
    then tie_rate/2 + (1 - tie_rate) * p_k, whose variance is
    (1 - tie_rate)^2 * Var(p_k).
    """

    name: str
    a_true: float
    b_true: float
    n_trials: int
    k_clauses: int
    tie_rate: float = 0.0
    homogeneous_p: float | None = None  # set for the null regime

    @property
    def encoded_mean(self) -> float:
        if self.homogeneous_p is not None:
            return self.tie_rate * 0.5 + (1.0 - self.tie_rate) * self.homogeneous_p
        p_mean = self.a_true / (self.a_true + self.b_true)
        return self.tie_rate * 0.5 + (1.0 - self.tie_rate) * p_mean

    @property
    def true_latent_variance(self) -> float:
        """Between-clause variance of the ENCODED clause mean."""
        if self.homogeneous_p is not None:
            return 0.0
        c = self.a_true + self.b_true
        var_p = (self.a_true * self.b_true) / (c * c * (c + 1.0))
        return (1.0 - self.tie_rate) ** 2 * var_p

    def pseudo_true_moment_matched_beta(self) -> tuple[float, float] | None:
        """The Beta target of the MOMENT MAP. NOT the true latent distribution.

        For a tie regime the latent distribution is a scaled Beta,
        theta_k = 0.5 t + (1 - t) p_k with p_k ~ Beta(a_true, b_true), which is
        not itself Beta. This moment-matched Beta is what an EB-MoM estimator
        converges to, so it is the right target for an estimator-recovery
        comparison. It is the WRONG object to call the oracle, and decision
        truth does not use it -- see oracle_decisions.
        """
        if self.true_latent_variance <= 0.0:
            return None
        mean = self.encoded_mean
        var = self.true_latent_variance
        c = mean * (1.0 - mean) / var - 1.0
        return mean * c, (1.0 - mean) * c

    @property
    def decisive_threshold(self) -> float:
        """The decisive-rate threshold equivalent to WIN_RATE_THRESHOLD.

        theta = 0.5 t + (1 - t) p exceeds the encoded threshold exactly when
        p exceeds (threshold - 0.5 t) / (1 - t). At t = 0.40 and a 0.60
        threshold that is 2/3.
        """
        if self.tie_rate <= 0.0:
            return WIN_RATE_THRESHOLD
        return (WIN_RATE_THRESHOLD - 0.5 * self.tie_rate) / (1.0 - self.tie_rate)


REGIMES: tuple[Regime, ...] = (
    # Tie-free, carried over from the original registration.
    Regime("small_n_bite", 0.65 * 20, 0.35 * 20, n_trials=10, k_clauses=200),
    Regime("low_heterogeneity", 0.65 * 100, 0.35 * 100, n_trials=25, k_clauses=200),
    Regime("benign_large_n", 0.65 * 10, 0.35 * 10, n_trials=100, k_clauses=200),
    # Tie-carrying, registered in amendment section 4.
    Regime(
        "tie_heavy_null",
        a_true=1.0,
        b_true=1.0,
        n_trials=25,
        k_clauses=200,
        tie_rate=0.40,
        homogeneous_p=0.75,
    ),
    Regime(
        "tie_heavy_signal",
        a_true=15.0,
        b_true=5.0,
        n_trials=25,
        k_clauses=200,
        tie_rate=0.40,
    ),
)


# --- seed derivation --------------------------------------------------------


def derive_seed(root_seed: str, *parts: object) -> int:
    """Derive a stream seed from the root and a label path.

    Every seed the harness uses comes through here, so the whole run is a pure
    function of the root seed the maintainer supplies.
    """
    material = "|".join([root_seed, *(str(p) for p in parts)])
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")


# --- world generation -------------------------------------------------------


def draw_world(regime: Regime, seed: int) -> tuple[list[ClauseObservations], list[float]]:
    """Generate one replicate. Returns (clauses, true encoded clause means)."""
    rng = random.Random(seed)  # noqa: S311  -- simulation, not a security primitive
    clauses: list[ClauseObservations] = []
    truths: list[float] = []

    for i in range(regime.k_clauses):
        if regime.homogeneous_p is not None:
            p_decisive = regime.homogeneous_p
        else:
            p_decisive = rng.betavariate(regime.a_true, regime.b_true)
        truths.append(regime.tie_rate * 0.5 + (1.0 - regime.tie_rate) * p_decisive)

        w = 0.0
        sum_sq = 0.0
        for _ in range(regime.n_trials):
            if regime.tie_rate > 0.0 and rng.random() < regime.tie_rate:
                obs = 0.5
            elif rng.random() < p_decisive:
                obs = 1.0
            else:
                obs = 0.0
            w += obs
            sum_sq += obs * obs
        clauses.append(ClauseObservations(clause_id=f"c{i}", w=w, n=regime.n_trials, sum_sq=sum_sq))
    return clauses, truths


# --- the baseline estimator, as `main` behaves ------------------------------


def baseline_fit(clauses: list[ClauseObservations]) -> tuple[str, float | None, float | None]:
    """Re-derivation of the estimator on `main`: no peel, /K variance, VAR_FLOOR.

    Written here rather than imported so the comparison survives the candidate
    replacing production. Returns (method, alpha_hat, beta_hat).
    """
    k = len(clauses)
    rates = [cl.w / cl.n for cl in clauses]
    mean = sum(rates) / k
    var = sum((r - mean) ** 2 for r in rates) / k  # population, unpeeled

    if var < VAR_FLOOR:
        return "bh_fdr_fallback", None, None
    common = mean * (1.0 - mean) / var - 1.0
    alpha_hat = mean * common
    beta_hat = (1.0 - mean) * common
    if alpha_hat <= 0.0 or beta_hat <= 0.0:
        return "bh_fdr_fallback", None, None
    return "ebmom_hierarchical", alpha_hat, beta_hat


# --- decisions --------------------------------------------------------------


def decision(p_win: float) -> str:
    if p_win >= PASS_P:
        return "PASS"
    if p_win <= FAIL_P:
        return "FAIL"
    return "UNDECIDED"


def oracle_decisions(regime: Regime, clauses: list[ClauseObservations]) -> list[str]:
    """Decision truth under the EXACT generative model (amendment section 4).

    For a tie regime this is the exact tie-model posterior, not a
    moment-matched approximation. A tie carries no information about p_k when
    the tie probability is fixed independently of it, so ties do not update
    p_k and the posterior is

        p_k | W, L  ~  Beta(a_true + W, b_true + L)

    and the encoded threshold maps to regime.decisive_threshold on p_k.
    """
    if regime.tie_rate > 0.0 and regime.homogeneous_p is None:
        out: list[str] = []
        for cl in clauses:
            wins, _ties, losses = decompose(cl)
            p_exceed = float(
                beta_dist.sf(
                    regime.decisive_threshold,
                    regime.a_true + wins,
                    regime.b_true + losses,
                )
            )
            out.append(decision(p_exceed))
        return out

    prior = regime.pseudo_true_moment_matched_beta()
    if prior is None:
        # Degenerate oracle: every clause's true encoded mean is exactly
        # regime.encoded_mean, so P(rate > threshold) is 0 or 1.
        verdict = "PASS" if regime.encoded_mean > WIN_RATE_THRESHOLD else "FAIL"
        return [verdict] * len(clauses)
    a0, b0 = prior
    return [
        decision(float(beta_dist.sf(WIN_RATE_THRESHOLD, a0 + cl.w, b0 + (cl.n - cl.w))))
        for cl in clauses
    ]


def fitted_tails(
    clauses: list[ClauseObservations], alpha_hat: float | None, beta_hat: float | None
) -> list[float]:
    """P(theta_k > WIN_RATE_THRESHOLD) per clause under the shrunken posterior.

    The tail rather than the decision, because v2 section 2.2's reliability
    table bins the fitted probability and the decision has already thrown it
    away. ``fitted_decisions`` is this function under ``decision``.
    """
    a0, b0 = (alpha_hat, beta_hat) if alpha_hat is not None and beta_hat is not None else (1.0, 1.0)
    return [
        float(beta_dist.sf(WIN_RATE_THRESHOLD, a0 + cl.w, b0 + (cl.n - cl.w))) for cl in clauses
    ]


def fitted_decisions(
    clauses: list[ClauseObservations], alpha_hat: float | None, beta_hat: float | None
) -> list[str]:
    """Decisions from the shrunken posterior, or unpooled when no fit was made."""
    return [decision(p) for p in fitted_tails(clauses, alpha_hat, beta_hat)]


# --- v2 rows 5c and 6c: the per-path kill and its reported set --------------
#
# Specification: docs/assurance/ebmom-peel-preregistration-amendment-v2.md
# sections 2, 2.1, 2.2 and 5, FROZEN 2026-09-05 (S414). Reference
# implementation: rescore405.py (columns and per-path tallies) and
# clustered_bound.py (both tests per cell) in
# docs/assurance/reference/ebmom-class2-S414/.
#
# The construction is the standard cluster-robust move for correlated binary
# outcomes: worlds are the clusters, and one observation per cluster gives
# independent Bernoulli trials whose sum is dominated by Binomial(G, 0.05)
# under the per-claim promise. Cluster-level inference for binary data is
# Donner and Klar, "Design and Analysis of Cluster Randomization Trials in
# Health Research" (2000), chapter 5; the one-per-cluster reduction is the
# degenerate case of their design effect, which costs power and buys an exact
# level at every G. The world-block percentile bound it replaces is the
# cluster bootstrap of Field and Welsh, "Bootstrapping clustered data", JRSS-B
# 69 (2007), and v2 section 2.1 records the measured reason it was demoted: its
# lower percentile is 0 by construction whenever four or fewer clusters carry a
# false decision, at any rate.

V2_NULL_P = 0.05  # the complement of the locked PASS_P, and equal to FAIL_P
V2_TEST_LEVEL = 0.01
V2_ROWS: tuple[str, ...] = ("5c", "6c")
V2_PATHS: tuple[str, ...] = ("admitted", "refused")
# The four columns of the prototype dumps. `oracle` and `main` carry no
# admission concept of their own; they are labelled by the CANDIDATE's
# admission verdict, so "the refused path" names a set of worlds and each
# column answers "what does this decider do where the candidate refuses".
V2_COLUMNS: tuple[str, ...] = ("oracle", "main", "cand_bpB", "cand_pb")
V2_CANDIDATE_COLUMN = "cand_pb"
BOUND_B = 999
BOUND_ORDER_INDEX = 9  # the 10th smallest of 999 = the one-sided 99 percent lower bound
BOUND_KILL = 0.05
RELIABILITY_BINS = 10


def select_one_decision_per_world(
    root_seed: str,
    regime_name: str,
    world: int,
    row: str,
    entries: list[tuple[str, bool]],
) -> bool:
    """v2 section 2.1 step 2: one decision per world, chosen by a seeded draw.

    The seed is SHA-256 over ``<root>|<regime>|<world>|<row>``, first eight
    bytes big-endian, feeding ``random.Random``, choosing uniformly among that
    world's decisions of the row's kind sorted by ``clause_id`` in Python str
    order. The selection is fixed by the root before any decision exists, which
    is what stops it being chosen after the counts are known.

    Returns whether the SELECTED decision is false.
    """
    ordered = sorted(entries)
    seed = derive_seed(root_seed, regime_name, world, row)
    chosen = random.Random(seed).choice(ordered)  # noqa: S311 -- registered selection, not a key
    return chosen[1]


def exact_kill_test(selected_false: int, clusters: int) -> dict[str, object]:
    """v2 section 2.1 step 3: exact binomial, one-sided greater, null 0.05, level 0.01.

    A cell with no decisions of its kind is NOT TESTABLE and is never reported
    as passed. That is section 2's wording and it is load-bearing: an empty cell
    passes every test that is applied to it, and reporting it as a pass would
    make an abstaining candidate indistinguishable from a calibrated one.
    """
    if clusters == 0:
        return {
            "testable": False,
            "selected_false": None,
            "clusters": 0,
            "p_value": None,
            "rejects": False,
            "passes": None,
            "note": "no decisions of this kind on this path; not testable",
        }
    p_value = float(binomtest(selected_false, clusters, V2_NULL_P, alternative="greater").pvalue)
    rejects = p_value < V2_TEST_LEVEL
    return {
        "testable": True,
        "selected_false": selected_false,
        "clusters": clusters,
        "p_value": p_value,
        "rejects": rejects,
        "passes": not rejects,
        "rejects_at": rejecting_count(clusters),
        "note": "",
    }


def rejecting_count(clusters: int) -> int | None:
    """The smallest number of false selections that rejects the cell, or None.

    Reported because a cell can be UNABLE to reject at any selection: with one
    decision-bearing world the largest attainable statistic is one false
    selection and ``P(Binomial(1, 0.05) >= 1) = 0.05``, which is above the
    level. A pass in such a cell is a property of its size, not of the
    candidate, and v2 section 0.6 turns on exactly that reading. Printing the
    threshold beside the verdict is what stops the pass being read as evidence.
    """
    for count in range(clusters + 1):
        if binomtest(count, clusters, V2_NULL_P, alternative="greater").pvalue < V2_TEST_LEVEL:
            return count
    return None


class ColumnTally:
    """Per-path, per-row tallies for one column in one regime.

    A world is one cluster, and every decision a world contributes sits on the
    same path, because the path is the candidate's admission verdict for that
    world. Three things are kept per world and per (row, path): the number of
    decisions of the row's kind, the number of those that are false, and
    whether the ONE decision the registered selection draws is false. The
    selection runs at the moment a world is scored rather than at the end, so
    no per-clause table has to survive to the end of a 4,000-world run.

    Keeping the three per world, rather than only their totals, is what lets a
    cell be recomputed over a sub-range of worlds without re-scoring anything.
    v2 section 4's freeze condition needs exactly that: worlds 500 to 999 of
    every regime and 1,000 to 3,999 of low_heterogeneity, evaluated inside the
    runs the chain already owes.
    """

    def __init__(
        self, root_seed: str, regime_name: str, replicates: int, world_offset: int = 0
    ) -> None:
        self.root_seed = root_seed
        self.regime_name = regime_name
        self.replicates = replicates
        self.world_offset = world_offset
        self.n: dict[str, dict[str, list[int]]] = {
            row: {path: [0] * replicates for path in V2_PATHS} for row in V2_ROWS
        }
        self.false: dict[str, dict[str, list[int]]] = {
            row: {path: [0] * replicates for path in V2_PATHS} for row in V2_ROWS
        }
        # -1 marks a world that contributed no decision of the row's kind, so it
        # is not a cluster. 0 and 1 are the selected decision's false indicator.
        self.selected: dict[str, dict[str, list[int]]] = {
            row: {path: [-1] * replicates for path in V2_PATHS} for row in V2_ROWS
        }
        self.wrong_pass = 0
        self.wrong_fail = 0
        self.abstain = 0

    def add(
        self,
        fitted: list[str],
        oracle: list[str],
        truths: list[float],
        clauses: list[ClauseObservations],
        path: str,
        world: int,
    ) -> None:
        """Tally one world's decisions for this column."""
        wrong_pass, wrong_fail, abstained = score(oracle, fitted)
        self.wrong_pass += wrong_pass
        self.wrong_fail += wrong_fail
        self.abstain += abstained

        lane = path
        entries: dict[str, list[tuple[str, bool]]] = {row: [] for row in V2_ROWS}
        for clause, verdict, truth in zip(clauses, fitted, truths, strict=True):
            if verdict == "PASS":
                entries["5c"].append((clause.clause_id, truth <= WIN_RATE_THRESHOLD))
            elif verdict == "FAIL":
                entries["6c"].append((clause.clause_id, truth > WIN_RATE_THRESHOLD))

        index = world - self.world_offset
        for row, row_entries in entries.items():
            if not row_entries:
                continue
            self.n[row][lane][index] = len(row_entries)
            self.false[row][lane][index] = sum(1 for _, is_false in row_entries if is_false)
            self.selected[row][lane][index] = int(
                select_one_decision_per_world(
                    self.root_seed, self.regime_name, world, row, row_entries
                )
            )

    def per_world(self, row: str, path: str | None) -> tuple[list[int], list[int], list[int]]:
        """(decisions, false, selected) per world. ``path=None`` pools the two paths."""
        lanes = V2_PATHS if path is None else (path,)
        counts = [0] * self.replicates
        falses = [0] * self.replicates
        selected = [-1] * self.replicates
        for lane in lanes:
            for index in range(self.replicates):
                counts[index] += self.n[row][lane][index]
                falses[index] += self.false[row][lane][index]
                if self.selected[row][lane][index] >= 0:
                    selected[index] = self.selected[row][lane][index]
        return counts, falses, selected

    def cell(
        self, row: str, path: str | None, lo: int | None = None, hi: int | None = None
    ) -> dict[str, object]:
        """The cell for one (row, path), optionally over a sub-range of worlds.

        ``lo`` and ``hi`` are absolute world numbers, half-open, as v2 section 4
        names them (500 to 999 is ``lo=500, hi=1000``).
        """
        counts, falses, selected = self.per_world(row, path)
        start = 0 if lo is None else lo - self.world_offset
        stop = self.replicates if hi is None else hi - self.world_offset
        counts = counts[start:stop]
        falses = falses[start:stop]
        selected = selected[start:stop]

        decisions = sum(counts)
        false_total = sum(falses)
        clusters = sum(1 for value in counts if value > 0)
        false_worlds = sum(1 for value in falses if value > 0)
        # The mutation point of v2 section 7 mutant 3: the registered test takes
        # ONE decision per world. Replacing this pair with (false_total,
        # decisions) is the retired all-decision test.
        trials, trial_false = clusters, sum(1 for value in selected if value == 1)

        verdict = exact_kill_test(trial_false, trials)
        cell: dict[str, object] = {
            "decisions": decisions,
            "false": false_total,
            "G": clusters,
            "g": false_worlds,
            "rate": (false_total / decisions) if decisions else None,
            "worlds_in_range": len(counts),
        }
        cell.update(verdict)
        if decisions == 0:
            cell["testable"] = False
            cell["rejects"] = False
            cell["passes"] = None
            cell["note"] = "no decisions of this kind on this path; not testable"
        return cell


def world_block_bound(
    root_label: str,
    regime_name: str,
    column: str,
    path: str,
    row: str,
    n_w: list[int] | list[float],
    f_w: list[int] | list[float],
) -> dict[str, object]:
    """v2 section 2.2: the world-block 99 percent lower bound, as a DIAGNOSTIC.

    Resample the range's worlds with replacement, B = 999; on each resample the
    rate is the summed false over the summed decisions; a resample with no
    decisions on the path counts as 0 and is counted; the bound is the 10th
    smallest of the 999 rates, the order-statistic form rather than an
    interpolated quantile. The seed is SHA-256 over
    ``<root label>|<regime>|<column>|<path>|<row>``, matching
    clustered_bound.py so the committed reference tables stay reproducible.

    It is reported, never a kill. v2 section 2.1 records why: the bound is 0 by
    construction whenever four or fewer worlds carry a false decision, whatever
    the rate, so it passes vacuously on exactly the sparse cells the exact test
    was chosen to reach.
    """
    # Imported here rather than at module scope: numpy is a dev extra, not a
    # runtime dependency (tests/test_assurance_manifest_161.py locks the runtime
    # manifest), and every other entry point in this file works without it.
    import numpy as np

    replicates = len(n_w)
    if replicates == 0 or sum(n_w) == 0:
        return {"bound_lower_99": None, "undefined_resamples": None, "fails": None, "B": BOUND_B}
    seed = derive_seed(root_label, regime_name, column, path, row)
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(replicates, np.full(replicates, 1.0 / replicates), size=BOUND_B)
    numerator = counts @ np.asarray(f_w, dtype=float)
    denominator = counts @ np.asarray(n_w, dtype=float)
    undefined = int((denominator == 0).sum())
    rates = np.where(denominator > 0, numerator / np.where(denominator > 0, denominator, 1.0), 0.0)
    rates.sort()
    bound = float(rates[BOUND_ORDER_INDEX])
    return {
        "bound_lower_99": bound,
        "undefined_resamples": undefined,
        "fails": bool(bound > BOUND_KILL),
        "B": BOUND_B,
    }


class ReliabilityTable:
    """v2 section 2.2 row 9: fitted P(theta > 0.60) in tenths against the truth.

    Diagnostic. A decider can pass both kill rows and still be badly calibrated
    away from the two cuts, and this is the surface that shows it. The binning
    is revisable per v2 section 9; tenths is what the document names.
    """

    def __init__(self) -> None:
        self.n = [0] * RELIABILITY_BINS
        self.exceed = [0] * RELIABILITY_BINS

    def add(self, tails: list[float], truths: list[float]) -> None:
        for tail, truth in zip(tails, truths, strict=True):
            index = min(int(tail * RELIABILITY_BINS), RELIABILITY_BINS - 1)
            self.n[index] += 1
            if truth > WIN_RATE_THRESHOLD:
                self.exceed[index] += 1

    def rows(self) -> list[dict[str, object]]:
        width = 1.0 / RELIABILITY_BINS
        return [
            {
                "bin_lo": round(index * width, 10),
                "bin_hi": round((index + 1) * width, 10),
                "n": self.n[index],
                "exceed": self.exceed[index],
                "frequency": (self.exceed[index] / self.n[index]) if self.n[index] else None,
            }
            for index in range(RELIABILITY_BINS)
        ]


def v2_kill_verdict(cells: dict[tuple[str, str, str], dict[str, object]]) -> dict[str, object]:
    """v2 section 5's kill criterion: a union over every 5c and 6c cell on either path.

    Any rejection in any cell, on either path, in any registered regime, rejects
    the candidate. The criterion is deliberately not corrected for multiplicity:
    section 5 states the level it does and does not claim, and a correction that
    divided the level across cells would return the sparse tail to the blind
    spot section 2.1 was chosen to remove. The claim this supports is "no cell
    showed the promise broken", not "this procedure has level 0.01".
    """
    rejecting = [list(key) for key, cell in sorted(cells.items()) if cell["rejects"]]
    not_testable = [list(key) for key, cell in sorted(cells.items()) if not cell["testable"]]
    return {
        "kill_criterion_triggered": bool(rejecting),
        "verdict": "REJECTED" if rejecting else "NOT_REJECTED",
        "rejecting_cells": rejecting,
        "not_testable_cells": not_testable,
        "rollback_state": "main",
    }


@dataclass
class RegimeV2:
    """One regime scored under v2, with everything sections 2.2 and 5 report."""

    name: str
    root_seed: str
    replicates: int
    world_offset: int
    true_latent_variance: float
    admitted: int = 0
    unpooled_reverts: int = 0
    fallback_reasons: dict[str, int] = field(default_factory=dict)
    latent_estimates: list[float] = field(default_factory=list)
    tallies: dict[str, ColumnTally] = field(default_factory=dict)
    reliability: dict[str, ReliabilityTable] = field(default_factory=dict)

    def relative_bias(self) -> float | None:
        if self.true_latent_variance <= 0.0 or not self.latent_estimates:
            return None
        mean_estimate = sum(self.latent_estimates) / len(self.latent_estimates)
        return (mean_estimate - self.true_latent_variance) / self.true_latent_variance


def score_regime_v2(
    regime: Regime,
    root_seed: str,
    replicates: int,
    world_offset: int = 0,
    before_world: Callable[[int], None] | None = None,
    after_world: Callable[[int, str, list[ClauseObservations], list[float], list[float]], None]
    | None = None,
) -> RegimeV2:
    """Score one regime's worlds through production, all four v2 columns in one pass.

    ``cand_pb`` is production itself. ``cand_bpB`` is the same run with the
    plug-in posterior on the ADMITTED path, which is the only place the two
    columns differ: the admitted-path mechanism is admitted-path-only, so the
    refused cells of the two columns are identical by construction and a run
    that reproduces both is also the evidence that the admitted-path work left
    the refused path alone.

    ``before_world`` is called with the world number before the fit, and
    ``after_world`` with (world, path, clauses, truths, candidate tails) after
    it. They exist so a caller that has to run the same worlds twice -- the
    reproduction against a prototype dump runs them once under production's seed
    and once under the prototype's -- can collect the per-clause tails it needs
    for the flip listing without a third pass over the worlds.
    """
    result = RegimeV2(
        name=regime.name,
        root_seed=root_seed,
        replicates=replicates,
        world_offset=world_offset,
        true_latent_variance=regime.true_latent_variance,
        tallies={
            column: ColumnTally(root_seed, regime.name, replicates, world_offset)
            for column in V2_COLUMNS
        },
        reliability={column: ReliabilityTable() for column in ("cand_pb", "main")},
    )

    for world in range(world_offset, world_offset + replicates):
        clauses, truths = draw_world(regime, derive_seed(root_seed, regime.name, world))
        oracle = oracle_decisions(regime, clauses)

        if before_world is not None:
            before_world(world)
        fit = fit_skill(clauses)
        provenance = fit.aggregation_provenance
        is_admitted = fit.aggregation_method == "ebmom_hierarchical"
        path = "admitted" if is_admitted else "refused"

        test = provenance.get("heterogeneity_test")
        if not isinstance(test, dict):
            attempted = provenance.get("attempted")
            if isinstance(attempted, dict):
                test = attempted.get("heterogeneity_test")
        if not isinstance(test, dict):
            raise AssertionError(
                f"no heterogeneity_test in provenance for method "
                f"{fit.aggregation_method!r}; row 3 would silently condition on admission"
            )
        result.latent_estimates.append(float(test["statistic"]))

        candidate_tails = [post.p_win_gt_threshold for post in fit.posteriors]
        candidate = [decision(tail) for tail in candidate_tails]

        base_alpha, base_beta = baseline_fit(clauses)[1:]
        main_tails = fitted_tails(clauses, base_alpha, base_beta)
        main = [decision(tail) for tail in main_tails]

        if is_admitted:
            result.admitted += 1
            alpha_hat = float(provenance["alpha_hat"])  # type: ignore[arg-type]
            beta_hat = float(provenance["beta_hat"])  # type: ignore[arg-type]
            bpb = fitted_decisions(clauses, alpha_hat, beta_hat)
        else:
            reason = str(provenance.get("fallback_reason", "unknown"))
            result.fallback_reasons[reason] = result.fallback_reasons.get(reason, 0) + 1
            pooling = provenance.get("bounded_pooling", {})
            if isinstance(pooling, dict):
                result.unpooled_reverts += int(pooling.get("unpooled_revert_count", 0))
            # The refused path is form B for both candidate columns.
            bpb = candidate

        for column, fitted in (
            ("oracle", oracle),
            ("main", main),
            ("cand_bpB", bpb),
            ("cand_pb", candidate),
        ):
            result.tallies[column].add(
                fitted=fitted,
                oracle=oracle,
                truths=truths,
                clauses=clauses,
                path=path,
                world=world,
            )
        result.reliability["cand_pb"].add(candidate_tails, truths)
        result.reliability["main"].add(main_tails, truths)
        if after_world is not None:
            after_world(world, path, clauses, truths, candidate_tails)

    return result


def v2_regime_report(
    result: RegimeV2,
    lo: int | None = None,
    hi: int | None = None,
) -> dict[str, object]:
    """Everything v2 section 2.2 reports beside the kill, for one regime.

    ``lo`` and ``hi`` restrict the cells to a world sub-range without
    re-scoring; the bound's seed label carries the range, exactly as
    clustered_bound.py's does, so a sub-range is not a subset of the full run's
    draws.
    """
    is_subrange = lo is not None or hi is not None
    start = result.world_offset if lo is None else lo
    stop = result.world_offset + result.replicates if hi is None else hi
    root_label = result.root_seed if not is_subrange else f"{result.root_seed}|worlds{start}:{stop}"

    columns: dict[str, object] = {}
    for column in V2_COLUMNS:
        tally = result.tallies[column]
        rows: dict[str, object] = {}
        for path in (*V2_PATHS, None):
            for row in V2_ROWS:
                cell = tally.cell(row, path, start, stop)
                counts, falses, _selected = tally.per_world(row, path)
                offset = start - result.world_offset
                length = stop - start
                cell["world_block_bound"] = world_block_bound(
                    root_label,
                    result.name,
                    column,
                    path or "pooled",
                    row,
                    counts[offset : offset + length],
                    falses[offset : offset + length],
                )
                label = "pooled" if path is None else path
                rows[f"row{row}_{'false_pass' if row == '5c' else 'false_fail'}_{label}"] = cell
        rows["vs_oracle"] = {
            "wrong_pass": tally.wrong_pass,
            "wrong_fail": tally.wrong_fail,
            "abstention": tally.abstain,
        }
        columns[column] = rows

    main_tally = result.tallies["main"]
    excess = {
        column: [
            result.tallies[column].wrong_pass - main_tally.wrong_pass,
            result.tallies[column].wrong_fail - main_tally.wrong_fail,
            result.tallies[column].abstain - main_tally.abstain,
        ]
        for column in V2_COLUMNS
    }

    return {
        "regime": result.name,
        "world_range": [start, stop],
        "is_subrange": is_subrange,
        "replicates": result.replicates,
        "admitted": result.admitted,
        "admission_rate": result.admitted / result.replicates,
        "true_latent_variance": result.true_latent_variance,
        "relative_bias_latent_raw": result.relative_bias(),
        "fallback_reasons": result.fallback_reasons,
        "unpooled_reverts": result.unpooled_reverts,
        "estimators": columns,
        "excess_over_main_vs_oracle": excess,
        "reliability": {
            column: table.rows() for column, table in sorted(result.reliability.items())
        },
    }


def v2_candidate_cells(
    reports: list[dict[str, object]],
) -> dict[tuple[str, str, str], dict[str, object]]:
    """The candidate's per-path 5c and 6c cells, keyed (regime, path, row).

    The pooled rows are deliberately excluded. They are reported for
    comparability with the prototype dumps; the kill criterion is per path, and
    a pooled row entering the union would let a cell convict twice.
    """
    cells: dict[tuple[str, str, str], dict[str, object]] = {}
    for report in reports:
        estimators = cast("dict[str, dict[str, Any]]", report["estimators"])
        rows = estimators[V2_CANDIDATE_COLUMN]
        for path in V2_PATHS:
            for row in V2_ROWS:
                name = f"row{row}_{'false_pass' if row == '5c' else 'false_fail'}_{path}"
                cells[(str(report["regime"]), path, row)] = rows[name]
    return cells


def oracle_self_check(reports: list[dict[str, object]]) -> dict[str, object]:
    """v2 section 5 rows 5c* and 6c*: the oracle must pass every testable cell.

    A failure voids the regime's result and is reported as a HARNESS DEFECT, not
    as a candidate verdict: the decider that knows the true hyperprior cannot
    break the promise unless the generative model or the oracle is mis-specified.
    """
    failures: list[list[str]] = []
    testable = 0
    for report in reports:
        estimators = cast("dict[str, dict[str, Any]]", report["estimators"])
        rows = estimators["oracle"]
        for path in V2_PATHS:
            for row in V2_ROWS:
                name = f"row{row}_{'false_pass' if row == '5c' else 'false_fail'}_{path}"
                cell = rows[name]
                if not cell["testable"]:
                    continue
                testable += 1
                if cell["rejects"]:
                    failures.append([str(report["regime"]), path, row])
    return {
        "testable_cells": testable,
        "failing_cells": failures,
        "passes": not failures,
        "consequence": ("a failing oracle cell voids that regime's result and is a harness defect"),
    }


# --- the matrix -------------------------------------------------------------


@dataclass
class RegimeResult:
    name: str
    true_latent_variance: float
    admitted: int = 0
    replicates: int = 0
    latent_estimates: list[float] = field(default_factory=list)
    fallback_reasons: dict[str, int] = field(default_factory=dict)
    wrong_pass_candidate: int = 0
    wrong_fail_candidate: int = 0
    added_abstention_candidate: int = 0
    wrong_pass_baseline: int = 0
    wrong_fail_baseline: int = 0
    added_abstention_baseline: int = 0

    def relative_bias(self) -> float | None:
        if self.true_latent_variance <= 0.0 or not self.latent_estimates:
            return None
        mean_est = sum(self.latent_estimates) / len(self.latent_estimates)
        return (mean_est - self.true_latent_variance) / self.true_latent_variance


def score(truth_decisions: list[str], fit_decisions: list[str]) -> tuple[int, int, int]:
    """Return (wrong_pass, wrong_fail, added_abstention)."""
    wrong_pass = wrong_fail = abstained = 0
    for oracle, fitted in zip(truth_decisions, fit_decisions, strict=True):
        if fitted == oracle:
            continue
        if fitted == "PASS":
            wrong_pass += 1
        elif fitted == "FAIL":
            wrong_fail += 1
        else:
            abstained += 1
    return wrong_pass, wrong_fail, abstained


def run_regime(regime: Regime, root_seed: str, replicates: int) -> RegimeResult:
    result = RegimeResult(regime.name, regime.true_latent_variance)

    for r in range(replicates):
        clauses, _truths = draw_world(regime, derive_seed(root_seed, regime.name, r))
        result.replicates += 1

        candidate = fit_skill(clauses)
        prov = candidate.aggregation_provenance
        # Row 3 reads latent_raw across ALL replicates, admitted or refused.
        # On the refused path the test record is nested under "attempted";
        # reading only the top level would collect admitted fits only, and
        # admission selects the positive tail, which manufactures bias.
        test = prov.get("heterogeneity_test")
        if not isinstance(test, dict):
            attempted = prov.get("attempted")
            if isinstance(attempted, dict):
                test = attempted.get("heterogeneity_test")
        if not isinstance(test, dict):
            raise AssertionError(
                f"no heterogeneity_test in provenance for method "
                f"{candidate.aggregation_method!r}; row 3 would silently "
                f"condition on admission"
            )
        result.latent_estimates.append(float(test["statistic"]))
        if candidate.aggregation_method == "ebmom_hierarchical":
            result.admitted += 1
            cand_a = float(prov["alpha_hat"])  # type: ignore[arg-type]
            cand_b = float(prov["beta_hat"])  # type: ignore[arg-type]
        else:
            cand_a = cand_b = None  # type: ignore[assignment]
            reason = str(prov.get("fallback_reason", "unknown"))
            result.fallback_reasons[reason] = result.fallback_reasons.get(reason, 0) + 1

        base_method, base_a, base_b = baseline_fit(clauses)
        del base_method

        oracle = oracle_decisions(regime, clauses)
        wp, wf, ab = score(oracle, fitted_decisions(clauses, cand_a, cand_b))
        result.wrong_pass_candidate += wp
        result.wrong_fail_candidate += wf
        result.added_abstention_candidate += ab

        wp, wf, ab = score(oracle, fitted_decisions(clauses, base_a, base_b))
        result.wrong_pass_baseline += wp
        result.wrong_fail_baseline += wf
        result.added_abstention_baseline += ab

    return result


def calibration_verdict(result: RegimeResult | RegimeV2) -> dict[str, object] | None:
    """Row 1: exact binomial test of admission rate against alpha."""
    if result.true_latent_variance > 0.0:
        return None
    test = binomtest(result.admitted, result.replicates, HETEROGENEITY_TEST_ALPHA)
    p_value = float(test.pvalue)
    return {
        "admitted": result.admitted,
        "replicates": result.replicates,
        "expected_rate": HETEROGENEITY_TEST_ALPHA,
        "p_value": p_value,
        "test_level": CALIBRATION_TEST_LEVEL,
        # Failure to reject is the pass condition.
        "calibrated": p_value >= CALIBRATION_TEST_LEVEL,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root-seed",
        required=True,
        help="Root seed supplied by the maintainer. Every regime and replicate "
        "seed is derived from it. The harness never invents one.",
    )
    parser.add_argument("--replicates", type=int, default=R_REPLICATES)
    parser.add_argument(
        "--regime",
        action="append",
        default=None,
        help="regime to score; repeatable. Default: every registered regime. "
        "A run that reports a subset is NOT a confirmatory run (v2 section 5).",
    )
    parser.add_argument(
        "--world-range",
        default=None,
        help="LO:HI, half-open, absolute world numbers. Reports the cells over "
        "that sub-range as well as over the whole run. v2 section 4's freeze "
        "condition names 500:1000 for every regime and 1000:4000 for "
        "low_heterogeneity.",
    )
    parser.add_argument("--out", default="-", help="JSON output path, or - for stdout")
    args = parser.parse_args(argv)

    wanted = args.regime or [regime.name for regime in REGIMES]
    complete = args.replicates == R_REPLICATES and len(wanted) == len(REGIMES)
    if not complete:
        print(
            f"NOTE: replicates={args.replicates} on {len(wanted)} of {len(REGIMES)} "
            f"regimes is not the registered matrix (R={R_REPLICATES}, every regime). "
            "This run is a smoke test and is NOT a confirmatory run.",
            file=sys.stderr,
        )

    sub: tuple[int, int] | None = None
    if args.world_range is not None:
        low, high = (int(part) for part in args.world_range.split(":"))
        sub = (low, high)

    report: dict[str, object] = {
        "root_seed": args.root_seed,
        "replicates": args.replicates,
        "registered_replicates": R_REPLICATES,
        "is_confirmatory": complete,
        "alpha": HETEROGENEITY_TEST_ALPHA,
        "bias_tolerance": BIAS_TOL,
        "specification": "docs/assurance/ebmom-peel-preregistration-amendment-v2.md",
        "kill_test": (
            "v2 section 2.1: one decision per world by the registered seeded "
            f"draw, exact binomial one-sided greater, null {V2_NULL_P}, level "
            f"{V2_TEST_LEVEL}"
        ),
        "candidate_column": V2_CANDIDATE_COLUMN,
    }

    regime_rows: list[dict[str, object]] = []
    subrange_rows: list[dict[str, object]] = []
    for regime in REGIMES:
        if regime.name not in wanted:
            continue
        started = time.time()
        scored = score_regime_v2(regime, args.root_seed, args.replicates)
        row = v2_regime_report(scored)
        bias = scored.relative_bias()
        row["calibration"] = calibration_verdict(scored)
        row["bias_within_tolerance"] = None if bias is None else abs(bias) <= BIAS_TOL
        regime_rows.append(row)
        if sub is not None:
            subrange_rows.append(v2_regime_report(scored, sub[0], sub[1]))
        print(
            f"[{regime.name}] admitted {scored.admitted}/{args.replicates} "
            f"in {time.time() - started:.0f}s",
            file=sys.stderr,
            flush=True,
        )

    report["regimes"] = regime_rows
    report.update(v2_kill_verdict(v2_candidate_cells(regime_rows)))
    report["oracle_self_check"] = oracle_self_check(regime_rows)
    if sub is not None:
        report["world_subrange"] = {
            "range": list(sub),
            "regimes": subrange_rows,
            "kill_verdict": v2_kill_verdict(v2_candidate_cells(subrange_rows)),
            "oracle_self_check": oracle_self_check(subrange_rows),
        }

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out == "-":
        print(payload)
    else:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
    # The harness reports; it does not gate CI. Exit 0 either way so a kill is
    # read from the verdict field rather than inferred from an exit code.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
