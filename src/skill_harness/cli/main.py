"""CLI entry point. Mirrors PRD §18.

Every `run` subcommand defaults to --dry-run; `--execute` is required to
perform writes or LLM calls (see docs/INVARIANTS.md #2 "Pipeline safety").
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.markup import escape as _escape_markup
from rich.table import Table

from skill_harness.aggregation import aggregate_skill
from skill_harness.aggregation.verdict import ValueClass
from skill_harness.extractor import (
    ExtractionError,
    ExtractionResult,
    MalformedSkillError,
    extract_skill,
)
from skill_harness.ratification import check_execute_ratification
from skill_harness.storage.context import StorageContext
from skill_harness.storage.recovery import find_resumable_run_for_skill

_console = Console()

# Calibrate command is imported inline to avoid heavy imports at module level


def _ensure_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 at CLI entry (#321).

    On Windows, a default console (cp1252 or another ANSI code page) leaves
    sys.stdout/sys.stderr unable to encode the non-ASCII characters this
    module's reports use (e.g. U+2192 RIGHTWARDS ARROW), and Rich's write
    raises an unhandled UnicodeEncodeError mid-report. Reconfiguring the
    streams here -- once, at the group callback that is every subcommand's
    entry point -- fixes every print site across the CLI package (non-ASCII
    report text is not confined to one file) rather than one Console
    construction.

    errors="replace" substitutes rather than raising on any residual gap; no
    report vocabulary changes. Guarded with getattr because a stream without
    .reconfigure (e.g. a plain non-TextIOWrapper test double) is left alone
    rather than raising a new error while fixing this one.
    """
    for _stream in (sys.stdout, sys.stderr):
        _reconfigure = getattr(_stream, "reconfigure", None)
        if _reconfigure is not None:
            _reconfigure(encoding="utf-8", errors="replace")


def _resolve_harness_version() -> str:
    """Resolve the harness version used to stamp reports (A54 spec).

    Prefers installed package metadata. On an uninstalled source tree the lookup
    raises ``PackageNotFoundError``; the fallback then reads the package's own
    ``__version__`` rather than a per-site hardcoded literal (which was two minors
    stale at v0.2.0). ``__version__`` still hand-syncs with pyproject, but this
    collapses two drift-prone sites to that one source. See
    tests/test_harness_version_fallback.py.
    """
    import importlib.metadata

    try:
        return importlib.metadata.version("skill-harness")
    except importlib.metadata.PackageNotFoundError:
        from skill_harness import __version__

        return __version__


# ---------------------------------------------------------------------------
# Sentinel exceptions for run ablation error paths (D.3)
# ---------------------------------------------------------------------------


class _DailyCapExceededError(Exception):
    """Raised when the trailing-24h daily spend cap is exceeded (D.3 --daily-cap error path).

    Distinct from BudgetAbortedError (which is per-run --max-usd) so the CLI
    can name the correct offending flag in its error message.
    """

    def __init__(self, spent: float, cap: float) -> None:
        super().__init__(f"Daily spend cap exceeded: ${spent:.4f} spent vs --daily-cap ${cap:.2f}")
        self.spent = spent
        self.cap = cap


class _IncompleteRunWarning(Exception):
    """Raised when a bare re-run detects an incomplete prior run for this skill_id.

    The CLI must surface the resumable run_id so the operator can use --resume.
    Never triggers a silent fresh-start (A52 double-spend protection).
    """

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Incomplete prior run detected: {run_id!r}")
        self.run_id = run_id


@click.group()
@click.version_option(package_name="skill-harness")
def cli() -> None:
    """Skill Harness — clause-ablation differential testing."""

    _ensure_utf8_streams()


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
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "Append full ExtractionResult as one JSONL line (dry-run or --execute). "
        "Refuses if the file already has a row for the same source sha."
    ),
)
def skill_init(
    path: Path,
    execute: bool,
    evidence_db: Path,
    runtime_db: Path,
    out_path: Path | None,
) -> None:
    """Import a skill artifact and extract atomic clauses.

    Calls the Anthropic API to extract behavioral clauses from PATH.
    Without --execute, prints a dry-run summary and exits (no DB writes).
    With --execute, persists skill + clauses to the evidence DB.
    Optional --out writes the full extraction JSONL for skill audit --extraction.
    """
    from skill_harness.extractor.clause_evidence import (
        SameShaExtractionRowError,
        append_extraction_result,
    )

    try:
        if execute:
            with StorageContext(evidence_db, runtime_db) as ctx:
                result = extract_skill(path, evidence_conn=ctx.evidence_conn)
            _print_result(result, persisted=True)
        else:
            result = extract_skill(path, evidence_conn=None)
            _print_result(result, persisted=False)
        if out_path is not None:
            append_extraction_result(out_path, result)
    except SameShaExtractionRowError as exc:
        raise click.ClickException(str(exc)) from exc
    except (ExtractionError, ValueError) as exc:
        # C4b: extract_skill (--execute path) raises a raw ValueError when a clause
        # persists as comparator_unspecified (extractor/pipeline.py _to_db_comparator's
        # documented abort-the-whole-persist doctrine). That abort behavior is correct
        # and untouched -- this only gives it a clean CLI surface instead of a raw
        # traceback. Merged with ExtractionError (R-1, S55 hostile review): the two
        # clauses were byte-identical bodies.
        raise click.ClickException(str(exc)) from exc


def _print_result(result: ExtractionResult, *, persisted: bool) -> None:
    """Print a Rich table summarising the extraction result."""
    mode = "[green]PERSISTED[/]" if persisted else "[yellow]DRY-RUN[/]"
    _console.print(
        f"\n{mode} — skill [bold]{_sanitize_clause_text(result.name, max_len=None)}[/]"
        f" ({result.skill_id[:12]}…)"
    )
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
            _sanitize_clause_text(clause.clause_text, max_len=80),
        )

    _console.print(table)
    _console.print(_SKILL_CLAUSES_LEGEND)

    # M2: warn about Tier-1 axes with no registered scorer (TEST-ARCH-2)
    try:
        from skill_harness.oracles.tier1.axis_registry import AxisScoreability, classify_axis

        for clause in result.clauses:
            # Asks the axis registry directly (#117) rather than membership-testing
            # the scorer dict: same verdict, same no-normalisation rule as the
            # runner's pre-sampling gate, and it does not import the metric modules
            # (and so tiktoken) just to print a warning.
            if (
                clause.oracle_tier == 1
                and classify_axis(clause.axis) is AxisScoreability.UNSCOREABLE
            ):
                _console.print(
                    f"[yellow][!] axis {clause.axis!r} has no registered Tier-1 scorer;"
                    f" will return UNMEASURED at run ablation.[/]"
                )
    except Exception:  # noqa: S110
        pass  # never crash skill init on a warning

    if not persisted:
        _console.print("[yellow]Dry-run: no data written. Use --execute to persist.[/]")


_SKILL_CLAUSES_LEGEND = """\
Column legend:
  axis         — the metric being asserted by the clause \
(e.g. verbosity, citation_presence_per_flag).
  oracle_tier  — Tier-1: mechanical/deterministic scorer; \
Tier-2: human-calibrated judge; Tier-3: real-world consequence.
  vacuity_flag — none: clause is testable; \
mechanical_vacuous: no metric exists for this axis; \
semantic_vacuous_pending_review: extractor judged clause un-falsifiable.
Note: vacuity kind and reason are not stored in the DB; they live in the \
extraction output (skill init --out) and render via skill audit --extraction."""


@skill.command("audit")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit 1 if any warning is found (for CI gates).",
)
@click.option(
    "--extraction",
    "extraction_path",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "JSONL from skill init --out; join on source_sha256 for clause evidence "
        "(zero-power; no DB)."
    ),
)
@click.pass_context
def skill_audit(
    ctx: click.Context,
    path: Path,
    strict: bool,
    extraction_path: Path | None,
) -> None:
    """Offline preflight of a skill artifact — no API key, no DB, no cost.

    Structural lint against Anthropic's published authoring spec, plus an
    evaluability preflight: which axes a paid evaluation could mechanically
    measure today, and which claims would honestly come back UNMEASURED.
    Optional --extraction joins extraction JSONL for clause-evidence (still no DB).
    """
    from skill_harness.preflight import audit_skill_artifact

    try:
        report = audit_skill_artifact(path)
    except MalformedSkillError as exc:
        raise click.ClickException(str(exc)) from exc

    _console.print("\n[bold]OFFLINE AUDIT[/] — no API calls, no cost")
    _console.print(f"  skill:  [bold]{_sanitize_clause_text(report.name, max_len=None)}[/]")
    _console.print(f"  source: {report.source_path}")
    _console.print(f"  sha256: {report.source_sha256[:16]}…")
    _console.print(
        f"  body:   {report.body_lines} lines / {report.body_words} words · "
        f"frontmatter keys: {', '.join(report.frontmatter_keys) or '(none)'}"
    )

    table = Table(title="Structure (Anthropic authoring spec)", show_lines=False)
    table.add_column("Level", width=6)
    table.add_column("Check", style="cyan", min_width=18)
    table.add_column("Finding", min_width=40)
    level_style = {"pass": "[green]PASS[/]", "warn": "[yellow]WARN[/]", "info": "[dim]INFO[/]"}
    for finding in report.findings:
        # F-1 (S55 hostile review): finding.message can embed an untrusted frontmatter
        # value verbatim (e.g. name-charset's `{fm_name!r}`) -- repr() escapes quotes/
        # control chars but not Rich markup brackets. Escape at this render site, same
        # helper as every other untrusted-text render path in this module.
        table.add_row(
            level_style[finding.level],
            finding.code,
            _sanitize_clause_text(finding.message, max_len=None),
        )
    _console.print(table)

    _console.print("[bold]Evaluability preflight[/] — what a paid run could measure today:")
    _console.print(
        f"  Tier-1 mechanical axes: [cyan]{', '.join(report.measurable_axes)}[/] "
        "(style-shaped only)."
    )
    _console.print(
        "  Behavior-shaped claims (correctness, tool use, outcomes): no mechanical"
        " instrument in v0.1 → the recorded state would be [bold]UNMEASURED[/], not an"
        " estimate."
    )
    _console.print(
        "  Judge-graded axes: require a calibrated (judge, axis) pair — none exists"
        " in a fresh install → UNMEASURED until you run `calibrate`."
    )
    # Cost figures sit beside evaluability — never a standalone quoteable block.
    # Mechanical only: arithmetic on text, not a measure of skill effect.
    lo, hi = report.standing_cost_calibration_range
    factor = report.standing_cost_calibration_factor
    if report.standing_cost_raw is None:
        _console.print(
            "  Standing cost (mechanical): [yellow]UNMEASURED[/] — frontmatter could not"
            " be parsed well enough to count the router listing line"
            " (see standing-cost-unparseable)."
        )
    else:
        _console.print(
            f"  Standing cost (mechanical): raw {report.standing_cost_raw} tokens · "
            f"calibrated {report.standing_cost_calibrated} tokens "
            f"(x{factor}, "
            f"measured range {lo}-{hi}) -- "
            "router listing line (name + description) charged every turn; "
            "0 when disable-model-invocation keeps the skill unlisted."
        )
    if report.fired_cost_raw is None:
        _console.print(
            "  Fired cost (mechanical): [yellow]UNMEASURED[/] — skill body could not be tokenized."
        )
    else:
        _console.print(
            f"  Fired cost (mechanical): raw {report.fired_cost_raw} tokens · "
            f"calibrated {report.fired_cost_calibrated} tokens "
            f"(x{factor}, measured range {lo}-{hi}) -- "
            "skill body charged when the skill runs and its body is read."
        )
    if report.aux_cost_raw is None:
        _console.print(
            "  Aux cost (mechanical): [yellow]UNMEASURED[/] — progressive-disclosure"
            " documentation beside the skill could not be read"
            " (see aux-cost-unreadable)."
        )
    else:
        _console.print(
            f"  Aux cost (mechanical): raw {report.aux_cost_raw} tokens · "
            f"calibrated {report.aux_cost_calibrated} tokens "
            f"(x{factor}, measured range {lo}-{hi}) -- "
            "other documentation files beside the skill (progressive disclosure); "
            "0 when the skill directory has none."
        )
    _console.print(
        f"\nSummary: {report.pass_count} pass · {report.warn_count} warn — "
        "UNMEASURED is a recorded state, not a failure (docs/concepts/why-unmeasured.md)."
    )
    _print_clause_evidence(report.source_sha256, extraction_path)
    if strict and report.warn_count > 0:
        ctx.exit(1)


