"""Mechanized mutation receipt for the #360 gate. ASCII only.

Every case runs in its OWN git worktree checked out at a fixed commit. The
production tree is never mutated in place, so a failed restore cannot leave a
mutant behind or make a clean run report a mutant's numbers. That failure mode
is not hypothetical: an earlier hand-run pass restored production through a
path the interpreter could not see, and a "clean" comparison silently reported
the mutant's result.

For each mutant the receipt asserts, and records:

  repository HEAD of both worktrees
  module.__file__ actually imported in each
  digest of the clean source file
  digest of the mutant source file
  the two digests differ
  the clean baseline PASSES the targeted selection first
  the targeted test collected a nonzero number of tests
  the named assertion FAILS under the mutant
  the production tree is unchanged after the receipt is generated

Usage:
    python scripts/ebmom_mutation_receipt.py --out docs/assurance/<name>.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET_REL = Path("src/skill_harness/aggregation/fit.py")


@dataclass(frozen=True)
class Mutant:
    mutant_id: str
    obligation: str  # "A" numerics, or "B" method selection
    description: str
    old: str
    new: str
    selection: str


MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        "M-A1",
        "A",
        "revert the finite-K correction: /(k-1) becomes /k",
        "sum((r - sample_mean) ** 2 for r in rates) / (k - 1)",
        "sum((r - sample_mean) ** 2 for r in rates) / k",
        "tests/test_aggregation_differential.py::TestFitSkillDifferential",
    ),
    Mutant(
        "M-A2",
        "A",
        "wrong peel denominator: (n-1)*n becomes n*n",
        "total += max(within_ss, 0.0) / (max(clause.n - 1.0, 1.0) * clause.n)",
        "total += max(within_ss, 0.0) / (clause.n * clause.n)",
        "tests/test_aggregation_differential.py::TestFitSkillDifferential",
    ),
    Mutant(
        "M-A3",
        "A",
        "tie-blind peel: ignore sum_sq and use the Bernoulli form",
        "within_ss = clause.sum_sq - clause.n * rate * rate",
        "within_ss = clause.n * rate * (1.0 - rate)",
        "tests/test_aggregation_differential.py::TestFitSkillDifferential",
    ),
    Mutant(
        "M-B1",
        "B",
        "remove the gate: always admit",
        "if not test.admitted:",
        "if False:",
        "tests/test_aggregation_fit.py::TestFitSkillEbmom",
    ),
    Mutant(
        "M-B2",
        "B",
        "seed from a constant rather than from the data",
        "digest = hashlib.sha256(_canonical_input_bytes(clauses)).digest()",
        'digest = hashlib.sha256(b"constant").digest()',
        "tests/test_aggregation_fit.py::TestFitSkillEbmom",
    ),
    Mutant(
        "M-B3",
        "B",
        "drop the +1 finite-bootstrap correction",
        "p_boot = (1.0 + exceed) / (HETEROGENEITY_BOOTSTRAP_B + 1.0)",
        "p_boot = exceed / HETEROGENEITY_BOOTSTRAP_B",
        "tests/test_aggregation_fit.py::TestFitSkillEbmom",
    ),
    Mutant(
        "M-B4",
        "B",
        "hold each clause's tie count fixed at its observed value: the superseded "
        "null's tie treatment, which conditions on a statistic that is part of the "
        "encoded-mean hypothesis",
        "ties_b = 0 if null.tie == 0.0 else "
        "sum(1 for _ in range(clause.n) if rng.random() < null.tie)",
        "ties_b = _decompose(clause)[1]",
        "tests/test_aggregation_fit.py::TestFitSkillEbmom",
    ),
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _env(root: Path | None = None) -> dict[str, str]:
    """Environment for a subprocess, pinned to a worktree's own sources.

    Without PYTHONPATH the editable install resolves skill_harness to the MAIN
    repository, so a worktree would run its own tests against production code
    from somewhere else and every mutant would appear to survive. Each case
    asserts module.__file__ actually resolves inside its worktree, so a silent
    reversion to the editable install invalidates the receipt instead of
    quietly passing.
    """
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONUTF8": "1"}
    if root is not None:
        env["PYTHONPATH"] = str(root / "src")
    return env


def _run_pytest(root: Path, selection: str) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 -- argv is literal, built in this file
        [sys.executable, "-m", "pytest", selection, "-p", "no:randomly", "-q", "--tb=line"],
        cwd=root,
        capture_output=True,
        env=_env(root),
        check=False,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def _module_file(root: Path) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", "import skill_harness.aggregation.fit as m; print(m.__file__)"],
        cwd=root,
        capture_output=True,
        env=_env(root),
        check=False,
    )
    return proc.stdout.decode("utf-8", "replace").strip()


def _collected(output: str) -> int:
    counts = [int(n) for n in re.findall(r"(\d+) (?:passed|failed)", output)]
    return sum(counts)


@dataclass
class CaseResult:
    mutant_id: str
    obligation: str
    description: str
    selection: str
    verdict: str
    clean: dict[str, object] = field(default_factory=dict)
    mutant: dict[str, object] = field(default_factory=dict)
    killing_assertions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run_case(mutant: Mutant, commit: str, workroot: Path) -> CaseResult:
    result = CaseResult(
        mutant.mutant_id, mutant.obligation, mutant.description, mutant.selection, "UNKNOWN"
    )
    tree = workroot / mutant.mutant_id
    subprocess.run(  # noqa: S603
        ["git", "worktree", "add", "--detach", str(tree), commit],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        check=True,
    )
    try:
        target = tree / TARGET_REL
        head = (
            subprocess.run(["git", "rev-parse", "HEAD"], cwd=tree, capture_output=True, check=True)  # noqa: S607
            .stdout.decode()
            .strip()
        )

        clean_digest = _digest(target)
        clean_module = _module_file(tree)
        code, out = _run_pytest(tree, mutant.selection)
        result.clean = {
            "worktree_head": head,
            "module_file": clean_module,
            "source_digest": clean_digest,
            "exit_code": code,
            "tests_collected": _collected(out),
            "baseline_passes": code == 0,
        }
        if not clean_module.startswith(str(tree)):
            result.verdict = "INVALID_ISOLATION"
            result.notes.append(
                f"module resolved to {clean_module!r}, outside the worktree {str(tree)!r}; "
                "the case would have tested another tree's code"
            )
            return result
        if code != 0 or _collected(out) == 0:
            result.verdict = "INVALID_BASELINE"
            result.notes.append(
                "clean baseline did not pass with nonzero collection; no kill can be "
                "attributed against it"
            )
            return result

        source = target.read_text(encoding="utf-8")
        if mutant.old not in source:
            result.verdict = "ANCHOR_ABSENT"
            return result
        target.write_bytes(source.replace(mutant.old, mutant.new, 1).encode("utf-8"))

        mutant_digest = _digest(target)
        compiles = subprocess.run(
            [sys.executable, "-c", "import skill_harness.aggregation.fit"],
            cwd=tree,
            capture_output=True,
            env=_env(tree),
            check=False,
        )
        code, out = _run_pytest(tree, mutant.selection)
        failed = re.findall(r"^FAILED (\S+)", out, re.M)
        result.mutant = {
            "worktree_head": head,
            "module_file": _module_file(tree),
            "source_digest": mutant_digest,
            "digests_differ": mutant_digest != clean_digest,
            "compiles": compiles.returncode == 0,
            "exit_code": code,
            "tests_collected": _collected(out),
        }
        result.killing_assertions = failed

        if compiles.returncode != 0:
            result.verdict = "STILLBORN"
            result.notes.append("mutant does not import; a stillborn mutant is not a kill")
        elif mutant_digest == clean_digest:
            result.verdict = "NO_OP"
            result.notes.append("mutation did not change the file")
        elif failed:
            result.verdict = "KILLED"
        else:
            result.verdict = "SURVIVED"
        return result
    finally:
        subprocess.run(  # noqa: S603
            ["git", "worktree", "remove", "--force", str(tree)],  # noqa: S607
            cwd=REPO,
            capture_output=True,
            check=False,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="-")
    args = parser.parse_args(argv)

    dirty = (
        subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, check=True)  # noqa: S607
        .stdout.decode()
        .strip()
    )
    if dirty:
        print(
            "REFUSE: production tree is dirty. The receipt must attest to a committed "
            "tree, or its digests name nothing a reader can fetch.\n" + dirty,
            file=sys.stderr,
        )
        return 1

    commit = (
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, check=True)  # noqa: S607
        .stdout.decode()
        .strip()
    )
    tree_digest_before = _digest(REPO / TARGET_REL)

    workroot = Path(tempfile.mkdtemp(prefix="ebmom-mutation-"))
    try:
        cases = [run_case(m, commit, workroot) for m in MUTANTS]
    finally:
        shutil.rmtree(workroot, ignore_errors=True)

    tree_digest_after = _digest(REPO / TARGET_REL)
    still_clean = (
        subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, check=True)  # noqa: S607
        .stdout.decode()
        .strip()
    )

    target_rel_posix = str(TARGET_REL).replace("\\", "/")
    report = {
        "commit_under_test": commit,
        "commit_under_test_is_informational": (
            "A rebase rewrites this and later commits move HEAD past it. The"
            " authoritative pin is target_digests; currency is checked against those."
        ),
        # `target_files`/`target_digests` rather than the `target_file` string this
        # script emitted until 2026-09-06. The currency gate in
        # `tests/test_mutation_receipt.py` reads `target_digests` and treats its
        # absence as a failure rather than a skip, so that a receipt written by an
        # older generator cannot opt out of the gate silently. This generator was
        # that older generator: its receipt was the one carrying no digests, and it
        # is the shape that changed here, not the measurement.
        "target_files": [target_rel_posix],
        "target_digests": {target_rel_posix: tree_digest_after},
        "production_tree_digest_before": tree_digest_before,
        "production_tree_digest_after": tree_digest_after,
        "production_tree_unchanged": tree_digest_before == tree_digest_after and still_clean == "",
        "python": sys.version.split()[0],
        "cases": [
            {
                "mutant_id": c.mutant_id,
                "obligation": c.obligation,
                "description": c.description,
                "selection": c.selection,
                "verdict": c.verdict,
                "clean": c.clean,
                "mutant": c.mutant,
                "killing_assertions": c.killing_assertions,
                "notes": c.notes,
            }
            for c in cases
        ],
    }
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out == "-":
        print(payload)
    else:
        Path(args.out).write_text(payload + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")

    for c in cases:
        print(
            f"{c.mutant_id} [{c.obligation}] {c.verdict}: {'; '.join(c.killing_assertions) or '-'}"
        )
    if not report["production_tree_unchanged"]:
        print("REFUSE: production tree changed during receipt generation", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
