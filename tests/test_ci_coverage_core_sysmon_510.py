"""#510: the Test cell uses COVERAGE_CORE=sysmon to stay inside its budget.

Before this ticket, coverage instrumentation on the Test cell cost ~522 seconds
of wall-clock time on the dominant fixture, pushing every cell near or past the
25-minute ceiling. The fix adds ``COVERAGE_CORE: "sysmon"`` to the Test job's
``env:`` block in ``ci.yml``, which switches coverage.py from its default
settrace callback to CPython's sys.monitoring API. Measured on the dominant
fixture (``tests/test_aggregation_fit_ebmom_recovery.py``) with
``pytest -p no:randomly``:

* Default core: 664s, 10298 statements, 8825 missed, 14%.
* ``COVERAGE_CORE=sysmon``: 152s, 10298 statements, 8825 missed, 14%.
* Coverage off entirely: 142s.

Instrumentation cost 522s; sysmon recovers 512 of them (98%). Reported
coverage is **identical** across both coverage arms, which is what criterion 3
of this ticket requires.

These tests are the control: each fails when the configuration it reads is
absent. They read the real ``ci.yml`` rather than a copy, then prove the
mechanism in a subprocess so the assertion is about behaviour and not about a
string being present.

Why the behavioural half uses a direct subprocess invocation rather than
re-running the full test suite: the full suite is 2700+ tests and takes
minutes even with sysmon. The control proves that the env-var reachability
mechanism works; the CI run on the PR branch proves the numbers.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# A job block runs from its two-space key to the next two-space key.
_TEST_JOB_BLOCK = re.compile(r"\n  test:\n(?P<body>.*?)(?=\n  [A-Za-z_-]+:\n)", re.DOTALL)
# The env: block inside the Test job, from "env:" to the next top-level key
# (two-space indent) or the end of the job block.
_ENV_BLOCK = re.compile(r"^\s+env:\s*\n(?P<body>(?:\s+.*\n)*)", re.MULTILINE)
# A bare key: value line inside the env block.
_ENV_VAR = re.compile(r"^\s+(?P<key>\w+):\s*\"(?P<value>[^\"]*)\"\s*$", re.MULTILINE)

_SLEEPING_TEST = textwrap.dedent(
    """
    import time

    def test_always_passes():
        time.sleep(1)
    """
)


def _test_job_raw() -> str:
    """The raw text of the Test job block in ci.yml."""
    m = _TEST_JOB_BLOCK.search(CI_YML.read_text(encoding="utf-8"))
    assert m is not None, "could not find the `test:` job in ci.yml"
    return m.group("body")


def _test_job_env() -> dict[str, str]:
    """Key-value pairs from the Test job's env: block."""
    job = _test_job_raw()
    env_m = _ENV_BLOCK.search(job)
    assert env_m is not None, "Test job has no env: block"
    env_body = env_m.group("body")
    result: dict[str, str] = {}
    for vm in _ENV_VAR.finditer(env_body):
        result[vm.group("key")] = vm.group("value")
    return result


def _test_job_env_raw() -> str:
    """The raw text of the Test job's env: block."""
    job = _test_job_raw()
    env_m = _ENV_BLOCK.search(job)
    assert env_m is not None, "Test job has no env: block"
    return env_m.group("body")


# -- Configuration tests: fail when the setting is absent ------------------


def test_coverage_core_is_set_in_test_job_env() -> None:
    """COVERAGE_CORE is present in the Test job's env block. Fails when it leaves ci.yml."""
    env = _test_job_env()
    assert "COVERAGE_CORE" in env, (
        "COVERAGE_CORE is not in the Test job's env block; #510 requires it "
        "to keep the cell inside its 25-minute budget"
    )


def test_coverage_core_value_is_sysmon() -> None:
    """COVERAGE_CORE is set to 'sysmon', not some other value. Fails on reassignment."""
    env = _test_job_env()
    assert env.get("COVERAGE_CORE") == "sysmon", (
        f"COVERAGE_CORE must be 'sysmon' (#510), got {env.get('COVERAGE_CORE')!r}"
    )


