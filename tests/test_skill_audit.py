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


def _cost_figure_block(out: str, label: str) -> str:
    """Slice one mechanical cost figure from the evaluability block.

    Labels are ``standing cost``, ``fired cost``, or ``aux cost``. Rich may wrap
    a single print across physical lines; capture through the next cost label
    or the summary so assertions pin one figure, not sibling costs.
    """
    section = out.lower().split("evaluability preflight", 1)[-1]
    labels = ("standing cost", "fired cost", "aux cost")
    if label not in labels:
        raise ValueError(f"unknown cost label {label!r}")
    others = [name for name in labels if name != label]
    tail = "|".join(re.escape(name) for name in others)
    pattern = rf"{re.escape(label)} \(mechanical\):(.*?)(?=(?:{tail}) \(mechanical\)|summary:|\Z)"
    match = re.search(pattern, section, flags=re.IGNORECASE | re.DOTALL)
    assert match is not None, f"missing {label!r} figure in:\n{out}"
    return match.group(0)


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


def test_cli_audit_summary_matches_readme_and_names_unmeasured_as_state(tmp_path: Path) -> None:
    path = write_skill(tmp_path, BLOCK_SCALAR_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    summary_lines = result.output.split("Summary:", 1)[1].splitlines()
    summary = "Summary: " + " ".join(line.strip() for line in summary_lines[:2]).split(" (", 1)[0]
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")

    readme_summary = next(line for line in readme.splitlines() if line.startswith("Summary:"))
    # The whole line, not just the tail after the em-dash. The tail-only
    # comparison let the counts drift: main carried "0 pass · 0 warn" wording
    # while the CLI printed a warn, and nothing failed, because the counts sit
    # on the half this assertion never read. The README renders the CLI's own
    # line plus a sentence period, so that is exactly what is compared.
    assert summary + "." == readme_summary
    assert summary.split(" — ", 1)[1] + "." == readme_summary.split(" — ", 1)[1]
    assert "UNMEASURED is a recorded state, not a failure" in summary


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
    assert report.standing_cost_calibrated == round(expected_raw * STANDING_COST_CALIBRATION_FACTOR)
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
    standing = _cost_figure_block(result.output, "standing cost")
    # Zero must be visibly present on the standing-cost figure (not omitted,
    # and not satisfied by a sibling cost line).
    assert re.search(r"raw\s+0\b", standing, re.IGNORECASE) or re.search(
        r"\b0\s+tokens\b", standing, re.IGNORECASE
    )


def test_unparseable_frontmatter_finding_and_no_standing_cost_number(tmp_path: Path) -> None:
    """Parse failure must not print a misleading low/zero standing-cost number.

    Both halves are required: the named finding *and* absence of any cost figure
    on the standing-cost line (fired/aux may still print their own numbers).
    """
    skill_dir = tmp_path / "block-skill"
    skill_dir.mkdir()
    report = audit_skill_artifact(write_skill(skill_dir, BLOCK_SCALAR_SKILL))
    codes = {f.code for f in report.findings}
    assert "standing-cost-unparseable" in codes
    assert report.standing_cost_raw is None
    assert report.standing_cost_calibrated is None

    path = write_skill(skill_dir, BLOCK_SCALAR_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "standing-cost-unparseable" in out
    standing = _cost_figure_block(out, "standing cost")
    assert "unmeasured" in standing
    assert "raw" not in standing
    assert not re.search(r"\d", standing)


def test_name_without_description_standing_cost_unmeasured(tmp_path: Path) -> None:
    """name present but no non-empty description → UNMEASURED, no cost number."""
    content = "---\nname: ok-skill\n---\n\nBody.\n"
    skill_dir = tmp_path / "no-desc-skill"
    skill_dir.mkdir()
    report = audit_skill_artifact(write_skill(skill_dir, content))
    codes = {f.code for f in report.findings}
    assert "standing-cost-unparseable" in codes
    assert report.standing_cost_raw is None
    assert report.standing_cost_calibrated is None

    path = write_skill(skill_dir, content)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "standing-cost-unparseable" in out
    standing = _cost_figure_block(out, "standing cost")
    assert "unmeasured" in standing
    assert "raw" not in standing
    assert not re.search(r"\d", standing)


def test_strict_exits_nonzero_on_unparseable_standing_cost(tmp_path: Path) -> None:
    path = write_skill(tmp_path, BLOCK_SCALAR_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path), "--strict"])
    assert result.exit_code == 1


def test_strict_exits_nonzero_on_name_without_description_standing_cost(
    tmp_path: Path,
) -> None:
    content = "---\nname: ok-skill\n---\n\nBody.\n"
    path = write_skill(tmp_path, content)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path), "--strict"])
    assert result.exit_code == 1


