"""Gate-1 machinery: two-point indifference-zone rule, Lee-Liu-style
extension governor, exact OC enumeration, deterministic curtailment.

Decision rule (#37 item 1, the v2 prototype form): after ``s`` passes of
``n`` Null-screen trials, the posterior on the true Null pass rate p0 is
Beta(1+s, 1+n-s) (uniform prior), and

    QUALIFIES  iff P(p0 <= theta_lo | s, n) >= gamma_qualify
    REJECTED   iff P(p0 >= theta_hi | s, n) >= gamma_reject
    UNRESOLVED otherwise

with a declared don't-care zone (theta_lo, theta_hi) between the two tested
points. The one-point rule was rejected on #37 (boundary UNRESOLVED sink,
non-vanishing in n); ``Gate1Design`` refuses it.

Extension governor (#37 item 2, Lee-Liu-style): at a batch boundary left
UNRESOLVED with batches remaining, spend another batch iff the posterior
predictive probability that the next batch RESOLVES the decision clears a
registered floor. The governor is one-step-lookahead ("spend another batch
vs stay UNRESOLVED" is exactly the next-batch question); it re-evaluates at
every boundary, so the policy is fully inside the exact OC characterization
- no ad-hoc retries. Revisit-if: a ratification wants the horizon-predictive
(Lee-Liu original) form for designs with max_batches >= 3 - the two coincide
at max_batches <= 2.

Deterministic curtailment (#37 item 6, default-on): stop observing the
moment every completion of the current partial sequence - through the FULL
design tree, extension batches included - yields the same final decision.
Determination against the full tree (not the current batch's horizon) is
what makes curtailment provably decision-identical when an extension
governor exists; the curtailment tests pin the identity differentially.

Everything is exact enumeration: no simulation, no seeds, no nominal levels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from math import comb

from skill_harness.oc.exact import beta_binomial_pmf, beta_cdf

# ---------------------------------------------------------------------------
# Vocabulary + design
# ---------------------------------------------------------------------------


class Gate1Decision(StrEnum):
    """Three-way Gate-1 outcome (#37: three-way gates, never a forced call)."""

    QUALIFIES = "qualifies"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Gate1Design:
    """A complete, registered Gate-1 design - every knob the OC depends on.

    Fields
    ------
    theta_lo : float
        QUALIFIES tests p0 <= theta_lo ("task hard enough").
    theta_hi : float
        REJECTED tests p0 >= theta_hi ("task clearly too easy").
    gamma_qualify : float
        Posterior mass required to certify QUALIFIES; in (0.5, 1).
    gamma_reject : float
        Posterior mass required to certify REJECTED; in (0.5, 1).
    n_initial : int
        Trials in the initial batch.
    max_batches : int
        Total batch cap including the initial batch; 1 = pure fixed-N.
    batch_size : int | None
        Extension batch size; required iff max_batches > 1.
    pp_floor : float
        Governor floor in [0, 1]: extend iff PP(next batch resolves) >= floor.
    """

    theta_lo: float
    theta_hi: float
    gamma_qualify: float
    gamma_reject: float
    n_initial: int
    max_batches: int = 1
    batch_size: int | None = None
    pp_floor: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 < self.theta_lo < 1.0 or not 0.0 < self.theta_hi < 1.0:
            raise ValueError(
                f"thetas must lie strictly inside (0, 1); "
                f"got theta_lo={self.theta_lo}, theta_hi={self.theta_hi}"
            )
        if not self.theta_lo < self.theta_hi:
            raise ValueError(
                "theta_lo must be strictly below theta_hi - the one-point rule "
                "was rejected on #37 (boundary UNRESOLVED sink); "
                f"got theta_lo={self.theta_lo}, theta_hi={self.theta_hi}"
            )
        for name, gamma in (
            ("gamma_qualify", self.gamma_qualify),
            ("gamma_reject", self.gamma_reject),
        ):
            if not 0.5 < gamma < 1.0:
                raise ValueError(
                    f"{name} must lie in (0.5, 1): at gamma <= 0.5 both decisions "
                    "can certify simultaneously (their posterior masses sum to "
                    f"<= 1), making the rule order-dependent; got {gamma}"
                )
        if self.n_initial < 1:
            raise ValueError(f"n_initial must be >= 1; got {self.n_initial}")
        if self.max_batches < 1:
            raise ValueError(f"max_batches must be >= 1; got {self.max_batches}")
        if self.max_batches > 1:
            if self.batch_size is None or self.batch_size < 1:
                raise ValueError(
                    "an extension design (max_batches > 1) requires batch_size >= 1; "
                    f"got batch_size={self.batch_size}"
                )
        elif self.batch_size is not None:
            raise ValueError(
                "batch_size is meaningless without extension batches; "
                "leave it None when max_batches == 1"
            )
        if not 0.0 <= self.pp_floor <= 1.0:
            raise ValueError(f"pp_floor must lie in [0, 1]; got {self.pp_floor}")

    @property
    def n_ceiling(self) -> int:
        """Worst-case total trials: the hard-cap spend surface (#40 tests
        worst-case fixed-N cost pre-spend, never curtailed expectation)."""
        return self.n_initial + (self.max_batches - 1) * (self.batch_size or 0)


@dataclass(frozen=True)
class Gate1OC:
    """Exact operating characteristics of one design at one true p0."""

    true_p0: float
    p_qualifies: float
    p_rejected: float
    p_unresolved: float
    expected_n: float
    curtailed: bool


@dataclass(frozen=True)
class Gate1AttainedErrors:
    """The #37 zone-edge misclassification pair - ATTAINED, never nominal.

    Fields
    ------
    p_qualify_at_theta_hi : float
        P(QUALIFIES | p0 = theta_hi): certifying "hard enough" when the task
        sits exactly at the too-easy edge.
    p_reject_at_theta_lo : float
        P(REJECTED | p0 = theta_lo): certifying "too easy" when the task sits
        exactly at the hard-enough edge.
    """

    p_qualify_at_theta_hi: float
    p_reject_at_theta_lo: float


# ---------------------------------------------------------------------------
# Decision rule + extension governor
# ---------------------------------------------------------------------------


def gate1_decide(design: Gate1Design, passes: int, trials: int) -> Gate1Decision:
    """Apply the two-point indifference-zone rule to observed counts.

    :param design: The registered design (only the rule knobs are read).
    :param passes: Null-screen passes observed, 0 <= passes <= trials.
    :param trials: Trials observed; 0 is allowed and returns UNRESOLVED.
    :returns: The three-way decision.
    :raises ValueError: If the counts are inconsistent.
    """
    if trials < 0 or not 0 <= passes <= trials:
        raise ValueError(f"need 0 <= passes <= trials; got passes={passes}, trials={trials}")
    if trials == 0:
        return Gate1Decision.UNRESOLVED
    a, b = 1 + passes, 1 + trials - passes
    if beta_cdf(design.theta_lo, a, b) >= design.gamma_qualify:
        return Gate1Decision.QUALIFIES
    if 1.0 - beta_cdf(design.theta_hi, a, b) >= design.gamma_reject:
        return Gate1Decision.REJECTED
    return Gate1Decision.UNRESOLVED


def gate1_extension_pp(design: Gate1Design, passes: int, trials: int) -> float:
    """Posterior predictive probability that ONE more batch resolves the gate.

    The Lee-Liu-style governor quantity: under the current posterior
    Beta(1+passes, 1+trials-passes), the beta-binomial probability that the
    decision after batch_size further trials is QUALIFIES or REJECTED.

    :param design: An extension design (max_batches > 1).
    :param passes: Null-screen passes observed so far.
    :param trials: Trials observed so far.
    :returns: PP in [0, 1].
    :raises ValueError: If the design has no extension batches or counts are
        inconsistent.
    """
    if design.batch_size is None:
        raise ValueError(
            "gate1_extension_pp is only defined for extension designs "
            "(max_batches > 1 with a batch_size)"
        )
    if trials < 0 or not 0 <= passes <= trials:
        raise ValueError(f"need 0 <= passes <= trials; got passes={passes}, trials={trials}")
    m = design.batch_size
    a, b = 1 + passes, 1 + trials - passes
    return sum(
        beta_binomial_pmf(k, m, a, b)
        for k in range(m + 1)
        if gate1_decide(design, passes + k, trials + m) is not Gate1Decision.UNRESOLVED
    )


# ---------------------------------------------------------------------------
# Exact OC enumeration
# ---------------------------------------------------------------------------


def _boundary_absorbs(
    design: Gate1Design, passes: int, trials: int, batch_idx: int
) -> Gate1Decision | None:
    """At a batch boundary: the absorbing decision, or None to extend."""
    decision = gate1_decide(design, passes, trials)
    if decision is not Gate1Decision.UNRESOLVED:
        return decision
    if batch_idx >= design.max_batches:
        return Gate1Decision.UNRESOLVED
    if gate1_extension_pp(design, passes, trials) >= design.pp_floor:
        return None
    return Gate1Decision.UNRESOLVED


@cache
def _reachable_from_boundary(
    design: Gate1Design, passes: int, trials: int, batch_idx: int
) -> frozenset[Gate1Decision]:
    """Final decisions reachable from a batch-boundary state through the full
    design tree (extension batches included)."""
    absorbed = _boundary_absorbs(design, passes, trials, batch_idx)
    if absorbed is not None:
        return frozenset({absorbed})
    batch = design.batch_size
    assert batch is not None  # extending implies an extension design
    out: set[Gate1Decision] = set()
    for gained in range(batch + 1):
        out |= _reachable_from_boundary(design, passes + gained, trials + batch, batch_idx + 1)
        if len(out) == 3:
            break
    return frozenset(out)


def _determined(
    design: Gate1Design, passes: int, trials: int, batch_idx: int, left: int
) -> Gate1Decision | None:
    """The single final decision every completion of this partial state
    reaches, or None if more than one is still reachable.

    Determination is checked against the FULL design tree: the union of
    boundary-reachable sets over every attainable pass count among the
    ``left`` remaining trials of the current batch.
    """
    seen: set[Gate1Decision] = set()
    for gained in range(left + 1):
        seen |= _reachable_from_boundary(design, passes + gained, trials + left, batch_idx)
        if len(seen) > 1:
            return None
    return next(iter(seen))


def _validate_p0(true_p0: float) -> None:
    if not 0.0 <= true_p0 <= 1.0:
        raise ValueError(f"true_p0 must lie in [0, 1]; got {true_p0}")


def _oc_fixed(design: Gate1Design, true_p0: float) -> Gate1OC:
    """Batch-level exact enumeration: every started batch is fully observed."""
    probs: dict[Gate1Decision, float] = dict.fromkeys(Gate1Decision, 0.0)
    expected_n = 0.0
    # boundary_mass[passes] = probability mass arriving at the upcoming
    # boundary with this cumulative pass count
    boundary_mass: dict[int, float] = {}
    for gained in range(design.n_initial + 1):
        pmf = (
            comb(design.n_initial, gained)
            * true_p0**gained
            * (1.0 - true_p0) ** (design.n_initial - gained)
        )
        if pmf > 0.0:
            boundary_mass[gained] = pmf
    trials = design.n_initial
    for batch_idx in range(1, design.max_batches + 1):
        carried: dict[int, float] = {}
        for passes, mass in boundary_mass.items():
            absorbed = _boundary_absorbs(design, passes, trials, batch_idx)
            if absorbed is not None:
                probs[absorbed] += mass
                expected_n += mass * trials
                continue
            batch = design.batch_size
            assert batch is not None
            for gained in range(batch + 1):
                pmf = comb(batch, gained) * true_p0**gained * (1.0 - true_p0) ** (batch - gained)
                if pmf > 0.0:
                    key = passes + gained
                    carried[key] = carried.get(key, 0.0) + mass * pmf
        if not carried:
            break
        boundary_mass = carried
        trials += design.batch_size or 0
    return Gate1OC(
        true_p0=true_p0,
        p_qualifies=probs[Gate1Decision.QUALIFIES],
        p_rejected=probs[Gate1Decision.REJECTED],
        p_unresolved=probs[Gate1Decision.UNRESOLVED],
        expected_n=expected_n,
        curtailed=False,
    )


def _oc_curtailed(design: Gate1Design, true_p0: float) -> Gate1OC:
    """Trial-by-trial exact walk absorbing at the first determined state.

    A deliberately different computation from :func:`_oc_fixed` (per-trial
    forward DP vs batch-level convolution), so the curtailment
    decision-identity tests are differential, not tautological.
    """
    probs: dict[Gate1Decision, float] = dict.fromkeys(Gate1Decision, 0.0)
    expected_n = 0.0
    # live: (passes, trials_observed, batch_idx, left_in_batch) -> mass
    live: dict[tuple[int, int, int, int], float] = {(0, 0, 1, design.n_initial): 1.0}
    while live:
        advanced: dict[tuple[int, int, int, int], float] = {}
        for (passes, trials, batch_idx, left), mass in live.items():
            settled = _determined(design, passes, trials, batch_idx, left)
            if settled is not None:
                probs[settled] += mass
                expected_n += mass * trials
                continue
            if left == 0:
                # Undetermined at a boundary can only mean the governor
                # extends (an absorbing boundary is a singleton reach-set).
                batch = design.batch_size
                assert batch is not None
                key = (passes, trials, batch_idx + 1, batch)
                advanced[key] = advanced.get(key, 0.0) + mass
                continue
            for gained, step_p in ((1, true_p0), (0, 1.0 - true_p0)):
                if step_p > 0.0:
                    key = (passes + gained, trials + 1, batch_idx, left - 1)
                    advanced[key] = advanced.get(key, 0.0) + mass * step_p
        live = advanced
    return Gate1OC(
        true_p0=true_p0,
        p_qualifies=probs[Gate1Decision.QUALIFIES],
        p_rejected=probs[Gate1Decision.REJECTED],
        p_unresolved=probs[Gate1Decision.UNRESOLVED],
        expected_n=expected_n,
        curtailed=True,
    )


def gate1_oc(design: Gate1Design, true_p0: float, *, curtail: bool = True) -> Gate1OC:
    """Exact operating characteristics of a Gate-1 design at one true p0.

    Decision probabilities are provably identical under both curtailment
    modes (the equivalence tests pin this differentially); ``expected_n`` is
    where they differ - curtailment stops spending the moment the decision
    is mathematically settled (#37 item 6, default-on).

    :param design: The registered design.
    :param true_p0: True Null pass rate in [0, 1].
    :param curtail: Deterministic curtailment (default True per #37).
    :returns: Exact decision probabilities and expected spend.
    :raises ValueError: If true_p0 is outside [0, 1].
    """
    _validate_p0(true_p0)
    if curtail:
        return _oc_curtailed(design, true_p0)
    return _oc_fixed(design, true_p0)


def gate1_attained_errors(design: Gate1Design) -> Gate1AttainedErrors:
    """The registered zone-edge misclassification pair for one design.

    #37 item 5: Gate 1 registers P(QUALIFIES | p0 = theta_hi) and
    P(REJECTED | p0 = theta_lo), attained off the exact enumeration
    (extension batches inside the characterization).

    :param design: The registered design.
    :returns: The attained zone-edge error pair.
    """
    return Gate1AttainedErrors(
        p_qualify_at_theta_hi=gate1_oc(design, design.theta_hi, curtail=False).p_qualifies,
        p_reject_at_theta_lo=gate1_oc(design, design.theta_lo, curtail=False).p_rejected,
    )
