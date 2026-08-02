"""CLI refusal matrix for the mechanical ratification gate on --execute (#57).

Required lanes per the ticket's acceptance criteria: missing record,
non-RATIFIED status, cap mismatch, scope mismatch, dry-run ungated, and one
happy path. The pure decision logic is unit-tested in tests/test_ratification.py;
these tests pin the CLI seam — exit code 1 (hard error class), the refusal
reason token in the output, and the gate firing BEFORE any run machinery.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner, Result

from skill_harness.cli.main import cli

_RECORD = """---
rat: RAT-0001
status: {status}
skill_id: skill-abc
task_family: append-only-evidence-design
estimand: treatment-policy
gate: gate2
n: 20
worst_case_cost_usd: 15.55
hard_cap_usd: 15.55
cost_provenance: project_pair_usd
sme_status: deliberated
ratified_date: "2026-08-02"
---

# RAT-0001 — skill-abc row-pick (test fixture)
"""


def _write_record(tmp_path: Path, status: str = "RATIFIED") -> Path:
    path = tmp_path / "RAT-0001-skill-abc.md"
    path.write_text(_RECORD.format(status=status), encoding="utf-8")
    return path


def _invoke(*args: str) -> Result:
    runner = CliRunner()
    env = {"COLUMNS": "200", "ANTHROPIC_API_KEY": "sk-test-dummy"}
    return runner.invoke(cli, list(args), env=env, catch_exceptions=False)


def _scope_args(record: Path, *, max_usd: str = "15.55") -> list[str]:
    return [
        "--ratification",
        str(record),
        "--task-family",
        "append-only-evidence-design",
        "--estimand",
        "treatment-policy",
        "--max-usd",
        max_usd,
    ]


class TestRefusalMatrix:
    def test_execute_without_ratification_refuses(self) -> None:
        result = _invoke("run", "ablation", "skill-abc", "--execute")
        assert result.exit_code == 1
        assert "record-missing" in result.output

    def test_execute_with_absent_record_refuses(self, tmp_path: Path) -> None:
        args = _scope_args(tmp_path / "RAT-0404-absent.md")
        result = _invoke("run", "ablation", "skill-abc", "--execute", *args)
        assert result.exit_code == 1
        assert "record-missing" in result.output

    def test_execute_with_draft_record_refuses(self, tmp_path: Path) -> None:
        args = _scope_args(_write_record(tmp_path, status="DRAFT"))
        result = _invoke("run", "ablation", "skill-abc", "--execute", *args)
        assert result.exit_code == 1
        assert "status-not-ratified" in result.output

    def test_execute_with_invalid_record_refuses(self, tmp_path: Path) -> None:
        args = _scope_args(_write_record(tmp_path, status="APPROVED"))
        result = _invoke("run", "ablation", "skill-abc", "--execute", *args)
        assert result.exit_code == 1
        assert "record-invalid" in result.output

    def test_execute_with_cap_mismatch_refuses(self, tmp_path: Path) -> None:
        args = _scope_args(_write_record(tmp_path), max_usd="5.0")
        result = _invoke("run", "ablation", "skill-abc", "--execute", *args)
        assert result.exit_code == 1
        assert "cap-mismatch" in result.output

    def test_execute_with_skill_scope_mismatch_refuses(self, tmp_path: Path) -> None:
        args = _scope_args(_write_record(tmp_path))
        result = _invoke("run", "ablation", "other-skill", "--execute", *args)
        assert result.exit_code == 1
        assert "scope-mismatch" in result.output

    def test_execute_with_undeclared_scope_refuses(self, tmp_path: Path) -> None:
        record = _write_record(tmp_path)
        result = _invoke(
            "run",
            "ablation",
            "skill-abc",
            "--execute",
            "--ratification",
            str(record),
            "--max-usd",
            "15.55",
        )
        assert result.exit_code == 1
        assert "scope-mismatch" in result.output
        assert "not declared" in result.output

    def test_gate_fires_before_run_machinery(self) -> None:
        # A refused --execute must never reach _cmd_execute (no DB, no client).
        with patch("skill_harness.cli.main._cmd_execute") as cmd:
            result = _invoke("run", "ablation", "skill-abc", "--execute")
        assert result.exit_code == 1
        cmd.assert_not_called()


class TestDryRunUngated:
    def test_dry_run_needs_no_ratification(self) -> None:
        # #47: dry-run stays ungated — no record, no scope flags, exit 0.
        result = _invoke("run", "ablation", "skill-abc")
        assert result.exit_code == 0
        assert "NO CALLS MADE" in result.output


class TestHappyPath:
    def test_ratified_matching_invocation_proceeds(self, tmp_path: Path) -> None:
        from skill_harness.ablation.stopping import StoppingReason

        passed = MagicMock()
        passed.stopping_reason = StoppingReason("passed")
        passed.unmeasured_reason = None
        passed.length_confounded = False
        passed.samples_collected = 8
        passed.stop_decision = MagicMock()
        passed.stop_decision.p_win_rate_exceeds_threshold = 0.97
        passed.stop_decision.n_samples = 8
        passed.clause_id = "clause-001"

        args = _scope_args(_write_record(tmp_path))
        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[passed],
        ):
            result = _invoke("run", "ablation", "skill-abc", "--execute", *args)
        assert result.exit_code == 0, f"Expected 0, got {result.exit_code}:\n{result.output}"
