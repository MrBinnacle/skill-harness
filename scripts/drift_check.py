"""Drift check — declarative contract table guarding locked public contracts.

Why this exists (#43, landed by #53): locked numeric contracts, registered
vocabulary, and public claim sentences had no mechanical guard against silent
drift — cross-site equality of the pass-rule thresholds was assumed, never
enforced. This script is that guard, the third instance of the house pattern
(scripts/release_gate.py = enumerated checks with listed failures;
the structural-bans CI job = token bans).

Contract rows are DATA (the tables below): adding a contract is a table row,
not new code. Nine live rows ship checked (DC-1..DC-6 from #43/#53; DC-7 and
DC-8 activated by the PR landing skill_harness/oc; DC-11 activated by the PR
landing the Gate-2 cross-checks — both per the #43 same-PR extension rule);
four registered PLANNED rows (DC-9/DC-10/DC-12/DC-13) print as PLANNED until
the PR landing each surface activates them (activation happens in that same
PR, never later). New rows enter only via a ratified decision or a locked
INVARIANTS entry.

Registered EXPECTATIONS live in this table; current STATE is read from the
tree. The expectation is deliberately never imported from the surface being
checked — drift would be unobservable otherwise.

Output convention (F7, ratified on #43): a green run prints every covered
contract ID + one-line summary, then the coverage boundary line, then the
PLANNED rows, then the token-ban allowlist (even when empty). Failures are ALL
listed (never first-fail), exit 1. Output is pure ASCII (Windows console
safety).

Run locally: ``python scripts/drift_check.py [--root <repo-root>]``.
Exit code 0 = no drift; 1 = at least one contract violated (each listed).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Check vocabulary — the small set of check kinds rows are assembled from
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValueSite:
    """A code constant pinned by regex: every match's groups must equal
    ``expected``; zero matches is drift too (a rename hides the constant)."""

    path: str
    pattern: str
    expected: tuple[str, ...]


@dataclass(frozen=True)
class RegisteredText:
    """A registered claim sentence / doc quote: the whitespace-normalized file
    must contain the normalized registered copy verbatim."""

    path: str
    text: str


@dataclass(frozen=True)
class TokenBan:
    """A banned token (structural-bans pattern). ``exemptions`` are the
    structural definition-site/scanner self-exclusions (E1b pattern) — NOT
    allowlist entries; the allowlist is a separate, printed surface.
    ``scan_repo_level`` adds the root-level ``*.md`` files + ``pyproject.toml``
    to the scan (the repo-wide rows keep it on; a package-scoped row like
    DC-11 turns it off so the scan matches its registered scope exactly)."""

    term: str
    roots: tuple[str, ...]
    suffixes: frozenset[str]
    exemptions: frozenset[str]
    scan_repo_level: bool = True


@dataclass(frozen=True)
class ImportScanBan:
    """An import-direction ban: no import statement in any ``.py`` file under
    ``package_root`` may reference a forbidden module name. Only import lines
    are scanned (conservative: a forbidden token anywhere on an import line
    fails). An empty or missing package is drift too - the ban must have a
    surface to guard."""

    package_root: str
    forbidden: tuple[str, ...]


@dataclass(frozen=True)
class EstimandContract:
    """The registry enum must hold EXACTLY the registered values, and every
    machine-readable ``estimand:`` field in docs must use a registered value
    (or the honest pre-registry ``n/a`` marker) — no other token admitted."""

    registry_path: str
    registered_values: frozenset[str]
    doc_allowed_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class LiveRow:
    dc_id: str
    summary: str
    value_sites: tuple[ValueSite, ...] = ()
    registered_texts: tuple[RegisteredText, ...] = ()
    live_pointers: tuple[str, ...] = ()
    token_bans: tuple[TokenBan, ...] = ()
    estimand_contract: EstimandContract | None = None
    import_ban: ImportScanBan | None = None


@dataclass(frozen=True)
class PlannedRow:
    dc_id: str
    summary: str
    activates: str


# ---------------------------------------------------------------------------
# The contract table (ratified on #43; DC-12 amendment from #47, DC-13 from #41)
# ---------------------------------------------------------------------------

_BAN_SCAN_ROOTS = ("src", "tests", "docs", "scripts", "examples")
_BAN_SCAN_SUFFIXES = frozenset({".py", ".md", ".txt", ".toml", ".yaml", ".yml"})
# Structural E1b self-exclusions: the registry definition site, the pytest
# scan, this script's own table, and this script's tests all carry the banned
# token by necessity. NOT allowlist entries — TOKEN_BAN_ALLOWLIST stays empty.
_BAN_STRUCTURAL_EXEMPTIONS = frozenset(
    {
        "src/skill_harness/semantics.py",
        "tests/test_semantics.py",
        "scripts/drift_check.py",
        "tests/test_drift_check.py",
    }
)

TOKEN_BAN_ALLOWLIST: frozenset[str] = frozenset()
"""EMPTY by ratified decision (#43): no speculative carve-outs — an unused
allowlist is an invisible coverage hole. Grows only by dated amendment (the
first legitimate QUOTE of a banned term in an append-only record adds that
file here, in that PR, with a dated note). Printed even when empty."""

# DC-11 scope: the registered row bans method tokens IN oc/ (#37 item 4 bans
# the exact conditional McNemar test and Wald intervals by name), so the scan
# roots are exactly the package. crosschecks.py is the E1b definition site:
# its docstrings must NAME the banned methods and quote the banning
# literature verbatim (FLL 2013) — a structural exemption, printed, never an
# allowlist entry.
_OC_BAN_ROOTS = ("src/skill_harness/oc",)
_OC_BAN_EXEMPTIONS = frozenset({"src/skill_harness/oc/crosschecks.py"})

LIVE_ROWS: tuple[LiveRow, ...] = (
    LiveRow(
        dc_id="DC-1",
        summary="pass-rule thresholds 0.60/0.95/0.05 (fit/stopping/status + doc quotes)",
        value_sites=(
            ValueSite(
                "src/skill_harness/aggregation/fit.py",
                r"^WIN_RATE_THRESHOLD: float = ([0-9.]+)$",
                ("0.60",),
            ),
            ValueSite(
                "src/skill_harness/ablation/stopping.py",
                r"^WIN_RATE_THRESHOLD: Final\[float\] = ([0-9.]+)$",
                ("0.60",),
            ),
            ValueSite(
                "src/skill_harness/ablation/stopping.py",
                r"^PASS_PROB_THRESHOLD: Final\[float\] = ([0-9.]+)$",
                ("0.95",),
            ),
            ValueSite(
                "src/skill_harness/ablation/stopping.py",
                r"^FAIL_PROB_THRESHOLD: Final\[float\] = ([0-9.]+)$",
                ("0.05",),
            ),
            ValueSite(
                "src/skill_harness/aggregation/status.py",
                r"^PASS_PROB_THRESHOLD: float = ([0-9.]+)$",
                ("0.95",),
            ),
            ValueSite(
                "src/skill_harness/aggregation/status.py",
                r"^FAIL_PROB_THRESHOLD: float = ([0-9.]+)$",
                ("0.05",),
            ),
        ),
        registered_texts=(
            RegisteredText("docs/INVARIANTS.md", "P(win_rate > 0.60) >= 0.95"),
            RegisteredText("docs/INVARIANTS.md", "P(win_rate > 0.60) <= 0.05"),
            RegisteredText("docs/INVARIANTS.md", "0.60/0.95/0.05"),
        ),
    ),
    LiveRow(
        dc_id="DC-2",
        summary="sampling schedule N_MIN=8 / N_INC=4 / N_MAX=40 (stopping/status + PRD quotes)",
        value_sites=(
            ValueSite(
                "src/skill_harness/ablation/stopping.py",
                r"^N_MIN: Final\[int\] = (\d+)$",
                ("8",),
            ),
            ValueSite(
                "src/skill_harness/ablation/stopping.py",
                r"^N_INC: Final\[int\] = (\d+)$",
                ("4",),
            ),
            ValueSite(
                "src/skill_harness/ablation/stopping.py",
                r"^N_MAX: Final\[int\] = (\d+)$",
                ("40",),
            ),
            ValueSite(
                "src/skill_harness/aggregation/status.py",
                r"^N_MIN: int = (\d+)$",
                ("8",),
            ),
        ),
        registered_texts=(
            RegisteredText("docs/PRD.md", "`N_min = 8` per condition pair"),
            RegisteredText("docs/PRD.md", "`N_inc = 4`"),
            RegisteredText("docs/PRD.md", "`N_max = 40`"),
        ),
    ),
    LiveRow(
        dc_id="DC-3",
        summary='"per-protocol" token ban, repo-wide, allowlist EMPTY (E9(R1) rule, #36)',
        token_bans=(
            TokenBan(
                term="per-protocol",
                roots=_BAN_SCAN_ROOTS,
                suffixes=_BAN_SCAN_SUFFIXES,
                exemptions=_BAN_STRUCTURAL_EXEMPTIONS,
            ),
        ),
        value_sites=(
            # Cross-site: the registry's own ban constants must state the same
            # registered term and the same empty allowlist this table states.
            ValueSite(
                "src/skill_harness/semantics.py",
                r'^BANNED_DECISION_TERMS: tuple\[str, \.\.\.\] = \("([^"]+)",\)$',
                ("per-protocol",),
            ),
            ValueSite(
                "src/skill_harness/semantics.py",
                r"^BANNED_TERM_ALLOWLIST: frozenset\[str\] = (frozenset\(\))$",
                ("frozenset()",),
            ),
        ),
    ),
    LiveRow(
        dc_id="DC-4",
        summary="estimand names: registry enum == the registered pair; no other token in docs",
        estimand_contract=EstimandContract(
            registry_path="src/skill_harness/semantics.py",
            registered_values=frozenset({"treatment-policy", "hypothetical"}),
            doc_allowed_prefixes=("treatment-policy", "hypothetical", "n/a"),
        ),
    ),
    LiveRow(
        dc_id="DC-5",
        summary="launch-trigger sentence registered verbatim at both README sites",
        registered_texts=(
            RegisteredText(
                "README.md",
                "A sized benefit run launches only on the first task whose "
                "no-skill screen returns a pass rate below 1",
            ),
            RegisteredText(
                "README.md",
                "a sized benefit run launches only when a screen returns a sub-1 pass rate",
            ),
        ),
    ),
    LiveRow(
        dc_id="DC-6",
        summary="spend-gating sentence registered (README + INVARIANTS) + enforcement pointer live",
        registered_texts=(
            RegisteredText(
                "README.md",
                "Every command that can spend money is dry-run by default; "
                "`--execute` is required to spend",
            ),
            RegisteredText(
                "docs/INVARIANTS.md",
                "`--execute` is required before the command performs writes or makes LLM API calls",
            ),
        ),
        live_pointers=("src/skill_harness/cli/main.py",),
    ),
    LiveRow(
        dc_id="DC-7",
        summary=(
            "oc grid constants GRID_N_MIN=6/GRID_N_MAX=40 == doc quotes + #40-provenance comment"
        ),
        value_sites=(
            ValueSite(
                "src/skill_harness/oc/conventions.py",
                r"^GRID_N_MIN: Final\[int\] = (\d+)$",
                ("6",),
            ),
            ValueSite(
                "src/skill_harness/oc/conventions.py",
                r"^GRID_N_MAX: Final\[int\] = (\d+)$",
                ("40",),
            ),
        ),
        registered_texts=(
            # The #40-provenance comment at the definition site (one line each
            # so whitespace normalization keeps the contains-check exact).
            RegisteredText(
                "src/skill_harness/oc/conventions.py",
                "Provenance: ratified decision #40 fixes the full integer grid n = 6-40;",
            ),
            RegisteredText(
                "src/skill_harness/oc/conventions.py",
                "ceiling is fixed by ratified decision, not by the legacy rule (#42",
            ),
            # The locked INVARIANTS entry (doc quotes).
            RegisteredText(
                "docs/INVARIANTS.md",
                "The `skill_harness.oc` engine enumerates the full integer grid `n = 6-40`",
            ),
            RegisteredText(
                "docs/INVARIANTS.md",
                "`GRID_N_MIN = 6` / `GRID_N_MAX = 40`",
            ),
            RegisteredText(
                "docs/INVARIANTS.md",
                "presentation highlight, never a grid bound",
            ),
        ),
    ),
    LiveRow(
        dc_id="DC-8",
        summary="oc import-direction ban: no ablation/subject/stopping imports inside oc/",
        import_ban=ImportScanBan(
            package_root="src/skill_harness/oc",
            forbidden=("ablation", "subject", "stopping"),
        ),
    ),
    LiveRow(
        dc_id="DC-11",
        summary=(
            "banned-methods tokens in oc/: 'exact conditional'/'exact_conditional'/'wald' "
            "(mid-p only + Newcombe/Tango only, #37 item 4)"
        ),
        token_bans=(
            TokenBan(
                term="exact conditional",
                roots=_OC_BAN_ROOTS,
                suffixes=frozenset({".py"}),
                exemptions=_OC_BAN_EXEMPTIONS,
                scan_repo_level=False,
            ),
            TokenBan(
                term="exact_conditional",
                roots=_OC_BAN_ROOTS,
                suffixes=frozenset({".py"}),
                exemptions=_OC_BAN_EXEMPTIONS,
                scan_repo_level=False,
            ),
            TokenBan(
                term="wald",
                roots=_OC_BAN_ROOTS,
                suffixes=frozenset({".py"}),
                exemptions=_OC_BAN_EXEMPTIONS,
                scan_repo_level=False,
            ),
        ),
    ),
)

PLANNED_ROWS: tuple[PlannedRow, ...] = (
    PlannedRow(
        "DC-9",
        "PAIR_COST token ban in src/skill_harness/ (costs live from PRICE_PER_MTOK, #40)",
        "the PR-2 change landing the frontier-assembly cost layer",
    ),
    PlannedRow(
        "DC-10",
        "budget values: $35 per-evaluation cap + $100 DAILY_CAP_HARD_CEILING_USD == doc quotes",
        "the PR-2 change landing the budget surfaces (#40)",
    ),
    PlannedRow(
        "DC-12",
        "RAT record internal consistency: hard_cap <= $35 and >= worst-case cost; "
        "self-certified records carry the disclosure line (#47)",
        "the PR landing the first docs/ratifications/RAT-*.md record",
    ),
    PlannedRow(
        "DC-13",
        "OBS ledger contract: front-matter parse + classification-state and "
        "prose-count consistency (#41)",
        "activation owed - the surface landed in PR #60 before this script "
        "existed, so the #43 same-PR rule could not fire; the next PR touching "
        "docs/observations/ activates it (see #53 PR record)",
    ),
)

COVERAGE_BOUNDARY_LINE = (
    "Coverage boundary: coverage is EXACTLY the list above; no other doc claim is checked."
)


# ---------------------------------------------------------------------------
# Check engine
# ---------------------------------------------------------------------------


def _normalized(text: str) -> str:
    """Collapse whitespace and strip blockquote markers so registered copies
    match across line wraps and `> ` quoting."""
    lines = [line.lstrip().removeprefix(">").lstrip() for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _read(root: Path, rel: str) -> str | None:
    path = root / rel
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _check_value_site(root: Path, site: ValueSite) -> list[str]:
    text = _read(root, site.path)
    if text is None:
        return [f"{site.path}: file missing (value site unreachable)"]
    matches = [m.groups() for m in re.finditer(site.pattern, text, re.MULTILINE)]
    if not matches:
        return [
            f"{site.path}: pattern {site.pattern!r} matched nothing - "
            "the pinned constant is gone or renamed"
        ]
    return [
        f"{site.path}: expected {'/'.join(site.expected)} but found {'/'.join(found)}"
        for found in matches
        if tuple(found) != site.expected
    ]


def _check_registered_text(root: Path, reg: RegisteredText) -> list[str]:
    text = _read(root, reg.path)
    if text is None:
        return [f"{reg.path}: file missing (registered text unreachable)"]
    if _normalized(reg.text) not in _normalized(text):
        return [f"{reg.path}: registered copy not found: {reg.text!r}"]
    return []


def _check_pointer(root: Path, rel: str) -> list[str]:
    if not (root / rel).is_file():
        return [f"enforcement pointer dead: {rel} does not exist"]
    return []


def _iter_ban_files(root: Path, ban: TokenBan) -> list[Path]:
    files: list[Path] = []
    for sub in ban.roots:
        base = root / sub
        if not base.is_dir():
            continue
        files.extend(
            p
            for p in base.rglob("*")
            if p.is_file() and p.suffix in ban.suffixes and "__pycache__" not in p.parts
        )
    if ban.scan_repo_level:
        files.extend(p for p in root.glob("*.md"))
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            files.append(pyproject)
    return files


def _check_token_ban(root: Path, ban: TokenBan) -> list[str]:
    pattern = re.compile(re.escape(ban.term), re.IGNORECASE)
    exempt = ban.exemptions | TOKEN_BAN_ALLOWLIST
    failures: list[str] = []
    for path in _iter_ban_files(root, ban):
        rel = path.relative_to(root).as_posix()
        if rel in exempt:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                failures.append(f"banned term {ban.term!r} at {rel}:{lineno}")
    return failures


def _check_import_ban(root: Path, ban: ImportScanBan) -> list[str]:
    base = root / ban.package_root
    files = sorted(base.rglob("*.py")) if base.is_dir() else []
    files = [p for p in files if "__pycache__" not in p.parts]
    if not files:
        return [f"{ban.package_root}: no .py files found (import-direction ban unreachable)"]
    import_line = re.compile(r"^\s*(?:from|import)\s")
    failures: list[str] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if import_line.match(line) and any(tok in line for tok in ban.forbidden):
                failures.append(f"forbidden import direction at {rel}:{lineno}: {line.strip()!r}")
    return failures


def _check_estimand_contract(root: Path, contract: EstimandContract) -> list[str]:
    failures: list[str] = []
    text = _read(root, contract.registry_path)
    if text is None:
        return [f"{contract.registry_path}: registry file missing"]
    block_match = re.search(
        r"^class Estimand\(StrEnum\):(.*?)(?=^class |\Z)", text, re.MULTILINE | re.DOTALL
    )
    if block_match is None:
        return [f"{contract.registry_path}: class Estimand(StrEnum) not found"]
    members = re.findall(r'^    [A-Z_]+ = "([^"]+)"$', block_match.group(1), re.MULTILINE)
    if set(members) != contract.registered_values or len(members) != len(
        contract.registered_values
    ):
        failures.append(
            f"{contract.registry_path}: Estimand members {sorted(members)} != "
            f"registered pair {sorted(contract.registered_values)}"
        )
    doc_files = (
        [p for p in (root / "docs").rglob("*.md") if p.is_file()]
        if (root / "docs").is_dir()
        else []
    )
    readme = root / "README.md"
    if readme.is_file():
        doc_files.append(readme)
    for path in doc_files:
        rel = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(content.splitlines(), start=1):
            for m in re.finditer(r"estimand:\s*`?([^\n`]*)", line):
                value = m.group(1).strip()
                if value and not value.startswith(contract.doc_allowed_prefixes):
                    failures.append(f"unregistered estimand token at {rel}:{lineno}: {value!r}")
    return failures


def _run_row(root: Path, row: LiveRow) -> list[str]:
    failures: list[str] = []
    for site in row.value_sites:
        failures.extend(_check_value_site(root, site))
    for reg in row.registered_texts:
        failures.extend(_check_registered_text(root, reg))
    for pointer in row.live_pointers:
        failures.extend(_check_pointer(root, pointer))
    for ban in row.token_bans:
        failures.extend(_check_token_ban(root, ban))
    if row.estimand_contract is not None:
        failures.extend(_check_estimand_contract(root, row.estimand_contract))
    if row.import_ban is not None:
        failures.extend(_check_import_ban(root, row.import_ban))
    return failures


# ---------------------------------------------------------------------------
# Report (F7 output convention) + entry point
# ---------------------------------------------------------------------------


@dataclass
class Report:
    failures_by_row: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_failures(self) -> int:
        return sum(len(v) for v in self.failures_by_row.values())


def run_drift_check(root: Path) -> Report:
    report = Report()
    for row in LIVE_ROWS:
        report.failures_by_row[row.dc_id] = _run_row(root, row)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repo root to check (default: this script's repo)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    report = run_drift_check(root)

    print(f"Drift check over {len(LIVE_ROWS)} live contract(s):")
    for row in LIVE_ROWS:
        failures = report.failures_by_row[row.dc_id]
        if failures:
            print(f"  FAIL     {row.dc_id}  {row.summary}")
            for failure in failures:
                print(f"           FAIL {row.dc_id}: {failure}")
        else:
            print(f"  OK       {row.dc_id}  {row.summary}")
    print(COVERAGE_BOUNDARY_LINE)
    print("PLANNED (registered, not yet checked):")
    for planned in PLANNED_ROWS:
        print(f"  PLANNED  {planned.dc_id}  {planned.summary} [activates: {planned.activates}]")
    if TOKEN_BAN_ALLOWLIST:
        entries = ", ".join(sorted(TOKEN_BAN_ALLOWLIST))
        print(f"Token-ban allowlist (grows only by dated amendment): {entries}")
    else:
        print("Token-ban allowlist (grows only by dated amendment): EMPTY")
    # F7 visibility: structural exemptions are carve-outs too — print them so
    # the ban's true coverage is never overstated by the EMPTY allowlist line.
    # Union across every live token ban (DC-3 repo-wide + DC-11 oc-scoped).
    all_exemptions: set[str] = set()
    for row in LIVE_ROWS:
        for ban in row.token_bans:
            all_exemptions |= ban.exemptions
    print("Structural scan exemptions (definition sites + scan machinery, not allowlist entries):")
    for rel in sorted(all_exemptions):
        print(f"  EXEMPT   {rel}")

    if report.total_failures:
        print(f"DRIFT CHECK: BLOCKED - {report.total_failures} contract violation(s) listed above.")
        return 1
    print(f"DRIFT CHECK: PASS - all {len(LIVE_ROWS)} live contracts hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
