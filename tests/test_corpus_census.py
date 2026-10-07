"""Tests for the deterministic extracted-clause corpus census (#118).

Pins external behaviour: given a fixture JSONL, the census reports fixed
counts, excludes metadata and failed-extraction rows from every denominator,
refuses structural-completeness on boolean-only falsifying_case schemas, and
re-runs byte-identically. No network, no model.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from skill_harness.extractor.corpus_census import (
    format_human_report,
    receipt_json_bytes,
    run_census,
    write_receipt,
)
from skill_harness.oracles.tier1.axis_registry import (
    TIER1_AXIS_NAMES,
    AxisScoreability,
    classify_axis,
)

_REPO = Path(__file__).resolve().parent.parent
_FIXTURES = _REPO / "tests" / "fixtures" / "corpus_census"
_SCRIPT = _REPO / "scripts" / "corpus_census.py"
_CURRENT = _FIXTURES / "current_gen.jsonl"
_OLDER = _FIXTURES / "older_gen_boolean_fc.jsonl"


# ---------------------------------------------------------------------------
# Current-generation fixture — full falsifying_case objects
# ---------------------------------------------------------------------------


def test_current_gen_excludes_metadata_and_failed_from_denominators() -> None:
    result = run_census(_CURRENT)
    # 2 metadata + 1 failed + 2 ok skills = 5 rows
    assert result.rows_total == 5
    assert result.metadata_rows_skipped == 2
    assert result.skills_covered == 2
    assert result.failed_extraction_slugs == ("brandkit",)
    # 5 clauses from skill-alpha + 1 from skill-beta; brandkit contributes 0
    assert result.known_clause_subtotal == 6


def test_current_gen_scoreable_axis_uses_registry_join() -> None:
    result = run_census(_CURRENT)
    # verbosity, hedge_index, compliance_proxy, structure_score,
    # citation_presence_per_flag = 5 scoreable; formality = 1 unscoreable
    assert result.scoreable_axis_count == 5
    assert result.unscoreable_axis_count == 1
    axis_sum = result.scoreable_axis_count + result.unscoreable_axis_count
    assert axis_sum == result.known_clause_subtotal
    # Sanity: the unscoreable axis really is outside the registry.
    assert classify_axis("formality") is AxisScoreability.UNSCOREABLE
    assert "formality" not in TIER1_AXIS_NAMES


def test_current_gen_comparator_unspecified_count() -> None:
    result = run_census(_CURRENT)
    assert result.comparator_unspecified_count == 1
    assert result.comparator_specified_count == 5


def test_current_gen_falsifying_case_structural_completeness_measured() -> None:
    result = run_census(_CURRENT)
    assert result.falsifying_case_status == "measured"
    assert result.falsifying_case_reason is None
    # vacuity_flag == none: indices 0,1,2,4 from alpha + 0 from beta = 5
    # complete: 0,1,2 alpha + beta = 4; incomplete: alpha index 4 (missing keys)
    assert result.falsifying_case_applicable_count == 5
    assert result.falsifying_case_complete_count == 4
    assert result.falsifying_case_incomplete_count == 1


def test_current_gen_vacuity_flag_tally() -> None:
    result = run_census(_CURRENT)
    assert result.vacuity_none_count == 5
    assert result.vacuity_semantic_pending_count == 1
    assert result.vacuity_other == ()


# ---------------------------------------------------------------------------
# #123 — unreviewed marker attached to semantic_vacuous_pending_review counts
# ---------------------------------------------------------------------------

_UNREVIEWED_MARKER_PHRASE = "unreviewed model judgement"
_UNREVIEWED_MEANING_PHRASE = "model's judgement about model instructions"
_NOT_ADJUDICATED_PHRASE = "not an adjudicated finding"


def test_human_report_marks_semantic_vacuous_count_as_unreviewed() -> None:
    """#123: rendered count carries explicit unreviewed marker on the same line.

    A reader who sees only the figure must still see that it is an unreviewed
    model judgement, not an adjudicated finding. Marker is words, not a symbol.
    """
    result = run_census(_CURRENT)
    assert result.vacuity_semantic_pending_count == 1
    human = format_human_report(result)
    # Find the line that carries the semantic_vacuous_pending_review count.
    tally_lines = [
        line
        for line in human.splitlines()
        if "semantic_vacuous_pending_review" in line and "1" in line
    ]
    assert tally_lines, (
        "human report must render semantic_vacuous_pending_review with its count:\n" + human
    )
    line = tally_lines[0]
    assert _UNREVIEWED_MARKER_PHRASE in line.lower(), (
        f"count line must carry unreviewed marker in the same output as the number:\n{line!r}"
    )
    assert _UNREVIEWED_MEANING_PHRASE in line.lower() or _NOT_ADJUDICATED_PHRASE in line.lower(), (
        f"marker must state meaning in words (model judgement, not adjudicated):\n{line!r}"
    )


def test_receipt_separates_unreviewed_from_reviewed_vacuity() -> None:
    """#123: receipt shape separates unreviewed from reviewed; never one total.

    Reviewed bucket is present (empty today) so a later reviewed category cannot
    be collapsed into the unreviewed count.
    """
    result = run_census(_CURRENT)
    receipt = result.to_receipt()
    tally = receipt["vacuity_flag_tally"]
    assert "unreviewed" in tally, "receipt must nest pending-review under unreviewed"
    assert "reviewed" in tally, "receipt must expose a reviewed bucket (empty until review exists)"
    unreviewed = tally["unreviewed"]
    assert isinstance(unreviewed, dict)
    pending = unreviewed["semantic_vacuous_pending_review"]
    assert isinstance(pending, dict)
    assert pending["count"] == 1
    label = str(pending.get("label", "")).lower()
    assert _UNREVIEWED_MARKER_PHRASE in label
    assert _UNREVIEWED_MEANING_PHRASE in label or _NOT_ADJUDICATED_PHRASE in label
    # Bare int under the old key would let readers treat it as final; forbid collapse.
    assert not isinstance(tally.get("semantic_vacuous_pending_review"), int)
    assert isinstance(tally["reviewed"], dict)
    # No undifferentiated total that sums reviewed + unreviewed.
    assert "total" not in tally
    assert "all" not in tally


def test_cli_stdout_and_receipt_carry_unreviewed_marker(tmp_path: Path) -> None:
    """#123: reporting seam (CLI stdout + JSON receipt) both disclose unreviewed."""
    receipt_path = tmp_path / "receipt.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), str(_CURRENT), "--receipt", str(receipt_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
    )
    assert proc.returncode == 0, proc.stderr
    assert "semantic_vacuous_pending_review" in proc.stdout
    assert _UNREVIEWED_MARKER_PHRASE in proc.stdout.lower()
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    pending = data["vacuity_flag_tally"]["unreviewed"]["semantic_vacuous_pending_review"]
    assert pending["count"] == 1
    assert _UNREVIEWED_MARKER_PHRASE in str(pending["label"]).lower()


