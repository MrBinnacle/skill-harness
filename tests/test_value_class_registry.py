"""Tests for the value-class registry + the four-record flip regression (#77).

These lock four things:
  1. The portfolio classification is complete and pins the S2-kill condition
     (0 transformative-lift → the signed kill fires; see F6-signoff-S166).
  2. The four historical false CUTs (OBS-0003..0006) re-render CAN'T-TELL-YET
     (wrong instrument), NEVER CUT, once their registered class flows through the
     guard — the standing regression against re-introducing the day-one falsehood.
  3. ``value_class_for`` is the honest default for an unregistered skill (None).
  4. The registry is measured by this file against a pinned list of
     ``(skill_name, value_class, retired_on)`` triples (#422).
  5. Every non-retired registry key names a skill that exists on a named surface;
     a rename that does not reach the registry is caught here (#601).

External-behaviour only — no store, no private logs (the guard is a pure function
of p0 + value_class; the registry is a pure map).
"""

from __future__ import annotations

from datetime import date

import pytest

from skill_harness.aggregation.value_class_registry import (
    SKILL_VALUE_CLASS,
    value_class_for,
)
from skill_harness.aggregation.verdict import (
    KeepCutVerdict,
    ValueClass,
    screen_verdict,
)

# The portfolio classification, measured by this file (#422).
# Each triple: (skill_name, value_class, retired_on | None).
# retired_on carries the date the card left the published collection (or was
# screened out); None means still published. Historic screen records use the
# pre-2026-09-08 names, so their aliases stay registered as retired. OBS-0003
# is keyed on sqlite-tie-break-red-test-trap, so that row stays (#41).
_PORTFOLIO_TRIPLES: list[tuple[str, ValueClass, date | None]] = [
    # --- calibration: make a measurement/evaluation trustworthy ---------------
    ("bayesian-eval-discipline", ValueClass.CALIBRATION, None),
    ("llm-judge-calibration", ValueClass.CALIBRATION, None),
    ("append-only-evidence-design", ValueClass.CALIBRATION, None),
    # --- trap-discipline: guard against one specific wrong action -------------
    ("git-pull-rebase-trap", ValueClass.TRAP_DISCIPLINE, date(2026, 9, 8)),
    (
        "sqlite-tie-break-red-test-trap",
        ValueClass.TRAP_DISCIPLINE,
        date(2026, 7, 10),  # screened out — RETIRED.md screened-out table
    ),
    ("github-pages-deploy-verification", ValueClass.TRAP_DISCIPLINE, date(2026, 9, 8)),
    ("subagent-research-reliability", ValueClass.TRAP_DISCIPLINE, date(2026, 9, 8)),
    ("downstream-instruction-framing", ValueClass.TRAP_DISCIPLINE, date(2026, 9, 8)),
    ("closure-mode-at-boundaries", ValueClass.TRAP_DISCIPLINE, date(2026, 9, 8)),
    (
        "skill-necessity-gate",
        ValueClass.TRAP_DISCIPLINE,
        date(2026, 8, 31),  # retired — skills#178, RETIRED.md
    ),
    ("parallel-review-disposition-schema", ValueClass.TRAP_DISCIPLINE, date(2026, 9, 8)),
    ("mock-masked-stub-trap", ValueClass.TRAP_DISCIPLINE, date(2026, 9, 8)),
    ("pull-rebase", ValueClass.TRAP_DISCIPLINE, None),
    ("stale-deploy", ValueClass.TRAP_DISCIPLINE, None),
    ("subagent-handback", ValueClass.TRAP_DISCIPLINE, None),
    ("decision-rights", ValueClass.TRAP_DISCIPLINE, None),
    ("closure-mode", ValueClass.TRAP_DISCIPLINE, None),
    ("disposition-schema", ValueClass.TRAP_DISCIPLINE, None),
    ("mocked-stub", ValueClass.TRAP_DISCIPLINE, None),
    # --- transformative-lift: intentionally empty (S2-kill fires) -------------
]

# The four historical Stage-0 records the guard exists to un-false-CUT.
_OBS_0003_0006 = (
    "sqlite-tie-break-red-test-trap",  # OBS-0003
    "bayesian-eval-discipline",  # OBS-0004
    "append-only-evidence-design",  # OBS-0005
    "llm-judge-calibration",  # OBS-0006
)


# ---------------------------------------------------------------------------
# Staleness detection — every non-retired key must name a live skill (#601)
# ---------------------------------------------------------------------------

