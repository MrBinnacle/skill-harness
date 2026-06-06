"""Tests for dry-run default behaviour (CLAUDE.md pipeline safety).

The calibrate command MUST default to dry-run; actual DB writes MUST require --execute.
These tests verify the command interface contract at the click CLI level.

TDD RED phase: some tests will fail until the command is updated with --execute gate.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from click.testing import CliRunner

from skill_harness.cli.main import cli


def test_pythonhashseed_set() -> None:
    assert os.environ.get("PYTHONHASHSEED") == "0"


def _make_jsonl_file(n_pairs: int = 60) -> str:
    """Create a temp JSONL file with n_pairs valid calibration pairs."""
    lines = []
    for i in range(n_pairs):
        human_pref = ["A", "B", "tie"][i % 3]
        lines.append(
            json.dumps(
                {
                    "pair_id": f"pair_{i:04d}",
                    "axis": "test_axis",
                    "prompt": "What is 2+2?",
                    "response_a": "The answer is 4.",
                    "response_b": "Four.",
                    "human_preference": human_pref,
                    "labeler_id": "labeler_1",
                    "labeled_at": "2026-01-01T00:00:00Z",
                }
            )
        )
    return "\n".join(lines)


class TestCalibrateDefaultsToDryRun:
    """calibrate command defaults to dry-run; --execute is required to write."""

    def test_calibrate_without_execute_prints_dry_run_label(self) -> None:
        """Without --execute, output must contain a dry-run indicator."""
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(_make_jsonl_file(60))
            tmppath = f.name

        try:
            result = runner.invoke(
                cli,
                ["calibrate", "test_judge_id", "test_axis", tmppath],
                catch_exceptions=False,
            )
            # Should not error (dry-run always OK)
            assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
            # Output must indicate dry-run mode
            output_lower = result.output.lower()
            assert "dry" in output_lower or "dry-run" in output_lower, (
                f"Expected dry-run indicator in output:\n{result.output}"
            )
        finally:
            os.unlink(tmppath)

    def test_calibrate_without_execute_does_not_write_db(self, tmp_path: Path) -> None:
        """Without --execute, no DB files should be created."""
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))
        evidence_db = tmp_path / "evidence.db"
        runtime_db = tmp_path / "runtime.db"

        runner.invoke(
            cli,
            [
                "calibrate",
                "test_judge",
                "test_axis",
                str(jsonl_path),
                "--evidence-db",
                str(evidence_db),
                "--runtime-db",
                str(runtime_db),
            ],
            catch_exceptions=False,
        )
        # Dry-run should not create DB files
        assert not evidence_db.exists(), "evidence.db should NOT exist after dry-run"
        assert not runtime_db.exists(), "runtime.db should NOT exist after dry-run"

    def test_calibrate_help_mentions_execute(self) -> None:
        """--execute flag should be documented in the help text."""
        runner = CliRunner()
        result = runner.invoke(cli, ["calibrate", "--help"])
        assert "--execute" in result.output

    def test_calibrate_help_mentions_dry_run(self) -> None:
        """Help text should mention dry-run as the default."""
        runner = CliRunner()
        result = runner.invoke(cli, ["calibrate", "--help"])
        assert "dry" in result.output.lower()


class TestCalibrateWithExecuteFlag:
    """--execute flag causes actual DB writes (verified by DB file existence)."""

    def test_execute_flag_creates_db_files(self, tmp_path: Path) -> None:
        """With --execute, DB files are created (migrations run).

        The calibration write requires a matching judge row (FK constraint).
        We verify DB files are created; the calibration itself may be rejected
        due to FK if judge is not pre-seeded (verifying schema+migration health).
        """
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))
        evidence_db = tmp_path / "evidence.db"
        runtime_db = tmp_path / "runtime.db"

        # Run with --execute; catch_exceptions=True because FK may fail
        result = runner.invoke(
            cli,
            [
                "calibrate",
                "unknown_judge_id",
                "test_axis",
                str(jsonl_path),
                "--execute",
                "--evidence-db",
                str(evidence_db),
                "--runtime-db",
                str(runtime_db),
            ],
        )

        # With --execute, DB files should be created by migrations even if write fails
        assert evidence_db.exists(), (
            f"evidence.db not created even with --execute. Output:\n{result.output}"
        )
        assert runtime_db.exists(), (
            f"runtime.db not created even with --execute. Output:\n{result.output}"
        )