def test_current_gen_records_extractor_model_from_header() -> None:
    result = run_census(_CURRENT)
    assert result.extractor_model == "claude-opus-5"


def test_current_gen_axis_distribution_sorted_and_complete() -> None:
    result = run_census(_CURRENT)
    axes = [name for name, _ in result.axis_distribution]
    assert axes == sorted(axes)
    assert sum(count for _, count in result.axis_distribution) == result.known_clause_subtotal
    as_dict = dict(result.axis_distribution)
    assert as_dict["compliance_proxy"] == 1
    assert as_dict["formality"] == 1
    assert as_dict["verbosity"] == 1


def test_current_gen_receipt_has_required_fields() -> None:
    result = run_census(_CURRENT)
    receipt = result.to_receipt()
    assert receipt["extractor_model"] == "claude-opus-5"
    assert receipt["known_clause_subtotal"] == 6
    assert receipt["scoreable_axis"]["count"] == 5
    assert receipt["unscoreable_axis"]["count"] == 1
    assert receipt["comparator_unspecified"]["count"] == 1
    assert receipt["failed_extractions"] == {"count": 1, "slugs": ["brandkit"]}
    assert receipt["metadata_rows_skipped"] == 2
    assert receipt["skills_covered"] == 2
    fc = receipt["falsifying_case_structural_completeness"]
    assert fc["status"] == "measured"
    assert fc["structurally_incomplete"] == 1
    assert "percent_complete_of_applicable" in fc
    # Must not look like a zeroed-out refusal.
    assert "reason" not in fc


