"""Decision-semantics vocabulary + estimand registry (PR-1; #36, #51).

Every verdict the harness emits is scoped to a registered
(skill x task family x estimand x delivery mechanism) tuple so no result can be
read as a broader claim than the run supports. This module is the vocabulary
authority for that tuple — PURE definitions, no I/O.

The registry is a labeling + routing decision over the two EXISTING subject
layers, not a new runner (resolution record #36, verified against source):

  - agentic paired (``subject/``; skill AVAILABLE, not forced) realizes the
    **treatment-policy** estimand — production default;
  - ablation forced-injection (``ablation/``; system-prompt-forced loading)
    realizes the **hypothetical** estimand — diagnostic.

Vocabulary is ICH E9(R1) (Estimands and Sensitivity Analysis in Clinical
Trials): "treatment-policy" answers "what happens under the production policy,
invoked or not"; "hypothetical" answers "what would happen were the skill
forced". The term "per-protocol" is BANNED repo-wide (``BANNED_DECISION_TERMS``)
because it names neither question while resembling both — the exact conflation
the registry exists to prevent. The allowlist is EMPTY by ratified decision and
grows only by dated amendment.

Delivery mechanism is part of the registered treatment (4-class taxonomy): a
CUT on model-pull may be pure retrieval failure while the production config is
hook-nudged, and nudge/block differ categorically (block forces π_c ≡ 1).
Verdicts therefore never generalize across delivery configs.

π_c (invocation rate) instrumentation is a separate ingest-layer concern; this
module only records HOW each mechanism's π_c is obtained (measured detector
lanes vs structural π_c ≡ 1). Historical pre-registry observations carry honest
n/a markers (``PRE_REGISTRY_ESTIMAND_LABEL``) — never a retrofitted label; the
per-record ledger in ``docs/observations/`` is canonical for those records.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Estimands — exactly two; the two subject layers ARE the two estimands (#36)
# ---------------------------------------------------------------------------


class Estimand(StrEnum):
    """A named decision target (ICH E9(R1) vocabulary — never "per-protocol").

    Exactly two members by ratified decision: each is realized by an existing
    subject layer. A third member here would be an invented decision target
    with no arm to realize it — do not add one without a new resolution record.
    """

    TREATMENT_POLICY = "treatment-policy"
    """Production default. Realized by the agentic paired subject layer: the
    skill is AVAILABLE under real invocation conditions, never forced."""

    HYPOTHETICAL = "hypothetical"
    """Diagnostic. Realized by the ablation layer: forced system-prompt
    injection — answers "what if the skill were always loaded", not "what
    happens in production"."""


# ---------------------------------------------------------------------------
# Delivery mechanism — part of the registered treatment (#36, 4-class taxonomy)
# ---------------------------------------------------------------------------


class DeliveryMechanism(StrEnum):
    """How the skill reaches the agent — registered as part of the treatment."""

    MODEL_PULL = "model-pull"
    """Model retrieves the skill on its own (description-triggered)."""

    HAND_INVOKED = "hand-invoked"
    """Operator invokes the skill explicitly (frozen into the task instance
    for treatment-policy evaluation — see ``RegisteredScope``)."""

    HOOK_NUDGED = "hook-nudged"
    """A hook suggests the skill; the model may still decline (π_c < 1)."""

    HOOK_BLOCKED = "hook-blocked"
    """A hook blocks progress until the skill is used (π_c ≡ 1 by construction)."""


class PiCHandling(StrEnum):
    """How π_c (invocation rate) is obtained for a delivery mechanism."""

    MEASURED = "measured"
    """Detector lane: π̂_c estimated from observed invocation events."""

    STRUCTURAL_ONE = "structural-one"
    """π_c ≡ 1 by construction — invocation is forced by the mechanism itself;
    there is nothing to detect."""


def pi_c_handling(mechanism: DeliveryMechanism) -> PiCHandling:
    """Map a delivery mechanism to its π_c handling (#36 item 3).

    Only model-pull and hook-nudged leave invocation to the model, so only they
    are detector lanes; hand-invoked (frozen-task) and hook-blocked force
    invocation by construction.
    """
    if mechanism in (DeliveryMechanism.MODEL_PULL, DeliveryMechanism.HOOK_NUDGED):
        return PiCHandling.MEASURED
    return PiCHandling.STRUCTURAL_ONE


