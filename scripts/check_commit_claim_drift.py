#!/usr/bin/env python3
"""Fail when the dated commit-count claim on ``docs/why-this-exists.md`` has gone stale.

Why this exists (steering repo issue 61). The page states how many commits the skill
collection and this instrument each carry, with a measurement date and the two shell
commands a reader can run to reproduce the figures. Two tests in
``tests/test_readme_origin_223.py`` guard that claim, and both lock its SHAPE: a date, two
integers, the two commands. Neither can tell whether the integers are still true. The first
pair (71 against 323) stood for eighteen days while the real counts moved to 152 against
511; the counts have moved again since. Each correction so far was a person noticing.

The rule. The prose figure is a CACHE of a derivation the page itself states. This check
runs that derivation and compares. The figures the page asserts are parsed, never assumed;
the commands the page states are parsed and executed, never re-typed here. Lock the shape,
not the value: nothing in this file knows what the right count is.

Two derivation bases. By default each command is run as the page states it: a fresh clone
into a temporary directory, then ``rev-list --count`` on the ref the command names. That is
the basis the page promises a reader, and it is the only basis a shallow CI checkout cannot
fake. ``--local NAME=PATH`` substitutes an existing clone for the directory the command
would create, for a maintainer working offline; the count is then taken in that clone at the
same ref, and whatever that clone's ref points at is what gets counted.

Exit 0 when both derived counts equal the figures the page asserts. Exit 1 when either
disagrees, naming the surface, the asserted figure and the derived one. Exit 2 when the
measurement cannot be taken (page or section missing, claim or commands unparseable, git
absent or failing), because a checker that cannot measure must not report PASS.

Companion in the steering repository: ``check_model_id_drift.py`` applies the same
prose-is-the-cache rule to model ids and uses the same exit codes.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "why-this-exists.md"
SECTION = "The size of the detour"

# The sentence the page asserts. Same shape test_readme_origin_223.py locks, so a page that
# passes that test is parseable here and a page this check cannot parse fails that test too.
CLAIM_RE = re.compile(
    r"Measured on (\d{4}-\d{2}-\d{2}):\s*\*\*(\d+) commits of collection"
    r" against (\d+) commits of machinery"
)

# One derivation command as the page states it: clone, then count on a named ref. The three
# captures are the clone source, the directory the clone lands in, and the ref counted.
COMMAND_RE = re.compile(
    r"^git clone (\S+)\s+&&\s+git -C (\S+)\s+rev-list --count (\S+)\s*$", re.MULTILINE
)

SURFACES = ("collection", "machinery")


class CannotMeasure(Exception):
    """The check could not take its measurement. Never a PASS and never a FAIL."""


@dataclass(frozen=True)
class Derivation:
    """One derivation command parsed off the page."""

    source: str
    directory: str
    ref: str


@dataclass(frozen=True)
class Claim:
    """The dated figures the page asserts."""

    measured_on: str
    collection: int
    machinery: int


@dataclass(frozen=True)
class Result:
    claim: Claim
    derived: dict[str, int]
    disagreements: list[str] = field(default_factory=list)

    @property
    def agrees(self) -> bool:
        return not self.disagreements


def section_text(page_text: str, heading: str = SECTION) -> str:
    """The body of one ``##`` section. Raises CannotMeasure when the heading is absent."""
    marker = f"## {heading}"
    start = page_text.find(marker)
    if start == -1:
        raise CannotMeasure(f"section '## {heading}' not found on the page")
    end = page_text.find("\n## ", start + len(marker))
    return page_text[start:] if end == -1 else page_text[start:end]


def parse_claim(section: str) -> Claim:
    """The dated figures. Raises CannotMeasure when the sentence is not there to compare."""
    match = CLAIM_RE.search(section)
    if match is None:
        raise CannotMeasure(
            "no dated commit-count claim found: expected"
            " 'Measured on YYYY-MM-DD: **N commits of collection against M commits of machinery'"
        )
    return Claim(match[1], int(match[2]), int(match[3]))


def parse_derivations(section: str) -> dict[str, Derivation]:
    """The two derivation commands, keyed by surface in the order the claim sentence names them.

    The page lists the collection's command first and the machinery's second, mirroring
    "N commits of collection against M commits of machinery". Anything other than exactly two
    commands is a page this check cannot read, not a pass.
    """
    found = [Derivation(*m.groups()) for m in COMMAND_RE.finditer(section)]
    if len(found) != len(SURFACES):
        raise CannotMeasure(
            f"expected {len(SURFACES)} derivation commands of the form"
            f" 'git clone SRC && git -C DIR rev-list --count REF', found {len(found)}"
        )
    return dict(zip(SURFACES, found, strict=True))


