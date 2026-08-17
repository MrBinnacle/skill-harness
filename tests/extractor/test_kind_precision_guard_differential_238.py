"""Differential coverage measurement for the #218 kind-precision guard."""

from __future__ import annotations

from skill_harness.extractor.vacuity_policy import measure_kind_precision_guard_delta


def test_new_stack_replays_every_pre_change_refusal_without_loss() -> None:
    report = measure_kind_precision_guard_delta()

    assert report.old_refusal_count > 0
    assert report.replayed_refusal_count == report.old_refusal_count
    assert report.lost_refusals == ()
