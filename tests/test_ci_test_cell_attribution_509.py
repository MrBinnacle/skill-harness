"""#509: a Test-cell overrun names the test that consumed the time.

Before this ticket a cell that exceeded its ceiling died with GitHub's annotation
"exceeded the maximum execution time" and nothing else, so every overrun read as a
capacity problem and the ceiling was raised twice on that reading. Two core-pytest
settings supply the attribution, with no new dependency:

* ``--durations=N --durations-min=S`` on the Test cell's pytest line in ``ci.yml``
  prints the slowest phases with their node ids when the cell finishes.
* ``faulthandler_timeout`` in ``pyproject.toml`` dumps every thread's stack, naming
  the running test's file and function, when one test phase exceeds it. It does not
  fail the test, so it cannot manufacture a red cell.

These tests are the control the ticket requires: each fails when the configuration
it reads is removed. They read the real ``ci.yml`` and ``pyproject.toml`` rather than
a copy, then prove the mechanism in a subprocess so the assertion is about behaviour
and not about a string being present.

Why the behavioural half uses a short override rather than the configured value:
the configured ``faulthandler_timeout`` is minutes long, and a control that sleeps
that long is not a control anyone runs. The coupling to the real file is the
configuration test, which fails when the key is absent; the behavioural test proves
the key does what the configuration test assumes.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"

_TEST_CELL_PYTEST_LINE = re.compile(
    r"^\s*run:\s*(pytest\b[^\n]*--cov=src/skill_harness[^\n]*)$", re.MULTILINE
)
_DURATIONS_FLAG = re.compile(r"--durations=(\d+)")
_DURATIONS_MIN_FLAG = re.compile(r"--durations-min=([0-9.]+)")
# A job block runs from its two-space key to the next two-space key.
_TEST_JOB_BLOCK = re.compile(r"\n  test:\n(?P<body>.*?)(?=\n  [A-Za-z_-]+:\n)", re.DOTALL)
_TIMEOUT_MINUTES = re.compile(r"^\s*timeout-minutes:\s*(\d+)\s*$", re.MULTILINE)

_SLEEPING_TEST = textwrap.dedent(
    """
    import time

    def test_named_when_slow():
        time.sleep(3)
    """
)


def _test_cell_pytest_line() -> str:
    """The Test cell's pytest invocation, identified by its coverage flag.

    Only the matrix Test cell runs with ``--cov=src/skill_harness``; the calibration
    job runs ``-m calibration`` without it. One match is the contract.
    """
    matches = _TEST_CELL_PYTEST_LINE.findall(CI_YML.read_text(encoding="utf-8"))
    assert len(matches) == 1, (
        f"expected exactly one coverage-bearing pytest line in ci.yml, found {len(matches)}"
    )
    return str(matches[0])


def _test_job_ceiling_minutes() -> int:
    block = _TEST_JOB_BLOCK.search(CI_YML.read_text(encoding="utf-8"))
    assert block is not None, "could not find the `test:` job in ci.yml"
    ceiling = _TIMEOUT_MINUTES.search(block.group("body"))
    assert ceiling is not None, "the Test job sets no timeout-minutes"
    return int(ceiling.group(1))


def _faulthandler_timeout() -> float:
    with PYPROJECT.open("rb") as fh:
        options = tomllib.load(fh)["tool"]["pytest"]["ini_options"]
    assert "faulthandler_timeout" in options, (
        "pyproject.toml [tool.pytest.ini_options] must set faulthandler_timeout (#509)"
    )
    return float(options["faulthandler_timeout"])


def _run_pytest_on(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Run pytest on one sleeping test in isolation from this repository's config.

    An explicit empty ini plus ``--rootdir`` keeps the repository's ``addopts``
    (``--strict-config`` among them) out of the subprocess, and the ``-p no:`` flags
    drop the plugins that would otherwise reseed, cache or instrument the run, so
    the only options in force are the ones passed.
    """
    (tmp_path / "test_sleeper.py").write_text(_SLEEPING_TEST, encoding="utf-8")
    (tmp_path / "empty.ini").write_text("[pytest]\n", encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(tmp_path / "empty.ini"),
        "--rootdir",
        str(tmp_path),
        "-p",
        "no:randomly",
        "-p",
        "no:cacheprovider",
        "-p",
        "no:cov",
        str(tmp_path / "test_sleeper.py"),
        *extra,
    ]
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=tmp_path, timeout=120, check=False
    )


def test_test_cell_requests_per_test_durations() -> None:
    """The Test cell prints a durations table. Fails when the flag leaves ci.yml."""
    line = _test_cell_pytest_line()
    count = _DURATIONS_FLAG.search(line)
    floor = _DURATIONS_MIN_FLAG.search(line)
    assert count is not None, f"Test cell pytest line carries no --durations=N (#509): {line}"
    assert int(count.group(1)) > 0, "--durations=0 prints every test; the cell wants the slowest N"
    assert floor is not None, (
        "Test cell pytest line carries no --durations-min=S; without it the table is noise"
    )


def test_durations_flags_from_ci_name_the_slow_test(tmp_path: Path) -> None:
    """The exact flags ci.yml uses produce a table that names the slow test's node id."""
    line = _test_cell_pytest_line()
    found = (_DURATIONS_FLAG.search(line), _DURATIONS_MIN_FLAG.search(line))
    flags = [m.group(0) for m in found if m]
    assert flags, "no durations flags on the Test cell line; the previous test reports why"
    result = _run_pytest_on(tmp_path, *flags)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "slowest" in result.stdout, "no durations table in output:\n" + result.stdout
    assert "test_sleeper.py::test_named_when_slow" in result.stdout, (
        "durations table does not name the test:\n" + result.stdout
    )


def test_faulthandler_timeout_is_configured_shorter_than_the_cell() -> None:
    """A per-test dump threshold exists and sits inside the Test cell's ceiling.

    A threshold at or above the job ceiling can never fire before GitHub kills the
    job, which would make the setting decoration. The ceiling is read from ci.yml
    rather than restated here.
    """
    assert 0 < _faulthandler_timeout() < _test_job_ceiling_minutes() * 60


def test_faulthandler_timeout_names_the_running_test(tmp_path: Path) -> None:
    """When a test phase exceeds the threshold, the dump names the file and function.

    Uses a one-second override so the control runs in seconds; the configured value
    is asserted by the previous test. The test still passes (faulthandler dumps, it
    does not fail), which is the property that makes the setting safe on every cell.
    """
    result = _run_pytest_on(tmp_path, "-o", "faulthandler_timeout=1")
    assert result.returncode == 0, result.stdout + result.stderr
    dump = result.stderr
    assert "Timeout" in dump, "faulthandler produced no timeout dump:\n" + dump
    assert "test_sleeper.py" in dump and "test_named_when_slow" in dump, (
        "dump does not name the test:\n" + dump
    )
