"""SERS conformance harness (#182).

Proves both directions of the Skill Efficacy Reporting Standard:
  - every hand-encoded receipt under docs/sers/receipts/ validates
  - schema enum vocabularies stay EQUAL to the code enums (no silent drift)
  - a poisoned fixture FAILS validation (a guard that cannot fail guards nothing)

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import ValidationError  # type: ignore[import-untyped]

from skill_harness.aggregation.status import UnmeasuredSubReason
from skill_harness.aggregation.verdict import CutSubReason, KeepCutVerdict, ValueClass
from skill_harness.cli.main import _resolve_harness_version
from skill_harness.sers import build_subject_identity
from skill_harness.subject.ingest import ORACLE_METRIC_VERSION, _oracle_implementation_hash

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERS_DIR = _REPO_ROOT / "docs" / "sers"
_SCHEMA_PATH = _SERS_DIR / "sers.schema.json"
_RECEIPTS_DIR = _SERS_DIR / "receipts"
_POISON_DIR = _REPO_ROOT / "tests" / "fixtures" / "sers"
_CONTROL_SKILL_MD = _POISON_DIR / "declared-synthetic-positive-control" / "SKILL.md"
_V11_MINTED = _POISON_DIR / "minted_synthetic_control_v1_1_0.json"


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


def _receipt_paths() -> list[Path]:
    assert _RECEIPTS_DIR.is_dir(), f"missing receipts dir {_RECEIPTS_DIR}"
    paths = sorted(_RECEIPTS_DIR.glob("*.json"))
    assert len(paths) >= 3, f"expected >=3 receipts, found {len(paths)}"
    return paths


# ---------------------------------------------------------------------------
# Conforming instances validate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("receipt_path", _receipt_paths(), ids=lambda p: p.name)
def test_receipt_conforms_to_sers_schema(
    receipt_path: Path, sers_validator: Draft202012Validator
) -> None:
    instance = _load_json(receipt_path)
    errors = sorted(sers_validator.iter_errors(instance), key=lambda e: list(e.path))
    assert not errors, f"{receipt_path.name} failed SERS validation:\n" + "\n".join(
        f"  - {e.message} (at {list(e.path)})" for e in errors
    )


def test_receipts_point_at_prose_sources(sers_validator: Draft202012Validator) -> None:
    """Each hand-encoded receipt cites a prose source that exists in-tree."""
    for path in _receipt_paths():
        instance = _load_json(path)
        sers_validator.validate(instance)
        prose = instance["source"]["prose_path"]
        assert isinstance(prose, str) and prose
        assert (_REPO_ROOT / prose).is_file(), f"{path.name}: missing prose source {prose}"


# ---------------------------------------------------------------------------
# Enum-drift guard: schema enums == code enums
# ---------------------------------------------------------------------------


def _schema_enum(schema: dict[str, Any], *path: str) -> set[str]:
    node: Any = schema
    for key in path:
        assert isinstance(node, dict), f"schema path {path} broke at {key}"
        assert key in node, f"schema missing path element {key!r} under {path}"
        node = node[key]
    assert isinstance(node, list), f"schema path {path} is not an enum list"
    return {str(v) for v in node if v is not None}


def test_schema_verdict_enum_matches_code(sers_schema: dict[str, Any]) -> None:
    schema_vals = _schema_enum(sers_schema, "properties", "verdict", "enum")
    code_vals = {m.value for m in KeepCutVerdict}
    assert schema_vals == code_vals


def test_schema_cut_sub_reason_enum_matches_code(sers_schema: dict[str, Any]) -> None:
    schema_vals = _schema_enum(sers_schema, "properties", "cut_sub_reason", "enum")
    code_vals = {m.value for m in CutSubReason}
    # schema may allow null for non-CUT verdicts; compare non-null members only
    assert schema_vals == code_vals


def test_schema_unmeasured_sub_reason_enum_matches_code(sers_schema: dict[str, Any]) -> None:
    schema_vals = _schema_enum(sers_schema, "properties", "unmeasured_sub_reason", "enum")
    code_vals = {m.value for m in UnmeasuredSubReason}
    assert schema_vals == code_vals


def test_schema_value_class_enum_matches_code(sers_schema: dict[str, Any]) -> None:
    schema_vals = _schema_enum(sers_schema, "properties", "value_class", "enum")
    code_vals = {m.value for m in ValueClass}
    assert schema_vals == code_vals


def test_schema_forbids_additional_properties(sers_schema: dict[str, Any]) -> None:
    assert sers_schema.get("additionalProperties") is False


def test_schema_uses_qualified_evidence_admissibility_term(
    sers_schema: dict[str, Any],
) -> None:
    """Gate term must be the qualified form only — never bare 'admissibility' as a key."""
    props = sers_schema["properties"]
    assert "evidence_admissibility" in props
    assert "admissibility" not in props
    raw = _SCHEMA_PATH.read_text(encoding="utf-8")
    # bare JSON key "admissibility" is banned; qualified form is required
    assert '"evidence_admissibility"' in raw
    assert '"admissibility"' not in raw


# ---------------------------------------------------------------------------
# Poison fixtures must FAIL validation
# ---------------------------------------------------------------------------


def _poison_paths() -> list[Path]:
    assert _POISON_DIR.is_dir(), f"missing poison fixture dir {_POISON_DIR}"
    paths = sorted(_POISON_DIR.glob("poison_*.json"))
    assert paths, f"no poison_*.json fixtures under {_POISON_DIR}"
    return paths


@pytest.mark.parametrize("poison_path", _poison_paths(), ids=lambda p: p.name)
def test_poisoned_fixture_fails_validation(
    poison_path: Path, sers_validator: Draft202012Validator
) -> None:
    instance = _load_json(poison_path)
    with pytest.raises(ValidationError):
        sers_validator.validate(instance)


def test_poison_wrong_verdict_vocabulary_is_red(sers_validator: Draft202012Validator) -> None:
    path = _POISON_DIR / "poison_wrong_verdict.json"
    assert path.is_file()
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(_load_json(path))
    assert "verdict" in str(excinfo.value).lower() or "KEEP" in str(excinfo.value)


def test_poison_missing_instrument_identity_is_red(
    sers_validator: Draft202012Validator,
) -> None:
    path = _POISON_DIR / "poison_missing_instrument_identity.json"
    assert path.is_file()
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(_load_json(path))
    assert "instrument_identity" in str(excinfo.value)


def test_poison_bare_gate_term_is_red(sers_validator: Draft202012Validator) -> None:
    """Bare 'admissibility' (term collision) must not validate as the gate field."""
    path = _POISON_DIR / "poison_bare_gate_term.json"
    assert path.is_file()
    instance = _load_json(path)
    assert "admissibility" in instance
    assert "evidence_admissibility" not in instance
    with pytest.raises(ValidationError):
        sers_validator.validate(instance)


def test_poison_missing_skill_id_is_red(sers_validator: Draft202012Validator) -> None:
    """1.1.0 subject_identity without skill_id must fail on that field (#298)."""
    path = _POISON_DIR / "poison_missing_skill_id.json"
    assert path.is_file()
    instance = _load_json(path)
    assert "skill_id" not in instance.get("subject_identity", {})
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "skill_id" in str(excinfo.value)


# ---------------------------------------------------------------------------
# subject_identity mint (#298): harness-populated, not hand-typed
# ---------------------------------------------------------------------------


def test_build_subject_identity_uses_live_harness_sources() -> None:
    """Every field comes from the harness path named in the ticket, not a literal."""
    assert _CONTROL_SKILL_MD.is_file()
    block = build_subject_identity(skill_md=_CONTROL_SKILL_MD, arms=["null", "full"])
    assert block["harness_version"] == _resolve_harness_version()
    assert block["metric_version"] == ORACLE_METRIC_VERSION
    assert block["implementation_hash"] == _oracle_implementation_hash()
    assert block["arms"] == ["null", "full"]
    assert len(block["skill_id"]) == 64
    assert set(block["skill_id"]) <= set("0123456789abcdef")


def test_v11_receipt_subject_identity_matches_harness_mint(
    sers_validator: Draft202012Validator,
) -> None:
    """1.1.0 mint of the real synthetic-control run: harness block, not hand-typed."""
    assert _V11_MINTED.is_file()
    instance = _load_json(_V11_MINTED)
    sers_validator.validate(instance)
    assert instance["sers_version"] == "1.1.0"
    expected = build_subject_identity(skill_md=_CONTROL_SKILL_MD, arms=["null", "full"])
    assert instance["subject_identity"] == expected
    # Measurements stay the documented real run — not an invented KEEP.
    assert instance["declared_synthetic_control"] is True
    assert instance["measurements"]["full_pass_rate"]["passes"] == 8
    assert instance["measurements"]["null_pass_rate"]["passes"] == 0