def _print_clause_evidence(source_sha256: str, extraction_path: Path | None) -> None:
    """Render the clause-evidence section after cost/evaluability (issue #157)."""
    from skill_harness.extractor.clause_evidence import (
        SECTION_TITLE,
        format_instrument_line,
        format_refusal_line,
        format_summary_lines,
        format_unparseable_warning,
        load_clause_evidence,
        no_extraction_outcome,
    )

    if extraction_path is None:
        outcome = no_extraction_outcome()
        _console.print(format_refusal_line(outcome))
        return

    outcome = load_clause_evidence(extraction_path, source_sha256)
    if outcome.kind != "measured":
        _console.print(format_refusal_line(outcome))
        if outcome.unparseable_line_count and outcome.kind != "unreadable_extraction_file":
            _console.print(format_unparseable_warning(outcome.unparseable_line_count))
        return

    assert outcome.measured is not None
    measured = outcome.measured
    _console.print(f"\n[bold]{SECTION_TITLE}[/]")
    _console.print(format_instrument_line(measured.instrument))

    table = Table(
        title="Clauses (scoreable as of current scorer registry)",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Axis", style="cyan", min_width=14)
    table.add_column("Scoreable", width=10, justify="center")
    table.add_column("Vacuity", min_width=12)
    table.add_column("Flag evidence", min_width=16)
    table.add_column("Kind (prediction)", min_width=16)
    table.add_column("Kind evidence", min_width=12)
    table.add_column("Adjudicated", min_width=12)
    table.add_column("Reason", min_width=16, max_width=48)
    table.add_column("FC", width=4, justify="center")

    for row in measured.rows:
        # Raw model prediction only — never decision-ready (#188).
        kind_cell = "-"
        if row.vacuity_kind is not None:
            kind_cell = f"{row.vacuity_kind} (advisory)"
        adj_cell = row.adjudicated_vacuity_kind if row.adjudicated_vacuity_kind is not None else "-"
        reason_cell = "-"
        if row.vacuity_reason is not None:
            reason_cell = _sanitize_clause_text(row.vacuity_reason)
        table.add_row(
            str(row.clause_index),
            _sanitize_clause_text(row.axis, max_len=40),
            "Y" if row.scoreable else "-",
            row.vacuity_flag,
            row.flag_evidence_status,
            kind_cell,
            row.kind_evidence_status,
            adj_cell,
            reason_cell,
            "Y" if row.constructible_fc else "-",
        )
    _console.print(table)
    for line in format_summary_lines(measured.summary):
        _console.print(line)
    if outcome.unparseable_line_count:
        _console.print(format_unparseable_warning(outcome.unparseable_line_count))


@skill.command("clauses")
@click.argument("skill_id")
@click.option(
    "--evidence-db",
    type=click.Path(path_type=Path),
    default=Path("./evidence.db"),
    show_default=True,
    help="Path to evidence DB (read-only; no writes, no API calls).",
)
def skill_clauses(skill_id: str, evidence_db: Path) -> None:
    """Inspect the extracted clause inventory for a skill (read-only).

    D5 (S49 hostile review): 'skill clauses <skill_id>' was advertised by both
    'skill init' (dry-run hints) and 'run ablation --dry-run' as the way to
    inspect per-clause detail, but was an unimplemented stub. This queries
    evidence.db read-only -- the same table 'run ablation --dry-run' already
    reads for its projection table.
    """
    from skill_harness.storage.errors import BootstrapError
    from skill_harness.storage.migrations import open_evidence_readonly

    if not evidence_db.exists():
        _console.print(
            "\n[yellow]skill not imported — run 'skill init <path>' first[/]"
            f"\n[dim]  (evidence.db not found at {evidence_db})[/]"
        )
        return

    db_conn: sqlite3.Connection | None = None
    rows: list[tuple[Any, ...]] = []
    try:
        db_conn = open_evidence_readonly(evidence_db)
        rows = db_conn.execute(
            "SELECT clause_index, axis, comparator, oracle_tier, vacuity_flag, "
            "falsifying_case_schema_sha256, clause_text "
            "FROM clauses WHERE skill_id = ? ORDER BY clause_index",
            (skill_id,),
        ).fetchall()
    except BootstrapError:
        _console.print(
            "\n[yellow]skill not imported — run 'skill init <path>' first[/]"
            f"\n[dim]  (evidence.db not found or skill_id {skill_id!r} not present)[/]"
        )
        return
    except Exception:
        # F-5 (S55 hostile review): BootstrapError only covers an ABSENT evidence.db
        # (already short-circuited above by the .exists() check). A PRESENT but
        # malformed DB (e.g. missing the clauses table -- sqlite3.OperationalError)
        # fell through uncaught here and surfaced as a raw traceback instead of the
        # same clean CLI hint _cmd_dry_run gives for the equivalent zero-state case.
        _console.print(
            "\n[yellow]skill not imported — run 'skill init <path>' first[/]"
            f"\n[dim]  (evidence.db at {evidence_db} is unreadable or malformed)[/]"
        )
        return
    finally:
        if db_conn is not None:
            db_conn.close()

    if not rows:
        _console.print(
            f"\n[yellow]No clauses found for skill {skill_id!r}. "
            "Run 'skill init <path>' to import.[/]"
        )
        return

    table = Table(title=f"Clause Inventory — {skill_id}", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Axis", style="cyan", min_width=14)
    table.add_column("Cmp", width=8)
    table.add_column("Tier", width=5)
    table.add_column("Status", min_width=20)
    table.add_column("Clause text", min_width=30, max_width=60)

    for clause_index, axis, comparator, oracle_tier, vacuity_flag, fc_sha, clause_text in rows:
        status = _clause_status(vacuity_flag, fc_sha)
        table.add_row(
            str(clause_index),
            axis,
            comparator,
            str(oracle_tier),
            status,
            _sanitize_clause_text(clause_text),
        )

    _console.print(table)
    _console.print(_SKILL_CLAUSES_LEGEND)


@skill.command("coverage")
@click.argument("corpus_dir", type=click.Path(exists=True, path_type=Path))
def skill_coverage(corpus_dir: Path) -> None:
    """Report how many skill cards in a directory can be loaded.

    Iterates over immediate subdirectories of CORPUS_DIR, each expected to
    contain a SKILL.md.  Reports how many are constructible (frontmatter
    normalised successfully) and how many are refused (with reasons).
    """
    from skill_harness.subject.inspect_adapter import skill_corpus_coverage

    report = skill_corpus_coverage(corpus_dir)

    _console.print(f"\n[bold]Skill corpus coverage[/] — {corpus_dir}")
    _console.print(f"  Candidates:    {report.candidate_count}")
    _console.print(f"  Constructible: {report.constructible_count}")
    _console.print(f"  Refused:       {report.refused_count}")

    if report.refused:
        table = Table(title="Refused cards", show_lines=True)
        table.add_column("Path", style="cyan", min_width=30)
        table.add_column("Reason", min_width=40)
        for path, reason in report.refused:
            table.add_row(str(path), _sanitize_clause_text(reason, max_len=80))
        _console.print(table)


@cli.group()
def run() -> None:
    """Evaluation runs (PRD §18)."""


@run.command("ablation")
@click.argument("skill_id")
@click.option("--clause", "clause_id", help="Clause to ablate (default: all).")
@click.option("--execute", is_flag=True, help="Execute live ablation run (default is dry-run).")
@click.option(
    "--user-message",
    "user_message",
    default="Review this code for AI-slop patterns and produce a structured flag report.",
    show_default=True,
    help="Task prompt sent to the subject model for every condition sample.",
)
@click.option(
    "--subject-model",
    "subject_model",
    default="claude-sonnet-4-6",
    show_default=True,
    help=(
        "Subject model id. Direct: 'claude-sonnet-4-6' (Anthropic), 'gpt-5.5' (OpenAI), "
        "'o4-mini' (OpenAI o-series). Via OpenRouter: '<provider>/<model>' e.g. "
        "'openai/gpt-5.5', 'anthropic/claude-sonnet-4-6', 'google/gemini-2-pro'. "
        "If only OPENROUTER_API_KEY is set, direct claude-* / gpt-* / o<N>-* models "
        "are auto-routed through OpenRouter with a stderr warning."
    ),
)
@click.option(
    "--max-usd",
    type=float,
    default=5.0,
    show_default=True,
    help="Per-run budget cap in USD. Refused if projected cost exceeds this (A42).",
)
@click.option(
    "--daily-cap",
    type=float,
    default=20.0,
    show_default=True,
    help=(
        "Trailing-24h daily spend cap in USD per runtime.db (A42)."
        " NOTE: scope is per-runtime.db; parallel worktrees with separate"
        " runtime DBs do NOT share the cap."
    ),
)
@click.option(
    "--resume",
    "resume_run_id",
    default=None,
    metavar="RUN_ID",
    help="Resume an incomplete prior run by run_id (A52).",
)
@click.option(
    "--show-rendered",
    "show_rendered_clause_id",
    default=None,
    metavar="CLAUSE_ID",
    help="Print Full/Ablated_k/Null condition text for a clause (A52).",
)
@click.option(
    "--probe-redundancy",
    is_flag=True,
    default=False,
    help=(
        "Probe for redundancy between clauses (reclassify-only; never promotes to PASSED). "
        "Optional; v0.1 shows documentation only."
    ),
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
@click.option(
    "--ratification",
    "ratification_path",
    type=click.Path(path_type=Path),
    default=None,
    metavar="RAT_FILE",
    help=(
        "Path to the RATIFIED row-pick record (docs/ratifications/RAT-NNNN-<slug>.md) "
        "authorizing this spend. Required with --execute (#47 mechanical binding); "
        "ignored on dry-run."
    ),
)
@click.option(
    "--task-family",
    "task_family",
    default=None,
    help=(
        "Task family this run evaluates; must match the ratification record's scope. "
        "Required with --execute; ignored on dry-run."
    ),
)
@click.option(
    "--estimand",
    "estimand",
    default=None,
    help=(
        "Registered estimand name (treatment-policy | hypothetical); must match the "
        "ratification record's scope. Required with --execute; ignored on dry-run."
    ),
)
def run_ablation(
    skill_id: str,
    clause_id: str | None,
    execute: bool,
    user_message: str,
    subject_model: str,
    max_usd: float,
    daily_cap: float,
    resume_run_id: str | None,
    show_rendered_clause_id: str | None,
    probe_redundancy: bool,
    evidence_db: Path,
    runtime_db: Path,
    ratification_path: Path | None,
    task_family: str | None,
    estimand: str | None,
) -> None:
    """Execute single-clause ablation.

    Defaults to dry-run (offline, no API calls, no DB connections). Use
    --execute to perform the live sampling run.

    Reporting honesty (A50): Contribution is labeled as
    'single-clause LOO; lower-bound under redundancy'. Absence of delta is
    not absence of contribution — a clause may contribute jointly with others
    and show no individual signal under LOO ablation.

    --probe-redundancy (optional): triggers a reclassification-only probe for
    inter-clause redundancy. Never promotes a clause to PASSED.

    Exit codes:
      0  — all verdict clauses reached a definitive verdict (PASSED or FAILED)
      2  — one or more clauses are UNMEASURED (underpowered, length-confounded,
             tier2_uncalibrated, etc.)
      1  — hard error (budget exceeded, configuration error, etc.)
    """
    # --show-rendered takes priority (read-only introspection, no API calls)
    if show_rendered_clause_id is not None:
        _cmd_show_rendered(skill_id, show_rendered_clause_id, evidence_db=evidence_db)
        return

    if not execute:
        # DRY-RUN: no writable DB conn, no migration-apply, no client, no API key (A51 ratified)
        # MAY open evidence.db READ-ONLY to enumerate imported clauses (A51 micro-council ruling)
        # Only pass evidence_db if the file actually exists (avoids misleading "not imported"
        # error when the DB simply hasn't been created yet in a fresh checkout).
        effective_evidence_db = evidence_db if evidence_db.exists() else None
        _cmd_dry_run(skill_id, clause_id, max_usd, daily_cap, evidence_db=effective_evidence_db)
        return

    # EXECUTE path — ratification preflight first (#47 mechanical binding,
    # landed by #57): un-ratified spend is refused before any DB connection,
    # client construction, or API-key check. Dry-run above stays ungated.
    decision = check_execute_ratification(
        ratification_path,
        skill_id=skill_id,
        task_family=task_family or "",
        estimand=estimand or "",
        max_usd=max_usd,
    )
    if not decision.allowed:
        raise click.ClickException(
            f"ratification preflight refused --execute [{decision.reason}]: {decision.detail}"
        )

    _cmd_execute(
        skill_id=skill_id,
        clause_id=clause_id,
        user_message=user_message,
        subject_model=subject_model,
        max_usd=max_usd,
        daily_cap=daily_cap,
        resume_run_id=resume_run_id,
        probe_redundancy=probe_redundancy,
        evidence_db=evidence_db,
        runtime_db=runtime_db,
    )


# ---------------------------------------------------------------------------
# D.3 helpers — module-level so tests can patch them by name
# ---------------------------------------------------------------------------


def _clause_status(vacuity_flag: str, falsifying_case_schema_sha256: str | None) -> str:
    """Compute per-clause status for the dry-run projection table (A51, M1).

    Status derives from two fields (write-time, never recomputed):
      - vacuity_flag in ('mechanical_vacuous', 'semantic_vacuous_pending_review')
                                                     → VACUOUS-EXCLUDED
      - vacuity_flag == 'none' and no falsifying case → NO-FALSIFYING-CASE
      - vacuity_flag == 'none' and has falsifying case → TESTABLE
    """
    if vacuity_flag != "none":
        return "VACUOUS-EXCLUDED"
    if falsifying_case_schema_sha256 is None:
        return "NO-FALSIFYING-CASE"
    return "TESTABLE"


def _sanitize_clause_text(text: str, *, max_len: int | None = 60) -> str:
    """Assert NUL/control-free + escape Rich markup for display (A51 output-side
    sanitisation, S2 hostile-review hardening).

    Untrusted clause text and rendered condition text both flow through Rich's
    markup-enabled Console.print()/Table. Without escaping, a hostile SKILL.md
    clause body containing Rich markup ('[red on red]', '[/]') is interpreted
    at print time instead of shown verbatim: the tagged span is silently
    swallowed from the rendered output (or, with real color support, forges
    terminal styling) -- terminal output forgery.

    Raises AssertionError if text contains NUL or ASCII control characters
    (except tab/newline, benign in prose). Escapes Rich markup via
    ``rich.markup.escape()`` so bracketed text renders literally. Truncation
    (when ``max_len`` is given) happens BEFORE escaping, not after: escaping
    can grow the string (inserted backslashes), and truncating an already-
    escaped string risks slicing a `\\[` escape sequence in half, which would
    itself misparse as markup. ``max_len=None`` returns the full escaped text
    (used for system_text, which must stay verbatim, not table-truncated).
    """
    for ch in text:
        cp = ord(ch)
        if cp == 0 or (cp < 0x20 and cp not in (0x09, 0x0A, 0x0D)):
            raise AssertionError(
                f"text contains control character U+{cp:04X} — "
                "refusing to display untrusted content"
            )
    truncated = text[:max_len] if max_len is not None else text
    return _escape_markup(truncated)


def _cmd_dry_run(
    skill_id: str,
    clause_id: str | None,
    max_usd: float,
    daily_cap: float,
    evidence_db: Path | None = None,
) -> None:
    """Dry-run: print A12-(a) projection + real per-clause table (A51 ratified, M1).

    Opens evidence.db READ-ONLY via the council-sanctioned helper to enumerate
    the skill's imported clauses. No API client, no API key, no writes.

    Dry-run invariants (A51 ratification, 2026-06-06):
    - NO writable DB conn, NO migration-apply, NO client, NO API key, NO write.
    - MAY open evidence.db READ-ONLY to enumerate imported clauses.
    - Zero-state default (non-conditional): skill not imported / db missing →
      print 'skill not imported — run skill init <path> first', never crash.
    """
    from skill_harness.ablation.stopping import N_MAX, N_MIN
    from skill_harness.storage.errors import BootstrapError
    from skill_harness.storage.migrations import open_evidence_readonly

    # A12-(a) projection one-liner
    min_calls_per_clause = N_MIN * 3
    max_calls_per_clause = N_MAX * 3
    _console.print(
        f"\n[bold]Projection for skill:[/] {skill_id}"
        f"\n  Sampling schedule: N_min={N_MIN} … N_max={N_MAX} (per clause)"
        f"\n  Calls per clause: {min_calls_per_clause} (min) … {max_calls_per_clause} (max)"
        f"\n  Conditions per clause: Full / Ablated_k / Null"
        f"\n  Per-run cap: ${max_usd:.2f}  ·  Daily cap: ${daily_cap:.2f}"
        "\n  Estimated cache reuse: ~70% on K>=5 skills"
        " (prefix shared; ablated clause renders last per A13)."
    )

    # Per-clause table — columns per D.3 spec
    table = Table(title="Clause Projection", show_lines=True)
    table.add_column("clause#", style="dim", width=8)
    table.add_column("axis", style="cyan", min_width=14)
    table.add_column("conditions", min_width=22)
    table.add_column("N_proj(min..max)", min_width=16)
    table.add_column("est_CI_width", min_width=12)
    table.add_column("status", min_width=20)

    # Attempt to open evidence.db READ-ONLY and enumerate the skill's clauses.
    # Zero-state (non-conditional): DB missing or skill not imported → clean message.
    db_conn: sqlite3.Connection | None = None
    clause_rows: list[dict[str, Any]] = []
    not_imported = False

    if evidence_db is not None:
        try:
            db_conn = open_evidence_readonly(evidence_db)
        except BootstrapError:
            # DB missing — skill not imported yet
            not_imported = True
        except Exception:
            not_imported = True

    if db_conn is not None:
        try:
            # skill_id as parameterised query value (A51 — no string-built SQL)
            query = (
                "SELECT clause_id, clause_index, axis, vacuity_flag, "
                "falsifying_case_schema_sha256 "
                "FROM clauses WHERE skill_id = ? ORDER BY clause_index"
            )
            params: list[Any] = [skill_id]
            if clause_id is not None:
                query = (
                    "SELECT clause_id, clause_index, axis, vacuity_flag, "
                    "falsifying_case_schema_sha256 "
                    "FROM clauses WHERE skill_id = ? AND clause_id = ? ORDER BY clause_index"
                )
                params = [skill_id, clause_id]
            rows = db_conn.execute(query, params).fetchall()
            clause_rows = [
                {
                    "clause_id": r[0],
                    "clause_index": r[1],
                    "axis": r[2],
                    "vacuity_flag": r[3],
                    "falsifying_case_schema_sha256": r[4],
                }
                for r in rows
            ]
        except Exception:
            not_imported = True
        finally:
            db_conn.close()

    if not_imported:
        # Skill not imported: DB missing or BootstrapError (zero-state default, non-conditional)
        _console.print(
            f"\n[yellow]skill not imported — run 'skill init <path>' first[/]"
            f"\n[dim]  (evidence.db not found or skill_id {skill_id!r} not present)[/]"
        )
        _console.print(
            "\n[bold yellow]NO CALLS MADE — re-run with --execute[/]\n"
            "[dim]Use 'skill clauses <skill_id>' to inspect per-clause detail.[/]"
        )
        return

    if clause_rows:
        for row in clause_rows:
            status = _clause_status(row["vacuity_flag"], row["falsifying_case_schema_sha256"])
            table.add_row(
                str(row["clause_index"]),
                row["axis"],
                "Full / Ablated_k / Null",
                f"{N_MIN}..{N_MAX}",
                "~0.55",
                status,
            )
    elif evidence_db is not None:
        # DB found but no clauses: skill may have been imported with no clauses
        _console.print(
            f"\n[yellow]No clauses found for skill {skill_id!r}. "
            "Run 'skill init <path>' to import.[/]"
        )
    else:
        # No --evidence-db provided: generic projection row
        table.add_row(
            "(all)" if clause_id is None else clause_id,
            "—",
            "Full / Ablated_k / Null",
            f"{N_MIN}..{N_MAX}",
            "~0.55",
            "TESTABLE",
        )

    _console.print(table)
    _console.print(
        "\n[bold yellow]NO CALLS MADE — re-run with --execute[/]"
        "\n[dim]Use 'skill clauses <skill_id>' to inspect per-clause detail before running.[/]"
    )


def _cmd_show_rendered(skill_id: str, clause_id: str, evidence_db: Path | None = None) -> None:
    """Print verbatim Full/Ablated_k/Null condition text + ablation_operator_version (A52).

    Delegates to _render_conditions_for_clause() so tests can patch that function.
    Passes evidence_db so real clause_text is loaded (m1 fix).
    """
    try:
        conditions, operator_version = _render_conditions_for_clause(
            skill_id, clause_id, evidence_db=evidence_db
        )
    except Exception as exc:
        raise click.ClickException(f"Could not render conditions for {clause_id!r}: {exc}") from exc

    _console.print(
        f"\n[bold]--show-rendered for clause:[/] {clause_id}"
        f"\n  skill_id: {skill_id}"
        f"\n  ablation_operator_version: [cyan]{operator_version}[/]"
    )

    for condition_name, condition_data in sorted(conditions.items()):
        system_text = condition_data.get("system_text", "")
        _console.print(f"\n[bold underline]{condition_name.upper()}[/]")
        _console.print(_sanitize_clause_text(system_text, max_len=None))


def _render_conditions_for_clause(
    skill_id: str,
    clause_id: str,
    evidence_db: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], str]:
    """Return (conditions_dict, operator_version) for the given clause.

    Loads the real clause_text from evidence.db READ-ONLY (m1 fix) so that
    --show-rendered shows verbatim content rather than a placeholder.

    Falls back to a stand-in only when evidence_db is None (backward-compat
    for tests that patch this function entirely).

    This function is module-level (not inlined) so tests can patch it cleanly.

    :returns: (conditions, ablation_operator_version)
    """
    from skill_harness.ablation.operator import ABLATION_OPERATOR_VERSION, AblationOperator
    from skill_harness.ablation.render import ConditionRenderer
    from skill_harness.storage.migrations import open_evidence_readonly

    operator = AblationOperator()
    renderer = ConditionRenderer(operator=operator)

    # Load real clause_text from evidence.db READ-ONLY (m1)
    clause_text: str | None = None
    if evidence_db is not None:
        db_conn: sqlite3.Connection | None = None
        try:
            db_conn = open_evidence_readonly(evidence_db)
            row = db_conn.execute(
                "SELECT clause_text FROM clauses WHERE clause_id = ?", (clause_id,)
            ).fetchone()
            if row is not None:
                clause_text = row[0]
        except Exception:
            clause_text = None
        finally:
            if db_conn is not None:
                db_conn.close()

    if clause_text is None:
        # Fallback: no DB or clause not found — use placeholder
        clause_text = f"[clause: {clause_id}]"

    conditions = renderer.render_conditions([clause_text], target_clause_index=0)

    return conditions, ABLATION_OPERATOR_VERSION


def _load_user_message_from_run(evidence_conn: sqlite3.Connection, run_id: str) -> str:
    """Load the user_message from runs.config_json for a given run_id (m2 fix).

    Returns the user_message string, or '' if the run does not exist or
    config_json lacks the key.

    Module-level for testability.
    """
    row = evidence_conn.execute(
        "SELECT config_json FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        return ""
    try:
        config = json.loads(row[0])
        return str(config.get("user_message", ""))
    except (json.JSONDecodeError, AttributeError):
        return ""


def _find_incomplete_run_for_execute(
    skill_id: str,
    runtime_db: Path | None = None,
    evidence_db: Path | None = None,
) -> str | None:
    """Return the run_id of an incomplete prior run for skill_id, or None (A52, E.3).

    Used exclusively by `_cmd_execute` bare-rerun guard. Opens both DBs read-only,
    delegates to find_resumable_run_for_skill (storage.recovery, A61).

    Module-level so tests can patch find_resumable_run_for_skill at cli.main scope.
    Returns None when either DB is absent (no prior runs possible).
    """
    from skill_harness.storage.migrations import open_evidence_readonly, open_runtime

    if runtime_db is None or evidence_db is None:
        return None

    rt: sqlite3.Connection | None = None
    ev_ro: sqlite3.Connection | None = None
    try:
        try:
            rt = open_runtime(runtime_db)
        except Exception:
            return None
        try:
            ev_ro = open_evidence_readonly(evidence_db)
        except Exception:  # includes BootstrapError when DB not yet bootstrapped
            # evidence.db not yet created — no runs can exist
            return None
        return find_resumable_run_for_skill(skill_id, evidence_conn_ro=ev_ro, runtime_conn=rt)
    except Exception:
        return None
    finally:
        if ev_ro is not None:
            ev_ro.close()
        if rt is not None:
            rt.close()


def _execute_ablation_run(
    skill_id: str,
    clause_id: str | None,
    subject_model: str,
    user_message: str,
    max_usd: float,
    resume_run_id: str | None,
    evidence_db: Path,
    runtime_db: Path,
    daily_cap: float = 20.0,
) -> list[Any]:
    """Execute the live ablation run and return clause results.

    Module-level so tests can patch it cleanly.
    This wraps AblationRunner.run_ablation() / resume_ablation().

    In v0.1, calling without a properly seeded evidence DB will fail with an FK
    error — that is by design. The operator must run 'skill init' first.
    """
    from skill_harness.ablation.operator import AblationOperator
    from skill_harness.ablation.render import ConditionRenderer
    from skill_harness.ablation.runner import AblationRunner
    from skill_harness.ablation.subject import make_subject_client

    with StorageContext(evidence_db, runtime_db) as ctx:
        operator = AblationOperator()
        renderer = ConditionRenderer(operator=operator)
        subject = make_subject_client(subject_model)
        runner = AblationRunner(
            evidence_conn=ctx.evidence_conn,
            runtime_conn=ctx.runtime_conn,
            subject_client=subject,
            operator=operator,
            renderer=renderer,
        )

        # In v0.1, clauses are loaded from the evidence DB (via skill_id FK).
        clauses = _load_clauses_from_db(ctx, skill_id, clause_id)

        if not clauses:
            raise click.ClickException(
                f"No testable clauses found for skill {skill_id!r}. Run 'skill init <path>' first."
            )

        if resume_run_id is not None:
            # m2: load user_message from runs.config_json (not empty string)
            user_message = _load_user_message_from_run(ctx.evidence_conn, resume_run_id)
            # C5: _load_user_message_from_run returns '' both when resume_run_id
            # doesn't exist in evidence.runs AND when the row exists but
            # config_json is corrupt/lacks the key. Either way, proceeding would
            # silently mix an empty-prompt tail onto samples collected under the
            # real prompt, with the stopping rule aggregating both under one
            # run_id and no record of the mismatch. Refuse instead.
            if not user_message:
                raise click.ClickException(
                    f"Cannot resume run {resume_run_id!r}: no user_message found in "
                    "runs.config_json for this run_id (the run does not exist in "
                    "evidence.db, or its config_json is corrupt/missing the key). "
                    "Refusing to proceed with an empty prompt -- verify --resume "
                    "RUN_ID against evidence.runs and re-run."
                )
            results = runner.resume_ablation(
                run_id=resume_run_id,
                clauses=clauses,
                user_message=user_message,
                max_usd=max_usd,
            )
        else:
            results = runner.run_ablation(
                skill_id=skill_id,
                clauses=clauses,
                user_message=user_message,
                max_usd=max_usd,
            )

    return results


def _load_clauses_from_db(
    ctx: StorageContext,
    skill_id: str,
    clause_id: str | None,
) -> list[Any]:
    """Load ClauseSpec list from the evidence DB for a skill.

    Module-level for testability. Queries evidence.clauses for the skill.
    """
    from skill_harness.ablation.runner import ClauseSpec

    query = """
        SELECT clause_id, clause_text, clause_index, axis, oracle_tier, comparator
        FROM clauses
        WHERE skill_id = ?
    """
    params: list[Any] = [skill_id]

    if clause_id is not None:
        query += " AND clause_id = ?"
        params.append(clause_id)

    query += " ORDER BY clause_index"

    rows = ctx.evidence_conn.execute(query, params).fetchall()
    return [
        ClauseSpec(
            clause_id=row[0],
            clause_text=row[1],
            clause_index=row[2],
            axis=row[3],
            oracle_tier=row[4],
            # Tier-1 clauses require metric_id IS NOT NULL (schema CHECK constraint).
            # Use the axis name as metric_id — the axis IS the registered scorer key.
            metric_id=row[3] if row[4] == 1 else None,
            # A2: persisted directional claim, threaded so delta_to_observation can
            # sign-flip 'decrease' clauses instead of always assuming 'increase'.
            comparator=row[5],
        )
        for row in rows
    ]


def _resolve_subject_model_with_fallback(subject_model: str) -> str:
    """Resolve subject_model against the available API keys; auto-route to OpenRouter
    as fallback. Emit warnings to stderr when a fallback rewrite happens. Raise
    click.ClickException if no usable key is present for the requested model.

    Rules:
    - If subject_model already contains '/' (explicit OpenRouter form): require
      OPENROUTER_API_KEY. Return subject_model unchanged.
    - If subject_model starts with 'claude-': require ANTHROPIC_API_KEY first;
      if absent and OPENROUTER_API_KEY is present, return 'anthropic/' + subject_model
      and emit a stderr warning naming the rewrite + the reason.
    - If subject_model starts with 'gpt-' or matches '^o[0-9]+-': require
      OPENAI_API_KEY first; if absent and OPENROUTER_API_KEY is present, return
      'openai/' + subject_model and emit a stderr warning.
    - If neither the direct key nor OPENROUTER_API_KEY is present for the model
      class, raise click.ClickException with a message naming BOTH env vars the
      operator could set (direct + OpenRouter).
    - If subject_model matches no recognised pattern, raise click.ClickException
      delegating to the factory's own error message.
    """
    import os
    import re

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")

    # Explicit OpenRouter form: 'provider/model'
    if "/" in subject_model:
        if not openrouter_key:
            raise click.ClickException(
                f"Subject model {subject_model!r} requires OPENROUTER_API_KEY (explicit"
                " OpenRouter provider/model form). Set OPENROUTER_API_KEY to proceed."
            )
        return subject_model

    # Anthropic direct: claude-*
    if subject_model.startswith("claude-"):
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            return subject_model
        if openrouter_key:
            rewritten = f"anthropic/{subject_model}"
            click.echo(
                f"Warning: ANTHROPIC_API_KEY not set; routing {subject_model!r} via "
                f"OpenRouter as {rewritten!r}. Set ANTHROPIC_API_KEY to use Anthropic "
                "direct.",
                err=True,
            )
            return rewritten
        raise click.ClickException(
            f"Subject model {subject_model!r} requires ANTHROPIC_API_KEY (Anthropic direct)"
            " or OPENROUTER_API_KEY (OpenRouter fallback). Set one to proceed."
        )

    # OpenAI direct: gpt-* or o<digit>* (o-series).
    # The o-series regex matches the factory's permissive pattern at
    # make_subject_client (subject.py: `model[0] == 'o' and model[1].isdigit()`).
    # Both bare 'o4' and dashed 'o4-mini' are accepted — divergence would route
    # bare names through the unrecognized-model probe and miss the OpenRouter
    # fallback contract.
    is_gpt = subject_model.startswith("gpt-")
    is_o_series = bool(re.match(r"^o[0-9]", subject_model))
    if is_gpt or is_o_series:
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            return subject_model
        if openrouter_key:
            rewritten = f"openai/{subject_model}"
            click.echo(
                f"Warning: OPENAI_API_KEY not set; routing {subject_model!r} via "
                f"OpenRouter as {rewritten!r}. Set OPENAI_API_KEY to use OpenAI "
                "direct.",
                err=True,
            )
            return rewritten
        raise click.ClickException(
            f"Subject model {subject_model!r} requires OPENAI_API_KEY (OpenAI direct)"
            " or OPENROUTER_API_KEY (OpenRouter fallback). Set one to proceed."
        )

    # Unrecognized pattern: delegate to factory for precise error message
    from skill_harness.ablation.subject import make_subject_client

    try:
        make_subject_client(subject_model)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    # If factory succeeded (e.g. future prefix added), trust it and return unchanged.
    return subject_model


def _check_daily_cap(runtime_db: Path, daily_cap: float) -> None:
    """Compute trailing-24h SUM(usd) from runtime.cost_ledger; raise _DailyCapExceededError
    if it would exceed daily_cap (B2 fix, A42).

    Fail-CLOSED discipline (I1): a spend guard must never silently allow a billed run
    when the ledger is unreadable due to a non-absent error.
    - Absent ledger (BootstrapError: DB not yet created) → treat as $0 trailing spend (allow).
      This is the legitimate "no prior spend" case for a fresh install.
    - Any other read error → re-raise so the caller refuses the run. Silently permitting
      a billed run when the ledger is corrupt or inaccessible is the OPPOSITE of conservative.

    Uses a read-only query on the runtime DB (already writable by --execute).
    The since_ts cutoff is 24 hours ago in ISO 8601 UTC.
    """
    from skill_harness.storage.errors import BootstrapError
    from skill_harness.storage.migrations import open_runtime
    from skill_harness.storage.repositories.runtime.cost_ledger import select_cost_ledger_since

    since_ts = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    conn: sqlite3.Connection | None = None
    trailing_spend = 0.0
    try:
        conn = open_runtime(runtime_db)
        rows = select_cost_ledger_since(conn, since_ts)
        trailing_spend = sum(r["usd"] for r in rows)
    except BootstrapError:
        # Ledger absent (DB not yet created) — no prior spend, allow the run.
        trailing_spend = 0.0
    finally:
        if conn is not None:
            conn.close()
    # All other exceptions propagate to the caller (fail-closed: refuse the run).

    if trailing_spend >= daily_cap:
        raise _DailyCapExceededError(trailing_spend, daily_cap)


def _cmd_execute(
    skill_id: str,
    clause_id: str | None,
    user_message: str,
    subject_model: str,
    max_usd: float,
    daily_cap: float,
    resume_run_id: str | None,
    probe_redundancy: bool,
    evidence_db: Path,
    runtime_db: Path,
) -> None:
    """Execute the live ablation run and render the results report.

    Exit codes:
      0 — all verdicts reached (PASSED or FAILED)
      2 — ≥1 UNMEASURED clause
      1 — intentional refusal (budget, double-spend guard, config error)
    Non-zero exit (sys.exit) for UNMEASURED to let callers discriminate without
    raising ClickException (which would add a noisy error message for a non-error
    state).
    """
    from skill_harness.ablation.runner import BudgetAbortedError

    # m3: model-aware API key pre-flight BEFORE any DB write (no orphan run rows)
    resolved_model = _resolve_subject_model_with_fallback(subject_model)

    # B2: daily-cap pre-run check BEFORE any DB write
    try:
        _check_daily_cap(runtime_db, daily_cap)
    except _DailyCapExceededError as exc:
        raise click.ClickException(
            f"Run refused — daily spend cap exceeded."
            f"\n  --daily-cap: ${exc.cap:.2f}  ·  trailing-24h spent: ${exc.spent:.4f}"
            f"\n  Wait until spend rolls off the 24h window or increase --daily-cap."
        ) from exc

    # A52: bare re-run guard — detect incomplete prior run BEFORE opening DB (B1 fix, E.3 refactor)
    # Uses find_resumable_run_for_skill (storage.recovery) directly — shim deleted in E.3.
    if resume_run_id is None:
        incomplete_run_id = _find_incomplete_run_for_execute(
            skill_id, runtime_db=runtime_db, evidence_db=evidence_db
        )
        if incomplete_run_id is not None:
            _console.print(
                f"\n[bold yellow]WARNING:[/] Incomplete prior run detected for skill {skill_id!r}."
                f"\n  Resumable run_id: [bold]{incomplete_run_id}[/]"
                f"\n  Re-run with --resume {incomplete_run_id!r} to continue."
                "\n  Starting a fresh run would discard partial evidence (double-spend risk)."
            )
            sys.exit(1)

    # Resume preview line (A52)
    if resume_run_id is not None:
        _console.print(
            f"\n[bold cyan]Resuming run:[/] {resume_run_id}"
            f"\n  skill_id: {skill_id}"
            "\n  Skipping already-collected samples (A40 idempotency)."
        )

    try:
        clause_results = _execute_ablation_run(
            skill_id=skill_id,
            clause_id=clause_id,
            subject_model=resolved_model,
            user_message=user_message,
            max_usd=max_usd,
            daily_cap=daily_cap,
            resume_run_id=resume_run_id,
            evidence_db=evidence_db,
            runtime_db=runtime_db,
        )
    except BudgetAbortedError as exc:
        raise click.ClickException(
            f"Run aborted — per-run budget exhausted."
            f"\n  --max-usd cap: ${exc.usd_cap:.2f}  ·  spent: ${exc.usd_spent:.4f}"
            f"\n  Increase --max-usd or resume with --resume <run_id>."
        ) from exc
    except _DailyCapExceededError as exc:
        raise click.ClickException(
            f"Run refused — daily spend cap exceeded."
            f"\n  --daily-cap: ${exc.cap:.2f}  ·  trailing-24h spent: ${exc.spent:.4f}"
            f"\n  Wait until spend rolls off the 24h window or increase --daily-cap."
        ) from exc

    _render_ablation_report(clause_results, probe_redundancy=probe_redundancy)

    # M4: caps footer (I4 honesty fix).
    # Labels as caps-only — actual run spend requires the run_id from the runner
    # which is not threaded to _cmd_execute. To audit actual spend, query cost_ledger
    # directly via the runtime DB.
    _console.print(
        f"\n[dim]─ caps only (not spend) ─[/]"
        f"\n  Per-run cap: ${max_usd:.2f} (run)  ·  Daily cap: ${daily_cap:.2f} (day)"
        f"\n  [dim]Audit actual spend: query runtime.cost_ledger for the run_id.[/]"
    )

    # Exit-code contract (A48): 0=all reached, 2=≥1 UNMEASURED
    has_unmeasured = _any_unmeasured(clause_results)
    if has_unmeasured:
        sys.exit(2)


def _is_unmeasured(result: Any) -> bool:
    """Return True iff the clause result is UNMEASURED.

    UNMEASURED is a recorded state, not a verdict: aggregation maps it to the
    CANT_TELL_YET verdict (aggregation/verdict.py, rule B3). The mapping is not
    injective — CONFOUNDED reaches CANT_TELL_YET too — so this predicate answers
    "is this result UNMEASURED", not "does this result reach CANT_TELL_YET".

    UNMEASURED covers:
    - StoppingReason.UNDERPOWERED_NMAX (hit N_MAX without decisive posterior)
    - unmeasured_reason is not None (tier2_uncalibrated, length_confounded)
    - StoppingReason.BUDGET_EXHAUSTED (sampling aborted mid-clause)

    UNMEASURED is NEVER FAILED — this is a core invariant (A48; see docs/INVARIANTS.md #3).
    """
    from skill_harness.ablation.stopping import StoppingReason

    if result.unmeasured_reason is not None:
        return True
    stopping_reason = result.stopping_reason
    return stopping_reason in (
        StoppingReason.UNDERPOWERED_NMAX,
        StoppingReason.BUDGET_EXHAUSTED,
    )


def _any_unmeasured(results: list[Any]) -> bool:
    """Return True if any clause result is UNMEASURED."""
    return any(_is_unmeasured(r) for r in results)


def _render_ablation_report(results: list[Any], *, probe_redundancy: bool = False) -> None:
    """Render the ablation results table + reporting-honesty caveats (A48, A50).

    Verdict rendering (A48):
    - PASSED  → green   "PASSED"
    - FAILED  → red     "FAILED (P(win)≤.05)"
    - UNMEASURED → yellow "UNMEASURED(<subreason>)"

    Contribution label (A50):
    - "single-clause LOO; lower-bound under redundancy"
    - "Absence of delta is not absence of contribution."
    """
    from skill_harness.ablation.stopping import StoppingReason
    from skill_harness.aggregation.status import UnmeasuredSubReason

    table = Table(title="Ablation Results", show_lines=True)
    table.add_column("clause_id", style="dim", min_width=12)
    table.add_column("verdict_id", style="dim", min_width=36)
    table.add_column("verdict", min_width=30)
    table.add_column("N", width=5, justify="right")
    table.add_column("P(win>0.60)", min_width=12)
    table.add_column("contribution", min_width=36)

    has_any_unmeasured = False

    for result in results:
        clause_id = result.clause_id
        # verdict_id: surfaced for `freeze` discoverability (A56).
        # CF-E3-1 (commit 32f3ad4): ClauseResult.verdict_id: str | None is always present.
        verdict_id_str = str(result.verdict_id or "—")
        stopping_reason = result.stopping_reason
        n_samples = result.stop_decision.n_samples
        p_win = result.stop_decision.p_win_rate_exceeds_threshold

        if _is_unmeasured(result):
            has_any_unmeasured = True
            # Which flavour of not-knowing occurred is the reportable content of
            # UNMEASURED. Derive it from the stopping reason when the runner did
            # not supply one; do NOT fall back to a single default, which would
            # report a budget-exhausted clause as underpowered.
            if result.unmeasured_reason is not None:
                subreason = result.unmeasured_reason
            elif stopping_reason == StoppingReason.BUDGET_EXHAUSTED:
                subreason = UnmeasuredSubReason.BUDGET_EXHAUSTED.value
            else:
                subreason = UnmeasuredSubReason.UNDERPOWERED.value
            verdict_str = f"[yellow]UNMEASURED({subreason})[/]"
            contrib_str = "[dim]—[/]"
        elif stopping_reason == StoppingReason.PASSED:
            verdict_str = "[green]PASSED[/]"
            contrib_str = "single-clause LOO; lower-bound under redundancy"
        elif stopping_reason == StoppingReason.FAILED:
            verdict_str = "[red]FAILED (P(win)≤.05)[/]"
            contrib_str = "single-clause LOO; lower-bound under redundancy"
        else:
            # Defensive: treat any other reason as UNMEASURED
            has_any_unmeasured = True
            verdict_str = f"[yellow]UNMEASURED({stopping_reason})[/]"
            contrib_str = "[dim]—[/]"

        table.add_row(
            clause_id,
            verdict_id_str,
            verdict_str,
            str(n_samples),
            f"{p_win:.3f}",
            contrib_str,
        )

    _console.print(table)

    # Reporting-honesty caveats (A50)
    _console.print(
        "\n[bold]Contribution note:[/]"
        "\n  Contribution is measured as single-clause LOO (leave-one-out)."
        "\n  This is a lower-bound under redundancy: a clause may contribute jointly"
        "\n  with other clauses and show no individual signal under LOO ablation."
        "\n  [italic]Absence of delta is not absence of contribution.[/]"
    )

    if has_any_unmeasured:
        _console.print(
            "\n[yellow][!] One or more clauses are UNMEASURED.[/]"
            "\n  UNMEASURED != FAILED. No admissible evidence -> no claim."
            "\n  See subreason for each UNMEASURED clause above."
        )

    if probe_redundancy:
        _console.print(
            "\n[dim]--probe-redundancy:[/] Redundancy probe is reclassify-only."
            "\n  It cannot promote a clause from UNMEASURED or FAILED to PASSED."
        )


@run.command("evaluate-skill")
@click.argument("skill_id")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["rich", "json"], case_sensitive=False),
    default="rich",
    show_default=True,
    help="Output format: rich table (default) or JSON bytes.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help=(
        "Preflight only: shows what would be aggregated "
        "(run_ids discovered, clause count, axes). "
        "NO AGGREGATION DONE — re-run without --dry-run."
    ),
)
@click.option(
    "--evidence-db",
    type=click.Path(path_type=Path),
    default=Path("./evidence.db"),
    show_default=True,
    help="Path to evidence DB.",
)
@click.option(
    "--runtime-db",
    type=click.Path(path_type=Path),
    default=Path("./runtime.db"),
    show_default=True,
    help="Path to runtime DB.",
)
def run_evaluate_skill(
    skill_id: str,
    output_format: str,
    dry_run: bool,
    evidence_db: Path,
    runtime_db: Path,
) -> None:
    """Run the full evaluation suite against a skill (A54).

    Aggregates admissible+non-confounded verdicts for SKILL_ID into a SkillReport.
    Checks for incomplete runs first — if found, WARN and exit 1.

    Reporting honesty (A50): Contribution is labeled as
    'single-clause LOO; lower-bound under redundancy'.

    Exit codes:
      0  — no UNMEASURED in the family (all PASSED / FAILED / CONFOUNDED)
      2  — >=1 UNMEASURED clause
      1  — hard error (incomplete runs, precondition fail, aggregation bug)
    """
    from skill_harness.aggregation.errors import PreconditionError
    from skill_harness.aggregation.report import to_json_bytes
    from skill_harness.storage.errors import BootstrapError
    from skill_harness.storage.migrations import open_evidence_readonly, open_runtime
    from skill_harness.storage.recovery import find_incomplete_runs

    harness_version = _resolve_harness_version()

    # ------------------------------------------------------------------
    # Open DB connections
    # ------------------------------------------------------------------
    ev_ro: sqlite3.Connection | None = None
    rt_conn: sqlite3.Connection | None = None
    mech_vacuous_count: int = 0  # OBS-G5: populated before ev_ro closes, rich render only
    try:
        try:
            ev_ro = open_evidence_readonly(evidence_db)
        except BootstrapError as exc:
            raise click.ClickException(
                f"Evidence DB not found at {evidence_db}. "
                "Run 'skill-harness skill init <path> --execute' first."
            ) from exc

        try:
            rt_conn = open_runtime(runtime_db)
        except Exception as exc:
            raise click.ClickException(f"Cannot open runtime DB at {runtime_db}: {exc}") from exc

        # ------------------------------------------------------------------
        # Precondition: no incomplete runs (A54 spec step 1)
        # ------------------------------------------------------------------
        incomplete = find_incomplete_runs(skill_id, evidence_conn_ro=ev_ro, runtime_conn=rt_conn)
        if incomplete:
            stderr_console = Console(stderr=True)
            for run in incomplete:
                stderr_console.print(
                    f"[bold yellow]WARN:[/] Incomplete run {run.run_id!r} "
                    f"(state={run.state!r}) for skill {skill_id!r}."
                )
                stderr_console.print(
                    f"  Suggest: skill-harness run ablation {skill_id} --resume {run.run_id}"
                )
            sys.exit(1)

        # ------------------------------------------------------------------
        # Dry-run path: preflight only, no aggregation
        # ------------------------------------------------------------------
        if dry_run:
            # Enumerate run_ids and clauses — read-only
            try:
                run_rows = ev_ro.execute(
                    "SELECT run_id FROM runs WHERE skill_id = ? AND completed_at IS NOT NULL",
                    (skill_id,),
                ).fetchall()
                clause_rows = ev_ro.execute(
                    "SELECT clause_id, axis FROM clauses WHERE skill_id = ?",
                    (skill_id,),
                ).fetchall()
            except Exception as exc:
                raise click.ClickException(f"Failed to read evidence DB: {exc}") from exc

            _console.print(
                f"\n[bold]Preflight for skill:[/] {skill_id}"
                f"\n  completed run_ids: {[r[0] for r in run_rows]}"
                f"\n  clause count: {len(clause_rows)}"
                f"\n  axes: {sorted({r[1] for r in clause_rows})}"
            )
            _console.print("\n[bold yellow]NO AGGREGATION DONE — re-run without --dry-run[/]")
            return

        # ------------------------------------------------------------------
        # Aggregate
        # ------------------------------------------------------------------
        generated_at_utc = datetime.now(UTC).isoformat()
        try:
            report = aggregate_skill(
                skill_id,
                evidence_conn_ro=ev_ro,
                runtime_conn=rt_conn,
                harness_version=harness_version,
                generated_at_utc=generated_at_utc,
            )
        except PreconditionError as exc:
            if exc.code == "no_completed_runs":
                raise click.ClickException(
                    f"No completed ablation runs found for skill {skill_id!r}. "
                    f"Run 'skill-harness run ablation {skill_id} --execute' first."
                ) from exc
            elif exc.code == "no_clauses":
                raise click.ClickException(
                    f"No clauses found for skill {skill_id!r}. "
                    f"Run 'skill-harness skill init <artifact>' first."
                ) from exc
            raise click.ClickException(str(exc)) from exc

        # OBS-G5: read mech-vacuous count for rich-render adjunct.
        # Must happen before ev_ro is closed. No wire-format change.
        mech_vacuous_count = 0
        if output_format != "json" and ev_ro is not None:
            try:
                row = ev_ro.execute(
                    "SELECT COUNT(*) FROM clauses"
                    " WHERE skill_id = ? AND vacuity_flag = 'mechanical_vacuous'",
                    (skill_id,),
                ).fetchone()
                mech_vacuous_count = int(row[0]) if row else 0
            except Exception:
                mech_vacuous_count = 0

    finally:
        if ev_ro is not None:
            ev_ro.close()
        if rt_conn is not None:
            rt_conn.close()

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    if output_format == "json":
        sys.stdout.buffer.write(to_json_bytes(report))
    else:
        _render_evaluate_skill_report(report, vacuity_count=mech_vacuous_count)

    # ------------------------------------------------------------------
    # Exit code (A58)
    # ------------------------------------------------------------------
    has_unmeasured = any(c.status == "UNMEASURED" for c in report.clauses)
    if has_unmeasured:
        sys.exit(2)


