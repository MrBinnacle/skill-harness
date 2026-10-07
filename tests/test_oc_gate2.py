"""Gate-2 seam tests for the pure-math ``skill_harness.oc`` package (#55).

Seam (ratified in spec #49 testing decision 1 — the only NEW seam): pure
functions from registered knobs -> decisions / OC rows, pinned at the
``skill_harness.oc`` public API only. If a decision-relevant behavior can only
be pinned below this API, that is a design smell in the API — deepen it, never
test internals (revisit-if carried from #49).

Gate-2 floor items from the banked prototype suite land here (#42 resolution
record, convention 4): trinomial sum-to-one (v1 T3), harm/benefit symmetry
(v1 T6), and the v3 lattice-curtailment error-identity — extended per #55's
AC with exact-enumeration cross-checks of the lattice DP, dual-MME
conforming-region edge cases, and boundary rows n=6 / n=40.

Expected literals were computed by an INDEPENDENT reference implementation
(exact ``fractions.Fraction`` polygon integration of the Dirichlet posterior
with the INTEGRATION ORDER SWAPPED relative to the production code, exact
trinomial enumeration, v3-style curtailment walk), anchored against a scipy
quadrature third route in (d, q) coordinates and hand-derived closed forms —
never by the code under test. Interval cross-checks are additionally anchored
to PUBLISHED worked examples: Tango score interval [0.139, 0.321] for
(b=2, c=25, N=102) (Duffy-Rothwell continuity-correction study, PMC10763857,
Table 2) and the Newcombe paired interval [0.011, 0.226] for the Altman 2000
thallium-stress table (14/5/0/22) via biostatUZH::confIntPairedProportion.
"""

from __future__ import annotations

import dataclasses

import pytest

from skill_harness.oc import (
    Gate2Decision,
    Gate2Design,
    MMESpec,
    beta_cdf,
    dirichlet_delta_tail,
    gate2_decide,
    gate2_oc,
    gate2_region_probs,
    gate2_worst_false_direction,
    mcnemar_midp,
    newcombe_interval,
    tango_interval,
)

TOL = 1e-12

# The canonical test design: n=16 pairs, gamma=0.9, dual MME (0.2, 0.7).
# All literals below were computed for exactly these knobs by the reference.
_D16 = Gate2Design(n_pairs=16, gamma=0.90, mme=MMESpec(delta_min=0.2, q_min=0.7))
_D6 = dataclasses.replace(_D16, n_pairs=6)
_D40 = dataclasses.replace(_D16, n_pairs=40)


# ---------------------------------------------------------------------------
# Exact Dirichlet net-lift tail (the Gate-2 posterior primitive)
# ---------------------------------------------------------------------------


def test_tail_zero_margin_reduces_to_beta_tail() -> None:
    """At c=0, P(p_f - p_n >= 0) = P(q > 1/2) = 1 - I_.5(a_f, a_n): the
    Dirichlet aggregation identity ties the new primitive to the existing
    exact beta CDF through a completely different computation."""
    for a_f, a_n, a_t in ((1, 1, 1), (3, 2, 5), (6, 2, 12), (2, 6, 12), (10, 4, 30)):
        assert dirichlet_delta_tail(0.0, a_f, a_n, a_t) == pytest.approx(
            1.0 - beta_cdf(0.5, a_f, a_n), abs=TOL
        )


def test_tail_uniform_simplex_closed_form() -> None:
    """Dirichlet(1,1,1) is uniform on the simplex; the tail region is a
    triangle of area (1-c)^2/4 against simplex area 1/2 -> (1-c)^2/2
    (hand-derived)."""
    for c in (0.0, 0.1, 0.3, 0.5, 0.9):
        assert dirichlet_delta_tail(c, 1, 1, 1) == pytest.approx((1 - c) ** 2 / 2, abs=TOL)


