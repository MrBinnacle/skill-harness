"""Tests for the persisted skill audit record (#673).

`skill audit --persist` writes one hash-bound JSON record per skill. The reader
returns the record only while its sha256 still matches the card's SKILL.md, so a
stale audit can never grant the `audited` evidence rung that #658 reads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from skill_harness import __version__
from skill_harness.audit_record import (
    AuditRecord,
    AuditRecordError,
    audit_record_for,
    record_from_report,
    write_audit_record,
)
from skill_harness.cli.main import cli
from skill_harness.preflight import audit_skill_artifact

GOOD_SKILL = """---
name: processing-pdfs
description: Extracts text and tables from PDF files. Use when working with PDFs.
---

# PDF Processing

Use pdfplumber for text extraction from `scripts/helper.py`.
"""

AUDITED_AT = "2026-10-28T12:00:00+00:00"


def _skill(tmp_path: Path, content: str = GOOD_SKILL) -> Path:
    skill_dir = tmp_path / "processing-pdfs"
    skill_dir.mkdir()
    path = skill_dir / "SKILL.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_record_carries_every_required_field(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    report = audit_skill_artifact(skill)
    record = record_from_report(report, audited_at_utc=AUDITED_AT)

    assert record.skill_name == "processing-pdfs"
    assert record.skill_md_sha256 == report.source_sha256
    assert record.audit_tool_version == __version__
    assert record.audited_at_utc == AUDITED_AT
    assert record.standing_cost.raw_tokens == report.standing_cost_raw
    assert record.standing_cost.calibrated_tokens == report.standing_cost_calibrated
    assert record.standing_cost.calibration_range == report.standing_cost_calibration_range
    assert record.claim_classification.tier1_mechanical_axes == report.measurable_axes
    assert record.claim_classification.behavior_shaped == "UNMEASURED"
    assert record.claim_classification.judge_graded == "UNMEASURED"


def test_standing_cost_is_never_labelled_exact(tmp_path: Path) -> None:
    record = record_from_report(audit_skill_artifact(_skill(tmp_path)), audited_at_utc=AUDITED_AT)
    text = record.model_dump_json()
    assert "exact" not in text.lower()
    assert record.standing_cost.basis == "calibrated_estimate"


def test_round_trip_through_reader(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    audits = tmp_path / "audits"
    record = record_from_report(audit_skill_artifact(skill), audited_at_utc=AUDITED_AT)

    written = write_audit_record(record, audits)

    assert written == audits / "processing-pdfs.json"
    assert audit_record_for(skill, audits) == record


def test_reader_returns_none_without_a_record(tmp_path: Path) -> None:
    assert audit_record_for(_skill(tmp_path), tmp_path / "audits") is None


def test_poison_stale_hash_does_not_grant_audited(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    audits = tmp_path / "audits"
    write_audit_record(
        record_from_report(audit_skill_artifact(skill), audited_at_utc=AUDITED_AT), audits
    )

    skill.write_text(GOOD_SKILL + "\nOne more line changes the hash.\n", encoding="utf-8")

    assert audit_record_for(skill, audits) is None


def test_poison_record_with_hand_edited_hash_is_refused(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    audits = tmp_path / "audits"
    path = write_audit_record(
        record_from_report(audit_skill_artifact(skill), audited_at_utc=AUDITED_AT), audits
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    data["skill_md_sha256"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")

    assert audit_record_for(skill, audits) is None


def test_malformed_record_raises_rather_than_granting(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    audits = tmp_path / "audits"
    audits.mkdir()
    (audits / "processing-pdfs.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(AuditRecordError):
        audit_record_for(skill, audits)


NAMELESS_SKILL = """---
description: Extracts text and tables from PDF files. Use when working with PDFs.
---

# PDF Processing
"""

ODD_NAME_SKILL = GOOD_SKILL.replace("name: processing-pdfs", "name: My_Helper")


@pytest.mark.parametrize("content", [NAMELESS_SKILL, ODD_NAME_SKILL])
def test_any_name_the_audit_accepts_persists_and_reads_back(tmp_path: Path, content: str) -> None:
    skill = _skill(tmp_path, content)
    audits = tmp_path / "audits"
    record = record_from_report(audit_skill_artifact(skill), audited_at_utc=AUDITED_AT)

    written = write_audit_record(record, audits)

    assert written.parent == audits
    assert audit_record_for(skill, audits) == record


@pytest.mark.parametrize("name", ["../escape", "a/b", "A_Upper", "", "x\\y", "..", "CON"])
def test_odd_name_maps_to_a_file_inside_audits_dir(tmp_path: Path, name: str) -> None:
    record = record_from_report(audit_skill_artifact(_skill(tmp_path)), audited_at_utc=AUDITED_AT)
    audits = tmp_path / "audits"
    written = write_audit_record(record.model_copy(update={"skill_name": name}), audits)
    assert written.resolve().parent == audits.resolve()
    assert sorted(p.name for p in audits.iterdir()) == [written.name]


def test_distinct_odd_names_never_share_a_file(tmp_path: Path) -> None:
    record = record_from_report(audit_skill_artifact(_skill(tmp_path)), audited_at_utc=AUDITED_AT)
    audits = tmp_path / "audits"
    names = ["My_Helper", "my-helper", "my_helper", "MY HELPER", "../my-helper", "", "_", "-"]
    paths = {write_audit_record(record.model_copy(update={"skill_name": n}), audits) for n in names}
    assert len(paths) == len(names)


def test_reader_returns_none_for_an_odd_name_with_no_record(tmp_path: Path) -> None:
    assert audit_record_for(_skill(tmp_path, ODD_NAME_SKILL), tmp_path / "audits") is None
    (tmp_path / "n").mkdir()
    assert audit_record_for(_skill(tmp_path / "n", NAMELESS_SKILL), tmp_path / "audits") is None


def test_write_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    record = record_from_report(audit_skill_artifact(_skill(tmp_path)), audited_at_utc=AUDITED_AT)
    audits = tmp_path / "audits"
    write_audit_record(record, audits)
    write_audit_record(record, audits)
    assert [p.name for p in audits.iterdir()] == ["processing-pdfs.json"]


def test_cli_persist_writes_record_for_a_nameless_card(tmp_path: Path) -> None:
    skill = _skill(tmp_path, NAMELESS_SKILL)
    out = tmp_path / "audits"
    result = CliRunner().invoke(cli, ["skill", "audit", str(skill), "--persist", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert isinstance(audit_record_for(skill, out), AuditRecord)


def test_cli_persist_writes_record(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    out = tmp_path / "audits"
    result = CliRunner().invoke(cli, ["skill", "audit", str(skill), "--persist", "--out", str(out)])
    assert result.exit_code == 0, result.output
    record = audit_record_for(skill, out)
    assert isinstance(record, AuditRecord)
    assert (out / "processing-pdfs.json").is_file()
    assert "Audit record written" in result.output


def test_cli_without_persist_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill = _skill(tmp_path)
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    before = sorted(p for p in tmp_path.rglob("*"))
    result = CliRunner().invoke(cli, ["skill", "audit", str(skill)])
    assert result.exit_code == 0, result.output
    assert sorted(p for p in tmp_path.rglob("*")) == before


def test_cli_out_without_persist_is_a_usage_error(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    out = tmp_path / "audits"
    result = CliRunner().invoke(cli, ["skill", "audit", str(skill), "--out", str(out)])
    assert result.exit_code == 2
    assert "--persist" in result.output
    assert not out.exists()
