"""S2 (hostile review): untrusted clause_text / system_text rendered through a
markup-enabled Rich Console must not be interpretable as Rich markup.

_sanitize_clause_text() (A51) only ever guarded against NUL/control characters
-- it never escaped Rich's `[tag]...[/tag]` markup syntax, which uses ordinary
printable ASCII brackets. A hostile SKILL.md clause body containing
`[bold red]...[/]` is interpreted by Console.print()/Table at render time: the
tag's enclosed text is silently swallowed from the output (or, with real ANSI
color support, forges terminal styling). This file proves the swallowing with
CliRunner (non-tty output still goes through markup resolution even though
color codes are stripped), and pins each of the three render paths named in
the finding: `skill clauses` (the one call site that WAS wired to the old
sanitizer), `skill init` dry-run summary (_print_result, unwired), and
`run ablation --show-rendered` (system_text, unwired).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from skill_harness.cli.main import _sanitize_clause_text, cli
from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractionResult,
    FalsifyingCaseSchema,
)

_INJECTED = "[bold red]INJECTED[/bold red]"


def _make_result_with_clause_text(clause_text: str) -> ExtractionResult:
    sha = "a" * 64
    fc = FalsifyingCaseSchema(
        input_population_spec="Factual prompts",
        expected_directional_pair="A beats B",
        min_reproducibility=0.8,
    )
    return ExtractionResult(
        skill_id=sha,
        name="test-skill",
        source_path="/tmp/SKILL.md",
        source_sha256=sha,
        clauses=[
            ExtractedClause(
                clause_index=0,
                clause_text=clause_text,
                axis="specificity",
                comparator="increase",
                oracle_tier=1,
                vacuity_flag="none",
                falsifying_case=fc,
            )
        ],
        raw_frontmatter={"name": "test-skill"},
        extractor_model="claude-opus-5",
    )


def _skill_file(tmp_path: Path, body: str = "# Instructions\nBe specific.\n") -> Path:
    p = tmp_path / "SKILL.md"
    p.write_text(f"---\nname: my-skill\n---\n\n{body}", encoding="utf-8")
    return p


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


# ---------------------------------------------------------------------------
# Unit level: the sanitizer itself must escape markup, not just control chars.
# ---------------------------------------------------------------------------


def test_sanitize_clause_text_escapes_rich_markup() -> None:
    """The output must be Rich-*escaped* (backslash before the bracket), not a
    raw passthrough that merely happens to still contain the substring --
    passthrough also contains '[bold red]' literally right up until Console
    interprets it as a tag and swallows it. Assert the actual escape marker
    rich.markup.escape() inserts, not just substring presence.
    """
    from rich.markup import escape

    out = _sanitize_clause_text(_INJECTED)
    assert escape("[bold red]") in out, (
        f"markup was not escaped (rich.markup.escape() marker absent): {out!r}"
    )
    assert "\\[bold red]" in out, f"expected an escaped bracket, got: {out!r}"


def test_sanitize_clause_text_still_rejects_control_chars() -> None:
    """Existing A51 control-char guard must not regress."""
    import pytest

    with pytest.raises(AssertionError):
        _sanitize_clause_text("bad\x07bell")


# ---------------------------------------------------------------------------
# skill clauses — the ALREADY-wired call site (still vulnerable pre-fix: the
# old sanitizer guarded control chars only, never markup).
# ---------------------------------------------------------------------------


def test_skill_clauses_does_not_interpret_markup_in_clause_text(tmp_path: Path) -> None:
    evidence_db = tmp_path / "evidence.db"
    skill_id = "skill-with-markup"
    _seed_skill_with_clause(evidence_db, skill_id, _INJECTED)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["skill", "clauses", skill_id, "--evidence-db", str(evidence_db)],
        env={"COLUMNS": "200"},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "[bold red]" in result.output, (
        f"Rich markup was interpreted (tag swallowed) instead of shown literally:\n{result.output}"
    )


# ---------------------------------------------------------------------------
# skill init (dry-run) — _print_result, previously entirely unwired.
# ---------------------------------------------------------------------------


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_does_not_interpret_markup_in_clause_text(
    mock_extract: Any, tmp_path: Path
) -> None:
    mock_extract.return_value = _make_result_with_clause_text(_INJECTED)
    runner = CliRunner()

    result = runner.invoke(
        cli, ["skill", "init", str(_skill_file(tmp_path))], env={"COLUMNS": "200"}
    )

    assert result.exit_code == 0, result.output
    assert "[bold red]" in result.output, (
        f"Rich markup was interpreted (tag swallowed) instead of shown literally:\n{result.output}"
    )


# ---------------------------------------------------------------------------
# run ablation --show-rendered — system_text, previously entirely unwired.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F-1 (S55 hostile review): skill name rendered raw at two more sites --
# _print_result's mode/name header (skill init) and skill_audit's header line
# + Structure findings table (name-charset finding embeds the raw name via
# repr()).
# ---------------------------------------------------------------------------


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_does_not_interpret_markup_in_skill_name(
    mock_extract: Any, tmp_path: Path
) -> None:
    sha = "a" * 64
    fc = FalsifyingCaseSchema(
        input_population_spec="Factual prompts",
        expected_directional_pair="A beats B",
        min_reproducibility=0.8,
    )
    mock_extract.return_value = ExtractionResult(
        skill_id=sha,
        name=_INJECTED,
        source_path="/tmp/SKILL.md",
        source_sha256=sha,
        clauses=[
            ExtractedClause(
                clause_index=0,
                clause_text="Be specific.",
                axis="specificity",
                comparator="increase",
                oracle_tier=1,
                vacuity_flag="none",
                falsifying_case=fc,
            )
        ],
        raw_frontmatter={"name": "test-skill"},
        extractor_model="claude-opus-5",
    )
    runner = CliRunner()

    result = runner.invoke(
        cli, ["skill", "init", str(_skill_file(tmp_path))], env={"COLUMNS": "200"}
    )

    assert result.exit_code == 0, result.output
    assert "[bold red]" in result.output, (
        f"Rich markup was interpreted (tag swallowed) instead of shown literally:\n{result.output}"
    )


def test_skill_audit_does_not_interpret_markup_in_skill_name(tmp_path: Path) -> None:
    """A name failing the charset check flows both as report.name (header line)
    and inside the name-charset finding's message (via repr()) into the
    Structure findings table -- both render paths must escape it.
    """
    p = tmp_path / "SKILL.md"
    p.write_text(
        f"---\nname: {_INJECTED}\ndescription: use when testing things\n---\n\nBody text.\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["skill", "audit", str(p)], env={"COLUMNS": "200"})

    assert result.exit_code == 0, result.output
    assert "[bold red]" in result.output, (
        f"Rich markup was interpreted (tag swallowed) instead of shown literally:\n{result.output}"
    )


def test_show_rendered_does_not_interpret_markup_in_system_text() -> None:
    from skill_harness.ablation.operator import ABLATION_OPERATOR_VERSION

    mock_conditions = {
        "full": {"system_text": f"BASE\n{_INJECTED}", "system_blocks": []},
        "ablated_0": {"system_text": "BASE\n[ABLATED]", "system_blocks": []},
        "null": {"system_text": "BASE", "system_blocks": []},
    }

    runner = CliRunner()
    with patch(
        "skill_harness.cli.main._render_conditions_for_clause",
        return_value=(mock_conditions, ABLATION_OPERATOR_VERSION),
    ):
        result = runner.invoke(
            cli,
            ["run", "ablation", "skill-abc", "--show-rendered", "clause-001"],
            env={"COLUMNS": "200", "ANTHROPIC_API_KEY": "sk-test-dummy"},
        )

    assert "[bold red]" in result.output, (
        f"Rich markup was interpreted (tag swallowed) instead of shown literally:\n{result.output}"
    )
