"""SERS conformance harness (#182).

Proves both directions of the Skill Efficacy Reporting Standard:
  - every hand-encoded receipt under docs/sers/receipts/ validates
  - schema enum vocabularies stay EQUAL to the code enums (no silent drift)
  - a poisoned fixture FAILS validation (a guard that cannot fail guards nothing)

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from skill_harness.aggregation.status import UnmeasuredSubReason
from skill_harness.aggregation.verdict import CutSubReason, KeepCutVerdict, ValueClass
from skill_harness.cli.main import _resolve_harness_version
from skill_harness.sers import build_subject_identity
from skill_harness.sers.delivery import (
    CHANNEL_BODY_AND_DESCRIPTION,
    CHANNEL_DESCRIPTION_ONLY,
    CHANNEL_NOT_INSTRUMENTED,
)
from skill_harness.subject.ingest import ORACLE_METRIC_VERSION, _oracle_implementation_hash

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERS_DIR = _REPO_ROOT / "docs" / "sers"
_SCHEMA_PATH = _SERS_DIR / "sers.schema.json"
_RECEIPTS_DIR = _SERS_DIR / "receipts"
_POISON_DIR = _REPO_ROOT / "tests" / "fixtures" / "sers"
_CONTROL_SKILL_MD = _POISON_DIR / "declared-synthetic-positive-control" / "SKILL.md"
_V11_MINTED = _POISON_DIR / "minted_synthetic_control_v1_1_0.json"
_V12_MINTED = _POISON_DIR / "minted_synthetic_control_v1_2_0.json"


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


def test_schema_rate_refusal_enum_matches_code(sers_schema: dict[str, Any]) -> None:
    """The second copy of the sub-reason vocabulary tracks the code enum (#578).

    $defs/rate_or_refusal is referenced by ten measurement fields and its own
    description says the refusal is "drawn from UnmeasuredSubReason (plus
    not_applicable for non-paths)". Nothing asserted that until now, so the copy
    went stale when #503 added two members and only the other copy was updated.
    """
    refusal_branch = sers_schema["$defs"]["rate_or_refusal"]["oneOf"][1]
    schema_vals = {str(v) for v in refusal_branch["properties"]["refusal"]["enum"]}
    code_vals = {m.value for m in UnmeasuredSubReason} | {"not_applicable"}
    assert schema_vals == code_vals


_SUB_REASON_PROSE_SURFACES = (
    "docs/sers/what-sers-is.md",
    "docs/sers/README.md",
    "docs/concepts/why-unmeasured.md",
)
"""Documents that write the UNMEASURED sub-reason vocabulary out in full.

Each one restates a code enum by hand, which is a claim no test read until #575.
`710ef78` added two members and updated one of the five places the vocabulary is
written. The README carried a wrong count for a day, inside the paragraph that
states this project's rule against inventing numbers.

