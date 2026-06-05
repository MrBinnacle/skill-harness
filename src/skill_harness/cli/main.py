"""CLI entry point. Mirrors PRD §18.

Every `run` subcommand defaults to --dry-run; `--execute` is required to
perform writes or LLM calls (per CLAUDE.md "Pipeline safety").
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from skill_harness.extractor import (
    ExtractionError,
    ExtractionResult,
    extract_skill,
)
from skill_harness.storage.context import StorageContext

_console = Console()


@click.group()
@click.version_option(package_name="skill-harness")
def cli() -> None:
    """Skill Harness — clause-ablation differential testing."""


@cli.group()
def skill() -> None:
    """Skill artifact operations (PRD §18)."""


@skill.command("init")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help="Persist extracted skill + clauses to evidence DB (default: dry-run, no writes).",
)
@click.option(
    "--evidence-db",
    type=click.Path(path_type=Path),
    default=Path("./evidence.db"),
    show_default=True,
    help="Path to evidence DB (only used with --execute).",
)
@click.option(
    "--runtime-db",
    type=click.Path(path_type=Path),
    default=Path("./runtime.db"),
    show_default=True,
    help="Path to runtime DB (only used with --execute).",
)
def skill_init(path: Path, execute: bool, evidence_db: Path, runtime_db: Path) -> None:
    """Import a skill artifact and extract atomic clauses.

    Calls the Anthropic API to extract behavioral clauses from PATH.
    Without --execute, prints a dry-run summary and exits (no DB writes).
    With --execute, persists skill + clauses to the evidence DB.
    """
    try:
        if execute:
            with StorageContext(evidence_db, runtime_db) as ctx:
                result = extract_skill(path, evidence_conn=ctx.evidence_conn)
            _print_result(result, persisted=True)
        else:
            result = extract_skill(path, evidence_conn=None)
            _print_result(result, persisted=False)
    except ExtractionError as exc:
        raise click.ClickException(str(exc)) from exc


def _print_result(result: ExtractionResult, *, persisted: bool) -> None:
    """Print a Rich table summarising the extraction result."""
    mode = "[green]PERSISTED[/]" if persisted else "[yellow]DRY-RUN[/]"
    _console.print(f"\n{mode} — skill [bold]{result.name}[/] ({result.skill_id[:12]}…)")
    _console.print(f"  source: {result.source_path}")
    _console.print(f"  sha256: {result.source_sha256[:16]}…")
    _console.print(f"  clauses extracted: {len(result.clauses)}")

    table = Table(title="Extracted Clauses", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Axis", style="cyan", min_width=16)
    table.add_column("Cmp", width=8)
    table.add_column("Tier", width=5)
    table.add_column("Vacuity", width=10)
    table.add_column("FC", width=4, justify="center")
    table.add_column("Clause text", min_width=30, max_width=60)

    for clause in result.clauses:
        fc_mark = "Y" if clause.falsifying_case is not None else "-"
        vacuity_display = "none" if clause.vacuity_flag == "none" else "sem-vac"
        table.add_row(
            str(clause.clause_index),
            clause.axis,
            clause.comparator,
            str(clause.oracle_tier),
            vacuity_display,
            fc_mark,
            clause.clause_text[:80],
        )

    _console.print(table)
    if not persisted:
        _console.print("[yellow]Dry-run: no data written. Use --execute to persist.[/]")


@skill.command("clauses")
@click.argument("skill_id")
def skill_clauses(skill_id: str) -> None:
    """Inspect the extracted clause inventory for a skill."""
    _ = skill_id
    raise click.ClickException("not implemented — see PRD §7")


@cli.group()
def run() -> None:
    """Evaluation runs (PRD §18)."""


@run.command("ablation")
@click.argument("skill_id")
@click.option("--clause", "clause_id", help="Clause to ablate (default: all).")
@click.option("--execute", is_flag=True, help="Execute (default is --dry-run estimation).")
def run_ablation(skill_id: str, clause_id: str | None, execute: bool) -> None:
    """Execute single-clause ablation. Defaults to dry-run cost estimate."""
    _ = (skill_id, clause_id, execute)
    raise click.ClickException("not implemented — see PRD §4")


@run.command("evaluate-skill")
@click.argument("skill_id")
@click.option("--execute", is_flag=True, help="Execute (default is --dry-run estimation).")
def run_evaluate_skill(skill_id: str, execute: bool) -> None:
    """Run the full evaluation suite against a skill."""
    _ = (skill_id, execute)
    raise click.ClickException("not implemented — see PRD §16")


@cli.command("diff")
@click.argument("skill_a")
@click.argument("skill_b")
def diff_skill(skill_a: str, skill_b: str) -> None:
    """Compare two skill revisions."""
    _ = (skill_a, skill_b)
    raise click.ClickException("not implemented — see PRD §16")


@cli.command("freeze")
@click.argument("sample_id")
def freeze(sample_id: str) -> None:
    """Promote a failure into the frozen regression suite."""
    _ = sample_id
    raise click.ClickException("not implemented — see PRD §9")


if __name__ == "__main__":  # pragma: no cover
    cli()