# The set of skill names known to exist on a named surface (the published
# collection).  Sourced from the class-hypothesis census (2026-09-20) and the
# skills collection's SKILL.md frontmatter.  A key absent from this set is
# stale: the card was renamed or removed and the registry was not updated.
# Update this set when the collection renames or retires a card.
_KNOWN_LIVE_SKILLS: frozenset[str] = frozenset(
    {
        "bayesian-eval-discipline",
        "llm-judge-calibration",
        "append-only-evidence-design",
        "pull-rebase",
        "stale-deploy",
        "subagent-handback",
        "decision-rights",
        "closure-mode",
        "disposition-schema",
        "mocked-stub",
    }
)

_RENAMED_SKILL_NAMES: tuple[tuple[str, str], ...] = (
    ("git-pull-rebase-trap", "pull-rebase"),
    ("github-pages-deploy-verification", "stale-deploy"),
    ("subagent-research-reliability", "subagent-handback"),
    ("downstream-instruction-framing", "decision-rights"),
    ("closure-mode-at-boundaries", "closure-mode"),
    ("parallel-review-disposition-schema", "disposition-schema"),
    ("mock-masked-stub-trap", "mocked-stub"),
)


def _stale_skill_keys(
    registry: dict[str, ValueClass],
    retired: set[str],
    live: frozenset[str],
) -> list[str]:
    """Return non-retired registry keys that do not name a known live skill.

    A key that names a retired skill is excluded (retired skills are expected
    to be absent from the live collection). A non-retired key missing from
    ``live`` is stale.
    """
    return sorted(
        name for name, _vc in registry.items() if name not in retired and name not in live
    )


def test_no_stale_skill_keys() -> None:
    """#601: every non-retired registry key resolves to a skill on a named surface.

    This catches renames that did not reach the registry (the defect
    ``closure-mode-at-boundaries`` → ``closure-mode`` that filed #601).
    When a card is renamed in the collection, this test fails until the
    registry key is updated to match.
    """
    retired = {name for name, _vc, retired_on in _PORTFOLIO_TRIPLES if retired_on is not None}
    stale = _stale_skill_keys(SKILL_VALUE_CLASS, retired, _KNOWN_LIVE_SKILLS)
    assert not stale, (
        f"registry key(s) name no known live skill: {stale}.  "
        "If the card was renamed, update the registry key and this test's "
        "_KNOWN_LIVE_SKILLS set.  If the card was retired, add a retired_on "
        "date to the _PORTFOLIO_TRIPLES entry."
    )


def test_stale_key_check_catches_poisoned_registry() -> None:
    """Negative control: the staleness check must fail when given a poisoned key.

    Proves the check is not vacuous — it would have caught the
    ``closure-mode-at-boundaries`` stale key before #601.
    """
    poisoned: dict[str, ValueClass] = {
        **SKILL_VALUE_CLASS,
        "deliberately-stale-key": ValueClass.TRAP_DISCIPLINE,
    }
    stale = _stale_skill_keys(poisoned, set(), _KNOWN_LIVE_SKILLS)
    assert "deliberately-stale-key" in stale, (
        "the staleness check did not catch the deliberately poisoned key; the check is vacuous"
    )


# ---------------------------------------------------------------------------
# Registry completeness + the S2-kill condition
# ---------------------------------------------------------------------------


def test_portfolio_pinned_by_triples() -> None:
    """#422: the map matches the pinned (skill_name, value_class, retired_on) list."""
    names = [name for name, _vc, _ret in _PORTFOLIO_TRIPLES]
    assert len(names) == len(set(names))
    assert set(SKILL_VALUE_CLASS) == set(names)
    for name, vc, _retired_on in _PORTFOLIO_TRIPLES:
        assert SKILL_VALUE_CLASS[name] is vc
    retired = {
        name: retired_on for name, _vc, retired_on in _PORTFOLIO_TRIPLES if retired_on is not None
    }
    assert retired == {
        "sqlite-tie-break-red-test-trap": date(2026, 7, 10),
        "skill-necessity-gate": date(2026, 8, 31),
        "git-pull-rebase-trap": date(2026, 9, 8),
        "github-pages-deploy-verification": date(2026, 9, 8),
        "subagent-research-reliability": date(2026, 9, 8),
        "downstream-instruction-framing": date(2026, 9, 8),
        "closure-mode-at-boundaries": date(2026, 9, 8),
        "parallel-review-disposition-schema": date(2026, 9, 8),
        "mock-masked-stub-trap": date(2026, 9, 8),
    }
    assert value_class_for("mocked-stub") is ValueClass.TRAP_DISCIPLINE


