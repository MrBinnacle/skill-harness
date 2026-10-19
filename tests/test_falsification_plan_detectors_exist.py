"""The falsification plan names detector modules; this checks that they exist.

`docs/assurance/falsification-plan.md` registers ten failure modes. Each row ends in a
`**Detection:**` line naming exactly one test module. Nine of the ten named modules were
absent from the tracked tree for the life of the document, and no check noticed. A person
noticed, once, by hand (#341).

This module makes the absence mechanical. The next plan row that names a file it does not
have fails here instead of waiting for someone to look.

Ratchet, not threshold
----------------------
A bare existence assertion goes red on nine rows the moment it lands, and a permanently red
gate is read as broken and then ignored. So the known-absent rows are recorded by name in
`docs/assurance/falsification-detector-baseline.json`, and three rules make that list a
ratchet rather than a mute button:

1. A named detector that is absent and unlisted fails.
2. A listed detector that now exists fails, demanding its removal from the baseline.
3. A missing or unparseable baseline fails.

Rule 2 is the ratchet. The baseline can only shrink, so it converges to empty and cannot be
edited to silence a red run. Rule 3 makes deleting the file useless.

Prior art in this repository: `tests/test_structural_bans.py`, whose allowlists are
themselves cross-checked against the pre-commit configuration so the two cannot drift.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
PLAN_PATH: Final[Path] = REPO_ROOT / "docs" / "assurance" / "falsification-plan.md"
BASELINE_PATH: Final[Path] = (
    REPO_ROOT / "docs" / "assurance" / "falsification-detector-baseline.json"
)

# The plan states its own size: "Ranked falsification list (exactly ten)". Without this
# count, a parser that silently matched nothing would make every other assertion here
# vacuously true, which is the failure the success-test-accepts-any-output card describes.
EXPECTED_DETECTION_ROWS: Final[int] = 10

# A Detection line reads: **Detection:** `tests/some_module.py` then prose that may wrap
# across several lines and contain further backticked identifiers. The detector is the first
# backticked token after the marker that ends in .py.
_DETECTION_MARKER: Final[str] = "**Detection:**"
_BACKTICKED_PY: Final[re.Pattern[str]] = re.compile(r"`([^`]+\.py)`")


def _read_plan() -> str:
    """Return the plan's text.

    The encoding is explicit because the document contains an em dash, a less-than-or-equal
    sign and combining accents. On a Windows host the platform default decodes those wrongly
    or raises, which would surface as a parser fault rather than the encoding fault it is.
    """
    if not PLAN_PATH.is_file():
        pytest.fail(
            f"the falsification plan is missing at {PLAN_PATH.relative_to(REPO_ROOT)}; "
            "this guard cannot establish which detectors are registered"
        )
    return PLAN_PATH.read_text(encoding="utf-8")


def _parse_registered_detectors() -> list[str]:
    """Return every detector module named by a Detection line, in document order."""
    text = _read_plan()
    detectors: list[str] = []
    for chunk in text.split(_DETECTION_MARKER)[1:]:
        match = _BACKTICKED_PY.search(chunk)
        if match is None:
            preview = " ".join(chunk.split())[:120]
            pytest.fail(
                f"a Detection line names no backticked .py module; the line begins: {preview!r}"
            )
        detectors.append(match.group(1))
    return detectors


def _load_baseline() -> dict[str, object]:
    """Return the parsed ratchet baseline, failing closed when it cannot be read."""
    if not BASELINE_PATH.is_file():
        pytest.fail(
            f"the ratchet baseline is missing at {BASELINE_PATH.relative_to(REPO_ROOT)}; "
            "a detector-existence guard with no baseline cannot distinguish known debt "
            "from new debt, so it fails closed rather than passing vacuously"
        )
    try:
        loaded = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"the ratchet baseline at {BASELINE_PATH.relative_to(REPO_ROOT)} is not valid "
            f"JSON and cannot be trusted to record known debt: {exc}"
        )
    if not isinstance(loaded, dict):
        pytest.fail("the ratchet baseline must be a JSON object")
    return loaded


def _baseline_detectors() -> dict[str, int]:
    """Return a mapping of detector path to falsification-plan item number."""
    baseline = _load_baseline()
    rows = baseline.get("not_yet_built")
    if not isinstance(rows, list):
        pytest.fail("the ratchet baseline needs a 'not_yet_built' list")
    mapping: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict) or "detector" not in row or "item" not in row:
            pytest.fail(
                "every baseline row needs a 'detector' path and an 'item' number; "
                f"this row is missing one or both: {row!r}"
            )
        mapping[str(row["detector"])] = int(row["item"])
    return mapping


def test_plan_registers_the_number_of_detectors_it_claims() -> None:
    """The parser must find ten rows, because the plan says it registers exactly ten."""
    detectors = _parse_registered_detectors()
    assert len(detectors) == EXPECTED_DETECTION_ROWS, (
        f"parsed {len(detectors)} Detection rows from the falsification plan, expected "
        f"{EXPECTED_DETECTION_ROWS}; either the plan changed size or the parser stopped "
        f"matching. Parsed: {detectors}"
    )


def test_every_registered_detector_exists_or_is_recorded_as_debt() -> None:
    """A named detector must exist in the tree, or be listed in the ratchet baseline."""
    baseline = _baseline_detectors()
    undeclared_absences: list[str] = []
    for detector in _parse_registered_detectors():
        if (REPO_ROOT / detector).is_file():
            continue
        if detector in baseline:
            continue
        undeclared_absences.append(detector)
    assert not undeclared_absences, (
        "the falsification plan names detector modules that do not exist and are not "
        "recorded in the ratchet baseline: "
        f"{sorted(undeclared_absences)}. A registered detection that cannot fire is a "
        "coverage claim with nothing behind it. Build the detector; do not add it to the "
        "baseline."
    )


def test_baseline_names_no_detector_that_now_exists() -> None:
    """The ratchet: a detector that has landed must leave the baseline in the same change."""
    landed: list[str] = [
        detector for detector in _baseline_detectors() if (REPO_ROOT / detector).is_file()
    ]
    assert not landed, (
        "these detectors exist in the tree but are still recorded as not-yet-built in "
        f"{BASELINE_PATH.name}: {sorted(landed)}. Remove each landed row from "
        "'not_yet_built'. The baseline only shrinks."
    )


def test_baseline_records_only_rows_the_plan_registers() -> None:
    """A baseline row naming a detector the plan no longer registers is stale debt."""
    registered = set(_parse_registered_detectors())
    unregistered = sorted(set(_baseline_detectors()) - registered)
    assert not unregistered, (
        "the ratchet baseline records detectors that no Detection line in the "
        f"falsification plan names: {unregistered}. Either the plan dropped the row, in "
        "which case drop it here too, or the detector path was edited in one file and not "
        "the other."
    )


def test_baseline_item_numbers_match_the_plan_order() -> None:
    """A baseline row's item number must match the row's position in the ranked list.

    The plan ranks its ten items by operator damage, and the ranking is load-bearing: the
    tickets, the phase reconciliation table and every reference to a numbered item use it. A
    baseline that renumbered silently would misdirect whoever picks the work up.
    """
    detectors = _parse_registered_detectors()
    position_of = {detector: index for index, detector in enumerate(detectors, start=1)}
    mismatches = [
        f"{detector}: baseline says item {item}, plan ranks it {position_of[detector]}"
        for detector, item in _baseline_detectors().items()
        if detector in position_of and position_of[detector] != item
    ]
    assert not mismatches, (
        f"ratchet baseline item numbers disagree with the plan's ranked order: {mismatches}"
    )
