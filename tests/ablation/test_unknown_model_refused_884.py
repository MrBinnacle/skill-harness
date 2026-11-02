"""A subject model with no price row is refused, never priced at another model's rate (#884).

#333 removed the Sonnet-4.6 fallback from ``_estimate_usd`` and left it at the
budget gate and in the OpenAI estimate. ``run ablation --execute`` accepted
``o4-mini``, projected its cost at $3/$15 per MTok, and enforced ``--max-usd``
against that figure.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner, Result

from skill_harness.ablation.subject import _estimate_usd_openai, project_call_cost
from skill_harness.cli.main import cli

_RECORD = """---
rat: RAT-0001
status: RATIFIED
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

# RAT-0001 - skill-abc row-pick (test fixture)
"""


def _execute(
    tmp_path: Path, subject_model: str, *, key_env: str
) -> tuple[Result, Path, Path, list[str]]:
    """Run ``run ablation --execute`` through the ratification gate with one API key set."""
    record = tmp_path / "RAT-0001-skill-abc.md"
    record.write_text(_RECORD, encoding="utf-8")
    evidence_db = tmp_path / "evidence.db"
    runtime_db = tmp_path / "runtime.db"
    env: dict[str, str | None] = {
        "COLUMNS": "200",
        "ANTHROPIC_API_KEY": None,
        "OPENAI_API_KEY": None,
        "OPENROUTER_API_KEY": None,
    }
    env[key_env] = "sk-test-dummy"
    models_run: list[str] = []

    def record_run(**kwargs: str) -> list[object]:
        models_run.append(kwargs["subject_model"])
        return []

    with patch("skill_harness.cli.main._execute_ablation_run", side_effect=record_run):
        result = CliRunner().invoke(
            cli,
            [
                "run",
                "ablation",
                "skill-abc",
                "--execute",
                "--subject-model",
                subject_model,
                "--ratification",
                str(record),
                "--task-family",
                "append-only-evidence-design",
                "--estimand",
                "treatment-policy",
                "--max-usd",
                "15.55",
                "--evidence-db",
                str(evidence_db),
                "--runtime-db",
                str(runtime_db),
            ],
            env=env,
        )
    return result, evidence_db, runtime_db, models_run


def test_budget_gate_refuses_a_model_with_no_row() -> None:
    with pytest.raises(KeyError, match="o4-mini"):
        project_call_cost("o4-mini", 1_000_000, 1_000_000)


def test_openai_estimate_refuses_a_model_with_no_row() -> None:
    with pytest.raises(KeyError, match="o4-mini"):
        _estimate_usd_openai("o4-mini", 1_000_000, 1_000_000, 0)


def test_budget_gate_prices_a_routed_model_at_its_own_row() -> None:
    """1M in at $2 plus 1M out at $10 is $12, where the fallback's $3/$15 gave $18."""
    assert project_call_cost("anthropic/claude-sonnet-5", 1_000_000, 1_000_000) == 12.00


def test_openai_estimate_prices_a_routed_model_at_its_own_row() -> None:
    """1M in at $5 plus 1M out at $30 is $35."""
    assert _estimate_usd_openai("openai/gpt-5.5", 1_000_000, 1_000_000, 0) == 35.00


@pytest.mark.parametrize(
    ("subject_model", "key_env", "named_in_refusal"),
    [
        ("o4-mini", "OPENAI_API_KEY", "o4-mini"),
        ("o4-mini", "OPENROUTER_API_KEY", "openai/o4-mini"),
        ("google/gemini-2-pro", "OPENROUTER_API_KEY", "google/gemini-2-pro"),
    ],
)
def test_execute_refuses_an_unpriced_model_before_any_database_write(
    tmp_path: Path, subject_model: str, key_env: str, named_in_refusal: str
) -> None:
    result, evidence_db, runtime_db, models_run = _execute(tmp_path, subject_model, key_env=key_env)

    assert result.exit_code == 1, result.output
    assert named_in_refusal in result.output
    assert "PRICE_PER_MTOK" in result.output
    assert models_run == []
    assert not runtime_db.exists()
    assert not evidence_db.exists()


def test_execute_lets_a_routed_model_with_a_row_through(tmp_path: Path) -> None:
    result, _, _, models_run = _execute(tmp_path, "openai/gpt-5.5", key_env="OPENROUTER_API_KEY")

    assert result.exit_code == 0, result.output
    assert models_run == ["openai/gpt-5.5"]
