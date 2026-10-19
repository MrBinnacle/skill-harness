"""J1w (S49 hostile review): judge_id is operator-supplied to `calibrate` and
was never derived from or cross-checked against JudgeClient.judge_id(model) --
a prompt/schema change (which changes judge_id()'s output) could silently
coexist with calibrations recorded under the same operator-typed string,
because nothing ever compared the two.

Design note (deviation from the proposed default-refuse shape): ~15 existing
tests across this test module and test_calibrate_cli.py / test_calibrate_max_
usd_refuse.py invoke `calibrate` with placeholder judge_id strings ("jid",
"test_judge", "judge-001") that do not match any real derived hash, and assert
exit_code == 0 for dry-run. Defaulting to a hard refuse on mismatch would
break all of them (and any operator script using a human-readable judge_id
convention) in one sweep. Instead: ALWAYS warn on mismatch (closes the
"silently coexist" gap -- the drift is now visible every run), and add
--verify-judge-id to escalate the warning to a refusal for callers who want
the hard guarantee (e.g. CI calibration pipelines).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

from skill_harness.cli.main import cli
from skill_harness.oracles.tier2.judge import JudgeClient


def _make_jsonl_file(n_pairs: int = 60) -> str:
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


def _write_jsonl(tmp_path: Path, n_pairs: int = 60) -> Path:
    p = tmp_path / "pairs.jsonl"
    p.write_text(_make_jsonl_file(n_pairs))
    return p


def _real_derived_judge_id() -> str:
    """The judge_id a fresh default-model JudgeClient() would derive -- fully
    offline (judge_id() only hashes local strings, no API call)."""
    client = JudgeClient()
    return client.judge_id(client.model)


def test_judge_client_exposes_model_publicly() -> None:
    """JudgeClient must expose its model publicly (was private-attribute-only,
    forcing any caller wanting judge_id(model) to reach into ._model)."""
    client = JudgeClient(model="claude-opus-4-8")
    assert client.model == "claude-opus-4-8"


def test_calibrate_mismatched_judge_id_warns_but_does_not_refuse_by_default() -> None:
    """A placeholder/mismatched judge_id must NOT break dry-run by default
    (existing CLI convention + ~15 pre-existing tests rely on this), but the
    mismatch must now be surfaced instead of silent."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = _write_jsonl(Path(tmpdir))
        result = runner.invoke(
            cli,
            ["calibrate", "operator-typed-placeholder", "test_axis", str(jsonl_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert "does not match" in result.output.lower() or "mismatch" in result.output.lower(), (
            f"Expected a judge_id mismatch warning in output:\n{result.output}"
        )


def test_calibrate_mismatched_judge_id_with_verify_flag_refuses() -> None:
    """--verify-judge-id escalates the mismatch to a hard refusal."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = _write_jsonl(Path(tmpdir))
        result = runner.invoke(
            cli,
            [
                "calibrate",
                "operator-typed-placeholder",
                "test_axis",
                str(jsonl_path),
                "--verify-judge-id",
            ],
        )
        assert result.exit_code != 0, f"expected refusal, got exit_code=0:\n{result.output}"
        assert "operator-typed-placeholder" in result.output
        assert "judge_id" in result.output.lower()


def test_calibrate_matching_judge_id_with_verify_flag_succeeds_without_warning() -> None:
    """The real derived judge_id, with --verify-judge-id, must pass clean (no
    warning, no refusal) -- proves the check compares correctly, not just
    that it refuses everything."""
    runner = CliRunner()
    real_judge_id = _real_derived_judge_id()
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = _write_jsonl(Path(tmpdir))
        result = runner.invoke(
            cli,
            ["calibrate", real_judge_id, "test_axis", str(jsonl_path), "--verify-judge-id"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert "mismatch" not in result.output.lower()
        assert "does not match" not in result.output.lower()


def test_calibrate_help_documents_judge_id_contract() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["calibrate", "--help"])
    assert result.exit_code == 0
    assert "--verify-judge-id" in result.output
