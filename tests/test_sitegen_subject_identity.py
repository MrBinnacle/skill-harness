"""AC1-AC3: sitegen renders subject identity on the receipt page (#490).

The subject identity section appears on skill.html, populated from
subject_identity. Three cases:

- AC1: 1.4.0 receipt with subject_identity including subject_model renders the
  identity block.
- AC2: 1.1.0-1.3.0 receipt with subject_identity but no subject_model renders
  the existing fields and shows subject_model absent.
- AC3: 1.0.0 receipt with no subject_identity renders a compact pointer to the
  prose source.

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skill_harness.sitegen.render import _subject_identity_section, render_skill_page

_SCHEMA: dict[str, Any] = json.loads(Path("docs/sers/sers.schema.json").read_text(encoding="utf-8"))

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


def _v14_receipt(**overrides: Any) -> dict[str, Any]:
    """A 1.4.0 receipt with subject_identity including subject_model."""
    receipt = dict(_MINIMAL_RECEIPT)
    receipt["sers_version"] = "1.4.0"
    subject_identity = {
        "skill_id": "aa" * 32,
        "harness_version": "0.3.0",
        "metric_version": "0.4.1",
        "implementation_hash": "bb" * 32,
        "subject_model": "anthropic/claude-sonnet-5",
        "arms": ["null", "full"],
    }
    subject_identity.update(overrides)
    receipt["subject_identity"] = subject_identity
    return receipt


def _v11_receipt(**overrides: Any) -> dict[str, Any]:
    """A 1.1.0 receipt with subject_identity but no subject_model."""
    receipt = dict(_MINIMAL_RECEIPT)
    receipt["sers_version"] = "1.1.0"
    subject_identity = {
        "skill_id": "cc" * 32,
        "harness_version": "0.3.0",
        "metric_version": "0.3.0",
        "implementation_hash": "dd" * 32,
        "arms": ["null", "full"],
    }
    subject_identity.update(overrides)
    receipt["subject_identity"] = subject_identity
    return receipt


def _evidence() -> Any:
    from skill_harness.extractor.clause_evidence import ClauseEvidenceOutcome

    return ClauseEvidenceOutcome(
        kind="no_extraction",
        refusal_detail="no extraction file found",
        measured=None,
        unparseable_line_count=0,
    )


# ---------------------------------------------------------------------------
# _subject_identity_section helper
# ---------------------------------------------------------------------------


def test_subject_identity_section_v14_renders_subject_model() -> None:
    """AC1: 1.4.0 receipt renders subject_model in the subject identity section."""
    receipt = _v14_receipt()
    html = _subject_identity_section(receipt)
    assert "anthropic/claude-sonnet-5" in html
    assert "subject_model" in html
    assert "Subject identity" in html


def test_subject_identity_section_v14_renders_all_fields() -> None:
    """AC1: 1.4.0 receipt renders all identity fields."""
    receipt = _v14_receipt()
    html = _subject_identity_section(receipt)
    assert "skill_id" in html
    assert "harness_version" in html
    assert "metric_version" in html
    assert "implementation_hash" in html
    assert "arms" in html


def test_subject_identity_section_v11_shows_subject_model_absent() -> None:
    """AC2: 1.1.0 receipt shows subject_model absent, not a claim."""
    receipt = _v11_receipt()
    html = _subject_identity_section(receipt)
    assert "subject_model" in html
    assert "absent from this receipt" in html
    # The other fields should render with values
    assert "cc" * 32 in html
    assert "0.3.0" in html


def test_subject_identity_section_v10_renders_pointer() -> None:
    """AC3: 1.0.0 receipt renders a compact pointer, not silence."""
    receipt = _MINIMAL_RECEIPT
    html = _subject_identity_section(receipt)
    assert "subject not recorded" in html
    assert "README.md" in html


# ---------------------------------------------------------------------------
# render_skill_page integration
# ---------------------------------------------------------------------------


def test_full_render_v14_shows_subject_identity_section() -> None:
    """AC1: Full page render includes Subject identity heading for 1.4.0."""
    page = render_skill_page(
        skill_name="test-skill",
        receipt=_v14_receipt(),
        evidence=_evidence(),
        schema=_SCHEMA,
        marker=_MARKER,
    )
    assert "Subject identity" in page
    assert "anthropic/claude-sonnet-5" in page


def test_full_render_v11_shows_subject_identity_section() -> None:
    """AC2: Full page render includes Subject identity heading for 1.1.0."""
    page = render_skill_page(
        skill_name="test-skill",
        receipt=_v11_receipt(),
        evidence=_evidence(),
        schema=_SCHEMA,
        marker=_MARKER,
    )
    assert "Subject identity" in page
    assert "absent from this receipt" in page
    assert "subject_model" in page


def test_full_render_v10_shows_subject_pointer() -> None:
    """AC3: Full page render includes pointer for 1.0.0."""
    page = render_skill_page(
        skill_name="test-skill",
        receipt=_MINIMAL_RECEIPT,
        evidence=_evidence(),
        schema=_SCHEMA,
        marker=_MARKER,
    )
    assert "Subject identity" in page
    assert "subject not recorded" in page
    assert "README.md" in page


def test_v14_receipt_does_not_render_pointer() -> None:
    """AC1: 1.4.0 receipt must not show the pointer (would be a defect)."""
    page = render_skill_page(
        skill_name="test-skill",
        receipt=_v14_receipt(),
        evidence=_evidence(),
        schema=_SCHEMA,
        marker=_MARKER,
    )
    assert "subject not recorded" not in page


def test_v11_receipt_does_not_render_pointer() -> None:
    """AC2: 1.1.0 receipt must not show the pointer (it has the block)."""
    page = render_skill_page(
        skill_name="test-skill",
        receipt=_v11_receipt(),
        evidence=_evidence(),
        schema=_SCHEMA,
        marker=_MARKER,
    )
    assert "subject not recorded" not in page