@cli.group("diff")
def diff_group() -> None:
    """Diff commands (PRD §18)."""


@diff_group.command("skill")
@click.argument("skill_id_a")
@click.argument("skill_id_b")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["rich", "json"], case_sensitive=False),
    default="rich",
    show_default=True,
    help="Output format: rich table (default) or JSON.",
)
@click.option(
    "--exit-on-divergence",
    is_flag=True,
    default=False,
    help="Exit 2 if any clause status differs from 'unchanged'.",
)
@click.option(
    "--evidence-db",
    type=click.Path(path_type=Path),
    default=Path("./evidence.db"),
    show_default=True,
    help="Path to evidence DB.",
)
@click.option(
    "--runtime-db",
    type=click.Path(path_type=Path),
    default=Path("./runtime.db"),
    show_default=True,
    help="Path to runtime DB.",
)
def diff_skill(
    skill_id_a: str,
    skill_id_b: str,
    output_format: str,
    exit_on_divergence: bool,
    evidence_db: Path,
    runtime_db: Path,
) -> None:
    """Compare two skill revisions clause-by-clause (A55).

    Aggregates each skill independently and aligns clauses by
    (axis, sha256(clause_text)). Reports per-clause status deltas.

    Status delta ordering: FAILED < CONFOUNDED < UNMEASURED < PASSED.

    Exit codes (A58):
      0  — diff ran (semantic success; default even if clauses differ)
      2  — divergence detected AND --exit-on-divergence set
      1  — hard error (precondition fail for either skill)
    """
    import hashlib

    from skill_harness.aggregation import aggregate_skill
    from skill_harness.aggregation.errors import PreconditionError
    from skill_harness.cli.diff_report import (
        REPORT_SCHEMA_VERSION,
        ClauseDiff,
        DiffReport,
        status_delta,
        to_json_bytes,
    )
    from skill_harness.storage.errors import BootstrapError
    from skill_harness.storage.migrations import open_evidence_readonly, open_runtime
    from skill_harness.storage.recovery import find_incomplete_runs

    harness_version = _resolve_harness_version()

    # ------------------------------------------------------------------
    # Open connections
    # ------------------------------------------------------------------
    ev_ro: sqlite3.Connection | None = None
    rt_conn: sqlite3.Connection | None = None
    try:
        try:
            ev_ro = open_evidence_readonly(evidence_db)
        except BootstrapError as exc:
            raise click.ClickException(
                f"Evidence DB not found at {evidence_db}. "
                "Run 'skill-harness skill init <path> --execute' first."
            ) from exc

        try:
            rt_conn = open_runtime(runtime_db)
        except Exception as exc:
            raise click.ClickException(f"Cannot open runtime DB at {runtime_db}: {exc}") from exc

        # ------------------------------------------------------------------
        # Precondition check: both skills must have no incomplete runs and
        # at least one completed run (A55 spec step 1)
        # ------------------------------------------------------------------
        for sid in [skill_id_a, skill_id_b]:
            incomplete = find_incomplete_runs(sid, evidence_conn_ro=ev_ro, runtime_conn=rt_conn)
            if incomplete:
                stderr_console = Console(stderr=True)
                for run in incomplete:
                    stderr_console.print(
                        f"[bold yellow]WARN:[/] Incomplete run {run.run_id!r} "
                        f"(state={run.state!r}) for skill {sid!r}."
                    )
                sys.exit(1)

        # ------------------------------------------------------------------
        # Aggregate both skills
        # ------------------------------------------------------------------
        generated_at_utc = datetime.now(UTC).isoformat()
        reports = []
        for sid in [skill_id_a, skill_id_b]:
            try:
                rep = aggregate_skill(
                    sid,
                    evidence_conn_ro=ev_ro,
                    runtime_conn=rt_conn,
                    harness_version=harness_version,
                    generated_at_utc=generated_at_utc,
                )
                reports.append(rep)
            except PreconditionError as exc:
                raise click.ClickException(
                    f"Precondition failed for skill {sid!r}: {exc.code}. "
                    "Run 'skill-harness run ablation <skill_id> --execute' first."
                ) from exc

        report_a, report_b = reports

        # ------------------------------------------------------------------
        # Clause alignment: read clause_text for both skills (A55 step 3)
        # Match by (axis, sha256(clause_text))
        # ------------------------------------------------------------------
        def _load_clause_texts(skill_id: str) -> dict[str, str]:
            """clause_id -> clause_text for a skill."""
            rows = ev_ro.execute(
                "SELECT clause_id, clause_text FROM clauses WHERE skill_id = ?",
                (skill_id,),
            ).fetchall()
            return {r[0]: r[1] for r in rows}

        texts_a = _load_clause_texts(skill_id_a)
        texts_b = _load_clause_texts(skill_id_b)

        def _sha(text: str) -> str:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()

        # Build maps: (axis, sha256) -> ClauseReport
        key_a: dict[tuple[str, str], Any] = {}
        for cr in report_a.clauses:
            text = texts_a.get(cr.clause_id, "")
            # Use axis from the ClauseReport (derived from the verdict axis)
            # Build with (first axis key, sha256)
            # v0.2 limitation: clauses with zero admissible verdicts (metric_id_per_axis == {})
            # collapse to axis_key="" and align by sha256 only. Multiple zero-verdict clauses
            # with the same clause_text_sha256 collapse to one bucket. See T9 regression test.
            axis_key = next(iter(cr.metric_id_per_axis.keys()), "")
            key_a[(axis_key, _sha(text))] = cr

        key_b: dict[tuple[str, str], Any] = {}
        for cr in report_b.clauses:
            text = texts_b.get(cr.clause_id, "")
            axis_key = next(iter(cr.metric_id_per_axis.keys()), "")
            key_b[(axis_key, _sha(text))] = cr

        # ------------------------------------------------------------------
        # Build per-clause diffs
        # ------------------------------------------------------------------
        clause_diffs: list[ClauseDiff] = []
        all_keys = set(key_a.keys()) | set(key_b.keys())

        for key in sorted(all_keys):
            axis_key, sha = key
            cr_a = key_a.get(key)
            cr_b = key_b.get(key)

            if cr_a is None:
                # new in B
                assert cr_b is not None
                clause_diffs.append(
                    ClauseDiff(
                        clause_text_sha256=sha,
                        axis=axis_key,
                        status_a=None,
                        status_b=cr_b.status,
                        delta="new",
                        metric_drift_reason=None,
                    )
                )
            elif cr_b is None:
                # removed in B
                clause_diffs.append(
                    ClauseDiff(
                        clause_text_sha256=sha,
                        axis=axis_key,
                        status_a=cr_a.status,
                        status_b=None,
                        delta="removed",
                        metric_drift_reason=None,
                    )
                )
            else:
                # Both present: check metric_drift first (A55, all four axes)
                drift_reason: str | None = None
                if cr_a.metric_id_per_axis != cr_b.metric_id_per_axis:
                    drift_reason = (
                        f"metric_id differs: A={cr_a.metric_id_per_axis} "
                        f"B={cr_b.metric_id_per_axis}"
                    )
                elif cr_a.metric_version_per_axis != cr_b.metric_version_per_axis:
                    drift_reason = (
                        f"metric_version differs: A={cr_a.metric_version_per_axis} "
                        f"B={cr_b.metric_version_per_axis}"
                    )
                elif cr_a.ablation_operator_hash != cr_b.ablation_operator_hash:
                    drift_reason = (
                        f"ablation_operator_hash differs: A={cr_a.ablation_operator_hash!r} "
                        f"B={cr_b.ablation_operator_hash!r}"
                    )
                elif cr_a.subject_model != cr_b.subject_model:
                    drift_reason = (
                        f"subject_model differs: A={cr_a.subject_model!r} B={cr_b.subject_model!r}"
                    )
                elif cr_a.user_message_sha256 != cr_b.user_message_sha256:
                    drift_reason = (
                        f"user_message_sha256 differs: A={cr_a.user_message_sha256!r} "
                        f"B={cr_b.user_message_sha256!r}"
                    )

                if drift_reason is not None:
                    delta = "metric_drift"
                else:
                    delta = status_delta(cr_a.status, cr_b.status)

                clause_diffs.append(
                    ClauseDiff(
                        clause_text_sha256=sha,
                        axis=axis_key,
                        status_a=cr_a.status,
                        status_b=cr_b.status,
                        delta=delta,
                        metric_drift_reason=drift_reason,
                    )
                )

    finally:
        if ev_ro is not None:
            ev_ro.close()
        if rt_conn is not None:
            rt_conn.close()

    divergent = any(cd.delta != "unchanged" for cd in clause_diffs)
    diff_report = DiffReport(
        report_schema_version=REPORT_SCHEMA_VERSION,
        skill_id_a=skill_id_a,
        skill_id_b=skill_id_b,
        generated_at_utc=generated_at_utc,
        harness_version=harness_version,
        clauses=tuple(clause_diffs),
        divergent=divergent,
    )

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    if output_format == "json":
        sys.stdout.buffer.write(to_json_bytes(diff_report))
    else:
        _render_diff_report(diff_report)

    # ------------------------------------------------------------------
    # Exit code (A58)
    # ------------------------------------------------------------------
    if exit_on_divergence and divergent:
        sys.exit(2)


