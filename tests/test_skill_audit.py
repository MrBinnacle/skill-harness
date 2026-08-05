"""Tests for the offline `skill audit` preflight (preflight.py + CLI).

All offline — no API calls, no DB, no cost. That property is the feature
under test: audit must work in a fresh clone with no keys set.

Exit-code contract:
  0 = audited (warnings allowed without --strict)
  1 = --strict with >=1 warning, or malformed artifact (ClickException)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from skill_harness.cli.main import cli
from skill_harness.preflight import audit_skill_artifact

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_SKILL = """---
name: processing-pdfs
description: Extracts text and tables from PDF files. Use when working with PDFs.
---

# PDF Processing

Use pdfplumber for text extraction from `scripts/helper.py`.
"""

BAD_SKILL = """---
name: My_Claude_Helper
description: I can help with stuff
---

# Helper

Run scripts\\helper.py to do things.
"""


def write_skill(tmp_path: Path, content: str, filename: str = "SKILL.md") -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# preflight.audit_skill_artifact — pure function
# ---------------------------------------------------------------------------


def test_good_skill_has_no_warnings(tmp_path: Path) -> None:
    report = audit_skill_artifact(write_skill(tmp_path, GOOD_SKILL))
    assert report.warn_count == 0
    assert report.pass_count >= 3  # name, description, body-length
    assert report.name == "processing-pdfs"


def test_bad_skill_flags_each_defect(tmp_path: Path) -> None:
    report = audit_skill_artifact(write_skill(tmp_path, BAD_SKILL))
    codes = {f.code for f in report.findings if f.level == "warn"}
    assert "name-charset" in codes  # uppercase + underscores
    assert "name-reserved-word" in codes  # "claude"
    assert "description-first-person" in codes  # "I can help"
    assert "windows-paths" in codes  # scripts\helper.py


def test_missing_name_and_description_warn(tmp_path: Path) -> None:
    report = audit_skill_artifact(write_skill(tmp_path, "# No frontmatter\n\nJust a body.\n"))
    codes = {f.code for f in report.findings if f.level == "warn"}
    assert "name-missing" in codes
    assert "description-missing" in codes


def test_name_too_long_warns(tmp_path: Path) -> None:
    long_name = "a" * 65
    content = f"---\nname: {long_name}\ndescription: Does a thing. Use when needed.\n---\n\nBody.\n"
    report = audit_skill_artifact(write_skill(tmp_path, content))
    assert "name-too-long" in {f.code for f in report.findings if f.level == "warn"}


def test_description_too_long_warns(tmp_path: Path) -> None:
    desc = "x" * 1025
    content = f"---\nname: ok-skill\ndescription: {desc}\n---\n\nBody.\n"
    report = audit_skill_artifact(write_skill(tmp_path, content))
    assert "description-too-long" in {f.code for f in report.findings if f.level == "warn"}


def test_body_over_500_lines_warns(tmp_path: Path) -> None:
    body = "\n".join(f"line {i}" for i in range(501))
    content = f"---\nname: ok-skill\ndescription: Does a thing. Use when needed.\n---\n{body}\n"
    report = audit_skill_artifact(write_skill(tmp_path, content))
    assert "body-too-long" in {f.code for f in report.findings if f.level == "warn"}


def test_measurable_axes_come_from_live_registry(tmp_path: Path) -> None:
    from skill_harness.ablation.confound import get_default_tier1_scorers

    report = audit_skill_artifact(write_skill(tmp_path, GOOD_SKILL))
    assert report.measurable_axes == tuple(sorted(get_default_tier1_scorers().keys()))
    assert len(report.measurable_axes) > 0


def test_block_scalar_description_refuses_instead_of_passing(tmp_path: Path) -> None:
    """A `description: >` block scalar must NOT pass as a 1-char description.

    Regression: first behavioral run judged the literal '>' indicator and
    reported 'description present (1 chars) and within spec'.
    """
    content = "---\nname: ok-skill\ndescription: >\n  Folded multi-line text.\n---\n\nBody.\n"
    report = audit_skill_artifact(write_skill(tmp_path, content))
    codes_by_level = {(f.level, f.code) for f in report.findings}
    assert ("info", "description-unparsed-block-scalar") in codes_by_level
    assert ("pass", "description") not in codes_by_level
    assert ("warn", "description-missing") not in codes_by_level


def test_no_trigger_vocab_is_info_not_warn(tmp_path: Path) -> None:
    content = "---\nname: ok-skill\ndescription: Does a specific thing well.\n---\n\nBody.\n"
    report = audit_skill_artifact(write_skill(tmp_path, content))
    info_codes = {f.code for f in report.findings if f.level == "info"}
    warn_codes = {f.code for f in report.findings if f.level == "warn"}
    assert "description-no-trigger-vocab" in info_codes
    assert "description-no-trigger-vocab" not in warn_codes


# ---------------------------------------------------------------------------
# CLI: skill audit
# ---------------------------------------------------------------------------


def test_cli_audit_good_skill_exit_0(tmp_path: Path) -> None:
    path = write_skill(tmp_path, GOOD_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    assert "OFFLINE AUDIT" in result.output
    assert "UNMEASURED" in result.output  # the posture is in the output


def test_cli_audit_warnings_exit_0_without_strict(tmp_path: Path) -> None:
    path = write_skill(tmp_path, BAD_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    assert "WARN" in result.output


def test_cli_audit_strict_exits_1_on_warnings(tmp_path: Path) -> None:
    path = write_skill(tmp_path, BAD_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path), "--strict"])
    assert result.exit_code == 1


def test_cli_audit_strict_exits_0_when_clean(tmp_path: Path) -> None:
    path = write_skill(tmp_path, GOOD_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path), "--strict"])
    assert result.exit_code == 0, result.output


def test_cli_audit_malformed_file_fails_cleanly(tmp_path: Path) -> None:
    p = tmp_path / "SKILL.md"
    p.write_bytes(b"---\nname: x\n---\n\n\xff\xfe not utf8")
    result = CliRunner().invoke(cli, ["skill", "audit", str(p)])
    assert result.exit_code == 1
    assert "Error" in result.output


def test_cli_audit_missing_file_fails(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["skill", "audit", str(tmp_path / "nope.md")])
    assert result.exit_code != 0


@pytest.mark.parametrize("flag", ["--help"])
def test_cli_audit_help_names_the_contract(flag: str) -> None:
    result = CliRunner().invoke(cli, ["skill", "audit", flag])
    assert result.exit_code == 0
    assert "no API key" in result.output


# ---------------------------------------------------------------------------
# Standing cost (mechanical, per-turn router listing tax)
# ---------------------------------------------------------------------------

DISABLE_INVOCATION_SKILL = """---
name: manual-only-helper
description: Run this by hand. Use when the operator invokes it explicitly.
disable-model-invocation: true
---

