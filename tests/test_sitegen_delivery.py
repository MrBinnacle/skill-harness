"""AC5: sitegen renders the delivery block on the receipt page (#388).

The delivery section appears between measurements and evidence admissibility.
For not_instrumented receipts the section still renders (it is part of the
1.2.0 contract); for receipts without a delivery block (1.0.0 / 1.1.0) the
section is absent.

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skill_harness.sitegen.render import _delivery_section, render_skill_page

_SCHEMA: dict[str, Any] = json.loads(
    Path("docs/sers/sers.schema.json").read_text(encoding="utf-8")
)

_MARKER = "test-build-marker"

_MINIMAL_RECEIPT: dict[str, Any] = {
    "sers_version": "1.0.0",
    "skill_name": "test-skill",
    "verdict": "KEEP",
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
        "extractor_model": "test",
        "prompt_fingerprint": "a",
        "schema_fingerprint": "b",
    },
    "source": {"prose_path": "README.md"},
    "summary": "Test receipt.",
}


def _delivery_receipt(channel: str, pi_c: dict | None = None, exposure: dict | None = None) -> dict:
    receipt = dict(_MINIMAL_RECEIPT)
    receipt["sers_version"] = "1.2.0"
    delivery: dict = {"channel": channel}
    if pi_c is not None:
        delivery["pi_c"] = pi_c
    if exposure is not None:
        delivery["exposure"] = exposure
    receipt["delivery"] = delivery
    return receipt


# ---------------------------------------------------------------------------
# _delivery_section helper
# ---------------------------------------------------------------------------


def test_delivery_section_description_only() -> None:
    """description_only channel renders the standing-description prose."""
    pi_c = {
        "hat": 0.0,
        "invocations": 0,
        "trials": 8,
        "ci_low": 0.0,
        "ci_high": 0.369,
        "confidence": 0.95,
        "detector": "v1",
    }
    receipt = _delivery_receipt(
        "description_only",
        pi_c=pi_c,
        exposure={"value": 1.0, "passes": 8, "epochs": 8},
    )
    html = _delivery_section(receipt)
    assert "standing description" in html
    assert "body was never read" in html
    assert "description_only" not in html  # prose, not raw enum


def test_delivery_section_body_and_description() -> None:
    """body_and_description channel renders the body-was-read prose."""
    pi_c = {
        "hat": 0.625,
        "invocations": 5,
        "trials": 8,
        "ci_low": 0.245,
        "ci_high": 0.915,
        "confidence": 0.95,
        "detector": "v1",
    }
    receipt = _delivery_receipt("body_and_description", pi_c=pi_c)
    html = _delivery_section(receipt)
    assert "body was read" in html


def test_delivery_section_not_instrumented() -> None:
    """not_instrumented channel renders the not-instrumented prose."""
    receipt = _delivery_receipt("not_instrumented")
    html = _delivery_section(receipt)
    assert "not instrumented" in html.lower()


def test_delivery_section_absent_when_no_block() -> None:
    """Receipts without a delivery block produce an empty string."""
    html = _delivery_section(_MINIMAL_RECEIPT)
    assert html == ""


def test_delivery_section_pi_c_refusal() -> None:
    """pi_c as a refusal renders the refusal line."""
    receipt = _delivery_receipt(
        "not_instrumented",
        pi_c={"refusal": "not_instrumented", "detail": "no detector"},
    )
    html = _delivery_section(receipt)
    assert "REFUSED" in html
    assert "not_instrumented" in html


def test_delivery_section_exposure_refusal() -> None:
    """exposure as a refusal renders the refusal line."""
    receipt = _delivery_receipt(
        "not_instrumented",
        exposure={"refusal": "not_instrumented", "detail": "no data"},
    )
    html = _delivery_section(receipt)
    assert "REFUSED" in html
    assert "not_instrumented" in html


def test_delivery_section_in_full_render() -> None:
    """The delivery section appears in the full skill page render."""
    pi_c = {
        "hat": 0.0,
        "invocations": 0,
        "trials": 8,
        "ci_low": 0.0,
        "ci_high": 0.369,
        "confidence": 0.95,
        "detector": "v1",
    }
    receipt = _delivery_receipt("description_only", pi_c=pi_c)
    from skill_harness.extractor.clause_evidence import ClauseEvidenceOutcome

    evidence = ClauseEvidenceOutcome(
        kind="no_extraction",
        refusal_detail="no extraction file found",
        measured=None,
        unparseable_line_count=0,
    )
    page = render_skill_page(
        skill_name="test-skill",
        receipt=receipt,
        evidence=evidence,
        schema=_SCHEMA,
        marker=_MARKER,
    )
    assert "Value delivery" in page
    assert "standing description" in page


def test_full_render_no_delivery_block() -> None:
    """1.0.0 receipts have no delivery section in the rendered page."""
    from skill_harness.extractor.clause_evidence import ClauseEvidenceOutcome

    evidence = ClauseEvidenceOutcome(
        kind="no_extraction",
        refusal_detail="no extraction file found",
        measured=None,
        unparseable_line_count=0,
    )
    page = render_skill_page(
        skill_name="test-skill",
        receipt=_MINIMAL_RECEIPT,
        evidence=evidence,
        schema=_SCHEMA,
        marker=_MARKER,
    )
    assert "Value delivery" not in page
