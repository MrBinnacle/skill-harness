"""Differential coverage measurement for the #218 kind-precision guard."""

from __future__ import annotations

from skill_harness.extractor.vacuity_policy import measure_kind_precision_guard_delta


def test_new_stack_replays_every_pre_change_refusal_without_loss() -> None:
    report = measure_kind_precision_guard_delta()

    assert report.old_refusal_count > 0
    assert report.replayed_refusal_count == report.old_refusal_count
    assert report.lost_refusals == ()


def test_delta_report_measures_gains_and_named_residuals() -> None:
    report = measure_kind_precision_guard_delta()

    assert report.per_generation_refusal_counts == {
        "vacuity-flag-calibration-2026-08-08": 4,
        "vacuity-flag-adjudication-2026-08-09": 4,
    }
    assert report.claim_layer_franken_tuple_refusal_count == 2
    assert report.serializer_format_variant_refusal_count == 4
    assert report.backstop_document_scope_residual_count == 2
    assert report.prose_bypassing_claim_object_residual_count == 2
