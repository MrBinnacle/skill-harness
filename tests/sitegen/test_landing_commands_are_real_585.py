"""Every command this project publishes is a command a stranger can run.

The landing page shipped `skill audit --help` as its only procedural line. No
such executable exists. A reader who followed the page's one instruction got
`FileNotFoundError`, because the console script this package declares is
`skill-harness`, not `skill`.

No test caught it. The page rendered, the build passed, and the suite was green,
because nothing bound the printed command to the packaging that has to serve it.
These tests bind the two.

Issue #588 moved the install commands off the landing page. The page is now a
heading, four sentences and three pointers, and one pointer sends the reader to
the README's usage section. The rule did not stop applying; its subject moved.
So these tests follow the commands to `README.md` rather than being deleted with
the section that used to carry them. Deleting them would have retired a live
control because its original address went away, which is the failure mode the
docstring above describes one layer up.
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
_COMMAND_SOURCE = _REPO / "README.md"
_PYPROJECT = _REPO / "pyproject.toml"

# The fence language is matched as an alternation. Keying on ``bash`` alone
# means relabelling a block to ``shell`` or ``console`` drops its commands from
# this check while the suite stays green on whatever blocks remain, which is a
# vacuity the guard below cannot see.
_BASH_BLOCK = re.compile(
    r"^```(?:bash|sh|shell|console|zsh)\n(?P<body>.*?)^```", re.MULTILINE | re.DOTALL
)
_INLINE_COMMENT = re.compile(r"\s+#.*$")


def _declared_console_scripts() -> set[str]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return set(data.get("project", {}).get("scripts", {}))


def _printed_commands() -> list[str]:
    """Every command the README's bash blocks publish, as one string each.

    A trailing backslash continues a command onto the next line. Splitting on
    newlines alone would hand the program check an argument as if it were a
    program, which is a test failing on its own parsing rather than on the
    thing it is there to catch.
    """
    text = _COMMAND_SOURCE.read_text(encoding="utf-8")
    commands: list[str] = []
    for block in _BASH_BLOCK.finditer(text):
        pending = ""
        for line in block.group("body").splitlines():
            stripped = _INLINE_COMMENT.sub("", line).strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.endswith("\\"):
                pending += stripped[:-1].strip() + " "
                continue
            commands.append((pending + stripped).strip())
            pending = ""
        if pending:
            commands.append(pending.strip())
    return commands


def test_the_published_copy_prints_at_least_one_command() -> None:
    """A vacuous pass is the failure mode these tests exist to avoid.

    Every assertion below iterates the printed commands. If the copy stopped
    naming any, they would all pass while saying nothing.
    """
    assert _printed_commands(), f"{_COMMAND_SOURCE} names no command to check"


def test_the_rendered_landing_page_prints_no_command_of_its_own(tmp_path: Path) -> None:
    """Issue #588: the page is a heading, four sentences and three pointers.

    This is the other half of the move. The commands are checked against the
    README above; here the page is held to the shape that sent them there, so a
    later edit cannot put an unchecked command back on the front page.

    A first version of this test grepped the copy file for a ``command:`` field.
    An independent reviewer pointed out that a command can return as hero prose,
    a pointer label or a supporting line, and that version would stay green. So
    this reads the RENDERED page and looks for any console script this package
    declares, wherever it appears. The rendered page is the surface a stranger
    meets, and the copy file's field names are not.
    """
    output = _build_site_for_test(tmp_path)
    page = (output / "index.html").read_text(encoding="utf-8")
    text = re.sub(r"<[^>]+>", " ", page)

    programs = sorted(_declared_console_scripts() | {"pip install", "python -m"})
    found = [program for program in programs if program in text]
    assert not found, (
        f"the rendered landing page names {found}. Issue #588 moved install behind a "
        f"pointer, and {_COMMAND_SOURCE.name} is where the command-reality tests look. "
        "A command on this page is unchecked by them."
    )


def _build_site_for_test(tmp_path: Path) -> Path:
    from skill_harness.sitegen import build_site

    output = tmp_path / "site"
    build_site(
        receipts_dir=_REPO / "docs" / "sers" / "receipts",
        schema_path=_REPO / "docs" / "sers" / "sers.schema.json",
        extraction_path=None,
        output_dir=output,
        marker="command-shape-585",
        landing=True,
        landing_copy_path=_LANDING_COPY,
    )
    return output


@pytest.mark.parametrize("command", _printed_commands())
def test_every_printed_command_names_a_real_program(command: str) -> None:
    """The first token is a program the reader can actually invoke.

    Either a declared console script of this package, or a tool the install
    line itself establishes. `skill` was neither.
    """
    program = command.split(maxsplit=1)[0]
    allowed = _declared_console_scripts() | {"pip", "python"}

    assert program in allowed, (
        f"{_COMMAND_SOURCE} prints {command!r}, whose program {program!r} is not a "
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
    assert audit is not None, f"{_COMMAND_SOURCE} prints no audit command"

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
