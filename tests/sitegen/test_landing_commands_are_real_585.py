"""Every command the landing page prints is a command a stranger can run.

The landing page shipped `skill audit --help` as its only procedural line. No
such executable exists. A reader who followed the page's one instruction got
`FileNotFoundError`, because the console script this package declares is
`skill-harness`, not `skill`.

No test caught it. The page rendered, the build passed, and the suite was green,
because nothing bound the printed command to the packaging that has to serve it.
These tests bind the two.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_LANDING_COPY = _REPO / "docs" / "site" / "landing.md"
_PYPROJECT = _REPO / "pyproject.toml"

_COMMAND_LINE = re.compile(r"^command:\s*(?P<command>.+?)\s*$", re.MULTILINE)


def _declared_console_scripts() -> set[str]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return set(data.get("project", {}).get("scripts", {}))


def _printed_commands() -> list[str]:
    text = _LANDING_COPY.read_text(encoding="utf-8")
    return [match.group("command") for match in _COMMAND_LINE.finditer(text)]


def test_the_landing_copy_prints_at_least_one_command() -> None:
    """A vacuous pass is the failure mode these tests exist to avoid.

    Every assertion below iterates the printed commands. If the copy stopped
    naming any, they would all pass while saying nothing.
    """
    assert _printed_commands(), f"{_LANDING_COPY} names no command to check"


@pytest.mark.parametrize("command", _printed_commands())
def test_every_printed_command_names_a_real_program(command: str) -> None:
    """The first token is a program the reader can actually invoke.

    Either a declared console script of this package, or a tool the install
    line itself establishes. `skill` was neither.
    """
    program = command.split(maxsplit=1)[0]
    allowed = _declared_console_scripts() | {"pip", "python"}

    assert program in allowed, (
        f"{_LANDING_COPY} prints {command!r}, whose program {program!r} is not a "
        f"console script this package declares ({sorted(_declared_console_scripts())}) "
        "and is not pip or python"
    )


def test_the_audit_command_runs_and_exits_zero() -> None:
    """The audit line is executed, not read.

    The page claims the audit needs no key and touches no network, so it is
    runnable in the test environment. A command that parses but refuses its own
    documented invocation is the same defect one layer down.
    """
    audit = next(
        (c for c in _printed_commands() if "audit" in c),
        None,
    )
    assert audit is not None, f"{_LANDING_COPY} prints no audit command"

    fixture = _REPO / "tests" / "fixtures" / "sers" / "declared-synthetic-positive-control"
    skill_md = fixture / "SKILL.md"
    assert skill_md.is_file(), f"audit fixture missing at {skill_md}"

    argv = audit.split()
    if shutil.which(argv[0]) is None:
        argv = [sys.executable, "-m", "skill_harness", *argv[1:]]
    argv = [str(skill_md) if "SKILL.md" in part else part for part in argv]

    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=_REPO,
        check=False,
    )

    assert completed.returncode == 0, (
        f"the landing page's audit command exited {completed.returncode}\n"
        f"argv: {argv}\nstdout: {completed.stdout[:400]}\nstderr: {completed.stderr[:400]}"
    )


def test_the_shipped_copy_and_the_test_fixture_do_not_drift() -> None:
    """The fixture the site tests build from is the copy the site ships.

    They were identical when the landing page landed. Two copies of one
    document is how one of them goes stale, and this is the cheapest guard
    against the stale one being the published one.
    """
    fixture = _REPO / "tests" / "sitegen" / "fixtures" / "landing.md"
    assert fixture.read_text(encoding="utf-8") == _LANDING_COPY.read_text(encoding="utf-8"), (
        f"{fixture} has drifted from {_LANDING_COPY}"
    )
