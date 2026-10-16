"""Path C: route an ablation clause decision through the Gate-2 discordant rule.

#368, ruled 2026-08-31, recorded in docs/INVARIANTS.md section 8. The estimand
of record is the DISCORDANT TABLE, and this module is the ablation lane's
consumer of it.

Why this module exists, given that stopping.py already conditions on the
discordant table
------------------------------------------------------------------------
Conditioning is necessary and not sufficient. ``BetaBinomialAccumulator``
reports q = P(Full wins | discordant), and q alone cannot see how often a
direction occurs at all. A clause that wins seven of the eight comparisons it
did not tie, having tied thirty, has an excellent q and a net lift of about
0.05. The scalar rule PASSES it. Nothing in the conditional posterior objects,
because the tie count was conditioned away.

That is the practical-significance inversion section 8 names in its Revisit-if
clause, and it is not hypothetical: the sizing frontier reaches d = 0.2, where
the minimum detectable q of 0.97 corresponds to a net lift of 0.188, under the
registered delta_min of 0.20 (tests/test_ablation_sizing.py pins it).

Gate 2 resolves it without reintroducing the blended rate. Its posterior is
Dirichlet over the four paired cells with the two tie cells pooled, so the tie
count returns as the pooled tie cell and the decision is made on the net lift
delta = p_f - p_n, identically d(2q - 1). The tie count is thereby evidence
about d, which is what it always was, rather than half-evidence about q, which
it never was.

The pooling is why the ablation lane fits Gate 2 exactly. An ablation tie is
undifferentiated: Full and Ablated_k scored equal on the axis, and there is no
both-pass / both-fail split to recover. Gate 2 never needs one, because
``gate2_region_probs`` pools those two cells anyway - every decision functional
depends on them only through their sum.

What is consumed by reference, and what is not
----------------------------------------------
gamma, delta_min and q_min are read from a ratification record and never
restated here. A threshold written into this file would be a cache of a
lookup, and the whole point of registering thresholds is that the code cannot
drift from the registration.

``n_pairs`` is taken from the REALISED comparison count, not from the record's
``n``. #368 asks which of the two the build consumes and this is the answer:
only the thresholds. The ablation lane is sequential with a variable stopping
point, so it has no fixed N to match against a registered one, and forcing the
record's N onto it would assert a design the lane did not run.

The consequence is stated rather than hidden: the operating characteristics of
a registered fixed-N Gate-2 design are NOT the operating characteristics of
this lane. ``gate2_oc`` describes the former. This module applies the former's
DECISION RULE to the latter's realised table, which is a defensible reading of
the evidence in hand and is not a power claim. A clause decided here inherits
the registered thresholds, not the registered design's error rates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skill_harness.ablation.stopping import StopDecision
from skill_harness.oc.gate2 import Gate2Decision, Gate2Design, Gate2RegionProbs, MMESpec
from skill_harness.oc.gate2 import gate2_decide as _gate2_decide
from skill_harness.oc.gate2 import gate2_region_probs as _gate2_region_probs
from skill_harness.ratification import parse_rat_record


class UnregisteredThresholdsError(ValueError):
    """A ratification record does not carry the Gate-2 thresholds Path C needs.

    Raised rather than defaulted. A missing threshold is a typed refusal, never
    an invented one: silently substituting a plausible gamma would produce a
    decision that looks registered and is not.
    """


@dataclass(frozen=True)
class RegisteredGate2Thresholds:
    """The thresholds Path C consumes, plus the id that registered them.

    Fields
    ------
    ratification_id : str
        The record's ``rat`` id, e.g. "RAT-0001". Recorded alongside any
        decision so a reader can retrieve what it was decided under.
    gamma : float
        Posterior mass required to certify a Gate-2 decision.
    delta_min : float
        Registered minimum meaningful net lift; also the equivalence margin.
    q_min : float
        Registered conditional-win-rate floor. Carried for provenance and
        frontier work; the three-sided decision rule does not read it.
    """

    ratification_id: str
    gamma: float
    delta_min: float
    q_min: float

    def design(self, n_pairs: int) -> Gate2Design:
        """Build the Gate-2 design for a realised comparison count.

        :param n_pairs: Comparisons actually drawn, ties included.
        :returns: A Gate2Design carrying the registered thresholds.
        :raises ValueError: If n_pairs < 1 (refused by Gate2Design).
        """
        return Gate2Design(
            n_pairs=n_pairs,
            gamma=self.gamma,
            mme=MMESpec(delta_min=self.delta_min, q_min=self.q_min),
        )


@dataclass(frozen=True)
class PathCResult:
    """A Gate-2 decision on an ablation clause's realised discordant table.

    Fields
    ------
    decision : Gate2Decision
        BENEFIT / HARM / EQUIVALENT / UNRESOLVED. Never a forced call.
    region_probs : Gate2RegionProbs
        The three posterior region masses, which sum to 1.
    ratification_id : str
        The record whose thresholds decided this.
    x_full_wins, x_ablated_wins, n_ties, n_pairs : int
        The realised table the decision was made on, carried so the decision
        is reproducible from the result alone.
    net_lift_point : float
        (x_f - x_n) / n_pairs, the plug-in estimate of delta. Reported for
        reading; the decision is made on posterior mass, not on this.
    """

    decision: Gate2Decision
    region_probs: Gate2RegionProbs
    ratification_id: str
    x_full_wins: int
    x_ablated_wins: int
    n_ties: int
    n_pairs: int
    net_lift_point: float


def registered_thresholds(record_path: Path | str) -> RegisteredGate2Thresholds:
    """Read the Gate-2 thresholds from a RATIFIED record.

    :param record_path: Path to the ratification record.
    :returns: The registered thresholds and the id that registered them.
    :raises UnregisteredThresholdsError: If the record is not RATIFIED, is not
        a gate2 record, or omits gamma / delta_min / q_min.
    """
    record = parse_rat_record(Path(record_path))

    if record.status != "RATIFIED":
        raise UnregisteredThresholdsError(
            f"{record.rat_id} has status {record.status!r}; Path C consumes "
            "RATIFIED thresholds only - an unratified record is a proposal"
        )
    if record.gate != "gate2":
        raise UnregisteredThresholdsError(
            f"{record.rat_id} registers gate {record.gate!r}, not 'gate2'; its "
            "thresholds were not calibrated for the three-sided discordant rule"
        )

    gamma, delta_min, q_min = record.gamma, record.delta_min, record.q_min
    missing = [
        name
        for name, value in (("gamma", gamma), ("delta_min", delta_min), ("q_min", q_min))
        if value is None
    ]
    if missing:
        raise UnregisteredThresholdsError(
            f"{record.rat_id} omits {', '.join(missing)}; Path C refuses rather "
            "than substituting a default, because a defaulted threshold makes an "
            "unregistered decision look registered"
        )
    # Narrowed by the refusal above. Written as an explicit re-check rather
    # than `assert`, which `python -O` strips (the F-4 rule in runner.py).
    if gamma is None or delta_min is None or q_min is None:  # pragma: no cover
        raise UnregisteredThresholdsError(f"{record.rat_id}: threshold check inconsistent")

    return RegisteredGate2Thresholds(
        ratification_id=record.rat_id,
        gamma=gamma,
        delta_min=delta_min,
        q_min=q_min,
    )


def decide_clause(decision: StopDecision, thresholds: RegisteredGate2Thresholds) -> PathCResult:
    """Decide an ablation clause on its realised discordant table.

    The clause's sequential run supplies the table; the registered thresholds
    supply the rule. ``n_pairs`` is the realised total comparison count, so the
    tie count enters through Gate-2's pooled tie cell and the effect-size floor
    applies (see the module docstring for what this does and does not claim).

    A run with zero comparisons is UNRESOLVED by Gate-2's defined
    zero-discordant branch, reached here through a degenerate one-pair design
    rather than by a special case, so the branch is the same one every other
    caller gets.

    :param decision: The stop decision carrying the realised table.
    :param thresholds: Registered thresholds from ``registered_thresholds``.
    :returns: The Gate-2 decision, its region masses, and the table.
    """
    x_f = decision.x_full_wins
    x_n = decision.x_ablated_wins
    n_pairs = max(decision.n_samples, 1)

    design = thresholds.design(n_pairs)
    gate_decision = _gate2_decide(design, x_f, x_n)
    probs = _gate2_region_probs(design, x_f, x_n)

    return PathCResult(
        decision=gate_decision,
        region_probs=probs,
        ratification_id=thresholds.ratification_id,
        x_full_wins=x_f,
        x_ablated_wins=x_n,
        n_ties=decision.n_ties,
        n_pairs=n_pairs,
        net_lift_point=(x_f - x_n) / n_pairs,
    )
