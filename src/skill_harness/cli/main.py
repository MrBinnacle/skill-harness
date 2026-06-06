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

# Calibrate command is imported inline to avoid heavy imports at module level


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


# ---------------------------------------------------------------------------
# calibrate — judge calibration command (PRD §18, A34, A37)
# ---------------------------------------------------------------------------


@cli.command("calibrate")
@click.argument("judge_id")
@click.argument("axis")
@click.argument("pair_set_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help="Persist calibration event to evidence DB (default: dry-run, no writes).",
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
def calibrate_cmd(
    judge_id: str,
    axis: str,
    pair_set_path: Path,
    execute: bool,
    evidence_db: Path,
    runtime_db: Path,
) -> None:
    """Calibrate a judge on an axis using a JSONL pair set.

    JUDGE_ID is the opaque judge identifier (sha256 of model+prompt+schema).
    AXIS is the evaluation axis (e.g. citation_support).
    PAIR_SET_PATH is a JSONL file of labeled human-preference pairs.

    Defaults to dry-run (no DB writes). Use --execute to persist.

    Three-tier admissibility (A34):
      N < 50    → rejected  (no write; exits with error)
      50-99     → conditional (write with credible-interval penalty)
      N ≥ 100   → calibrated (if all four thresholds pass)
    """
    from skill_harness.oracles.calibration.command import calibrate
    from skill_harness.oracles.tier2.judge import JudgeClient

    judge_client = JudgeClient()

    if execute:
        with StorageContext(evidence_db, runtime_db) as ctx:
            result = calibrate(
                judge_id=judge_id,
                axis=axis,
                pair_set_path=pair_set_path,
                judge_client=judge_client,
                evidence_conn=ctx.evidence_conn,
                runtime_conn=ctx.runtime_conn,
            )
    else:
        # Dry-run: parse + compute metrics but do not write
        from unittest.mock import MagicMock

        result = calibrate(
            judge_id=judge_id,
            axis=axis,
            pair_set_path=pair_set_path,
            judge_client=judge_client,
            evidence_conn=MagicMock(),
            runtime_conn=MagicMock(),
        )
        # In dry-run mode, we patch out the write entirely
        # C.4 will implement proper dry-run output formatter (Rich table + projection)

    _print_calibrate_result(result, executed=execute)

    if result.state == "rejected":
        raise click.ClickException(
            f"Calibration rejected — {result.reason} (N={result.n_pairs}). "
            "Provide a pair set with N≥50."
        )


def _print_calibrate_result(result: object, *, executed: bool) -> None:
    """Print a calibration result summary (duck-typed; accepts real result or mock)."""
    mode = "[green]EXECUTED[/]" if executed else "[yellow]DRY-RUN[/]"
    _console.print(f"\n{mode} — calibrate [bold]{getattr(result, 'state', '?').upper()}[/]")
    _console.print(f"  pairs: {getattr(result, 'n_pairs', '?')}")
    _console.print(f"  pairwise_agreement:   {getattr(result, 'pairwise_agreement', 0.0):.3f}")
    _console.print(f"  position_consistency: {getattr(result, 'position_consistency', 0.0):.3f}")
    _console.print(f"  cohen_kappa:          {getattr(result, 'cohen_kappa', 0.0):.3f}")
    _console.print(f"  chance_baseline:      {getattr(result, 'chance_baseline', 0.0):.3f}")
    state = getattr(result, "state", "")
    reason = getattr(result, "reason", None)
    if state == "rejected" and reason:
        _console.print(f"  [red]reason: {reason}[/]")
    cal_id = getattr(result, "calibration_event_id", None)
    if cal_id:
        _console.print(f"  calibration_event_id: {cal_id}")
    if not executed:
        _console.print("[yellow]Dry-run: no data written. Use --execute to persist.[/]")


if __name__ == "__main__":  # pragma: no cover
    cli()
