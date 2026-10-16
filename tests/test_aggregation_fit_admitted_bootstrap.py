"""Mechanism class 2 on the admitted path: the port, the seed, and mutant 4.

Specification: docs/assurance/ebmom-peel-preregistration-amendment-v2.md
sections 0.5, 4 and 7, FROZEN 2026-09-05 (S414). Reference implementation:
``pb_probs`` in docs/assurance/reference/ebmom-class2-S414/proto_pb.py, which
produced every number v2 sections 0.3 to 0.7 record.

What is pinned here.

The port is the reference, not a paraphrase of it
-------------------------------------------------
The mechanism is a Monte Carlo average, so "close enough" is not a check: two
implementations that draw different streams agree on verdicts and disagree in
the third decimal, and a paraphrase would pass a verdict comparison while
having stopped being the procedure v2 measured. The port is therefore driven
with the PROTOTYPE'S OWN SEED and required to return the prototype's
probabilities to four decimal places -- 0.0429 on world 783, and the three
UNDECIDED tails beside it. That is a bit-level identity claim about the
arithmetic, and it is the only test here that can catch a drifting draw order,
a changed block size, or a moment recomputed differently.

Production does not use that seed, and cannot
---------------------------------------------
The prototype seeds from ``<root>|<regime>|<world>|pb`` because a harness knows
which world it drew. ``fit_skill`` sees clauses and nothing else, so v2 section
4 and the ticket both derive the production seed from the canonical clause
encoding under v1 section 3's frozen procedure, with the label ``pb``. The two
seeds are different integers and draw different streams. Measured on the four
named worlds: the probabilities differ by at most 0.014, and NOT ONE decision
differs. Both facts are asserted below, the second as the criterion the build is
actually held to and the first as its size.

Mutant 4 of v2 section 7
-------------------------
"A fourth, if section 4 freezes a mechanism: the mechanism removed (plug-in
restored), killed by the admitted 6c cell in low_heterogeneity on the burned
root."

The cell is four decisions, one per world, and v2 section 0.5 names the worlds
that carry them: 255, 316, 600 and 783, found by ``find_fail_worlds.py`` over
worlds 0 to 999. Under the plug-in three of the four are false, and the
registered exact binomial returns p = 4.8e-4, which rejects at level 0.01. That
arithmetic is reproduced here as the positive control.

WHAT THIS FILE DOES AND DOES NOT MEASURE, stated because the difference matters:
it re-derives the DECISIONS on the four named worlds from production, and it
takes the cell's MEMBERSHIP -- that these four worlds are the whole cell at
R = 1000 -- from v2 section 0.5 rather than re-deriving it. Scanning 1,000
worlds of a K = 200 regime through a 999-replicate admission bootstrap twice
over is hours of wall time and cannot sit in the gate. The control below is what
keeps the borrowed membership honest: if the plug-in stopped minting exactly
three false FAILs of four on these worlds, the borrowed cell would no longer
describe the code and the control would fail rather than the kill passing
quietly.

The cell is sparse, and v2 section 5 says what a sparse cell can say: a
rejection in a cell of two to four claims is valid, and a PASS in one is weak
evidence, because a lane that makes one claim or none passes too. Nothing here
is a confirmatory result, and the burned root is used because that is the root
the cell was registered on, not because a result on it confirms anything.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import random
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]
from scipy.stats import binomtest

from skill_harness.aggregation.fit import (
    ADMITTED_BOOTSTRAP_DRAWS,
    WIN_RATE_THRESHOLD,
    ClauseObservations,
    _admission_conditioned_probs,
    _admitted_bootstrap_seed,
    _bootstrap_seed,
    _plugin_tail_probabilities,
    fit_skill,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent

# The burned root of v2 section 0.5 and section 8. Burned means it has already
# been scored, so nothing measured on it is confirmatory; it is used because the
# cell this file reproduces was registered on it.
BURNED_ROOT = "f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a"
REGIME_NAME = "low_heterogeneity"

# The development smoke root. Used only by the refused-path case, which is a
# statement about a code path rather than about a registered cell, and which
# therefore has no business consuming the burned root's worlds.
SMOKE_ROOT = "SMOKE_NOT_CONFIRMATORY"

# v2 section 0.5, found by find_fail_worlds.py over worlds 0 to 999.
NAMED_WORLDS: tuple[int, ...] = (255, 316, 600, 783)

# The registered kill of v2 section 2.1: one-sided exact binomial against the
# null rate the locked rule promises, at test level 0.01.
KILL_NULL_P = 0.05
KILL_LEVEL = 0.01

# v2 section 0.5's per-world plug-in tails and the prototype's class-2 tails on
# the clause each world's FAIL sits on, to four decimal places. The plug-in
# column is a second, independent pin: it comes from world_diag.py, not from
# proto_pb.py, so the two columns cannot drift together.
REFERENCE_TAILS: dict[int, dict[str, object]] = {
    255: {"clause_id": "c36", "plugin": 0.0464, "class2": 0.0628, "class2_decision": "UNDECIDED"},
    316: {"clause_id": "c33", "plugin": 0.0369, "class2": 0.0547, "class2_decision": "UNDECIDED"},
    600: {"clause_id": "c186", "plugin": 0.0425, "class2": 0.0564, "class2_decision": "UNDECIDED"},
    783: {"clause_id": "c13", "plugin": 0.0361, "class2": 0.0429, "class2_decision": "FAIL"},
}

# v2 section 0.5's fitted concentration per world, to one decimal place. Pinned
# because every probability below is conditional on the fit that produced it: if
# alpha_hat + beta_hat moved, a reproduced tail would be a coincidence.
REFERENCE_CONCENTRATION: dict[int, float] = {255: 42.3, 316: 45.7, 600: 65.7, 783: 49.6}


def _load_acceptance_matrix() -> ModuleType:
    """Import scripts/ebmom_acceptance_matrix.py by path.

    scripts/ carries no __init__.py and is not a package. The regimes, the world
    generator, the seed derivation and the locked decision rule are taken from
    the harness rather than restated, so a drift between the two shows up as a
    failure here instead of as two implementations that agree with themselves.
    """
    path = _REPO_ROOT / "scripts" / "ebmom_acceptance_matrix.py"
    spec = importlib.util.spec_from_file_location("ebmom_acceptance_matrix", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves a frozen class through sys.modules while the module
    # body is still executing, so the entry must exist BEFORE exec_module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MATRIX = _load_acceptance_matrix()


def _prototype_seed(world: int) -> int:
    """The seed proto_pb.py uses: SHA-256 over ``<root>|<regime>|<world>|pb``.

    Restated here rather than imported because the prototype is a frozen
    artefact outside the package, and this file's job is to check production
    against it. If the prototype's derivation ever changed, this constant would
    have to change with it deliberately.
    """
    material = f"{BURNED_ROOT}|{REGIME_NAME}|{world}|pb"
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")


def _select_one_decision_per_world(
    per_world: dict[int, list[tuple[str, bool]]], row: str
) -> tuple[int, int]:
    """v2 section 2.1: one decision per world, chosen by a seeded draw.

    Returns (false_count, G). The seed is SHA-256 over
    ``<root>|<regime>|<world>|<row>``, first 8 bytes big-endian, feeding
    random.Random, choosing uniformly among that world's decisions of the row's
    kind sorted by clause_id. Fixed by the root before any decision exists.

    The same selection appears in tests/test_aggregation_fit_bounded_pooling.py
    for the refused-path cell. Both are restatements of the specification, which
    is the authority; what could silently drift -- the regimes, the world draw
    and the decision rule -- is imported from the harness in both files rather
    than restated in either.
    """
    false_count = 0
    clusters = 0
    for world in sorted(per_world):
        entries = sorted(per_world[world])
        if not entries:
            continue
        clusters += 1
        material = f"{BURNED_ROOT}|{REGIME_NAME}|{world}|{row}"
        seed = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")
        chosen = random.Random(seed).choice(entries)
        if chosen[1]:
            false_count += 1
    return false_count, clusters


def _exact_binomial_rejects(false_count: int, clusters: int) -> tuple[bool, float | None]:
    """The registered kill: one-sided exact binomial, null 0.05, level 0.01.

    A cell with no decisions of its kind is NOT TESTABLE and never passed, so it
    returns (False, None) and the caller says which it got.
    """
    if clusters == 0:
        return False, None
    p_value = float(binomtest(false_count, clusters, KILL_NULL_P, alternative="greater").pvalue)
    return p_value < KILL_LEVEL, p_value


def _fail_entries(
    probabilities: list[float],
    clauses: list[ClauseObservations],
    truths: list[float],
) -> list[tuple[str, bool]]:
    """(clause_id, is_false) for every FAIL among these probabilities."""
    return [
        (clause.clause_id, truth > WIN_RATE_THRESHOLD)
        for probability, clause, truth in zip(probabilities, clauses, truths, strict=True)
        if _MATRIX.decision(probability) == "FAIL"
    ]


@pytest.fixture(scope="module")
def named_worlds() -> dict[int, dict[str, Any]]:
    """Score the four named worlds once, three ways, on identical data.

    ``built`` is what production decides. ``plugin`` is the retired plug-in
    scored on the same fit, which is the positive control: mutant 4 makes
    ``built`` become ``plugin``, so the control must reject where the kill
    assertion does not. ``prototype`` is the mechanism driven with the
    prototype's own seed, which is the port check.
    """
    regime = next(r for r in _MATRIX.REGIMES if r.name == REGIME_NAME)
    scored: dict[int, dict[str, Any]] = {}
    for world in NAMED_WORLDS:
        clauses, truths = _MATRIX.draw_world(
            regime, _MATRIX.derive_seed(BURNED_ROOT, regime.name, world)
        )
        result = fit_skill(clauses)
        provenance = result.aggregation_provenance
        entry: dict[str, Any] = {
            "clauses": clauses,
            "truths": truths,
            "result": result,
            "method": result.aggregation_method,
            "built": [post.p_win_gt_threshold for post in result.posteriors],
        }
        if result.aggregation_method == "ebmom_hierarchical":
            alpha_hat = float(provenance["alpha_hat"])  # type: ignore[arg-type]
            beta_hat = float(provenance["beta_hat"])  # type: ignore[arg-type]
            heterogeneity = provenance["heterogeneity_test"]
            critical = float(heterogeneity["critical_order_statistic"])  # type: ignore[index]
            entry["alpha_hat"] = alpha_hat
            entry["beta_hat"] = beta_hat
            entry["diagnostics"] = provenance["admitted_bootstrap"]
            entry["plugin"] = _plugin_tail_probabilities(clauses, alpha_hat, beta_hat)
            entry["prototype"] = _admission_conditioned_probs(
                clauses, alpha_hat, beta_hat, critical, _prototype_seed(world)
            )[0]
        scored[world] = entry
    return scored


# ---------------------------------------------------------------------------
# The guard: the cell is on the path it claims to be on
# ---------------------------------------------------------------------------


def test_the_four_named_worlds_reach_the_admitted_path(
    named_worlds: dict[int, dict[str, Any]],
) -> None:
    """REFUSAL GUARD for the kill assertion below.

    A mutant that made these worlds REFUSED would empty the admitted cell, and
    an empty cell passes the kill assertion trivially. The kill would then be
    read as evidence about the mechanism when it was evidence about admission.
    """
    methods = {world: entry["method"] for world, entry in named_worlds.items()}
    assert set(methods.values()) == {"ebmom_hierarchical"}, (
        "the four worlds v2 section 0.5 names as ADMITTED FAIL worlds did not all "
        f"reach the admitted path: {methods}. The admitted 6c cell below is then "
        "about something other than the admitted path."
    )


def test_the_fitted_concentration_matches_the_registered_fit(
    named_worlds: dict[int, dict[str, Any]],
) -> None:
    """Every probability below is conditional on the fit that produced it.

    v2 section 0.5 records the fitted concentration per world. If it moved, a
    reproduced tail probability would be a coincidence rather than a
    reproduction, so the fit is pinned before the tails are.
    """
    for world, expected in REFERENCE_CONCENTRATION.items():
        entry = named_worlds[world]
        concentration = entry["alpha_hat"] + entry["beta_hat"]
        assert round(concentration, 1) == expected, (
            f"world {world}: fitted concentration {concentration:.4f} rounds to "
            f"{round(concentration, 1)}, v2 section 0.5 records {expected}"
        )


# ---------------------------------------------------------------------------
# The port: bit-level identity with the reference implementation
# ---------------------------------------------------------------------------


def test_the_mechanism_reproduces_the_prototype_under_the_prototype_seed(
    named_worlds: dict[int, dict[str, Any]],
) -> None:
    """The port is proto_pb.py's arithmetic, to four decimal places.

    Driven with the seed the prototype used, the built mechanism must return the
    prototype's probabilities. A verdict-level comparison cannot make this
    claim: a paraphrase with a different draw order agrees on every verdict here
    and still is not the procedure v2 measured. Four decimal places on a
    200-draw average is an identity claim, not a tolerance.
    """
    for world, expected in REFERENCE_TAILS.items():
        entry = named_worlds[world]
        clause_ids = [clause.clause_id for clause in entry["clauses"]]
        index = clause_ids.index(expected["clause_id"])
        got = entry["prototype"][index]
        assert round(got, 4) == expected["class2"], (
            f"world {world} clause {expected['clause_id']}: the built mechanism under "
            f"the prototype's seed returned {got!r}, which rounds to {round(got, 4)}; "
            f"proto_pb.py returns {expected['class2']}. The port has stopped being the "
            "reference arithmetic."
        )


def test_the_plugin_tail_matches_the_registered_diagnosis(
    named_worlds: dict[int, dict[str, Any]],
) -> None:
    """The plug-in column of v2 section 0.5, independently pinned.

    These four numbers come from world_diag.py rather than from proto_pb.py, so
    they cannot drift together with the class-2 column above. They are also what
    the mutant restores, which makes them the control's subject.
    """
    for world, expected in REFERENCE_TAILS.items():
        entry = named_worlds[world]
        clause_ids = [clause.clause_id for clause in entry["clauses"]]
        index = clause_ids.index(expected["clause_id"])
        got = entry["plugin"][index]
        assert round(got, 4) == expected["plugin"], (
            f"world {world} clause {expected['clause_id']}: plug-in tail {got!r} rounds "
            f"to {round(got, 4)}, v2 section 0.5 records {expected['plugin']}"
        )


def test_the_built_path_decides_the_named_worlds_as_the_reference_does(
    named_worlds: dict[int, dict[str, Any]],
) -> None:
    """Production's own seed reaches the reference's verdicts.

    The production seed is a different integer from the prototype's and draws a
    different stream, so this is a claim the test above does not make: that the
    verdicts v2 section 0.5 records survive the seed the build is obliged to
    use. 255, 316 and 600 UNDECIDED; 783 FAIL.
    """
    for world, expected in REFERENCE_TAILS.items():
        entry = named_worlds[world]
        clause_ids = [clause.clause_id for clause in entry["clauses"]]
        index = clause_ids.index(expected["clause_id"])
        got = _MATRIX.decision(entry["built"][index])
        assert got == expected["class2_decision"], (
            f"world {world} clause {expected['clause_id']}: the built path decided "
            f"{got}, the reference decides {expected['class2_decision']} at "
            f"P = {entry['built'][index]!r}"
        )


def test_the_two_seeds_agree_on_every_decision_and_differ_only_in_the_third_decimal(
    named_worlds: dict[int, dict[str, Any]],
) -> None:
    """The size of the seed difference, measured rather than assumed.

    The production seed and the prototype seed draw different streams, so the
    probabilities differ. What must NOT differ is any decision: if the mechanism
    were so noisy at S = 200 that the seed changed verdicts, the reproduction
    claims above would be about one stream rather than about the procedure. The
    bound is asserted loosely and the decision agreement exactly, because the
    first is a property of Monte Carlo error and the second is the claim.
    """
    for world, entry in named_worlds.items():
        built = entry["built"]
        prototype = entry["prototype"]
        flips = [
            (clause.clause_id, _MATRIX.decision(a), _MATRIX.decision(b))
            for clause, a, b in zip(entry["clauses"], built, prototype, strict=True)
            if _MATRIX.decision(a) != _MATRIX.decision(b)
        ]
        assert not flips, (
            f"world {world}: the production seed and the prototype seed disagree on "
            f"{len(flips)} decision(s): {flips[:5]}. At S = "
            f"{ADMITTED_BOOTSTRAP_DRAWS} the mechanism is then too noisy for the "
            "reproduction claims in this file to be about the procedure."
        )
        gap = max(abs(a - b) for a, b in zip(built, prototype, strict=True))
        assert gap < 0.05, (
            f"world {world}: the two seeds' probabilities differ by up to {gap!r}, "
            "which is larger than the Monte Carlo error this mechanism was measured "
            "to carry"
        )


# ---------------------------------------------------------------------------
# Mutant 4 of v2 section 7
# ---------------------------------------------------------------------------


def test_mutant_4_low_heterogeneity_admitted_false_fail_rate(
    named_worlds: dict[int, dict[str, Any]],
) -> None:
    """KILL ASSERTION for mutant 4 of v2 section 7.

    The admitted 6c cell of low_heterogeneity on the burned root, one decision
    per world, must not reject the registered exact binomial. Under the plug-in
    it is three false of four and rejects at p = 4.8e-4; the mechanism widens
    the tails and leaves one FAIL standing.

    The cell is sparse, and v2 section 5 is explicit about what a sparse pass is
    worth: a lane that makes one claim passes too. This assertion is a kill
    detector, not a demonstration that the mechanism is calibrated.
    """
    cells = {
        world: _fail_entries(entry["built"], entry["clauses"], entry["truths"])
        for world, entry in named_worlds.items()
    }
    false_count, clusters = _select_one_decision_per_world(cells, "6c")
    rejects, p_value = _exact_binomial_rejects(false_count, clusters)
    assert not rejects, (
        "ADMITTED_PATH_FALSE_FAIL_RATE_REJECTS on low_heterogeneity: "
        f"{false_count} of {clusters} selected FAIL decisions are false, exact "
        f"binomial p={p_value!r} < {KILL_LEVEL} against null p={KILL_NULL_P}. This is "
        "the signature of the admission-conditioned bootstrap having been removed and "
        "the plug-in posterior restored on the admitted path."
    )


def test_control_plugin_admitted_path_rejects_on_the_same_worlds(
    named_worlds: dict[int, dict[str, Any]],
) -> None:
    """POSITIVE CONTROL for the kill assertion above.

    The assertion above passes on a cell with no decisions in it, which is
    exactly how a detector comes to accept any output. On the SAME fits, the
    plug-in posterior the mutant restores mints three false FAILs of four and
    the same test rejects. So the test can fire, these worlds can produce the
    condition, and what stops it is the mechanism.

    This is also what keeps the borrowed cell membership honest. The claim that
    these four worlds are the whole cell at R = 1000 comes from v2 section 0.5,
    not from this file; if the plug-in stopped producing exactly that cell on
    them, this control fails rather than the kill above passing quietly.
    """
    cells = {
        world: _fail_entries(entry["plugin"], entry["clauses"], entry["truths"])
        for world, entry in named_worlds.items()
    }
    false_count, clusters = _select_one_decision_per_world(cells, "6c")
    rejects, p_value = _exact_binomial_rejects(false_count, clusters)
    assert clusters == len(NAMED_WORLDS), (
        f"the plug-in minted FAIL decisions in {clusters} of {len(NAMED_WORLDS)} named "
        "worlds; v2 section 0.5 records one per world, so the borrowed cell no longer "
        "describes this code and the kill assertion is unproven"
    )
    assert false_count == 3, (
        f"the plug-in cell is {false_count} false of {clusters}; v2 section 4 records 3 "
        "of 4 (world 255 carries the one true FAIL). The borrowed cell no longer "
        "describes this code."
    )
    assert rejects, (
        "CONTROL_DID_NOT_FIRE: the plug-in was expected to reject the registered kill "
        f"on low_heterogeneity, got {false_count} of {clusters} false with "
        f"p={p_value!r} >= {KILL_LEVEL}. Until it fires, the kill assertion above "
        "cannot be read as evidence that the mechanism is what prevents the false "
        "FAILs."
    )
    assert p_value is not None and math.isclose(p_value, 4.8125e-4, rel_tol=1e-6), (
        f"the registered arithmetic of v2 section 4 gives p = 4.8e-4 for 3 of 4; got {p_value!r}"
    )


# ---------------------------------------------------------------------------
# The seed, the typed fallback, and the divergence the receipt has to declare
# ---------------------------------------------------------------------------


def test_the_bootstrap_seed_is_a_function_of_the_data_and_a_distinct_label() -> None:
    """Determinism, and the two streams are not the same stream.

    fit_skill promises determinism and this mechanism samples, so the seed must
    be a function of the input alone. It must also differ from the admission
    test's seed on the same data: sharing one would make the mechanism resample
    the stream the admission test already consumed, which is a dependence
    neither the specification nor the reproduction accounts for.
    """
    clauses = [
        ClauseObservations.bernoulli(clause_id=f"c{i:02d}", w=10.0 + i, n=25) for i in range(12)
    ]
    again = [
        ClauseObservations.bernoulli(clause_id=f"c{i:02d}", w=10.0 + i, n=25) for i in range(12)
    ]
    assert _admitted_bootstrap_seed(clauses) == _admitted_bootstrap_seed(again)
    assert _admitted_bootstrap_seed(clauses) != _bootstrap_seed(clauses)

    moved = [*clauses[:-1], ClauseObservations(clause_id="c11", w=21.5, n=25, sum_sq=21.0)]
    assert _admitted_bootstrap_seed(moved) != _admitted_bootstrap_seed(clauses), (
        "the seed must cover sum_sq: two clause sets differing only in tie composition "
        "are different data and must not share a draw stream"
    )


def test_an_empty_draw_budget_falls_back_to_the_plugin_and_counts_it() -> None:
    """The typed fallback, exercised rather than described.

    Admission conditioning can reject every candidate draw. The mechanism then
    has nothing to average and returns the PLUG-IN probabilities with
    ``fell_back_to_plugin`` true, rather than inventing a decision from an empty
    average. The critical order statistic is set past anything a draw can reach,
    which is the only way to reach this branch deterministically.
    """
    clauses = [
        ClauseObservations.bernoulli(clause_id=f"c{i:02d}", w=12.0 + (i % 7), n=25)
        for i in range(30)
    ]
    unreachable_critical_value = 1e9
    probabilities, diagnostics = _admission_conditioned_probs(
        clauses, 6.0, 4.0, unreachable_critical_value, 1234
    )
    assert diagnostics["fell_back_to_plugin"] is True
    assert diagnostics["kept"] == 0
    assert diagnostics["used"] == 0
    assert diagnostics["exhausted"] is True
    assert diagnostics["below_crit"] == diagnostics["drawn"]
    assert probabilities == _plugin_tail_probabilities(clauses, 6.0, 4.0)


def test_a_reachable_budget_keeps_the_target_and_reports_no_fallback() -> None:
    """The negative control for the fallback test above.

    Without it, a mechanism that ALWAYS fell back would pass that test and every
    verdict claim in this file would be about the plug-in.
    """
    clauses = [
        ClauseObservations.bernoulli(clause_id=f"c{i:02d}", w=12.0 + (i % 7), n=25)
        for i in range(30)
    ]
    probabilities, diagnostics = _admission_conditioned_probs(clauses, 6.0, 4.0, -1.0, 1234)
    assert diagnostics["fell_back_to_plugin"] is False
    assert diagnostics["exhausted"] is False
    assert diagnostics["used"] == ADMITTED_BOOTSTRAP_DRAWS
    assert probabilities != _plugin_tail_probabilities(clauses, 6.0, 4.0)


def test_the_reported_tail_is_the_mixture_and_not_the_reported_betas(
    named_worlds: dict[int, dict[str, Any]],
) -> None:
    """The declared inconsistency, pinned so it cannot be closed by accident.

    On the admitted path ``p_win_gt_threshold`` is the tail of a mixture over S
    hyperparameter draws, and no single Beta carries it. The reported
    ``posterior_alpha``/``posterior_beta`` are the plug-in posterior the
    mechanism integrates around, kept rather than replaced by a moment-matched
    stand-in that the run never used. So the two DO disagree, by construction,
    and a reader of a receipt has to be told which one decided.

    If a later change quietly made them agree again, that would mean the
    mechanism had stopped reaching the decision, and this test is what says so.
    """
    disagreements = 0
    for entry in named_worlds.values():
        for posterior in entry["result"].posteriors:
            plugin_tail = float(
                beta_dist.sf(
                    WIN_RATE_THRESHOLD, posterior.posterior_alpha, posterior.posterior_beta
                )
            )
            if not math.isclose(plugin_tail, posterior.p_win_gt_threshold, rel_tol=1e-9):
                disagreements += 1
    assert disagreements > 0, (
        "p_win_gt_threshold equals sf(threshold, posterior_alpha, posterior_beta) on "
        "every clause of all four worlds, so the admitted path is deciding on the "
        "plug-in posterior and the mechanism is not reaching the decision"
    )


def test_the_refused_path_is_untouched_by_this_ticket() -> None:
    """Criterion: refused-path cells are unchanged; form B is shared.

    A refused world must still be decided by form B alone -- the same pooled
    posterior, the same locked rule -- and must carry no admitted-bootstrap
    provenance, because the mechanism is admitted-path-only. The check is an
    identity against form B recomputed from provenance, not a comparison against
    a stored number, so it stays true if the world generator ever moves.
    """
    regime = next(r for r in _MATRIX.REGIMES if r.name == "tie_heavy_null")
    clauses, _truths = _MATRIX.draw_world(regime, _MATRIX.derive_seed(SMOKE_ROOT, regime.name, 0))
    result = fit_skill(clauses)

    assert result.aggregation_method == "bounded_pooling_refused", (
        "tie_heavy_null world 0 on the smoke root was expected to refuse; it reached "
        f"{result.aggregation_method}, so this case measures the wrong path"
    )
    provenance = result.aggregation_provenance
    assert "admitted_bootstrap" not in provenance, (
        "the refused path recorded admitted-bootstrap provenance, so the mechanism ran "
        "somewhere it must not"
    )

    pooling = provenance["bounded_pooling"]
    assert pooling["reverted_to_unpooled"] is False, (  # type: ignore[index]
        "this world reverted to unpooled, so it does not exercise form B's pooled "
        "posterior and cannot show it is unchanged"
    )
    mu = float(pooling["mu"])  # type: ignore[index]
    c_bound = float(pooling["c_bound"])  # type: ignore[index]
    for posterior, clause in zip(result.posteriors, clauses, strict=True):
        expected_tail = float(
            beta_dist.sf(
                WIN_RATE_THRESHOLD,
                mu * c_bound + clause.w,
                (1.0 - mu) * c_bound + (clause.n - clause.w),
            )
        )
        assert posterior.p_win_gt_threshold == expected_tail, (
            f"clause {clause.clause_id}: the refused path reported "
            f"{posterior.p_win_gt_threshold!r} where form B gives {expected_tail!r}"
        )