def test_no_frontmatter_standing_cost_unmeasured(tmp_path: Path) -> None:
    """No frontmatter block → UNMEASURED, no standing-cost number (especially not 0)."""
    content = "# No frontmatter\n\nJust a body.\n"
    skill_dir = tmp_path / "no-fm-skill"
    skill_dir.mkdir()
    report = audit_skill_artifact(write_skill(skill_dir, content))
    codes = {f.code for f in report.findings}
    assert "standing-cost-unparseable" in codes
    assert report.standing_cost_raw is None
    assert report.standing_cost_calibrated is None

    path = write_skill(skill_dir, content)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "standing-cost-unparseable" in out
    standing = _cost_figure_block(out, "standing cost")
    assert "unmeasured" in standing
    assert "raw" not in standing
    # Must not look like disable-model-invocation's real zero — on this figure.
    assert not re.search(r"\d", standing)
    assert not re.search(r"\braw\s+0\b", standing, re.IGNORECASE)
    assert not re.search(r"\b0\s+tokens\b", standing, re.IGNORECASE)
    # Sibling aux zero is a real figure and must not be confused with standing.
    aux = _cost_figure_block(out, "aux cost")
    assert re.search(r"raw\s+0\b", aux, re.IGNORECASE) or re.search(
        r"\b0\s+tokens\b", aux, re.IGNORECASE
    )


def test_strict_exits_nonzero_on_no_frontmatter_standing_cost(tmp_path: Path) -> None:
    content = "# No frontmatter\n\nJust a body.\n"
    path = write_skill(tmp_path, content)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path), "--strict"])
    assert result.exit_code == 1


def test_standing_cost_deterministic(tmp_path: Path) -> None:
    path = write_skill(tmp_path, GOOD_SKILL)
    a = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    b = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert a.exit_code == 0 and b.exit_code == 0
    assert a.output == b.output


# ---------------------------------------------------------------------------
# Fired cost + aux cost (mechanical; body vs progressive-disclosure docs)
# ---------------------------------------------------------------------------


def test_fired_cost_from_skill_body(tmp_path: Path) -> None:
    """Fired cost is cl100k tokens of the skill body (not frontmatter)."""
    from skill_harness.oracles.tier1.verbosity import count_tokens
    from skill_harness.preflight import STANDING_COST_CALIBRATION_FACTOR

    report = audit_skill_artifact(write_skill(tmp_path, GOOD_SKILL))
    # Body after frontmatter close (parser keeps leading newline).
    body = "\n# PDF Processing\n\nUse pdfplumber for text extraction from `scripts/helper.py`.\n"
    expected_raw = count_tokens(body)
    assert report.fired_cost_raw == expected_raw
    assert report.fired_cost_calibrated == round(expected_raw * STANDING_COST_CALIBRATION_FACTOR)
    assert report.fired_cost_raw is not None
    # Distinct from standing: body tokens ≠ name+description tokens.
    assert report.fired_cost_raw != report.standing_cost_raw


def test_fired_cost_is_newline_normalised(tmp_path: Path) -> None:
    """Identical skill, LF vs CRLF on disk → identical fired cost.

    The body is sliced from raw decoded bytes rather than read in text mode,
    so without normalisation every ``\\r`` is charged and the same skill costs
    more on a Windows checkout than on a Linux one. That would make the figure
    a property of how the file was checked out instead of of the skill.

    Bytes are written explicitly so this pins the behaviour on every platform,
    not only the one whose line ending differs from the author's.
    """
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(GOOD_SKILL.encode("utf-8"))
    crlf.write_bytes(GOOD_SKILL.replace("\n", "\r\n").encode("utf-8"))

    lf_report = audit_skill_artifact(lf)
    crlf_report = audit_skill_artifact(crlf)

    assert lf_report.fired_cost_raw == crlf_report.fired_cost_raw
    assert lf_report.fired_cost_calibrated == crlf_report.fired_cost_calibrated
    # Standing and aux are already newline-stable; assert it so a future change
    # to either path cannot reintroduce a platform-dependent figure unnoticed.
    assert lf_report.standing_cost_raw == crlf_report.standing_cost_raw
    assert lf_report.aux_cost_raw == crlf_report.aux_cost_raw


def test_aux_cost_zero_when_no_aux_files(tmp_path: Path) -> None:
    """No sibling documentation → real zero, not missing/error."""
    report = audit_skill_artifact(write_skill(tmp_path, GOOD_SKILL))
    assert report.aux_cost_raw == 0
    assert report.aux_cost_calibrated == 0


