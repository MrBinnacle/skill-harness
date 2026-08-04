"""Per-skill evaluation profile — separated GRADE-style axes (pure logic).

This module is a REPORTING-LAYER VIEW, not a new measurement. It presents the
harness's already-computed signals as SEPARATE columns, one row per skill:

    [ skill | disposition | verdict | evidence-quality | cost | effect ]

It never fuses those axes into a single ranking scalar. The discipline is the
GRADE separation: Guyatt et al. (BMJ 2008;336:924-6) warn that schemes which fail
to keep the *quality* of the evidence separate from the *strength* of the
recommendation "create confusion". The evidence-quality axis is an ORDINAL ladder
(Velleman & Wilkinson 1993 — no arithmetic on an ordinal scale): compare/sort by
its declared order, never average or add it.

Like ``verdict.py`` this module is PURE — no I/O, no DB, no datetime. Sourcing the
inputs (verdicts, screen counts, cost figures, frontmatter flags) is the CLI's job;
here we only map already-sourced inputs to rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from skill_harness.aggregation.status import N_MIN
from skill_harness.aggregation.verdict import CutSubReason, KeepCutVerdict
from skill_harness.oc import Gate2Decision, Gate2Design, gate2_decide
from skill_harness.oc.crosschecks import newcombe_interval

# ---------------------------------------------------------------------------
# Axis vocabularies (each axis has its OWN enum — never a shared scalar)
# ---------------------------------------------------------------------------


class RankingDisposition(StrEnum):
    """Whether a skill is eligible to compete in a keep/cut ranking.

    This is a single-axis eligibility label, NOT a rank or score.
    """

    ADMITTED = "ADMITTED"  # a KEEP — earns its slot
    EXCLUDED = "EXCLUDED"  # a CUT — cut from the library
    NOT_YET_RANKABLE = "NOT_YET_RANKABLE"  # needs evidence before it can compete


class EvidenceQuality(StrEnum):
    """Ordinal quality of the evidence behind a skill's disposition (low -> high).

    ORDINAL only. Use ``EVIDENCE_QUALITY_ORDER`` to compare/sort; never average,
    add, or otherwise do arithmetic on these labels (Velleman & Wilkinson 1993).
    """

    UNMEASURABLE = "UNMEASURABLE"  # cannot be screened by construction
    UNMEASURED = "UNMEASURED"  # never screened
    MEASURED_LOW = "MEASURED_LOW"  # underpowered / borderline screen
    MEASURED_HIGH = "MEASURED_HIGH"  # adequately-powered decisive screen


EVIDENCE_QUALITY_ORDER: tuple[EvidenceQuality, ...] = (
    EvidenceQuality.UNMEASURABLE,
    EvidenceQuality.UNMEASURED,
    EvidenceQuality.MEASURED_LOW,
    EvidenceQuality.MEASURED_HIGH,
)
"""The ordinal authority for the evidence-quality ladder, low -> high.