README.md is deliberately absent from this tuple. It no longer enumerates the
vocabulary at all; it names `UnmeasuredSubReason` and links the definitions.
That is the fix for a surface whose job is not to be a reference.
"""


@pytest.mark.parametrize("relative_path", _SUB_REASON_PROSE_SURFACES)
def test_prose_surfaces_carry_every_sub_reason(relative_path: str) -> None:
    """Every document that enumerates the vocabulary enumerates all of it (#575).

    An eleventh member reddens this test once per stale document, and the
    failure names the document and the member, so the fix is not a search.
    """
    text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
    missing = sorted(m.value for m in UnmeasuredSubReason if m.value not in text)

    assert not missing, f"{relative_path} does not name {missing}"


def test_schema_value_class_enum_matches_code(sers_schema: dict[str, Any]) -> None:
    schema_vals = _schema_enum(sers_schema, "properties", "value_class", "enum")
    code_vals = {m.value for m in ValueClass}
    assert schema_vals == code_vals


def test_schema_outcome_type_enum_matches_code(sers_schema: dict[str, Any]) -> None:
    """outcome_type closed vocabulary equals the registered set (#424)."""
    schema_vals = _schema_enum(sers_schema, "properties", "outcome_type", "enum")
    # The registered outcome types: pass_fail (legacy) and invariant (split oracle).
    code_vals = {"pass_fail", "invariant"}
    assert schema_vals == code_vals


def test_schema_delivery_channel_enum_matches_code(sers_schema: dict[str, Any]) -> None:
    """delivery.channel closed vocabulary equals the mint-path constants (#388)."""
    schema_vals = _schema_enum(
        sers_schema, "properties", "delivery", "properties", "channel", "enum"
    )
    code_vals = {
        CHANNEL_DESCRIPTION_ONLY,
        CHANNEL_BODY_AND_DESCRIPTION,
        CHANNEL_NOT_INSTRUMENTED,
    }
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
    """1.1.0 mint of the real synthetic-control run: harness block, not hand-typed.

    ``implementation_hash`` is deliberately EXCLUDED from the live-equality check
    (#373). It is a SHA-256 over ``subject/ingest.py``'s own bytes, so asserting
    that a stored fixture equals a live recomputation makes every edit to the
    oracle module red, whatever the edit does.

    Excluding it is not a concession to convenience. The field never held the
    property this test is named for. The fixture's own ``source.notes`` records
    its measurements as copying the documented run of 2026-07-27, and
    ``subject/ingest.py`` was edited five times between that date and the #300
    mint (5533740, 45087f0, 2d19430, 8da8e20, f347dab). The recorded hash has
    therefore never been the identity of the oracle that produced 8 vs 0, and it
    cannot be made so: the run's inputs were not retained in-tree, so the control
    cannot be re-executed and re-minted from its own evidence.

    The not-hand-typed invariant (#298) is carried by the fields that survive
    below. ``skill_id`` is a digest of the skill file's bytes and cannot be typed
    from a failing assertion; ``implementation_hash`` is the one field in the
    block that can be, by copying it out of this test's own output.

    The live invariant that DOES have content is asserted separately, in
    ``test_fresh_subject_identity_mint_hashes_the_live_oracle_module``.

    ``metric_version`` is excluded from the live-equality check for the same
    reason, found the same way (#391, 2026-09-03). It names the identity that
    minted the receipt, and a receipt minted under 0.4.0 stays a 0.4.0 receipt
    after the module moves to 0.4.1. Asserting it equals the live constant
    makes every version bump red, and the fixture shows what happens next: at
    4001686 its ``metric_version`` was retyped from 0.3.0 to 0.4.0 beside an
    ``implementation_hash`` that still names the 2026-08-17 module, which never
    carried 0.4.0. The field was typed from a failing assertion, which is the
    exact defect #298 named. It is now held to the registered-version shape.
    """
    assert _V11_MINTED.is_file()
    instance = _load_json(_V11_MINTED)
    sers_validator.validate(instance)
    assert instance["sers_version"] == "1.1.0"
    recorded = instance["subject_identity"]
    expected = build_subject_identity(skill_md=_CONTROL_SKILL_MD, arms=["null", "full"])
    for field in ("skill_id", "harness_version", "arms"):
        assert recorded[field] == expected[field], (
            f"SUBJECT_IDENTITY_DRIFT: {field} in the stored 1.1.0 fixture does not match"
            f" a live harness mint. This block must be harness-populated (#298)."
        )
    historical_version = recorded["metric_version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", historical_version), historical_version
    historical_hash = recorded["implementation_hash"]
    assert len(historical_hash) == 64, historical_hash
    assert set(historical_hash) <= set("0123456789abcdef"), historical_hash
    # Measurements stay the documented real run — not an invented KEEP.
    assert instance["declared_synthetic_control"] is True
    assert instance["measurements"]["full_pass_rate"]["passes"] == 8
    assert instance["measurements"]["null_pass_rate"]["passes"] == 0


def test_v12_receipt_delivery_block_conforms(
    sers_validator: Draft202012Validator,
) -> None:
    """1.2.0 mint carries a delivery block; schema requires it (#388)."""
    assert _V12_MINTED.is_file()
    instance = _load_json(_V12_MINTED)
    sers_validator.validate(instance)
    assert instance["sers_version"] == "1.2.0"
    delivery = instance["delivery"]
    assert delivery["channel"] == CHANNEL_NOT_INSTRUMENTED
    assert "refusal" in delivery["pi_c"]
    assert "refusal" in delivery["exposure"]
    assert instance["declared_synthetic_control"] is True
    assert instance["measurements"]["full_pass_rate"]["passes"] == 8
    assert instance["measurements"]["null_pass_rate"]["passes"] == 0


def test_fresh_subject_identity_mint_hashes_the_live_oracle_module() -> None:
    """A mint made NOW must carry the hash of the oracle module as it is now.

    This is the half of the old assertion that has content, and nothing else
    held it. It compares a fresh mint against live bytes, never against the
    historical fixture, so it stays true across every edit to the oracle while
    still failing if `build_subject_identity` ever stops reading the live module.
    """
    block = build_subject_identity(skill_md=_CONTROL_SKILL_MD, arms=["null", "full"])
    live_bytes = (_REPO_ROOT / "src" / "skill_harness" / "subject" / "ingest.py").read_bytes()
    assert block["implementation_hash"] == hashlib.sha256(live_bytes).hexdigest(), (
        "MINT_DOES_NOT_HASH_THE_LIVE_ORACLE: build_subject_identity returned an"
        " implementation_hash that is not a digest of the oracle module's current"
        " bytes, so a minted receipt would name an oracle that is not the one running."
    )


# ---------------------------------------------------------------------------
# Subject / extractor role split (#479)
# ---------------------------------------------------------------------------
#
# Before 1.4.0 the only model pin on a receipt was
# ``instrument_identity.extractor_model``, documented as "Extractor (or subject)
# model pin". One field named two instruments answering two different questions,
# and which one it named was not machine-readable. A reader asking "was this
# measured on the model it claims?" had to read the schema definition to learn the
# field was overloaded, and then still could not answer it.
#
# 1.4.0 splits the roles: ``subject_identity.subject_model`` names the model that
# executed the epochs, and ``extractor_model`` narrows to the extraction stage
# alone. The tests below hold both halves of that split, and the freeze on the
# receipts minted before it.


def _v14_instance() -> dict[str, Any]:
    """A minimal conforming 1.4.0 instance, built rather than stored.

    Deliberately not a fixture file. Every stored receipt in this repository is a
    record of a measurement that happened, and a 1.4.0 file would have to assert a
    ``subject_model`` for a run whose role assignment nobody recorded. Building the
    shape here proves the schema accepts the split without minting a document that
    could be mistaken for a receipt of record.
    """
    return {
        "sers_version": "1.4.0",
        "skill_name": "role-split-shape",
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
            "extractor_model": {"refusal": "not_applicable"},
            "prompt_fingerprint": "a",
            "schema_fingerprint": "b",
        },
        "delivery": {
            "channel": "not_instrumented",
            "exposure": {"refusal": "not_instrumented"},
            "pi_c": {"refusal": "not_instrumented"},
        },
        "source": {"prose_path": "README.md"},
        "summary": "Shape instance for the 1.4.0 subject/extractor role split.",
        "subject_identity": {
            "skill_id": "aabbccddee0011223344556677889900aabbccddee0011223344556677889900",
            "harness_version": "0.3.0",
            "metric_version": "0.4.1",
            "implementation_hash": (
                "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
            ),
            "arms": "null",
            "subject_model": "anthropic/claude-sonnet-5",
        },
    }


def test_v14_roles_split_instance_validates(sers_validator: Draft202012Validator) -> None:
    """A 1.4.0 receipt naming both roles separately is accepted."""
    sers_validator.validate(_v14_instance())


def test_v14_accepts_a_named_extractor_alongside_the_subject(
    sers_validator: Draft202012Validator,
) -> None:
    """The split is two pins, not a swap: both may be named, and they may differ."""
    instance = _v14_instance()
    instance["instrument_identity"]["extractor_model"] = "openai/gpt-5.6-sol"
    sers_validator.validate(instance)
    assert (
        instance["subject_identity"]["subject_model"]
        != instance["instrument_identity"]["extractor_model"]
    )


def test_poison_missing_subject_model_v14_is_red(sers_validator: Draft202012Validator) -> None:
    """1.4.0 subject_identity without subject_model must fail on that field (#479)."""
    path = _POISON_DIR / "poison_missing_subject_model_v14.json"
    assert path.is_file()
    instance = _load_json(path)
    assert instance["sers_version"] == "1.4.0"
    assert "subject_model" not in instance["subject_identity"]
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "subject_model" in str(excinfo.value)


def test_poison_extractor_model_open_refusal_is_red(
    sers_validator: Draft202012Validator,
) -> None:
    """extractor_model may be refused, but only from the closed vocabulary (#479).

    Free text in the refusal slot is how the overload would come back: a minter who
    cannot say which model played which role narrates a guess instead of declining.
    """
    path = _POISON_DIR / "poison_extractor_model_open_refusal.json"
    assert path.is_file()
    instance = _load_json(path)
    refusal = instance["instrument_identity"]["extractor_model"]["refusal"]
    assert refusal not in {"not_applicable", "not_instrumented"}
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "extractor_model" in str(excinfo.value)


def test_subject_model_is_not_required_before_v14(sers_validator: Draft202012Validator) -> None:
    """The version gate carries the requirement, so older receipts still stand.

    Every prior identity block landed the same way: subject_identity at 1.1.0,
    delivery at 1.2.0, the trap keys at 1.3.0. Adding subject_model to
    subject_identity's own required list would have retroactively invalidated every
    1.1.0 to 1.3.0 receipt in the store.
    """
    instance = _v14_instance()
    instance["sers_version"] = "1.3.0"
    del instance["subject_identity"]["subject_model"]
    sers_validator.validate(instance)


def test_published_receipts_before_v14_carry_no_subject_model() -> None:
    """The existing receipts are frozen, not migrated (#479).

    A receipt is a dated record of a measurement that was made. Adding a
    subject_model to one would assert which model played the subject role in a run
    where no field recorded it, which is a fact nobody wrote down. On every receipt
    in the store the recorded pin is consistent with the subject reading, but
    consistent is not recorded, and an append-only store is exactly where that
    difference matters. They stay as minted; the interpretation rule in
    docs/sers/README.md tells a reader how to read them.

    This control fails if a later change back-fills one, which is the moment that
    decision should be taken deliberately rather than as a tidy-up.
    """
    offenders = []
    for path in sorted(_RECEIPTS_DIR.rglob("*.json")):
        instance = _load_json(path)
        if instance.get("sers_version") == "1.4.0":
            continue
        if "subject_model" in instance.get("subject_identity", {}):
            offenders.append(path.name)
    assert not offenders, (
        "RECEIPT_BACKFILLED: these pre-1.4.0 receipts gained a subject_model they were"
        f" not minted with: {offenders}. The store is append-only; mint a new receipt"
        " rather than editing a dated record."
    )


def test_schema_no_longer_documents_extractor_model_as_the_subject() -> None:
    """The defect itself, held open (#479).

    The whole issue was one sentence: "Extractor (or subject) model pin that
    produced the figures." If that parenthetical returns the field is overloaded
    again, and every other test here still passes, because nothing else reads it.
    """
    raw = _SCHEMA_PATH.read_text(encoding="utf-8")
    assert "Extractor (or subject)" not in raw
    identity = _load_json(_SCHEMA_PATH)["properties"]["instrument_identity"]["properties"]
    assert "never the subject under test" in identity["extractor_model"]["description"]


def test_build_subject_identity_records_the_subject_model() -> None:
    """The mint helper carries the pin the caller supplies, and omits it otherwise."""
    without = build_subject_identity(skill_md=_CONTROL_SKILL_MD, arms=["null", "full"])
    assert "subject_model" not in without

    with_pin = build_subject_identity(
        skill_md=_CONTROL_SKILL_MD,
        arms=["null", "full"],
        subject_model="anthropic/claude-sonnet-5",
    )
    assert with_pin["subject_model"] == "anthropic/claude-sonnet-5"


@pytest.mark.parametrize("blank", ["", "   "])
def test_build_subject_identity_refuses_a_blank_subject_model(blank: str) -> None:
    """A blank pin is a manufactured record, not a missing one."""
    with pytest.raises(ValueError, match="subject_model"):
        build_subject_identity(skill_md=_CONTROL_SKILL_MD, arms="null", subject_model=blank)


# ---------------------------------------------------------------------------
# On-Irreducibility additions 3, 5, 6 (#526)
# ---------------------------------------------------------------------------


def _v15_instance() -> dict[str, Any]:
    """A minimal conforming 1.5.0 instance with all three new optional fields."""
    return {
        "sers_version": "1.5.0",
        "skill_name": "on-irreducibility-shape",
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
            "extractor_model": {"refusal": "not_applicable"},
            "prompt_fingerprint": "a",
            "schema_fingerprint": "b",
        },
        "delivery": {
            "channel": "not_instrumented",
            "exposure": {"refusal": "not_instrumented"},
            "pi_c": {"refusal": "not_instrumented"},
        },
        "source": {"prose_path": "README.md"},
        "summary": "Shape instance for the 1.5.0 On-Irreducibility additions.",
        "subject_identity": {
            "skill_id": "aabbccddee0011223344556677889900aabbccddee0011223344556677889900",
            "harness_version": "0.3.0",
            "metric_version": "0.4.1",
            "implementation_hash": (
                "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
            ),
            "arms": "null",
            "subject_model": "anthropic/claude-sonnet-5",
        },
        "implementation_family": "retrieval-augmented generation",
        "claim_scope": "Behavioral claim under standard agent workload disturbances",
        "retest_triggers": "Metric version bump or skill content change",
        "expiry_state": "current",
    }


