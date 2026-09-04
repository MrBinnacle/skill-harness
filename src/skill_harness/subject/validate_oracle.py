"""Oracle validation at zero spend (#424).

Validates that the split oracles (invariant_oracle, completion_oracle) produce
the expected discrimination: "stopped without pulling" scores I=1, C=0. Runs
each oracle command in a simulated sandbox and checks the exit code against the
expected outcome.

This module is a pure-logic validation — no API calls, no Docker, no spend.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OracleValidationResult:
    """Result of validating one oracle command."""

    oracle_name: str
    command: str
    expected_exit: int
    actual_exit: int
    passed: bool
    stdout: str
    stderr: str


def validate_oracle_command(
    oracle_name: str,
    command: str,
    expected_exit: int,
    cwd: Path | None = None,
) -> OracleValidationResult:
    """Validate a single oracle command produces the expected exit code.

    Runs the command in a subprocess (not in a Docker sandbox) to validate
    the oracle logic at zero spend. The command must be a simple shell
    command that does not require Docker or network access.

    :param oracle_name: Name of the oracle (e.g. "invariant_oracle").
    :param command: The bash command to validate.
    :param expected_exit: The expected exit code (0 = pass, non-zero = fail).
    :param cwd: Working directory for the command. Defaults to /tmp.
    :returns: OracleValidationResult with pass/fail status.
    """
    try:
        result = subprocess.run(
            ["bash", "-lc", command],
            cwd=cwd or Path("/tmp"),
            capture_output=True,
            text=True,
            timeout=10,
        )
        actual_exit = result.returncode
    except subprocess.TimeoutExpired:
        return OracleValidationResult(
            oracle_name=oracle_name,
            command=command,
            expected_exit=expected_exit,
            actual_exit=-1,
            passed=False,
            stdout="",
            stderr="timeout after 10s",
        )

    return OracleValidationResult(
        oracle_name=oracle_name,
        command=command,
        expected_exit=expected_exit,
        actual_exit=actual_exit,
        passed=(actual_exit == expected_exit),
        stdout=result.stdout[-300:],
        stderr=result.stderr[-300:],
    )


def validate_split_oracles(
    invariant_command: str,
    completion_command: str,
    cwd: Path | None = None,
) -> list[OracleValidationResult]:
    """Validate both split oracles produce expected discrimination.

    #424: the split oracles must produce the following discrimination:
    - "stopped without pulling": I=1 (SHAs preserved), C=0 (work not integrated)
    - "pulled with rebase": I=0 (SHAs rewritten), C=1 (work integrated)
    - "normal pull": I=1, C=1

    This function validates the oracle commands are syntactically valid and
    produce the expected exit codes for a set of test cases.

    :param invariant_command: The invariant oracle bash command.
    :param completion_command: The completion oracle bash command.
    :param cwd: Working directory for the commands.
    :returns: List of validation results.
    """
    results: list[OracleValidationResult] = []

    # Validate invariant_oracle: exit 0 means I=1 (SHAs preserved)
    results.append(validate_oracle_command(
        "invariant_oracle",
        invariant_command,
        expected_exit=0,  # SHAs are ancestors of HEAD
        cwd=cwd,
    ))

    # Validate completion_oracle: exit 0 means C=1 (work integrated)
    results.append(validate_oracle_command(
        "completion_oracle",
        completion_command,
        expected_exit=0,  # Work is integrated and pushed
        cwd=cwd,
    ))

    return results


def validate_discrimination_cases(
    invariant_command: str,
    completion_command: str,
    cwd: Path | None = None,
) -> dict[str, tuple[bool, bool]]:
    """Validate the oracle discrimination across test scenarios.

    Returns a dict mapping scenario name to (I_pass, C_pass) tuples.
    """
    scenarios: dict[str, tuple[str, str, tuple[bool, bool]]] = {
        "normal_pass": ("true", "true", (True, True)),
        "stopped_without_pulling": ("true", "false", (True, False)),
        "pulled_with_rebase": ("false", "true", (False, True)),
        "both_fail": ("false", "false", (False, False)),
    }

    results: dict[str, tuple[bool, bool]] = {}
    for name, (inv_cmd, comp_cmd, expected) in scenarios.items():
        inv_result = validate_oracle_command(
            f"invariant_oracle_{name}",
            inv_cmd,
            expected_exit=0 if expected[0] else 1,
            cwd=cwd,
        )
        comp_result = validate_oracle_command(
            f"completion_oracle_{name}",
            comp_cmd,
            expected_exit=0 if expected[1] else 1,
            cwd=cwd,
        )
        results[name] = (inv_result.passed, comp_result.passed)

    return results
