"""The frozen class-2 reference directory executes, and its vendored copies are pinned (#458).

``docs/assurance/reference/ebmom-class2-S414/`` is a frozen reference: its job is to be the
fixed thing later work is measured against. It shipped unable to run. ``rescore405.py`` loads
``errors-branch.py`` by path and that file was never vendored -- ``git log --diff-filter=D``
over the directory returns nothing and ``rescore405.py`` has exactly one commit, so this was
never a regression. The README's own file table lists six files and does not name it either.

A frozen artifact that cannot execute has quietly stopped being an oracle. Every consumer has
to assemble a runnable copy, and no two consumers are guaranteed to assemble the same one --
which is exactly what the #442 build did, checking its reproduction against a locally
assembled directory rather than against what the repository ships. Nothing detected that,
because nothing under ``tests/`` ran anything in the directory. This module is that check.

Why a subprocess and not an import
----------------------------------
``rescore405.py`` installs stub packages into ``sys.modules`` under the names
``skill_harness``, ``skill_harness.aggregation`` and ``skill_harness.aggregation.fit`` so that
``fit-branch.py``'s ``from skill_harness.aggregation.errors import ConvergenceFailure`` and
``matrix.py``'s ``from skill_harness.aggregation.fit import ...`` bind to the VENDORED copies
rather than to the installed package. That is the whole mechanism by which the directory is
self-contained, and ``errors-branch.py`` was the one hole in it.

Importing the directory in-process would do two unacceptable things: it would overwrite this
test session's real ``skill_harness.aggregation.fit`` entry in ``sys.modules``, and -- if the
production module were already imported -- it could bind the vendored code to production
internals. Measured while writing this test: loading ``matrix.py`` without the stubs resolves
``skill_harness.aggregation.fit`` to the INSTALLED package, not to ``fit-branch.py``. A
subprocess gets a clean interpreter, so the stubbing does what it was written to do.

What this test asserts, and what it does not
--------------------------------------------
It asserts that the directory EXECUTES end to end and reproduces exact per-world output for
three regimes at world 0 on the burned acceptance root -- the fit, the admission test, the
bootstrap and the decision rule, on both the admitted and the refused path.

It does NOT reproduce the R = 1000 figures the three consuming test modules cite in their
docstrings (``tests/test_aggregation_fit_admitted_bootstrap.py``'s four named worlds,
``tests/test_aggregation_fit_bounded_pooling.py``'s "251 of 251 false at R = 1000"). Those
are thousand-world scans; this is a smoke measured in seconds. The bar met here is "the
reference runs and its per-world arithmetic is unchanged", not "the reference reproduces the
published cells".

Nothing here may be cited as a result about the estimator. World 0 of three regimes is a
smoke, not a measurement.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REF_DIR = _REPO_ROOT / "docs" / "assurance" / "reference" / "ebmom-class2-S414"

# The root amendment v2 burned for the class-2 acceptance, named in the directory's README.
BURNED_ROOT = "f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a"

# Git blob ids of the three vendored copies. A blob id is SHA-1 over
# ``b"blob %d\0" % len(content) + content``, so it is computable from file bytes alone -- no
# git history required, which matters because CI checks out at depth 1. Each id is the blob
# the named path carried at the S414 freeze commit e322876; verify any of them by hand with
# ``git rev-parse <commit>:<path>``.
VENDORED_PINS: dict[str, tuple[str, str, str]] = {
    # vendored file: (blob id, source path at the freeze, commit that introduced that blob)
    "errors-branch.py": (
        "a32f891f954121c18c9b3625f637d4bf057e16f9",
        "src/skill_harness/aggregation/errors.py",
        "8df6710",
    ),
    "fit-branch.py": (
        "ce472ac540d00778a9b76eff671968edf269ccdb",
        "src/skill_harness/aggregation/fit.py",
        "b9099fe",
    ),
    "matrix.py": (
        "d473b29ebfb3d6251e728cf4943558f84c8bc543",
        "scripts/ebmom_acceptance_matrix.py",
        "e260c6f",
    ),
}

# Per-world output at world 0 on the burned root, measured 2026-09-08 after vendoring
# errors-branch.py. tie_heavy_signal and tie_heavy_null exercise the ADMITTED path (the
# bootstrap runs); low_heterogeneity is refused, so the class does not apply and the file
# says so -- both branches of proto_pb.py's per-world report are covered.
EXPECTED_WORLD_0: dict[str, list[str]] = {
    "tie_heavy_signal": [
        "== world 0: c_hat=104.3 kept=200/400 below_crit=16 nonpositive_c=0",
        "   decisions changed by the mechanism: 0 of 200",
    ],
    "tie_heavy_null": [
        "== world 0: c_hat=216.4 kept=200/400 below_crit=180 nonpositive_c=0",
        "   decisions changed by the mechanism: 52 of 200",
    ],
    "low_heterogeneity": [
        "world 0: refused; this class applies to admitted fits only",
    ],
}


def _git_blob_id(payload: bytes) -> str:
    """Return git's blob id for ``payload``, computed from content alone."""
    header = b"blob %d\0" % len(payload)
    return hashlib.sha1(header + payload, usedforsecurity=False).hexdigest()