@pytest.mark.parametrize(("retired_name", "published_name"), _RENAMED_SKILL_NAMES)
def test_renamed_skill_names_preserve_historic_and_published_lookups(
    retired_name: str, published_name: str
) -> None:
    """#601: renamed cards resolve under their published and historical screen names."""
    assert value_class_for(retired_name) is ValueClass.TRAP_DISCIPLINE
    assert value_class_for(published_name) is ValueClass.TRAP_DISCIPLINE


def test_s2_kill_condition_transformative_lift_class_is_empty() -> None:
    """The machine-checkable form of the signed S2-kill trigger (F6-signoff-S166):
    NO skill is transformative-lift → the harness has zero current customers for its
    one measurement path → ship field/CAN'T-TELL-YET only, do NOT build the S3 board.
    If a future transformative-lift KEEP is registered here, this test flips and the
    kill calculus is revisited (F6 Revisit-if) — that is the intended trip-wire."""
    assert ValueClass.TRANSFORMATIVE_LIFT not in SKILL_VALUE_CLASS.values()


def test_f8a_third_class_named_and_populated() -> None:
    """F8a: the canonical third partition is named from the real distribution and is
    non-empty (calibration skills). The point-trap disciplines are the balance."""
    assert ValueClass.CALIBRATION.value == "calibration"
    counts = {vc: sum(1 for v in SKILL_VALUE_CLASS.values() if v is vc) for vc in ValueClass}
    pinned = {vc: sum(1 for _n, v, _r in _PORTFOLIO_TRIPLES if v is vc) for vc in ValueClass}
    assert counts[ValueClass.CALIBRATION] == pinned[ValueClass.CALIBRATION]
    assert counts[ValueClass.TRAP_DISCIPLINE] == pinned[ValueClass.TRAP_DISCIPLINE]
    assert counts[ValueClass.CALIBRATION] > 0
    assert counts[ValueClass.TRAP_DISCIPLINE] > 0
    assert counts[ValueClass.TRANSFORMATIVE_LIFT] == 0


def test_value_class_for_unregistered_is_none() -> None:
    """The honest default: an unknown skill_name → None → the guard's not-transformative
    path (CAN'T-TELL-YET), never a false CUT."""
    assert value_class_for("some-unregistered-skill") is None
    assert value_class_for("pull-rebase") is ValueClass.TRAP_DISCIPLINE
    assert value_class_for("closure-mode") is ValueClass.TRAP_DISCIPLINE
    assert value_class_for("closure-mode-at-boundaries") is ValueClass.TRAP_DISCIPLINE
    assert value_class_for("llm-judge-calibration") is ValueClass.CALIBRATION


# ---------------------------------------------------------------------------
# The four-record flip regression — the standing guard against the false CUT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_name", _OBS_0003_0006)
def test_obs_records_ceiling_flips_to_cant_tell_not_cut(skill_name: str) -> None:
    """THE flip regression (US-3): each of OBS-0003..0006 ceilings at p0 = 1.00 on its
    Null screen. Routed through its REGISTERED value_class, the guard must render
    CAN'T-TELL-YET (wrong instrument), never CUT(subsumed). Reintroducing the false CUT
    (dropping the class, or mapping any of these to transformative-lift) fails here."""
    vc = value_class_for(skill_name)
    assert vc is not None, f"{skill_name} must be registered"
    assert vc is not ValueClass.TRANSFORMATIVE_LIFT

    v = screen_verdict(1.0, value_class=vc)
    # CANT_TELL_YET (not CUT) with no subsumed sub-reason == the false CUT withheld.
    assert v.verdict is KeepCutVerdict.CANT_TELL_YET
    assert v.cut_sub_reason is None
    assert v.wrong_instrument is True
    assert "wrong instrument" in v.rationale.lower()


def test_calibration_ceiling_is_wrong_instrument_like_trap() -> None:
    """The new CALIBRATION class behaves at the guard exactly like trap-discipline:
    a screen ceiling is a wrong-instrument CAN'T-TELL-YET, not a subsumed CUT."""
    v = screen_verdict(1.0, value_class=ValueClass.CALIBRATION)
    assert v.verdict is KeepCutVerdict.CANT_TELL_YET
    assert v.wrong_instrument is True