# ---------------------------------------------------------------------------
# Hand-invoked class constants (#36 item 5)
# ---------------------------------------------------------------------------

HAND_INVOKED_NULL_ARM_SEMANTIC: str = "the invocation names an absent skill"
"""The ratified Null-arm semantic for the frozen-task hand-invoked design: the
Null arm receives the SAME frozen invocation but the skill does not exist, so
the stock agent improvises. That is the honest production counterfactual — but
NOT a neutral baseline, which is why ``RegisteredScope`` refuses a hand-invoked
treatment-policy registration whose semantic was not explicitly declared."""

PRE_REGISTRY_ESTIMAND_LABEL: str = "n/a (pre-registry observation)"
"""Honest marker for verdicts produced before the registry existed (#41 rule:
historical records carry n/a markers, never a retrofitted estimand label). The
per-record OBS ledger (``docs/observations/``) is canonical for those records."""


# ---------------------------------------------------------------------------
# The registered scope tuple
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisteredScope:
    """One registered (skill x task family x estimand x delivery mechanism)
    tuple — the claim boundary every verdict carries.

    One skill may hold multiple registrations (e.g. model-pull AND hook-nudged);
    a verdict under one registration says nothing about the others. π_c handling
    is derived from the mechanism, never stored separately (``pi_c``).

    Hand-invoked x treatment-policy is the frozen-task design (the only
    non-degenerate one for that class: a ``disable-model-invocation`` skill
    cannot be model-pulled, so a paraphrase task would force π_c ≡ 0 → perpetual
    refusal). Its Null-arm semantic MUST be explicitly declared at registration
    (``HAND_INVOKED_NULL_ARM_SEMANTIC`` is the ratified declaration); the
    registered fallback for the class is a hypothetical-only registration, which
    has no Null-arm counterfactual to declare.
    """

    skill: str
    task_family: str
    estimand: Estimand
    delivery_mechanism: DeliveryMechanism
    null_arm_semantic: str | None = None

    def __post_init__(self) -> None:
        if not self.skill.strip():
            raise ValueError("RegisteredScope.skill must be a non-blank skill id")
        if not self.task_family.strip():
            raise ValueError("RegisteredScope.task_family must be a non-blank family id")
        needs_null_arm = (
            self.delivery_mechanism is DeliveryMechanism.HAND_INVOKED
            and self.estimand is Estimand.TREATMENT_POLICY
        )
        if needs_null_arm and not (self.null_arm_semantic or "").strip():
            raise ValueError(
                "hand-invoked treatment-policy registration requires a declared "
                "Null-arm semantic (frozen-task design; see "
                "HAND_INVOKED_NULL_ARM_SEMANTIC for the ratified declaration)"
            )

    @property
    def pi_c(self) -> PiCHandling:
        """How π_c is obtained under this registration (derived, never stored)."""
        return pi_c_handling(self.delivery_mechanism)

    def label(self) -> str:
        """Scope fragment for verdict lines: ``"treatment-policy, hook-nudged"``
        (#36's ratified verdict-line shape; skill/family render as their own
        columns at the report layer)."""
        return f"{self.estimand.value}, {self.delivery_mechanism.value}"


# ---------------------------------------------------------------------------
# Banned vocabulary — the surface the DC-3 drift row consumes
# ---------------------------------------------------------------------------

BANNED_DECISION_TERMS: tuple[str, ...] = ("per-protocol",)
"""Decision-semantics terms banned repo-wide (code, docs, docstrings).

"per-protocol" names an as-treated analysis population from the clinical-trials
literature that E9(R1) explicitly superseded with the estimand framework; in
this repo it would read as either estimand while meaning neither. Enforced by
the pytest scan in ``tests/test_semantics.py`` today and by the drift-check CI
row DC-3 once that lands (the CI row is then the enforcement of record)."""

BANNED_TERM_ALLOWLIST: frozenset[str] = frozenset()
"""Files exempt from the banned-term scan. EMPTY by ratified decision — it
grows only by dated amendment. (The scan's self-exclusion of this module and
the scan test, which carry the literal token by necessity, is the structural
E1b definition-site pattern, not an allowlist entry.)"""