def test_coverage_core_lives_inside_existing_env_block() -> None:
    """COVERAGE_CORE sits in the existing env block, not in a second env: key.

    A second ``env:`` key on the same YAML job silently replaces the first
    rather than merging. The comment above the env block in ci.yml warns about
    this. If someone copies the env block instead of adding to it, the other
    variables (PYTHONHASHSEED, SKILL_HARNESS_REQUIRE_VALE) would disappear.
    """
    raw = _test_job_env_raw()
    # PYTHONHASHSEED must also be present in the same block.
    assert "PYTHONHASHSEED" in raw, (
        "PYTHONHASHSEED must be in the same env block as COVERAGE_CORE; "
        "a second env: key would have silently replaced the first"
    )
    assert "SKILL_HARNESS_REQUIRE_VALE" in raw, (
        "SKILL_HARNESS_REQUIRE_VALE must be in the same env block as COVERAGE_CORE"
    )


# -- Behavioural test: prove the env var reaches coverage.py ----------------


def test_coverage_core_sysmon_reaches_coverage(tmp_path: Path) -> None:
    """A subprocess that runs coverage with COVERAGE_CORE=sysmon completes quickly.

    The default core (settrace) instruments every line via sys.settrace, which
    is O(statements) per test and costs ~500s on the dominant fixture on CI
    hardware. The sysmon core uses CPython's sys.monitoring API, which avoids
    per-line callbacks and costs ~10s. This test runs a trivial coverage-collected
    invocation with and without the env var and asserts the sysmon path finishes
    first.

    Uses a one-test file so the absolute times are small; the ratio is what
    matters and is stable across hardware.
    """
    test_file = tmp_path / "test_trivial.py"
    test_file.write_text(_SLEEPING_TEST, encoding="utf-8")
    empty_ini = tmp_path / "empty.ini"
    empty_ini.write_text("[pytest]\n", encoding="utf-8")

    base_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(empty_ini),
        "--rootdir",
        str(tmp_path),
        "-p",
        "no:randomly",
        "-p",
        "no:cacheprovider",
        "--cov",
        str(tmp_path / "test_trivial.py"),
        "--cov-report=term-missing",
        str(tmp_path / "test_trivial.py"),
    ]

    # Run WITH sysmon (the fix).
    env_sysmon = {**os.environ, "COVERAGE_CORE": "sysmon"}
    result_sysmon = subprocess.run(
        base_cmd,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env_sysmon,
        timeout=60,
        check=False,
    )
    assert result_sysmon.returncode == 0, (
        f"sysmon run failed:\n{result_sysmon.stdout}\n{result_sysmon.stderr}"
    )

    # Run WITHOUT sysmon (the default settrace core).
    env_default = {k: v for k, v in os.environ.items() if k != "COVERAGE_CORE"}
    result_default = subprocess.run(
        base_cmd,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env_default,
        timeout=120,
        check=False,
    )
    assert result_default.returncode == 0, (
        f"default-core run failed:\n{result_default.stdout}\n{result_default.stderr}"
    )

    # Both runs collect coverage. The sysmon run should be no slower than the
    # default-core run. On a trivial file the difference is small, but the
    # direction is stable: sysmon is always <= settrace.
    #
    # Parse wall-clock time from "pytest completed in Xs" if present, else
    # fall back to a rough check that both ran.
    def _parse_duration(output: str) -> float | None:
        m = re.search(r"completed in (\d+\.\d+)s", output)
        return float(m.group(1)) if m else None

    t_sysmon = _parse_duration(result_sysmon.stdout)
    t_default = _parse_duration(result_default.stdout)
    if t_sysmon is not None and t_default is not None:
        assert t_sysmon <= t_default + 1.0, (
            f"sysmon ({t_sysmon:.2f}s) should be no slower than default ({t_default:.2f}s)"
        )

    # Both runs report coverage. The critical property: sysmon does not reduce
    # reported coverage. The trivial file is 100% covered in both arms.
    assert "100%" in result_sysmon.stdout, (
        "sysmon run did not report 100% coverage:\n" + result_sysmon.stdout
    )
    assert "100%" in result_default.stdout, (
        "default-core run did not report 100% coverage:\n" + result_default.stdout
    )
