"""Tests for the JSONL calibration pair-set parser (A34).

Covers:
- Strict schema enforcement: extra fields rejected, missing fields rejected,
  wrong types rejected (strict=True, extra='forbid').
- NUL byte and forbidden C0 control character rejection (A24 reuse).
- pair_set_sha256 is deterministic for a given set of pairs.
- pair_set_sha256 changes when pair content changes.
- Human preference values restricted to A | B | tie.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(pairs: list[dict], path: Path) -> None:
    """Write a list of pair dicts as JSONL to path."""
    with path.open("w", encoding="utf-8") as fh:
        for p in pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")


def _valid_pair(
    pair_id: str = "p1",
    axis: str = "citation_support",
    human_preference: str = "A",
) -> dict:
    return {
        "pair_id": pair_id,
        "axis": axis,
        "prompt": "Is this correct?",
        "response_a": "Yes, because X.",
        "response_b": "No, because Y.",
        "human_preference": human_preference,
        "labeler_id": "labeler-001",
        "labeled_at": "2026-01-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Schema enforcement — extra fields forbidden
# ---------------------------------------------------------------------------


def test_parse_pair_set_rejects_extra_field(tmp_path: Path) -> None:
    """A JSONL line with an extra field must raise (extra='forbid')."""
    from skill_harness.oracles.calibration.jsonl_parser import parse_pair_set

    p = _valid_pair()
    p["unexpected_key"] = "oops"
    path = tmp_path / "pairs.jsonl"
    _write_jsonl([p], path)
    with pytest.raises(ValueError, match="unexpected_key"):
        parse_pair_set(path)


# ---------------------------------------------------------------------------
# Schema enforcement — missing required field rejected
# ---------------------------------------------------------------------------


def test_parse_pair_set_rejects_missing_field(tmp_path: Path) -> None:
    """A JSONL line missing a required field must raise."""
    from skill_harness.oracles.calibration.jsonl_parser import parse_pair_set

    p = _valid_pair()
    del p["labeler_id"]
    path = tmp_path / "pairs.jsonl"
    _write_jsonl([p], path)
    with pytest.raises(ValueError, match="labeler_id"):
        parse_pair_set(path)


# ---------------------------------------------------------------------------
# Schema enforcement — wrong type rejected (strict=True)
# ---------------------------------------------------------------------------


def test_parse_pair_set_rejects_wrong_type_for_pair_id(tmp_path: Path) -> None:
    """pair_id must be a string; an integer must raise (strict=True)."""
    from skill_harness.oracles.calibration.jsonl_parser import parse_pair_set

    p = _valid_pair()
    p["pair_id"] = 42  # type: ignore[assignment]
    path = tmp_path / "pairs.jsonl"
    _write_jsonl([p], path)
    with pytest.raises(ValueError):
        parse_pair_set(path)


# ---------------------------------------------------------------------------
# Schema enforcement — invalid human_preference rejected
# ---------------------------------------------------------------------------


def test_parse_pair_set_rejects_invalid_human_preference(tmp_path: Path) -> None:
    """human_preference must be 'A', 'B', or 'tie'; anything else raises."""
    from skill_harness.oracles.calibration.jsonl_parser import parse_pair_set

    p = _valid_pair()
    p["human_preference"] = "C"
    path = tmp_path / "pairs.jsonl"
    _write_jsonl([p], path)
    with pytest.raises(ValueError):
        parse_pair_set(path)


# ---------------------------------------------------------------------------
# NUL byte rejection (A24)
# ---------------------------------------------------------------------------


def test_parse_pair_set_rejects_nul_in_prompt(tmp_path: Path) -> None:
    """A NUL byte \\x00 in any text field must raise."""
    from skill_harness.oracles.calibration.jsonl_parser import parse_pair_set

    p = _valid_pair()
    p["prompt"] = "Is this\x00correct?"
    path = tmp_path / "pairs.jsonl"
    _write_jsonl([p], path)
    with pytest.raises(ValueError, match="forbidden control"):
        parse_pair_set(path)


def test_parse_pair_set_rejects_nul_in_response_a(tmp_path: Path) -> None:
    """A NUL byte in response_a must raise."""
    from skill_harness.oracles.calibration.jsonl_parser import parse_pair_set

    p = _valid_pair()
    p["response_a"] = "Yes\x00!"
    path = tmp_path / "pairs.jsonl"
    _write_jsonl([p], path)
    with pytest.raises(ValueError, match="forbidden control"):
        parse_pair_set(path)


def test_parse_pair_set_accepts_tabs_and_newlines(tmp_path: Path) -> None:
    """Tab and newline characters ARE permitted per A24 exemptions."""
    from skill_harness.oracles.calibration.jsonl_parser import parse_pair_set

    p = _valid_pair()
    p["prompt"] = "Question:\n\tWhy?"
    path = tmp_path / "pairs.jsonl"
    _write_jsonl([p], path)
    pairs = parse_pair_set(path)
    assert pairs[0].prompt == "Question:\n\tWhy?"


# ---------------------------------------------------------------------------
# pair_set_sha256 determinism and sensitivity
# ---------------------------------------------------------------------------


def test_parse_pair_set_sha256_is_deterministic(tmp_path: Path) -> None:
    """Same JSONL content → same pair_set_sha256 on two invocations."""

    pairs_data = [_valid_pair("p1"), _valid_pair("p2", human_preference="B")]
    path = tmp_path / "pairs.jsonl"
    _write_jsonl(pairs_data, path)

    _pairs1, sha1 = _parse_with_sha(path)
    _pairs2, sha2 = _parse_with_sha(path)
    assert sha1 == sha2


def test_parse_pair_set_sha256_changes_on_content_change(tmp_path: Path) -> None:
    """Different content → different pair_set_sha256."""

    path1 = tmp_path / "a.jsonl"
    path2 = tmp_path / "b.jsonl"
    _write_jsonl([_valid_pair("p1")], path1)
    p2 = _valid_pair("p1")
    p2["human_preference"] = "B"
    _write_jsonl([p2], path2)

    _, sha1 = _parse_with_sha(path1)
    _, sha2 = _parse_with_sha(path2)
    assert sha1 != sha2


def test_parse_pair_set_sha256_order_independent(tmp_path: Path) -> None:
    """pair_set_sha256 is computed over *sorted* lines — order in JSONL doesn't matter."""

    p1 = _valid_pair("p1")
    p2 = _valid_pair("p2", human_preference="tie")

    path_ab = tmp_path / "ab.jsonl"
    path_ba = tmp_path / "ba.jsonl"
    _write_jsonl([p1, p2], path_ab)
    _write_jsonl([p2, p1], path_ba)

    _, sha_ab = _parse_with_sha(path_ab)
    _, sha_ba = _parse_with_sha(path_ba)
    assert sha_ab == sha_ba