def test_v15_with_all_new_fields_validates(sers_validator: Draft202012Validator) -> None:
    """A 1.5.0 receipt carrying implementation_family, claim_scope,
    retest_triggers and expiry_state validates."""
    sers_validator.validate(_v15_instance())


def test_v15_without_new_fields_still_validates(sers_validator: Draft202012Validator) -> None:
    """The new fields are optional; a 1.5.0 receipt omitting them still validates."""
    instance = _v15_instance()
    del instance["implementation_family"]
    del instance["claim_scope"]
    del instance["retest_triggers"]
    del instance["expiry_state"]
    sers_validator.validate(instance)


def test_expiry_state_rejects_invalid_value(sers_validator: Draft202012Validator) -> None:
    """expiry_state must be one of current, stale, no_current_metric_version."""
    instance = _v15_instance()
    instance["expiry_state"] = "expired"
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "expiry_state" in str(excinfo.value)


def test_v14_receipt_without_new_fields_still_validates(
    sers_validator: Draft202012Validator,
) -> None:
    """The new fields are optional at every version, including pre-1.5.0."""
    instance = _v14_instance()
    sers_validator.validate(instance)
    assert "implementation_family" not in instance
    assert "claim_scope" not in instance
    assert "retest_triggers" not in instance
    assert "expiry_state" not in instance


