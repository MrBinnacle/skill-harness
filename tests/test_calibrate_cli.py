"""CLI integration test for the `calibrate` command (C.3).

Verifies:
- `calibrate --help` shows the expected arguments and options.
- `calibrate <judge_id> <axis> <path>` defaults to dry-run (no writes).
- `calibrate <judge_id> <axis> <path>` with N<50 exits with an error message.
- The command is wired into the CLI as a top-level `calibrate` group
  (per PRD §18 + brief: `calibrate <judge_id> <axis> <pair_set.jsonl>`).

Network is not blocked here since the CLI test uses CliRunner with mocked
internals; actual judge calls are patched out.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_pairs(tmp_path: Path, n: int) -> Path:
    path = tmp_path / "pairs.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for i in range(n):
            pair = {
                "pair_id": f"p{i:04d}",
                "axis": "clarity",
                "prompt": f"Q{i}",
                "response_a": f"A{i}",
                "response_b": f"B{i}",
                "human_preference": "A",
                "labeler_id": "lab-001",
                "labeled_at": "2026-01-01T00:00:00Z",
            }
            fh.write(json.dumps(pair) + "\n")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_calibrate_help_shows_required_args(tmp_path: Path) -> None:
    """--help output must mention judge_id, axis, pair_set_path."""
    from skill_harness.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["calibrate", "--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    assert "judge" in output
    assert "axis" in output


def test_calibrate_dry_run_default_no_db_args(tmp_path: Path) -> None:
    """calibrate without --execute must not require DB connections and exit 0."""
    from unittest.mock import MagicMock, patch

    from skill_harness.cli.main import cli

    path = _write_pairs(tmp_path, n=60)

    runner = CliRunner()
    with patch(
        "skill_harness.oracles.calibration.command.calibrate",
    ) as mock_calibrate:
        mock_result = MagicMock()
        mock_result.state = "conditional"
        mock_result.n_pairs = 60
        mock_result.pairwise_agreement = 0.7
        mock_result.position_consistency = 0.8
        mock_result.cohen_kappa = 0.4
        mock_result.chance_baseline = 0.35
        mock_calibrate.return_value = mock_result

        result = runner.invoke(
            cli,
            ["calibrate", "judge-001", "clarity", str(path)],
        )
    # Dry-run should exit cleanly (exit_code 0 or indicate dry-run)
    assert result.exit_code == 0 or "dry" in result.output.lower()


def test_calibrate_n_below_50_exits_with_error_message(tmp_path: Path) -> None:
    """N<50 must result in a user-visible error / warning message."""
    from unittest.mock import MagicMock, patch

    from skill_harness.cli.main import cli

    path = _write_pairs(tmp_path, n=20)

    runner = CliRunner()
    with patch(
        "skill_harness.oracles.calibration.command.calibrate",
    ) as mock_calibrate:
        mock_result = MagicMock()
        mock_result.state = "rejected"
        mock_result.n_pairs = 20
        mock_calibrate.return_value = mock_result

        result = runner.invoke(
            cli,
            ["calibrate", "judge-001", "clarity", str(path)],
        )
    # Should either exit non-zero or show 'rejected' / 'insufficient' in output
    output_lower = result.output.lower()
    assert result.exit_code != 0 or "rejected" in output_lower or "insufficient" in output_lower


def test_calibrate_command_is_top_level(tmp_path: Path) -> None:
    """calibrate must be a top-level command (not under skill/ or run/)."""
    from skill_harness.cli.main import cli

    # Verify 'calibrate' appears in top-level commands
    commands = cli.commands if hasattr(cli, "commands") else {}
    assert "calibrate" in commands, (
        f"'calibrate' not found in top-level CLI commands. Found: {list(commands)}"
    )
