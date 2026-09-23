"""Card-facing SERS currentness and scope rendering (#643)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skill_harness.extractor.clause_evidence import ClauseEvidenceOutcome
from skill_harness.sitegen.render import CARRIED_FORWARD_DISCLAIMER, render_skill_page

_SCHEMA: dict[str, Any] = json.loads(Path("docs/sers/sers.schema.json").read_text(encoding="utf-8"))
_MARKER = "test-build-marker"


def _receipt(*, verdict: str = "KEEP", currentness: dict[str, Any] | None = None) -> dict[str, Any]:
    """A valid 1.6.0 receipt carrying the scope rendered by the card."""
    receipt: dict[str, Any] = {
        "sers_version": "1.6.0",
        "skill_name": "verdict-validity-card",
        "verdict": verdict,
        "cut_sub_reason": None,
        "unmeasured_sub_reason": None,
        "value_class": "transformative-lift",
        "evidence_admissibility": {"status": "not_applicable"},
        "cost": {
            "standing_tokens": {"refusal": "not_applicable"},
            "fired_tokens": {"refusal": "not_applicable"},
            "aux_tokens": {"refusal": "not_applicable"},
        },
        "instrument_identity": {
            "extractor_model": {"refusal": "not_applicable"},
            "prompt_fingerprint": "a",
            "schema_fingerprint": "b",
        },
        "source": {"prose_path": "README.md"},
        "summary": "Test receipt.",
        "subject_identity": {
            "skill_id": "aa" * 32,
            "harness_version": "0.3.0",
            "metric_version": "0.4.1",
            "implementation_hash": "bb" * 32,
            "arms": ["null", "full"],
            "subject_model": "model-2026-09",
        },
        "delivery": {
            "channel": "not_instrumented",
            "exposure": {"refusal": "not_instrumented"},
            "pi_c": {"refusal": "not_instrumented"},
        },
        "verdict_scope": {
            "model_id": "model-2026-09",
            "task_family": "review-task",
            "estimand": "treatment-policy",
            "delivery_mechanism": "hook-nudged",
            "tested_at": "2026-09-22T00:00:00Z",
        },
    }
    if currentness is not None:
        receipt["currentness"] = currentness
    return receipt


def _evidence() -> ClauseEvidenceOutcome:
    return ClauseEvidenceOutcome(
        kind="no_extraction",
        refusal_detail="no extraction file found",
        measured=None,
        unparseable_line_count=0,
    )


def _render(receipt: dict[str, Any]) -> str:
    return render_skill_page(
        skill_name="verdict-validity-card",
        receipt=receipt,
        evidence=_evidence(),
        schema=_SCHEMA,
        marker=_MARKER,
    )


def test_keep_card_renders_scope_line_and_carried_forward_disclaimer() -> None:
    """The card marks surveillance as distinct from a new full validation."""
    page = _render(
        _receipt(
            currentness={
                "state": "CARRIED_FORWARD",
                "basis": "SENTINEL_PASS",
                "last_checked_at": "2026-09-23T00:00:00Z",
                "next_check_due": "2026-09-30T00:00:00Z",
                "max_age_days": 90,
            }
        )
    )

    assert '<h2 id="verdict-scope">Verdict scope</h2>' in page
    assert "<dt>task_family</dt><dd><code>review-task</code></dd>" in page
    assert (
        "Shown here: effect on review-task, model-2026-09, hook-nudged, "
        "measured 2026-09-22T00:00:00Z." in page
    )
    assert "Not shown: other task families, models, environments, or real-world incidence." in page
    assert '<h2 id="currentness">Currentness</h2>' in page
    assert "<dt>state</dt><dd><code>CARRIED_FORWARD</code></dd>" in page
    assert "<dt>basis</dt><dd><code>SENTINEL_PASS</code></dd>" in page
    assert CARRIED_FORWARD_DISCLAIMER in page


def test_currentness_is_stale_when_the_receipt_carries_no_currentness() -> None:
    """No currentness block must never appear as an implicit validation."""
    page = _render(_receipt())

    assert "<dt>state</dt><dd><code>STALE</code></dd>" in page
    assert "<dt>basis</dt><dd><code>NONE</code></dd>" in page
    assert CARRIED_FORWARD_DISCLAIMER not in page


def test_non_keep_card_does_not_make_the_keep_only_scope_claim() -> None:
    """The scoped card sentence is licensed by KEEP, not by scope metadata alone."""
    page = _render(_receipt(verdict="CANT_TELL_YET"))

    assert '<h2 id="verdict-scope">Verdict scope</h2>' in page
    assert "Shown here: effect on" not in page
