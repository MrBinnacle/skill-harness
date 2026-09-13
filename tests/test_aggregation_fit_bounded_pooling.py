"""Form B on the refused path: continuity, the typed revert, and mutant 1.

Specification: docs/assurance/ebmom-peel-preregistration-amendment-v2.md
sections 3 and 7, FROZEN 2026-09-05 (S414). Reference implementation of the
pooled form: ``bounded_c`` and the ``cand_bpB`` column of ``rescore405.py`` in
docs/assurance/reference/ebmom-class2-S414/.

Three things are pinned here.

Continuity across the admission boundary
----------------------------------------
Form B was selected over form A partly because its bound IS the admission
test's critical order statistic, so the estimator does not jump at the point
where the admission verdict flips. A discontinuity there would mean two worlds
that differ by an arbitrarily small amount in the observed statistic get
materially different shrinkage, and the per-path rates v2 section 2 measures
would carry that artefact.

The two cases below hold the DATA fixed and move only the boundary the
admission test reports, because that is the only way to make the comparison
exact: the critical order statistic is a function of the data, so two genuinely
different worlds have two different boundaries and could only ever be compared
approximately. The estimator is never patched. What is patched is the recorded
boundary and the admitted flag, which is exactly the pair that differs between
a world just above the critical value and a world just below it.

The typed revert
----------------
A non-positive c_bound has no proper Beta behind it, so the fit reverts to the
unpooled posterior. v2 section 3 requires that revert to be typed and counted
rather than silent, because a run whose refused path silently degraded to the
retired fallback would report form-B numbers that form B did not produce.

Mutant 1 of v2 section 7
-------------------------
"Pooling removed on the refused path (revert to unpooled): killed by the
tie_heavy_null refused 6c assertion (251 of 251 false at R = 1000; any R above
40 suffices)."

Every clause of the registered ``tie_heavy_null`` regime has true encoded mean
0.65, above the 0.60 threshold, so every FAIL on that regime is false by
construction. The unpooled fallback mints them; form B mints none. The kill
assertion is ``test_mutant_1_tie_heavy_null_refused_false_fail_rate``, and
``test_control_unpooled_refused_path_rejects_on_the_same_worlds`` is the
positive control that proves it is not passing vacuously: on the SAME worlds,
the retired procedure rejects at the same test.

Root: SMOKE_NOT_CONFIRMATORY, R = 41. A development smoke, deliberately not
the burned confirmatory root, and deliberately above the R = 40 the spec names
as sufficient. Nothing here is a confirmatory result.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import math
import random
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from scipy.stats import binomtest  # type: ignore[import-untyped]

from skill_harness.aggregation import fit as fit_module
from skill_harness.aggregation.fit import (
    VAR_FLOOR,
    ClauseObservations,
    _bounded_pooling_concentration,
    _HeterogeneityTest,
    fit_skill,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent

ROOT_SEED = "SMOKE_NOT_CONFIRMATORY"
REPLICATES = 41
KILL_NULL_P = 0.05
KILL_LEVEL = 0.01


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


def _heterogeneous_clauses() -> list[ClauseObservations]:
    """K=20, n=50, a spread wide enough that the peeled variance is well clear
    of the arithmetic floor. Used only as a carrier for the boundary cases."""
    pairs = [(20.0 + 1.5 * i, 50) for i in range(20)]
    return [
        ClauseObservations.bernoulli(clause_id=f"c{i:02d}", w=w, n=n)
        for i, (w, n) in enumerate(pairs)
    ]


def _pin_boundary(
    monkeypatch: pytest.MonkeyPatch,
    *,
    admitted: bool,
    scale: float = 1.0,
    absolute: float | None = None,
) -> None:
    """Report a chosen critical order statistic and admission verdict.

    The real test runs; only its recorded boundary and verdict are replaced.
    The peel, the moment inversion and the posterior construction are the
    production ones throughout.
    """
    original = fit_module._heterogeneity_test

    def _patched(clauses: list[ClauseObservations], latent_var_raw: float) -> _HeterogeneityTest:
        real = original(clauses, latent_var_raw)
        crit = absolute if absolute is not None else real.statistic * scale
        return dataclasses.replace(real, critical_order_statistic=crit, admitted=admitted)

    monkeypatch.setattr(fit_module, "_heterogeneity_test", _patched)


class TestAdmissionBoundaryContinuity:
    """Continuity of the SHRINKAGE, which is what v2 section 3 claims.

    Section 3's continuity argument is about the pooled posterior: "a fit
    admitted at the boundary and a fit refused at the boundary shrink
    identically", because form B inverts the moment map at the same critical
    order statistic the admitted branch would have inverted at. That property is
    unchanged and is asserted below on `posterior_alpha` and `posterior_beta`.

    The DECISION quantity is a different matter since v2 section 4 landed
    (#442). The admitted path no longer decides on the tail of that posterior; it
    decides on the tail averaged over admission-conditioned draws of the
    hyperparameters, and the refused path plugs in. So `p_win_gt_threshold` IS
    discontinuous at the admission boundary, by construction, and the case below
    asserts that rather than the equality it used to assert. This is a real
    consequence of section 4 and it is recorded here rather than left for a
    reader to discover: the continuity that motivated form B's selection is the
    shrinkage's, and it does not extend to the decision.
    """

    def test_shrinkage_matches_exactly_at_the_admission_boundary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A world sitting exactly on the critical value shrinks the same way
        whichever side of the admission verdict it lands on."""
        clauses = _heterogeneous_clauses()

        _pin_boundary(monkeypatch, admitted=True, scale=1.0)
        admitted = fit_skill(clauses)
        _pin_boundary(monkeypatch, admitted=False, scale=1.0)
        refused = fit_skill(clauses)

        assert admitted.aggregation_method == "ebmom_hierarchical"
        assert refused.aggregation_method == "bounded_pooling_refused"

        for lhs, rhs in zip(admitted.posteriors, refused.posteriors, strict=True):
            assert lhs.clause_id == rhs.clause_id
            assert lhs.posterior_alpha == rhs.posterior_alpha, (
                f"ESTIMATOR_DISCONTINUOUS_AT_ADMISSION for {lhs.clause_id}: "
                f"admitted alpha {lhs.posterior_alpha!r} != refused {rhs.posterior_alpha!r}"
            )
            assert lhs.posterior_beta == rhs.posterior_beta
            assert lhs.posterior_mean == rhs.posterior_mean
            assert lhs.credible_interval_lo == rhs.credible_interval_lo
            assert lhs.credible_interval_hi == rhs.credible_interval_hi

    def test_the_decision_quantity_is_discontinuous_at_the_boundary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The section 4 consequence, asserted rather than left implicit.

        The same data on the two sides of the admission verdict yields the same
        posterior and a DIFFERENT decision probability, because the admitted side
        integrates over hyperparameter uncertainty and the refused side plugs in.
        If this ever stopped being true, the mechanism would have stopped
        reaching the admitted decision, and the equality above would be hiding
        it.
        """
        clauses = _heterogeneous_clauses()

        _pin_boundary(monkeypatch, admitted=True, scale=1.0)
        admitted = fit_skill(clauses)
        _pin_boundary(monkeypatch, admitted=False, scale=1.0)
        refused = fit_skill(clauses)

        differing = [
            lhs.clause_id
            for lhs, rhs in zip(admitted.posteriors, refused.posteriors, strict=True)
            if lhs.p_win_gt_threshold != rhs.p_win_gt_threshold
        ]
        assert differing, (
            "the admitted and refused decision probabilities agree on every clause "
            "at the admission boundary, so the admission-conditioned bootstrap is not "
            "reaching the admitted decision"
        )

    def test_shrinkage_is_continuous_just_above_and_just_below(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One world just above the critical value and one just below it.

        Above: the statistic exceeds the boundary, the fit is admitted, and it
        inverts the moment map at the observed latent variance. Below: the
        statistic falls short, the fit is refused, and it inverts at the
        boundary. As the gap closes the two must converge, and at a relative
        gap of 1e-9 they agree to well inside 1e-6.

        The comparison is of the POSTERIOR, not of the decision probability. See
        this class's docstring: since v2 section 4 the admitted path decides on
        an integrated tail and the refused path on a plug-in tail, so the two
        decision probabilities do not converge as the gap closes and asserting
        that they do would be asserting the mechanism away.
        """
        clauses = _heterogeneous_clauses()
        eps = 1e-9

        _pin_boundary(monkeypatch, admitted=True, scale=1.0 - eps)
        just_above = fit_skill(clauses)
        _pin_boundary(monkeypatch, admitted=False, scale=1.0 + eps)
        just_below = fit_skill(clauses)

        assert just_above.aggregation_method == "ebmom_hierarchical"
        assert just_below.aggregation_method == "bounded_pooling_refused"

        for lhs, rhs in zip(just_above.posteriors, just_below.posteriors, strict=True):
            assert lhs.posterior_alpha == pytest.approx(rhs.posterior_alpha, rel=1e-6)
            assert lhs.posterior_beta == pytest.approx(rhs.posterior_beta, rel=1e-6)
            assert lhs.posterior_mean == pytest.approx(rhs.posterior_mean, abs=1e-6)

    def test_a_wider_gap_moves_the_estimator_so_the_agreement_is_not_trivial(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Control for the case above: the agreement must come from the gap
        being small, not from the two branches being insensitive to it."""
        clauses = _heterogeneous_clauses()

        _pin_boundary(monkeypatch, admitted=True, scale=1.0)
        at_boundary = fit_skill(clauses)
        _pin_boundary(monkeypatch, admitted=False, scale=2.0)
        far_below = fit_skill(clauses)

        differences = [
            abs(lhs.posterior_alpha - rhs.posterior_alpha)
            for lhs, rhs in zip(at_boundary.posteriors, far_below.posteriors, strict=True)
        ]
        assert max(differences) > 1e-3, (
            "doubling the bound left the posteriors unchanged, so the continuity "
            f"assertion above cannot see a discontinuity either: max diff {max(differences)!r}"
        )


class TestUnpooledRevert:
    def test_non_positive_c_bound_reverts_and_is_counted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bound above the largest variance a Beta with this mean can carry
        leaves no proper Beta, so the fit reverts and says so."""
        clauses = _heterogeneous_clauses()
        _pin_boundary(monkeypatch, admitted=False, absolute=0.5)
        result = fit_skill(clauses)

        pooling = result.aggregation_provenance["bounded_pooling"]
        assert isinstance(pooling, dict)
        assert pooling["c_bound"] is None
        assert pooling["reverted_to_unpooled"] is True
        assert pooling["unpooled_revert_count"] == 1, (
            "the revert must be COUNTED, not only flagged: a harness sums this column "
            "over worlds to report the revert count v2 section 3 requires"
        )
        assert all(not post.is_shrunken for post in result.posteriors)
        for post, clause in zip(result.posteriors, clauses, strict=True):
            assert post.posterior_alpha == pytest.approx(1.0 + clause.w)
            assert post.posterior_beta == pytest.approx(1.0 + (clause.n - clause.w))

    def test_a_bound_at_the_arithmetic_floor_reverts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """VAR_FLOOR guards the division, exactly as it does inside _ebmom.

        It is an arithmetic epsilon and never an admission rule: the admission
        decision was already made, and reverting here only decides which
        posterior a refused fit reports.
        """
        clauses = _heterogeneous_clauses()
        _pin_boundary(monkeypatch, admitted=False, absolute=VAR_FLOOR)
        result = fit_skill(clauses)
        pooling = result.aggregation_provenance["bounded_pooling"]
        assert isinstance(pooling, dict)
        assert pooling["reverted_to_unpooled"] is True

    def test_the_revert_predicate_matches_the_vendored_reference(self) -> None:
        """_bounded_pooling_concentration must agree with bounded_c in
        rescore405.py, which produced v2 section 0's cand_bpB numbers."""
        cases = [
            (0.65, 0.01),
            (0.65, 0.2275),  # mu (1 - mu) exactly: c_bound == 0, non-positive
            (0.65, 0.5),
            (0.65, VAR_FLOOR),
            (0.65, VAR_FLOOR / 2.0),
            (0.65, 0.0),
            (0.0, 0.01),
            (1.0, 0.01),
        ]
        for mu, v_bound in cases:
            got = _bounded_pooling_concentration(mu, v_bound)
            if v_bound <= VAR_FLOOR:
                expected: float | None = None
            else:
                candidate = mu * (1.0 - mu) / v_bound - 1.0
                if candidate <= 0.0 or mu * candidate <= 0.0 or (1.0 - mu) * candidate <= 0.0:
                    expected = None
                else:
                    expected = candidate
            assert got == expected, f"mu={mu} v_bound={v_bound}: got {got!r} want {expected!r}"


# ---------------------------------------------------------------------------
# Mutant 1 of v2 section 7: pooling removed on the refused path
# ---------------------------------------------------------------------------


def _select_one_decision_per_world(
    per_world: dict[int, list[tuple[str, bool]]], row: str
) -> tuple[int, int]:
    """v2 section 2.1: one decision per world, chosen by a seeded draw.

    Returns (false_count, G). The seed is SHA-256 over
    ``<root>|<regime>|<world>|<row>``, first 8 bytes big-endian, feeding
    random.Random, choosing uniformly among that world's decisions of the row's
    kind sorted by clause_id. Fixed by the root before any decision exists.
    """
    false_count = 0
    clusters = 0
    for world in sorted(per_world):
        entries = sorted(per_world[world])
        if not entries:
            continue
        clusters += 1
        material = f"{ROOT_SEED}|tie_heavy_null|{world}|{row}"
        seed = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")
        chosen = random.Random(seed).choice(entries)
        if chosen[1]:
            false_count += 1
    return false_count, clusters


def _exact_binomial_rejects(false_count: int, clusters: int) -> tuple[bool, float | None]:
    """The registered kill: one-sided exact binomial, null 0.05, level 0.01.

    A cell with no decisions of its kind is NOT TESTABLE and never passed, so
    it returns (False, None) and the caller says which it got.
    """
    if clusters == 0:
        return False, None
    p_value = float(binomtest(false_count, clusters, KILL_NULL_P, alternative="greater").pvalue)
    return p_value < KILL_LEVEL, p_value


@pytest.fixture(scope="module")
def tie_heavy_null_refused_cells() -> dict[str, Any]:
    """Score tie_heavy_null once, both ways, on the same worlds.

    ``form_b`` is what the built fit_skill decides. ``unpooled`` is the retired
    fallback scored on the identical worlds, which is the positive control: the
    mutant makes form_b become unpooled, so the control must reject where the
    kill assertion does not.
    """
    regime = next(r for r in _MATRIX.REGIMES if r.name == "tie_heavy_null")
    form_b: dict[int, list[tuple[str, bool]]] = {}
    unpooled: dict[int, list[tuple[str, bool]]] = {}
    refused_worlds = 0

    for world in range(REPLICATES):
        clauses, truths = _MATRIX.draw_world(
            regime, _MATRIX.derive_seed(ROOT_SEED, regime.name, world)
        )
        result = fit_skill(clauses)
        if result.aggregation_method == "ebmom_hierarchical":
            continue
        refused_worlds += 1

        form_b[world] = []
        unpooled[world] = []
        for post, clause, truth in zip(result.posteriors, clauses, truths, strict=True):
            if _MATRIX.decision(post.p_win_gt_threshold) == "FAIL":
                form_b[world].append((clause.clause_id, truth > _MATRIX.WIN_RATE_THRESHOLD))
            raw = float(
                _MATRIX.beta_dist.sf(
                    _MATRIX.WIN_RATE_THRESHOLD,
                    1.0 + clause.w,
                    1.0 + (clause.n - clause.w),
                )
            )
            if _MATRIX.decision(raw) == "FAIL":
                unpooled[world].append((clause.clause_id, truth > _MATRIX.WIN_RATE_THRESHOLD))

    return {"form_b": form_b, "unpooled": unpooled, "refused_worlds": refused_worlds}


@pytest.mark.slow
def test_the_regime_reaches_the_refused_path_at_all(
    tie_heavy_null_refused_cells: dict[str, Any],
) -> None:
    """Guard against a vacuous kill: if no world were refused, the cell below
    would be empty for a reason that has nothing to do with pooling."""
    assert tie_heavy_null_refused_cells["refused_worlds"] == REPLICATES, (
        "tie_heavy_null is a homogeneous regime and every replicate must be refused; "
        f"got {tie_heavy_null_refused_cells['refused_worlds']} of {REPLICATES}"
    )


@pytest.mark.slow
def test_mutant_1_tie_heavy_null_refused_false_fail_rate(
    tie_heavy_null_refused_cells: dict[str, Any],
) -> None:
    """KILL ASSERTION for mutant 1 of v2 section 7.

    Every clause of tie_heavy_null has true encoded mean 0.65, so every FAIL is
    false. Form B mints none, and if it minted them at the rate the unpooled
    fallback does, the registered exact binomial rejects.
    """
    false_count, clusters = _select_one_decision_per_world(
        tie_heavy_null_refused_cells["form_b"], "6c"
    )
    rejects, p_value = _exact_binomial_rejects(false_count, clusters)
    assert not rejects, (
        "REFUSED_PATH_FALSE_FAIL_RATE_REJECTS on tie_heavy_null: "
        f"{false_count} of {clusters} selected FAIL decisions are false, exact binomial "
        f"p={p_value!r} < {KILL_LEVEL} against null p={KILL_NULL_P}. Every clause of this "
        "regime is truly above the threshold, so a FAIL here is false by construction. "
        "This is the signature of pooling having been removed from the refused path."
    )


@pytest.mark.slow
def test_control_unpooled_refused_path_rejects_on_the_same_worlds(
    tie_heavy_null_refused_cells: dict[str, Any],
) -> None:
    """POSITIVE CONTROL for the kill assertion above.

    The assertion above passes on a cell with no decisions in it, which is
    exactly how a detector comes to accept any output. On the same worlds, the
    retired unpooled fallback mints false FAILs and the same test rejects. So
    the test can fire, the regime can produce the condition, and what stops it
    is the pooling.
    """
    false_count, clusters = _select_one_decision_per_world(
        tie_heavy_null_refused_cells["unpooled"], "6c"
    )
    rejects, p_value = _exact_binomial_rejects(false_count, clusters)
    assert clusters > 0, (
        "the retired fallback minted no FAIL on this regime at "
        f"R={REPLICATES}; the control cannot fire and the kill assertion is unproven"
    )
    assert rejects, (
        "CONTROL_DID_NOT_FIRE: the unpooled fallback was expected to reject the "
        f"registered kill on tie_heavy_null, got {false_count} of {clusters} false with "
        f"p={p_value!r} >= {KILL_LEVEL}. Until it fires, the kill assertion above cannot "
        "be read as evidence that pooling is what prevents the false FAILs."
    )
    assert false_count == clusters, (
        "every FAIL on this regime is false by construction (true encoded mean 0.65 "
        f"against a 0.60 threshold), so the selected count must be {clusters}, "
        f"got {false_count}"
    )
    assert math.isfinite(p_value if p_value is not None else 0.0)