def test_tail_reference_literals() -> None:
    """Independent-reference literals (order-swapped exact integration,
    confirmed by scipy quadrature in (d, q) coordinates to <1e-9)."""
    assert dirichlet_delta_tail(0.15, 6, 2, 10) == pytest.approx(0.69668360682312, abs=TOL)
    assert dirichlet_delta_tail(0.2, 3, 1, 4) == pytest.approx(0.5963776, abs=TOL)
    assert dirichlet_delta_tail(0.5, 2, 2, 2) == pytest.approx(0.0546875, abs=TOL)
    assert dirichlet_delta_tail(0.1, 9, 3, 30) == pytest.approx(0.7082452823435612, abs=TOL)
    assert dirichlet_delta_tail(0.2, 2, 1, 17) == pytest.approx(0.04503599627370496, abs=TOL)


def test_tail_edges_and_negative_margin() -> None:
    assert dirichlet_delta_tail(1.0, 3, 2, 4) == 0.0
    assert dirichlet_delta_tail(1.5, 3, 2, 4) == 0.0
    assert dirichlet_delta_tail(-1.0, 3, 2, 4) == 1.0
    # negative margin: complement of the mirrored positive tail
    assert dirichlet_delta_tail(-0.2, 3, 2, 4) == pytest.approx(
        1.0 - dirichlet_delta_tail(0.2, 2, 3, 4), abs=TOL
    )


def test_tail_validation() -> None:
    with pytest.raises(ValueError):
        dirichlet_delta_tail(0.2, 0, 1, 1)
    with pytest.raises(ValueError):
        dirichlet_delta_tail(0.2, 1, -1, 1)
    with pytest.raises(ValueError):
        dirichlet_delta_tail(0.2, 1, 1, 0)


# ---------------------------------------------------------------------------
# Dual-MME registration (#40: BOTH delta_min AND q_min; H1 conjunction)
# ---------------------------------------------------------------------------


def test_mme_validation() -> None:
    with pytest.raises(ValueError):
        MMESpec(delta_min=0.0, q_min=0.7)  # zero margin collapses three-sided
    with pytest.raises(ValueError):
        MMESpec(delta_min=1.0, q_min=0.7)
    with pytest.raises(ValueError):
        MMESpec(delta_min=0.2, q_min=0.5)  # q floor must exceed the coin flip
    with pytest.raises(ValueError):
        MMESpec(delta_min=0.2, q_min=1.0)
    MMESpec(delta_min=0.2, q_min=0.7)  # registered shape constructs


def test_mme_conforming_region_edges() -> None:
    """#55 AC: dual-MME conforming-region edge cases. Boundary points use
    binary-exact floats so >= is tested at true equality."""
    mme = MMESpec(delta_min=0.25, q_min=0.625)
    assert mme.in_h1(1.0, 0.625)  # delta = 0.25 == delta_min, q == q_min
    assert mme.in_h1(0.5, 0.75)  # delta = 0.25 exactly, q above floor
    assert not mme.in_h1(1.0, 0.6249)  # q floor fails alone
    assert not mme.in_h1(0.49, 0.75)  # delta fails alone (0.245 < 0.25)
    assert not mme.in_h1(0.0, 0.99)  # zero discordance never conforms
    assert not mme.in_h1(1.0, 0.4)  # harm direction is not in H1


def test_mme_in_h1_validates_inputs() -> None:
    mme = MMESpec(delta_min=0.2, q_min=0.7)
    with pytest.raises(ValueError):
        mme.in_h1(-0.1, 0.7)
    with pytest.raises(ValueError):
        mme.in_h1(0.5, 1.1)


# ---------------------------------------------------------------------------
# Design validation (#37 rule form; gamma-only confidence knob)
# ---------------------------------------------------------------------------


def test_design_refuses_gamma_at_or_below_half() -> None:
    """The three region probabilities partition to 1, so gamma <= 0.5 admits
    two regions certifying simultaneously (a 0.5/0.5 split fires both) —
    the rule would be order-dependent. Same proof shape as Gate-1's."""
    for gamma in (0.5, 0.3, 1.0, 1.5):
        with pytest.raises(ValueError):
            dataclasses.replace(_D16, gamma=gamma)