@cli.command("freeze")
@click.argument("verdict_id")
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help="Write to frozen_cases (default: dry-run, no writes).",
)
@click.option(
    "--oracle-source",
    default="mechanical",
    show_default=True,
    help="Oracle source for the frozen case (Tier-1 only in v0.1).",
)
@click.option(
    "--evidence-db",
    type=click.Path(path_type=Path),
    default=Path("./evidence.db"),
    show_default=True,
    help="Path to evidence DB.",
)
@click.option(
    "--runtime-db",
    type=click.Path(path_type=Path),
    default=Path("./runtime.db"),
    show_default=True,
    help="Path to runtime DB (unused in v0.1 freeze; reserved).",
)
def freeze(
    verdict_id: str,
    execute: bool,
    oracle_source: str,
    evidence_db: Path,
    runtime_db: Path,
) -> None:
    """Promote a freezable verdict into the frozen regression suite (A56/A-prime).

    Eligibility (branches on verdict.comparison):
      - ablation (full_vs_ablated): verdict.observation in {0.0, 0.5} (FAILING side)
      - paired (full_vs_null, A-prime): verdict.observation == 1.0 AND the metric
        registered as binary — the Null-arm sample is stored as the falsifying
        case. A paired frozen case is the Null half of the winning evidence
        re-encoded, not independent falsification (PRD §18 `freeze`).
      - verdict.admissibility_state == 'admissible'
      - verdict.oracle_source == 'mechanical' (Tier-1 only in v0.1)
      - verdict's parent run must be complete (completed_at IS NOT NULL)

    Defaults to dry-run — use --execute to write.
    Idempotent: double-freeze exits 0 with 'already frozen' message (A48).

    Exit codes (A58):
      0  — frozen or already frozen
      1  — validation refused (ineligibility, missing verdict, incomplete parent)
    """
    from skill_harness.storage.migrations import open_evidence, open_evidence_readonly
    from skill_harness.storage.repositories.evidence.frozen_cases import (
        PAIRED_FREEZE_BINARY_METRIC_IDS,
        freeze_verdict,
    )

    # I4: open read-only for dry-run (least-privilege); writable only on --execute.
    # Mirrors open_evidence_readonly used by run evaluate-skill (main.py:1014).
    ev_conn: sqlite3.Connection | None = None
    try:
        try:
            ev_conn = open_evidence(evidence_db) if execute else open_evidence_readonly(evidence_db)
        except Exception as exc:  # includes BootstrapError when DB not found
            raise click.ClickException(f"Cannot open evidence DB at {evidence_db}: {exc}") from exc

        # ------------------------------------------------------------------
        # Validate: verdict exists
        # ------------------------------------------------------------------
        verdict_row = ev_conn.execute(
            """SELECT verdict_id, clause_id, axis, comparison, observation,
                      admissibility_state, metric_id, sample_b_id
               FROM oracle_verdicts WHERE verdict_id = ?""",
            (verdict_id,),
        ).fetchone()

        if verdict_row is None:
            raise click.ClickException(f"verdict_id {verdict_id!r} not found in oracle_verdicts.")

        (
            _vrd_id,
            clause_id,
            axis,
            comparison,
            observation,
            admissibility_state,
            metric_id,
            sample_b_id,
        ) = verdict_row

        # ------------------------------------------------------------------
        # Eligibility checks (A56 ablation / A-prime paired) — mirror freeze_verdict
        # ------------------------------------------------------------------
        if comparison == "full_vs_null":
            if observation != 1.0:
                raise click.ClickException(
                    f"verdict {verdict_id!r} has observation={observation!r} "
                    "(paired full_vs_null verdicts freeze only at observation 1.0 — "
                    "a winning epoch whose Null arm failed absolutely; a paired 0.5 "
                    "may be a both-PASS tie and 0.0 means the Null arm won)."
                )
            if metric_id not in PAIRED_FREEZE_BINARY_METRIC_IDS:
                raise click.ClickException(
                    f"verdict {verdict_id!r} uses metric {metric_id!r}, which is not "
                    "registered as binary — paired freezing under a graded metric "
                    f"could store a passing Null sample. Registered binary metrics: "
                    f"{sorted(PAIRED_FREEZE_BINARY_METRIC_IDS)}."
                )
        elif observation not in (0.0, 0.5):
            raise click.ClickException(
                f"verdict {verdict_id!r} has observation={observation!r} "
                "(PASSING side — only FAILING verdicts with observation in {0.0, 0.5} can be "
                "frozen)."
            )
        if admissibility_state != "admissible":
            raise click.ClickException(
                f"verdict {verdict_id!r} is {admissibility_state!r} "
                "(only 'admissible' verdicts can be frozen)."
            )

        # Look up parent run's completion status
        run_row = ev_conn.execute(
            "SELECT run_id, completed_at FROM runs "
            "WHERE run_id = (SELECT run_id FROM oracle_verdicts WHERE verdict_id = ?)",
            (verdict_id,),
        ).fetchone()
        if run_row is None or run_row[1] is None:
            run_id_str = run_row[0] if run_row is not None else "unknown"
            raise click.ClickException(
                f"Parent run {run_id_str!r} is incomplete (completed_at IS NULL). "
                "Finish the ablation run before freezing a verdict."
            )

        # Compute failing_input_sha256 for dry-run display
        sample_row = ev_conn.execute(
            "SELECT output_sha256 FROM samples WHERE sample_id = ?",
            (sample_b_id,),
        ).fetchone()
        failing_sha = sample_row[0] if sample_row else "(unknown)"

        # ------------------------------------------------------------------
        # Dry-run path
        # ------------------------------------------------------------------
        if not execute:
            _console.print(
                f"\n[bold yellow]DRY-RUN[/] (no writes — use --execute to write)"
                f"\nWOULD freeze verdict [bold]{verdict_id}[/]:"
                f"\n  clause_id:              {clause_id}"
                f"\n  axis:                   {axis}"
                f"\n  comparison:             {comparison}"
                f"\n  observation:            {observation}"
                f"\n  failing_input_sha256:   {failing_sha}"
                f"\n  oracle_source:          {oracle_source}"
            )
            return

        # ------------------------------------------------------------------
        # Execute path: write to frozen_cases
        # ------------------------------------------------------------------
        try:
            frozen_case_id = freeze_verdict(ev_conn, verdict_id, oracle_source=oracle_source)
            _console.print(
                f"\n[green]frozen[/] verdict [bold]{verdict_id}[/] "
                f"→ frozen_case_id=[bold]{frozen_case_id}[/]"
            )
        except sqlite3.IntegrityError:
            # Already frozen — look up existing frozen_case_id (idempotent per A48)
            existing_row = ev_conn.execute(
                "SELECT frozen_case_id FROM frozen_cases WHERE verdict_id = ?",
                (verdict_id,),
            ).fetchone()
            existing_id = existing_row[0] if existing_row else "(unknown)"
            _console.print(
                f"[yellow]verdict {verdict_id!r} already frozen "
                f"as frozen_case_id={existing_id!r}[/]"
            )
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

    finally:
        if ev_conn is not None:
            ev_conn.close()


