"""Gate-1 seam tests for the pure-math ``skill_harness.oc`` package (#54).

Seam (ratified in spec #49 testing decision 1 — the only NEW seam): pure
functions from registered knobs -> decisions / OC rows, pinned at the
``skill_harness.oc`` public API only. If a decision-relevant behavior can only
be pinned below this API, that is a design smell in the API — deepen it, never
test internals (revisit-if carried from #49).

The banked prototype suite (provenance: #42 resolution record, convention 4;
prototypes ``oc_prototype{,_v2,_v3}.py``) is the FLOOR, not the ceiling. Gate-1
floor items carried here: T1 hand-checked Beta CDF, T2 CDF symmetry, T3
sum-to-one, T4 monotonicity, T5 degenerate-n, and v3's curtailment
error-identity. The Gate-2 floor items (trinomial sum-to-one, harm/benefit
symmetry T6, lattice-DP cross-checks) land with the Gate-2 ticket #55.

Expected literals were computed by an INDEPENDENT reference implementation
(exact ``fractions.Fraction`` arithmetic, brute-force tree walk, curtailment
determination by completion enumeration) — not by the code under test. Each
literal carries its derivation.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from skill_harness.oc import (
    GRID_N_MAX,
    GRID_N_MIN,
    Gate1Decision,
    Gate1Design,
    beta_cdf,
    gate1_attained_errors,
    gate1_decide,
    gate1_extension_pp,
    gate1_oc,
)

TOL = 1e-12

# Config A — the v2-prototype knobs, fixed-N n=8 (no extension).
_A = Gate1Design(theta_lo=0.3, theta_hi=0.6, gamma_qualify=0.80, gamma_reject=0.90, n_initial=8)

# Config B — extension design: initial 6, one 4-trial extension batch,
# governor floor 0.3.
_B = Gate1Design(
    theta_lo=0.3,
    theta_hi=0.6,
    gamma_qualify=0.80,
    gamma_reject=0.90,
    n_initial=6,
    max_batches=2,
    batch_size=4,
    pp_floor=0.3,
)


# ---------------------------------------------------------------------------
# Exact Beta CDF (floor T1/T2 + edges)
# ---------------------------------------------------------------------------


def test_beta_cdf_hand_checked_value() -> None:
    """Floor T1: I_.3(2,3) = C(4,2).3^2.7^2 + C(4,3).3^3.7 + .3^4
    = .2646 + .0756 + .0081 = .3483 (posterior after 1/3 passes)."""
    assert beta_cdf(0.3, 2, 3) == pytest.approx(0.3483, abs=1e-9)


def test_beta_cdf_symmetry() -> None:
    """Floor T2: I_.5(a,a) = 0.5 exactly, any a."""
    for a in (1, 3, 7):
        assert beta_cdf(0.5, a, a) == pytest.approx(0.5, abs=TOL)


def test_beta_cdf_edges_and_validation() -> None:
    assert beta_cdf(0.0, 2, 5) == 0.0
    assert beta_cdf(-0.5, 2, 5) == 0.0
    assert beta_cdf(1.0, 2, 5) == 1.0
    assert beta_cdf(1.5, 2, 5) == 1.0
    with pytest.raises(ValueError):
        beta_cdf(0.5, 0, 3)
    with pytest.raises(ValueError):
        beta_cdf(0.5, 3, -1)


# ---------------------------------------------------------------------------
# Two-point indifference-zone rule (#37 item 1; v2 prototype form)
# ---------------------------------------------------------------------------


def test_decide_qualifies_on_zero_passes() -> None:
    """s=0, n=8: P(p0 <= .3 | Beta(1,9)) = 1 - .7^9 = 0.959646... >= .80."""
    assert gate1_decide(_A, 0, 8) is Gate1Decision.QUALIFIES


def test_decide_rejects_on_all_passes() -> None:
    """s=8, n=8: P(p0 >= .6 | Beta(9,1)) = 1 - .6^9 = 0.989922... >= .90."""
    assert gate1_decide(_A, 8, 8) is Gate1Decision.REJECTED


def test_decide_mid_zone_is_unresolved() -> None:
    assert gate1_decide(_A, 4, 8) is Gate1Decision.UNRESOLVED


def test_decide_perfect_null_run_boundary() -> None:
    """Historical perfect-Null-run anchor (v2 prototype report): with
    theta_hi=.6, gamma_reject=.90, an n/n-pass record gives
    P(p0 >= .6) = 1 - .6^(n+1): 3/3 -> 0.8704 (UNRESOLVED), 4/4 -> 0.92224
    (REJECTED)."""
    assert gate1_decide(_A, 3, 3) is Gate1Decision.UNRESOLVED
    assert gate1_decide(_A, 4, 4) is Gate1Decision.REJECTED


def test_decide_zero_trials_is_unresolved() -> None:
    """Floor T5 (degenerate n): no data can never resolve."""
    assert gate1_decide(_A, 0, 0) is Gate1Decision.UNRESOLVED


def test_decide_validates_counts() -> None:
    with pytest.raises(ValueError):
        gate1_decide(_A, 5, 4)
    with pytest.raises(ValueError):
        gate1_decide(_A, -1, 4)


def test_decision_tokens_are_stable() -> None:
    """The decision vocabulary will appear verbatim in reports and records —
    pin the string values."""
    assert Gate1Decision.QUALIFIES.value == "qualifies"
    assert Gate1Decision.REJECTED.value == "rejected"
    assert Gate1Decision.UNRESOLVED.value == "unresolved"


# ---------------------------------------------------------------------------
# Design validation (refusals over silent nonsense)
# ---------------------------------------------------------------------------


def test_design_refuses_one_point_rule() -> None:
    """theta_lo == theta_hi is the v1 single-threshold rule, rejected on #37
    (P(UNRESOLVED) 0.55-0.83 at the boundary, non-vanishing in n). Revisit-if:
    ratification deliberately wants a one-point rule."""
    with pytest.raises(ValueError):
        Gate1Design(theta_lo=0.4, theta_hi=0.4, gamma_qualify=0.8, gamma_reject=0.9, n_initial=8)


def test_design_refuses_gamma_at_or_below_half() -> None:
    """gamma <= 0.5 admits simultaneous QUALIFIES and REJECTED certification
    (P(p0<=lo) + P(p0>=hi) <= 1, so both >= gamma forces 2*gamma <= 1) — the
    rule would depend on check order. Refused."""
    with pytest.raises(ValueError):
        Gate1Design(theta_lo=0.3, theta_hi=0.6, gamma_qualify=0.5, gamma_reject=0.9, n_initial=8)
    with pytest.raises(ValueError):
        Gate1Design(theta_lo=0.3, theta_hi=0.6, gamma_qualify=0.8, gamma_reject=0.4, n_initial=8)


def test_design_refuses_bad_thetas_and_n() -> None:
    with pytest.raises(ValueError):
        Gate1Design(theta_lo=0.0, theta_hi=0.6, gamma_qualify=0.8, gamma_reject=0.9, n_initial=8)
    with pytest.raises(ValueError):
        Gate1Design(theta_lo=0.3, theta_hi=1.0, gamma_qualify=0.8, gamma_reject=0.9, n_initial=8)
    with pytest.raises(ValueError):
        Gate1Design(theta_lo=0.3, theta_hi=0.6, gamma_qualify=0.8, gamma_reject=0.9, n_initial=0)


def _design(**overrides: int | float | None) -> Gate1Design:
    kwargs: dict[str, object] = {
        "theta_lo": 0.3,
        "theta_hi": 0.6,
        "gamma_qualify": 0.8,
        "gamma_reject": 0.9,
        "n_initial": 8,
    }
    kwargs.update(overrides)
    return Gate1Design(**kwargs)  # type: ignore[arg-type]


def test_design_refuses_inconsistent_extension_knobs() -> None:
    with pytest.raises(ValueError):  # extension declared but no batch size
        _design(max_batches=2)
    with pytest.raises(ValueError):  # batch size without extension
        _design(batch_size=4)
    with pytest.raises(ValueError):  # zero batches
        _design(max_batches=0)
    with pytest.raises(ValueError):  # governor floor outside [0, 1]
        _design(max_batches=2, batch_size=4, pp_floor=1.5)


def test_design_n_ceiling() -> None:
    assert _A.n_ceiling == 8
    assert _B.n_ceiling == 10


# ---------------------------------------------------------------------------
# Exact OC enumeration (floor T3/T4 + independent-reference literals)
# ---------------------------------------------------------------------------


def test_oc_rows_sum_to_one() -> None:
    """Floor T3, both curtailment modes, extension and boundary-n configs."""
    n_min_design = Gate1Design(
        theta_lo=0.3,
        theta_hi=0.6,
        gamma_qualify=0.8,
        gamma_reject=0.9,
        n_initial=GRID_N_MIN,
    )
    n_max_design = Gate1Design(
        theta_lo=0.3,
        theta_hi=0.6,
        gamma_qualify=0.8,
        gamma_reject=0.9,
        n_initial=GRID_N_MAX,
    )
    for design in (_A, _B, n_min_design, n_max_design):
        for p0 in (0.0, 0.1, 0.3, 0.7, 1.0):
            for curtail in (True, False):
                oc = gate1_oc(design, p0, curtail=curtail)
                total = oc.p_qualifies + oc.p_rejected + oc.p_unresolved
                assert total == pytest.approx(1.0, abs=TOL), (design, p0, curtail)


def test_oc_qualify_probability_monotone_in_true_p0() -> None:
    """Floor T4: P(QUALIFIES) nonincreasing as the true Null pass rate rises."""
    prev = None
    for p0 in (0.05, 0.2, 0.4, 0.6, 0.8, 0.95):
        p_q = gate1_oc(_A, p0).p_qualifies
        if prev is not None:
            assert p_q <= prev + TOL
        prev = p_q


def test_oc_reference_literals_config_a() -> None:
    """Independent-reference pins, config A at p0=0.3 (exact fractions):
    P(QUALIFIES)=0.25529833, P(REJECTED)=0.00129033, P(UNRESOLVED)=0.74341134."""
    oc = gate1_oc(_A, 0.3, curtail=False)
    assert oc.p_qualifies == pytest.approx(0.25529833, abs=TOL)
    assert oc.p_rejected == pytest.approx(0.00129033, abs=TOL)
    assert oc.p_unresolved == pytest.approx(0.74341134, abs=TOL)
    assert oc.expected_n == pytest.approx(8.0, abs=TOL)


def test_oc_reference_literals_config_b_extension() -> None:
    """Independent-reference pins, config B at p0=0.45. The governor extends
    only from boundary states whose PP clears 0.3 (s=1 and s=5; the mid-zone
    states cannot resolve within one batch, PP=0), so
    E[N. fixed] = 6 + 4*P(extend) = 6.78712425."""
    oc = gate1_oc(_B, 0.45, curtail=False)
    assert oc.p_qualifies == pytest.approx(0.04011513040175781, abs=TOL)
    assert oc.p_rejected == pytest.approx(0.010800811745507812, abs=TOL)
    assert oc.p_unresolved == pytest.approx(0.9490840578527344, abs=TOL)
    assert oc.expected_n == pytest.approx(6.78712425, abs=TOL)


def test_oc_degenerate_true_p0_zero() -> None:
    """p0=0: the path is all-fails, so config A resolves QUALIFIES surely."""
    oc = gate1_oc(_A, 0.0)
    assert oc.p_qualifies == pytest.approx(1.0, abs=TOL)


def test_oc_validates_true_p0() -> None:
    with pytest.raises(ValueError):
        gate1_oc(_A, -0.1)
    with pytest.raises(ValueError):
        gate1_oc(_A, 1.1)


# ---------------------------------------------------------------------------
# Lee-Liu-style extension governor (#37 item 2)
# ---------------------------------------------------------------------------


def test_extension_pp_literal() -> None:
    """Config B boundary state s=1, n=6: PP that one 4-trial batch resolves =
    21/55 = 0.381818... (beta-binomial over Beta(2,6); exact-fraction
    reference). Mid-zone s=3 cannot resolve within one batch: PP = 0."""
    assert gate1_extension_pp(_B, 1, 6) == pytest.approx(21.0 / 55.0, abs=TOL)
    assert gate1_extension_pp(_B, 3, 6) == pytest.approx(0.0, abs=TOL)


def test_extension_pp_in_unit_interval() -> None:
    for s in range(7):
        assert 0.0 <= gate1_extension_pp(_B, s, 6) <= 1.0


def test_extension_pp_requires_extension_design() -> None:
    with pytest.raises(ValueError):
        gate1_extension_pp(_A, 2, 8)


def test_extension_only_converts_unresolved() -> None:
    """Extension fires only on UNRESOLVED boundary states, so vs the same
    design without the second batch it can only grow both resolution
    probabilities and shrink P(UNRESOLVED)."""
    fixed6 = Gate1Design(
        theta_lo=0.3, theta_hi=0.6, gamma_qualify=0.8, gamma_reject=0.9, n_initial=6
    )
    for p0 in (0.1, 0.3, 0.45, 0.6, 0.9):
        ext = gate1_oc(_B, p0)
        base = gate1_oc(fixed6, p0)
        assert ext.p_qualifies >= base.p_qualifies - TOL
        assert ext.p_rejected >= base.p_rejected - TOL
        assert ext.p_unresolved <= base.p_unresolved + TOL


def test_governor_floor_monotonicity() -> None:
    """Raising pp_floor can only extend less: E[N] nonincreasing,
    P(UNRESOLVED) nondecreasing (independent-reference sweep at p0=0.45:
    floor 0 -> E[N] 5.400/P 0.949; floor 0.5 and 1 -> E[N] 2.964/P 0.964)."""
    prev_en, prev_unres = None, None
    for floor in (0.0, 0.5, 1.0):
        design = Gate1Design(
            theta_lo=0.3,
            theta_hi=0.6,
            gamma_qualify=0.8,
            gamma_reject=0.9,
            n_initial=6,
            max_batches=2,
            batch_size=4,
            pp_floor=floor,
        )
        oc = gate1_oc(design, 0.45)
        if prev_en is not None and prev_unres is not None:
            assert oc.expected_n <= prev_en + TOL
            assert oc.p_unresolved >= prev_unres - TOL
        prev_en, prev_unres = oc.expected_n, oc.p_unresolved


# ---------------------------------------------------------------------------
# Deterministic curtailment (#37 item 6; v3 error-identity floor)
# ---------------------------------------------------------------------------


def test_curtailment_decision_identity() -> None:
    """v3 floor: curtailed and uncurtailed designs decide IDENTICALLY —
    the two modes are computed by different walks, so this is differential."""
    n_max_design = Gate1Design(
        theta_lo=0.3,
        theta_hi=0.6,
        gamma_qualify=0.8,
        gamma_reject=0.9,
        n_initial=GRID_N_MAX,
    )
    for design in (_A, _B, n_max_design):
        for p0 in (0.0, 0.3, 0.45, 0.6, 1.0):
            curt = gate1_oc(design, p0, curtail=True)
            fixed = gate1_oc(design, p0, curtail=False)
            assert curt.p_qualifies == pytest.approx(fixed.p_qualifies, abs=TOL)
            assert curt.p_rejected == pytest.approx(fixed.p_rejected, abs=TOL)
            assert curt.p_unresolved == pytest.approx(fixed.p_unresolved, abs=TOL)


def test_curtailment_saves_expected_trials() -> None:
    """Curtailed E[N] never exceeds the fixed spend, and the reference pins
    the exact savings for config A at p0=0.3: 5.976145 vs 8.0."""
    curt = gate1_oc(_A, 0.3, curtail=True)
    fixed = gate1_oc(_A, 0.3, curtail=False)
    assert curt.expected_n == pytest.approx(5.976145, abs=TOL)
    assert fixed.expected_n == pytest.approx(8.0, abs=TOL)
    assert curt.expected_n <= fixed.expected_n


def test_curtailment_stops_at_first_determined_trial() -> None:
    """Config A at p0=0: the all-fail path is determined at t=7 (both s=0 and
    s=1 completions at n=8 QUALIFY: I_.3(2,8) = 0.80400... >= .80), never
    earlier — reference E[N] is exactly 7.0."""
    assert gate1_oc(_A, 0.0, curtail=True).expected_n == pytest.approx(7.0, abs=TOL)


def test_curtailment_extension_literals() -> None:
    """Independent-reference pin for the extension design B at p0=0.45:
    curtailed E[N] = 5.400415216640625."""
    assert gate1_oc(_B, 0.45, curtail=True).expected_n == pytest.approx(5.400415216640625, abs=TOL)


def test_curtailment_is_the_default() -> None:
    """#37 item 6 / #54 AC: curtailment default-on within fixed-N designs."""
    assert gate1_oc(_A, 0.3).expected_n == pytest.approx(5.976145, abs=TOL)
    assert gate1_oc(_A, 0.3).curtailed is True
    assert gate1_oc(_A, 0.3, curtail=False).curtailed is False