def test_design_refuses_bad_n_pairs() -> None:
    with pytest.raises(ValueError):
        dataclasses.replace(_D16, n_pairs=0)


def test_design_is_not_grid_bounded() -> None:
    """The math layer accepts any n >= 1: the #40 grid bounds the FRONTIER
    enumeration (#56), not the engine (same assertion as Gate-1, #54)."""
    assert Gate2Design(n_pairs=3, gamma=0.9, mme=_D16.mme).n_pairs == 3
    assert Gate2Design(n_pairs=55, gamma=0.9, mme=_D16.mme).n_pairs == 55


def test_decision_tokens_are_stable() -> None:
    assert Gate2Decision.BENEFIT.value == "benefit"
    assert Gate2Decision.HARM.value == "harm"
    assert Gate2Decision.EQUIVALENT.value == "equivalent"
    assert Gate2Decision.UNRESOLVED.value == "unresolved"


# ---------------------------------------------------------------------------
# Three-sided decision rule (#37 item 3: Goeman partition, gamma-only)
# ---------------------------------------------------------------------------


def test_decide_zero_discordant_is_defined_unresolved() -> None:
    """#37 locked: zero-discordant is a DEFINED UNRESOLVED branch — even when
    the posterior equivalence mass alone would clear gamma (the companion
    test below pins that the override is real, not vacuous)."""
    assert gate2_decide(_D16, 0, 0) is Gate2Decision.UNRESOLVED
    assert gate2_decide(_D40, 0, 0) is Gate2Decision.UNRESOLVED


def test_zero_discordant_override_is_not_vacuous() -> None:
    """At (0,0), n=16 the raw posterior HAS P_equiv >= gamma; the defined
    branch deliberately overrides it. This discontinuity (k=1 can return
    EQUIVALENT while k=0 cannot) is disclosed in the PR record."""
    probs = gate2_region_probs(_D16, 0, 0)
    assert probs.p_equivalent > _D16.gamma


def test_decide_reference_table() -> None:
    """Decision table from the independent reference (n=16, gamma=0.9,
    delta_min=0.2)."""
    expect = {
        (1, 0): Gate2Decision.EQUIVALENT,
        (8, 0): Gate2Decision.BENEFIT,
        (0, 8): Gate2Decision.HARM,
        (5, 1): Gate2Decision.UNRESOLVED,
        (8, 1): Gate2Decision.UNRESOLVED,
        (2, 2): Gate2Decision.EQUIVALENT,
        (12, 0): Gate2Decision.BENEFIT,
        (16, 0): Gate2Decision.BENEFIT,
        (3, 0): Gate2Decision.UNRESOLVED,
        (6, 2): Gate2Decision.UNRESOLVED,
    }
    for (x_f, x_n), want in expect.items():
        assert gate2_decide(_D16, x_f, x_n) is want, (x_f, x_n)


def test_decide_benefit_harm_mirror() -> None:
    """Swapping (x_f, x_n) swaps BENEFIT and HARM and fixes the other two."""
    swap = {
        Gate2Decision.BENEFIT: Gate2Decision.HARM,
        Gate2Decision.HARM: Gate2Decision.BENEFIT,
        Gate2Decision.EQUIVALENT: Gate2Decision.EQUIVALENT,
        Gate2Decision.UNRESOLVED: Gate2Decision.UNRESOLVED,
    }
    for x_f in range(0, 17, 2):
        for x_n in range(0, 17 - x_f, 3):
            assert gate2_decide(_D16, x_n, x_f) is swap[gate2_decide(_D16, x_f, x_n)]


def test_decide_validates_counts() -> None:
    with pytest.raises(ValueError):
        gate2_decide(_D16, -1, 0)
    with pytest.raises(ValueError):
        gate2_decide(_D16, 0, -1)
    with pytest.raises(ValueError):
        gate2_decide(_D16, 10, 7)  # 17 outcomes from 16 pairs


