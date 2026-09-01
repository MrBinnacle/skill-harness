"""Guards on the mutation-receipt generator (`scripts/mutation_receipt.py`).

The generator is the instrument that attests to a repair, so its own failure
modes are silent by construction: a receipt that measured nothing still renders
as a table of verdicts. These tests pin the three properties a reader of a
receipt relies on and cannot check from the JSON alone.

1. Every registered mutation anchor is present EXACTLY ONCE in the file it
   targets. An anchor that has drifted returns `ANCHOR_ABSENT`, and an anchor
   that matches twice mutates a site the case does not name.
2. An invalid case exits non-zero. A stillborn mutant, a no-op edit, a red
   baseline or a module resolved outside its worktree produced no measurement;
   exiting zero on one would publish a receipt that attests to nothing.
   `SURVIVED` is deliberately NOT invalid: a preserved survivor is a finding.
3. `_collected` reads a nonzero test count out of real pytest tail lines. The
   generator refuses a case whose baseline collected nothing, so a parse miss
   turns a valid baseline into `INVALID_BASELINE` and silently deletes evidence.
4. `_run_pytest` spreads every node id of a multi-node selection into argv.
   This one is written from a live defect rather than from foresight: changing
   `selection` from a space-separated string to a tuple left one
   `selection.split()` behind, and the campaign died with an `AttributeError`
   mid-run. The properties above all passed while it was broken, because none
   of them built the command line.

Not covered here: an end-to-end campaign. That needs a git worktree and a
pytest subprocess per case and runs in minutes, so the campaign's own output is
the evidence for it -- `docs/assurance/nan-score-refusal-mutation-receipt.json`
records the isolation and baseline assertions for every case it ran.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "mutation_receipt.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mutation_receipt", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["mutation_receipt"] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load()


def test_every_mutation_anchor_matches_its_target_exactly_once() -> None:
    for mutant in MODULE.MUTANTS:
        target = _REPO_ROOT / mutant.target
        assert target.is_file(), f"{mutant.mutant_id}: target {mutant.target} does not exist"
        source = target.read_text(encoding="utf-8")
        count = source.count(mutant.old)
        assert count == 1, (
            f"{mutant.mutant_id}: anchor matches {count} times in {mutant.target}."
            f" Zero means the anchor drifted and the case cannot run; more than one"
            f" means the case mutates a site it does not name."
        )
        assert mutant.new != mutant.old, f"{mutant.mutant_id}: mutation is a no-op"


def test_every_mutation_selection_names_a_test_file_that_exists() -> None:
    for mutant in MODULE.MUTANTS:
        for node in mutant.selection:
            rel = node.split("::", 1)[0]
            assert (_REPO_ROOT / rel).is_file(), (
                f"{mutant.mutant_id}: selection {node} names {rel}, which does not exist"
            )


def test_survived_is_not_an_invalid_verdict() -> None:
    """A preserved survivor is a finding, not a failure.

    Folding SURVIVED into the exit code would create pressure to delete the
    survivor rather than report it, which is the opposite of what the receipts
    are for.
    """
    assert "SURVIVED" not in MODULE.INVALID_VERDICTS
    assert "KILLED" not in MODULE.INVALID_VERDICTS
    assert {
        "ANCHOR_ABSENT",
        "INVALID_BASELINE",
        "INVALID_ISOLATION",
        "NO_OP",
        "STILLBORN",
    } <= MODULE.INVALID_VERDICTS


@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        ("7 passed in 3.91s", 7),
        ("1 failed, 6 passed in 3.86s", 7),
        ("31 passed, 1 skipped in 3.89s", 31),
        ("no tests ran in 0.01s", 0),
        ("ERROR: file or directory not found: tests/nope.py", 0),
    ],
)
def test_collected_counts_executed_tests(tail: str, expected: int) -> None:
    assert MODULE._collected(tail) == expected


def test_run_pytest_spreads_every_node_of_a_multi_node_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: a tuple selection must reach argv as separate arguments.

    The campaign previously died with `AttributeError: 'tuple' object has no
    attribute 'split'` after `selection` changed type. Nothing else in this
    module builds the command line, so nothing else could catch it.
    """
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, b"2 passed in 0.1s", b"")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    code, out = MODULE._run_pytest(tmp_path, ("tests/a.py::test_one", "tests/b.py::test_two"))

    assert code == 0
    assert MODULE._collected(out) == 2
    argv = seen[0]
    assert "tests/a.py::test_one" in argv
    assert "tests/b.py::test_two" in argv
    assert not any(" " in arg for arg in argv[3:]), (
        f"a node id reached argv still joined to another: {argv!r}"
    )
