"""Operator-facing keep/cut verdict layer (S67/S68).

Maps measurement outcomes to the decision the operator actually has:

    "I run ~75 skills in my Claude Code setup. Which are worth their slot, and which
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
  2026-07-09). A skill can only reach KEEP if the Null arm fails often enough
  (p0 ≤ ~0.3) that a transformative lift is even detectable. The "~" is the
  pre-registration's own hedge — the boundary is soft; a p0 near the ceiling is
  borderline, not a sharp verdict flip.

Screen verdict rules (Path A, `screen_verdict`), ordered:
  A1. p0 outside [0, 1] → ValueError (not a rate).
  A2. p0 > TRANSFORMATIVE_NULL_CEILING, split by value_class (the #74/#76 guard):
        - value_class == transformative-lift → CUT(subsumed). The Null arm is too
          competent for the skill to be transformative; no affordable paired run
          can change that (a marginal lift below the bar is refused BY DESIGN).
            - p0 == 1.0: total ceiling — the model never fails without the skill.
            - ceiling > p0 > 1.0-nothing: subsumed WITH measured headroom — fails
              sometimes, but not often enough to clear the transformative bar.
        - any other class, OR unset (default) → CANT_TELL_YET (wrong instrument),
          NEVER CUT. The transformative-lift estimand is the WRONG INSTRUMENT for a
          trap/discipline/calibration skill: a high Null pass-rate means "the trap
          did not fire in this screen", not "the model does this unaided" — so a
          CUT(subsumed) here would be a category error. The verdict carries
          ``wrong_instrument=True`` (the board routes the cell to the
          field-evidence lane). The default is "not transformative-lift" so an
          UNCLASSIFIED skill is never false-CUT while its class is pending.
  A3. p0 <= TRANSFORMATIVE_NULL_CEILING → CANT_TELL_YET (sourced candidate),
      unchanged, regardless of value_class. The Null arm fails often enough that
      the skill COULD be transformative — but no paired run has confirmed a KEEP.
      This is a task-sourcing success, not a verdict yet.

Paired verdict rules (Path B, `paired_verdict`):
  B1. ClauseStatus.PASSED → KEEP (paired posterior cleared the transformative bar).
  B2. ClauseStatus.FAILED → CUT(no_lift) — measured, skill did not deliver a
      transformative lift on a task where the model needed help. This is NOT
      "subsumed" (the model fails without the skill) and NOT "harmful" (see below);
      it is a distinct, honestly-labelled cut.
  B3. ClauseStatus.UNMEASURED → CANT_TELL_YET (underpowered / budget / no data).
  B4. ClauseStatus.CONFOUNDED → CANT_TELL_YET (evidence exists but is confounded).

CUT(harmful) requires a SIGNED-delta interval. The Stage-0 screen path and the
bare-point `ContributionSummary.full_vs_null_delta` still cannot distinguish
"no effect" from "worse", so `screen_verdict` / `paired_verdict` never emit it.
The matched Gate-2 path (#85) produces a signed-delta interval via
`effect_from_matched_gate2`; `matched_gate2_verdict` emits CUT(harmful) there,
and `harmful_verdict_supported(effect)` returns True for that estimate.

Path C verdict rules (`matched_gate2_verdict`), by Gate2Decision (#86/#87):
  C1. decision is None → ValueError (refusal-over-coercion; no silent scaffold map).
  C2. BENEFIT → KEEP (class-independent).
  C3. HARM → CUT(harmful) (class-independent — harm is cut regardless of intended value).
  C4. EQUIVALENT, split by value_class (the #76/#77 guard, mirrored onto Path C at #87):
        - value_class == transformative-lift → CUT(no_lift). Pass-rate lift is this
          class's estimand; EQUIVALENT means the skill did not deliver it.
        - any other class, OR unset (default) → CANT_TELL_YET (wrong_instrument=True),
          NEVER CUT. Guard/calibration skills are measured on hazard-enriched pairs;
          EQUIVALENT does not mean "delete it" — the pass/fail-lift instrument is the
          wrong instrument for a non-lift skill. Unset defaults to "not transformative-
          lift" so an unclassified skill is never false-CUT while its class is pending.
  C5. UNRESOLVED → CANT_TELL_YET (class-independent).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, assert_never

from skill_harness.aggregation.status import ClauseStatus
from skill_harness.oc import Gate2Decision
from skill_harness.semantics import PRE_REGISTRY_ESTIMAND_LABEL, RegisteredScope

if TYPE_CHECKING:
    from skill_harness.aggregation.profile import EffectEstimate

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
    """Skill makes outcomes measurably WORSE. Emitted only by the matched
    Gate-2 path (`matched_gate2_verdict`) once a signed-delta interval is
    available; never by screen_verdict / paired_verdict. See
    harmful_verdict_supported()."""


class ValueClass(StrEnum):
    """The value KIND of a skill — which estimand can even see it (#74/#76).

    The screen path measures TRANSFORMATIVE LIFT only (the module docstring's
    threshold provenance: "the instrument detects TRANSFORMATIVE skills only").
    So ``screen_verdict``'s ``p0 above the bar → CUT(subsumed)`` mapping is VALID
    ONLY for a skill whose value IS transformative lift. For any other class it
    is a category error — the wrong instrument — so the guard withholds the CUT
    and routes to the field-evidence lane instead (US-1/US-2).

    Deliberately NOT the ``Estimand`` enum. ``Estimand`` is the decision TARGET of
    a measured arm — ratified at exactly two members, docstring-locked and
    ``drift_check.py`` DC-4-guarded against a third (C-FIX-1). ``ValueClass`` is
    orthogonal: the skill's value kind, not a scope/estimand field (it is NOT read
    off ``RegisteredScope`` — the four target records are pre-registry screens with
    ``scope = None``, and #41 bans retrofitting a label onto them, so the class
    must be an independent parameter). Unlike ``Estimand``, this enum is EXPECTED
    to grow: the third partition (F8a) was left to be named from the real portfolio
    in the follow-up classify-the-11 ticket (#77), NOT at #76. #77 resolved F8a from
    the actual distribution of the 11 skills → ``CALIBRATION`` (the pre-registered
    placeholder candidates ``field-governed`` / ``variance`` were not what the real
    portfolio named). The guard branches only on ``TRANSFORMATIVE_LIFT`` vs not, so
    every non-transformative member (trap-discipline, calibration) withholds the CUT
    identically; the distinction is descriptive (which non-transformative KIND), not
    a guard-behaviour change.
    """

    TRANSFORMATIVE_LIFT = "transformative-lift"
    """The screen instrument's own estimand: the skill is meant to let the model
    succeed on a task it fails unaided. p0 above the bar genuinely means
    "subsumed" for this class → the existing CUT stands."""

    TRAP_DISCIPLINE = "trap-discipline"
    """A guard/discipline skill (e.g. a git-pull-rebase trap): it prevents a wrong
    action, it does not add a capability. p0 = 1.00 on a Null screen means "the
    trap did not fire here", NOT "the model does this unaided" — the
    transformative-lift instrument cannot see its value, so it must never be CUT
    on a screen ceiling."""

    CALIBRATION = "calibration"
    """An evaluation/measurement-soundness skill (e.g. bayesian-eval-discipline,
    llm-judge-calibration, append-only-evidence-design): it makes a measurement
    trustworthy — statistical rigour, judge calibration, evidence integrity. Like
    trap-discipline it adds no task capability the transformative-lift screen can
    see, so p0 = 1.00 on a Null screen means "this screen task did not exercise the
    calibration hazard", NOT "the model does this unaided" — it must never be CUT
    on a screen ceiling. Named at #77 as the canonical F8a third partition, from
    the real portfolio (3 of the 11 are calibration; 0 are transformative-lift)."""


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
    wrong_instrument: bool = False
    """Board-layer routing signal (#74/#76/#87). Set True when a path WITHHELD a
    CUT because ``value_class`` is not transformative-lift — the
    transformative-lift instrument cannot see this skill's value. Fires on the
    screen path (above-bar p0) and on Path C (matched EQUIVALENT). The future
    BoardCell consumes this to route the cell to the field-evidence lane
    (``evidence_lane = field``) and render "HOLD — wrong instrument" rather than
    "HOLD — untested (sourced candidate)". Default False keeps every existing
    verdict and call site unchanged; it is never True on a CUT or a KEEP, nor on
    the ordinary below-bar sourced-candidate / UNRESOLVED CANT_TELL_YET."""

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


def screen_verdict(
    p0: float,
    *,
    scope: RegisteredScope | None = None,
    value_class: ValueClass | None = None,
) -> VerdictResult:
    """Map a Stage-0 Null screen pass-rate to a keep/cut verdict.

    p0 is the fraction of Null-arm (no-skill) epochs that passed on a domain task.
    See rules A1-A3 in the module docstring. ``scope`` is the registered claim
    boundary the verdict carries; omit it ONLY for pre-registry observations
    (historical screens), which render estimand n/a.

    ``value_class`` is the #74/#76 wrong-instrument guard: the ``p0 above the bar
    → CUT(subsumed)`` mapping fires ONLY for ``ValueClass.TRANSFORMATIVE_LIFT``.
    For any other class — or when UNSET (the default is "not transformative-lift",
    so an unclassified skill is never false-CUT) — an above-bar p0 yields
    CANT_TELL_YET carrying ``wrong_instrument=True`` (route to the field lane),
    never CUT. Below the bar the verdict is the sourced-candidate CANT_TELL_YET
    regardless of class.
    """
    if not 0.0 <= p0 <= 1.0:
        raise ValueError(f"p0 must be a pass-rate in [0, 1]; got {p0!r}")

    if p0 > TRANSFORMATIVE_NULL_CEILING:
        if value_class is not ValueClass.TRANSFORMATIVE_LIFT:
            if value_class is None:
                class_clause = (
                    "this skill has no value class yet (unclassified), so it cannot be "
                    "confirmed transformative-lift and the subsumed CUT is withheld until "
                    "the skill is classified"
                )
            else:
                class_clause = (
                    f"this skill's value class is {value_class.value!r}, not "
                    f"transformative-lift, so the transformative instrument cannot see its "
                    f"value (e.g. a trap/discipline skill scoring p0=1 means the trap did "
                    f"not fire, NOT that the model is unaided) and CUT(subsumed) would be a "
                    f"category error"
                )
            rationale = (
                f"CAN'T-TELL-YET (wrong instrument): Null arm p0={p0:.2f} is above the "
                f"~{TRANSFORMATIVE_NULL_CEILING:.2f} transformative bar, but {class_clause}. "
                f"Verdict withheld; routed to the field-evidence lane."
            )
            return VerdictResult(
                KeepCutVerdict.CANT_TELL_YET,
                None,
                rationale,
                scope=scope,
                wrong_instrument=True,
            )
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
    clause_status: ClauseStatus,
    *,
    scope: RegisteredScope | None = None,
    pi_c_hat: float | None = None,
    pi_c_n: int | None = None,
    pi_c_ci_low: float | None = None,
    pi_c_ci_high: float | None = None,
    pi_c_confidence: float | None = None,
) -> VerdictResult:
    """Map a paired-run terminal ClauseStatus to a keep/cut verdict.

    See rules B1-B4 in the module docstring. Path B has never fired to date; this
    mapping is prospective. ``scope`` is the registered claim boundary the
    verdict carries; omit it ONLY for pre-registry observations.

    ``pi_c_hat``..``pi_c_ci_high`` carry the invocation-rate stratifier from the
    paired ingest path. When provided, every verdict rationale carries the pi_c
    line per #36 adoption 4 display rule: ``pi_c_hat = k/n = 0.xxxx [95% CI lo, hi]``.
    At pi_c = 0 the CACE secondary is stated as not identified, never computed.
    Callers minting a paired-path verdict under #384 must pass pi_c — the
    optional form exists only for pre-#384 Path B unit fixtures.
    """
    pi_c_line = ""
    if pi_c_hat is not None and pi_c_n is not None:
        ci_lo = pi_c_ci_low if pi_c_ci_low is not None else 0.0
        ci_hi = pi_c_ci_high if pi_c_ci_high is not None else 1.0
        conf = pi_c_confidence if pi_c_confidence is not None else 0.95
        # #36 adoption 4 display: pi_c_hat = k/n [95% CI lo, hi]
        k = round(pi_c_hat * pi_c_n)
        pi_c_line = (
            f" pi_c_hat = {k}/{pi_c_n} = {pi_c_hat:.4f} [{conf:.0%} CI {ci_lo:.4f}, {ci_hi:.4f}]."
        )
        if pi_c_hat == 0.0:
            pi_c_line += " CACE secondary is not identified (zero invocations with full exposure)."

    match clause_status:
        case ClauseStatus.PASSED:
            return VerdictResult(
                KeepCutVerdict.KEEP,
                None,
                (
                    f"KEEP: paired Full-vs-Null cleared the transformative bar (Null ≤ "
                    f"~{TRANSFORMATIVE_NULL_CEILING:.2f}, Full ≥ "
                    f"~{TRANSFORMATIVE_FULL_FLOOR:.2f}, posterior ≥ pass threshold)."
                    f"{pi_c_line}"
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
                    f"{pi_c_line}"
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
                    f"{pi_c_line}"
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
                    f"{pi_c_line}"
                ),
                scope=scope,
            )
        case _:
            assert_never(clause_status)


# ---------------------------------------------------------------------------
# Path C — matched Gate-2 effect (signed-delta interval)
# ---------------------------------------------------------------------------


def matched_gate2_verdict(
    effect: EffectEstimate,
    *,
    scope: RegisteredScope | None = None,
    value_class: ValueClass | None = None,
) -> VerdictResult:
    """Map a matched Gate-2 EffectEstimate to a keep/cut verdict.

    Harm is a first-class CUT sub-reason here — never folded into no_lift.
    Requires ``effect.decision`` from ``effect_from_matched_gate2``; a scaffold
    estimate without a Gate-2 decision is refused (no silent coercion).

    ``value_class`` is the #76/#77/#87 wrong-instrument guard on EQUIVALENT:
    ``EQUIVALENT → CUT(no_lift)`` fires ONLY for ``ValueClass.TRANSFORMATIVE_LIFT``.
    For any other class — or when UNSET (default "not transformative-lift") —
    EQUIVALENT yields CANT_TELL_YET carrying ``wrong_instrument=True``, never CUT.
    BENEFIT / HARM / UNRESOLVED are class-independent (see rules C2-C5).
    """
    if effect.decision is None:
        raise ValueError(
            "matched_gate2_verdict requires effect.decision from the matched "
            "Gate-2 path; a scaffold EffectEstimate without a decision cannot "
            "be coerced into a verdict"
        )
    delta_clause = (
        f"signed delta={effect.mean:.3f}, 95% CI [{effect.ci_lo:.3f}, {effect.ci_hi:.3f}]"
    )
    match effect.decision:
        case Gate2Decision.BENEFIT:
            return VerdictResult(
                KeepCutVerdict.KEEP,
                None,
                f"KEEP: matched Gate-2 certified BENEFIT ({delta_clause}).",
                scope=scope,
            )
        case Gate2Decision.HARM:
            return VerdictResult(
                KeepCutVerdict.CUT,
                CutSubReason.HARMFUL,
                (
                    f"CUT (harmful): matched Gate-2 certified HARM ({delta_clause}). "
                    f"First-class harm — not 'no lift'."
                ),
                scope=scope,
            )
        case Gate2Decision.EQUIVALENT:
            if value_class is not ValueClass.TRANSFORMATIVE_LIFT:
                if value_class is None:
                    class_clause = (
                        "this skill has no value class yet (unclassified), so it cannot be "
                        "confirmed transformative-lift and the no-lift CUT is withheld until "
                        "the skill is classified"
                    )
                else:
                    class_clause = (
                        f"this skill's value class is {value_class.value!r}, not "
                        f"transformative-lift, so the pass/fail-lift instrument cannot see its "
                        f"value (e.g. a guard skill measured EQUIVALENT on hazard-enriched "
                        f"pairs does not mean 'delete it') and CUT(no_lift) would be a "
                        f"category error"
                    )
                rationale = (
                    f"CAN'T-TELL-YET (wrong instrument): matched Gate-2 certified "
                    f"EQUIVALENT ({delta_clause}), but {class_clause}. "
                    f"Verdict withheld; routed to the field-evidence lane."
                )
                return VerdictResult(
                    KeepCutVerdict.CANT_TELL_YET,
                    None,
                    rationale,
                    scope=scope,
                    wrong_instrument=True,
                )
            return VerdictResult(
                KeepCutVerdict.CUT,
                CutSubReason.NO_LIFT,
                (
                    f"CUT (no lift): matched Gate-2 certified EQUIVALENT ({delta_clause}). "
                    f"Not harmful — the interval does not support worse."
                ),
                scope=scope,
            )
        case Gate2Decision.UNRESOLVED:
            return VerdictResult(
                KeepCutVerdict.CANT_TELL_YET,
                None,
                (f"CAN'T-TELL-YET: matched Gate-2 left the contrast UNRESOLVED ({delta_clause})."),
                scope=scope,
            )
        case _:
            assert_never(effect.decision)


# ---------------------------------------------------------------------------
# CUT(harmful) support gate
# ---------------------------------------------------------------------------


def harmful_verdict_supported(effect: EffectEstimate | None = None) -> bool:
    """Whether the harness can emit a CUT(harmful) verdict for this estimate.

    No-arg / None → False: the Stage-0 screen path and bare-point
    ContributionSummary.full_vs_null_delta still cannot distinguish worse from
    no-effect. A matched Gate-2 EffectEstimate (decision set, signed interval)
    → True: harm is then a first-class Gate-2 outcome via matched_gate2_verdict.
    """
    return effect is not None and effect.decision is not None