# Manual helper

Body text.
"""

BLOCK_SCALAR_SKILL = """---
name: ok-skill
description: >
  Folded multi-line text that the minimal parser cannot read.
---

Body.
"""


def test_standing_cost_from_name_and_description(tmp_path: Path) -> None:
    """Model-invocable skill: standing cost is cl100k tokens of name + description."""
    from skill_harness.oracles.tier1.verbosity import count_tokens
    from skill_harness.preflight import (
        STANDING_COST_CALIBRATION_FACTOR,
        STANDING_COST_CALIBRATION_RANGE,
    )

    report = audit_skill_artifact(write_skill(tmp_path, GOOD_SKILL))
    assert report.standing_cost_raw is not None
    name = "processing-pdfs"
    desc = "Extracts text and tables from PDF files. Use when working with PDFs."
    expected_raw = count_tokens(name) + count_tokens(desc)
    assert report.standing_cost_raw == expected_raw
    assert report.standing_cost_calibrated == round(
        expected_raw * STANDING_COST_CALIBRATION_FACTOR
    )
    assert report.standing_cost_calibration_factor == STANDING_COST_CALIBRATION_FACTOR
    assert report.standing_cost_calibration_range == STANDING_COST_CALIBRATION_RANGE


def test_disable_model_invocation_standing_cost_is_zero(tmp_path: Path) -> None:
    report = audit_skill_artifact(write_skill(tmp_path, DISABLE_INVOCATION_SKILL))
    assert report.standing_cost_raw == 0
    assert report.standing_cost_calibrated == 0


def test_cli_standing_cost_in_evaluability_block_labelled_mechanical(tmp_path: Path) -> None:
    path = write_skill(tmp_path, GOOD_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    out = result.output
    # Cost lives in the evaluability block, not as a free-standing quoteable figure.
    eval_idx = out.lower().index("evaluability preflight")
    cost_idx = out.lower().index("standing cost", eval_idx)
    assert cost_idx > eval_idx
    assert "mechanical" in out[eval_idx:].lower()
    assert "raw" in out[cost_idx:].lower()
    assert "calibrat" in out[cost_idx:].lower()
    assert "1.128" in out[cost_idx:]
    assert "1.084" in out[cost_idx:]
    assert "1.179" in out[cost_idx:]


def test_cli_disable_model_invocation_prints_zero_standing_cost(tmp_path: Path) -> None:
    path = write_skill(tmp_path, DISABLE_INVOCATION_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "standing cost" in out.lower()
    # Zero must be visibly present (not omitted).
    assert re.search(r"raw\s+0\b", out, re.IGNORECASE) or re.search(
        r"\b0\s+tokens\b", out, re.IGNORECASE
    )


def test_unparseable_frontmatter_finding_and_no_standing_cost_number(tmp_path: Path) -> None:
    """Parse failure must not print a misleading low/zero standing-cost number.

    Both halves are required: the named finding *and* absence of any cost figure.
    """
    report = audit_skill_artifact(write_skill(tmp_path, BLOCK_SCALAR_SKILL))
    codes = {f.code for f in report.findings}
    assert "standing-cost-unparseable" in codes
    assert report.standing_cost_raw is None
    assert report.standing_cost_calibrated is None

    path = write_skill(tmp_path, BLOCK_SCALAR_SKILL, filename="block.md")
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "standing-cost-unparseable" in out
    # No standing-cost number anywhere — not even a fabricated zero beside the finding.
    assert not re.search(r"standing cost[^\n]*\d", out, re.IGNORECASE)
    # Calibrated factor digits must not appear as a cost substitute either when
    # the measurement itself is absent.
    cost_section = out.lower().split("evaluability preflight", 1)[-1]
    assert "raw" not in cost_section or "standing cost" not in cost_section


def test_strict_exits_nonzero_on_unparseable_standing_cost(tmp_path: Path) -> None:
    path = write_skill(tmp_path, BLOCK_SCALAR_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path), "--strict"])
    assert result.exit_code == 1


def test_standing_cost_deterministic(tmp_path: Path) -> None:
    path = write_skill(tmp_path, GOOD_SKILL)
    a = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    b = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert a.exit_code == 0 and b.exit_code == 0
    assert a.output == b.output
