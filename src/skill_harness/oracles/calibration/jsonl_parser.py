"""JSONL calibration pair-set parser (A34).

``parse_pair_set(path)`` reads a JSONL file of 8-field calibration pairs,
validates each line with Pydantic strict + extra='forbid', applies A24
control-character validation, and returns the parsed list.

``pair_set_sha256`` is computed over canonical-serialized sorted-by-pair_id
JSONL bytes so the content hash is deterministic regardless of line order.

Schema (A34 verbatim):
    pair_id          str
    axis             str
    prompt           str
    response_a       str
    response_b       str
    human_preference Literal["A", "B", "tie"]
    labeler_id       str
    labeled_at       str  (ISO8601; stored as str)
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

# ---------------------------------------------------------------------------
# Forbidden control-character pattern (A24 discipline, reuse from models.py)
# ---------------------------------------------------------------------------

_FORBIDDEN_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _check_text(value: str, field_name: str = "value") -> str:
    """Reject NUL bytes and forbidden C0 control characters.

    Permits \\t (0x09), \\n (0x0A), \\r (0x0D) as legitimate whitespace.
    """
    if _FORBIDDEN_CTRL.search(value):
        raise ValueError(
            f"{field_name}: contains forbidden control characters "
            "(NUL or C0 0x00-0x1F excluding \\t, \\n, \\r)"
        )
    return value


# ---------------------------------------------------------------------------
# CalibrationPair Pydantic model
# ---------------------------------------------------------------------------


class CalibrationPair(BaseModel):
    """Strict Pydantic model for a single calibration pair line (A34)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    pair_id: str
    axis: str
    prompt: str
    response_a: str
    response_b: str
    human_preference: Literal["A", "B", "tie"]
    labeler_id: str
    labeled_at: str  # ISO8601; stored as str per A34 spec

    @field_validator(
        "pair_id", "axis", "prompt", "response_a", "response_b", "labeler_id", "labeled_at"
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)


# ---------------------------------------------------------------------------
# parse_pair_set
# ---------------------------------------------------------------------------


def parse_pair_set(path: Path) -> list[CalibrationPair]:
    """Parse a JSONL calibration pair-set file.

    Each line is validated against ``CalibrationPair`` (strict=True,
    extra='forbid').  Any validation error raises ``ValueError`` with
    context about the failing line and field.

    Returns the list of ``CalibrationPair`` objects in file order.
    Call ``compute_pair_set_sha256(pairs)`` separately to get the content
    hash over canonical-sorted lines.

    Raises:
        ValueError: if any line fails Pydantic validation or contains
                    forbidden control characters.
        FileNotFoundError: if ``path`` does not exist.
        UnicodeDecodeError: if the file is not valid UTF-8.
    """
    raw = path.read_text(encoding="utf-8")
    pairs: list[CalibrationPair] = []
    for lineno, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {lineno}: invalid JSON — {exc}") from exc
        try:
            pair = CalibrationPair.model_validate(data)
        except Exception as exc:
            raise ValueError(f"line {lineno}: {exc}") from exc
        pairs.append(pair)
    return pairs


def compute_pair_set_sha256(pairs: list[CalibrationPair]) -> str:
    """Compute a deterministic SHA-256 over canonical-serialized sorted pairs.

    Pairs are sorted by pair_id, then each is serialized via
    ``model_dump_json()`` (Pydantic's canonical JSON serializer).
    The sorted serialized lines are joined with '\\n' and hashed.

    This produces the same hash regardless of the order pairs appear
    in the JSONL file (per A34: 'pair_set_sha256 computed over
    canonical-serialized sorted lines').
    """
    sorted_pairs = sorted(pairs, key=lambda p: p.pair_id)
    lines = [p.model_dump_json() for p in sorted_pairs]
    content = "\n".join(lines)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