def test_current_gen_receipt_omits_zero_and_hundred_incomplete_on_measured() -> None:
    """Structurally incomplete is a real count, not a silent 100% incomplete dump."""
    result = run_census(_CURRENT)
    text = format_human_report(result)
    assert "unmeasurable_for_this_input" not in text
    assert "structurally_incomplete: 1" in text


# ---------------------------------------------------------------------------
# Older generation — boolean-only has_falsifying_case; refuse criterion 3
# ---------------------------------------------------------------------------


def test_older_gen_refuses_structural_completeness_never_zero() -> None:
    result = run_census(_OLDER)
    assert result.falsifying_case_status == "unmeasurable_for_this_input"
    assert result.falsifying_case_reason is not None
    assert "falsifying_case" in result.falsifying_case_reason
    assert result.falsifying_case_complete_count == 0
    assert result.falsifying_case_incomplete_count == 0

    receipt = result.to_receipt()
    fc = receipt["falsifying_case_structural_completeness"]
    assert fc == {
        "reason": result.falsifying_case_reason,
        "status": "unmeasurable_for_this_input",
    }
    # Refuse-don't-zero: no percent, no incomplete count that could read as 0% or 100%.
    assert "structurally_incomplete" not in fc
    assert "structurally_complete" not in fc
    assert "percent_complete_of_applicable" not in fc
    human = format_human_report(result)
    assert "unmeasurable_for_this_input" in human
    fc_block = human.split("falsifying_case_structural_completeness")[1].split(
        "vacuity_flag_tally"
    )[0]
    assert "0%" not in fc_block
    assert "100%" not in fc_block
    assert "incomplete" not in fc_block


def test_older_gen_still_computes_other_categories() -> None:
    result = run_census(_OLDER)
    # 3 + 1 clauses from two ok skills; brandkit failed excluded
    assert result.known_clause_subtotal == 4
    assert result.skills_covered == 2
    assert result.failed_extraction_slugs == ("brandkit",)
    assert result.metadata_rows_skipped == 0
    # verbosity, compliance_proxy, structure_score scoreable; formality not
    assert result.scoreable_axis_count == 3
    assert result.unscoreable_axis_count == 1
    assert result.comparator_unspecified_count == 1
    assert result.vacuity_none_count == 3
    assert result.vacuity_semantic_pending_count == 1
    assert result.extractor_model == "claude-sonnet-4-6"


