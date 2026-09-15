"""The published pages never print a machine token where a reader expects a word (#583).

``_nullable_text`` converted Python ``None`` into the four-character string
``null`` and handed it to the qualifier list, so a receipt page printed
``Cut sub-reason: null`` nine lines below the index's promise that "a missing
number is a typed refusal, never an invented score". The same function turned
``False`` into ``false``, which is a real answer rendered in the wrong language.

The vocabulary is never invented here. It comes from one of three places, in
this order:

1. ``true`` / ``false`` render as ``yes`` / ``no``, the plain-language form of
   the answer the receipt actually carries.
2. A ``None`` whose schema field declares its own null case in the
   ``null = <word>`` form renders that word.
3. Everything else is absent, and wears the treatment the measurements table has
   used since #186: ``ABSENT_TEXT`` with the ``absent`` class.

The ``schema.html`` page is deliberately out of scope. It publishes the closed
vocabularies, and ``null`` is a member of two of those enums, so the word there
is the subject rather than a value.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from skill_harness.sitegen import build_site, load_schema
from skill_harness.sitegen.render import ABSENT_TEXT, null_case_language, skill_page_name

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = _REPO_ROOT / "docs" / "sers" / "sers.schema.json"
_RECEIPTS = _REPO_ROOT / "docs" / "sers" / "receipts"

_MARKER = "null-vocabulary-probe"

# The machine tokens a reader must never meet as a value. Matched as the whole
# text of an element, which is how they reached the live site.
_MACHINE_TOKENS = ("null", "true", "false", "None", "True", "False")


def _minimal_receipt(**overrides: Any) -> dict[str, Any]:
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


def _build(tmp_path: Path, receipts_dir: Path, name: str = "site") -> Path:
    output = tmp_path / name
    build_site(
        schema_path=_SCHEMA,
        receipts_dir=receipts_dir,
        extraction_path=None,
        output_dir=output,
        marker=_MARKER,
    )
    return output


def _definition(page: Path, term: str) -> tuple[str, str]:
    """The text and the class of the ``<dd>`` following the ``<dt>`` reading ``term``."""
    root = ET.parse(page).getroot()
    for definition_list in root.iter("dl"):
        children = list(definition_list)
        for index, child in enumerate(children):
            if child.tag != "dt":
                continue
            if re.sub(r"\s+", " ", "".join(child.itertext())).strip() != term:
                continue
            value = children[index + 1]
            assert value.tag == "dd", f"{term!r} is not followed by a dd"
            text = re.sub(r"\s+", " ", "".join(value.itertext())).strip()
            return text, value.get("class", "")
    raise AssertionError(f"no definition term {term!r} in {page.name}")


def _machine_tokens_printed_as_values(page: Path) -> list[str]:
    """Every element on ``page`` whose entire visible text is a machine token."""
    root = ET.parse(page).getroot()
    found: list[str] = []
    for element in root.iter():
        text = re.sub(r"\s+", " ", "".join(element.itertext())).strip()
        if text in _MACHINE_TOKENS:
            found.append(f"<{element.tag}>{text}</{element.tag}>")
    return found


# ---------------------------------------------------------------------------
# The acceptance criteria named on #583
# ---------------------------------------------------------------------------


def test_no_published_receipt_page_prints_a_machine_token_as_a_value(tmp_path: Path) -> None:
    """The first half of #583's acceptance, run over the receipts that are published."""
    output = _build(tmp_path, _RECEIPTS)
    offenders: dict[str, list[str]] = {}
    pages = sorted(output.glob("skill-*.html"))
    assert pages, "the build wrote no receipt pages"
    for page in pages:
        printed = _machine_tokens_printed_as_values(page)
        if printed:
            offenders[page.name] = printed
    assert offenders == {}, f"machine tokens printed as values: {offenders}"


def test_a_null_qualifier_renders_the_absent_treatment(tmp_path: Path) -> None:
    """The second half: a receipt carrying ``None`` says absent, in the site's one wording."""
    receipts = _write_receipts(tmp_path, _minimal_receipt())
    output = _build(tmp_path, receipts)
    page = output / skill_page_name("fixture-skill")

    text, css_class = _definition(page, "Cut sub-reason")
    assert text == ABSENT_TEXT, text
    assert "absent" in css_class.split(), css_class


def test_a_boolean_qualifier_renders_as_yes_or_no(tmp_path: Path) -> None:
    """``wrong_instrument: false`` is an answer, and ``no`` is its plain-language form."""
    receipts = _write_receipts(
        tmp_path,
        _minimal_receipt(wrong_instrument=False, declared_synthetic_control=True),
    )
    output = _build(tmp_path, receipts)
    page = output / skill_page_name("fixture-skill")

    assert _definition(page, "Wrong instrument")[0] == "no"
    assert _definition(page, "Declared synthetic control")[0] == "yes"


def test_a_null_whose_schema_declares_a_word_uses_the_schema_word(tmp_path: Path) -> None:
    """``value_class`` declares ``null = unclassified``; the page says what the schema says."""
    receipts = _write_receipts(tmp_path, _minimal_receipt(value_class=None))
    output = _build(tmp_path, receipts)
    page = output / skill_page_name("fixture-skill")

    assert _definition(page, "Value class")[0] == "unclassified"


# ---------------------------------------------------------------------------
# The vocabulary reader itself, including its refusal direction
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return load_schema(_SCHEMA)


def test_null_case_language_reads_the_schema_and_invents_nothing(
    schema: dict[str, Any],
) -> None:
    """The one field whose description names a word for its null case, and two that do not.

    ``cut_sub_reason`` and ``unmeasured_sub_reason`` both discuss their null
    case at length without naming a word for it. Returning ``None`` for those is
    the point: the caller then says absent instead of paraphrasing a sentence
    into a label.
    """
    assert null_case_language(schema, "value_class") == "unclassified"
    assert null_case_language(schema, "cut_sub_reason") is None
    assert null_case_language(schema, "unmeasured_sub_reason") is None
    assert null_case_language(schema, "no_such_field_exists") is None
