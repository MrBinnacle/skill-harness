"""Tests for --max-usd and --daily-cap enforcement in calibrate command.

Per A36: if projected cost exceeds --max-usd, refuse with exit-1.
Hard ceiling on --daily-cap ≤ $100 without SKILL_HARNESS_DAILY_CAP_OVERRIDE env var.

TDD RED phase: tests will fail until cost projection + cap enforcement is wired.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from skill_harness.cli.main import cli
from skill_harness.oracles.calibration.cost_projection import (
    DAILY_CAP_HARD_CEILING_USD,
    DAILY_CAP_OVERRIDE_ENV,
)


def test_pythonhashseed_set() -> None:
    assert os.environ.get("PYTHONHASHSEED") == "0"


def _make_jsonl_file(n_pairs: int = 60) -> str:
    lines = []
    for i in range(n_pairs):
        human_pref = ["A", "B", "tie"][i % 3]
        lines.append(
            json.dumps(
                {
                    "pair_id": f"pair_{i:04d}",
                    "axis": "test_axis",
                    "prompt": "prompt",
                    "response_a": "response a",
                    "response_b": "response b",
                    "human_preference": human_pref,
                    "labeler_id": "labeler_1",
                    "labeled_at": "2026-01-01T00:00:00Z",
                }
            )
        )
    return "\n".join(lines)


class TestMaxUsdEnforcement:
    """Projection exceeds --max-usd → refuse with exit-1."""

    def test_refuse_when_projection_exceeds_max_usd_zero(self, tmp_path: Path) -> None:
        """--max-usd 0.0 always refuses (projection is always > 0)."""
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path), "--max-usd", "0.0"],
        )
        assert result.exit_code != 0, (
            f"Expected exit-1 when projection exceeds max-usd=0.0\n{result.output}"
        )

    def test_refuse_when_projection_exceeds_max_usd_tiny(self, tmp_path: Path) -> None:
        """--max-usd 0.001 refuses for any realistic pair set."""
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path), "--max-usd", "0.001"],
        )
        assert result.exit_code != 0, f"Expected exit-1 for max-usd=0.001\n{result.output}"

    def test_refusal_message_mentions_max_usd(self, tmp_path: Path) -> None:
        """Refusal message should mention the cap that was exceeded."""
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path), "--max-usd", "0.0"],
        )
        assert result.exit_code != 0
        output = (result.output or "") + (str(result.exception) if result.exception else "")
        assert "max" in output.lower() or "usd" in output.lower() or "cap" in output.lower(), (
            f"Refusal message should mention cap. Output:\n{result.output}"
        )

    def test_dry_run_shows_projection_even_when_over_cap(self, tmp_path: Path) -> None:
        """Even in dry-run mode, projection should be computed and shown."""
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path)],
        )
        # Dry-run with default max-usd $5 should show projection info
        out = result.output
        assert "projected" in out.lower() or "$" in out or "usd" in out.lower(), (
            f"Expected projection numbers in dry-run output:\n{out}"
        )


class TestDailyCapHardCeiling:
    """--daily-cap above $100 is rejected unless SKILL_HARNESS_DAILY_CAP_OVERRIDE=1."""

    def test_daily_cap_constant_value(self) -> None:
        assert pytest.approx(100.0) == DAILY_CAP_HARD_CEILING_USD

    def test_daily_cap_override_env_name(self) -> None:
        assert DAILY_CAP_OVERRIDE_ENV == "SKILL_HARNESS_DAILY_CAP_OVERRIDE"

    def test_refuse_daily_cap_over_100(self, tmp_path: Path) -> None:
        """--daily-cap 101.0 is rejected without override env var."""
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path), "--daily-cap", "101.0"],
            env={k: v for k, v in os.environ.items() if k != DAILY_CAP_OVERRIDE_ENV},
        )
        assert result.exit_code != 0, (
            f"Expected exit-1 for --daily-cap 101.0 without override\n{result.output}"
        )
        output = (result.output or "") + (str(result.exception) if result.exception else "")
        assert "ceiling" in output.lower() or "100" in output or "cap" in output.lower(), (
            f"Error message should mention ceiling. Output:\n{result.output}"
        )

    def test_allow_daily_cap_over_100_with_override_env(self, tmp_path: Path) -> None:
        """--daily-cap 200.0 is allowed when SKILL_HARNESS_DAILY_CAP_OVERRIDE=1."""
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        env = {**os.environ, DAILY_CAP_OVERRIDE_ENV: "1"}
        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path), "--daily-cap", "200.0"],
            env=env,
        )
        # With override, should not fail due to ceiling (may fail for other reasons)
        output = result.output or ""
        ceiling_error = "ceiling" in output.lower() and "override" not in output.lower()
        assert not ceiling_error, f"Should not reject ceiling with override env set:\n{output}"

    def test_daily_cap_100_is_at_ceiling_exact(self, tmp_path: Path) -> None:
        """--daily-cap exactly 100.0 is allowed (≤ ceiling)."""
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path), "--daily-cap", "100.0"],
            env={k: v for k, v in os.environ.items() if k != DAILY_CAP_OVERRIDE_ENV},
        )
        # Should not fail due to ceiling (may fail for other reasons but not ceiling)
        if result.exit_code != 0:
            err = (result.output or "") + str(result.exception or "")
            assert "ceiling" not in err.lower(), (
                f"--daily-cap 100.0 should not be rejected by ceiling check:\n{err}"
            )


class TestDryRunProjectionOutput:
    """Dry-run output contains A36-shape projection information."""

    def test_dry_run_contains_calls_count(self, tmp_path: Path) -> None:
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        n_pairs = 60
        jsonl_path.write_text(_make_jsonl_file(n_pairs))

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path)],
        )
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        # Should mention call count (60 pairs x 2 = 120 calls)
        assert "120" in result.output or "calls" in result.output.lower(), (
            f"Expected call count in output:\n{result.output}"
        )

    def test_dry_run_contains_model_name(self, tmp_path: Path) -> None:
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path)],
        )
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        # Should mention the model name in cost projection
        assert "sonnet" in result.output.lower() or "claude" in result.output.lower(), (
            f"Expected model name in output:\n{result.output}"
        )

    def test_dry_run_contains_se_projection(self, tmp_path: Path) -> None:
        runner = CliRunner()
        jsonl_path = tmp_path / "pairs.jsonl"
        jsonl_path.write_text(_make_jsonl_file(60))

        result = runner.invoke(
            cli,
            ["calibrate", "test_judge", "test_axis", str(jsonl_path)],
        )
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        # Should contain SE or CI projection
        output_lower = result.output.lower()
        assert "se" in output_lower or "ci" in output_lower or "0." in result.output, (
            f"Expected SE/CI projection in output:\n{result.output}"
        )
