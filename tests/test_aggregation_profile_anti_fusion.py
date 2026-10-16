"""Anti-fusion invariant for the per-skill evaluation profile (RED first).

The founding pathology this feature exists to prevent: collapsing the harness's
separate signals (disposition, verdict, evidence-quality, cost, and — held —
effect) into a single ranking scalar. GRADE (Guyatt et al., BMJ 2008;336:924-6)
warns that schemes which fail to separate the *quality* of evidence from the
*strength* of a recommendation "create confusion"; the profile keeps the axes as
separate columns so no cross-axis total order can be read off a fused number.

This module is the regression guard: it fails if anyone later adds a
composite/score/rank field or a function that returns a fused cross-axis scalar.
"""

from __future__ import annotations

import dataclasses
import types

import skill_harness.aggregation.profile as profile
from skill_harness.aggregation.profile import (
    EvidenceQuality,
    SkillProfileInput,
    SkillProfileRow,
    build_skill_profile,
)

# The exact separated field set. Adding any fused/composite field breaks this.
# `estimand` (#51) is a scope qualifier on the verdict axis — the claim boundary
# the verdict is confined to — not a new axis and not a fusable scalar.
_EXPECTED_ROW_FIELDS = frozenset(
    {
        "skill",
        "verdict",
        "cut_sub_reason",
        "estimand",
        "disposition",
        "evidence_quality",
        "desc_token_cost",
        "fired_token_cost",
        "fired_usd",
        "effect",
        "effect_per_cost",
    }
)


class TestRowFieldSetIsExactlySeparated:
    def test_field_set_is_exactly_the_separated_axes(self) -> None:
        actual = {f.name for f in dataclasses.fields(SkillProfileRow)}
        assert actual == set(_EXPECTED_ROW_FIELDS), (
            "SkillProfileRow field set drifted from the separated-axes contract. "
            "A new field here is how axis fusion sneaks in — if you added a "
            f"composite/score/rank field, remove it. Got: {sorted(actual)}"
        )

    def test_no_field_name_reads_as_a_fused_scalar(self) -> None:
        for f in dataclasses.fields(SkillProfileRow):
            low = f.name.lower()
            assert not any(
                bad in low for bad in ("composite", "score", "rank", "weighted", "overall")
            ), f"field {f.name!r} names a fused/total-order scalar — the axes must stay separate"


class TestEvidenceQualityIsOrdinalLabel:
    def test_evidence_quality_is_a_strenum(self) -> None:
        from enum import StrEnum

        assert issubclass(EvidenceQuality, StrEnum), (
            "evidence-quality must be an ordinal StrEnum label, not a number "
            "(Velleman & Wilkinson 1993 — no arithmetic on an ordinal ladder)"
        )

    def test_ordinal_order_authority_is_low_to_high(self) -> None:
        # The module exposes the ordinal ordering as a tuple (the ONLY sanctioned
        # way to sort/compare the ladder); it must run low->high and be complete.
        order = profile.EVIDENCE_QUALITY_ORDER
        assert tuple(order) == (
            EvidenceQuality.UNMEASURABLE,
            EvidenceQuality.UNMEASURED,
            EvidenceQuality.MEASURED_LOW,
            EvidenceQuality.MEASURED_HIGH,
        )
        assert set(order) == set(EvidenceQuality), "ordering must cover every ladder value"


class TestNoFusedScalarFunction:
    def test_module_exposes_no_composite_score_function(self) -> None:
        # Only functions DEFINED in profile.py (not imported names, not the enum
        # classes such as RankingDisposition which legitimately carry 'rank').
        own_functions = [
            name
            for name, obj in vars(profile).items()
            if not name.startswith("_")
            and isinstance(obj, types.FunctionType)
            and obj.__module__ == profile.__name__
        ]
        assert own_functions, "expected the profile module to define public functions"
        for name in own_functions:
            low = name.lower()
            assert not any(
                bad in low for bad in ("composite", "score", "rank", "weighted", "fused")
            ), (
                f"function {name!r} reads as a fused cross-axis ranking scalar; "
                "the profile must never fuse the axes into one number"
            )


class TestNoTotalOrderToDisagreeWith:
    """Two skills a naive (effect+quality+cost) sum would order oppositely to the
    separated axes: the profile must expose NO fused ordering to get wrong."""

    def _row(self, skill: str, n_trials: int, desc: int) -> SkillProfileRow:
        from skill_harness.aggregation.verdict import KeepCutVerdict

        (row,) = build_skill_profile(
            [
                SkillProfileInput(
                    skill=skill,
                    verdict=KeepCutVerdict.CUT,
                    cut_sub_reason=None,
                    has_screen=True,
                    n_trials=n_trials,
                    is_disable_model_invocation=False,
                    desc_token_cost=desc,
                    fired_token_cost=None,
                    fired_usd=None,
                )
            ]
        )
        return row

    def test_rows_carry_no_single_total_order_field(self) -> None:
        # Skill A: high evidence-quality, high cost. Skill B: low quality, low cost.
        # A naive sum would rank them; the row has no scalar that could.
        row_a = self._row("aaa-skill", n_trials=40, desc=400)
        row_b = self._row("bbb-skill", n_trials=2, desc=4)
        assert row_a.evidence_quality != row_b.evidence_quality
        # effect (and thus effect-per-cost) is HELD: no measured effect exists, so
        # there is no numeric total order to disagree with the separated axes.
        assert row_a.effect is None and row_b.effect is None
        assert row_a.effect_per_cost is None and row_b.effect_per_cost is None
        field_names = {f.name for f in dataclasses.fields(SkillProfileRow)}
        # No single field is a cross-axis total order.
        assert "composite_score" not in field_names
        assert "rank" not in field_names
