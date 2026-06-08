"""Tests for the ``skill init`` CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from skill_harness.cli.main import cli
from skill_harness.extractor.errors import ExtractorClaudeError, MalformedSkillError
from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractionResult,
    FalsifyingCaseSchema,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(name: str = "test-skill", n_clauses: int = 3) -> ExtractionResult:
    sha = "a" * 64
    fc = FalsifyingCaseSchema(
        input_population_spec="Factual prompts",
        expected_directional_pair="A beats B",
        min_reproducibility=0.8,
    )
    clauses = [
        ExtractedClause(
            clause_index=i,
            clause_text=f"Clause {i} text.",
            axis="specificity",
            comparator="increase",
            oracle_tier=1,
            vacuity_flag="none",
            falsifying_case=fc,
        )
        for i in range(n_clauses)
    ]
    return ExtractionResult(
        skill_id=sha,
        name=name,
        source_path="/tmp/SKILL.md",
        source_sha256=sha,
        clauses=clauses,
        raw_frontmatter={"name": name},
    )


def _skill_file(tmp_path: Path, body: str = "# Instructions\nBe specific.\n") -> Path:
    p = tmp_path / "SKILL.md"
    p.write_text(f"---\nname: my-skill\n---\n\n{body}", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# skill init — dry-run (default)
# ---------------------------------------------------------------------------


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_dry_run_exits_zero(mock_extract: Any, tmp_path: Path) -> None:
    mock_extract.return_value = _make_result()
    runner = CliRunner()

    result = runner.invoke(cli, ["skill", "init", str(_skill_file(tmp_path))])

    assert result.exit_code == 0, result.output


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_dry_run_prints_summary(mock_extract: Any, tmp_path: Path) -> None:
    mock_extract.return_value = _make_result(n_clauses=5)
    runner = CliRunner()

    result = runner.invoke(cli, ["skill", "init", str(_skill_file(tmp_path))])

    assert "5" in result.output or "clauses" in result.output.lower()


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_dry_run_shows_dry_run_message(mock_extract: Any, tmp_path: Path) -> None:
    mock_extract.return_value = _make_result()
    runner = CliRunner()

    result = runner.invoke(cli, ["skill", "init", str(_skill_file(tmp_path))])

    # Should mention dry-run somewhere
    assert "dry" in result.output.lower() or "execute" in result.output.lower()


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_dry_run_calls_extract_with_no_conn(mock_extract: Any, tmp_path: Path) -> None:
    """Without --execute, extract_skill must be called with evidence_conn=None."""
    mock_extract.return_value = _make_result()
    runner = CliRunner()

    runner.invoke(cli, ["skill", "init", str(_skill_file(tmp_path))])

    mock_extract.assert_called_once()
    _, kwargs = mock_extract.call_args
    assert kwargs.get("evidence_conn") is None


# ---------------------------------------------------------------------------
# skill init — --execute flag
# ---------------------------------------------------------------------------


@patch("skill_harness.cli.main.StorageContext")
@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_execute_calls_extract_with_conn(
    mock_extract: Any,
    mock_ctx_cls: Any,
    tmp_path: Path,
) -> None:
    """With --execute, extract_skill must be called with a real evidence_conn."""
    mock_result = _make_result()
    mock_extract.return_value = mock_result
    mock_ctx = mock_ctx_cls.return_value.__enter__.return_value
    mock_ctx.evidence_conn = object()  # sentinel

    runner = CliRunner()
    skill_path = _skill_file(tmp_path)
    result = runner.invoke(
        cli,
        ["skill", "init", "--execute", str(skill_path)],
    )

    assert result.exit_code == 0, result.output
    mock_extract.assert_called_once()
    _, kwargs = mock_extract.call_args
    assert kwargs.get("evidence_conn") is mock_ctx.evidence_conn


# ---------------------------------------------------------------------------
# skill init — error handling
# ---------------------------------------------------------------------------


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_malformed_exits_nonzero(mock_extract: Any, tmp_path: Path) -> None:
    mock_extract.side_effect = MalformedSkillError("empty body")
    runner = CliRunner()

    result = runner.invoke(cli, ["skill", "init", str(_skill_file(tmp_path))])

    assert result.exit_code != 0


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_claude_error_exits_nonzero(mock_extract: Any, tmp_path: Path) -> None:
    mock_extract.side_effect = ExtractorClaudeError("API failure")
    runner = CliRunner()

    result = runner.invoke(cli, ["skill", "init", str(_skill_file(tmp_path))])

    assert result.exit_code != 0


def test_skill_init_missing_file_exits_nonzero(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["skill", "init", str(tmp_path / "nonexistent.md")])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# skill init — existing stubs not broken
# ---------------------------------------------------------------------------


def test_skill_clauses_placeholder_message() -> None:
    """MN3: skill clauses emits a v0.2 placeholder message with exit 0 (not a crash)."""
    runner = CliRunner()
    result = runner.invoke(cli, ["skill", "clauses", "some-skill-id"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output.lower()
    assert "v0.2" in result.output


def test_skill_clauses_legend_in_output() -> None:
    """Item 5: skill clauses output must include a legend explaining the three load-bearing columns.

    axis, oracle_tier, and vacuity_flag must be explained in the footer so a
    first-time reader is not left with opaque column names.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["skill", "clauses", "some-skill-id"])
    assert result.exit_code == 0
    output = result.output.lower()
    # Each of the three load-bearing columns must be explained in the legend footer
    assert "axis" in output
    assert "oracle_tier" in output or "oracle tier" in output
    assert "vacuity_flag" in output or "vacuity flag" in output
    # The legend must explain what these mean, not just name them
    assert "tier-1" in output or "tier 1" in output or "mechanical" in output