def test_aux_cost_unreadable_refuses_number(tmp_path: Path) -> None:
    """Unreadable aux text → named finding and no aux figure (not a partial sum)."""
    skill_dir = tmp_path / "bad-aux"
    skill_dir.mkdir()
    write_skill(skill_dir, GOOD_SKILL)
    # Invalid UTF-8 payload — read_text(encoding=utf-8) must fail loud.
    (skill_dir / "BROKEN.md").write_bytes(b"\xff\xfe not utf-8 \x80\x81")
    report = audit_skill_artifact(skill_dir / "SKILL.md")
    codes = {f.code for f in report.findings}
    assert "aux-cost-unreadable" in codes
    assert report.aux_cost_raw is None
    assert report.aux_cost_calibrated is None

    result = CliRunner().invoke(cli, ["skill", "audit", str(skill_dir / "SKILL.md")])
    assert result.exit_code == 0, result.output
    assert "aux-cost-unreadable" in result.output
    aux = _cost_figure_block(result.output, "aux cost")
    assert "unmeasured" in aux
    assert "raw" not in aux


def test_aux_cost_counts_sibling_documentation(tmp_path: Path) -> None:
    """Aux cost sums other documentation files beside the skill file."""
    from skill_harness.oracles.tier1.verbosity import count_tokens
    from skill_harness.preflight import STANDING_COST_CALIBRATION_FACTOR

    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    write_skill(skill_dir, GOOD_SKILL)
    aux_a = "AAA reference material for progressive disclosure.\n"
    aux_b = "BBB deeper notes the body may point the model at.\n"
    (skill_dir / "REFERENCE.md").write_text(aux_a, encoding="utf-8")
    (skill_dir / "notes.txt").write_text(aux_b, encoding="utf-8")
    # Non-documentation must not contribute.
    (skill_dir / "helper.py").write_text("print('not docs')\n", encoding="utf-8")

    report = audit_skill_artifact(skill_dir / "SKILL.md")
    expected_raw = count_tokens(aux_a) + count_tokens(aux_b)
    assert report.aux_cost_raw == expected_raw
    assert report.aux_cost_calibrated == round(expected_raw * STANDING_COST_CALIBRATION_FACTOR)


def test_aux_cost_skill_dir_via_symlink_counted_once(tmp_path: Path) -> None:
    """Skill directory reached through a symlink is counted once (no double-count)."""
    from skill_harness.oracles.tier1.verbosity import count_tokens

    real_dir = tmp_path / "real-skill"
    real_dir.mkdir()
    write_skill(real_dir, GOOD_SKILL)
    aux_text = "Unique aux payload that must not be double-counted.\n"
    (real_dir / "EXTRA.md").write_text(aux_text, encoding="utf-8")

    link_dir = tmp_path / "linked-skill"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    via_link = audit_skill_artifact(link_dir / "SKILL.md")
    via_real = audit_skill_artifact(real_dir / "SKILL.md")
    expected = count_tokens(aux_text)
    assert via_link.aux_cost_raw == expected
    assert via_real.aux_cost_raw == expected
    assert via_link.aux_cost_raw == via_real.aux_cost_raw


def test_aux_cost_does_not_follow_symlinks_outward(tmp_path: Path) -> None:
    """Outward symlinks from the skill dir must not pull in foreign docs."""
    from skill_harness.oracles.tier1.verbosity import count_tokens

    outside = tmp_path / "outside"
    outside.mkdir()
    foreign = "FOREIGN documentation that must not be counted.\n"
    (outside / "FOREIGN.md").write_text(foreign, encoding="utf-8")

    skill_dir = tmp_path / "scoped-skill"
    skill_dir.mkdir()
    write_skill(skill_dir, GOOD_SKILL)
    local = "Local aux only.\n"
    (skill_dir / "LOCAL.md").write_text(local, encoding="utf-8")
    (skill_dir / "escape.md").symlink_to(outside / "FOREIGN.md")
    # Symlinked subdirectory pointing outside — must not be walked into.
    (skill_dir / "other-pkg").symlink_to(outside, target_is_directory=True)

    report = audit_skill_artifact(skill_dir / "SKILL.md")
    assert report.aux_cost_raw == count_tokens(local)


