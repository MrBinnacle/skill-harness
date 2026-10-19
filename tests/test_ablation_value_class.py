"""External behavior for the registered value_class ablation script."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from skill_harness.storage.migrations import open_evidence
from skill_harness.storage.models import ScreenRunWrite, ScreenTrialWrite
from skill_harness.storage.repositories.evidence.screens import (
    insert_screen_run,
    insert_screen_trial,
)

_SCREEN_RECEIPT_TEMPLATE: dict[str, Any] = {
    "sers_version": "1.0.0",
    "skill_name": "test-skill",
    "verdict": "CANT_TELL_YET",
    "cut_sub_reason": None,
    "unmeasured_sub_reason": None,
    "value_class": None,
    "wrong_instrument": False,
    "declared_synthetic_control": True,
    "measurements": {
        "p0": {"value": 0.5, "passes": 4, "epochs": 8},
        "go_nogo": "NOT_APPLICABLE",
    },
}


def _make_receipt(
    skill_name: str,
    value_class: str | None,
    p0: float,
) -> dict[str, Any]:
    """Build a minimal screen-path SERS receipt dict."""
    r: dict[str, Any] = dict(_SCREEN_RECEIPT_TEMPLATE)
    r["skill_name"] = skill_name
    r["value_class"] = value_class
    r["measurements"] = dict(_SCREEN_RECEIPT_TEMPLATE["measurements"])
    r["measurements"]["p0"] = {"value": p0, "passes": int(p0 * 8), "epochs": 8}
    return r


def _seed_evidence_store(path: Path) -> None:
    """Write one admissible, above-bar screen to a temporary evidence store."""
    conn = open_evidence(path)
    try:
        insert_screen_run(
            conn,
            ScreenRunWrite(
                screen_run_id="screen-pull-rebase",
                skill_name="pull-rebase",
                subject_model="test-model",
                harness_pin_fingerprint=None,
                source_eval_task_id="test-task",
                source_eval_sha256="0" * 64,
                admissibility_state="admissible",
                inadmissibility_reason=None,
                d4_check_state="not_applicable",
                created_at="2026-09-22T00:00:00Z",
                ingested_at="2026-09-22T00:00:00Z",
            ),
        )
        insert_screen_trial(
            conn,
            ScreenTrialWrite(
                screen_trial_id="trial-pull-rebase",
                screen_run_id="screen-pull-rebase",
                epoch=0,
                passed=1,
                scorer_name="mechanical",
                scorer_explanation=None,
                output_sha256="1" * 64,
                sampled_at="2026-09-22T00:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_ablation_script_reports_change_and_no_change(tmp_path: Path) -> None:
    """The script reports both required outcomes from only the supplied receipts."""
    receipt_dir = tmp_path / "docs" / "sers" / "receipts"
    receipt_dir.mkdir(parents=True)
    trap = _make_receipt("test-trap-skill", "trap-discipline", p0=1.0)
    lift = _make_receipt("test-lift-skill", "transformative-lift", p0=0.0)
    (receipt_dir / "trap.json").write_text(json.dumps(trap, indent=2), encoding="utf-8")
    (receipt_dir / "lift.json").write_text(json.dumps(lift, indent=2), encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "scripts" / "ablation_value_class.py"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    result = subprocess.run(
        ["python", str(script), "--receipt-dir", str(receipt_dir)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(tmp_path),
        check=False,
    )
    assert result.returncode == 0, (
        f"script exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    rows = {
        fields[0]: fields
        for line in result.stdout.splitlines()
        if (fields := line.split()) and fields[0] in {"trap", "lift"}
    }
    assert rows["trap"] == [
        "trap",
        "test-trap-skill",
        "CANT_TELL_YET",
        "CUT(subsumed)",
        "YES",
    ]
    assert rows["lift"] == [
        "lift",
        "test-lift-skill",
        "CANT_TELL_YET",
        "CANT_TELL_YET",
        "no",
    ]
    assert "Total verdict inputs:  2" in result.stdout
    assert "Verdicts unchanged:    1" in result.stdout


def test_ablation_script_enumerates_offline_evidence_store(tmp_path: Path) -> None:
    """The script includes every screen input derivable from an offline store."""
    evidence_db = tmp_path / "evidence.db"
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    _seed_evidence_store(evidence_db)

    script = Path(__file__).resolve().parents[1] / "scripts" / "ablation_value_class.py"
    result = subprocess.run(
        [
            "python",
            str(script),
            "--receipt-dir",
            str(receipt_dir),
            "--evidence-db",
            str(evidence_db),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    row = next(
        line.split()
        for line in result.stdout.splitlines()
        if line.startswith("evidence.db:pull-rebase")
    )
    assert row == [
        "evidence.db:pull-rebase",
        "pull-rebase",
        "CANT_TELL_YET",
        "CUT(subsumed)",
        "YES",
    ]
    assert "SERS receipts:         0" in result.stdout
    assert "Evidence-store inputs: 1" in result.stdout
