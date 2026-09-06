"""The v2 acceptance matrix: per-path rows 5c and 6c, the one-per-world exact kill, mutants 2 and 3.

Specification: docs/assurance/ebmom-peel-preregistration-amendment-v2.md
sections 2, 2.1, 2.2, 5 and 7, FROZEN 2026-09-05 (S414). Reference
implementation: ``rescore405.py`` for the columns and the per-path tallies and
``clustered_bound.py`` for both tests per cell, in
docs/assurance/reference/ebmom-class2-S414/.

What is pinned here.

The kill test of section 2.1
----------------------------
One decision per decision-bearing world, chosen by a seeded draw fixed by the
root before any decision exists, then a one-sided exact binomial against null
0.05 at level 0.01. The selection material is ``<root>|<regime>|<world>|<row>``,
first eight bytes of SHA-256 big-endian, feeding ``random.Random``, choosing
uniformly among that world's decisions of the row's kind sorted by
``clause_id``. A cell with no decisions of its kind is NOT TESTABLE and is
never reported as passed.

Mutant 2 of section 7
---------------------
"Per-path split removed (rows pooled): killed by an assertion that the
refused-path cell in ``low_heterogeneity`` is reported separately with its own
``G``, and that a pooled-only tally cannot produce it."

The kill assertion is
``test_mutant_2_low_heterogeneity_refused_cell_carries_its_own_G``. Two worlds
of the registered ``low_heterogeneity`` regime are scored through production,
chosen because one reaches the admitted path and the other the refused one.
``test_control_the_pooled_cell_differs_from_both_per_path_cells`` is the
positive control: it requires the pooled tally to be strictly larger than
either path's, so a per-path cell that agreed with the pooled one by accident
could not carry the kill. ``test_the_fixture_worlds_reach_both_paths`` is the
guard: a mutant that sent both worlds down one path would empty a cell and look
like a kill for a reason that has nothing to do with the split.

Mutant 3 of section 7
---------------------
"One-per-world selection replaced by all decisions, on a fixture world with two
correlated false decisions, where the all-decision test rejects and the
registered test does not."

The kill assertion is
``test_mutant_3_two_correlated_false_decisions_do_not_reject``. The fixture is
one world carrying two FAIL decisions, both false. Under the registered test
that is one trial, one false, ``p = 0.05``, which does not reject at level
0.01. Under the all-decision test it is two of two, ``p = 0.0025``, which does.
``test_control_the_all_decision_test_rejects_on_the_same_fixture`` is the
positive control that proves the fixture can fire at all, and
``test_the_fixture_is_one_world_carrying_two_decisions`` is the guard against a
fixture that is discriminating for the wrong reason.

Root: SMOKE_NOT_CONFIRMATORY for the fixtures that need one, and the burned
root only where a cell's membership is quoted from v2 section 0. Nothing here
is a confirmatory result.
"""

from __future__ import annotations

import hashlib
import importlib.util
import random
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from scipy.stats import binomtest  # type: ignore[import-untyped]

from skill_harness.aggregation.fit import ClauseObservations

_REPO_ROOT = Path(__file__).resolve().parent.parent

ROOT_SEED = "SMOKE_NOT_CONFIRMATORY"


