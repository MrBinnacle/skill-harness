"""Receipts-site generator: fixture receipts in, asserted content out (#186).

Fixture-only, no network, no model calls. Every assertion here is about what a
visitor can see on a rendered page or about the build refusing, never about which
internal branch ran.

The property the site exists to hold is that it cannot invent a number:
``test_refused_cost_leg_is_rendered_without_a_number`` and
``test_every_number_on_a_page_traces_to_the_receipt`` are the two directions of
that, and ``test_invalid_receipt_refuses_before_rendering`` is the RED-then-guarded
case for the validation gate.
"""

from __future__ import annotations

import json
import re
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from jsonschema.exceptions import ValidationError  # type: ignore[import-untyped]

from skill_harness.extractor.clause_evidence import (
    REASON_NO_EXTRACTION,
    SECTION_TITLE,
    append_extraction_result,
    format_instrument_line,
    format_summary_lines,
    load_clause_evidence,
)
from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractionResult,
    FalsifyingCaseSchema,
)
from skill_harness.sitegen import SiteBuildError, build_site, load_receipts, load_schema
from skill_harness.sitegen.__main__ import main as sitegen_main
from skill_harness.sitegen.render import ABSENT_TEXT, skill_page_name

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = _REPO_ROOT / "docs" / "sers" / "sers.schema.json"
_RECEIPTS = _REPO_ROOT / "docs" / "sers" / "receipts"
_VALID = _RECEIPTS / "double-ceiling-nogo-2026-07-09.json"

_MARKER = "build-marker-7f3a91"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_receipt(**overrides: Any) -> dict[str, Any]:
    """A receipt that validates, with no measurements block at all."""
    receipt: dict[str, Any] = {
        "sers_version": "1.0.0",
        "skill_name": "fixture-skill",
        "verdict": "CANT_TELL_YET",
        "cut_sub_reason": None,
        "unmeasured_sub_reason": "no_data",
        "value_class": None,
        "evidence_admissibility": {"status": "not_applicable"},
        "cost": {
            "standing_tokens": {"refusal": "not_instrumented", "detail": "never instrumented"},
            "fired_tokens": {"tokens": 1234},
            "aux_tokens": {"refusal": "not_applicable"},
        },
        "instrument_identity": {
            "extractor_model": "fixture-model",
            "prompt_fingerprint": "prompt-fp",
            "schema_fingerprint": "schema-fp",
        },
        "source": {"prose_path": "docs/README.md"},
        "summary": "Fixture receipt: nothing here is a measurement of anything.",
    }
    receipt.update(overrides)
    return receipt


def _write_receipts(tmp_path: Path, *receipts: dict[str, Any]) -> Path:
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir()
    for index, receipt in enumerate(receipts):
        (receipts_dir / f"fixture-{index}.json").write_text(json.dumps(receipt), encoding="utf-8")
    return receipts_dir


def _copy_real_receipt(tmp_path: Path) -> Path:
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir()
    (receipts_dir / "valid.json").write_text(_VALID.read_text(encoding="utf-8"), encoding="utf-8")
    return receipts_dir


def _extraction_jsonl(path: Path, *, skill_name: str, sha: str = "a" * 64) -> Path:
    falsifying_case = FalsifyingCaseSchema(
        input_population_spec="fixture prompts",
        expected_directional_pair="A cites the source; B does not",
        min_reproducibility=0.8,
    )
    result = ExtractionResult(
        skill_id=sha,
        name=skill_name,
        source_path="/fixture/SKILL.md",
        source_sha256=sha,
        clauses=[
            ExtractedClause(
                clause_index=0,
                clause_text="Be concise when summarising tables.",
                axis="verbosity",
                comparator="decrease",
                oracle_tier=1,
                vacuity_flag="none",
                falsifying_case=falsifying_case,
            ),
            ExtractedClause(
                clause_index=1,
                clause_text="Prefer elegance in layout.",
                axis="elegance",
                comparator="increase",
                oracle_tier=2,
                vacuity_flag="semantic_vacuous_pending_review",
                vacuity_kind="weak_directive",
                vacuity_reason="elegance is not a measurable axis",
                falsifying_case=None,
            ),
        ],
        raw_frontmatter={"name": skill_name},
        extractor_model="fixture-model",
        system_prompt_sha256="b" * 64,
        tool_schema_sha256="c" * 64,
    )
    append_extraction_result(path, result)
    return path


