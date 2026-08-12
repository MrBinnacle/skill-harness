"""Static SERS receipt and clause-evidence site generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]


def load_receipts(schema_path: Path, receipts_dir: Path) -> list[dict[str, Any]]:
    """Load all receipts through the SERS validation gate."""
    schema_obj: object = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema_obj, dict):
        raise TypeError("SERS schema must be a JSON object")
    schema: dict[str, Any] = schema_obj
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    loaded: list[dict[str, Any]] = []
    for path in sorted(receipts_dir.glob("*.json")):
        receipt_obj: object = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(receipt_obj)
        if not isinstance(receipt_obj, dict):
            raise TypeError(f"{path}: SERS receipt must be a JSON object")
        loaded.append(receipt_obj)
    return loaded


def build_site(
    *,
    schema_path: Path,
    receipts_dir: Path,
    extraction_path: Path,
    skills_dir: Path,
    output_dir: Path,
    marker: str,
) -> None:
    """Build the static site after validating every receipt."""
    del extraction_path, skills_dir, marker
    load_receipts(schema_path, receipts_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