@cli.command("audit-metric")
@click.argument("metric_id")
@click.option(
    "--attest",
    default=None,
    help=(
        "REQUIRED non-empty operator attestation string. Echoed in output "
        "(dry-run and execute) and intended for the operator's commit trail; "
        "NOT stored in the DB (metric_versions has no attester column)."
    ),
)
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help="Write the audited row (default: dry-run, no writes).",
)
@click.option(
    "--evidence-db",
    type=click.Path(path_type=Path),
    default=Path("./evidence.db"),
    show_default=True,
    help="Path to evidence DB (created and bootstrapped on --execute if absent).",
)
def audit_metric(metric_id: str, attest: str | None, execute: bool, evidence_db: Path) -> None:
    """Register an audited metric_versions row for a subject Tier-1 metric.

    The audited-metric act (PRD §15.1; S88 A-double-prime): audited=1 attests
    that a deliberate operator act registered this metric implementation,
    hash-pinned against the shipped module at execution time. It is an
    operator-attested, hash-pinned registration — NOT a claim of independent
    construct-validity review. Attester identity lives in the operator's
    commit trail, not the DB.

    Pre-register-before-ingest: run this against a FRESH store BEFORE its
    first ingest; ingest's existence guard then short-circuits and frozen
    cases can label 'current'. No act flips audited on an existing row
    (append-only): a store whose row was minted unaudited requires re-ingest
    into a store audited first.

    Defaults to dry-run — use --execute to write.
    Idempotent: re-run after success exits 0 with 'already audited' ONLY if
    the existing row is audited and its hash matches the live module; a hash
    mismatch refuses loudly (implementation drift).

    Exit codes (A58):
      0  — registered or already audited
      1  — refused (missing/blank --attest, unregistered metric_id,
           existing unaudited row, hash drift, DB not found on dry-run)
    """
    from skill_harness.storage.migrations import open_evidence, open_evidence_readonly
    from skill_harness.storage.repositories.evidence.frozen_cases import (
        PAIRED_FREEZE_BINARY_METRIC_IDS,
    )
    from skill_harness.storage.repositories.evidence.metric_versions import (
        plan_audited_metric_registration,
        register_audited_metric,
    )

    # K3: the act is a deliberate typed attestation — refuse before any DB work.
    if attest is None or not attest.strip():
        raise click.ClickException(
            'audit-metric requires a non-empty --attest "<text>" — the audited flip is '
            "a deliberate operator act; type what you are attesting."
        )

    # Membership pre-check BEFORE opening the DB: --execute bootstraps an absent
    # store, and a refused act must not leave one behind. The refusal logic
    # itself stays single-sourced in plan_audited_metric_registration (K6);
    # this only mirrors freeze's registry-membership guard (no third copy of
    # the id strings).
    if metric_id not in PAIRED_FREEZE_BINARY_METRIC_IDS:
        raise click.ClickException(
            f"metric {metric_id!r} is not registered for the audit-metric act. "
            f"Registered metric ids: {sorted(PAIRED_FREEZE_BINARY_METRIC_IDS)}."
        )

    # I4: open read-only for dry-run (least-privilege); writable only on
    # --execute. Mirrors freeze.
    ev_conn: sqlite3.Connection | None = None
    try:
        try:
            ev_conn = open_evidence(evidence_db) if execute else open_evidence_readonly(evidence_db)
        except Exception as exc:  # includes BootstrapError when DB not found
            raise click.ClickException(f"Cannot open evidence DB at {evidence_db}: {exc}") from exc

        try:
            plan = plan_audited_metric_registration(ev_conn, metric_id)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        if not execute:
            if plan.action == "already_audited":
                _console.print(
                    f"\n[bold yellow]DRY-RUN[/] (no writes — use --execute to write)"
                    f"\nmetric [bold]{metric_id}[/] is already audited at version "
                    f"{plan.version} with a hash matching the live module — nothing to do."
                    f"\n  attestation (echoed, not stored): {attest}"
                )
                return
            _console.print(
                f"\n[bold yellow]DRY-RUN[/] (no writes — use --execute to write)"
                f"\nWOULD register audited metric_versions row:"
                f"\n  metric_id:                        {plan.metric_id}"
                f"\n  version:                          {plan.version}"
                f"\n  implementation_hash (live):       {plan.implementation_hash}"
                f"\n  tier:                             1"
                f"\n  audited:                          1"
                f"\n  mechanical_validity_test_passed:  1"
                f"\n  attestation (echoed, not stored): {attest}"
            )
            return

        try:
            row = register_audited_metric(ev_conn, metric_id)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        verb = "already audited" if plan.action == "already_audited" else "registered"
        colour = "yellow" if plan.action == "already_audited" else "green"
        _console.print(
            f"\n[{colour}]{verb}[/] audited metric [bold]{row['metric_id']}[/]"
            f" version {row['version']}:"
            f"\n  implementation_hash:              {row['implementation_hash']}"
            f"\n  registered_at:                    {row['registered_at']}"
            f"\n  attestation (echoed, not stored): {attest}"
        )
    finally:
        if ev_conn is not None:
            ev_conn.close()


