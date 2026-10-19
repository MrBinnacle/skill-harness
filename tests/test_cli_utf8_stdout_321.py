"""Regression test for #321: `skill audit` crashed on a non-UTF-8 console.

The defect: `src/skill_harness/cli/main.py` prints report text containing
non-ASCII characters (U+2192 RIGHTWARDS ARROW among others) through a Rich
`Console` that writes to `sys.stdout`. On a Windows console using cp1252
(the platform default), the write raised an unhandled `UnicodeEncodeError`
partway through the report.

Why this cannot be a captured-text test: pytest's own capture object accepts
`str` directly and never routes through the console's byte encoder, so an
assertion on captured text cannot see this failure -- that is precisely why
the existing CI Windows job passed on the broken code. This test instead
drives the CLI as a real subprocess with the child's stdio encoding forced
away from UTF-8, so the child process's own encoder is exercised.

Guarantee scope (ticket #321, "Revisit if" clause): GitHub's Windows CI
runners do not necessarily present cp1252 as the ambient console code page,
so this test does not rely on the host's locale at all. It forces the non-
UTF-8 encoding explicitly via PYTHONIOENCODING/PYTHONUTF8 env vars, which
CPython honors as an override regardless of locale (verified: a child
process launched with these two vars reports
`sys.stdout.encoding == "cp1252"` on this host). The claim this test proves
is therefore the slightly narrower one named in the ticket: `skill audit`
exits 0 when its stdout/stderr encoding is forced to a non-UTF-8 codec via
PYTHONIOENCODING -- not specifically "on a cp1252 Windows console", though
that was the original reproduction and is exercised too when run on such a
host (PYTHONUTF8 unset, ambient cp1252, see test_skill_audit.py's normal
CliRunner coverage for the offline-audit behavior itself).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

GOOD_SKILL = """---
name: processing-pdfs
description: Extracts text and tables from PDF files. Use when working with PDFs.
---

# PDF Processing

Use pdfplumber for text extraction from `scripts/helper.py`.
"""


def test_skill_audit_exits_zero_under_forced_non_utf8_stdout(tmp_path: Path) -> None:
    """`skill audit` must not crash when the process's own stdio encoding
    cannot represent the report's non-ASCII characters (#321).

    Forces PYTHONIOENCODING=cp1252 and PYTHONUTF8=0 on the child so its
    sys.stdout/sys.stderr are cp1252-encoded regardless of the host's actual
    console, then asserts the process still exits 0. Output is captured as
    raw bytes and never decoded by this test -- decoding here would let this
    test's own encoding choice mask the child's, which is the same trap the
    ticket names for pytest's text capture.
    """
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(GOOD_SKILL, encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    env["PYTHONUTF8"] = "0"

    result = subprocess.run(
        [sys.executable, "-m", "skill_harness", "skill", "audit", str(skill_path)],
        env=env,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, (
        "skill audit exited "
        f"{result.returncode} under forced non-UTF-8 stdout encoding "
        f"(PYTHONIOENCODING=cp1252, PYTHONUTF8=0); stderr tail: "
        f"{result.stderr[-2000:]!r}"
    )
