"""Differential coverage measurement for the #218 kind-precision guard."""

from __future__ import annotations

from skill_harness.extractor.vacuity_policy import (
    format_kind_precision_guard_delta,
    measure_kind_precision_guard_delta,
)


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


def test_coverage_statement_is_derived_from_the_measurement() -> None:
    statement = format_kind_precision_guard_delta(measure_kind_precision_guard_delta())

    assert statement == (
        "Measured differential coverage: the new stack replayed 8/8 pre-change refusals; "
        "lost refusals: 0. Per-generation refusals: "
        "vacuity-flag-calibration-2026-08-08=4, "
        "vacuity-flag-adjudication-2026-08-09=4. Gains measured: claim-layer franken "
        "tuple refusals=2; serializer format-variant refusals=4. Named residuals measured: "
        "backstop document-level scope=2; prose bypassing the claim object=2."
    )