def test_region_probs_reference_literals() -> None:
    """Posterior region masses, exact-reference literals (n=16 knobs)."""
    cases = {
        (8, 0): (0.9400637500508078, 2.81474976710656e-05, 0.059908102451521124),
        (1, 0): (0.04503599627370496, 0.0036028797018963967, 0.9513611240243987),
        (5, 1): (0.49964623115908546, 0.001970324836974592, 0.49838344400393997),
        (2, 2): (0.04785074604081152, 0.04785074604081152, 0.904298507918377),
        (8, 1): (0.85379002042155, 0.0002885118511284224, 0.1459214677273215),
    }
    for (x_f, x_n), (p_b, p_h, p_e) in cases.items():
        probs = gate2_region_probs(_D16, x_f, x_n)
        assert probs.p_benefit == pytest.approx(p_b, abs=TOL)
        assert probs.p_harm == pytest.approx(p_h, abs=TOL)
        assert probs.p_equivalent == pytest.approx(p_e, abs=TOL)
        assert probs.p_benefit + probs.p_harm + probs.p_equivalent == pytest.approx(1.0, abs=TOL)


# ---------------------------------------------------------------------------
# Exact OC: trinomial enumeration + (x_f, x_n) lattice DP curtailment
# ---------------------------------------------------------------------------

# (d, q, BEN, HARM, EQ, UNRES, E[N]) — independent-reference literals, n=16.
_OC16 = (
    (
        0.5,
        0.5,
        0.003011597553268075,
        0.003011597553268075,
        0.01798248291015625,
        0.9759943219833076,
        11.153299605473876,
    ),
    (
        0.5,
        0.9,
        0.31607647286026996,
        3.3257153440322874e-09,
        0.00423052978515625,
        0.6796929940288584,
        14.035877048429436,
    ),
    (
        0.8,
        0.9,
        0.7896536736037439,
        9.314235157705184e-10,
        2.145000620032e-07,
        0.21034611096477052,
        14.518074058091337,
    ),
    (
        0.2,
        0.9,
        0.003036254999486347,
        5.849055231009695e-11,
        0.22681297603809772,
        0.7701507689039254,
        14.346133671193156,
    ),
    (
        0.8,
        0.1,
        9.314235157705184e-10,
        0.7896536736037439,
        2.145000620032e-07,
        0.21034611096477052,
        14.518074058091337,
    ),
    (0.0, 0.7, 0.0, 0.0, 0.0, 1.0, 16.0),
    (1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 13.0),
    (
        0.75,
        0.5,
        0.007377582076035338,
        0.007377582076035338,
        1.5648663975298405e-05,
        0.985229187183954,
        10.383115561165425,
    ),
)


def test_oc_reference_literals_n16() -> None:
    """#55 AC: exact OC rows pinned against the independent reference
    (fixed-mode enumeration; probabilities are curtailment-invariant)."""
    for d, q, ben, harm, eq, unres, _en in _OC16:
        oc = gate2_oc(_D16, d, q, curtail=False)
        assert oc.p_benefit == pytest.approx(ben, abs=TOL), (d, q)
        assert oc.p_harm == pytest.approx(harm, abs=TOL), (d, q)
        assert oc.p_equivalent == pytest.approx(eq, abs=TOL), (d, q)
        assert oc.p_unresolved == pytest.approx(unres, abs=TOL), (d, q)
        assert oc.curtailed is False
        assert oc.expected_n == pytest.approx(16.0, abs=TOL)  # fixed mode spends all


def test_oc_curtailment_decision_identity_and_expected_n() -> None:
    """v3 floor + #55 AC: curtailed and uncurtailed decide identically (the
    two modes are genuinely different walks — trinomial convolution vs
    per-pair lattice DP), and curtailed E[N] matches the exact reference."""
    for d, q, ben, harm, eq, unres, e_n in _OC16:
        oc = gate2_oc(_D16, d, q)  # curtailment default-on (#37 item 6)
        assert oc.curtailed is True
        assert oc.p_benefit == pytest.approx(ben, abs=TOL), (d, q)
        assert oc.p_harm == pytest.approx(harm, abs=TOL), (d, q)
        assert oc.p_equivalent == pytest.approx(eq, abs=TOL), (d, q)
        assert oc.p_unresolved == pytest.approx(unres, abs=TOL), (d, q)
        assert oc.expected_n == pytest.approx(e_n, abs=TOL), (d, q)
        assert oc.expected_n <= 16.0 + TOL