def _load_acceptance_matrix() -> ModuleType:
    """Import scripts/ebmom_acceptance_matrix.py by path.

    scripts/ carries no __init__.py and is not a package. The regimes, the
    world generator and the locked rule are taken from the harness rather than
    restated, so a drift between the two shows up as a failure here instead of
    as two implementations that agree with themselves.
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

# The two low_heterogeneity worlds the mutant-2 fixture uses. World 0 is
# refused and world 1 is admitted on the burned root, per the per-world table of
# proto-pb-low_heterogeneity-R4000-f95e4de5.json rows [0, "refused", ...] and
# [1, "admitted", ...]. The guard test re-derives both from production rather
# than trusting the quotation.
BURNED_ROOT = "f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a"
MUTANT_2_WORLDS = (0, 1)


# --- section 2.1: the selection and the exact test ---------------------------


def test_the_selection_material_is_the_frozen_root_regime_world_row() -> None:
    """The seeded draw is a pure function of the root, and fixed before any decision exists."""
    entries = [("c0", False), ("c1", True), ("c2", False)]
    material = f"{ROOT_SEED}|low_heterogeneity|7|6c"
    seed = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")
    expected = random.Random(seed).choice(sorted(entries))

    got = _MATRIX.select_one_decision_per_world(ROOT_SEED, "low_heterogeneity", 7, "6c", entries)

    assert got == expected[1]


def test_the_selection_orders_by_clause_id_and_not_by_arrival() -> None:
    """Sorted by clause_id in Python str order, so the draw does not depend on iteration order."""
    entries = [("c9", True), ("c10", False), ("c1", False)]
    forward = _MATRIX.select_one_decision_per_world(ROOT_SEED, "small_n_bite", 3, "5c", entries)
    reversed_order = _MATRIX.select_one_decision_per_world(
        ROOT_SEED, "small_n_bite", 3, "5c", list(reversed(entries))
    )
    assert forward == reversed_order


def test_a_cell_with_no_decisions_is_not_testable_and_never_passed() -> None:
    """Section 2: a cell with zero decisions of its kind reports not testable, never passed."""
    verdict = _MATRIX.exact_kill_test(selected_false=0, clusters=0)

    assert verdict["testable"] is False
    assert verdict["rejects"] is False
    assert verdict["p_value"] is None
    assert verdict["passes"] is None


def test_the_exact_test_rejects_below_the_registered_level() -> None:
    """Null 0.05, one-sided greater, level 0.01. Two false of two selected rejects."""
    verdict = _MATRIX.exact_kill_test(selected_false=2, clusters=2)

    assert verdict["testable"] is True
    assert verdict["rejects"] is True
    assert verdict["p_value"] == binomtest(2, 2, 0.05, alternative="greater").pvalue


# --- mutant 3: one-per-world selection replaced by all decisions -------------


def _mutant_3_fixture() -> Any:
    """One world of the fixture regime carrying two FAIL decisions, both false.

    The world is synthetic and is fed to the tally directly rather than drawn,
    because what is under test is the tally's arithmetic and not the generator.
    Both decisions are false, and they sit in the same world, which is exactly
    the correlation the one-per-world construction exists to absorb.
    """
    tally = _MATRIX.ColumnTally(
        root_seed=ROOT_SEED, regime_name="low_heterogeneity", replicates=1, world_offset=0
    )
    clauses = [
        ClauseObservations(clause_id="c0", w=20.0, n=25, sum_sq=20.0),
        ClauseObservations(clause_id="c1", w=20.0, n=25, sum_sq=20.0),
    ]
    # Truth above the 0.60 threshold makes a FAIL false, per section 2 row 6c.
    tally.add(
        fitted=["FAIL", "FAIL"],
        oracle=["PASS", "PASS"],
        truths=[0.80, 0.80],
        clauses=clauses,
        path="admitted",
        world=0,
    )
    return tally


def test_the_fixture_is_one_world_carrying_two_decisions() -> None:
    """The guard: a fixture spread over two worlds would not discriminate the two tests."""
    cell = _mutant_3_fixture().cell("6c", "admitted")

    assert cell["decisions"] == 2
    assert cell["false"] == 2
    assert cell["G"] == 1
    assert cell["g"] == 1


def test_control_the_all_decision_test_rejects_on_the_same_fixture() -> None:
    """The positive control: the retired construction DOES reject here, so the kill can fire."""
    cell = _mutant_3_fixture().cell("6c", "admitted")
    all_decision_p = float(
        binomtest(cell["false"], cell["decisions"], 0.05, alternative="greater").pvalue
    )

    assert all_decision_p < _MATRIX.V2_TEST_LEVEL, (
        f"all-decision p = {all_decision_p}; the fixture cannot separate the two tests"
    )


def test_mutant_3_two_correlated_false_decisions_do_not_reject() -> None:
    """KILL for mutant 3. One decision per world: one false of one, p = 0.05, no rejection."""
    cell = _mutant_3_fixture().cell("6c", "admitted")

    assert cell["G"] == 1
    assert cell["selected_false"] == 1
    assert cell["rejects"] is False, (
        f"the registered one-per-world test rejected a cell of one world "
        f"(selected {cell['selected_false']} of {cell['G']}, p = {cell['p_value']}); "
        "two correlated false decisions in one world are one trial, not two"
    )


# --- mutant 2: the per-path split ------------------------------------------


def _mutant_2_tally() -> tuple[Any, dict[int, str]]:
    """Score two burned-root low_heterogeneity worlds through production, per path.

    Two worlds rather than a thousand: what the kill asserts is that the refused
    cell is REPORTED separately with its own G, which one world of each kind
    settles. The rate on such a cell is not a result and is not asserted.
    """
    regime = next(r for r in _MATRIX.REGIMES if r.name == "low_heterogeneity")
    tally = _MATRIX.ColumnTally(
        root_seed=BURNED_ROOT,
        regime_name=regime.name,
        replicates=len(MUTANT_2_WORLDS),
        world_offset=MUTANT_2_WORLDS[0],
    )
    paths: dict[int, str] = {}
    for world in MUTANT_2_WORLDS:
        clauses, truths = _MATRIX.draw_world(
            regime, _MATRIX.derive_seed(BURNED_ROOT, regime.name, world)
        )
        from skill_harness.aggregation.fit import fit_skill

        result = fit_skill(clauses)
        path = "admitted" if result.aggregation_method == "ebmom_hierarchical" else "refused"
        paths[world] = path
        fitted = [_MATRIX.decision(post.p_win_gt_threshold) for post in result.posteriors]
        oracle = _MATRIX.oracle_decisions(regime, clauses)
        tally.add(
            fitted=fitted,
            oracle=oracle,
            truths=truths,
            clauses=clauses,
            path=path,
            world=world,
        )
    return tally, paths


def test_the_fixture_worlds_reach_both_paths() -> None:
    """The guard: both worlds down one path would empty a cell for the wrong reason."""
    _tally, paths = _mutant_2_tally()

    assert set(paths.values()) == {"admitted", "refused"}, (
        f"the two fixture worlds landed on {paths}; the per-path assertion below "
        "would then be about an empty cell rather than about the split"
    )


def test_mutant_2_low_heterogeneity_refused_cell_carries_its_own_G() -> None:
    """KILL for mutant 2. The refused 5c cell is reported separately, with its own G."""
    tally, paths = _mutant_2_tally()
    refused_world = next(w for w, p in paths.items() if p == "refused")
    refused = tally.cell("5c", "refused")
    admitted = tally.cell("5c", "admitted")

    assert refused["G"] == 1, (
        f"the refused 5c cell reports G = {refused['G']} over world {refused_world}; "
        "a tally that pooled the paths cannot report a refused cluster count at all"
    )
    assert refused["decisions"] > 0
    assert admitted["G"] == 1
    assert refused["decisions"] != admitted["decisions"]


def test_control_the_pooled_cell_differs_from_both_per_path_cells() -> None:
    """The positive control: the pooled tally is strictly larger, so neither path is it."""
    tally, _paths = _mutant_2_tally()
    pooled = tally.cell("5c", None)
    refused = tally.cell("5c", "refused")
    admitted = tally.cell("5c", "admitted")

    assert pooled["decisions"] == refused["decisions"] + admitted["decisions"]
    assert pooled["G"] == 2
    assert pooled["decisions"] > refused["decisions"]
    assert pooled["decisions"] > admitted["decisions"]


# --- the kill criterion ------------------------------------------------------


def test_the_kill_criterion_is_a_union_over_every_cell_on_either_path() -> None:
    """Section 5: any rejection in any 5c or 6c cell, on either path, in any regime."""
    cells = {
        ("low_heterogeneity", "admitted", "5c"): {"rejects": False, "testable": True},
        ("low_heterogeneity", "refused", "6c"): {"rejects": True, "testable": True},
        ("tie_heavy_null", "admitted", "6c"): {"rejects": False, "testable": False},
    }

    verdict = _MATRIX.v2_kill_verdict(cells)

    assert verdict["kill_criterion_triggered"] is True
    assert verdict["verdict"] == "REJECTED"
    assert verdict["rejecting_cells"] == [["low_heterogeneity", "refused", "6c"]]


def test_a_run_with_no_rejection_is_not_rejected_and_lists_what_was_not_testable() -> None:
    """A not-testable cell is neither a rejection nor a pass, and it is named."""
    cells = {
        ("low_heterogeneity", "admitted", "5c"): {"rejects": False, "testable": True},
        ("tie_heavy_null", "admitted", "6c"): {"rejects": False, "testable": False},
    }

    verdict = _MATRIX.v2_kill_verdict(cells)

    assert verdict["kill_criterion_triggered"] is False
    assert verdict["verdict"] == "NOT_REJECTED"
    assert verdict["not_testable_cells"] == [["tie_heavy_null", "admitted", "6c"]]


# --- the reported diagnostics of section 2.2 ---------------------------------


def test_the_world_block_bound_matches_the_reference_construction() -> None:
    """The 10th smallest of 999 world-block resample rates, as clustered_bound.py computes it."""
    n_w = [4.0, 0.0, 3.0, 5.0, 0.0, 2.0, 6.0, 1.0]
    f_w = [1.0, 0.0, 0.0, 2.0, 0.0, 0.0, 1.0, 1.0]

    bound = _MATRIX.world_block_bound(
        root_label=ROOT_SEED,
        regime_name="low_heterogeneity",
        column="cand_pb",
        path="admitted",
        row="5c",
        n_w=n_w,
        f_w=f_w,
    )

    reference = _reference_bound(
        ROOT_SEED, "low_heterogeneity", "cand_pb", "admitted", "5c", n_w, f_w
    )
    assert bound["bound_lower_99"] == reference
    assert bound["B"] == 999


def _reference_bound(
    root: str,
    regime: str,
    column: str,
    path: str,
    row: str,
    n_w: list[float],
    f_w: list[float],
) -> float:
    """clustered_bound.py's construction, restated so the harness is checked against it."""
    import numpy as np

    material = "|".join([root, regime, column, path, row])
    seed = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    replicates = len(n_w)
    counts = rng.multinomial(replicates, np.full(replicates, 1.0 / replicates), size=999)
    num = counts @ np.asarray(f_w)
    den = counts @ np.asarray(n_w)
    rates = np.where(den > 0, num / np.where(den > 0, den, 1), 0.0)
    rates.sort()
    return float(rates[9])


def test_the_reliability_table_bins_the_fitted_tail_in_tenths() -> None:
    """Section 2.2 row 9: fitted P(theta > 0.60) in tenths against the empirical frequency."""
    table = _MATRIX.ReliabilityTable()
    table.add([0.05, 0.15, 0.95, 0.96], [0.10, 0.70, 0.80, 0.90])

    rows = table.rows()

    assert len(rows) == 10
    assert rows[0] == {"bin_lo": 0.0, "bin_hi": 0.1, "n": 1, "exceed": 0, "frequency": 0.0}
    assert rows[1] == {"bin_lo": 0.1, "bin_hi": 0.2, "n": 1, "exceed": 1, "frequency": 1.0}
    assert rows[9] == {"bin_lo": 0.9, "bin_hi": 1.0, "n": 2, "exceed": 2, "frequency": 1.0}
    assert rows[5]["n"] == 0
    assert rows[5]["frequency"] is None
