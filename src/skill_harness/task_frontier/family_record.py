"""Family record schema and registration checks (#647).

A family record declares the causal mechanism a task family tests, frozen
before any run.  Five fields identify the mechanism; a reviewer who can
point at the field that changed a second family's realization while
``mechanism_id`` stayed the same establishes that the two families are
materially distinct.

Registration checks enforce two constraints:

  predate-first-epoch  — the family's registration commit must predate
    its first paid epoch (``registered_at`` < ``first_epoch_at``).
  fixture-path uniqueness — the harness refuses a family record that
    shares its fixture_path with an existing family.

The record is the pre-declaration that makes the REPLICATED and ROBUST
claim levels machine-checkable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

_KNOWN_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "mechanism_id",
        "hazard_condition",
        "intervention_action",
        "outcome",
        "allowed_substitutions",
        "fixture_path",
        "registered_at",
    }
)


@dataclass(frozen=True)
class FamilyRecord:
    """A declared causal mechanism, frozen before any run.

    ``mechanism_id`` is stable across families that test the same mechanism.
    ``fixture_path`` must be unique across all registered families — two
    families that share a fixture path are the same task and cannot both
    count as independent replications.
    """

    mechanism_id: str
    hazard_condition: str
    intervention_action: str
    outcome: str
    allowed_substitutions: str
    fixture_path: str
    registered_at: str


def load_family_record(data: Mapping[str, Any]) -> FamilyRecord:
    """Parse and validate a family record.

    :param data: The raw mapping (as loaded from JSON).
    :returns: A frozen ``FamilyRecord``.
    :raises ValueError: If a required key is absent, mistyped, or an
        unrecognised key is present.
    """
    unknown = sorted(set(data) - _KNOWN_FIELDS)
    if unknown:
        raise ValueError(
            f"family record: unrecognised key(s) {unknown} — this loader carries "
            f"only {sorted(_KNOWN_FIELDS)}"
        )
    return FamilyRecord(
        mechanism_id=_require_str(data, "mechanism_id", "family record"),
        hazard_condition=_require_str(data, "hazard_condition", "family record"),
        intervention_action=_require_str(data, "intervention_action", "family record"),
        outcome=_require_str(data, "outcome", "family record"),
        allowed_substitutions=_require_str(data, "allowed_substitutions", "family record"),
        fixture_path=_require_str(data, "fixture_path", "family record"),
        registered_at=_require_str(data, "registered_at", "family record"),
    )


def check_predate_first_epoch(
    family: FamilyRecord,
    first_epoch_at: str,
) -> None:
    """Refuse a family whose registration predates no epoch.

    The family's ``registered_at`` must be strictly before ``first_epoch_at``.
    Both values must be ISO-8601 datetimes with an explicit UTC offset.

    :raises ValueError: If the family was registered on or after the first epoch.
    """
    registered_at = _parse_timestamp(family.registered_at, "registered_at")
    first_epoch = _parse_timestamp(first_epoch_at, "first_epoch_at")
    if registered_at >= first_epoch:
        raise ValueError(
            f"family record {family.mechanism_id!r}: registered_at "
            f"{family.registered_at!r} is not before first_epoch_at "
            f"{first_epoch_at!r} — the family must be registered before any "
            "paid epoch"
        )


def check_fixture_path_uniqueness(
    new_family: FamilyRecord,
    existing: Mapping[str, FamilyRecord],
) -> None:
    """Refuse a family that shares its fixture path with an existing family.

    Two families that share a fixture path test the same task and cannot both
    count as independent replications.

    :param new_family: The family being registered.
    :param existing: mapping of mechanism_id -> FamilyRecord for already-registered
        families.
    :raises ValueError: If an existing family has the same ``fixture_path``.
    """
    for existing_id, existing_family in existing.items():
        if existing_family.fixture_path == new_family.fixture_path:
            raise ValueError(
                f"family record {new_family.mechanism_id!r}: fixture_path "
                f"{new_family.fixture_path!r} is already registered by family "
                f"{existing_id!r} — two families sharing a fixture path are not "
                "materially distinct"
            )


def _require_str(data: Mapping[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: key {key!r} must be a non-empty string; got {value!r}")
    return value


def _parse_timestamp(value: str, field: str) -> datetime:
    """Parse an offset-aware ISO-8601 timestamp for an ordering check."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"family record: {field} must be an ISO-8601 datetime; got {value!r}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"family record: {field} must include a UTC offset; got {value!r}")
    return parsed