def test_failed_extraction_does_not_count_as_zero_clause_skill() -> None:
    """brandkit is a failed extraction, not a skill with zero scoreable clauses."""
    for path in (_CURRENT, _OLDER):
        result = run_census(path)
        assert result.failed_extraction_slugs == ("brandkit",)
        # Failed rows are outside skills_covered; they do not pad clause totals.
        assert result.skills_covered >= 1
        receipt = result.to_receipt()
        assert receipt["failed_extractions"] == {"count": 1, "slugs": ["brandkit"]}
        assert (
            receipt["skills_covered"]
            + receipt["failed_extractions"]["count"]
            + receipt["metadata_rows_skipped"]
            == receipt["rows_total"]
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_rerun_produces_byte_identical_receipt(tmp_path: Path) -> None:
    r1 = run_census(_CURRENT)
    r2 = run_census(_CURRENT)
    assert receipt_json_bytes(r1) == receipt_json_bytes(r2)
    assert format_human_report(r1) == format_human_report(r2)

    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    write_receipt(r1, p1)
    write_receipt(r2, p2)
    assert p1.read_bytes() == p2.read_bytes()


def test_receipt_json_is_sorted_and_stable() -> None:
    raw = receipt_json_bytes(run_census(_CURRENT))
    # Re-parse and re-dump with sort_keys must match (canonical form).
    data = json.loads(raw.decode("utf-8"))
    again = (json.dumps(data, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")
    assert raw == again


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_writes_receipt_and_stdout(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), str(_CURRENT), "--receipt", str(receipt)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
    )
    assert proc.returncode == 0, proc.stderr
    assert "known_clause_subtotal: 6" in proc.stdout
    assert "scoreable_axis: 5" in proc.stdout
    assert "failed_extractions: 1" in proc.stdout
    assert "brandkit" in proc.stdout
    assert "metadata_rows_skipped: 2" in proc.stdout
    assert receipt.is_file()
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["extractor_model"] == "claude-opus-5"
    assert data["known_clause_subtotal"] == 6


def test_cli_older_gen_refuses_on_stdout(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), str(_OLDER), "--receipt", str(receipt)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
    )
    assert proc.returncode == 0, proc.stderr
    assert "unmeasurable_for_this_input" in proc.stdout
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["falsifying_case_structural_completeness"]["status"] == (
        "unmeasurable_for_this_input"
    )


def test_cli_missing_file_exits_nonzero() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), str(_REPO / "no-such.jsonl")],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
    )
    assert proc.returncode != 0


def test_no_network_import_side_effects() -> None:
    """Census module must not pull network-touching scorer imports at import time."""
    # classify_axis / registry names only — get_tier1_scorers is the lazy path.
    import skill_harness.extractor.corpus_census as mod

    assert hasattr(mod, "run_census")
    # Running on fixture must not need scorers either.
    run_census(_CURRENT)


@pytest.mark.parametrize("path", [_CURRENT, _OLDER])
def test_failed_row_with_empty_clauses_never_enters_axis_counts(path: Path) -> None:
    result = run_census(path)
    # If brandkit were counted as a zero-clause skill, skills_covered would
    # include it. It must appear only under failed_extractions.
    assert result.failed_extraction_slugs == ("brandkit",)
    receipt = json.loads(receipt_json_bytes(result))
    assert (
        receipt["skills_covered"]
        + receipt["failed_extractions"]["count"]
        + receipt["metadata_rows_skipped"]
        == receipt["rows_total"]
    )


def test_cli_report_is_ascii_only(tmp_path: Path) -> None:
    """Report text must be ASCII: a Windows console is cp1252 by default.

    A single em dash is written as byte 0x97 there and then fails to decode
    in any UTF-8 reader. That took out both windows CI cells on #121, and
    again on #123 when a new label reintroduced one into this module -- which
    the coverage module's guard could not see, because it only ever checked
    the coverage CLI. Asserting on the bytes a user actually sees is the only
    check that catches a reintroduced character.
    """
    receipt = tmp_path / "receipt.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), str(_CURRENT), "--receipt", str(receipt)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
    )
    assert proc.returncode == 0, proc.stderr
    offenders = sorted({ch for ch in proc.stdout if not ch.isascii()})
    assert not offenders, f"non-ASCII in CLI report: {offenders!r}"


def test_cli_help_text_is_ascii_only() -> None:
    """--help is a user-facing surface too, and it is not covered above.

    The argparse description carried a latent em dash that no test ever
    rendered, so the defect sat in the module while the report was clean.
    """
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
    )
    offenders = sorted({ch for ch in proc.stdout if not ch.isascii()})
    assert not offenders, f"non-ASCII in CLI --help: {offenders!r}"