def _git(args: list[str], cwd: Path) -> str:
    """Run one git command; any failure is a measurement failure, not a verdict."""
    try:
        proc = subprocess.run(  # noqa: S603 -- argv is built from the page's own command
            ["git", *args],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CannotMeasure("git is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise CannotMeasure(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def count_commits(derivation: Derivation, local: Mapping[str, Path] | None = None) -> int:
    """Run one derivation command and return the count it yields.

    Without a ``local`` substitute for the derivation's directory, the command runs as the page
    states it: a fresh clone into a temporary directory, then the count. With one, the count is
    taken in the substitute clone and no network is touched.
    """
    substitute = (local or {}).get(derivation.directory)
    if substitute is not None:
        if not substitute.is_dir():
            raise CannotMeasure(f"local clone for '{derivation.directory}' not found: {substitute}")
        return _count_in(substitute, derivation.ref)
    with tempfile.TemporaryDirectory(prefix="commit-claim-") as tmp:
        target = Path(tmp) / derivation.directory
        _git(["clone", "--quiet", derivation.source, str(target)], cwd=Path(tmp))
        return _count_in(target, derivation.ref)


def _count_in(clone: Path, ref: str) -> int:
    text = _git(["rev-list", "--count", ref], cwd=clone)
    try:
        return int(text)
    except ValueError as exc:
        raise CannotMeasure(
            f"rev-list --count {ref} in {clone} returned non-integer {text!r}"
        ) from exc


def check(page_text: str, derive: Callable[[Derivation], int]) -> Result:
    """Compare the page's asserted figures with what its own derivations yield now."""
    section = section_text(page_text)
    claim = parse_claim(section)
    derivations = parse_derivations(section)
    derived = {surface: derive(derivations[surface]) for surface in SURFACES}
    disagreements = [
        f"{surface}: page asserts {getattr(claim, surface)}, derivation yields {derived[surface]}"
        for surface in SURFACES
        if getattr(claim, surface) != derived[surface]
    ]
    return Result(claim, derived, disagreements)


def format_report(result: Result) -> str:
    out = ["COMMIT CLAIM DRIFT CHECK", "=" * 68, ""]
    out.append(f"Page asserts (measured on {result.claim.measured_on}):")
    for surface in SURFACES:
        asserted, derived = getattr(result.claim, surface), result.derived[surface]
        flag = "ok  " if asserted == derived else "FAIL"
        out.append(f"{flag} {surface:<11} asserted {asserted:>6}  derived {derived:>6}")
    out.append("")
    if result.agrees:
        out.append("PASS: both figures on the page match a fresh derivation.")
    else:
        out.append(f"FAIL: {len(result.disagreements)} stale figure(s) on the page.")
        out.extend(f"  {line}" for line in result.disagreements)
        out.append(
            "Re-measure with the page's own commands, update both figures and the date together."
        )
    return "\n".join(out)


def _parse_local(items: list[str]) -> dict[str, Path]:
    local: dict[str, Path] = {}
    for item in items:
        name, sep, raw = item.partition("=")
        if not sep or not name or not raw:
            raise CannotMeasure(f"--local expects NAME=PATH, got {item!r}")
        local[name] = Path(raw)
    return local


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--page", type=Path, default=PAGE, help="page carrying the claim")
    parser.add_argument(
        "--local",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="use an existing clone at PATH for the command that clones into NAME",
    )
    return parser


def main(argv: list[str] | None = None, derive: Callable[[Derivation], int] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if not args.page.is_file():
            raise CannotMeasure(f"page not found: {args.page}")
        local = _parse_local(args.local)
        derive = derive or (lambda d: count_commits(d, local))
        result = check(args.page.read_text(encoding="utf-8"), derive)
    except CannotMeasure as exc:
        print("COMMIT CLAIM DRIFT CHECK")
        print(f"REFUSED: {exc}")
        print("The measurement could not be taken. This is not a PASS.")
        return 2
    print(format_report(result))
    return 0 if result.agrees else 1


if __name__ == "__main__":
    sys.exit(main())