def test_costs_deliberately_different_sizes_not_swappable(tmp_path: Path) -> None:
    """Description, body, and aux are sized so swapping any two figures fails."""
    from skill_harness.oracles.tier1.verbosity import count_tokens
    from skill_harness.preflight import STANDING_COST_CALIBRATION_FACTOR

    # Standing (name+desc) small, body medium, aux large — three distinct bands.
    name = "sz-skill"
    desc = "Tiny desc. Use when sizing."  # short
    body = ("BODY-MED " * 40).strip() + "\n"  # medium
    aux = ("AUX-LARGE " * 200).strip() + "\n"  # large

    skill_dir = tmp_path / "sized"
    skill_dir.mkdir()
    content = f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}"
    write_skill(skill_dir, content)
    (skill_dir / "BIG.md").write_text(aux, encoding="utf-8")

    report = audit_skill_artifact(skill_dir / "SKILL.md")
    standing = count_tokens(name) + count_tokens(desc)
    # Parser body includes the blank line after ---.
    fired = count_tokens("\n" + body)
    aux_raw = count_tokens(aux)

    assert report.standing_cost_raw == standing
    assert report.fired_cost_raw == fired
    assert report.aux_cost_raw == aux_raw
    # Strict inequality bands — any pairwise swap fails.
    assert standing < fired < aux_raw
    assert report.standing_cost_calibrated == round(standing * STANDING_COST_CALIBRATION_FACTOR)
    assert report.fired_cost_calibrated == round(fired * STANDING_COST_CALIBRATION_FACTOR)
    assert report.aux_cost_calibrated == round(aux_raw * STANDING_COST_CALIBRATION_FACTOR)


def test_inversion_human_only_large_body_vs_invocable_small_body(tmp_path: Path) -> None:
    """Standing-cost order is the reverse of body-size order (size ≠ standing cost).

    Human-only skills pay zero standing tax regardless of body size; a tiny
    model-invocable skill still pays standing cost on its listing line.
    """
    large_body = "# Human-only manual\n\n" + ("paragraph of guidance\n" * 80)
    human = (
        "---\n"
        "name: big-manual\n"
        "description: Operator manual. Use when invoked by hand only.\n"
        "disable-model-invocation: true\n"
        "---\n"
        f"{large_body}"
    )
    small_body = "# Tiny\n\nGo.\n"
    invocable = (
        "---\n"
        "name: tiny-auto\n"
        "description: Small auto skill with a longer listing line for discovery. "
        "Use when the model should pick this up automatically on matching tasks.\n"
        "---\n"
        f"{small_body}"
    )

    human_dir = tmp_path / "human"
    inv_dir = tmp_path / "inv"
    human_dir.mkdir()
    inv_dir.mkdir()
    human_report = audit_skill_artifact(write_skill(human_dir, human))
    inv_report = audit_skill_artifact(write_skill(inv_dir, invocable))

    assert human_report.standing_cost_raw == 0
    assert inv_report.standing_cost_raw is not None and inv_report.standing_cost_raw > 0
    assert human_report.fired_cost_raw is not None and inv_report.fired_cost_raw is not None
    assert human_report.fired_cost_raw > inv_report.fired_cost_raw
    # The inversion: larger body, smaller standing cost.
    assert human_report.standing_cost_raw < inv_report.standing_cost_raw
    assert human_report.fired_cost_raw > inv_report.fired_cost_raw


def test_cli_three_costs_named_in_evaluability_block(tmp_path: Path) -> None:
    path = write_skill(tmp_path, GOOD_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    out = result.output
    eval_idx = out.lower().index("evaluability preflight")
    section = out[eval_idx:].lower()
    assert "standing cost" in section
    assert "fired cost" in section
    assert "aux cost" in section
    # No combined size figure.
    assert "total cost" not in section
    assert "combined size" not in section
    assert "body size" not in section
    for label in ("standing cost", "fired cost", "aux cost"):
        idx = section.index(label)
        chunk = section[idx : idx + 160]
        assert "mechanical" in chunk
        assert "raw" in chunk
        assert "calibrat" in chunk
        assert "1.128" in chunk


def test_cli_aux_zero_visible(tmp_path: Path) -> None:
    path = write_skill(tmp_path, GOOD_SKILL)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "aux cost" in out.lower()
    # Zero aux must be a printed figure (report field is 0; CLI shows it).
    aux_line = next(line for line in out.splitlines() if "aux cost" in line.lower())
    assert re.search(r"raw\s+0\b", aux_line, re.IGNORECASE) or re.search(
        r"\b0\s+tokens\b", aux_line, re.IGNORECASE
    )


def test_fired_and_aux_offline_deterministic(tmp_path: Path) -> None:
    skill_dir = tmp_path / "det"
    skill_dir.mkdir()
    write_skill(skill_dir, GOOD_SKILL)
    (skill_dir / "REF.md").write_text("Deterministic aux text.\n", encoding="utf-8")
    path = skill_dir / "SKILL.md"
    a = audit_skill_artifact(path)
    b = audit_skill_artifact(path)
    assert a.fired_cost_raw == b.fired_cost_raw
    assert a.aux_cost_raw == b.aux_cost_raw
    ca = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    cb = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert ca.exit_code == 0 and cb.exit_code == 0
    assert ca.output == cb.output
