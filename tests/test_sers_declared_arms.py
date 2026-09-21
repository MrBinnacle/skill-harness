"""SERS receipts carry a run's declared arm set (#554 AC3).

The receipt vocabulary was built for the two-arm paired instrument and stopped
there: ``subject_identity.arms`` was a two-value enum, ``null`` and ``full``,
and the mint helper refused anything outside that pair. A declared-arm
(composition) run declares its own named arms, so the schema accepts the
declared arm set — a single name or an array of unique lowercase-slug names —
while the two-value vocabulary keeps validating.

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from skill_harness.cli.main import _resolve_harness_version
from skill_harness.sers import build_subject_identity
from skill_harness.subject.ingest import ORACLE_METRIC_VERSION, _oracle_implementation_hash

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_PATH = _REPO_ROOT / "docs" / "sers" / "sers.schema.json"
_SKILL_MD = (
    _REPO_ROOT / "tests" / "fixtures" / "sers" / "declared-synthetic-positive-control" / "SKILL.md"
)

_DECLARED_ARMS = [
    "parent_present__specialist_present",
    "parent_present__specialist_absent",
    "parent_absent__specialist_present",
    "parent_absent__specialist_absent",
]


@pytest.fixture(scope="module")
def sers_validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _base_receipt() -> dict[str, Any]:
    """A minimal valid 1.1.0 receipt body; the caller sets subject_identity."""
    return {
        "sers_version": "1.1.0",
        "skill_name": "composition-study",
        "verdict": "CANT_TELL_YET",
        "cut_sub_reason": None,
        "unmeasured_sub_reason": "no_data",
        "value_class": None,
        "evidence_admissibility": {"status": "not_applicable"},
        "cost": {
            "standing_tokens": {"refusal": "not_applicable"},
            "fired_tokens": {"refusal": "not_applicable"},
            "aux_tokens": {"refusal": "not_applicable"},
        },
        "instrument_identity": {
            "extractor_model": "test-model",
            "prompt_fingerprint": "declared-arms-run",
            "schema_fingerprint": "declared-arms-run",
        },
        "source": {"prose_path": "README.md"},
        "summary": "Fixture receipt: the declared-arm vocabulary validates.",
    }


def test_mint_accepts_a_declared_arm_set(
    sers_validator: Draft202012Validator,
) -> None:
    """A composition run's four named arms mint and validate (#554 AC3)."""
    block = build_subject_identity(skill_md=_SKILL_MD, arms=_DECLARED_ARMS)
    assert block["arms"] == _DECLARED_ARMS
    assert block["harness_version"] == _resolve_harness_version()
    assert block["metric_version"] == ORACLE_METRIC_VERSION
    assert block["implementation_hash"] == _oracle_implementation_hash()

    receipt = _base_receipt()
    receipt["subject_identity"] = block
    errors = sorted(sers_validator.iter_errors(receipt), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"  - {e.message} (at {list(e.path)})" for e in errors)


def test_mint_accepts_a_single_declared_arm(
    sers_validator: Draft202012Validator,
) -> None:
    """One declared arm normalizes to the string shape and validates."""
    block = build_subject_identity(skill_md=_SKILL_MD, arms=["placebo_only"])
    assert block["arms"] == "placebo_only"
    receipt = _base_receipt()
    receipt["subject_identity"] = block
    sers_validator.validate(receipt)


def test_existing_two_arm_receipt_still_validates(
    sers_validator: Draft202012Validator,
) -> None:
    """The two-value vocabulary keeps validating (existing receipts, #554 AC3)."""
    block = build_subject_identity(skill_md=_SKILL_MD, arms=["null", "full"])
    assert block["arms"] == ["null", "full"]
    receipt = _base_receipt()
    receipt["subject_identity"] = block
    sers_validator.validate(receipt)

    single = build_subject_identity(skill_md=_SKILL_MD, arms="null")
    assert single["arms"] == "null"


def test_mint_refuses_invalid_declared_arm_names() -> None:
    """The mint helper is the vocabulary floor, not a free-text field."""
    for bad in (["Full"], [""], ["a b"], ["null", "null"], [123]):
        with pytest.raises(ValueError):
            build_subject_identity(skill_md=_SKILL_MD, arms=bad)  # type: ignore[arg-type]


def test_schema_refuses_an_ill_formed_arm_name(
    sers_validator: Draft202012Validator,
) -> None:
    receipt = _base_receipt()
    receipt["subject_identity"] = build_subject_identity(skill_md=_SKILL_MD, arms=["null", "full"])
    receipt["subject_identity"]["arms"] = ["null", "Full"]
    with pytest.raises(ValidationError):
        sers_validator.validate(receipt)


def test_schema_refuses_duplicate_arm_names(
    sers_validator: Draft202012Validator,
) -> None:
    receipt = _base_receipt()
    receipt["subject_identity"] = build_subject_identity(skill_md=_SKILL_MD, arms=["null", "full"])
    receipt["subject_identity"]["arms"] = ["null", "null"]
    with pytest.raises(ValidationError):
        sers_validator.validate(receipt)


def test_poison_fixture_for_ill_formed_arm_names_fails(
    sers_validator: Draft202012Validator,
) -> None:
    """The poison fixture pins the schema's declared-arm name floor."""
    path = _REPO_ROOT / "tests" / "fixtures" / "sers" / "poison_arms_bad_name.json"
    assert path.is_file()
    instance = json.loads(path.read_text(encoding="utf-8"))
    assert instance["subject_identity"]["arms"] == ["null", "Full"]
    with pytest.raises(ValidationError):
        sers_validator.validate(instance)
