"""RED tests for Pydantic write-model field validators.

Written before the validators exist — these must FAIL until models.py is implemented.
Per TDD discipline: RED first, then GREEN.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# These imports will fail until models.py exists.
from skill_harness.storage.models import (
    ClauseWrite,
    SkillWrite,
)


class TestNulByteRejection:
    """NUL byte (\x00) must be rejected by field_validator on all text fields."""

    def test_skill_name_rejects_nul(self) -> None:
        with pytest.raises(ValidationError, match="control"):
            SkillWrite(
                skill_id="abc123",
                name="bad\x00name",
                source_path="/tmp/skill.md",
                source_sha256="a" * 64,
                imported_at="2026-06-04T00:00:00.000Z",
            )

    def test_skill_source_path_rejects_nul(self) -> None:
        with pytest.raises(ValidationError, match="control"):
            SkillWrite(
                skill_id="abc123",
                name="good name",
                source_path="/tmp/\x00bad.md",
                source_sha256="a" * 64,
                imported_at="2026-06-04T00:00:00.000Z",
            )


class TestC0ControlRejection:
    """Non-printable C0 control chars (0x00-0x1F except \t, \n, \r) must be rejected."""

    def test_skill_name_rejects_bell(self) -> None:
        # \x07 BEL — not tab/LF/CR, must be rejected
        with pytest.raises(ValidationError, match="control"):
            SkillWrite(
                skill_id="abc123",
                name="bad\x07name",
                source_path="/tmp/skill.md",
                source_sha256="a" * 64,
                imported_at="2026-06-04T00:00:00.000Z",
            )

    def test_skill_name_rejects_escape(self) -> None:
        # \x1B ESC — forbidden
        with pytest.raises(ValidationError, match="control"):
            SkillWrite(
                skill_id="abc123",
                name="bad\x1bname",
                source_path="/tmp/skill.md",
                source_sha256="a" * 64,
                imported_at="2026-06-04T00:00:00.000Z",
            )

    def test_skill_name_allows_tab(self) -> None:
        # \t (0x09) is permitted
        obj = SkillWrite(
            skill_id="abc123",
            name="tab\there",
            source_path="/tmp/skill.md",
            source_sha256="a" * 64,
            imported_at="2026-06-04T00:00:00.000Z",
        )
        assert "\t" in obj.name

    def test_skill_name_allows_newline(self) -> None:
        # \n (0x0A) is permitted
        obj = SkillWrite(
            skill_id="abc123",
            name="line1\nline2",
            source_path="/tmp/skill.md",
            source_sha256="a" * 64,
            imported_at="2026-06-04T00:00:00.000Z",
        )
        assert "\n" in obj.name

    def test_skill_name_allows_cr(self) -> None:
        # \r (0x0D) is permitted
        obj = SkillWrite(
            skill_id="abc123",
            name="cr\rhere",
            source_path="/tmp/skill.md",
            source_sha256="a" * 64,
            imported_at="2026-06-04T00:00:00.000Z",
        )
        assert "\r" in obj.name


class TestOversizeRejection:
    """Size caps: output_text 256 KB; clause_text 64 KB."""

    def test_oracle_verdict_output_text_oversize_rejected(self) -> None:
        # OracleVerdictWrite doesn't have output_text directly; that's on SampleWrite.
        # But ClauseWrite has clause_text.
        big = "x" * (64 * 1024 + 1)
        with pytest.raises(ValidationError, match="size"):
            ClauseWrite(
                clause_id="c1",
                skill_id="s1",
                clause_index=0,
                rendering_index=0,
                clause_text=big,
                axis="citation_support",
                comparator="increase",
                oracle_tier=1,
                vacuity_flag="none",
                falsifying_case_schema_sha256=None,
                created_at="2026-06-04T00:00:00.000Z",
            )

    def test_clause_text_at_limit_ok(self) -> None:
        at_limit = "x" * (64 * 1024)
        obj = ClauseWrite(
            clause_id="c1",
            skill_id="s1",
            clause_index=0,
            rendering_index=0,
            clause_text=at_limit,
            axis="citation_support",
            comparator="increase",
            oracle_tier=1,
            vacuity_flag="none",
            falsifying_case_schema_sha256=None,
            created_at="2026-06-04T00:00:00.000Z",
        )
        assert len(obj.clause_text) == 64 * 1024


class TestFrozenStrict:
    """Models must be frozen (immutable) and strict."""

    def test_skill_write_is_frozen(self) -> None:
        obj = SkillWrite(
            skill_id="abc123",
            name="good name",
            source_path="/tmp/skill.md",
            source_sha256="a" * 64,
            imported_at="2026-06-04T00:00:00.000Z",
        )
        with pytest.raises(Exception):
            obj.name = "changed"

    def test_skill_write_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            SkillWrite(  # type: ignore[call-arg]
                skill_id="abc123",
                name="good name",
                source_path="/tmp/skill.md",
                source_sha256="a" * 64,
                imported_at="2026-06-04T00:00:00.000Z",
                extra_field="oops",
            )
