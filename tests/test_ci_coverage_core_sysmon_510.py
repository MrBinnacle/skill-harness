"""#510: the Test cell uses COVERAGE_CORE=sysmon to stay inside its budget.

Before this ticket, coverage instrumentation on the Test cell cost ~522 seconds
of wall-clock time on the dominant fixture, pushing every cell near or past the
25-minute ceiling. The fix adds ``COVERAGE_CORE: "sysmon"`` to the Test job's
``env:`` block in ``ci.yml``, which switches coverage.py from its default
core to CPython's sys.monitoring API. Measured on the dominant fixture
(``tests/test_aggregation_fit_ebmom_recovery.py``) with ``pytest -p no:randomly``:

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

Why the behavioural half uses a direct coverage invocation rather than
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
# Job-level keys sit four spaces under the workflow (``  test:`` then ``    env:``).
_JOB_LEVEL_KEY = re.compile(r"^    ([A-Za-z_][A-Za-z0-9_-]*):", re.MULTILINE)
# The env: block: only lines indented deeper than the ``env:`` key itself. A
# greedy ``\s+.*`` body would swallow strategy/steps and make the "same block"
# check vacuous when a second ``env:`` key appears later in the job.
_ENV_BLOCK = re.compile(
    r"^(?P<indent>[ \t]+)env:\s*\n(?P<body>(?:(?P=indent)[ \t]+.+\n)*)",
    re.MULTILINE,
)
# A bare key: value line inside the env block (quoted values, as ci.yml writes them).
_ENV_VAR = re.compile(r"^\s+(?P<key>\w+):\s*\"(?P<value>[^\"]*)\"\s*$", re.MULTILINE)

_PARTIAL_MODULE = textwrap.dedent(
    """
    def covered() -> int:
        return 1

    def uncovered() -> int:
        return 2
    """
)

_PARTIAL_TEST = textwrap.dedent(
    """
    from mod import covered

    def test_covers_one_function():
        assert covered() == 1
    """
)

_CORE_PROBE = textwrap.dedent(
    """
    import os
    from coverage import Coverage

    cov = Coverage()
    cov.start()
    _ = 1 + 1
    cov.stop()
    tracers = list(cov._collector.tracers)
    print(type(tracers[0]).__name__ if tracers else "NONE")
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
    """The raw text of the Test job's env: block (values only, not siblings)."""
    job = _test_job_raw()
    env_m = _ENV_BLOCK.search(job)
    assert env_m is not None, "Test job has no env: block"
    return env_m.group("body")


def _parse_coverage_percent(output: str) -> str:
    """TOTAL row percent from a term-missing coverage report."""
    m = re.search(r"^TOTAL\s+\d+\s+\d+\s+(\d+%)\s*$", output, re.MULTILINE)
    assert m is not None, "no TOTAL coverage row in output:\n" + output
    return m.group(1)


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
    job = _test_job_raw()
    job_keys = _JOB_LEVEL_KEY.findall(job)
    assert job_keys.count("env") == 1, (
        f"Test job must declare exactly one job-level env: key; found "
        f"{job_keys.count('env')} among {job_keys!r}. A second env: key "
        f"silently replaces the first rather than merging."
    )
    raw = _test_job_env_raw()
    assert "PYTHONHASHSEED" in raw, (
        "PYTHONHASHSEED must be in the same env block as COVERAGE_CORE; "
        "a second env: key would have silently replaced the first"
    )
    assert "SKILL_HARNESS_REQUIRE_VALE" in raw, (
        "SKILL_HARNESS_REQUIRE_VALE must be in the same env block as COVERAGE_CORE"
    )
    assert "COVERAGE_CORE" in raw, "COVERAGE_CORE missing from the single env block body"


# -- Behavioural test: prove the env var reaches coverage.py ----------------


def test_coverage_core_sysmon_reaches_coverage(tmp_path: Path) -> None:
    """COVERAGE_CORE=sysmon selects SysMonitor and does not reduce reported coverage.

    The configuration tests above fail when the variable leaves ci.yml. This
    test proves the variable does what those tests assume: coverage.py reads it
    and switches to the sys.monitoring core, and the reported statement
    coverage on a module with a deliberate miss is identical to the default
    core. A duration race on a one-second sleep is not a control — both cores
    finish inside the sleep — so this asserts core identity and coverage
    parity instead.
    """
    probe = subprocess.run(
        [sys.executable, "-c", _CORE_PROBE],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "COVERAGE_CORE": "sysmon"},
        timeout=30,
        check=False,
    )
    assert probe.returncode == 0, f"sysmon core probe failed:\n{probe.stdout}\n{probe.stderr}"
    assert probe.stdout.strip() == "SysMonitor", (
        f"COVERAGE_CORE=sysmon must select SysMonitor, got {probe.stdout.strip()!r}"
    )

    (tmp_path / "mod.py").write_text(_PARTIAL_MODULE, encoding="utf-8")
    (tmp_path / "test_partial.py").write_text(_PARTIAL_TEST, encoding="utf-8")
    (tmp_path / "empty.ini").write_text("[pytest]\n", encoding="utf-8")

    base_cmd = [
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
        "--cov=mod",
        "--cov-report=term-missing",
        str(tmp_path / "test_partial.py"),
    ]

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

    # Partial module: covered() runs, uncovered() does not. Both cores must
    # report the same TOTAL percent; a silent drop under sysmon fails criterion 3.
    pct_sysmon = _parse_coverage_percent(result_sysmon.stdout)
    pct_default = _parse_coverage_percent(result_default.stdout)
    assert pct_sysmon == pct_default, (
        f"sysmon reported {pct_sysmon}, default reported {pct_default}; "
        f"criterion 3 forbids a smaller number under sysmon.\n"
        f"sysmon out:\n{result_sysmon.stdout}\ndefault out:\n{result_default.stdout}"
    )
    assert pct_sysmon != "100%", (
        "fixture module was fully covered; the deliberate miss is gone and "
        "parity against 100% no longer tests criterion 3:\n" + result_sysmon.stdout
    )