# ---------------------------------------------------------------------------
# Render helpers for evaluate-skill and diff skill
# ---------------------------------------------------------------------------


def _render_evaluate_skill_report(report: Any, vacuity_count: int = 0) -> None:
    """Rich table render for SkillReport (A54 / A50).

    Renders two tables:
    1. Vector summary (Passed / Failed / Confounded / Unmeasured / Coverage)
    2. Per-clause detail (clause_id / status / sub_reason / posterior_mean / CI)

    UNMEASURED rows → YELLOW; FAILED rows → RED; PASSED rows → GREEN;
    CONFOUNDED rows → MAGENTA. (A54 spec)

    Footer cites A50 framing (single-clause LOO; lower-bound under redundancy).

    OBS-G5 (Appendix G): when vacuity_count > 0, Coverage cell gains adjunct:
      "50.0% (1 verified / 2 authored; 1 mech-vacuous excluded from testing)"
    Read-side derivation only; no wire-format change.
    """
    # Vector summary table
    vec = report.vector
    vec_table = Table(title="Skill Vector Summary", show_lines=True)
    vec_table.add_column("Passed", style="green", justify="right")
    vec_table.add_column("Failed", style="red", justify="right")
    vec_table.add_column("Confounded", style="magenta", justify="right")
    vec_table.add_column("Unmeasured", style="yellow", justify="right")
    vec_table.add_column("Coverage", justify="right")
    vec_table.add_column("Contribution", min_width=40)

    contrib = report.contribution
    contrib_label = getattr(contrib, "label", "single-clause LOO; lower-bound under redundancy")
    delta = getattr(contrib, "full_vs_null_delta", None)
    contrib_str = f"{contrib_label} (Δ={delta:.3f})" if delta is not None else contrib_label
    # OBS-G5: coverage adjunct when mech-vacuous clauses exist.
    total_authored = vec.passed + vec.failed + vec.confounded + vec.unmeasured
    verified = round(report.coverage * total_authored)
    if vacuity_count > 0:
        coverage_str = (
            f"{report.coverage:.1%}"
            f" ({verified} verified / {total_authored} authored;"
            f" {vacuity_count} mech-vacuous excluded from testing)"
        )
    else:
        coverage_str = f"{report.coverage:.1%}"
    vec_table.add_row(
        str(vec.passed),
        str(vec.failed),
        str(vec.confounded),
        str(vec.unmeasured),
        coverage_str,
        contrib_str,
    )
    _console.print(vec_table)

    # Per-clause detail table
    clause_table = Table(title="Per-Clause Results", show_lines=True)
    clause_table.add_column("clause_id", style="dim", min_width=20)
    clause_table.add_column("status", min_width=12)
    clause_table.add_column("sub_reason", min_width=20)
    clause_table.add_column("posterior_mean", min_width=14, justify="right")
    # #187: lead with the anytime-valid confidence sequence; posterior interval
    # is Bayesian-only (no frequentist coverage claim under sequential stop).
    clause_table.add_column("CS 95% (anytime-valid)", min_width=18, justify="right")
    clause_table.add_column("posterior CrI 95%", min_width=16, justify="right")

    for clause in report.clauses:
        status = clause.status
        sub_reason = clause.sub_reason or "—"
        post_lo, post_hi = clause.posterior_credible_interval_95
        # B5: is_prior_only clauses carry an uninformative Beta(1,1) PRIOR
        # (posterior_mean=0.5 etc.), not a measurement — render a dim placeholder
        # instead of the fabricated numbers so a reader never mistakes UNMEASURED
        # for "measured at 0.5".
        if clause.is_prior_only:
            cs_str = "[dim]— (prior)[/]"
            post_str = "[dim]— (prior)[/]"
        elif clause.interval_status == "UNMEASURED_INCOMPARABLE_POOL":
            cs_str = "[dim]— (incomparable pool)[/]"
            post_str = f"[{post_lo:.3f}, {post_hi:.3f}]"
        elif clause.sequential_confidence_sequence_95 is not None:
            cs_lo, cs_hi = clause.sequential_confidence_sequence_95
            cs_str = f"[{cs_lo:.3f}, {cs_hi:.3f}]"
            post_str = f"[{post_lo:.3f}, {post_hi:.3f}]"
        else:
            cs_str = "[dim]—[/]"
            post_str = f"[{post_lo:.3f}, {post_hi:.3f}]"

        if status == "UNMEASURED":
            status_str = f"[yellow]{status}[/]"
        elif status == "FAILED":
            status_str = f"[red]{status}[/]"
        elif status == "PASSED":
            status_str = f"[green]{status}[/]"
        elif status == "CONFOUNDED":
            status_str = f"[magenta]{status}[/]"
        else:
            status_str = status

        if clause.is_prior_only:
            posterior_mean_str = "[dim]— (prior)[/]"
        else:
            posterior_mean_str = f"{clause.posterior_mean:.3f}"
        clause_table.add_row(
            clause.clause_id,
            status_str,
            sub_reason,
            posterior_mean_str,
            cs_str,
            post_str,
        )

    _console.print(clause_table)

    # M5: bridge note for UNMEASURED(no_data) → ablation sub_reason mapping
    has_no_data = any(c.sub_reason == "no_data" for c in report.clauses)
    if has_no_data:
        _console.print(
            "[dim]Note: UNMEASURED(no_data) at evaluate-skill maps to"
            " UNMEASURED(tier2_uncalibrated) at ablation time when oracle gate fires"
            " before verdict write.[/]"
        )

    # A50 footer
    _console.print(
        "\n[bold]Contribution (A50):[/] single-clause LOO; lower-bound under redundancy."
        "\n  Absence of delta is not absence of contribution."
    )

    # Link to UNMEASURED explanation when any clause is UNMEASURED
    if any(c.status == "UNMEASURED" for c in report.clauses):
        _console.print(
            "\n[dim]UNMEASURED is not a failure — see"
            " docs/concepts/why-unmeasured.md for sub-reason explanations.[/]"
        )


