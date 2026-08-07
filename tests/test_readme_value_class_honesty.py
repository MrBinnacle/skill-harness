"""README honesty lock for the value-class guard reclassification (#139).

Pins outward-facing text only: the status block must keep the dated pre-guard
CUT (subsumed) results, state the post-guard CAN'T-TELL-YET reclassification and
its reason, and not defend a CUT the code no longer returns. Also locks the
three-case reproduction the ticket requires (two portfolio skills + positive
control).
"""

from __future__ import annotations

import re
from pathlib import Path

from skill_harness.aggregation.value_class_registry import value_class_for
from skill_harness.aggregation.verdict import KeepCutVerdict, ValueClass, screen_verdict

_README = Path(__file__).resolve().parents[1] / "README.md"


def _readme() -> str:
    return _README.read_text(encoding="utf-8")


def test_three_case_reproduction_matches_ticket() -> None:
    """Ticket reproduction at p0=1.00: two portfolio skills CANT_TELL_YET; TL control CUT."""
    p0 = 1.00
    cases = [
        ("append-only-evidence-design", KeepCutVerdict.CANT_TELL_YET),
        ("git-pull-rebase-trap", KeepCutVerdict.CANT_TELL_YET),
    ]
    for skill_name, expected in cases:
        vc = value_class_for(skill_name)
        assert vc is not None and vc is not ValueClass.TRANSFORMATIVE_LIFT
        assert screen_verdict(p0, value_class=vc).verdict is expected

    control = screen_verdict(p0, value_class=ValueClass.TRANSFORMATIVE_LIFT)
    assert control.verdict is KeepCutVerdict.CUT
    assert control.cut_sub_reason is not None
    assert control.cut_sub_reason.value == "subsumed"


def test_readme_retains_dated_cut_subsumed_as_historical() -> None:
    text = _readme()
    assert "append-only-evidence-design" in text
    assert "git-pull-rebase-trap" in text
    assert "CUT (subsumed)" in text
    # Historical, not retracted: pre-guard / at the time / returned.
    assert re.search(
        r"both returned \*\*CUT \(subsumed\)\*\*.*(pre-guard|at the time|under the pre-)",
        text,
        re.DOTALL | re.IGNORECASE,
    )


def test_readme_states_reclassification_to_cant_tell_yet() -> None:
    text = _readme()
    assert re.search(r"value-class guard", text, re.IGNORECASE)
    assert re.search(
        r"reclassif\w+.*CAN'?T-TELL-YET|CAN'?T-TELL-YET.*reclassif",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    assert re.search(
        r"TRANSFORMATIVE_LIFT|transformative-lift",
        text,
    )
    assert re.search(
        r"above-bar|above the bar|p0.*only for",
        text,
        re.IGNORECASE,
    )


def test_unqualified_cut_defence_is_gone() -> None:
    text = _readme()
    assert "That is the tool doing its job, not a failure" not in text


def test_every_cut_subsumed_sits_beside_reclassification_note() -> None:
    text = _readme()
    # Window around each occurrence must name the reclassification.
    for m in re.finditer(r"CUT \(subsumed\)", text):
        start = max(0, m.start() - 400)
        end = min(len(text), m.end() + 400)
        window = text[start:end]
        assert re.search(r"reclassif|value-class guard|pre-guard", window, re.IGNORECASE), (
            f"CUT (subsumed) at offset {m.start()} lacks a nearby reclassification note"
        )


def test_keep_cut_cant_tell_product_claim_is_value_class_qualified() -> None:
    """Bare present-tense KEEP/CUT/CAN'T-TELL-YET product claims name the guard."""
    text = _readme()
    # Status-block product sentence: three verdicts.
    m = re.search(
        r"one of three verdicts:.*?(?:KEEP|CUT|CAN'T-TELL-YET).{0,800}",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    assert m is not None, "expected the three-verdicts product claim in README"
    window = m.group(0)
    assert re.search(r"value.class|value_class|TRANSFORMATIVE_LIFT|transformative-lift", window), (
        "three-verdicts claim must be qualified by the value-class guard"
    )