This tuple is the ONLY sanctioned way to order the ladder — its index is a
position, not a magnitude. Deliberately NOT a function that returns a number to
do arithmetic on: an ordinal scale admits sort/compare, not averaging."""


# ---------------------------------------------------------------------------
# Effect estimate (Stage-0 screen path leaves it None; matched Gate-2 populates)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectEstimate:
    """A per-skill effect estimate as a signed interval, never a bare point.

    Two producers:

    - Matched Gate-2 path (#85): signed paired delta = (full-only - null-only) / n
      with the Newcombe (1998) 95% interval over the four-outcome table, plus the
      three-sided Gate-2 decision (benefit / harm / equivalent / unresolved).
      ``decision`` is set; ``is_prior_only`` is False.
    - Scaffold / display-aid construction (tests, effect-per-cost): a rate-style
      bracket may omit ``decision`` (None). The Stage-0 screen path never builds
      one — profile rows keep ``effect is None`` there.
    """

    mean: float
    ci_lo: float
    ci_hi: float
    is_prior_only: bool
    decision: Gate2Decision | None = None


def effect_from_matched_gate2(
    design: Gate2Design,
    *,
    both_pass: int,
    full_only: int,
    null_only: int,
    both_fail: int,
) -> EffectEstimate:
    """Map a matched four-outcome table through Gate-2 to a signed EffectEstimate.

    Pure: no I/O. The caller pre-registers ``design`` (n_pairs, gamma, dual MME);
    this function ships no default delta / prob_threshold. Routes through
    ``gate2_decide`` only — never ``two_arm_gate`` (DIF-confined).

    :param design: Registered Gate-2 design (pair count + gamma + dual MME).
    :param both_pass: Pairs where both arms pass.
    :param full_only: Full-only-win pairs (x_f).
    :param null_only: Null-only-win pairs (x_n).
    :param both_fail: Pairs where both arms fail.
    :returns: Populated effect with signed MLE delta, Newcombe interval, decision.
    :raises ValueError: If any cell is negative, the table is empty, or the cell
        sum disagrees with ``design.n_pairs``.
    """
    cells = (both_pass, full_only, null_only, both_fail)
    if any(v < 0 for v in cells):
        raise ValueError(f"all four paired-outcome counts must be >= 0; got {cells}")
    n = both_pass + full_only + null_only + both_fail
    if n == 0:
        raise ValueError("the 2x2 table must contain at least one pair")
    if n != design.n_pairs:
        raise ValueError(
            f"paired-outcome counts must sum to design.n_pairs={design.n_pairs}; got {n}"
        )
    decision = gate2_decide(design, full_only, null_only)
    ci_lo, ci_hi = newcombe_interval(both_pass, full_only, null_only, both_fail)
    return EffectEstimate(
        mean=(full_only - null_only) / n,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        is_prior_only=False,
        decision=decision,
    )


# ---------------------------------------------------------------------------
# Mappers (pure)
# ---------------------------------------------------------------------------


def disposition_from_verdict(verdict: KeepCutVerdict | None) -> RankingDisposition:
    """Map a keep/cut verdict (or its absence) to a ranking disposition.

    - ``KEEP`` -> ADMITTED
    - ``CUT`` -> EXCLUDED
    - ``CANT_TELL_YET`` -> NOT_YET_RANKABLE
    - ``None`` (never screened) -> NOT_YET_RANKABLE

    On ``CANT_TELL_YET``: ``verdict.py`` calls it "a sourced candidate, not a
    verdict" — an unconfirmed skill is not admitted to ranking as if measured, so
    it maps to NOT_YET_RANKABLE. *Revisit if:* a harness doc explicitly wants
    can't-tell-yet skills to compete in ranking — then this is a conflict to
    surface, not to silently flip either way.
    """
    match verdict:
        case KeepCutVerdict.KEEP:
            return RankingDisposition.ADMITTED
        case KeepCutVerdict.CUT:
            return RankingDisposition.EXCLUDED
        case KeepCutVerdict.CANT_TELL_YET | None:
            return RankingDisposition.NOT_YET_RANKABLE


def evidence_quality_from_screen(
    *, has_screen: bool, n_trials: int, is_disable_model_invocation: bool
) -> EvidenceQuality:
    """Map a skill's screen situation to its ordinal evidence-quality label.

    - ``is_disable_model_invocation`` -> UNMEASURABLE: a skill the model never
      auto-invokes cannot be Null-arm screened, so the screen is meaningless for
      it (wins over any stray screen rows).
    - else no screen -> UNMEASURED.
    - else ``n_trials < N_MIN`` -> MEASURED_LOW (underpowered / borderline).
    - else -> MEASURED_HIGH.

    *Revisit if:* the code exposes a cleaner power/CI signal for a screen than raw
    ``n_trials`` (e.g. a stored power flag) — prefer it, keep the four-value shape.
    """
    if is_disable_model_invocation:
        return EvidenceQuality.UNMEASURABLE
    if not has_screen:
        return EvidenceQuality.UNMEASURED
    if n_trials < N_MIN:
        return EvidenceQuality.MEASURED_LOW
    return EvidenceQuality.MEASURED_HIGH


# ---------------------------------------------------------------------------
# Assembler input + row
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillProfileInput:
    """Already-sourced per-skill inputs for one profile row (no I/O here)."""

    skill: str
    verdict: KeepCutVerdict | None
    cut_sub_reason: CutSubReason | None
    has_screen: bool
    n_trials: int
    is_disable_model_invocation: bool
    desc_token_cost: int | None  # standing tax; 0 if never loaded, None if not sourced
    fired_token_cost: int | None  # per-epoch fired tax from the cost ledger; None if no data
    fired_usd: float | None
    estimand: str | None = None
    """The verdict's estimand scope label (#51) — ``VerdictResult.estimand_label``
    at the source: an Estimand enum value, or the pre-registry n/a marker for
    historical screens. None iff there is no verdict to scope (never screened)."""

    effect: EffectEstimate | None = None
    """Matched Gate-2 effect (#85). None on the Stage-0 screen path (no paired
    effect). When set, ``build_skill_profile`` carries it onto the row."""


@dataclass(frozen=True)
class SkillProfileRow:
    """One skill's profile: the harness's signals as SEPARATE axes.

    ANTI-FUSION CONTRACT: there is NO field here that is a cross-axis
    composite/score/rank. Each field is one axis or one axis's raw input. Adding a
    fused field is exactly the pathology this feature exists to prevent
    (test_aggregation_profile_anti_fusion pins the field set).
    """

    skill: str
    verdict: str | None  # KeepCutVerdict value, or None (never screened)
    cut_sub_reason: str | None
    estimand: str | None  # verdict scope qualifier (#51); None iff verdict is None
    disposition: str  # RankingDisposition value
    evidence_quality: str  # EvidenceQuality value
    desc_token_cost: int | None  # standing tax; 0 if never loaded, None if not sourced
    fired_token_cost: int | None
    fired_usd: float | None
    effect: EffectEstimate | None  # None on Stage-0 screen path; set on matched path
    effect_per_cost: float | None  # None unless a measured effect is present


def effect_per_cost(effect: EffectEstimate | None, desc_token_cost: int | None) -> float | None:
    """Effect-per-standing-cost display aid — defined ONLY where its inputs exist.

    Returns ``effect.mean / desc_token_cost`` when a measured effect is present and
    the standing cost is a positive sourced value; otherwise ``None``. This is a
    display aid shown BESIDE its inputs, never a cross-axis total order: it does not
    combine evidence-quality or disposition, and it is undefined the moment either
    input is missing. The Stage-0 screen path leaves effect None so every screen
    caller gets ``None``; the matched Gate-2 path supplies a real estimate.
    """
    if effect is None or desc_token_cost is None or desc_token_cost <= 0:
        return None
    return effect.mean / desc_token_cost


def build_skill_profile(inputs: list[SkillProfileInput]) -> list[SkillProfileRow]:
    """Assemble profile rows from already-sourced inputs (pure — no I/O).

    Rows are ordered by skill name for stable output. ``effect`` is taken from the
    input when the matched Gate-2 path supplied one; the Stage-0 screen path leaves
    it None, so ``effect_per_cost`` stays None there too. An effect-per-cost display
    aid is shown only beside a real, measured effect, never invented from absence.
    """
    rows: list[SkillProfileRow] = []
    for inp in sorted(inputs, key=lambda i: i.skill):
        disposition = disposition_from_verdict(inp.verdict)
        evidence_quality = evidence_quality_from_screen(
            has_screen=inp.has_screen,
            n_trials=inp.n_trials,
            is_disable_model_invocation=inp.is_disable_model_invocation,
        )
        effect = inp.effect
        rows.append(
            SkillProfileRow(
                skill=inp.skill,
                verdict=inp.verdict.value if inp.verdict is not None else None,
                cut_sub_reason=inp.cut_sub_reason.value if inp.cut_sub_reason is not None else None,
                estimand=inp.estimand,
                disposition=disposition.value,
                evidence_quality=evidence_quality.value,
                desc_token_cost=inp.desc_token_cost,
                fired_token_cost=inp.fired_token_cost,
                fired_usd=inp.fired_usd,
                effect=effect,
                effect_per_cost=effect_per_cost(effect, inp.desc_token_cost),
            )
        )
    return rows
