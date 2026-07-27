"""Two-arm posterior-difference gate (DIF screen K7).

Compares two independently-run conditions (treatment vs control) on a binary
pass-rate, with a decision rule that is two-sided ON ARM DIRECTION:

  Posteriors: independent Beta(1 + pass, 1 + (trials - pass)) per arm
              (uniform prior — the package's standing convention, see
              ablation/stopping.py and aggregation/fit.py).
  TREATMENT_BETTER : P(p_t - p_c >  delta) >= prob_threshold
  TREATMENT_WORSE  : P(p_c - p_t >  delta) >= prob_threshold
  NULL             : neither region reached at the registered power.

This gate exists because the package's single-tail screen/paired machinery
(`screen_verdict` p0 semantics; the Full-vs-Null stopping rule) cannot express
a two-condition contrast and would absorb a REVERSE delta into "no lift" —
the reactance direction is a registered outcome region here, not noise.

delta and prob_threshold are the caller's PRE-REGISTERED constants, frozen
before any spend — this module deliberately ships no defaults, so a caller
cannot run the gate without having chosen them.

NULL is a statement about the instrument, not the world: at ~8 epochs/arm only
transformative (~>=0.5 absolute) separations resolve (registered power floor,
council record K7/R6). A NULL means "no transformative effect on this
model/fixture at the registered power", never "no effect exists".

Determinism: the probability P(p_t - p_c > delta) is computed by fixed-order
numerical quadrature over the closed-form Beta pdf/cdf —
    P = integral_0^1 pdf_t(x) * cdf_c(x - delta) dx
— no random sampling anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from scipy.integrate import quad  # type: ignore[import-untyped]
from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Outcome regions
# ---------------------------------------------------------------------------


class TwoArmOutcome(StrEnum):
    """Registered outcome regions for a two-arm contrast (K7)."""

    TREATMENT_BETTER = "treatment_better"
    """P(p_t - p_c > delta) cleared the registered threshold."""

    NULL = "null"
    """Neither directional region reached at the registered power. NOT "no
    effect" — see the module docstring's power-floor registration."""

    TREATMENT_WORSE = "treatment_worse"
    """P(p_c - p_t > delta) cleared the registered threshold (the reactance
    direction — a first-class region, never absorbed into NULL silently)."""


# ---------------------------------------------------------------------------
# Result struct
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TwoArmGateResult:
    """Gate outcome plus the full posterior evidence behind it."""

    outcome: TwoArmOutcome
    p_treatment_better: float
    """P(p_t - p_c > delta) under the independent posteriors."""
    p_treatment_worse: float
    """P(p_c - p_t > delta) under the independent posteriors."""
    treatment_alpha: float
    treatment_beta: float
    control_alpha: float
    control_beta: float
    delta: float
    prob_threshold: float
    rationale: str


# ---------------------------------------------------------------------------
# Internal: P(X - Y > delta) for independent X ~ Beta(a1,b1), Y ~ Beta(a2,b2)
# ---------------------------------------------------------------------------


def _p_difference_exceeds(
    a1: float,
    b1: float,
    a2: float,
    b2: float,
    delta: float,
) -> float:
    """P(X - Y > delta) via deterministic quadrature.

    P(X - Y > delta) = integral over x of pdf_X(x) * P(Y < x - delta) dx.
    cdf_Y(x - delta) is 0 for x <= delta, so the integrand is supported on
    (delta, 1]. With integer counts and a Beta(1,1) prior, a,b >= 1 always,
    so the pdf is bounded and quad converges cleanly.
    """

    def integrand(x: float) -> float:
        return float(
            beta_dist.pdf(x, a1, b1) * beta_dist.cdf(x - delta, a2, b2)
        )

    value, _ = quad(integrand, delta, 1.0, limit=200)
    # Clamp tiny quadrature over/undershoot back into [0, 1].
    return min(1.0, max(0.0, float(value)))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def two_arm_gate(
    treatment_pass: int,
    treatment_trials: int,
    control_pass: int,
    control_trials: int,
    *,
    delta: float,
    prob_threshold: float,
) -> TwoArmGateResult:
    """Evaluate the two-arm posterior-difference gate.

    :param treatment_pass: Primary-binary passes in the treatment arm.
    :param treatment_trials: Admissible epochs in the treatment arm.
    :param control_pass: Primary-binary passes in the control arm.
    :param control_trials: Admissible epochs in the control arm.
    :param delta: Pre-registered minimum meaningful pass-rate difference,
        in [0, 1).
    :param prob_threshold: Pre-registered posterior probability required to
        call a directional region, in (0.5, 1]. The >0.5 floor makes the two
        directional regions mutually exclusive, since for delta >= 0
        P(d > delta) + P(d < -delta) <= 1.
    :raises ValueError: On counts that are not valid pass/trial pairs, or
        delta / prob_threshold outside their documented ranges.
    """
    for label, n_pass, n_trials in (
        ("treatment", treatment_pass, treatment_trials),
        ("control", control_pass, control_trials),
    ):
        if n_trials < 1:
            raise ValueError(f"{label}_trials must be >= 1; got {n_trials!r}")
        if not 0 <= n_pass <= n_trials:
            raise ValueError(
                f"{label}_pass must be in [0, {label}_trials={n_trials}]; got {n_pass!r}"
            )
    if not 0.0 <= delta < 1.0:
        raise ValueError(f"delta must be in [0, 1); got {delta!r}")
    if not 0.5 < prob_threshold <= 1.0:
        raise ValueError(f"prob_threshold must be in (0.5, 1]; got {prob_threshold!r}")

    t_alpha = 1.0 + treatment_pass
    t_beta = 1.0 + (treatment_trials - treatment_pass)
    c_alpha = 1.0 + control_pass
    c_beta = 1.0 + (control_trials - control_pass)

    p_better = _p_difference_exceeds(t_alpha, t_beta, c_alpha, c_beta, delta)
    p_worse = _p_difference_exceeds(c_alpha, c_beta, t_alpha, t_beta, delta)

    if p_better >= prob_threshold:
        outcome = TwoArmOutcome.TREATMENT_BETTER
        rationale = (
            f"TREATMENT_BETTER: P(p_t - p_c > {delta:.2f}) = {p_better:.4f} >= "
            f"{prob_threshold:.2f} under independent Beta posteriors "
            f"({treatment_pass}/{treatment_trials} vs {control_pass}/{control_trials})."
        )
    elif p_worse >= prob_threshold:
        outcome = TwoArmOutcome.TREATMENT_WORSE
        rationale = (
            f"TREATMENT_WORSE: P(p_c - p_t > {delta:.2f}) = {p_worse:.4f} >= "
            f"{prob_threshold:.2f} — the registered reverse (reactance) region "
            f"({treatment_pass}/{treatment_trials} vs {control_pass}/{control_trials})."
        )
    else:
        outcome = TwoArmOutcome.NULL
        rationale = (
            f"NULL at registered power: P(better) = {p_better:.4f}, "
            f"P(worse) = {p_worse:.4f}, neither >= {prob_threshold:.2f}. "
            "No transformative effect resolved on this model/fixture; this is "
            "not evidence that no effect exists (registered power floor)."
        )

    return TwoArmGateResult(
        outcome=outcome,
        p_treatment_better=p_better,
        p_treatment_worse=p_worse,
        treatment_alpha=t_alpha,
        treatment_beta=t_beta,
        control_alpha=c_alpha,
        control_beta=c_beta,
        delta=delta,
        prob_threshold=prob_threshold,
        rationale=rationale,
    )
