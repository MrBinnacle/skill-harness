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
from skill_harness.storage.migrations import open_db, open_evidence
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
                d4_check_state="not_applicable",
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
    """alpha screened (p0=1; UNCLASSIFIED under the #74/#76 guard -> CANT_TELL_YET
    (wrong instrument) -> NOT_YET_RANKABLE, never a false EXCLUDED on a ceiling;
    10 trials -> MEASURED_HIGH); beta never screened (NOT_YET_RANKABLE/UNMEASURED);
    gamma disable-model-invocation (UNMEASURABLE)."""
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

    def test_screened_ceiling_is_not_yet_rankable_and_measured_high(self, tmp_path: Path) -> None:
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
        # alpha p0=1.0 is UNCLASSIFIED under the #74/#76 guard -> CANT_TELL_YET
        # (wrong instrument) -> NOT_YET_RANKABLE, NOT a false EXCLUDED. The evidence
        # axis is independent of the verdict: 10 trials >= N_MIN -> MEASURED_HIGH.
        assert "NOT_YET_RANKABLE" in result.output, result.output
        assert "CANT_TELL_YET" in result.output, result.output
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
        base_args = [
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(skills_root),
        ]
        hidden = _invoke(*base_args)
        shown = _invoke(*base_args, "--show-held-columns")
        assert hidden.exit_code == 0 and shown.exit_code == 0, shown.output

        # The eff/cost header appears ONLY under the flag (unique token — not an
        # incidental em-dash that also lives in a verdict cell).
        assert "eff/cost" not in hidden.output
        assert "eff/cost" in shown.output, (
            f"--show-held-columns must reveal the held eff/cost column:\n{shown.output}"
        )
        # The two held columns (effect + eff/cost) each render an em-dash per row —
        # a measured effect is absent, and effect is never a bare point. So the
        # flagged render must carry strictly more em-dashes than the hidden one:
        # exactly the effect columns' contribution, not just an incidental dash.
        n_rows = 3  # alpha (screened) + beta + gamma
        assert shown.output.count("—") >= hidden.output.count("—") + 2 * n_rows, (
            f"held effect columns must render an em-dash per row:\n{shown.output}"
        )


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
        # Honesty note: UNMEASURABLE depends on skills-root (frontmatter-sourced
        # disable-model-invocation flag), so the footer must say so.
        assert "UNMEASURABLE" in result.output, result.output


class TestScreenProfileMalformedEvidenceDb:
    def test_present_but_no_screen_tables_still_profiles_library(self, tmp_path: Path) -> None:
        """F-5: a PRESENT evidence.db lacking screen_runs/screen_trials (pre-0501 or
        malformed) must NOT traceback — it falls back to no screens and still profiles
        the --skills-root library."""
        evidence_db = tmp_path / "evidence.db"
        # Valid SQLite file with a dummy table but no screen store (never migrated).
        conn = open_db(evidence_db)
        try:
            conn.execute("CREATE TABLE dummy (x INTEGER)")
            conn.commit()
        finally:
            conn.close()

        skills_root = tmp_path / "skills"
        _write_skill(skills_root, "some-helper", "A helper skill in the library.")

        result = _invoke(
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(skills_root),
        )
        assert result.exit_code == 0, result.output
        assert "Traceback" not in result.output, result.output
        # Library still profiled.
        assert "some-helper" in result.output, result.output
        assert "UNMEASURED" in result.output, result.output


class TestScreenProfileBadSkillsRoot:
    def test_non_directory_skills_root_warns_and_continues(self, tmp_path: Path) -> None:
        evidence_db = tmp_path / "evidence.db"
        _seed_screen(evidence_db, "alpha-skill", n_trials=10, n_pass=10)
        bogus_root = tmp_path / "does-not-exist"
        result = _invoke(
            "screen",
            "profile",
            "--evidence-db",
            str(evidence_db),
            "--skills-root",
            str(bogus_root),
        )
        assert result.exit_code == 0, result.output
        # A silent drop gives the user zero signal; the command must warn.
        assert "not a directory" in result.output.lower(), result.output
        # Screened skills are still profiled.
        assert "alpha-skill" in result.output, result.output


class TestScreenProfileHelp:
    def test_help_documents_flags(self) -> None:
        result = _invoke("screen", "profile", "--help")
        assert result.exit_code == 0
        assert "--skills-root" in result.output
        assert "--show-held-columns" in result.output


class TestEstimandScopeColumn:
    """#51 (record #36): wherever verdicts render, the estimand surfaces from the
    Estimand enum — and a verdict with no registered scope (every screen-store
    row today) renders the honest pre-registry n/a marker, never a retrofitted
    label (#41 rule)."""

    def test_screen_verdict_renders_estimand_column_with_pre_registry_marker(
        self, tmp_path: Path
    ) -> None:
        evidence_db = tmp_path / "evidence.db"
        _seed_screen(evidence_db, "alpha-skill", n_trials=10, n_pass=10)
        result = _invoke("screen", "verdict", "--evidence-db", str(evidence_db))
        assert result.exit_code == 0, result.output
        assert "estimand" in result.output.lower(), (
            f"'screen verdict' must render an estimand column:\n{result.output}"
        )
        from skill_harness.semantics import PRE_REGISTRY_ESTIMAND_LABEL

        assert PRE_REGISTRY_ESTIMAND_LABEL in result.output, (
            f"store rows are pre-registry observations and must say so:\n{result.output}"
        )

    def test_profile_renders_estimand_column(self, tmp_path: Path) -> None:
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
        assert "estimand" in result.output.lower(), (
            f"profile must render the estimand scope column:\n{result.output}"
        )
        from skill_harness.semantics import PRE_REGISTRY_ESTIMAND_LABEL

        # alpha is screened -> pre-registry marker; beta/gamma have no verdict
        # at all, so their estimand cell is an em-dash (nothing to scope).
        assert PRE_REGISTRY_ESTIMAND_LABEL in result.output, result.output
