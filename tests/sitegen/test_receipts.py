"""SERS receipt loading for the static-site generator (#186)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError  # type: ignore[import-untyped]

from skill_harness.sitegen import build_site, load_receipts

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = _REPO_ROOT / "docs" / "sers" / "sers.schema.json"
_VALID = _REPO_ROOT / "docs" / "sers" / "receipts" / "double-ceiling-nogo-2026-07-09.json"


def test_load_receipts_validates_and_returns_claims(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "valid.json").write_text(_VALID.read_text(encoding="utf-8"), encoding="utf-8")

    loaded = load_receipts(_SCHEMA, receipts)

    assert [receipt["skill_name"] for receipt in loaded] == ["sqlite-expert"]
    assert loaded[0]["verdict"] == "CANT_TELL_YET"


def test_invalid_receipt_refuses_before_rendering(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    invalid = json.loads(_VALID.read_text(encoding="utf-8"))
    del invalid["cost"]["standing_tokens"]
    (receipts / "invalid.json").write_text(json.dumps(invalid), encoding="utf-8")
    output = tmp_path / "site"

    with pytest.raises(ValidationError, match="standing_tokens"):
        build_site(
            schema_path=_SCHEMA,
            receipts_dir=receipts,
            extraction_path=tmp_path / "extraction.jsonl",
            skills_dir=tmp_path / "skills",
            output_dir=output,
            marker="test-build",
        )

    assert not output.exists()