def _build(
    tmp_path: Path,
    *,
    receipts_dir: Path,
    extraction_path: Path | None = None,
    output_name: str = "site",
    marker: str = _MARKER,
) -> Path:
    output = tmp_path / output_name
    build_site(
        schema_path=_SCHEMA,
        receipts_dir=receipts_dir,
        extraction_path=extraction_path,
        output_dir=output,
        marker=marker,
    )
    return output


def _main_text(page: Path) -> str:
    """Visible text of the page's <main> element, whitespace-collapsed.

    Text nodes are joined with a space rather than concatenated: a table header
    cell and the figure cell after it are separate words on screen, and running
    them together would fuse two numbers into a third that is on no page.
    """
    main = ET.parse(page).getroot().find("body/main")
    assert main is not None, f"{page.name} has no <main> element"
    words = [fragment.strip() for fragment in main.itertext() if fragment.strip()]
    return re.sub(r"\s+", " ", " ".join(words))


def _cell(page: Path, row_label: str) -> str:
    """Text of the figure cell of the table row whose header is ``row_label``."""
    for row in ET.parse(page).getroot().iter("tr"):
        header = row.find("th")
        if header is not None and (header.text or "").strip() == row_label:
            cells = row.findall("td")
            assert cells, f"row {row_label!r} has no cells"
            return "".join(cells[0].itertext()).strip()
    raise AssertionError(f"no row labelled {row_label!r} in {page.name}")


# ---------------------------------------------------------------------------
# The validation gate: rendering and validation are the same event
# ---------------------------------------------------------------------------


def test_load_receipts_validates_and_returns_claims(tmp_path: Path) -> None:
    loaded = load_receipts(_SCHEMA, _copy_real_receipt(tmp_path))

    assert [receipt["skill_name"] for receipt in loaded] == ["sqlite-expert"]
    assert loaded[0]["verdict"] == "CANT_TELL_YET"


