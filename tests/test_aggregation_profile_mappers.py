"""Pure mapper tests for the per-skill evaluation profile (RED first).

Covers the two axis mappers and their boundaries:
  - disposition_from_verdict: all four inputs incl. None (never screened).
  - evidence_quality_from_screen: all four ordinal outputs incl. the
    disable-model-invocation -> UNMEASURABLE and n_trials < N_MIN -> MEASURED_LOW
    boundaries.
"""

from __future__ import annotations

import pytest

from skill_harness.aggregation.profile import (
    EvidenceQuality,
    RankingDisposition,
    disposition_from_verdict,
    evidence_quality_from_screen,
)
from skill_harness.aggregation.status import N_MIN
from skill_harness.aggregation.verdict import KeepCutVerdict


class TestDispositionFromVerdict:
    def test_keep_is_admitted(self) -> None:
        assert disposition_from_verdict(KeepCutVerdict.KEEP) == RankingDisposition.ADMITTED

    def test_cut_is_excluded(self) -> None:
        assert disposition_from_verdict(KeepCutVerdict.CUT) == RankingDisposition.EXCLUDED

    def test_cant_tell_yet_is_not_yet_rankable(self) -> None:
        # Author-flagged deviation from the originating spec: a CAN'T-TELL-YET skill
        # is "a sourced candidate, not a verdict yet" (verdict.py) — it is NOT
        # admitted to ranking as if measured.
        assert (
            disposition_from_verdict(KeepCutVerdict.CANT_TELL_YET)
            == RankingDisposition.NOT_YET_RANKABLE
        )

    def test_none_never_screened_is_not_yet_rankable(self) -> None:
        assert disposition_from_verdict(None) == RankingDisposition.NOT_YET_RANKABLE


class TestEvidenceQualityFromScreen:
    def test_disable_model_invocation_is_unmeasurable(self) -> None:
        # A skill the model never auto-invokes cannot be Null-arm screened.
        # UNMEASURABLE wins even if a screen and trials are present.
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=99, is_disable_model_invocation=True
            )
            == EvidenceQuality.UNMEASURABLE
        )

    def test_no_screen_is_unmeasured(self) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=False, n_trials=0, is_disable_model_invocation=False
            )
            == EvidenceQuality.UNMEASURED
        )

    def test_below_n_min_is_measured_low(self) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=N_MIN - 1, is_disable_model_invocation=False
            )
            == EvidenceQuality.MEASURED_LOW
        )

    def test_at_n_min_is_measured_high(self) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=N_MIN, is_disable_model_invocation=False
            )
            == EvidenceQuality.MEASURED_HIGH
        )

    def test_above_n_min_is_measured_high(self) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=N_MIN + 50, is_disable_model_invocation=False
            )
            == EvidenceQuality.MEASURED_HIGH
        )

    @pytest.mark.parametrize("n_trials", [0, 1, 7])
    def test_has_screen_but_underpowered_is_measured_low(self, n_trials: int) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=n_trials, is_disable_model_invocation=False
            )
            == EvidenceQuality.MEASURED_LOW
        )
