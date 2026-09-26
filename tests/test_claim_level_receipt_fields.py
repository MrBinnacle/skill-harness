"""#647 receipt fields for claim level ladder.

Proves the five new receipt fields: ``designer``, ``designer_independent``,
``family_replication``, ``model_replication``, and ``claim_level``.

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_PATH = _REPO_ROOT / "docs" / "sers" / "sers.schema.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sers_schema() -> dict[str, Any]:
    assert _SCHEMA_PATH.is_file(), f"missing SERS schema at {_SCHEMA_PATH}"
    loaded = _load_json(_SCHEMA_PATH)
    assert isinstance(loaded, dict)
    schema: dict[str, Any] = loaded
    Draft202012Validator.check_schema(schema)
    return schema


@pytest.fixture(scope="module")
def sers_validator(sers_schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(sers_schema)


def _minimal_receipt(**overrides: Any) -> dict[str, Any]:
    """A minimal v1.6.0 receipt with the new fields absent (optional)."""
    base = {
        "sers_version": "1.6.0",
        "skill_name": "test-skill",
        "verdict": "KEEP",
        "cut_sub_reason": None,
        "unmeasured_sub_reason": None,
        "value_class": "trap-discipline",
        "evidence_admissibility": {"status": "not_applicable"},
        "cost": {
            "standing_tokens": {"tokens": 100},
            "fired_tokens": {"tokens": 50},
            "aux_tokens": {"tokens": 10},
        },
        "instrument_identity": {
            "extractor_model": "test-model",
            "prompt_fingerprint": "fp-abc123",
            "schema_fingerprint": "sf-def456",
        },
        "source": {"prose_path": "docs/observations/OBS-0001-fts5-notes-search-v1.md"},
        "summary": "Test receipt for claim level fields.",
        "subject_identity": {
            "skill_id": "a" * 64,
            "harness_version": "0.3.0",
            "metric_version": "0.3.0",
            "implementation_hash": "b" * 64,
            "subject_model": "test-model",
            "arms": ["null", "full"],
        },
        "delivery": {
            "channel": "description_only",
            "exposure": {"value": 1.0},
            "pi_c": {"refusal": "not_applicable"},
        },
        "verdict_scope": {
            "model_id": "test-model",
            "task_family": "test-family",
            "delivery_mechanism": "model-pull",
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# AC1 — claim_level is a valid enum in the schema
# ---------------------------------------------------------------------------


class TestClaimLevelSchema:
    def test_claim_level_property_exists(self, sers_schema: dict[str, Any]) -> None:
        """claim_level is defined in the schema properties."""
        props = sers_schema.get("properties", {})
        assert "claim_level" in props

    def test_claim_level_enum_values(self, sers_schema: dict[str, Any]) -> None:
        """claim_level has exactly three string values: KEEP, REPLICATED, ROBUST."""
        props = sers_schema.get("properties", {})
        claim_level = props.get("claim_level", {})
        enum_vals = {v for v in claim_level.get("enum", []) if v is not None}
        assert enum_vals == {"KEEP", "REPLICATED", "ROBUST"}

    def test_claim_level_nullable(self, sers_schema: dict[str, Any]) -> None:
        """claim_level is nullable — null means not yet classified."""
        props = sers_schema.get("properties", {})
        claim_level = props.get("claim_level", {})
        assert "null" in claim_level.get("type", []) or claim_level.get("type") == [
            "string",
            "null",
        ]


# ---------------------------------------------------------------------------
# AC2 — designer, designer_independent, family_replication, model_replication exist
# ---------------------------------------------------------------------------


class TestReceiptFieldsExist:
    def test_designer_property_exists(self, sers_schema: dict[str, Any]) -> None:
        props = sers_schema.get("properties", {})
        assert "designer" in props
        assert props["designer"].get("type") == "string"

    def test_designer_independent_property_exists(self, sers_schema: dict[str, Any]) -> None:
        props = sers_schema.get("properties", {})
        assert "designer_independent" in props
        assert props["designer_independent"].get("type") == "boolean"

    def test_family_replication_property_exists(self, sers_schema: dict[str, Any]) -> None:
        props = sers_schema.get("properties", {})
        assert "family_replication" in props

    def test_model_replication_property_exists(self, sers_schema: dict[str, Any]) -> None:
        props = sers_schema.get("properties", {})
        assert "model_replication" in props


# ---------------------------------------------------------------------------
# AC3 — a receipt with the new fields validates
# ---------------------------------------------------------------------------


class TestReceiptWithClaimLevel:
    def test_receipt_with_claim_level_keep_validates(
        self, sers_validator: Draft202012Validator
    ) -> None:
        instance = _minimal_receipt(claim_level="KEEP")
        errors = sorted(sers_validator.iter_errors(instance), key=lambda e: list(e.path))
        assert not errors, "KEEP claim_level failed validation:\n" + "\n".join(
            f"  - {e.message} (at {list(e.path)})" for e in errors
        )

    def test_receipt_with_claim_level_replicated_validates(
        self, sers_validator: Draft202012Validator
    ) -> None:
        instance = _minimal_receipt(claim_level="REPLICATED")
        errors = sorted(sers_validator.iter_errors(instance), key=lambda e: list(e.path))
        assert not errors, "REPLICATED claim_level failed validation:\n" + "\n".join(
            f"  - {e.message} (at {list(e.path)})" for e in errors
        )

    def test_receipt_with_claim_level_robust_validates(
        self, sers_validator: Draft202012Validator
    ) -> None:
        instance = _minimal_receipt(claim_level="ROBUST")
        errors = sorted(sers_validator.iter_errors(instance), key=lambda e: list(e.path))
        assert not errors, "ROBUST claim_level failed validation:\n" + "\n".join(
            f"  - {e.message} (at {list(e.path)})" for e in errors
        )

    def test_receipt_without_claim_level_still_validates(
        self, sers_validator: Draft202012Validator
    ) -> None:
        """claim_level is optional — receipts without it must still validate."""
        instance = _minimal_receipt()
        errors = sorted(sers_validator.iter_errors(instance), key=lambda e: list(e.path))
        assert not errors

    def test_claim_level_invalid_value_is_rejected(
        self, sers_validator: Draft202012Validator
    ) -> None:
        instance = _minimal_receipt(claim_level="INVALID")
        errors = list(sers_validator.iter_errors(instance))
        assert errors, "claim_level=INVALID should fail validation"

    def test_receipt_with_designer_and_independent_validates(
        self, sers_validator: Draft202012Validator
    ) -> None:
        instance = _minimal_receipt(
            designer="alice",
            designer_independent=True,
            family_replication=2,
            model_replication=1,
            claim_level="REPLICATED",
        )
        errors = sorted(sers_validator.iter_errors(instance), key=lambda e: list(e.path))
        assert not errors