def test_oc_rows_sum_to_one() -> None:
    """Floor T3 (trinomial sum-to-one) across configs including edges."""
    for d in (0.0, 0.3, 1.0):
        for q in (0.0, 0.5, 1.0):
            for curtail in (True, False):
                oc = gate2_oc(_D16, d, q, curtail=curtail)
                total = oc.p_benefit + oc.p_harm + oc.p_equivalent + oc.p_unresolved
                assert total == pytest.approx(1.0, abs=TOL), (d, q, curtail)


def test_oc_harm_benefit_symmetry() -> None:
    """Floor T6: swapping q -> 1-q swaps BENEFIT/HARM and fixes EQ/UNRES."""
    a = gate2_oc(_D16, 0.5, 0.85)
    b = gate2_oc(_D16, 0.5, 0.15)
    assert a.p_benefit == pytest.approx(b.p_harm, abs=TOL)
    assert a.p_harm == pytest.approx(b.p_benefit, abs=TOL)
    assert a.p_equivalent == pytest.approx(b.p_equivalent, abs=TOL)
    assert a.p_unresolved == pytest.approx(b.p_unresolved, abs=TOL)


def test_oc_degenerate_all_ties_never_curtails() -> None:
    """Deterministic curtailment is distribution-free: at d=0 every pair
    ties, but unobserved pairs could still be discordant, so the walk cannot
    stop early — E[N] = n exactly, all mass UNRESOLVED."""
    oc = gate2_oc(_D16, 0.0, 0.7)
    assert oc.p_unresolved == pytest.approx(1.0, abs=TOL)
    assert oc.expected_n == pytest.approx(16.0, abs=TOL)


def test_oc_boundary_rows_n6() -> None:
    """#55 AC boundary row n=6 (EQUIVALENT is structurally unreachable at
    these knobs — the margin cannot clear gamma with so few pairs)."""
    cases = (
        (0.5, 0.5, 0.003173828125, 0.003173828125, 0.0, 0.99365234375, 2.935546875),
        (0.8, 1.0, 0.65536, 0.0, 0.0, 0.34464, 5.41248),
        (1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 6.0),
    )
    for d, q, ben, harm, eq, unres, e_n in cases:
        curt = gate2_oc(_D6, d, q)
        fixed = gate2_oc(_D6, d, q, curtail=False)
        for oc in (curt, fixed):
            assert oc.p_benefit == pytest.approx(ben, abs=TOL), (d, q)
            assert oc.p_harm == pytest.approx(harm, abs=TOL), (d, q)
            assert oc.p_equivalent == pytest.approx(eq, abs=TOL), (d, q)
            assert oc.p_unresolved == pytest.approx(unres, abs=TOL), (d, q)
        assert curt.expected_n == pytest.approx(e_n, abs=TOL), (d, q)


def test_oc_boundary_row_n40() -> None:
    """#55 AC boundary row n=40 (the grid ceiling; the slow exact-lattice
    case — kept to a single row deliberately)."""
    curt = gate2_oc(_D40, 0.8, 0.9)
    fixed = gate2_oc(_D40, 0.8, 0.9, curtail=False)
    assert curt.p_benefit == pytest.approx(0.9918582601771889, abs=TOL)
    assert curt.p_harm == pytest.approx(6.31392066910192e-18, abs=TOL)
    assert curt.p_equivalent == pytest.approx(2.1517119248903538e-08, abs=TOL)
    assert curt.p_unresolved == pytest.approx(0.008141718305691796, abs=TOL)
    assert curt.expected_n == pytest.approx(34.51969376922504, abs=TOL)
    for field in ("p_benefit", "p_harm", "p_equivalent", "p_unresolved"):
        assert getattr(curt, field) == pytest.approx(getattr(fixed, field), abs=TOL)
    sure = gate2_oc(_D40, 1.0, 1.0)
    assert sure.p_benefit == pytest.approx(1.0, abs=TOL)
    assert sure.expected_n == pytest.approx(29.0, abs=TOL)