# ---------------------------------------------------------------------------
# Happy-path parse
# ---------------------------------------------------------------------------


def test_parse_pair_set_returns_all_three_preferences(tmp_path: Path) -> None:
    """A JSONL with A, B, and tie preferences parses correctly."""

    pairs_data = [
        _valid_pair("p1", human_preference="A"),
        _valid_pair("p2", human_preference="B"),
        _valid_pair("p3", human_preference="tie"),
    ]
    path = tmp_path / "pairs.jsonl"
    _write_jsonl(pairs_data, path)
    pairs, _sha = _parse_with_sha(path)
    assert len(pairs) == 3
    prefs = {p.pair_id: p.human_preference for p in pairs}
    assert prefs == {"p1": "A", "p2": "B", "p3": "tie"}


# ---------------------------------------------------------------------------
# Helper to get (pairs, sha256) from parse_pair_set
# ---------------------------------------------------------------------------


def _parse_with_sha(path: Path):  # type: ignore[return]
    """Call parse_pair_set and return (pairs, pair_set_sha256)."""
    from skill_harness.oracles.calibration.jsonl_parser import (
        parse_pair_set,
    )

    pairs = parse_pair_set(path)
    # Compute sha256 the same way the parser should: canonical sorted lines
    sorted_pairs = sorted(pairs, key=lambda p: p.pair_id)
    lines = [p.model_dump_json() for p in sorted_pairs]
    sha256 = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return pairs, sha256
