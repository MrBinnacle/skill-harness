#!/usr/bin/env python3
"""Atheris target: SKILL.md frontmatter/body parse path on arbitrary bytes (#170).

Container-only (atheris). Expected refusals (MalformedSkillError) are not
crashes. Uncaught exceptions are findings.

Usage:
  python fuzz/parser_target.py -max_total_time=1800 fuzz/corpus/parser \\
      -artifact_prefix=fuzz/crashes/parser/
"""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO / "src" / "skill_harness"
_SRC = _SRC_ROOT / "extractor"


def _ensure_package_shells() -> None:
    """Register package shells so submodule import skips package ``__init__``."""
    if "skill_harness" not in sys.modules:
        pkg = types.ModuleType("skill_harness")
        pkg.__path__ = [str(_SRC_ROOT)]  # type: ignore[attr-defined]
        pkg.__package__ = "skill_harness"
        sys.modules["skill_harness"] = pkg
    if "skill_harness.extractor" not in sys.modules:
        sub = types.ModuleType("skill_harness.extractor")
        sub.__path__ = [str(_SRC)]  # type: ignore[attr-defined]
        sub.__package__ = "skill_harness.extractor"
        sys.modules["skill_harness.extractor"] = sub


_ensure_package_shells()

with atheris.instrument_imports(
    include=["skill_harness.extractor.errors", "skill_harness.extractor.parser"]
):
    from skill_harness.extractor.errors import MalformedSkillError
    from skill_harness.extractor.parser import parse_skill_file

_TMP = Path(tempfile.mkdtemp(prefix="atheris-parser-"))
_PATH = _TMP / "SKILL.md"


def TestOneInput(data: bytes) -> None:
    """Feed arbitrary bytes through parse_skill_file."""
    _PATH.write_bytes(data)
    try:
        parse_skill_file(_PATH)
    except MalformedSkillError:
        return


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