# ---------------------------------------------------------------------------
# Attained errors (#37 item 5: the zone-edge misclassification pair)
# ---------------------------------------------------------------------------


def test_attained_errors_zone_edge_pair() -> None:
    """ATTAINED (never nominal) zone-edge errors for config A, pinned by the
    independent reference: P(QUALIFIES | p0=theta_hi=.6) = 0.00851968 and
    P(REJECTED | p0=theta_lo=.3) = 0.00129033."""
    errors = gate1_attained_errors(_A)
    assert errors.p_qualify_at_theta_hi == pytest.approx(0.00851968, abs=TOL)
    assert errors.p_reject_at_theta_lo == pytest.approx(0.00129033, abs=TOL)


def test_attained_errors_cover_extension_designs() -> None:
    errors = gate1_attained_errors(_B)
    assert 0.0 <= errors.p_qualify_at_theta_hi <= 1.0
    assert 0.0 <= errors.p_reject_at_theta_lo <= 1.0


# ---------------------------------------------------------------------------
# Grid conventions + boundary rows (#40; #54 AC)
# ---------------------------------------------------------------------------


def test_grid_constants_registered_values() -> None:
    """DC-7 surface: the ratified #40 grid, oc's OWN constants."""
    assert GRID_N_MIN == 6
    assert GRID_N_MAX == 40