def test_oc_validates_true_parameters() -> None:
    with pytest.raises(ValueError):
        gate2_oc(_D16, -0.1, 0.5)
    with pytest.raises(ValueError):
        gate2_oc(_D16, 0.5, 1.5)


# ---------------------------------------------------------------------------
# Worst-case false direction at the null (#37 item 5)
# ---------------------------------------------------------------------------


def test_worst_false_direction_reference_literals() -> None:
    """At the null q=1/2 the direction-call probability is a Bernstein
    polynomial in the nuisance d with coefficients h(k) in [0,1], so
    max_k h(k) certifies an upper bound on the continuous supremum. Reference
    literals: h(15) = 9/256 is the certified bound; the d-grid max sits at
    d=1 where B(1) = h(16) = 697/32768 exactly."""
    bound = gate2_worst_false_direction(_D16, (0.25, 0.5, 0.75, 1.0))
    assert bound.grid_max == pytest.approx(0.021270751953125, abs=TOL)
    assert bound.certified_upper_bound == pytest.approx(0.03515625, abs=TOL)
    assert bound.grid_max <= bound.certified_upper_bound + TOL


def test_worst_false_direction_always_evaluates_d_one() -> None:
    """d=1 is always in the evaluated set: B(1) = h(n) exactly, so a sparse
    grid can never miss the all-discordant endpoint."""
    bound = gate2_worst_false_direction(_D16, (0.25,))
    assert bound.grid_max >= 0.021270751953125 - TOL


def test_worst_false_direction_validation() -> None:
    with pytest.raises(ValueError):
        gate2_worst_false_direction(_D16, ())
    with pytest.raises(ValueError):
        gate2_worst_false_direction(_D16, (0.5, 1.2))


# ---------------------------------------------------------------------------
# Mid-p McNemar cross-check (#37 item 4: mid-p ONLY; FLL 2013)
# ---------------------------------------------------------------------------


def test_midp_hand_checked_literals() -> None:
    """midp(5,1): X~Bin(6,1/2), m=5: 2*P(X>5) + P(X=5) = 2/64 + 6/64 = 1/8.
    midp(8,1): X~Bin(9,1/2): 2*(1/512) + 9/512 = 11/512."""
    assert mcnemar_midp(5, 1) == pytest.approx(0.125, abs=TOL)
    assert mcnemar_midp(8, 1) == pytest.approx(0.021484375, abs=TOL)
    assert mcnemar_midp(9, 3) == pytest.approx(0.09228515625, abs=TOL)
    assert mcnemar_midp(25, 2) == pytest.approx(3.032386302947998e-06, abs=1e-15)


def test_midp_degenerate_and_cap() -> None:
    assert mcnemar_midp(0, 0) == 1.0  # zero-discordant: no evidence either way
    assert mcnemar_midp(2, 2) == 1.0  # capped at 1 on a perfect tie


def test_midp_symmetry_and_validation() -> None:
    assert mcnemar_midp(7, 2) == pytest.approx(mcnemar_midp(2, 7), abs=TOL)
    with pytest.raises(ValueError):
        mcnemar_midp(-1, 2)


# ---------------------------------------------------------------------------
# Tango score interval (#37 item 4; Tango 1998 via score inversion)
# ---------------------------------------------------------------------------


def test_tango_published_literal() -> None:
    """PUBLISHED anchor (PMC10763857 Table 2, floppy-eyelid study):
    discordant 25 vs 2 of N=102 -> 95% Tango CI [0.139, 0.321]."""
    lo, hi = tango_interval(25, 2, 102)
    assert lo == pytest.approx(0.139183, abs=2e-6)
    assert hi == pytest.approx(0.3213295, abs=2e-6)
    assert lo == pytest.approx(0.139, abs=5e-4)
    assert hi == pytest.approx(0.321, abs=5e-4)