def test_schema_15_version_in_enum(sers_schema: dict[str, Any]) -> None:
    """sers_version enum includes 1.5.0."""
    schema_vals = _schema_enum(sers_schema, "properties", "sers_version", "enum")
    assert "1.5.0" in schema_vals


def test_schema_new_properties_are_optional() -> None:
    """None of the three new On-Irreducibility keys appear in the top-level
    required list — they are author-typed and never computed by the harness."""
    schema = _load_json(_SCHEMA_PATH)
    required = set(schema.get("required", []))
    assert "implementation_family" not in required
    assert "claim_scope" not in required
    assert "retest_triggers" not in required
    assert "expiry_state" not in required


# ---------------------------------------------------------------------------
# Verdict validity: verdict_scope / currentness / drift_policy (#643)
# ---------------------------------------------------------------------------


def _v16_instance() -> dict[str, Any]:
    """A minimal conforming 1.6.0 instance with all three new objects."""
    return {
        "sers_version": "1.6.0",
        "skill_name": "verdict-validity-shape",
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
            "extractor_model": {"refusal": "not_applicable"},
            "prompt_fingerprint": "a",
            "schema_fingerprint": "b",
        },
        "source": {"prose_path": "README.md"},
        "summary": "Shape instance for the 1.6.0 verdict-validity additions.",
        "subject_identity": {
            "skill_id": "aabbccddee0011223344556677889900aabbccddee0011223344556677889900",
            "harness_version": "0.3.0",
            "metric_version": "0.4.1",
            "implementation_hash": (
                "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
            ),
            "arms": "null",
            "subject_model": "anthropic/claude-sonnet-5",
        },
        "verdict_scope": {
            "model_id": "anthropic/claude-sonnet-5",
            "harness_version": "0.3.0",
            "fixture_version": "abc123",
            "task_id": "test-task",
            "tested_at": "2026-09-22T00:00:00Z",
            "task_family": "test-family",
            "estimand": "treatment-policy",
            "delivery_mechanism": "model-pull",
            "n_per_arm": 8,
            "margin_pp": 5.0,
            "cs_lower_bound": 0.75,
            "control_world_result": "pass",
            "placebo_ref": "synthetic-control",
            "fixture_id": "fixture-001",
        },
        "currentness": {
            "state": "VALIDATED",
            "basis": "FULL_VALIDATION",
            "last_checked_at": "2026-09-22T00:00:00Z",
            "next_check_due": "2026-12-21T00:00:00Z",
            "max_age_days": 90,
        },
        "drift_policy": {
            "null_trigger_pp": 10,
            "canary_n": 8,
            "full_rerun_on_null_trigger": True,
            "full_rerun_on_canary_failure": True,
            "full_rerun_on_model_change": True,
        },
    }


