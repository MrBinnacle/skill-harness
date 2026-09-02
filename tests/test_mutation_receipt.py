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
4. Every generated receipt is CURRENT: the files it says it mutated still hash
   to the digests it recorded. This is the currency gate, and it is keyed on
   content rather than on `commit_under_test`, which a rebase rewrites and every
   later commit moves HEAD past. A receipt carried across a rebase is still
   valid; a receipt whose subject changed is not, and only the second should be
   red.
5. `_run_pytest` spreads every node id of a multi-node selection into argv.
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

import hashlib
import importlib.util
import json
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


def _receipt_paths() -> list[Path]:
    return sorted((_REPO_ROOT / "docs" / "assurance").glob("*mutation-receipt*.json"))


def test_at_least_one_mutation_receipt_is_present() -> None:
    """Guards the currency test below against passing on an empty glob."""
    assert _receipt_paths(), "no mutation receipts found; the currency test would be vacuous"


def _stale_targets(receipt: dict[str, Any], root: Path) -> list[str]:
    """Return one message per file whose live bytes disagree with the receipt.

    Shared by the currency gate and its negative control, so the control
    exercises the same code the gate runs rather than a paraphrase of it.
    """
    recorded = receipt["target_digests"]
    assert recorded, "receipt records no target digests"
    stale: list[str] = []
    for rel, digest in recorded.items():
        target = root / rel
        if not target.is_file():
            stale.append(f"{rel}: named by the receipt but no longer present")
            continue
        live = hashlib.sha256(target.read_bytes()).hexdigest()
        if live != digest:
            stale.append(f"{rel}: attested {digest[:12]}, live {live[:12]}")
    return stale


@pytest.mark.parametrize("receipt_path", _receipt_paths(), ids=lambda p: p.name)
def test_receipt_still_describes_the_files_it_measured(receipt_path: Path) -> None:
    """A receipt is stale when its SUBJECT moves, not when a commit does.

    `commit_under_test` is deliberately NOT checked. A rebase rewrites it and
    every commit landing after generation moves HEAD past it, so gating on it
    reddens for reasons that cannot have affected the measurement. The digests
    of the mutated files change if and only if the code under test changed.

    `target_digests` is required rather than optional. Treating its absence as a
    skip would let a receipt written by an older generator opt out of the gate
    silently, which is the failure this gate exists to prevent.
    """
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "target_digests" in receipt, (
        f"{receipt_path.name} carries no target_digests, so its currency cannot be"
        f" checked. Regenerate it with scripts/mutation_receipt.py."
    )
    stale = _stale_targets(receipt, _REPO_ROOT)
    assert not stale, (
        f"STALE_RECEIPT: {receipt_path.name} was measured against a tree that no longer"
        f" exists ({'; '.join(stale)}). Its kills therefore attest to code that is not"
        f" the code shipping. Regenerate with scripts/mutation_receipt.py."
    )


def test_the_currency_gate_detects_a_moved_target(tmp_path: Path) -> None:
    """Negative control: the gate must fire on a digest that does not match.

    Without this, a bug making `_stale_targets` always return an empty list
    would leave every currency assertion above green and silent.
    """
    moved = tmp_path / "subject.py"
    moved.write_text("# the file as it is now", encoding="utf-8")
    receipt = {"target_digests": {"subject.py": "0" * 64}}
    assert _stale_targets(receipt, tmp_path), "the gate passed a digest that does not match"

    current = {"target_digests": {"subject.py": hashlib.sha256(moved.read_bytes()).hexdigest()}}
    assert not _stale_targets(current, tmp_path), "the gate fired on a matching digest"

    absent = {"target_digests": {"gone.py": "0" * 64}}
    assert _stale_targets(absent, tmp_path), "the gate passed a file that does not exist"


def _receipt_prose_pairs() -> list[tuple[Path, Path]]:
    """Every machine-readable receipt that has a prose companion beside it."""
    pairs = []
    for json_path in _receipt_paths():
        prose = json_path.with_suffix(".md")
        if prose.is_file():
            pairs.append((json_path, prose))
    return pairs


@pytest.mark.parametrize(
    ("receipt_path", "prose_path"),
    _receipt_prose_pairs(),
    ids=lambda p: p.name,
)
def test_prose_companion_names_the_digest_its_receipt_attests(
    receipt_path: Path, prose_path: Path
) -> None:
    """The prose must name the same digest the JSON pins.

    The currency gate above reads the JSON only. A regeneration that updates the
    JSON and leaves the prose alone therefore passes it, and the document a human
    actually reads goes on naming a digest that is not the code shipping. That
    happened on 2026-09-02: both ingest receipts were regenerated and merged with
    their prose still naming the superseded digest, and CI was green throughout.

    This case compares each prose file against ITS OWN receipt, not against the
    live tree, so a receipt that legitimately pins a different module is
    unaffected.
    """
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    prose = prose_path.read_text(encoding="utf-8")
    missing = [
        f"{target}: {digest[:12]}"
        for target, digest in receipt.get("target_digests", {}).items()
        if digest not in prose
    ]
    assert not missing, (
        f"PROSE_DRIFT: {prose_path.name} does not name the digest(s) its receipt"
        f" attests to ({'; '.join(missing)}). The JSON was regenerated and the prose"
        f" was not, so the document a reader trusts describes a tree that no longer"
        f" exists. Update the prose to match {receipt_path.name}."
    )
