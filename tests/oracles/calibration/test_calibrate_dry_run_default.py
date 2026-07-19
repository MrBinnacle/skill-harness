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


class TestCalibrateMalformedPairSet:
    """D2 (S49 hostile review): malformed JSONL must surface as a clean CLI
    error, not a raw ValueError/pydantic ValidationError traceback.

    calibrate_cmd previously wrapped only validate_daily_cap's ValueError;
    parse_pair_set's ValueError (raised inside calibrate(), called for both
    dry-run and --execute) propagated unwrapped.
    """

    def test_malformed_json_line_is_clean_click_error(self, tmp_path: Path) -> None:
        """Invalid JSON on a line must exit non-zero via ClickException, with the
        parser's message in the output -- not an uncaught ValueError."""
        jsonl_path = tmp_path / "bad.jsonl"
        jsonl_path.write_text("not valid json at all\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["calibrate", "jid", "axis", str(jsonl_path)])

        assert result.exit_code != 0
        assert not isinstance(result.exception, ValueError), (
            f"A raw ValueError must not escape calibrate_cmd; got {result.exception!r}"
        )
        assert "line 1" in result.output and "invalid JSON" in result.output, (
            f"Expected the parser's line-numbered message in output:\n{result.output}"
        )

    def test_pydantic_validation_error_is_clean_click_error(self, tmp_path: Path) -> None:
        """A line that is valid JSON but fails CalibrationPair validation (e.g. an
        invalid human_preference value) must also surface as a clean CLI error."""
        jsonl_path = tmp_path / "bad_schema.jsonl"
        jsonl_path.write_text(
            json.dumps(
                {
                    "pair_id": "pair_0000",
                    "axis": "test_axis",
                    "prompt": "What is 2+2?",
                    "response_a": "4",
                    "response_b": "Four",
                    "human_preference": "not_a_valid_choice",
                    "labeler_id": "labeler_1",
                    "labeled_at": "2026-01-01T00:00:00Z",
                }
            )
            + "\n"
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["calibrate", "jid", "axis", str(jsonl_path)])

        assert result.exit_code != 0
        assert not isinstance(result.exception, ValueError), (
            f"A raw ValueError must not escape calibrate_cmd; got {result.exception!r}"
        )
        assert "line 1" in result.output, (
            f"Expected line-numbered message in output:\n{result.output}"
        )


class TestCalibrateWithExecuteFlag:
    """--execute flag causes actual DB writes (verified by DB file existence)."""

    def test_execute_flag_creates_db_files_when_api_key_present(self, tmp_path: Path) -> None:
        """With --execute and a usable ANTHROPIC_API_KEY, DB files are created
        (migrations run) past the D1 pre-flight.

        The calibration write requires a matching judge row (FK constraint).
        We verify DB files are created; the calibration itself may be rejected
        due to FK if judge is not pre-seeded (verifying schema+migration health).
        A syntactically-present-but-invalid key is enough to clear the D1
        pre-flight (presence-only check, mirrors m3); the write then fails on
        the FK constraint before any real network call would matter here.
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
            env={"ANTHROPIC_API_KEY": "sk-ant-test-dummy"},
        )

        # With --execute, DB files should be created by migrations even if write fails
        assert evidence_db.exists(), (
            f"evidence.db not created even with --execute. Output:\n{result.output}"
        )
        assert runtime_db.exists(), (
            f"runtime.db not created even with --execute. Output:\n{result.output}"
        )

    def test_execute_without_api_key_refuses_before_db_creation(self, tmp_path: Path) -> None:
        """D1 (S49 hostile review): --execute without ANTHROPIC_API_KEY must refuse
        BEFORE any DB/StorageContext creation. Previously, StorageContext created
        both DB files unconditionally, and the missing key only surfaced lazily
        when the first judge call failed -- after the DBs already existed.
        """
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))
        evidence_db = tmp_path / "evidence.db"
        runtime_db = tmp_path / "runtime.db"

        clean_env: dict[str, str | None] = {
            k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"
        }
        clean_env["ANTHROPIC_API_KEY"] = None  # delete from os.environ if present
        clean_env["COLUMNS"] = "200"

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
            env=clean_env,
        )

        assert result.exit_code != 0, (
            f"Expected refusal without ANTHROPIC_API_KEY, got exit 0:\n{result.output}"
        )
        assert "ANTHROPIC_API_KEY" in result.output, (
            f"Expected ANTHROPIC_API_KEY named in the refusal:\n{result.output}"
        )
        assert not evidence_db.exists(), (
            f"evidence.db must NOT be created before the D1 pre-flight. Output:\n{result.output}"
        )
        assert not runtime_db.exists(), (
            f"runtime.db must NOT be created before the D1 pre-flight. Output:\n{result.output}"
        )

    def test_dry_run_does_not_require_api_key(self, tmp_path: Path) -> None:
        """D1 pre-flight is --execute-only: dry-run must still work with no key
        at all (mirrors 'run ablation --dry-run' never requiring one either)."""
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        clean_env: dict[str, str | None] = {
            k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"
        }
        clean_env["ANTHROPIC_API_KEY"] = None
        clean_env["COLUMNS"] = "200"

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge_id", "test_axis", str(jsonl_path)],
            env=clean_env,
            catch_exceptions=False,
        )
        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
