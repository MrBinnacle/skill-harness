"""Issue 189: checked-in adjudication records upgrade matching rows to ADJUDICATED.

The records file is the committed per-row output of the preregistered issue-189
adjudication program (receipt vacuity-flag-adjudication-2026-08-09). These tests
pin the loader's fail-closed contract and the end-to-end join through
``derive_vacuity_policy``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_harness.extractor.vacuity_policy import (
    clause_context_sha256,
    default_adjudication_records_path,
    derive_vacuity_policy,
    load_adjudication_records,
    load_calibration_receipt,
)

_REPO = Path(__file__).resolve().parents[2]
_RECORDS = _REPO / "docs" / "calibration" / "vacuity-adjudication-2026-08-09.jsonl"
_RECEIPT_ID = "vacuity-flag-adjudication-2026-08-09"


def test_committed_records_load_complete_and_unique() -> None:
    records = load_adjudication_records(_RECORDS)
    assert len(records) == 402  # 282 census + 120 recall draw, no duplicates
    kinds = {r.adjudicated_vacuity_kind for r in records.values()}
    assert kinds <= {"weak_directive", "not_a_directive", "testable_directive", "undecided"}
    assert all(r.adjudication_receipt == _RECEIPT_ID for r in records.values())


def test_default_path_resolves_to_committed_records() -> None:
    records = load_adjudication_records(default_adjudication_records_path())
    assert len(records) == 402


def test_missing_file_returns_empty_mapping(tmp_path: Path) -> None:
    assert load_adjudication_records(tmp_path / "absent.jsonl") == {}


def test_loader_fails_closed_on_bad_kind(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps(
            {
                "source_sha256": "a" * 64,
                "clause_context_sha256": "b" * 64,
                "adjudicated_vacuity_kind": "clean_directive",  # panel label, not policy kind
                "adjudication_receipt": "r1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="adjudicated_vacuity_kind invalid"):
        load_adjudication_records(bad)


def test_loader_fails_closed_on_duplicate_key(tmp_path: Path) -> None:
    row = json.dumps(
        {
            "source_sha256": "a" * 64,
            "clause_context_sha256": "b" * 64,
            "adjudicated_vacuity_kind": "not_a_directive",
            "adjudication_receipt": "r1",
        }
    )
    dup = tmp_path / "dup.jsonl"
    dup.write_text(row + "\n" + row + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate adjudication join key"):
        load_adjudication_records(dup)


def test_record_upgrade_requires_exact_identity() -> None:
    """A committed record only upgrades a row carrying the exact join identity.

    The committed clause texts are not reproduced in this repo, so the positive
    path is pinned with a synthetic identity and the negative path with a real
    committed record against a non-matching clause text.
    """
    receipt = load_calibration_receipt()
    _, record = next(iter(sorted(load_adjudication_records(_RECORDS).items())))
    mismatched = derive_vacuity_policy(
        instrument=receipt.instrument(),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="not_a_directive",
        source_sha256=record.source_sha256,
        clause_text="stand-in text that is not the adjudicated clause",
        adjudication=record,
    )
    assert mismatched.kind_evidence_status == "ADVISORY"
    assert mismatched.adjudicated_vacuity_kind is None

    # Positive path, synthetic identity built the way the records were built:
    clause = "Always do the thing before the other thing."
    synthetic = type(record)(
        source_sha256="c" * 64,
        clause_context_sha256=clause_context_sha256(clause),
        adjudicated_vacuity_kind="testable_directive",
        adjudication_receipt=_RECEIPT_ID,
    )
    upgraded = derive_vacuity_policy(
        instrument=receipt.instrument(),
        vacuity_flag="none",
        predicted_vacuity_kind=None,
        source_sha256="c" * 64,
        clause_text=clause,
        adjudication=synthetic,
    )
    assert upgraded.kind_evidence_status == "ADJUDICATED"
    assert upgraded.adjudicated_vacuity_kind == "testable_directive"