def _render_diff_report(diff_report: Any) -> None:
    """Rich table render for DiffReport (A55)."""

    table = Table(
        title=f"Diff: {diff_report.skill_id_a} vs {diff_report.skill_id_b}",
        show_lines=True,
    )
    table.add_column("axis", style="cyan", min_width=12)
    table.add_column("sha256[:12]", style="dim", min_width=14)
    table.add_column("status_a", min_width=12)
    table.add_column("status_b", min_width=12)
    table.add_column("delta", min_width=14)
    table.add_column("detail", min_width=30)

    _STATUS_COLORS = {
        "PASSED": "green",
        "FAILED": "red",
        "UNMEASURED": "yellow",
        "CONFOUNDED": "magenta",
    }

    def _fmt_status(s: str | None) -> str:
        if s is None:
            return "[dim]—[/]"
        color = _STATUS_COLORS.get(s, "white")
        return f"[{color}]{s}[/]"

    _DELTA_COLORS = {
        "unchanged": "dim",
        "improved": "green",
        "regressed": "red",
        "new": "blue",
        "removed": "magenta",
        "metric_drift": "yellow",
    }

    for cd in diff_report.clauses:
        sha_short = cd.clause_text_sha256[:12]
        delta_color = _DELTA_COLORS.get(cd.delta, "white")
        delta_str = f"[{delta_color}]{cd.delta}[/]"
        detail = cd.metric_drift_reason or ""
        table.add_row(
            cd.axis,
            sha_short,
            _fmt_status(cd.status_a),
            _fmt_status(cd.status_b),
            delta_str,
            detail[:60],
        )

    _console.print(table)

    divergent_str = "[red]DIVERGENT[/]" if diff_report.divergent else "[green]IDENTICAL[/]"
    _console.print(f"\n  Diff result: {divergent_str}")
    if diff_report.divergent:
        _console.print("  [dim]Use --exit-on-divergence to signal divergence via exit code.[/]")


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
    "--max-usd",
    type=float,
    default=5.0,
    show_default=True,
    help="Per-run cost cap in USD; refuse if projected cost exceeds this (A36).",
)
@click.option(
    "--daily-cap",
    type=float,
    default=20.0,
    show_default=True,
    help=(
        "Trailing-24h daily spend cap in USD per runtime.db (A36). Hard ceiling at $100 "
        "(override via SKILL_HARNESS_DAILY_CAP_OVERRIDE=1). NOTE: scope is per-runtime.db; "
        "parallel worktrees with separate runtime DBs do NOT share the cap."
    ),
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
@click.option(
    "--verify-judge-id",
    is_flag=True,
    default=False,
    help=(
        "Refuse (instead of merely warning) if JUDGE_ID does not match "
        "JudgeClient.judge_id(model) for the model this run would actually use. "
        "Off by default for backward compatibility with human-readable operator "
        "judge_id conventions; a mismatch is always warned about either way (J1w)."
    ),
)
def calibrate_cmd(
    judge_id: str,
    axis: str,
    pair_set_path: Path,
    execute: bool,
    max_usd: float,
    daily_cap: float,
    evidence_db: Path,
    runtime_db: Path,
    verify_judge_id: bool,
) -> None:
    """Calibrate a judge on an axis using a JSONL pair set.

    JUDGE_ID is the opaque judge identifier (sha256 of model+prompt+schema).
    It is operator-supplied, NOT derived automatically -- calibrations recorded
    under a given JUDGE_ID string are only comparable if the underlying
    (model, system prompt, tool schema) are unchanged; JudgeClient.judge_id(model)
    computes the value that would be current for this run's model. A mismatch
    is always warned about (J1w: a prompt/schema change must not silently
    coexist with calibrations still filed under the old operator string);
    pass --verify-judge-id to make a mismatch a hard refusal instead.
    AXIS is the evaluation axis (e.g. citation_support).
    PAIR_SET_PATH is a JSONL file of labeled human-preference pairs.

    Defaults to dry-run (no DB writes). Use --execute to persist.

    Three-tier evidence admissibility (A34):
      N < 50    → rejected  (no write; exits with error)
      50-99     → conditional (write with credible-interval penalty)
      N ≥ 100   → calibrated (if all four thresholds pass)

    Cost caps (A36):
      --max-usd   per-run cap; refuse if projected cost exceeds it.
      --daily-cap per-day cap; hard ceiling $100 (override via env var).
    """
    import os

    from skill_harness.oracles.calibration.command import calibrate
    from skill_harness.oracles.calibration.cost_projection import validate_daily_cap
    from skill_harness.oracles.tier2.judge import JudgeClient

    # Validate daily cap against hard ceiling (A36)
    try:
        validate_daily_cap(daily_cap)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    # D1: model-aware API key pre-flight BEFORE any DB/StorageContext creation,
    # mirroring m3's doctrine for 'run ablation' (_resolve_subject_model_with_fallback).
    # JudgeClient always constructs anthropic.Anthropic() directly -- unlike the
    # subject-model factory it has no OpenRouter routing -- so this checks
    # ANTHROPIC_API_KEY only rather than reusing _resolve_subject_model_with_fallback
    # verbatim (that would falsely promise an OpenRouter fallback JudgeClient can't
    # perform). Without this, StorageContext below creates both DB files before the
    # first judge call fails lazily on the missing key.
    if execute and not os.environ.get("ANTHROPIC_API_KEY"):
        raise click.ClickException(
            "calibrate --execute requires ANTHROPIC_API_KEY. JudgeClient calls the "
            "Anthropic API directly for judge calibration (no OpenRouter fallback is "
            "supported here). Set ANTHROPIC_API_KEY to proceed."
        )

    judge_client = JudgeClient()

    # J1w: judge_id is operator-supplied and was never cross-checked against
    # JudgeClient.judge_id(model) -- a system-prompt/tool-schema change (which
    # changes judge_id()'s output) could silently coexist with calibrations
    # still filed under the same operator string. Always surface a mismatch;
    # --verify-judge-id escalates it to a refusal for callers that want the
    # hard guarantee. Off by default: human-readable judge_id conventions
    # (e.g. "judge-001") are an established CLI/test convention here and a
    # default refusal would break them, not just warn about drift.
    derived_judge_id = judge_client.judge_id(judge_client.model)
    if judge_id != derived_judge_id:
        mismatch_msg = (
            f"judge_id {judge_id!r} does not match JudgeClient.judge_id(model) "
            f"for model {judge_client.model!r}: derived {derived_judge_id!r}. "
            "This is expected if judge_id is a human-readable operator label; it is "
            "NOT expected if you meant to calibrate the model/prompt/schema identity "
            "this run would actually use -- calibrations recorded under different "
            "judge_id strings for the same real judge are not comparable, and this "
            "run's system prompt or tool schema may have changed since judge_id was "
            "chosen."
        )
        if verify_judge_id:
            raise click.ClickException(mismatch_msg + " Refusing (--verify-judge-id).")
        _console.print(f"[yellow]WARNING:[/] {mismatch_msg}")

    # D2: parse_pair_set (inside calibrate()) raises ValueError on malformed JSONL
    # (invalid JSON or a pydantic ValidationError wrapped as ValueError). Previously
    # only validate_daily_cap's ValueError was wrapped here, so a malformed pair-set
    # file surfaced as a raw traceback instead of a clean CLI error.
    try:
        if execute:
            with StorageContext(evidence_db, runtime_db) as ctx:
                result = calibrate(
                    judge_id=judge_id,
                    axis=axis,
                    pair_set_path=pair_set_path,
                    judge_client=judge_client,
                    evidence_conn=ctx.evidence_conn,
                    runtime_conn=ctx.runtime_conn,
                    max_usd=max_usd,
                    daily_cap=daily_cap,
                    dry_run=False,
                )
        else:
            # Dry-run: parse, project cost, but do not make any judge calls or DB writes
            from unittest.mock import MagicMock

            result = calibrate(
                judge_id=judge_id,
                axis=axis,
                pair_set_path=pair_set_path,
                judge_client=judge_client,
                evidence_conn=MagicMock(),
                runtime_conn=MagicMock(),
                max_usd=max_usd,
                daily_cap=daily_cap,
                dry_run=True,
            )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    _print_calibrate_result(result, executed=execute, daily_cap=daily_cap)

    if result.state == "rejected":
        reason = getattr(result, "reason", "")
        if reason and "projected_cost_exceeds" in reason:
            proj = getattr(result, "cost_projection", None)
            proj_usd = f"${proj.usd:.4f}" if proj else "unknown"
            raise click.ClickException(
                f"Calibration refused — projected cost {proj_usd} exceeds --max-usd ${max_usd:.2f}."
            )
        raise click.ClickException(
            f"Calibration rejected — {reason} (N={result.n_pairs}). Provide a pair set with N≥50."
        )


def _print_calibrate_result(
    result: object,
    *,
    executed: bool,
    daily_cap: float = 20.0,
) -> None:
    """Print calibration result summary with A36-shape dry-run projection."""
    mode = "[green]EXECUTED[/]" if executed else "[yellow]DRY-RUN[/]"
    state = getattr(result, "state", "?")
    n_pairs = getattr(result, "n_pairs", 0)
    _console.print(f"\n{mode} — calibrate [bold]{state.upper()}[/]")
    _console.print(f"  pairs: {n_pairs}")

    # A36 dry-run projection output
    proj = getattr(result, "cost_projection", None)
    if proj is not None:
        model_name = "claude-sonnet-4-6"
        _console.print(
            f"\nprojected: {proj.n_calls} calls ({n_pairs} pairs x2 position swaps), "
            f"{proj.t_in_cache_read + proj.t_in_uncached + proj.t_in_cached:,} input tok"
        )
        _console.print(
            f"           ({proj.t_in_cache_read:,} cache-read + {proj.t_in_uncached:,} uncached + "
            f"{proj.t_in_cached:,} unique tails),"
        )
        _console.print(f"           {proj.t_out:,} output tok, ≈${proj.usd:.4f} on {model_name};")
        _console.print(f"           cache reuse: {proj.cache_reuse_pct:.0f}% on input.")
        _console.print(
            f"           est_SE_pairwise_agreement: {proj.est_se_pairwise_agreement:.3f}. "
            f"est_CI_95_width: {proj.est_ci_95_width:.3f}."
        )
        _console.print(f"           Per-run cap: $5.00. Daily cap: ${daily_cap:.2f}.")

    if not executed and state not in ("rejected",):
        _console.print("[yellow]Dry-run: no data written. Use --execute to persist.[/]")

    if state == "dry_run":
        return

    if state not in ("rejected", "dry_run"):
        pa = getattr(result, "pairwise_agreement", 0.0)
        pc = getattr(result, "position_consistency", 0.0)
        ck = getattr(result, "cohen_kappa", 0.0)
        cb = getattr(result, "chance_baseline", 0.0)
        _console.print(f"  pairwise_agreement:   {pa:.3f}")
        _console.print(f"  position_consistency: {pc:.3f}")
        _console.print(f"  cohen_kappa:          {ck:.3f}")
        _console.print(f"  chance_baseline:      {cb:.3f}")

    reason = getattr(result, "reason", None)
    if state == "rejected" and reason:
        _console.print(f"  [red]reason: {reason}[/]")

    cal_id = getattr(result, "calibration_event_id", None)
    if cal_id:
        _console.print(f"  calibration_event_id: {cal_id}")


@cli.group()
def screen() -> None:
    """Stage-0 Null-only screen store (migration 0501) — keep/cut verdicts."""


@screen.command("verdict")
@click.option(
    "--evidence-db",
    type=click.Path(path_type=Path),
    default=Path("./evidence.db"),
    show_default=True,
    help="Path to evidence DB (read-only; no writes, no API calls).",
)
@click.option(
    "--fresh-pin",
    type=str,
    default=None,
    help="Fresh harness_pin_fingerprint to compare against stored rows. When set,"
    " admissible screens with a different fingerprint are refused (#382).",
)
def screen_verdict_cmd(evidence_db: Path, fresh_pin: str | None) -> None:
    """Derive p0 per skill from the screen store and print the keep/cut verdict.

    Read-only. p0 is DERIVED from admissible screen trials (never stored); each
    skill's Null-arm pass rate maps to KEEP / CUT / CAN'T-TELL-YET via the locked
    transformative bar, gated by the skill's registered value_class (#74/#77).

    A ceiling (p0=1) means CUT only for a transformative-lift skill, where it
    genuinely reads "the model does this unaided." For any other class it means
    "the trap did not fire in this Null screen" — the wrong instrument for the
    question — and the verdict is CAN'T-TELL-YET, never CUT. An unclassified
    skill is treated as not-transformative, so it cannot be false-CUT.

    Pin currency (#382): when --fresh-pin is provided, admissible screens whose
    harness_pin_fingerprint differs from it are refused — the screen was captured
    under a different instrument version and must not silently contribute to p0.
    """
    from skill_harness.aggregation.value_class_registry import value_class_for
    from skill_harness.aggregation.verdict import screen_verdict
    from skill_harness.storage.errors import BootstrapError, StalePinError
    from skill_harness.storage.migrations import open_evidence_readonly
    from skill_harness.storage.repositories.evidence.screens import (
        derive_p0_by_skill,
        select_stale_pin_skills,
    )

    if not evidence_db.exists():
        _console.print(
            "\n[yellow]no screen store — run 'screen backfill --execute' or a screen run first[/]"
            f"\n[dim]  (evidence.db not found at {evidence_db})[/]"
        )
        return

    db_conn: sqlite3.Connection | None = None
    try:
        db_conn = open_evidence_readonly(evidence_db)
        stale_rows = select_stale_pin_skills(db_conn, fresh_pin) if fresh_pin is not None else []
        # Pin filter is applied inside derive so mixed-pin skills keep only fresh rows.
        rows = derive_p0_by_skill(db_conn, fresh_pin=fresh_pin)
    except BootstrapError:
        _console.print(f"\n[yellow]evidence.db not found at {evidence_db}.[/]")
        return
    finally:
        if db_conn is not None:
            db_conn.close()

    if stale_rows:
        _console.print(f"\n[red]Stale pin refused ({len(stale_rows)} skill(s)):[/]")
        for stale in stale_rows:
            refusal = StalePinError(
                stored_fingerprints=stale.stored_fingerprints,
                fresh_fingerprint=fresh_pin or "",
            )
            _console.print(
                f"  [red]{_sanitize_clause_text(stale.skill_name, max_len=None)}: "
                f"{_sanitize_clause_text(str(refusal), max_len=None)}[/]"
            )
        _console.print(
            "[dim]  These screens were captured under a different harness pin and"
            " must not silently contribute to p0 (#382).[/]"
        )

    if not rows:
        if fresh_pin is not None and stale_rows:
            _console.print("\n[yellow]No admissible screens remain after pin-currency check.[/]")
        else:
            _console.print(
                "\n[yellow]No admissible screens in the store.[/]"
                "\n[dim]  Backfill batch-1 with 'screen backfill --execute', or run a screen.[/]"
            )
        return

    table = Table(title="Screen verdicts (p0 derived from admissible trials)", show_lines=True)
    table.add_column("skill", style="cyan", min_width=24)
    table.add_column("p0", width=6, justify="right")
    table.add_column("epochs", width=8, justify="right")
    table.add_column("verdict", min_width=14)
    # Scope column (#51): store rows predate the estimand registry, so every
    # cell today is the honest pre-registry n/a marker — never a retrofitted
    # label. Values come from VerdictResult.estimand_label (enum-backed).
    table.add_column("estimand", min_width=14, no_wrap=True)
    table.add_column("rationale", min_width=40, max_width=70)

    for row in rows:
        # Value-class guard (#74/#76/#77): the per-skill value_class comes from the
        # classify-the-11 registry (US-16). A transformative-lift skill above the bar
        # CUTs (subsumed); every non-transformative class (trap-discipline, calibration)
        # renders CANT_TELL_YET (wrong instrument) — the four false CUTs (OBS-0003..0006)
        # are structurally withheld, not by accident of being unclassified (US-3). A
        # skill_name absent from the registry → None → the same honest CANT_TELL_YET.
        v = screen_verdict(row.p0, value_class=value_class_for(row.skill_name))
        sub = f"({v.cut_sub_reason.value})" if v.cut_sub_reason else ""
        verdict_color = {"KEEP": "green", "CUT": "red", "CANT_TELL_YET": "yellow"}[v.verdict.value]
        table.add_row(
            _sanitize_clause_text(row.skill_name, max_len=None),
            f"{row.p0:.2f}",
            f"{row.n_pass}/{row.n_trials}",
            f"[{verdict_color}]{v.verdict.value}{sub}[/]",
            f"[dim]{v.estimand_label}[/]",
            _sanitize_clause_text(v.rationale, max_len=None),
        )
    _console.print(table)
    _console.print(
        "\n[dim]p0 is derived from ADMISSIBLE screen trials only; inadmissible (voided)"
        " screens are kept in the store but excluded. A verdict is a hardness screen,"
        " not a paired measurement.[/]"
    )
    if fresh_pin is None:
        _console.print(
            "\n[dim]Pin currency check skipped: supply --fresh-pin to refuse rows"
            " captured under a different harness instrument (#382).[/]"
        )


@screen.command("profile")
@click.option(
    "--evidence-db",
    type=click.Path(path_type=Path),
    default=Path("./evidence.db"),
    show_default=True,
    help="Path to evidence DB (read-only; no writes, no API calls).",
)
@click.option(
    "--skills-root",
    type=click.Path(path_type=Path),
    default=None,
    help="Root of a skills tree (<root>/<skill>/SKILL.md). Enables the "
    "description-token standing-cost axis and library enumeration.",
)
@click.option(
    "--show-held-columns",
    is_flag=True,
    default=False,
    help="Show the HELD effect (95% CrI) and eff/cost columns (empty until the "
    "paired path measures a per-skill effect).",
)
def screen_profile_cmd(
    evidence_db: Path, skills_root: Path | None, show_held_columns: bool
) -> None:
    """Per-skill evaluation profile — separated GRADE-style axes (read-only VIEW).

    Presents the harness's existing signals as SEPARATE columns — disposition,
    verdict, evidence-quality, cost — one row per skill over the UNION of screened
    skills and skills-root skills. It never fuses the axes into one ranking scalar
    (GRADE / Guyatt 2008: keep evidence quality separate from strength). Evidence
    quality is an ORDINAL label (Velleman & Wilkinson 1993 — no arithmetic on it).

    The effect + eff/cost columns are HELD (the Stage-0 screen path yields no
    paired per-skill effect yet); the fired-tax cost half is likewise held (no
    sanctioned read-only open path exists for the runtime cost ledger yet).
    """
    from skill_harness.aggregation.profile import (
        SkillProfileInput,
        build_skill_profile,
    )
    from skill_harness.aggregation.value_class_registry import value_class_for
    from skill_harness.aggregation.verdict import screen_verdict
    from skill_harness.extractor.errors import MalformedSkillError
    from skill_harness.extractor.parser import parse_skill_file
    from skill_harness.storage.errors import BootstrapError
    from skill_harness.storage.migrations import open_evidence_readonly
    from skill_harness.storage.repositories.evidence.screens import (
        ScreenP0,
        derive_p0_by_skill,
    )

    # --- Source the screened skills (read-only; p0 derived, never stored) -----
    screened: dict[str, ScreenP0] = {}
    if evidence_db.exists():
        db_conn: sqlite3.Connection | None = None
        try:
            db_conn = open_evidence_readonly(evidence_db)
            screened = {row.skill_name: row for row in derive_p0_by_skill(db_conn)}
        except BootstrapError:
            screened = {}
        except sqlite3.OperationalError:
            # F-5 precedent (see 'skill clauses'): open_evidence_readonly does NOT
            # apply migrations, so a PRESENT-but-malformed or pre-0501 evidence.db
            # (missing screen_runs/screen_trials) makes derive_p0_by_skill raise
            # OperationalError. Fall back to no screens — unlike 'screen verdict',
            # this command can still profile the --skills-root library.
            _console.print(
                f"\n[yellow]evidence.db at {evidence_db} has no screen store "
                "(missing/older schema); profiling the skills-root library only.[/]"
            )
            screened = {}
        finally:
            if db_conn is not None:
                db_conn.close()

    # --- Source the skills-root standing cost + disable-model-invocation flag --
    # skills-root keys on the skill DIRECTORY name; the screen store keys on
    # skill_name. In this store those identifiers are the same kebab-case slug, so
    # the union below joins on that string. desc_token_cost is a chars/4 estimate;
    # a disable-model-invocation skill is never loaded into context, so its
    # standing tax is 0 (not None).
    library: dict[str, tuple[int, bool]] = {}
    if skills_root is not None and not skills_root.is_dir():
        _console.print(
            f"\n[yellow]--skills-root {skills_root} is not a directory — skipped.[/] "
            "[dim]The description-token standing-cost axis and library enumeration "
            "are unavailable.[/]"
        )
    if skills_root is not None and skills_root.is_dir():
        # A skills tree is either flat (<root>/<skill>/SKILL.md) or grouped by
        # category (<root>/<category>/<skill>/SKILL.md). MrBinnacle/skills is the
        # latter -- engineering/, meta/, orchestration/ -- so a single-level scan
        # enumerated ZERO of its 14 cards and degraded to the "no skills-root
        # library" footnote without erroring. That silently blanked desc-cost, the
        # one axis on this table that needs no eval spend at all.
        # Descend one extra level only where the direct child carries no SKILL.md,
        # so a flat root keeps its existing behaviour exactly.
        for child in sorted(skills_root.iterdir()):
            if not child.is_dir():
                continue
            if (child / "SKILL.md").is_file():
                candidates = [child]
            else:
                candidates = [g for g in sorted(child.iterdir()) if (g / "SKILL.md").is_file()]
            for candidate in candidates:
                try:
                    parsed = parse_skill_file(candidate / "SKILL.md")
                except (MalformedSkillError, OSError):
                    continue
                description = parsed.frontmatter.get("description", "")
                is_disable = parsed.frontmatter.get(
                    "disable-model-invocation", ""
                ).strip().lower() == ("true")
                desc_cost = 0 if is_disable else (len(description) + 3) // 4  # ceil(len/4)
                library[candidate.name] = (desc_cost, is_disable)

    if not screened and not library:
        _console.print(
            "\n[yellow]nothing to profile[/] — no screened skills and no --skills-root."
            "\n[dim]  Run 'screen backfill --execute' or a screen, and/or pass --skills-root.[/]"
        )
        return

    # --- Assemble the union into separated-axis inputs (no fusion) -------------
    inputs: list[SkillProfileInput] = []
    for skill in sorted(set(screened) | set(library)):
        sp = screened.get(skill)
        estimand: str | None
        if sp is not None:
            # Value-class guard (#74/#76/#77): the per-skill value_class comes from
            # the classify-the-11 registry (see the `screen verdict` command). Every
            # non-transformative class → CANT_TELL_YET (wrong instrument) →
            # NOT_YET_RANKABLE, never a false EXCLUDED on a screen ceiling.
            v = screen_verdict(sp.p0, value_class=value_class_for(sp.skill_name))
            verdict = v.verdict
            cut_sub_reason = v.cut_sub_reason
            estimand = v.estimand_label  # pre-registry marker for store rows (#51)
            has_screen = True
            n_trials = sp.n_trials
        else:
            verdict = None
            cut_sub_reason = None
            estimand = None  # no verdict at all — nothing to scope
            has_screen = False
            n_trials = 0
        # A screened skill absent from (or with no) skills-root has an unsourced
        # standing cost (None), distinct from a real 0 for a never-loaded skill.
        desc_cost_opt: int | None
        desc_cost_opt, is_disable = library.get(skill, (None, False))
        inputs.append(
            SkillProfileInput(
                skill=skill,
                verdict=verdict,
                cut_sub_reason=cut_sub_reason,
                has_screen=has_screen,
                n_trials=n_trials,
                is_disable_model_invocation=is_disable,
                desc_token_cost=desc_cost_opt,
                fired_token_cost=None,  # HELD — no read-only runtime open path yet
                fired_usd=None,
                estimand=estimand,
            )
        )

    rows = build_skill_profile(inputs)

    # --- Render: SEPARATE columns, per-axis vocabularies ----------------------
    _disp_color = {"ADMITTED": "green", "EXCLUDED": "red", "NOT_YET_RANKABLE": "yellow"}
    table = Table(title="Skill evaluation profile (separated GRADE-style axes)", show_lines=True)
    table.add_column("skill", style="cyan", min_width=20, no_wrap=True)
    table.add_column("disposition", min_width=12, no_wrap=True)
    table.add_column("verdict", min_width=10, no_wrap=True)
    table.add_column("estimand", min_width=14, no_wrap=True)
    table.add_column("evidence-quality", min_width=14, no_wrap=True)
    table.add_column("desc-cost", justify="right", no_wrap=True)
    table.add_column("fired-cost", justify="right", no_wrap=True)
    if show_held_columns:
        table.add_column("effect (95% CrI)", justify="center", no_wrap=True)
        table.add_column("eff/cost", justify="right", no_wrap=True)

    for row in rows:
        disp = f"[{_disp_color[row.disposition]}]{row.disposition}[/]"
        if row.verdict is None:
            verdict_cell = "—"
        else:
            sub = f"({row.cut_sub_reason})" if row.cut_sub_reason else ""
            verdict_cell = f"{row.verdict}{sub}"
        desc_cell = "—" if row.desc_token_cost is None else f"{row.desc_token_cost:,}"
        fired_cell = "—" if row.fired_token_cost is None else f"{row.fired_token_cost:,}"
        # Estimand scope qualifier (#51): em-dash iff there is no verdict to scope.
        estimand_cell = "—" if row.estimand is None else f"[dim]{row.estimand}[/]"
        cells = [
            _sanitize_clause_text(row.skill, max_len=None),
            disp,
            verdict_cell,
            estimand_cell,
            row.evidence_quality,
            desc_cell,
            fired_cell,
        ]
        if show_held_columns:
            # Effect is held: never a bare point — an em-dash until a CrI exists.
            eff_cell = (
                "—" if row.effect is None else f"[{row.effect.ci_lo:.2f}, {row.effect.ci_hi:.2f}]"
            )
            effpc_cell = "—" if row.effect_per_cost is None else f"{row.effect_per_cost:.4f}"
            cells.extend([eff_cell, effpc_cell])
        table.add_row(*cells)

    _console.print(table)

    # --- Footer notes (mirror the 'screen verdict' honesty footer) ------------
    _console.print(
        "\n[dim]Axes are SEPARATE and not fused into any ranking scalar (GRADE / Guyatt"
        " 2008). evidence-quality is an ORDINAL label — compare, do not average"
        " (Velleman & Wilkinson 1993). A verdict is a hardness screen, not a paired"
        " measurement.[/]"
    )
    _console.print(
        "[dim]desc-cost is a chars/4 estimate of the always-on description-token standing"
        " tax (0 for disable-model-invocation skills — never loaded into context)."
        " fired-cost (the per-epoch ledger tax) is HELD: no sanctioned read-only open"
        " path exists for the runtime cost ledger yet.[/]"
    )
    if not library:
        _console.print(
            "[dim]No skills-root library: profiling screened skills only; the"
            " description-token standing-cost axis and full library enumeration are shown"
            " as '—'. UNMEASURABLE also depends on skills-root — the"
            " disable-model-invocation flag is frontmatter-sourced, so a"
            " disable-model-invocation skill profiled without skills-root cannot be"
            " labelled UNMEASURABLE.[/]"
        )
    if show_held_columns:
        _console.print(
            "[dim]effect (95% CrI) and eff/cost are HELD/scaffolded: the Stage-0 screen"
            " path yields no paired per-skill effect, so both render '—'. Effect is a"
            " Beta(1,1) equal-tailed 95% credible interval when measured — never a bare"
            " point.[/]"
        )


@screen.command("backfill")
@click.option(
    "--screens-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path(".private/microrun"),
    show_default=True,
    help="Root of the local Inspect .eval log tree (gitignored microrun data).",
)
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help="Persist the batch-1 manifest to the screen store (default: dry-run, no writes).",
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
def screen_backfill_cmd(
    screens_root: Path, execute: bool, evidence_db: Path, runtime_db: Path
) -> None:
    """Backfill the curated batch-1 screen manifest into the screen store.

    Ingests the batch-1 Stage-0 ``.eval`` logs (parsing needs the ``[inspect]``
    extra). Voided logs are stored INADMISSIBLE per the manifest's cited rulings;
    p0 excludes them. Without --execute, prints the manifest (the curated
    evidence-admissibility decisions) without touching any DB.
    """
    from skill_harness.subject.screen_backfill import (
        BATCH1_MANIFEST,
        apply_manifest,
        supersede_d4_screen_runs,
    )

    if not execute:
        _console.print("\n[bold yellow]DRY-RUN[/] — batch-1 screen manifest (no writes):")
        for entry in BATCH1_MANIFEST:
            mark = (
                "[green]admissible[/]"
                if entry.admissibility_state == "admissible"
                else (f"[red]inadmissible[/] ({entry.inadmissibility_reason})")
            )
            _console.print(f"  {entry.expected_skill}: {mark}")
            _console.print(f"    [dim]{entry.rel_path}[/]")
        _console.print("\n[yellow]Dry-run: no data written. Use --execute to persist.[/]")
        return

    with StorageContext(evidence_db, runtime_db) as ctx:
        report = apply_manifest(screens_root, ctx.evidence_conn)
        # #402: re-disposition the four D4-finding rows via the supersession path.
        # Idempotent: already-superseded rows are skipped.
        redispositioned = supersede_d4_screen_runs(ctx.evidence_conn)

    _console.print(f"\n[green]Backfilled[/] {len(report.ingested)} screens into {evidence_db}")
    if report.skipped:
        _console.print(
            f"[dim]Skipped {len(report.skipped)} manifest entr"
            f"{'y' if len(report.skipped) == 1 else 'ies'} already in the store (#430):[/]"
        )
        for line in report.skipped:
            _console.print(f"  [dim]{_sanitize_clause_text(line, max_len=None)}[/]")
    for result in report.ingested:
        state = result.admissibility_state
        color = "green" if state == "admissible" else "red"
        _console.print(
            f"  {result.skill_name}: [{color}]{state}[/] ({result.n_pass}/{result.n_trials} passed)"
        )
    if redispositioned:
        _console.print(
            f"\n[yellow]Re-dispositioned[/] {len(redispositioned)} screen run(s) "
            "via supersession (#402 D4 / stale-pin disposition table)."
        )
    if report.mismatches:
        _console.print("\n[bold red]AUDIT MISMATCHES[/] (manifest disagrees with stored evidence):")
        for m in report.mismatches:
            _console.print(f"  [red]{_sanitize_clause_text(m, max_len=None)}[/]")
        raise click.ClickException("backfill audit failed — see mismatches above")
    _console.print("\n[dim]Run 'screen verdict' to see the derived keep/cut verdicts.[/]")


@run.command("evaluate-paired")
@click.argument("run_id")
@click.argument("ratification_path", type=click.Path(exists=True, path_type=Path))
@click.argument(
    "value_class",
    type=click.Choice([vc.value for vc in ValueClass], case_sensitive=False),
)
@click.option(
    "--evidence-db",
    type=click.Path(path_type=Path),
    default=Path("./evidence.db"),
    show_default=True,
    help="Path to evidence DB (read-only; no writes, no API calls).",
)
def run_evaluate_paired(
    run_id: str,
    ratification_path: Path,
    value_class: str,
    evidence_db: Path,
) -> None:
    """Read-only paired-lane Gate-2 decision.

    Takes a paired RUN_ID, a ratification-record reference, and a VALUE_CLASS,
    and prints the decision, signed delta with its interval, pi_c line, and
    verdict — or a typed refusal.  Performs no writes and no API calls.

    The design used is the one in the referenced RATIFIED record; a DRAFT
    record, a missing record, or a field mismatch is a typed refusal naming
    the field.  Pair count != n_pairs returns COUNT_MISMATCH.
    """
    from skill_harness.aggregation.verdict import ValueClass as VC
    from skill_harness.cli.paired_gate2 import PairedGate2Refusal, paired_gate2_read

    try:
        vc = VC(value_class)
        paired_gate2_read(
            run_id,
            ratification_path,
            vc,
            evidence_db=evidence_db,
        )
    except PairedGate2Refusal as exc:
        _console.print(f"[red]REFUSAL[/]: {exc}")
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":  # pragma: no cover
    cli()
