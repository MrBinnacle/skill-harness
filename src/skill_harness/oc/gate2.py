"""Gate-2 machinery: three-sided paired rule over the four-outcome lattice,
dual-MME registration, exact OC (trinomial + lattice-DP curtailment), and the
null false-direction bound.

Decision rule (#37 item 3, the Goeman-partition form): with observed
discordant counts (x_f, x_n) out of n pairs, the reference-prior
Dirichlet(1,1,1,1) over the four paired cells aggregates to
(p_f, p_n, p_tie) ~ Dirichlet(1+x_f, 1+x_n, 2+ties) - the two tie cells are
pooled because every decision functional depends on them only through their
sum. The net lift delta = p_f - p_n (identically d(2q-1), the reported effect
scale) partitions the parameter space into three DISJOINT regions at the
registered margin delta_min:

    BENEFIT     iff P(delta >= delta_min | data)             >= gamma
    HARM        iff P(delta <= -delta_min | data)            >= gamma
    EQUIVALENT  iff P(-delta_min < delta < delta_min | data) >= gamma
    UNRESOLVED  otherwise. Zero-discordant is a DEFINED UNRESOLVED branch
                (#37) - it overrides even a posterior whose equivalence mass
                clears gamma (the seam tests pin that the override is real).

The three region masses sum to one (Goeman 2010 partitioning skeleton - three
disjoint hypotheses, no multiplicity penalty), so gamma > 0.5 guarantees at
most one region certifies; ``Gate2Design`` refuses gamma <= 0.5 (a 0.5/0.5
split would certify two decisions simultaneously, making the rule
order-dependent - the same double-fire proof as Gate-1's).

gamma is the ONLY confidence knob ("gamma-only", #37 - k_min was dropped as
inert). The equivalence margin is the registered dual-MME delta_min, never a
separate tuning knob; q_min is consumed by the FRONTIER's power region H1
(#40/#56), not by the decision rule - a strongly-evidenced net lift above
delta_min is BENEFIT however the win rate decomposes, while q_min scopes
which alternatives the design promises power against.

The OC state is the 2D discordant lattice (x_f, x_n) - the scalar half-update
state is ratified-insufficient (conflates discordant splits; counterexample
in #42's record). Deterministic curtailment (#37 item 6, default-on) absorbs
a walk the moment every completion of the remaining tree yields one decision;
determination is distribution-free (probabilities never enter reachability),
which is what makes it provably decision-identical. The two OC modes are
deliberately different computations (trinomial convolution vs per-pair
forward DP) so the curtailment-identity tests are differential.

Everything is exact enumeration: no simulation, no seeds, no nominal levels.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from math import comb

from skill_harness.oc.exact import dirichlet_delta_tail

# ---------------------------------------------------------------------------
# Vocabulary + registration
# ---------------------------------------------------------------------------


class Gate2Decision(StrEnum):
    """Three-sided Gate-2 outcome + UNRESOLVED (#37: never a forced call)."""

    BENEFIT = "benefit"
    HARM = "harm"
    EQUIVALENT = "equivalent"
    UNRESOLVED = "unresolved"


_DIRECTIONAL = frozenset({Gate2Decision.BENEFIT, Gate2Decision.HARM})


@dataclass(frozen=True)
class MMESpec:
    """Dual minimum-meaningful-effect registration (#40: BOTH knobs).

    Fields
    ------
    delta_min : float
        Margin on the net lift delta = d(2q-1) = p_f - p_n; in (0, 1).
        Doubles as the three-sided rule's equivalence margin (Goeman
        skeleton) - a zero margin would collapse the rule to
        direction-only, which is not the #37 form.
    q_min : float
        Floor on the conditional win rate q; in (0.5, 1). Consumed by the
        frontier's power region H1, not by the decision rule (#40: the
        explicit q floor guards degenerate wins structurally).
    """

    delta_min: float
    q_min: float

    def __post_init__(self) -> None:
        if not 0.0 < self.delta_min < 1.0:
            raise ValueError(
                "delta_min must lie strictly inside (0, 1) - at 0 the "
                "equivalence region is empty and the three-sided rule "
                f"collapses to direction-only; got {self.delta_min}"
            )
        if not 0.5 < self.q_min < 1.0:
            raise ValueError(
                "q_min must lie strictly inside (0.5, 1) - a floor at or "
                "below the coin flip guards nothing (#40); "
                f"got {self.q_min}"
            )

    def in_h1(self, d: float, q: float) -> bool:
        """Membership in the conforming region H1 = {(d, q): d(2q-1) >=
        delta_min and q >= q_min} (#40/#55 - the alternative region the
        frontier's power target is evaluated over; enumerated on (d, q)
        because power is not a function of delta alone).

        :param d: True discordance probability in [0, 1].
        :param q: True conditional win rate in [0, 1].
        :returns: Whether (d, q) is a registered-meaningful benefit.
        :raises ValueError: If d or q is outside [0, 1].
        """
        if not 0.0 <= d <= 1.0 or not 0.0 <= q <= 1.0:
            raise ValueError(f"need d, q in [0, 1]; got d={d}, q={q}")
        return d * (2.0 * q - 1.0) >= self.delta_min and q >= self.q_min


@dataclass(frozen=True)
class Gate2Design:
    """A complete, registered Gate-2 design - every knob the OC depends on.

    Fields
    ------
    n_pairs : int
        Registered fixed-N pair count, >= 1. The #40 grid (6-40) bounds the
        FRONTIER enumeration (#56), not this math layer.
    gamma : float
        Posterior mass required to certify any of the three decisions; in
        (0.5, 1). The only confidence knob (#37 "gamma-only").
    mme : MMESpec
        The registered dual MME; ``mme.delta_min`` is also the rule's
        partition margin.
    """

    n_pairs: int
    gamma: float
    mme: MMESpec

    def __post_init__(self) -> None:
        if self.n_pairs < 1:
            raise ValueError(f"n_pairs must be >= 1; got {self.n_pairs}")
        if not 0.5 < self.gamma < 1.0:
            raise ValueError(
                "gamma must lie in (0.5, 1): the three region masses sum to "
                "1, so at gamma <= 0.5 two decisions can certify "
                f"simultaneously, making the rule order-dependent; got {self.gamma}"
            )


@dataclass(frozen=True)
class Gate2RegionProbs:
    """Posterior masses of the three delta-partition regions (sum to 1).

    These are posterior FACTS, computed even at zero discordant counts -
    the #37 defined UNRESOLVED branch is a rule override applied by
    :func:`gate2_decide`, not a gap in the posterior.
    """

    p_benefit: float
    p_harm: float
    p_equivalent: float


@dataclass(frozen=True)
class Gate2OC:
    """Exact operating characteristics of one design at one true (d, q)."""

    true_d: float
    true_q: float
    p_benefit: float
    p_harm: float
    p_equivalent: float
    p_unresolved: float
    expected_n: float
    curtailed: bool


@dataclass(frozen=True)
class Gate2NullErrorBound:
    """Worst-case false-direction rate at the null q = 1/2 (#37 item 5).

    At the null the direction-call probability is the Bernstein polynomial
    B(d) = sum_k C(n,k) d^k (1-d)^(n-k) h(k) in the nuisance d, with
    coefficients h(k) = P(directional call | k discordant) in [0, 1]. The
    Bernstein coefficient bound gives sup_d B(d) <= max_k h(k), so the true
    supremum lies in [grid_max, certified_upper_bound]; when the two agree
    the supremum is exactly determined (B(1) = h(n), so a maximizing final
    coefficient closes the gap).
    """

    grid_max: float
    certified_upper_bound: float


# ---------------------------------------------------------------------------
# Decision rule
# ---------------------------------------------------------------------------


def _validate_counts(design: Gate2Design, x_f: int, x_n: int) -> None:
    if x_f < 0 or x_n < 0 or x_f + x_n > design.n_pairs:
        raise ValueError(
            f"need x_f, x_n >= 0 with x_f + x_n <= n_pairs={design.n_pairs}; "
            f"got x_f={x_f}, x_n={x_n}"
        )


def gate2_region_probs(design: Gate2Design, x_f: int, x_n: int) -> Gate2RegionProbs:
    """Posterior region masses for observed discordant counts.

    Posterior: (p_f, p_n, p_tie) ~ Dirichlet(1+x_f, 1+x_n, 2+ties) - the
    Dirichlet(1,1,1,1) reference prior over the four paired cells with the
    two tie cells pooled (their split never enters delta or q).

    :param design: The registered design (only n_pairs and the margin read).
    :param x_f: Full-only-win pairs observed.
    :param x_n: Null-only-win pairs observed.
    :returns: The three region masses (sum to 1).
    :raises ValueError: If the counts are inconsistent with the design.
    """
    _validate_counts(design, x_f, x_n)
    a_f, a_n = 1 + x_f, 1 + x_n
    a_t = 2 + design.n_pairs - x_f - x_n
    p_ben = dirichlet_delta_tail(design.mme.delta_min, a_f, a_n, a_t)
    # HARM is the mirrored tail: P(p_n - p_f >= margin) with the discordant
    # roles relabelled (coordinate-exchange symmetry of the Dirichlet).
    p_harm = dirichlet_delta_tail(design.mme.delta_min, a_n, a_f, a_t)
    return Gate2RegionProbs(p_benefit=p_ben, p_harm=p_harm, p_equivalent=1.0 - p_ben - p_harm)


@cache
def _decision(design: Gate2Design, x_f: int, x_n: int) -> Gate2Decision:
    """The rule body, cached across the OC enumerations (counts pre-checked)."""
    if x_f + x_n == 0:
        return Gate2Decision.UNRESOLVED  # #37: defined zero-discordant branch
    probs = gate2_region_probs(design, x_f, x_n)
    if probs.p_benefit >= design.gamma:
        return Gate2Decision.BENEFIT
    if probs.p_harm >= design.gamma:
        return Gate2Decision.HARM
    if probs.p_equivalent >= design.gamma:
        return Gate2Decision.EQUIVALENT
    return Gate2Decision.UNRESOLVED


def gate2_decide(design: Gate2Design, x_f: int, x_n: int) -> Gate2Decision:
    """Apply the three-sided rule to observed discordant counts.

    :param design: The registered design.
    :param x_f: Full-only-win pairs observed.
    :param x_n: Null-only-win pairs observed.
    :returns: The four-way decision (three-sided + UNRESOLVED).
    :raises ValueError: If the counts are inconsistent with the design.
    """
    _validate_counts(design, x_f, x_n)
    return _decision(design, x_f, x_n)


# ---------------------------------------------------------------------------
# Exact OC enumeration
# ---------------------------------------------------------------------------


def _validate_dq(d: float, q: float) -> None:
    if not 0.0 <= d <= 1.0 or not 0.0 <= q <= 1.0:
        raise ValueError(f"true (d, q) must lie in [0, 1]^2; got d={d}, q={q}")


def _oc_fixed(design: Gate2Design, d: float, q: float) -> Gate2OC:
    """Trinomial convolution: k ~ Bin(n, d) discordant, x_f ~ Bin(k, q)."""
    n = design.n_pairs
    probs: dict[Gate2Decision, float] = dict.fromkeys(Gate2Decision, 0.0)
    for k in range(n + 1):
        p_k = comb(n, k) * d**k * (1.0 - d) ** (n - k)
        if p_k == 0.0:
            continue
        for x_f in range(k + 1):
            p_x = comb(k, x_f) * q**x_f * (1.0 - q) ** (k - x_f)
            if p_x > 0.0:
                probs[_decision(design, x_f, k - x_f)] += p_k * p_x
    return Gate2OC(
        true_d=d,
        true_q=q,
        p_benefit=probs[Gate2Decision.BENEFIT],
        p_harm=probs[Gate2Decision.HARM],
        p_equivalent=probs[Gate2Decision.EQUIVALENT],
        p_unresolved=probs[Gate2Decision.UNRESOLVED],
        expected_n=float(n),
        curtailed=False,
    )


@cache
def _reachable(design: Gate2Design, x_f: int, x_n: int, t: int) -> frozenset[Gate2Decision]:
    """Final decisions reachable from lattice state (x_f, x_n) at time t
    through every completion of the remaining pairs (distribution-free)."""
    if t == design.n_pairs:
        return frozenset({_decision(design, x_f, x_n)})
    out: set[Gate2Decision] = set()
    for next_f, next_n in ((x_f + 1, x_n), (x_f, x_n + 1), (x_f, x_n)):
        out |= _reachable(design, next_f, next_n, t + 1)
        if len(out) == 4:
            break
    return frozenset(out)


def _oc_curtailed(design: Gate2Design, d: float, q: float) -> Gate2OC:
    """Per-pair forward DP over the (x_f, x_n) lattice absorbing at the
    first determined state - a deliberately different walk from
    :func:`_oc_fixed` so the decision-identity tests are differential."""
    p_f, p_n = d * q, d * (1.0 - q)
    p_t = 1.0 - d
    probs: dict[Gate2Decision, float] = dict.fromkeys(Gate2Decision, 0.0)
    expected_n = 0.0
    live: dict[tuple[int, int], float] = {(0, 0): 1.0}
    for t in range(design.n_pairs + 1):
        advanced: dict[tuple[int, int], float] = {}
        for (x_f, x_n), mass in live.items():
            reach = _reachable(design, x_f, x_n, t)
            if len(reach) == 1:
                probs[next(iter(reach))] += mass
                expected_n += mass * t
                continue
            # More than one decision reachable implies pairs remain
            # (horizon states have singleton reach-sets by construction).
            for step_p, key in (
                (p_f, (x_f + 1, x_n)),
                (p_n, (x_f, x_n + 1)),
                (p_t, (x_f, x_n)),
            ):
                if step_p > 0.0:
                    advanced[key] = advanced.get(key, 0.0) + mass * step_p
        live = advanced
        if not live:
            break
    return Gate2OC(
        true_d=d,
        true_q=q,
        p_benefit=probs[Gate2Decision.BENEFIT],
        p_harm=probs[Gate2Decision.HARM],
        p_equivalent=probs[Gate2Decision.EQUIVALENT],
        p_unresolved=probs[Gate2Decision.UNRESOLVED],
        expected_n=expected_n,
        curtailed=True,
    )


def gate2_oc(design: Gate2Design, d: float, q: float, *, curtail: bool = True) -> Gate2OC:
    """Exact operating characteristics of a Gate-2 design at one true (d, q).

    Decision probabilities are provably identical under both curtailment
    modes (deterministic curtailment is distribution-free; the equivalence
    tests pin this differentially); ``expected_n`` is where they differ -
    curtailment stops spending the moment the decision is mathematically
    settled (#37 item 6, default-on).

    :param design: The registered design.
    :param d: True discordance probability in [0, 1].
    :param q: True conditional win rate in [0, 1].
    :param curtail: Deterministic curtailment (default True per #37).
    :returns: Exact decision probabilities and expected spend in pairs.
    :raises ValueError: If (d, q) is outside the unit square.
    """
    _validate_dq(d, q)
    if curtail:
        return _oc_curtailed(design, d, q)
    return _oc_fixed(design, d, q)


def gate2_worst_false_direction(
    design: Gate2Design, d_values: Sequence[float]
) -> Gate2NullErrorBound:
    """Worst-case false-direction rate at the null q = 1/2 (#37 item 5).

    The nuisance d is continuous, so a finite evaluation cannot claim the
    supremum by itself; this returns BOTH the max over the supplied d grid
    (d = 1 is always included - B(1) = h(n) exactly) and the certified
    Bernstein-coefficient upper bound max_k h(k). The registered value is a
    frontier-time choice (#56); this layer refuses to conflate a grid max
    with a supremum.

    :param design: The registered design.
    :param d_values: Nuisance-d evaluation points, each in [0, 1]; nonempty.
    :returns: The grid maximum and the certified upper bound.
    :raises ValueError: If d_values is empty or any point is out of range.
    """
    if not d_values:
        raise ValueError("d_values must be a nonempty sequence of points in [0, 1]")
    for d in d_values:
        if not 0.0 <= d <= 1.0:
            raise ValueError(f"every d must lie in [0, 1]; got {d}")
    n = design.n_pairs
    h: list[float] = []
    for k in range(n + 1):
        # C(k, x_f) / 2^k is dyadic-exact in float for the whole #40 grid.
        h.append(
            sum(
                comb(k, x_f) / 2.0**k
                for x_f in range(k + 1)
                if _decision(design, x_f, k - x_f) in _DIRECTIONAL
            )
        )

    def bernstein(d: float) -> float:
        return sum(comb(n, k) * d**k * (1.0 - d) ** (n - k) * h[k] for k in range(n + 1))

    grid = {float(v) for v in d_values} | {1.0}
    return Gate2NullErrorBound(
        grid_max=max(bernstein(v) for v in grid),
        certified_upper_bound=max(h),
    )
