"""README positioning rewrite lock (#154 / #150 resolution).

Pins external README behaviour only: retired front-door phrases gone, four-part
section order, honest-maturity UNMEASURED lines with ticket links, banner alt
byte-equal to both SVG aria-labels and to the join of their text nodes, status-block
facts retained, drift-registered sentences intact.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_README = _ROOT / "README.md"
_BANNERS = (_ROOT / "assets" / "banner-dark.svg", _ROOT / "assets" / "banner-light.svg")
_SVG_TEXT = "{http://www.w3.org/2000/svg}text"
_DASHES = (chr(0x2014), chr(0x2013))  # em dash, en dash


def _readme() -> str:
    return _README.read_text(encoding="utf-8")


def test_retired_front_door_phrases_absent() -> None:
    text = _readme()
    assert "skill disposition engine" not in text
    assert "first verdict" not in text


def _banner_alt(text: str) -> str:
    picture = re.search(r"<picture>(.*?)</picture>", text, re.DOTALL)
    assert picture is not None, "README has no <picture> banner element"
    alt = re.search(r'<img[^>]*\salt="([^"]*)"', picture.group(1))
    assert alt is not None, "banner <img> has no alt attribute"
    return alt.group(1)


def _label(svg: Path) -> str:
    return ET.fromstring(svg.read_text(encoding="utf-8")).get("aria-label") or ""


def _text_join(root: ET.Element) -> str:
    """The label rule of record (S427 R4): each ``<text>`` node's itertext, stripped,
    in document order; consecutive nodes joined with ``". "`` unless the earlier node
    already ends in ``.``, ``?`` or ``!``, in which case with ``" "``."""
    parts = ["".join(node.itertext()).strip() for node in root.iter(_SVG_TEXT)]
    out = ""
    for part in parts:
        if out:
            out += " " if out.endswith((".", "?", "!")) else ". "
        out += part
    return out


def test_banner_alt_equals_svg_labels_and_text_join() -> None:
    """Property lock, not a string pin: the alt, both aria-labels and each file's text
    join are one byte string, with no em dash or en dash. Any future owner line passes;
    a divergence, a returning dash, or a node added without entering the label fails."""
    alt = _banner_alt(_readme())
    for svg in _BANNERS:
        root = ET.fromstring(svg.read_text(encoding="utf-8"))
        label = root.get("aria-label")
        assert label is not None, f"{svg.name}: root has no aria-label"
        assert label == alt, f"{svg.name}: aria-label differs from README alt"
        assert _text_join(root) == label, f"{svg.name}: aria-label differs from text join"
    labels = {svg.name: _label(svg) for svg in _BANNERS}
    for name, value in {"README alt": alt, **labels}.items():
        assert not any(dash in value for dash in _DASHES), f"{name} carries an em or en dash"


def test_four_part_section_order() -> None:
    """Document body order of record from #150: need, question, audit, refusal."""
    text = _readme()
    # Status block is front-matter; body sections follow.
    need = re.search(
        r"^## .*(?:Why this exists|measurement problem|Why naive|trap)",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    question = re.search(
        r"^## .*(?:What does this skill cost|ratified question|The question)",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    audit = re.search(
        r"^## .*(?:skill audit|offline|no API key|60-second|free offline)",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    refusal = re.search(
        r"^## .*(?:evidence grade|refusal|UNMEASURED|KEEP.*CUT|What it (?:measures|refuses))",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    assert need is not None, "section 1 (statement of need) missing"
    assert question is not None, "section 2 (ratified question) missing"
    assert audit is not None, "section 3 (skill audit / free offline) missing"
    assert refusal is not None, "section 4 (evidence grades / refusal) missing"
    assert need.start() < question.start() < audit.start() < refusal.start(), (
        f"section order wrong: need@{need.start()} question@{question.start()} "
        f"audit@{audit.start()} refusal@{refusal.start()}"
    )


def test_ratified_question_verbatim() -> None:
    text = _readme()
    assert "What does this skill cost you, and which parts of it are worth that cost?" in text


def test_honest_maturity_names_both_gaps_with_tickets() -> None:
    # #152 resolved 2026-08-08 (3x repeat: 29/33/34 clauses, not stable), so the
    # repeat-variance line pins the measured figure, not an UNMEASURED gap.
    text = _readme()
    assert "**Extraction repeat-variance:** MEASURED for one skill" in text
    assert "29/33/34" in text
    assert "not stable" in text
    assert "github.com/MrBinnacle/skill-harness/issues/152" in text
    # #153 resolved 2026-08-08 (blind cross-family adjudication over the receipt's
    # adjudicated_rows = 106), so the precision line pins the measured figure, not an
    # UNMEASURED gap. The class split of record is 77/77, NOT 77/78: receipt
    # docs/calibration/vacuity-adjudication-receipt-2026-08-09.json, arm_C_kind.note --
    # "Historical S211 class split of record is 77/77 + 4/20 = 81/97; the published 77/78
    # was an off-by-one denominator, reconciled 2026-08-09." The aggregate agrees: 0.835 is
    # 81/97, not 81/98. The `"77/78" not in text` assertion below is therefore a live guard
    # against reintroducing the retired figure, not a stale pin.
    assert "**Vacuity-flag precision:** MEASURED" in text
    assert "0.972" in text
    # Pinned because it was NOT: 102 stood here unsupported from 63395ba until it was traced
    # to no source of record. Any row count on this line must match the receipt.
    assert "106" in text
    assert "102" not in text
    assert "flag-level only" in text
    assert "kind-precision 0.835" in text
    assert "`not_a_directive` matched 77/77" in text
    assert "`weak_directive` matched 4/20" in text
    assert "77/78" not in text
    assert "github.com/MrBinnacle/skill-harness/issues/153" in text


def test_status_block_facts_unchanged() -> None:
    text = _readme()
    # Derived, not pinned: the banner must track the package version (release
    # gate G3), so a hardcoded literal here would fail on every release bump.
    from skill_harness import __version__

    assert f"Status: v{__version__}" in text
    assert "zero production-skill KEEPs" in text or "Zero production-skill KEEPs" in text
    assert "value-class guard" in text
    assert "append-only-evidence-design" in text
    assert "git-pull-rebase-trap" in text
    assert "CAN'T-TELL-YET" in text
    assert "TRANSFORMATIVE_LIFT" in text


def test_noise_figure_carries_generation_or_receipt() -> None:
    """±17.6% must not stand bare; link the findings receipt or name the arc."""
    text = _readme()
    if "17.6" not in text:
        return
    for m in re.finditer(r"17\.6", text):
        start = max(0, m.start() - 350)
        end = min(len(text), m.end() + 350)
        window = text[start:end]
        assert re.search(
            r"why-naive-skill-benchmarks-mislead|60 trial|Opus-class|MEASURED|2026-07",
            window,
            re.IGNORECASE,
        ), f"17.6 figure at offset {m.start()} lacks generation context or receipt link"


def test_comparison_honest_guidance_and_prior_art_intact() -> None:
    text = _readme()
    assert "if you want the most *featureful* skill benchmarking today" in text.lower() or (
        "most *featureful* skill benchmarking today" in text
    )
    assert "skill-eval-harness" in text
    assert "no first-mover" in text.lower() or "no first-mover" in text
    assert "ai-slop-sentinel-under-ablation" in text
    assert "double-ceiling-structurally-unmeasured" in text
    assert "displaced-enforcement-skill-ablation-blind-spot" in text


def test_skill_audit_names_cost_triple() -> None:
    text = _readme()
    assert re.search(r"standing", text, re.IGNORECASE)
    assert re.search(r"fired", text, re.IGNORECASE)
    assert re.search(r"\baux\b", text, re.IGNORECASE)
    assert "skill audit" in text or "skill-harness skill audit" in text