def test_v16_with_all_new_objects_validates(sers_validator: Draft202012Validator) -> None:
    """A 1.6.0 receipt carrying verdict_scope, currentness and drift_policy validates."""
    sers_validator.validate(_v16_instance())


def test_v16_without_new_objects_still_validates(sers_validator: Draft202012Validator) -> None:
    """The three objects are optional; a 1.6.0 receipt omitting them still validates."""
    instance = _v16_instance()
    del instance["verdict_scope"]
    del instance["currentness"]
    del instance["drift_policy"]
    sers_validator.validate(instance)


def test_v16_partial_objects_validates(sers_validator: Draft202012Validator) -> None:
    """A 1.6.0 receipt carrying only currentness validates."""
    instance = _v16_instance()
    del instance["verdict_scope"]
    del instance["drift_policy"]
    sers_validator.validate(instance)


def test_schema_16_version_in_enum(sers_schema: dict[str, Any]) -> None:
    """sers_version enum includes 1.6.0."""
    schema_vals = _schema_enum(sers_schema, "properties", "sers_version", "enum")
    assert "1.6.0" in schema_vals


def test_schema_verdict_validity_properties_are_optional() -> None:
    """verdict_scope, currentness, drift_policy are not in the top-level required list."""
    schema = _load_json(_SCHEMA_PATH)
    required = set(schema.get("required", []))
    assert "verdict_scope" not in required
    assert "currentness" not in required
    assert "drift_policy" not in required