def test_invalid_receipt_refuses_before_rendering(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    invalid = json.loads(_VALID.read_text(encoding="utf-8"))
    del invalid["cost"]["standing_tokens"]
    (receipts / "invalid.json").write_text(json.dumps(invalid), encoding="utf-8")
    output = tmp_path / "site"

    with pytest.raises(ValidationError, match="standing_tokens"):
        build_site(
            schema_path=_SCHEMA,
            receipts_dir=receipts,
            extraction_path=None,
            output_dir=output,
            marker=_MARKER,
        )

    assert not output.exists()


def test_one_invalid_receipt_publishes_none_of_the_valid_ones(tmp_path: Path) -> None:
    """The gate is per build, not per receipt: no partial site survives a refusal."""
    invalid = _minimal_receipt(skill_name="broken-skill")
    del invalid["cost"]["aux_tokens"]
    receipts = _write_receipts(tmp_path, _minimal_receipt(), invalid)
    output = tmp_path / "site"

    with pytest.raises(ValidationError, match="aux_tokens"):
        build_site(
            schema_path=_SCHEMA,
            receipts_dir=receipts,
            extraction_path=None,
            output_dir=output,
            marker=_MARKER,
        )

    assert not output.exists()


def test_build_refuses_without_a_content_marker(tmp_path: Path) -> None:
    """A build with no marker cannot be verified from the published URL."""
    receipts = _write_receipts(tmp_path, _minimal_receipt())
    output = tmp_path / "site"

    with pytest.raises(SiteBuildError, match="marker"):
        build_site(
            schema_path=_SCHEMA,
            receipts_dir=receipts,
            extraction_path=None,
            output_dir=output,
            marker="   ",
        )

    assert not output.exists()


def test_build_refuses_to_overwrite_an_existing_output_directory(tmp_path: Path) -> None:
    receipts = _write_receipts(tmp_path, _minimal_receipt())
    output = tmp_path / "site"
    output.mkdir()

    with pytest.raises(FileExistsError):
        build_site(
            schema_path=_SCHEMA,
            receipts_dir=receipts,
            extraction_path=None,
            output_dir=output,
            marker=_MARKER,
        )


# ---------------------------------------------------------------------------
# Asserted content out
# ---------------------------------------------------------------------------


def test_index_page_states_every_receipt_claim(tmp_path: Path) -> None:
    output = _build(tmp_path, receipts_dir=_copy_real_receipt(tmp_path))

    index = _main_text(output / "index.html")
    assert "sqlite-expert" in index
    assert "CANT_TELL_YET" in index
    assert "unmeasured: underpowered" in index
    assert "admissible" in index
    assert "docs/case-studies/double-ceiling-structurally-unmeasured.md" in index
    assert skill_page_name("sqlite-expert") in (output / "index.html").read_text(encoding="utf-8")


def test_skill_page_puts_the_cost_triple_beside_the_clause_evidence(tmp_path: Path) -> None:
    output = _build(tmp_path, receipts_dir=_copy_real_receipt(tmp_path))
    page = output / skill_page_name("sqlite-expert")

    assert _cell(page, "standing_tokens") == "REFUSED (not_instrumented)"
    assert _cell(page, "fired_tokens") == "REFUSED (not_instrumented)"
    assert _cell(page, "aux_tokens") == "REFUSED (not_applicable)"
    # Beside, not on another page: one section holds both.
    root = ET.parse(page).getroot()
    beside = [
        section
        for section in root.iter("section")
        if section.get("class") == "cost-beside-evidence"
    ]
    assert len(beside) == 1
    text = "".join(beside[0].itertext())
    assert "standing_tokens" in text
    assert "Clause evidence: UNMEASURED" in text


def test_refusal_verdict_and_sub_reason_are_primary_content(tmp_path: Path) -> None:
    """CANT_TELL_YET and its sub-reason are in the body copy, not a footnote."""
    output = _build(tmp_path, receipts_dir=_copy_real_receipt(tmp_path))
    page = output / skill_page_name("sqlite-expert")
    root = ET.parse(page).getroot()

    main_text = _main_text(page)
    assert "Verdict: CANT_TELL_YET" in main_text
    assert "Unmeasured sub-reason underpowered" in main_text
    # Nothing on the page hides content behind a disclosure widget or aside.
    assert [element.tag for element in root.iter() if element.tag in {"details", "aside"}] == []
    # The verdict is stated before the sections that qualify it.
    assert main_text.index("CANT_TELL_YET") < main_text.index("Cost beside evidence")


def test_refusal_lines_are_rendered_verbatim(tmp_path: Path) -> None:
    output = _build(tmp_path, receipts_dir=_copy_real_receipt(tmp_path))
    page_text = _main_text(output / skill_page_name("sqlite-expert"))

    # The clause-evidence refusal, exactly as the audit path words it.
    assert f"Clause evidence: UNMEASURED ({REASON_NO_EXTRACTION})" in page_text
    # The receipt's own refusal detail, not a paraphrase of it.
    assert (
        "Case study reports USD spend (~$6.17), not the standing/fired/aux token triple."
        in page_text
    )
    assert (
        "At d\u22720.5 no effect is detectable inside N_max=40; Full-vs-Null is "
        "structurally UNMEASURED regardless of budget." in page_text
    )


def test_refused_cost_leg_is_rendered_without_a_number(tmp_path: Path) -> None:
    """The refusal direction of "never invents a number", pinned per cell."""
    receipts = _write_receipts(tmp_path, _minimal_receipt())
    output = _build(tmp_path, receipts_dir=receipts)
    page = output / skill_page_name("fixture-skill")

    refused = _cell(page, "standing_tokens")
    assert refused == "REFUSED (not_instrumented)"
    assert not any(char.isdigit() for char in refused), refused
    # The measured leg beside it carries the receipt's figure, unchanged.
    assert _cell(page, "fired_tokens") == "1234 tokens"


def test_absent_measurement_is_stated_absent_and_never_filled_in(tmp_path: Path) -> None:
    """A receipt with no measurements block yields no measurement numbers."""
    receipts = _write_receipts(tmp_path, _minimal_receipt())
    output = _build(tmp_path, receipts_dir=receipts)
    page = output / skill_page_name("fixture-skill")

    schema = load_schema(_SCHEMA)
    keys = list(schema["properties"]["measurements"]["properties"])
    assert keys, "schema declares no measurement keys"
    for key in keys:
        cell = _cell(page, key)
        assert cell == ABSENT_TEXT, f"{key}: {cell!r}"
        assert not any(char.isdigit() for char in cell)


def test_every_number_on_a_page_traces_to_the_receipt(tmp_path: Path) -> None:
    """No digit run in the rendered body originates in the generator.

    The generator's only sources of figures are the receipt and the
    clause-evidence loader; anything else on the page would be interpolation.
    """
    receipts = _copy_real_receipt(tmp_path)
    output = _build(tmp_path, receipts_dir=receipts)
    page = output / skill_page_name("sqlite-expert")

    allowed = (receipts / "valid.json").read_text(encoding="utf-8") + REASON_NO_EXTRACTION
    unexplained = [run for run in re.findall(r"\d+", _main_text(page)) if run not in allowed]
    assert unexplained == [], f"numbers not present in the receipt: {unexplained}"


def test_schema_page_publishes_the_closed_vocabularies(tmp_path: Path) -> None:
    output = _build(tmp_path, receipts_dir=_write_receipts(tmp_path, _minimal_receipt()))
    text = _main_text(output / "schema.html")

    for value in ("KEEP", "CUT", "CANT_TELL_YET", "underpowered", "not_instrumented"):
        assert value in text, value
    # The machine-readable schema itself is published beside the pages.
    published = output / "sers.schema.json"
    assert json.loads(published.read_text(encoding="utf-8")) == load_schema(_SCHEMA)


def test_every_page_carries_the_build_marker(tmp_path: Path) -> None:
    """The deploy check greps the published URL for this marker."""
    output = _build(tmp_path, receipts_dir=_copy_real_receipt(tmp_path))

    pages = sorted(output.glob("*.html"))
    assert len(pages) >= 3
    for page in pages:
        assert _MARKER in page.read_text(encoding="utf-8"), page.name


def test_one_stylesheet_and_no_script(tmp_path: Path) -> None:
    output = _build(tmp_path, receipts_dir=_copy_real_receipt(tmp_path))

    assert [path.name for path in sorted(output.glob("*.css"))] == ["style.css"]
    assert list(output.glob("*.js")) == []
    for page in sorted(output.glob("*.html")):
        root = ET.parse(page).getroot()
        assert [element.tag for element in root.iter("script")] == [], page.name
        links = [element.get("href") for element in root.iter("link")]
        assert links == ["style.css"], page.name


# ---------------------------------------------------------------------------
# The extraction join, through the audit path's own loader
# ---------------------------------------------------------------------------


def test_clause_level_grade_matches_the_audit_loader(tmp_path: Path) -> None:
    receipts = _write_receipts(tmp_path, _minimal_receipt())
    extraction = _extraction_jsonl(tmp_path / "extraction.jsonl", skill_name="fixture-skill")
    output = _build(tmp_path, receipts_dir=receipts, extraction_path=extraction)
    page_text = _main_text(output / skill_page_name("fixture-skill"))

    outcome = load_clause_evidence(extraction, "a" * 64)
    assert outcome.kind == "measured"
    assert outcome.measured is not None
    assert SECTION_TITLE in page_text
    assert format_instrument_line(outcome.measured.instrument) in page_text
    for line in format_summary_lines(outcome.measured.summary):
        assert line in page_text, line
    # Clause-level, not just the roll-up: each clause's axis and flag are shown.
    for clause in outcome.measured.rows:
        assert clause.axis in page_text
        assert clause.vacuity_flag in page_text


def test_join_only_skill_gets_a_page_that_claims_no_verdict(tmp_path: Path) -> None:
    receipts = _write_receipts(tmp_path, _minimal_receipt())
    extraction = _extraction_jsonl(tmp_path / "extraction.jsonl", skill_name="unreceipted-skill")
    output = _build(tmp_path, receipts_dir=receipts, extraction_path=extraction)

    page = output / skill_page_name("unreceipted-skill")
    text = _main_text(page)
    assert "No receipt on file for this skill" in text
    assert "Verdict" not in text
    assert "verbosity" in text
    # And the index says so rather than leaving the page unreachable.
    index = _main_text(output / "index.html")
    assert "unreceipted-skill" in index


def test_skill_name_under_two_shas_refuses_rather_than_choosing(tmp_path: Path) -> None:
    receipts = _write_receipts(tmp_path, _minimal_receipt())
    extraction = tmp_path / "extraction.jsonl"
    _extraction_jsonl(extraction, skill_name="fixture-skill", sha="a" * 64)
    _extraction_jsonl(extraction, skill_name="fixture-skill", sha="d" * 64)
    output = tmp_path / "site"

    with pytest.raises(SiteBuildError, match="refusing to choose"):
        build_site(
            schema_path=_SCHEMA,
            receipts_dir=receipts,
            extraction_path=extraction,
            output_dir=output,
            marker=_MARKER,
        )

    assert not output.exists()


def test_two_receipts_for_one_skill_refuse_rather_than_choosing(tmp_path: Path) -> None:
    receipts = _write_receipts(tmp_path, _minimal_receipt(), _minimal_receipt())
    output = tmp_path / "site"

    with pytest.raises(SiteBuildError, match="refusing to choose"):
        build_site(
            schema_path=_SCHEMA,
            receipts_dir=receipts,
            extraction_path=None,
            output_dir=output,
            marker=_MARKER,
        )

    assert not output.exists()


# ---------------------------------------------------------------------------
# The command the Pages workflow runs
# ---------------------------------------------------------------------------


def test_module_entry_point_builds_the_site(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "site"
    exit_code = sitegen_main(
        [
            "--schema",
            str(_SCHEMA),
            "--receipts",
            str(_RECEIPTS),
            "--output",
            str(output),
            "--marker",
            _MARKER,
        ]
    )

    assert exit_code == 0
    assert (output / "index.html").is_file()
    assert "SITE BUILD:" in capsys.readouterr().out


def test_module_entry_point_reports_a_refusal_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid = _minimal_receipt()
    invalid["verdict"] = "PROBABLY_FINE"
    receipts = _write_receipts(tmp_path, invalid)
    output = tmp_path / "site"

    exit_code = sitegen_main(
        [
            "--schema",
            str(_SCHEMA),
            "--receipts",
            str(receipts),
            "--output",
            str(output),
            "--marker",
            _MARKER,
        ]
    )

    assert exit_code == 1
    assert not output.exists()
    assert "SITE BUILD: REFUSED" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# The repo's own data
# ---------------------------------------------------------------------------


def test_repo_receipts_build_a_page_each_with_no_warnings(tmp_path: Path) -> None:
    """AC: the site builds locally from repo data, with zero warnings."""
    output = tmp_path / "site"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = build_site(
            schema_path=_SCHEMA,
            receipts_dir=_RECEIPTS,
            extraction_path=None,
            output_dir=output,
            marker=_MARKER,
        )
    assert [str(warning.message) for warning in caught] == []

    receipts = load_receipts(_SCHEMA, _RECEIPTS)
    expected = {"index.html", "schema.html", "style.css", "sers.schema.json"} | {
        skill_page_name(receipt["skill_name"]) for receipt in receipts
    }
    assert {path.name for path in written} == expected
    for page in sorted(output.glob("*.html")):
        ET.parse(page)  # semantic markup, well-formed enough to parse
