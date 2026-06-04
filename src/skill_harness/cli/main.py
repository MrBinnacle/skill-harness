"""CLI entry point. Mirrors PRD §18.

Every `run` subcommand defaults to --dry-run; `--execute` is required to
perform writes or LLM calls (per CLAUDE.md "Pipeline safety").
"""

from __future__ import annotations

import click


@click.group()
@click.version_option(package_name="skill-harness")
def cli() -> None:
    """Skill Harness — clause-ablation differential testing."""


@cli.group()
def skill() -> None:
    """Skill artifact operations (PRD §18)."""


@skill.command("init")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
def skill_init(path: str) -> None:
    """Import a skill artifact and extract atomic clauses."""
    _ = path  # consumed by future implementation (PRD §7)
    raise click.ClickException("not implemented — see PRD §7")


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