def test_poison_validated_sentinel_pass_is_red(sers_validator: Draft202012Validator) -> None:
    """currentness VALIDATED with SENTINEL_PASS basis must fail (criterion 2)."""
    path = _POISON_DIR / "poison_validated_sentinel_pass.json"
    assert path.is_file()
    instance = _load_json(path)
    assert instance["currentness"]["state"] == "VALIDATED"
    assert instance["currentness"]["basis"] == "SENTINEL_PASS"
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "SENTINEL_PASS" in str(excinfo.value) or "basis" in str(excinfo.value)


def test_poison_keep_no_model_id_is_red(sers_validator: Draft202012Validator) -> None:
    """KEEP at 1.6.0 without verdict_scope.model_id must fail (criterion 4)."""
    path = _POISON_DIR / "poison_keep_no_model_id.json"
    assert path.is_file()
    instance = _load_json(path)
    assert instance["verdict"] == "KEEP"
    assert instance["sers_version"] == "1.6.0"
    assert "model_id" not in instance.get("verdict_scope", {})
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "model_id" in str(excinfo.value)


def test_poison_keep_no_task_family_is_red(sers_validator: Draft202012Validator) -> None:
    """KEEP at 1.6.0 without task_family in verdict_scope must fail (S476 criterion 3)."""
    path = _POISON_DIR / "poison_keep_no_task_family.json"
    assert path.is_file()
    instance = _load_json(path)
    assert instance["verdict"] == "KEEP"
    assert "task_family" not in instance.get("verdict_scope", {})
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "task_family" in str(excinfo.value)


