"""Tests for dual corpus coverage: constructible vs instantiated (#121).

Pins external behaviour:
- both figures reported per skill and corpus-wide, each with denominator
- each figure labelled constructible vs instantiated in the output itself
- instantiated is a named refusal (never 0%) when no frozen_cases / no evidence DB
- per-skill constructible inherits boolean-only unmeasurable refusal
- ok:false and metadata rows excluded from every denominator, reported by slug
- falsifying_case_complete is the public shared predicate (no second copy)
- CensusResult corpus-wide receipt keys stay present
- zero network; byte-identical re-run; JSON receipt written
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from skill_harness.extractor import corpus_census as census_mod
from skill_harness.extractor.corpus_census import (
    falsifying_case_complete,
    run_census,
)
from skill_harness.extractor.corpus_coverage import (
    format_human_report,
    receipt_json_bytes,
    run_coverage,
    write_receipt,
)
from skill_harness.storage.migrations import open_evidence

_REPO = Path(__file__).resolve().parent.parent
_FIXTURES = _REPO / "tests" / "fixtures" / "corpus_census"
_SCRIPT = _REPO / "scripts" / "corpus_coverage.py"
_MULTI = _FIXTURES / "coverage_multi_skill.jsonl"
_CURRENT = _FIXTURES / "current_gen.jsonl"
_OLDER = _FIXTURES / "older_gen_boolean_fc.jsonl"

_TS = "2026-06-06T10:00:00.000Z"
_SHA = "a" * 64


def _seed_evidence_with_one_frozen(path: Path) -> Path:
    """Evidence DB: skill-gamma clauses 0..2; only clause 0 has a frozen_case.

    skill-delta present with two clauses, zero frozen_cases.
    """
    conn = open_evidence(path)
    try:
        conn.execute(
            "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
            " VALUES ('sid-gamma', 'skill-gamma', '/g.md', ?, ?)",
            (_SHA, _TS),
        )
        conn.execute(
            "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
            " VALUES ('sid-delta', 'skill-delta', '/d.md', ?, ?)",
            ("b" * 64, _TS),
        )
        for idx, cid in enumerate(("cg-0", "cg-1", "cg-2")):
            conn.execute(
                "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
                " clause_text, axis, comparator, oracle_tier, vacuity_flag)"
                " VALUES (?, 'sid-gamma', ?, ?, ?, 'verbosity', 'increase', 1, 'none')",
                (cid, idx, idx, f"g{idx}"),
            )
        for idx, cid in enumerate(("cd-0", "cd-1")):
            conn.execute(
                "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
                " clause_text, axis, comparator, oracle_tier, vacuity_flag)"
                " VALUES (?, 'sid-delta', ?, ?, ?, 'formality', 'increase', 1, 'none')",
                (cid, idx, idx, f"d{idx}"),
            )
        conn.execute(
            "INSERT INTO metric_versions (metric_id, version, implementation_hash, tier,"
            " audited, mechanical_validity_test_passed)"
            " VALUES ('verbosity', '1.0.0', ?, 1, 1, 1)",
            ("c" * 64,),
        )
        conn.execute(
            "INSERT INTO frozen_cases ("
            " frozen_case_id, clause_id, failing_input_text, failing_input_sha256,"
            " oracle_source, metric_id, metric_version, implementation_hash, frozen_at"
            ") VALUES ("
            " 'fc-g0', 'cg-0', 'failing input', ?, 'mechanical',"
            " 'verbosity', '1.0.0', ?, ?"
            ")",
            ("d" * 64, "c" * 64, _TS),
        )
        conn.commit()
    finally:
        conn.close()
    return path


# ---------------------------------------------------------------------------
# Predicate promotion
# ---------------------------------------------------------------------------


def test_falsifying_case_complete_is_public_and_only_implementation() -> None:
    assert callable(falsifying_case_complete)
    assert not hasattr(census_mod, "_falsifying_case_complete")
    src = Path(census_mod.__file__).read_text(encoding="utf-8")
    # No private twin left behind.
    assert "def _falsifying_case_complete" not in src
    assert "def falsifying_case_complete" in src
    # No second implementation elsewhere under src/.
    tree = _REPO / "src"
    copies = []
    for path in tree.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"def\s+falsifying_case_complete\s*\(", text):
            copies.append(path)
        # Structural completeness key-set only lives in corpus_census.
        if (
            path.name != "corpus_census.py"
            and "_FC_REQUIRED_KEYS" in text
            and "input_population_spec" in text
            and "expected_directional_pair" in text
            and "min_reproducibility" in text
        ):
            copies.append(path)
    assert copies == [tree / "skill_harness" / "extractor" / "corpus_census.py"]


def test_predicate_behaviour_byte_identical_to_prior() -> None:
    complete = {
        "falsifying_case": {
            "input_population_spec": "x",
            "expected_directional_pair": "y",
            "min_reproducibility": 0.5,
        }
    }
    assert falsifying_case_complete(complete) is True
    assert falsifying_case_complete({"falsifying_case": True}) is False
    assert falsifying_case_complete({}) is False
    assert (
        falsifying_case_complete(
            {"falsifying_case": {"input_population_spec": "x", "expected_directional_pair": "y"}}
        )
        is False
    )
    assert (
        falsifying_case_complete(
            {
                "falsifying_case": {
                    "input_population_spec": "",
                    "expected_directional_pair": "y",
                    "min_reproducibility": 0.5,
                }
            }
        )
        is False
    )


# ---------------------------------------------------------------------------
# Census per-skill extension + existing receipt keys
# ---------------------------------------------------------------------------


def test_census_per_skill_constructible_and_receipt_keys_stable() -> None:
    result = run_census(_CURRENT)
    assert result.per_skill
    slugs = [r.slug for r in result.per_skill]
    assert slugs == sorted(slugs)
    assert "brandkit" not in slugs
    by = {r.slug: r for r in result.per_skill}
    # alpha: indices 0,1,2 complete; 3 vacuous; 4 incomplete → 3 constructible / 5
    assert by["skill-alpha"].total_clauses == 5
    assert by["skill-alpha"].constructible_count == 3
    assert by["skill-alpha"].falsifying_case_status == "measured"
    assert by["skill-beta"].constructible_count == 1
    assert by["skill-beta"].total_clauses == 1

    receipt = result.to_receipt()
    # #118 corpus-wide keys must still be present with same semantics.
    for key in (
        "total_clauses",
        "scoreable_axis",
        "unscoreable_axis",
        "comparator_specified",
        "comparator_unspecified",
        "falsifying_case_structural_completeness",
        "failed_extractions",
        "metadata_rows_skipped",
        "skills_covered",
        "axis_distribution",
        "vacuity_flag_tally",
        "extractor_model",
        "input_path",
        "rows_total",
    ):
        assert key in receipt
    assert receipt["total_clauses"] == 6
    assert receipt["failed_extractions"] == {"count": 1, "slugs": ["brandkit"]}
    assert "per_skill" in receipt


def test_census_per_skill_boolean_only_refuses() -> None:
    result = run_census(_OLDER)
    assert result.per_skill
    for row in result.per_skill:
        assert row.falsifying_case_status == "unmeasurable_for_this_input"
        assert row.falsifying_case_reason is not None
        assert "falsifying_case" in row.falsifying_case_reason
        assert row.constructible_count == 0


# ---------------------------------------------------------------------------
# Dual coverage — multi-skill fixture
# ---------------------------------------------------------------------------


def test_no_evidence_refuses_instantiated_never_zero_percent() -> None:
    result = run_coverage(_MULTI)
    assert result.corpus_instantiated.status == "refused"
    assert result.corpus_instantiated.reason is not None
    assert "no_evidence_database" in result.corpus_instantiated.reason
    human = format_human_report(result)
    receipt = result.to_receipt()
    # No percentage for the refused instantiated figure anywhere.
    inst_block = human.split("instantiated_coverage:")[1].split("constructible_coverage:")[0]
    assert "0%" not in inst_block
    assert "%" not in inst_block.split("status:")[1].split("\n")[0]
    corpus_inst = receipt["corpus"]["instantiated_coverage"]
    assert "percent" not in corpus_inst
    assert corpus_inst["status"] == "refused"
    for row in receipt["per_skill"]:
        assert row["instantiated_coverage"]["status"] == "refused"
        assert "percent" not in row["instantiated_coverage"]


def test_multi_skill_constructible_split_not_corpus_mean(tmp_path: Path) -> None:
    """Per-skill constructible must not collapse into the corpus mean."""
    ev = _seed_evidence_with_one_frozen(tmp_path / "evidence.db")
    result = run_coverage(_MULTI, evidence_path=ev)
    by = {r.slug: r for r in result.per_skill}
    assert set(by) == {"skill-delta", "skill-gamma"}
    # gamma: 2 constructible (idx 0,1) / 3; idx 2 incomplete
    assert by["skill-gamma"].constructible.status == "measured"
    assert by["skill-gamma"].constructible.numerator == 2
    assert by["skill-gamma"].constructible.denominator == 3
    # delta: 1 constructible / 2
    assert by["skill-delta"].constructible.numerator == 1
    assert by["skill-delta"].constructible.denominator == 2
    # Corpus: 3/5 — not equal to either skill alone.
    assert result.corpus_constructible.numerator == 3
    assert result.corpus_constructible.denominator == 5
    assert result.corpus_constructible.numerator / result.corpus_constructible.denominator not in (
        2 / 3,
        1 / 2,
    )


def test_multi_skill_instantiated_three_way_and_refusal_on_empty_skill(
    tmp_path: Path,
) -> None:
    """One constructible+instantiated, one constructible-not-instantiated, one neither.

    skill-delta has zero frozen_cases → named refusal, not 0%.
    """
    ev = _seed_evidence_with_one_frozen(tmp_path / "evidence.db")
    result = run_coverage(_MULTI, evidence_path=ev)
    by = {r.slug: r for r in result.per_skill}

    g = by["skill-gamma"]
    assert g.instantiated.status == "measured"
    assert g.instantiated.numerator == 1  # only clause 0
    assert g.instantiated.denominator == 3
    # Labels present on the figure itself.
    assert g.constructible.label == "constructible"
    assert g.instantiated.label == "instantiated"

    d = by["skill-delta"]
    assert d.instantiated.status == "refused"
    assert d.instantiated.reason is not None
    assert "no_instantiated_frozen_cases" in d.instantiated.reason
    d_receipt = d.instantiated.to_receipt()
    assert "percent" not in d_receipt

    # Corpus has ≥1 frozen case → measured 1/5.
    assert result.corpus_instantiated.status == "measured"
    assert result.corpus_instantiated.numerator == 1
    assert result.corpus_instantiated.denominator == 5


def test_empty_frozen_cases_db_refuses_never_zero_percent(tmp_path: Path) -> None:
    """Evidence DB with clauses but zero frozen_cases → instrument-gap refusal."""
    db = tmp_path / "empty-fc.db"
    conn = open_evidence(db)
    try:
        conn.execute(
            "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
            " VALUES ('sid-gamma', 'skill-gamma', '/g.md', ?, ?)",
            (_SHA, _TS),
        )
        conn.execute(
            "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
            " clause_text, axis, comparator, oracle_tier, vacuity_flag)"
            " VALUES ('cg-0', 'sid-gamma', 0, 0, 'x', 'verbosity', 'increase', 1, 'none')"
        )
        conn.commit()
    finally:
        conn.close()

    result = run_coverage(_MULTI, evidence_path=db)
    assert result.corpus_instantiated.status == "refused"
    assert "no_instantiated_frozen_cases" in (result.corpus_instantiated.reason or "")
    human = format_human_report(result)
    # Guard: no "0%" attached to an instantiated_coverage measured line.
    for block in human.split("instantiated_coverage:"):
        if "status: refused" in block.split("\n")[2] if len(block.split("\n")) > 2 else False:
            pass
    assert "instantiated_coverage:" in human
    # Receipt: no percent key on refused instantiated figures.
    receipt = json.loads(receipt_json_bytes(result))
    assert "percent" not in receipt["corpus"]["instantiated_coverage"]
    assert (
        "0%"
        not in format_human_report(result)
        .split("missing_stage_note")[0]
        .split("instantiated_coverage:")[1]
        .split("per_skill:")[0]
    )


def test_boolean_only_constructible_refusal_per_skill() -> None:
    result = run_coverage(_OLDER)
    assert result.corpus_constructible.status == "unmeasurable_for_this_input"
    assert result.corpus_constructible.reason is not None
    human = format_human_report(result)
    assert "unmeasurable_for_this_input" in human
    for row in result.per_skill:
        assert row.constructible.status == "unmeasurable_for_this_input"
        assert row.constructible.reason is not None
        assert "percent" not in row.constructible.to_receipt()
    # Must not look like 0% constructible.
    c_block = human.split("constructible_coverage:")[1].split("instantiated_coverage:")[0]
    assert "0%" not in c_block
    assert "100%" not in c_block


def test_failed_and_metadata_excluded_and_named() -> None:
    result = run_coverage(_MULTI)
    assert result.metadata_rows_skipped == 2
    assert result.failed_extraction_slugs == ("broken-skill",)
    assert result.skills_covered == 2
    assert result.total_clauses == 5
    assert "broken-skill" not in [r.slug for r in result.per_skill]
    receipt = result.to_receipt()
    assert receipt["failed_extractions"] == {"count": 1, "slugs": ["broken-skill"]}
    assert receipt["metadata_rows_skipped"] == 2


def test_missing_stage_note_present_in_output() -> None:
    result = run_coverage(_MULTI)
    assert "input_population_spec" in result.missing_stage_note
    assert "failing_input_text" in result.missing_stage_note
    assert "metric_id" in result.missing_stage_note
    human = format_human_report(result)
    assert "input_population_spec" in human
    assert "failing_input_text" in human
    receipt = result.to_receipt()
    assert "input_population_spec" in receipt["missing_stage_note"]


def test_labels_distinguish_constructible_from_instantiated_in_output(
    tmp_path: Path,
) -> None:
    ev = _seed_evidence_with_one_frozen(tmp_path / "evidence.db")
    result = run_coverage(_MULTI, evidence_path=ev)
    human = format_human_report(result)
    assert "constructible_coverage:" in human
    assert "instantiated_coverage:" in human
    assert "structurally complete falsifying_case" in human
    assert "frozen_cases" in human
    receipt = result.to_receipt()
    cc = receipt["corpus"]["constructible_coverage"]
    ic = receipt["corpus"]["instantiated_coverage"]
    assert cc["label"] == "constructible"
    assert ic["label"] == "instantiated"
    assert "constructible" in cc["what_it_measures"]
    assert "frozen_cases" in ic["what_it_measures"]
    # Both denominators present.
    assert cc["denominator"] == 5
    assert ic["denominator"] == 5


def test_rerun_byte_identical(tmp_path: Path) -> None:
    ev = _seed_evidence_with_one_frozen(tmp_path / "evidence.db")
    r1 = run_coverage(_MULTI, evidence_path=ev)
    r2 = run_coverage(_MULTI, evidence_path=ev)
    assert receipt_json_bytes(r1) == receipt_json_bytes(r2)
    assert format_human_report(r1) == format_human_report(r2)
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    write_receipt(r1, p1)
    write_receipt(r2, p2)
    assert p1.read_bytes() == p2.read_bytes()


def test_cli_writes_receipt(tmp_path: Path) -> None:
    ev = _seed_evidence_with_one_frozen(tmp_path / "evidence.db")
    receipt = tmp_path / "receipt.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            str(_MULTI),
            "--evidence",
            str(ev),
            "--receipt",
            str(receipt),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
    )
    assert proc.returncode == 0, proc.stderr
    assert "constructible_coverage:" in proc.stdout
    assert "instantiated_coverage:" in proc.stdout
    assert "skill-gamma" in proc.stdout
    assert "broken-skill" in proc.stdout
    assert receipt.is_file()
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["corpus"]["constructible_coverage"]["label"] == "constructible"
    assert data["corpus"]["instantiated_coverage"]["status"] == "measured"


def test_cli_without_evidence_refuses_instantiated(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), str(_MULTI), "--receipt", str(receipt)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
    )
    assert proc.returncode == 0, proc.stderr
    assert "no_evidence_database" in proc.stdout
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["corpus"]["instantiated_coverage"]["status"] == "refused"
    assert "percent" not in data["corpus"]["instantiated_coverage"]


def test_no_second_predicate_implementation_in_coverage_module() -> None:
    cov_path = _REPO / "src" / "skill_harness" / "extractor" / "corpus_coverage.py"
    text = cov_path.read_text(encoding="utf-8")
    assert "def falsifying_case_complete" not in text
    assert "_FC_REQUIRED_KEYS" not in text
