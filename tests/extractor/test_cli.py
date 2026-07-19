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


@patch("skill_harness.cli.main.StorageContext")
@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_comparator_unspecified_exits_cleanly(
    mock_extract: Any, mock_ctx_cls: Any, tmp_path: Path
) -> None:
    """C4b RED: persisting a comparator_unspecified clause via 'skill init --execute'
    raises a raw ValueError from extract_skill (extractor/pipeline.py
    _to_db_comparator's documented abort-the-whole-persist doctrine). The CLI's
    `except ExtractionError` does not catch ValueError, so today it propagates as an
    uncaught traceback instead of a clean click.ClickException. Data correctness is
    unaffected (the abort-on-persist behavior is correct and untouched) -- this is
    CLI UX only.
    """
    mock_extract.side_effect = ValueError(
        "comparator_unspecified cannot be stored: the clause direction is undefined. "
        "Mark the clause as semantic_vacuous_pending_review instead."
    )
    mock_ctx = mock_ctx_cls.return_value.__enter__.return_value
    mock_ctx.evidence_conn = object()

    runner = CliRunner()
    result = runner.invoke(
        cli, ["skill", "init", "--execute", str(_skill_file(tmp_path))]
    )

    assert result.exit_code != 0
    assert not isinstance(result.exception, ValueError), (
        "C4b: a raw ValueError must be caught and converted to click.ClickException "
        f"(clean CLI error), not propagate uncaught. Got: {result.exception!r}"
    )


# ---------------------------------------------------------------------------
# skill init — existing stubs not broken
# ---------------------------------------------------------------------------


def _seed_skill_with_clause(evidence_db: Path, skill_id: str, clause_text: str) -> None:
    from skill_harness.storage.migrations import open_evidence
    from skill_harness.storage.models import ClauseWrite, SkillWrite
    from skill_harness.storage.repositories.evidence.clauses import insert_clause
    from skill_harness.storage.repositories.evidence.skills import insert_skill
    from skill_harness.storage.transaction import writer_transaction

    ev = open_evidence(evidence_db)
    try:
        with writer_transaction(ev):
            insert_skill(
                ev,
                SkillWrite(
                    skill_id=skill_id,
                    name="clauses-test-skill",
                    source_path="/tmp/SKILL.md",
                    source_sha256="c" * 64,
                    imported_at="2026-06-06T00:00:00.000000+00:00",
                ),
            )
            insert_clause(
                ev,
                ClauseWrite(
                    clause_id="clause-cli-001",
                    skill_id=skill_id,
                    clause_index=0,
                    rendering_index=0,
                    clause_text=clause_text,
                    axis="specificity",
                    comparator="increase",
                    oracle_tier=1,
                    vacuity_flag="none",
                    falsifying_case_schema_sha256="abc123",
                    created_at="2026-06-06T00:00:00.000000+00:00",
                ),
            )
    finally:
        ev.close()


def test_skill_clauses_not_imported_message(tmp_path: Path) -> None:
    """D5 (S49 hostile review): skill clauses is now a real read-only query, not
    the v0.2 stub. With no evidence.db, it must print a clean 'not imported'
    message and exit 0 (not a crash), matching the 'skill init'/'run ablation
    --dry-run' zero-state convention.
    """
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "skill",
            "clauses",
            "some-skill-id",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        ],
    )
    assert result.exit_code == 0
    assert "not imported" in result.output.lower()
    assert "skill init" in result.output.lower()


def test_skill_clauses_malformed_db_gives_clean_error(tmp_path: Path) -> None:
    """F-5 (S55 hostile review): evidence.db PRESENT but malformed (missing the
    'clauses' table) used to escape the previously-narrow ``except BootstrapError``
    as a raw sqlite3.OperationalError traceback -- BootstrapError only covers an
    ABSENT file. A present-but-unreadable DB must get the same clean CLI hint as
    the absent-DB / not-imported case, not crash.
    """
    # A23 Sec.3 / structural ban: use the sanctioned open_db() helper, not a raw
    # sqlite3 connect call (open_db() applies no migrations itself, so it's safe
    # here to get an unmigrated file -- same pattern as test_smoke.py's
    # test_migration_apply_is_atomic).
    from skill_harness.storage.migrations import open_db

    evidence_db = tmp_path / "evidence.db"
    # A real sqlite3 file that exists but was never migrated -- no 'clauses' table.
    conn = open_db(evidence_db)
    conn.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    conn.close()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["skill", "clauses", "some-skill-id", "--evidence-db", str(evidence_db)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "not imported" in result.output.lower() or "malformed" in result.output.lower()


def test_skill_clauses_no_clauses_for_skill_message(tmp_path: Path) -> None:
    """DB exists but has no clauses for the requested skill_id -> clean message,
    not an empty/crashed table."""
    evidence_db = tmp_path / "evidence.db"
    _seed_skill_with_clause(evidence_db, "other-skill-id", "Some clause.")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["skill", "clauses", "some-skill-id", "--evidence-db", str(evidence_db)],
    )
    assert result.exit_code == 0
    assert "no clauses found" in result.output.lower()


def test_skill_clauses_prints_real_clause_table(tmp_path: Path) -> None:
    """D5: with a real evidence.db, skill clauses must print the actual clause
    inventory (verbatim clause text), not a placeholder."""
    evidence_db = tmp_path / "evidence.db"
    skill_id = "skill-with-clauses"
    real_text = "Always cite the source document when making a factual claim."
    _seed_skill_with_clause(evidence_db, skill_id, real_text)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["skill", "clauses", skill_id, "--evidence-db", str(evidence_db)],
        env={"COLUMNS": "200"},  # wide terminal so Rich doesn't wrap the clause text
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert real_text[:30] in result.output
    assert "specificity" in result.output
    assert "not yet implemented" not in result.output.lower()


def test_skill_clauses_legend_in_output(tmp_path: Path) -> None:
    """Item 5: skill clauses output must include a legend explaining the three load-bearing columns.

    axis, oracle_tier, and vacuity_flag must be explained in the footer so a
    first-time reader is not left with opaque column names.
    """
    evidence_db = tmp_path / "evidence.db"
    skill_id = "skill-legend-test"
    _seed_skill_with_clause(evidence_db, skill_id, "Be concise.")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["skill", "clauses", skill_id, "--evidence-db", str(evidence_db)],
    )
    assert result.exit_code == 0
    output = result.output.lower()
    # Each of the three load-bearing columns must be explained in the legend footer
    assert "axis" in output
    assert "oracle_tier" in output or "oracle tier" in output
    assert "vacuity_flag" in output or "vacuity flag" in output
    # The legend must explain what these mean, not just name them
    assert "tier-1" in output or "tier 1" in output or "mechanical" in output
