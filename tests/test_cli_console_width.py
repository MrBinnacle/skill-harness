"""Acceptance test for issue #564: Console reads COLUMNS at import, not at render.

The defect: ``_console = Console()`` at module level in ``cli/main.py`` reads
``COLUMNS`` once at import and pins ``self._width``.  Tests that later set
``os.environ["COLUMNS"]`` via ``CliRunner(..., env={"COLUMNS": "200"})`` have
no effect — the Console already ignores the environment.

The fix: make the Console lazily constructed so it reads the environment at
render time, not at import time.

This test proves the fix by spawning a subprocess that:
  1. Sets ``COLUMNS=80`` in its environment.
  2. Imports the CLI module (Console reads COLUMNS=80 and would pin width=80).
  3. Invokes a table-rendering command via CliRunner with ``env={"COLUMNS": "200"}``.
  4. Asserts a substring that only survives at width 200 and is truncated at 80.

Before the fix: step 2 pins Console width to 80; step 3 changes os.environ but
not the Console; step 4 fails (truncated output).

After the fix: the Console is constructed lazily (or per-invocation) and reads
the environment at render time, so step 3's COLUMNS=200 takes effect and step 4
passes.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def test_console_width_reads_columns_at_render_not_import() -> None:
    """COLUMNS set before import must not pin the Console for later renders.

    Spawns a fresh subprocess so the module import is under our control.
    """
    script = textwrap.dedent(
        """\
        import hashlib
        import os
        from pathlib import Path

        # --- Step 1: COLUMNS=80 is already in the subprocess environment ---
        assert os.environ.get("COLUMNS") == "80", "subprocess env not set"

        # --- Step 2: import the CLI module (Console reads COLUMNS here) ---
        from click.testing import CliRunner
        from skill_harness.cli.main import cli

        # --- Step 3: seed minimal data for `screen profile` ---
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="issue564_"))
        evidence_db = tmp / "evidence.db"
        skills_root = tmp / "skills"
        skills_root.mkdir(exist_ok=True)

        # Create a skill card
        skill_dir = skills_root / "alpha-skill"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\\nname: alpha-skill\\ndescription: Alpha does things.\\n---\\n\\nBody.\\n",
            encoding="utf-8",
        )

        # Seed screen data
        def sha(text: str) -> str:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()

        from skill_harness.storage.migrations import open_evidence
        from skill_harness.storage.models import ScreenRunWrite, ScreenTrialWrite
        from skill_harness.storage.repositories.evidence.screens import (
            insert_screen_run,
            insert_screen_trial,
        )

        ts = "2026-07-01T10:00:00.000Z"
        conn = open_evidence(evidence_db)
        try:
            insert_screen_run(
                conn,
                ScreenRunWrite(
                    screen_run_id="sr-alpha",
                    skill_name="alpha-skill",
                    subject_model="claude-sonnet-4-6",
                    harness_pin_fingerprint=None,
                    source_eval_task_id="task-1",
                    source_eval_sha256=sha("task-1"),
                    admissibility_state="admissible",
                    inadmissibility_reason=None,
                    d4_check_state="not_applicable",
                    created_at=ts,
                    ingested_at=ts,
                ),
            )
            for i in range(10):
                insert_screen_trial(
                    conn,
                    ScreenTrialWrite(
                        screen_trial_id=f"st-alpha-{i}",
                        screen_run_id="sr-alpha",
                        epoch=i,
                        passed=1,
                        scorer_name="mechanical",
                        scorer_explanation=None,
                        output_sha256=sha(f"alpha-{i}"),
                        sampled_at=ts,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        # --- Step 4: invoke with COLUMNS=200 via CliRunner ---
        result = CliRunner().invoke(
            cli,
            [
                "screen",
                "profile",
                "--evidence-db",
                str(evidence_db),
                "--skills-root",
                str(skills_root),
            ],
            env={"COLUMNS": "200"},
        )

        assert result.exit_code == 0, result.output

        # The estimand column renders "n/a (pre-registry observation)" (30 chars).
        # At width 80 the table truncates this; at width 200 it fits.
        label = "n/a (pre-registry observation)"
        assert label in result.output, result.output
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**dict(__import__("os").environ), "COLUMNS": "80"},
    )

    print("STDOUT:", result.stdout)
    if result.stderr:
        # Only print last 500 chars of stderr to avoid noise
        print("STDERR (tail):", result.stderr[-500:])

    assert result.returncode == 0, (
        f"subprocess failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr[-1000:]}"
    )
