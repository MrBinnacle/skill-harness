"""CLI integration tests for `screen profile` (per-skill evaluation profile).

The profile is a read-only reporting-layer VIEW over already-computed data: it
presents the harness's signals as SEPARATE GRADE-style columns (disposition,
verdict, evidence-quality, cost), one row per skill, over the UNION of screened
skills and skills-root skills. It never fuses the axes.

All tests are offline (no Anthropic API, no live marker).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from skill_harness.cli.main import cli
from skill_harness.storage.migrations import open_evidence
from skill_harness.storage.models import ScreenRunWrite, ScreenTrialWrite
from skill_harness.storage.repositories.evidence.screens import (
    insert_screen_run,
    insert_screen_trial,
)

_TS = "2026-07-01T10:00:00.000Z"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _invoke(*args: str) -> Any:
    return CliRunner().invoke(cli, list(args), env={"COLUMNS": "200"})


def _seed_screen(evidence_db: Path, skill_name: str, *, n_trials: int, n_pass: int) -> None:
    conn = open_evidence(evidence_db)
    try:
        run_id = f"sr-{skill_name}"
        insert_screen_run(
            conn,
            ScreenRunWrite(
                screen_run_id=run_id,
                skill_name=skill_name,
                subject_model="claude-sonnet-4-6",
                harness_pin_fingerprint=None,
                source_eval_task_id="task-1",
                source_eval_sha256=_sha("task-1"),
                admissibility_state="admissible",
                inadmissibility_reason=None,
                created_at=_TS,
                ingested_at=_TS,
            ),
        )
        for i in range(n_trials):
            insert_screen_trial(
                conn,
                ScreenTrialWrite(
                    screen_trial_id=f"st-{skill_name}-{i}",
                    screen_run_id=run_id,
                    epoch=i,
                    passed=1 if i < n_pass else 0,
                    scorer_name="mechanical",
                    scorer_explanation=None,
                    output_sha256=_sha(f"{skill_name}-{i}"),
                    sampled_at=_TS,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _write_skill(root: Path, dir_name: str, description: str, *, disable: bool = False) -> None:
    skill_dir = root / dir_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {dir_name}", f"description: {description}"]
    if disable:
        lines.append("disable-model-invocation: true")
    lines += ["---", "", f"# {dir_name}", "", "Body text for the skill.", ""]
    (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")


def _make_library(tmp_path: Path) -> tuple[Path, Path]:
    """alpha screened (p0=1 -> CUT, 10 trials -> MEASURED_HIGH); beta never
    screened (NOT_YET_RANKABLE/UNMEASURED); gamma disable-model-invocation
    (UNMEASURABLE)."""
    evidence_db = tmp_path / "evidence.db"
    _seed_screen(evidence_db, "alpha-skill", n_trials=10, n_pass=10)
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, "alpha-skill", "Alpha does a screened thing when asked.")
    _write_skill(skills_root, "beta-skill", "Beta was never screened at all here.")
    _write_skill(skills_root, "gamma-skill", "Gamma is procedure-only.", disable=True)
    return evidence_db, skills_root


class TestScreenProfileSeparatedColumns:
    def test_renders_separated_axis_columns(self, tmp_path: Path) -> None:
        evidence_db, skills_root = _make_library(tmp_path)
        result = _invoke(
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(skills_root),
        )
        assert result.exit_code == 0, result.output
        low = result.output.lower()
        for header in ("disposition", "verdict", "evidence", "cost"):
            assert header in low, f"missing separated column {header!r}:\n{result.output}"

    def test_one_row_per_skill_union(self, tmp_path: Path) -> None:
        evidence_db, skills_root = _make_library(tmp_path)
        result = _invoke(
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(skills_root),
        )
        assert result.exit_code == 0, result.output
        for skill in ("alpha-skill", "beta-skill", "gamma-skill"):
            assert skill in result.output, f"{skill} missing from union:\n{result.output}"

    def test_unmeasured_is_first_class_rendered_value(self, tmp_path: Path) -> None:
        evidence_db, skills_root = _make_library(tmp_path)
        result = _invoke(
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(skills_root),
        )
        assert result.exit_code == 0, result.output
        # beta was never screened -> UNMEASURED + NOT_YET_RANKABLE, both rendered.
        assert "UNMEASURED" in result.output, result.output
        assert "NOT_YET_RANKABLE" in result.output, result.output

    def test_disable_model_invocation_is_unmeasurable(self, tmp_path: Path) -> None:
        evidence_db, skills_root = _make_library(tmp_path)
        result = _invoke(
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(skills_root),
        )
        assert result.exit_code == 0, result.output
        assert "UNMEASURABLE" in result.output, result.output

    def test_screened_skill_is_excluded_and_measured_high(self, tmp_path: Path) -> None:
        evidence_db, skills_root = _make_library(tmp_path)
        result = _invoke(
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(skills_root),
        )
        assert result.exit_code == 0, result.output
        # alpha p0=1.0 -> CUT(subsumed) -> EXCLUDED; 10 trials >= N_MIN -> MEASURED_HIGH.
        assert "EXCLUDED" in result.output, result.output
        assert "MEASURED_HIGH" in result.output, result.output


class TestScreenProfileHeldColumns:
    def test_held_columns_hidden_by_default(self, tmp_path: Path) -> None:
        evidence_db, skills_root = _make_library(tmp_path)
        result = _invoke(
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(skills_root),
        )
        assert result.exit_code == 0, result.output
        assert "eff/cost" not in result.output, (
            f"held effect-per-cost column must be hidden by default:\n{result.output}"
        )

    def test_held_columns_shown_with_flag(self, tmp_path: Path) -> None:
        evidence_db, skills_root = _make_library(tmp_path)
        result = _invoke(
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(skills_root),
            "--show-held-columns",
        )
        assert result.exit_code == 0, result.output
        assert "eff/cost" in result.output, (
            f"--show-held-columns must reveal the held eff/cost column:\n{result.output}"
        )
        # Held effect has no measured value yet -> rendered as an em-dash, never a
        # bare point estimate.
        assert "—" in result.output, result.output


class TestScreenProfileNoSkillsRoot:
    def test_screened_only_when_skills_root_omitted(self, tmp_path: Path) -> None:
        evidence_db = tmp_path / "evidence.db"
        _seed_screen(evidence_db, "alpha-skill", n_trials=10, n_pass=10)
        result = _invoke("screen", "profile", "--evidence-db", str(evidence_db))
        assert result.exit_code == 0, result.output
        assert "alpha-skill" in result.output
        # No skills-root -> desc-token standing-cost axis is unavailable; the
        # command says so and shows the cost as an em-dash.
        assert "skills-root" in result.output.lower(), result.output


class TestScreenProfileHelp:
    def test_help_documents_flags(self) -> None:
        result = _invoke("screen", "profile", "--help")
        assert result.exit_code == 0
        assert "--skills-root" in result.output
        assert "--show-held-columns" in result.output
