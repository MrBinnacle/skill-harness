"""Operator-facing keep/cut verdict layer (S67/S68).

Maps measurement outcomes to the decision the operator actually has:

    "I run ~75 skills in my Claude Code setup. Which earn their slot, and which
     are dead weight I should delete?"

This module is PURE logic — no I/O, no DB, no datetime, no wire format. It maps
an already-measured outcome to a verdict; sourcing/persisting the outcome is a
separate concern (see the two data paths below).

Two data paths feed a verdict (per the v0.2 pre-registration):

  Path A — Stage-0 Null screen (`p0`). Run the STOCK agent WITHOUT the skill on
    a domain task; `p0` = fraction of Null epochs that pass. This is the DOMINANT
    path: every real verdict in the program to date is a screen outcome (the
    per-record ledger in `docs/observations/` is canonical for those historical
    records and their counts). `screen_verdict()` maps it.

  Path B — paired Full-vs-Null (`ClauseStatus`). Launches only when the screen
    shows the skill has room to matter. FIRING TRIGGER: the first task whose Null
    screen returns p0 < 1 (real-workload or engineered) — that is the first skill
    with epochs the skill could actually improve. Has NEVER fired to date: every
    screen run so far ceilings at p0 = 1.00 (per-record history in
    `docs/observations/`; dispositions stand as dated decisions), so no paired
    run has been warranted. The mapping is coded and $0-validated (7/7
    oracle-discrimination cases on the git-pull fixture) but unexercised on live
    paired data. `paired_verdict()` maps it.

Threshold provenance (do NOT silently retune — operator-accepted values decision):
  The instrument detects TRANSFORMATIVE skills only. Under arm-independence the
  locked stopping rule's 80%-power region requires roughly Null pass ≤ ~0.3 AND
  Full pass ≥ ~0.8 (v0.2-preregistration.md, "Detectability disclosure", accepted
  2026-07-09). A skill can only earn KEEP if the Null arm fails often enough
  (p0 ≤ ~0.3) that a transformative lift is even detectable. The "~" is the
  pre-registration's own hedge — the boundary is soft; a p0 near the ceiling is
  borderline, not a sharp verdict flip.

Screen verdict rules (Path A, `screen_verdict`), ordered:
  A1. p0 outside [0, 1] → ValueError (not a rate).
  A2. p0 > TRANSFORMATIVE_NULL_CEILING → CUT(subsumed). The Null arm is too
      competent for the skill to be transformative; no affordable paired run can
      change that (a marginal lift below the bar is refused BY DESIGN).
        - p0 == 1.0: total ceiling — the model never fails without the skill.
        - ceiling > p0 > 1.0-nothing: subsumed WITH measured headroom — the model
          fails sometimes, but not often enough to clear the transformative bar.
  A3. p0 <= TRANSFORMATIVE_NULL_CEILING → CANT_TELL_YET. The Null arm fails often
      enough that the skill COULD be transformative — but no paired run has
      confirmed a KEEP. This is a task-sourcing success, not a verdict yet.

Paired verdict rules (Path B, `paired_verdict`):
  B1. ClauseStatus.PASSED → KEEP (paired posterior cleared the transformative bar).
  B2. ClauseStatus.FAILED → CUT(no_lift) — measured, skill did not deliver a
      transformative lift on a task where the model needed help. This is NOT
      "subsumed" (the model fails without the skill) and NOT "harmful" (see below);
      it is a distinct, honestly-labelled cut.
  B3. ClauseStatus.UNMEASURED → CANT_TELL_YET (underpowered / budget / no data).
  B4. ClauseStatus.CONFOUNDED → CANT_TELL_YET (evidence exists but is confounded).

CUT(harmful) is DEFERRED from v1 (design lock S64): representing "actively worse"
honestly requires a SIGNED-delta confidence interval, and today's
`ContributionSummary.full_vs_null_delta` is a bare point estimate with no CI — it
cannot distinguish "no effect" from "worse". The sub-reason is defined so the
verdict vocabulary is complete, but no mapping emits it yet; see
`harmful_verdict_supported()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from skill_harness.aggregation.status import ClauseStatus
from skill_harness.semantics import PRE_REGISTRY_ESTIMAND_LABEL, RegisteredScope

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class KeepCutVerdict(StrEnum):
    """Operator-facing verdict on a skill.

    Modelled on the repo's own ClauseStatus/UnmeasuredSubReason pattern: a small
    set of top-level verdicts, with CUT qualified by a sub-reason (below).
    """

    KEEP = "KEEP"
    CUT = "CUT"
    CANT_TELL_YET = "CANT_TELL_YET"


class CutSubReason(StrEnum):
    """Sub-reason qualifying a CUT verdict."""

    SUBSUMED = "subsumed"
    """Screen path: the model does it without the skill (p0 above the
    transformative bar). Includes the total-ceiling case (p0 = 1)."""

    NO_LIFT = "no_lift"
    """Paired path: measured on a task where the model needed help, and the skill
    did not deliver a transformative lift (ClauseStatus.FAILED)."""

    HARMFUL = "harmful"
    """Skill makes outcomes measurably WORSE. NOT YET DERIVABLE — requires a
    signed-delta confidence interval the current point-estimate delta cannot
    supply. Defined for vocabulary completeness; no mapping emits it in v1.
    See harmful_verdict_supported()."""


# ---------------------------------------------------------------------------
# Locked thresholds (operator-accepted; see module docstring provenance)
# ---------------------------------------------------------------------------

TRANSFORMATIVE_NULL_CEILING: float = 0.3
"""Null pass-rate ceiling for a skill to be a KEEP candidate. p0 above this →
the skill cannot be transformative (v0.2-preregistration.md Detectability
disclosure, "Null pass ≤ ~0.3"). Soft boundary — the pre-reg hedges with "~"."""

TRANSFORMATIVE_FULL_FLOOR: float = 0.8
"""Full pass-rate floor a KEEP requires (v0.2-preregistration.md, "Full pass ≥
~0.8"). Not gated in the screen path (no Full arm there); documented for the
paired path and for operator-facing rationale."""


# ---------------------------------------------------------------------------
# Result struct
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerdictResult:
    """A verdict plus the machine-checkable reason and human rationale.

    ``scope`` is the registered (skill x task family x estimand x delivery
    mechanism) tuple the verdict is confined to (#36/#51). ``None`` means a
    pre-registry observation — every historical Stage-0 screen — and renders as
    the honest n/a marker, never a retrofitted label (#41 rule).
    """

    verdict: KeepCutVerdict
    cut_sub_reason: CutSubReason | None  # set iff verdict == CUT
    rationale: str
    scope: RegisteredScope | None = None

    @property
    def estimand_label(self) -> str:
        """The estimand string render surfaces print — always an ``Estimand``
        enum value or the ratified pre-registry marker, never free-typed (the
        surface the DC-4 drift row pins)."""
        if self.scope is None:
            return PRE_REGISTRY_ESTIMAND_LABEL
        return self.scope.estimand.value


# ---------------------------------------------------------------------------
# Path A — Stage-0 Null screen
# ---------------------------------------------------------------------------


def screen_verdict(p0: float, *, scope: RegisteredScope | None = None) -> VerdictResult:
    """Map a Stage-0 Null screen pass-rate to a keep/cut verdict.

    p0 is the fraction of Null-arm (no-skill) epochs that passed on a domain task.
    See rules A1-A3 in the module docstring. ``scope`` is the registered claim
    boundary the verdict carries; omit it ONLY for pre-registry observations
    (historical screens), which render estimand n/a.
    """
    if not 0.0 <= p0 <= 1.0:
        raise ValueError(f"p0 must be a pass-rate in [0, 1]; got {p0!r}")

    if p0 > TRANSFORMATIVE_NULL_CEILING:
        if p0 >= 1.0:
            rationale = (
                f"CUT (subsumed): Null arm passed every epoch (p0={p0:.2f}) — the "
                f"model does this without the skill. Total ceiling."
            )
        else:
            rationale = (
                f"CUT (subsumed, with measured headroom): Null arm p0={p0:.2f} sits "
                f"above the ~{TRANSFORMATIVE_NULL_CEILING:.2f} transformative bar, so no "
                f"paired run can clear the bar; the model fails sometimes but not often "
                f"enough for the skill to be transformative."
            )
        return VerdictResult(KeepCutVerdict.CUT, CutSubReason.SUBSUMED, rationale, scope=scope)

    rationale = (
        f"CAN'T-TELL-YET: Null arm p0={p0:.2f} is at or below the "
        f"~{TRANSFORMATIVE_NULL_CEILING:.2f} bar — the model fails often enough that the "
        f"skill could be transformative. No paired Full-vs-Null run has confirmed a "
        f"KEEP; this is a sourced candidate, not a verdict."
    )
    return VerdictResult(KeepCutVerdict.CANT_TELL_YET, None, rationale, scope=scope)


# ---------------------------------------------------------------------------
# Path B — paired Full-vs-Null
# ---------------------------------------------------------------------------


def paired_verdict(
    clause_status: ClauseStatus, *, scope: RegisteredScope | None = None
) -> VerdictResult:
    """Map a paired-run terminal ClauseStatus to a keep/cut verdict.

    See rules B1-B4 in the module docstring. Path B has never fired to date; this
    mapping is prospective. ``scope`` is the registered claim boundary the
    verdict carries; omit it ONLY for pre-registry observations.
    """
    match clause_status:
        case ClauseStatus.PASSED:
            return VerdictResult(
                KeepCutVerdict.KEEP,
                None,
                (
                    f"KEEP: paired Full-vs-Null cleared the transformative bar (Null ≤ "
                    f"~{TRANSFORMATIVE_NULL_CEILING:.2f}, Full ≥ "
                    f"~{TRANSFORMATIVE_FULL_FLOOR:.2f}, posterior ≥ pass threshold)."
                ),
                scope=scope,
            )
        case ClauseStatus.FAILED:
            return VerdictResult(
                KeepCutVerdict.CUT,
                CutSubReason.NO_LIFT,
                (
                    "CUT (no lift): measured on a task where the model needed help, and "
                    "the skill did not deliver a transformative lift (paired posterior "
                    "below the fail threshold). Not 'subsumed' — the model fails without "
                    "the skill."
                ),
                scope=scope,
            )
        case ClauseStatus.UNMEASURED:
            return VerdictResult(
                KeepCutVerdict.CANT_TELL_YET,
                None,
                (
                    "CAN'T-TELL-YET: paired run is UNMEASURED (underpowered / budget / no "
                    "admissible data). Needs more epochs or a better-sourced task."
                ),
                scope=scope,
            )
        case ClauseStatus.CONFOUNDED:
            return VerdictResult(
                KeepCutVerdict.CANT_TELL_YET,
                None,
                (
                    "CAN'T-TELL-YET: paired evidence is CONFOUNDED (a harness/environment "
                    "difference co-varies with the arm). Verdict withheld until the "
                    "confound is resolved."
                ),
                scope=scope,
            )
        case _:
            assert_never(clause_status)


# ---------------------------------------------------------------------------
# CUT(harmful) support gate
# ---------------------------------------------------------------------------


def harmful_verdict_supported() -> bool:
    """Whether the harness can currently emit a CUT(harmful) verdict.

    Always False in v1: CUT(harmful) needs a SIGNED-delta confidence interval to
    distinguish "actively worse" from "no effect". Today's
    ContributionSummary.full_vs_null_delta is a bare point estimate with no CI, so
    "worse" cannot be told from "no effect" honestly. Wire this to True only once a
    paired run produces a signed-delta interval.
    """
    return False