def test_poison_keep_no_delivery_mechanism_is_red(
    sers_validator: Draft202012Validator,
) -> None:
    """KEEP at 1.6.0 without delivery_mechanism in verdict_scope must fail (S476 criterion 3)."""
    path = _POISON_DIR / "poison_keep_no_delivery_mechanism.json"
    assert path.is_file()
    instance = _load_json(path)
    assert instance["verdict"] == "KEEP"
    assert "delivery_mechanism" not in instance.get("verdict_scope", {})
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "delivery_mechanism" in str(excinfo.value)


def test_carried_forward_requires_tested_at(sers_validator: Draft202012Validator) -> None:
    """CARRIED_FORWARD currentness requires verdict_scope.tested_at."""
    instance = _v16_instance()
    instance["currentness"]["state"] = "CARRIED_FORWARD"
    instance["currentness"]["basis"] = "SENTINEL_PASS"
    del instance["verdict_scope"]["tested_at"]
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "tested_at" in str(excinfo.value)


def test_carried_forward_with_tested_at_validates(
    sers_validator: Draft202012Validator,
) -> None:
    """CARRIED_FORWARD with tested_at present validates."""
    instance = _v16_instance()
    instance["currentness"]["state"] = "CARRIED_FORWARD"
    instance["currentness"]["basis"] = "SENTINEL_PASS"
    sers_validator.validate(instance)


def test_stale_currentness_validates(sers_validator: Draft202012Validator) -> None:
    """STALE currentness with NONE basis validates."""
    instance = _v16_instance()
    instance["currentness"]["state"] = "STALE"
    instance["currentness"]["basis"] = "NONE"
    sers_validator.validate(instance)


def test_keep_at_16_requires_verdict_scope(sers_validator: Draft202012Validator) -> None:
    """KEEP at 1.6.0 requires verdict_scope (not just model_id)."""
    instance = _v16_instance()
    instance["verdict"] = "KEEP"
    del instance["verdict_scope"]
    with pytest.raises(ValidationError) as excinfo:
        sers_validator.validate(instance)
    assert "verdict_scope" in str(excinfo.value)
