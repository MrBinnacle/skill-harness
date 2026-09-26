"""#647 family record schema and registration checks.

Proves the family record schema, the predate-first-epoch guard, and the
fixture-path uniqueness guard.  Every assertion crosses the family-record
seam; storage internals are never touched.

The property under test is the registration firewall:

  * ``load_family_record`` freezes the five mechanism fields plus the
    fixture path and registration timestamp;
  * ``check_predate_first_epoch`` refuses a family registered on or after
    its first epoch;
  * ``check_fixture_path_uniqueness`` refuses a family whose fixture path
    is already registered.
"""

from __future__ import annotations

import pytest

from skill_harness.task_frontier.family_record import (
    check_fixture_path_uniqueness,
    check_predate_first_epoch,
    load_family_record,
)

# ---------------------------------------------------------------------------
# Fixtures — a minimal, hand-checkable family record.
# ---------------------------------------------------------------------------

_MINIMAL_DATA = {
    "mechanism_id": "git-pull-rebase-trap",
    "hazard_condition": "user runs git pull on a diverged branch",
    "intervention_action": "skill suggests rebase before pull",
    "outcome": "user avoids accidental merge commit",
    "allowed_substitutions": "none",
    "fixture_path": "fixtures/gitpull/v3a",
    "registered_at": "2026-09-20T00:00:00Z",
}


def _record(**overrides: str) -> dict[str, str]:
    data = dict(_MINIMAL_DATA)
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# AC1 — a well-formed family record loads and round-trips frozen.
# ---------------------------------------------------------------------------


class TestFamilyRecordRoundTrip:
    def test_minimal_record_round_trips(self) -> None:
        record = load_family_record(_MINIMAL_DATA)

        assert record.mechanism_id == "git-pull-rebase-trap"
        assert record.hazard_condition == "user runs git pull on a diverged branch"
        assert record.intervention_action == "skill suggests rebase before pull"
        assert record.outcome == "user avoids accidental merge commit"
        assert record.allowed_substitutions == "none"
        assert record.fixture_path == "fixtures/gitpull/v3a"
        assert record.registered_at == "2026-09-20T00:00:00Z"

    def test_record_is_frozen(self) -> None:
        record = load_family_record(_MINIMAL_DATA)
        with pytest.raises((AttributeError, TypeError)):
            record.mechanism_id = "something-else"  # type: ignore[misc]

    def test_all_five_mechanism_fields_are_present(self) -> None:
        """The five fields the ruling names are all loadable."""
        record = load_family_record(_MINIMAL_DATA)
        assert record.mechanism_id
        assert record.hazard_condition
        assert record.intervention_action
        assert record.outcome
        assert record.allowed_substitutions


# ---------------------------------------------------------------------------
# AC2 — unrecognised keys are refused, not dropped.
# ---------------------------------------------------------------------------


class TestGuardsBite:
    def test_unrecognised_key_is_refused(self) -> None:
        data = _record(extra_field="should not be here")
        with pytest.raises(ValueError, match="unrecognised key"):
            load_family_record(data)

    @pytest.mark.parametrize(
        "missing",
        [
            "mechanism_id",
            "hazard_condition",
            "intervention_action",
            "outcome",
            "allowed_substitutions",
            "fixture_path",
            "registered_at",
        ],
    )
    def test_missing_required_key_is_refused(self, missing: str) -> None:
        data = dict(_MINIMAL_DATA)
        del data[missing]
        with pytest.raises(ValueError, match=r"missing required key|must be a non-empty string"):
            load_family_record(data)

    def test_empty_string_is_refused(self) -> None:
        data = _record(mechanism_id="")
        with pytest.raises(ValueError, match="must be a non-empty string"):
            load_family_record(data)


# ---------------------------------------------------------------------------
# AC3 — predate-first-epoch guard.
# ---------------------------------------------------------------------------


class TestPredateFirstEpoch:
    def test_family_registered_before_first_epoch_passes(self) -> None:
        family = load_family_record(_MINIMAL_DATA)
        check_predate_first_epoch(family, "2026-09-21T00:00:00Z")

    def test_family_registered_on_first_epoch_is_refused(self) -> None:
        family = load_family_record(_MINIMAL_DATA)
        with pytest.raises(ValueError, match="not before first_epoch_at"):
            check_predate_first_epoch(family, "2026-09-20T00:00:00Z")

    def test_family_registered_after_first_epoch_is_refused(self) -> None:
        family = load_family_record(_MINIMAL_DATA)
        with pytest.raises(ValueError, match="not before first_epoch_at"):
            check_predate_first_epoch(family, "2026-09-19T00:00:00Z")


# ---------------------------------------------------------------------------
# AC4 — fixture-path uniqueness guard.
# ---------------------------------------------------------------------------


class TestFixturePathUniqueness:
    def test_different_fixture_path_passes(self) -> None:
        family = load_family_record(_MINIMAL_DATA)
        existing = {
            "other-mechanism": load_family_record(
                _record(
                    mechanism_id="other-mechanism",
                    fixture_path="fixtures/other/v1",
                )
            ),
        }
        check_fixture_path_uniqueness(family, existing)

    def test_same_fixture_path_is_refused(self) -> None:
        family = load_family_record(_MINIMAL_DATA)
        existing = {
            "existing-mechanism": load_family_record(
                _record(
                    mechanism_id="existing-mechanism",
                    fixture_path="fixtures/gitpull/v3a",
                )
            ),
        }
        with pytest.raises(ValueError, match=r"fixture_path.*already registered"):
            check_fixture_path_uniqueness(family, existing)

    def test_empty_existing_registry_passes(self) -> None:
        family = load_family_record(_MINIMAL_DATA)
        check_fixture_path_uniqueness(family, {})