def test_tango_reference_literals() -> None:
    """Fine-grid scan-inversion reference values (grid step 5e-7)."""
    lo, hi = tango_interval(5, 1, 14)
    assert lo == pytest.approx(-0.066577, abs=2e-6)
    assert hi == pytest.approx(0.573453, abs=2e-6)


def test_tango_null_symmetry() -> None:
    lo, hi = tango_interval(0, 0, 10)
    assert lo == pytest.approx(-hi, abs=1e-9)
    assert hi == pytest.approx(0.2775325, abs=2e-6)


def test_tango_edges() -> None:
    lo, hi = tango_interval(10, 0, 10)
    assert hi == 1.0  # x_f == n: upper limit is exactly 1 (PropCIs edge rule)
    assert lo == pytest.approx(0.4449345, abs=2e-6)
    lo2, hi2 = tango_interval(0, 10, 10)
    assert lo2 == -1.0
    assert hi2 == pytest.approx(-0.4449345, abs=2e-6)


def test_tango_swap_negates() -> None:
    lo, hi = tango_interval(7, 2, 20)
    lo2, hi2 = tango_interval(2, 7, 20)
    assert lo == pytest.approx(-hi2, abs=1e-9)
    assert hi == pytest.approx(-lo2, abs=1e-9)


def test_tango_validation() -> None:
    with pytest.raises(ValueError):
        tango_interval(5, 1, 0)
    with pytest.raises(ValueError):
        tango_interval(9, 8, 16)  # 17 discordant outcomes from 16 pairs
    with pytest.raises(ValueError):
        tango_interval(5, 1, 14, level=1.0)


# ---------------------------------------------------------------------------
# Newcombe paired interval (#37 item 4; Newcombe 1998 method 10)
# ---------------------------------------------------------------------------


def test_newcombe_published_literal() -> None:
    """PUBLISHED anchor (Altman 2000 'Statistics with confidence' table 6.2,
    thallium stress test, via biostatUZH::confIntPairedProportion):
    (both=14, x_f=5, x_n=0, neither=22) -> 95% CI [0.011, 0.226]."""
    lo, hi = newcombe_interval(14, 5, 0, 22)
    assert lo == pytest.approx(0.011483241383033305, abs=1e-9)
    assert hi == pytest.approx(0.22649268435121117, abs=1e-9)
    assert lo == pytest.approx(0.011, abs=5e-4)
    assert hi == pytest.approx(0.226, abs=5e-4)


def test_newcombe_reference_literals() -> None:
    lo, hi = newcombe_interval(6, 5, 1, 2)
    assert lo == pytest.approx(-0.06395085330112271, abs=1e-9)
    assert hi == pytest.approx(0.5559546555878594, abs=1e-9)
    lo2, hi2 = newcombe_interval(0, 0, 0, 8)
    assert lo2 == pytest.approx(-0.3244075648838801, abs=1e-9)
    assert hi2 == pytest.approx(0.3244075648838801, abs=1e-9)


def test_newcombe_swap_negates_and_bounds() -> None:
    lo, hi = newcombe_interval(6, 5, 1, 2)
    lo2, hi2 = newcombe_interval(6, 1, 5, 2)
    assert lo == pytest.approx(-hi2, abs=TOL)
    assert hi == pytest.approx(-lo2, abs=TOL)
    for cells in ((0, 10, 0, 0), (0, 0, 10, 0), (5, 0, 0, 5), (1, 1, 1, 1)):
        lo3, hi3 = newcombe_interval(*cells)
        assert -1.0 - TOL <= lo3 <= hi3 <= 1.0 + TOL, cells


def test_newcombe_validation() -> None:
    with pytest.raises(ValueError):
        newcombe_interval(0, 0, 0, 0)  # empty table
    with pytest.raises(ValueError):
        newcombe_interval(-1, 2, 3, 4)
    with pytest.raises(ValueError):
        newcombe_interval(1, 2, 3, 4, level=0.0)