def _run_proto_pb(*args: str) -> str:
    """Run ``proto_pb.py`` in the reference directory and return its stdout.

    ``cwd`` is the reference directory because that is how the README documents the entry
    point. The directory does not actually depend on it -- ``rescore405.py`` resolves its
    siblings from ``Path(__file__).parent`` -- and ``test_directory_does_not_depend_on_cwd``
    holds that property down, so a pass here is not an artifact of where the checkout lives.
    """
    proc = subprocess.run(
        [sys.executable, "proto_pb.py", *args],
        cwd=_REF_DIR,
        capture_output=True,
        text=True,
        timeout=600,
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
    )
    assert proc.returncode == 0, (
        f"proto_pb.py {' '.join(args)} exited {proc.returncode}.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    return proc.stdout


def test_every_file_rescore405_loads_by_path_is_present() -> None:
    """Every ``HERE / "<name>"`` operand of a ``_load`` call resolves to a file that exists.

    This is the defect #449 reported, stated as a rule rather than as one missing filename:
    ``rescore405.py`` named ``errors-branch.py`` and the directory did not contain it. A
    future vendored dependency added to the load list is covered by the same assertion.
    """
    source = (_REF_DIR / "rescore405.py").read_text(encoding="utf-8")
    loaded = re.findall(r'_load\(\s*"[^"]+"\s*,\s*HERE\s*/\s*"([^"]+)"', source)

    assert loaded, 'no `_load(..., HERE / "...")` calls found -- the loader shape changed'

    missing = [name for name in loaded if not (_REF_DIR / name).is_file()]
    assert not missing, (
        f"rescore405.py loads {missing} by path, but the reference directory does not "
        f"contain them. A frozen reference that cannot execute is not an oracle."
    )


@pytest.mark.parametrize("name", sorted(VENDORED_PINS))
def test_vendored_copy_matches_its_pinned_blob(name: str) -> None:
    """Each vendored copy is byte-identical to the blob the README pins it to.

    The README states the pin in prose. This makes it falsifiable, so the vendored bytes
    cannot drift away from the commit they claim to be a copy of without going red.
    """
    blob_id, source_path, commit = VENDORED_PINS[name]
    actual = _git_blob_id((_REF_DIR / name).read_bytes())
    assert actual == blob_id, (
        f"{name} is no longer byte-identical to {source_path} at {commit}.\n"
        f"  expected blob {blob_id}\n"
        f"  actual   blob {actual}\n"
        f"These files are frozen: they must stay identical to what produced amendment v2's "
        f"numbers. If the change is deliberate, the README's pin table changes with it."
    )


@pytest.mark.parametrize("regime", sorted(EXPECTED_WORLD_0))
def test_reference_directory_runs_and_reproduces_world_0(regime: str) -> None:
    """The directory executes and its world-0 report is unchanged.

    Seeds derive from SHA-256 over ``"<root>|<regime>|<world>|pb"``, so the output is
    deterministic by construction rather than by luck.
    """
    stdout = _run_proto_pb("worlds", BURNED_ROOT, regime, "0")
    assert stdout.splitlines() == EXPECTED_WORLD_0[regime]


def test_directory_does_not_depend_on_cwd() -> None:
    """Running from an unrelated working directory gives byte-identical output.

    ``rescore405.py`` resolves its vendored siblings from ``Path(__file__).parent``. If that
    ever became cwd-relative, the directory would run for whoever happened to be standing in
    it and fail for everyone else -- a subtler form of the same rot #449 found.
    """
    regime = "tie_heavy_signal"
    from_ref_dir = _run_proto_pb("worlds", BURNED_ROOT, regime, "0")

    proc = subprocess.run(
        [sys.executable, str(_REF_DIR / "proto_pb.py"), "worlds", BURNED_ROOT, regime, "0"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
    )
    assert proc.returncode == 0, f"exited {proc.returncode}\nstderr:\n{proc.stderr}"
    assert proc.stdout == from_ref_dir
