"""Differential coverage measurement for the #218 kind-precision guard.

The measurement replays one corpus through two predicates: the guard as it stood
before the #234 build, and the claim layer plus document-level backstop as they
stand now. These tests pin the outcome of that replay; they do not assert
"nothing lost" ahead of it, which is the point of measuring instead of claiming.
"""

from __future__ import annotations

from skill_harness.extractor.vacuity_policy import (
    KindPrecisionGuardDelta,
    format_kind_precision_guard_delta,
    measure_kind_precision_guard_delta,
)

_GEN_1 = "vacuity-flag-calibration-2026-08-08"
_GEN_2 = "vacuity-flag-adjudication-2026-08-09"


def test_current_stack_replays_every_pre_change_refusal_without_loss() -> None:
    """Every refusal the pre-change guard produced, minus one named retraction.

    The baseline is executed, not remembered: ``old_refusal_count`` counts the
    rows the pinned pre-change predicate refuses, so a row that guard never
    refused cannot be counted as replayed.
    """
    report = measure_kind_precision_guard_delta()

    assert report.old_refusal_count == 13
    assert report.lost_refusals == ()
    # The one deliberate narrowing: the pre-change substring comparison refused a
    # census percentage whose digit run spans the aggregate. #237 retracted that
    # false refusal, and it is named here so a future loss cannot hide inside the
    # same bucket.
    assert report.retracted_false_refusals == (f"census-digit-run:{_GEN_1}",)
    assert report.replayed_refusal_count == 12
    assert (
        report.replayed_refusal_count
        + len(report.lost_refusals)
        + len(report.retracted_false_refusals)
        == report.old_refusal_count
    )


def test_delta_report_measures_gains_and_named_residuals() -> None:
    report = measure_kind_precision_guard_delta()

    # Per-generation coverage: each generation's aggregate is now refused with the
    # other generation's receipt held, and with no receipt at all. Four rows per
    # generation, none of which the pre-change guard refused.
    assert report.per_generation_gained_refusal_counts == ((_GEN_1, 4), (_GEN_2, 4))
    assert report.gained_refusal_count == sum(
        count for _, count in report.per_generation_gained_refusal_counts
    )
    # Franken tuples: one generation's headline on the other's splits, both
    # directions, refused at construction.
    assert report.claim_layer_franken_tuple_refusal_count == 2
    # Format variants at the serializer: the output set is one canonical string
    # per registered receipt, and none of them is bare or percent-spelled.
    assert report.serializer_enumerated_output_count == 2
    assert report.serializer_bare_or_percent_output_count == 0
    # The two named residuals, measured separately: the backstop's co-occurrence
    # is document-level, and the tuple it lets through is refused at the claim
    # layer, so the hole is confined to prose that bypasses the claim object.
    assert report.backstop_document_scope_residual_count == 2
    assert report.prose_bypassing_claim_object_residual_count == 2
    # The percent spelling, refused by neither revision. The backstop reads
    # decimals (#234 fences a prose claim detector out of it) and hand-written
    # percent copy stays with the #215 static scanner.
    assert report.refused_by_neither_guard == (
        f"percent-spelling:{_GEN_1}",
        f"percent-spelling:{_GEN_2}",
    )


def test_coverage_statement_reads_the_report_it_is_given() -> None:
    """The statement is derived, so a formatter ignoring the measurement fails here."""
    fabricated = KindPrecisionGuardDelta(
        old_refusal_count=5,
        replayed_refusal_count=3,
        lost_refusals=("bare:some-receipt",),
        retracted_false_refusals=("census-digit-run:some-receipt",),
        gained_refusal_count=1,
        per_generation_gained_refusal_counts=(("some-receipt", 1),),
        refused_by_neither_guard=(),
        claim_layer_franken_tuple_refusal_count=7,
        serializer_enumerated_output_count=1,
        serializer_bare_or_percent_output_count=1,
        backstop_document_scope_residual_count=9,
        prose_bypassing_claim_object_residual_count=4,
    )

    statement = format_kind_precision_guard_delta(fabricated)

    assert "refuses 3 of the 5 corpus rows" in statement
    assert "Lost refusals: 1 (bare:some-receipt)" in statement
    assert "Retracted false refusals: 1 (census-digit-run:some-receipt)" in statement
    assert "Gains: 1 refusals" in statement
    assert "per generation some-receipt=1" in statement
    assert "franken tuple refusals 7" in statement
    assert "outputs enumerated 1, of which bare or percent-spelled 1" in statement
    assert "document-level scope 9" in statement
    assert "bypassing the claim object 4" in statement
    assert "Refused by neither revision: 0." in statement


def test_measured_coverage_statement_is_the_text_posted_to_218() -> None:
    """The statement of record. Its figures are the measurement's, not the author's."""
    statement = format_kind_precision_guard_delta(measure_kind_precision_guard_delta())

    assert statement == (
        "Measured differential coverage, pre-change guard 5f82a57 against the claim layer plus "
        "document-level backstop. Replay: the current stack refuses 12 of the 13 corpus rows "
        "the pre-change guard refused. Lost refusals: 0. Retracted false refusals: 1 "
        f"(census-digit-run:{_GEN_1}). Gains: 8 refusals the pre-change guard did not produce, "
        f"per generation {_GEN_1}=4, {_GEN_2}=4; claim-layer franken tuple refusals 2; "
        "canonical serializer outputs enumerated 2, of which bare or percent-spelled 0. Named "
        "residuals: backstop document-level scope 2; prose bypassing the claim object 2. "
        f"Refused by neither revision: 2 (percent-spelling:{_GEN_1}, percent-spelling:{_GEN_2})."
    )