def test_boundary_rows_n6_and_n40() -> None:
    """#54 AC: boundary rows n=6 and n=40 produce valid, decision-identical
    OC under both curtailment modes."""
    for n in (GRID_N_MIN, GRID_N_MAX):
        design = Gate1Design(
            theta_lo=0.3,
            theta_hi=0.6,
            gamma_qualify=0.8,
            gamma_reject=0.9,
            n_initial=n,
        )
        for p0 in (0.15, 0.45):
            curt = gate1_oc(design, p0, curtail=True)
            fixed = gate1_oc(design, p0, curtail=False)
            total = curt.p_qualifies + curt.p_rejected + curt.p_unresolved
            assert total == pytest.approx(1.0, abs=TOL)
            assert curt.p_qualifies == pytest.approx(fixed.p_qualifies, abs=TOL)
            assert curt.expected_n <= n + TOL


# ---------------------------------------------------------------------------
# Import direction (#42 architecture; DC-8 surface)
# ---------------------------------------------------------------------------


def test_oc_imports_nothing_from_ablation_or_subject() -> None:
    """#42: oc imports nothing from the ablation or subject packages — proven
    behaviorally in a fresh interpreter, not by source inspection."""
    probe = (
        "import sys; import skill_harness.oc; "
        "banned = [m for m in sys.modules if m.startswith("
        "('skill_harness.ablation', 'skill_harness.subject'))]; "
        "sys.exit(1 if banned else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
