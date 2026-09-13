"""Issue #500 — the Path B docstring must state the current facts, not a stale
"never fired" claim.

The original module docstring and ``paired_verdict``'s own docstring both said
Path B "has never fired to date" and that the mapping was "unexercised on live
paired data". That framing is stale as a description of the program: a sized
paired run landed on 2026-09-03 (receipt
``docs/sers/receipts/gitpull-paired-n32-2026-09-03-sized.json``), so live paired
data now exists. Its CANT_TELL_YET verdict was hand-encoded under the #403
hazard-not-met ruling — it came through neither ``paired_verdict`` nor the
matched Gate-2 path — and ``paired_verdict`` still has no production caller
under ``src/``. The docstrings must state both facts instead of the blanket
"never fired" sentence.

These tests assert the text a reader of the verdict layer actually sees (the
module and function docstrings) and that the "no production caller" claim is
mechanically true against the tree. They fail against the pre-#500 wording.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from skill_harness.aggregation import verdict as verdict_mod
from skill_harness.aggregation.verdict import paired_verdict

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
_RECEIPT = "docs/sers/receipts/gitpull-paired-n32-2026-09-03-sized.json"


def _norm(text: str) -> str:
    """Whitespace-normalized lowercased text, so a substring check does not
    depend on where the docstring happens to wrap a line (same convention as
    ``scripts/drift_check.py``'s ``_normalized``)."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _module_doc() -> str:
    return verdict_mod.__doc__ or ""


def _paired_doc() -> str:
    return paired_verdict.__doc__ or ""


def test_neither_docstring_says_path_b_has_never_fired() -> None:
    """AC: neither the module docstring nor ``paired_verdict``'s docstring
    carries the stale 'never fired' sentence. The literal sentence was true
    (``paired_verdict`` has no production caller), but paired with 'unexercised
    on live paired data' it described a program that no longer matches reality:
    live paired data exists, it just did not flow through this mapping."""
    assert "never fired" not in _norm(_module_doc()), (
        "module docstring still claims Path B 'has never fired'"
    )
    assert "never fired" not in _norm(_paired_doc()), (
        "paired_verdict docstring still claims Path B 'has never fired'"
    )


def test_module_docstring_states_paired_verdict_has_no_production_caller() -> None:
    """AC: the module docstring states the current fact — ``paired_verdict``
    has no production caller under ``src/`` — rather than the stale 'never
    fired / unexercised on live paired data' framing."""
    doc = _norm(_module_doc())
    assert "no production caller" in doc, (
        "module docstring does not state that paired_verdict has no production caller"
    )


def test_paired_verdict_docstring_states_it_is_uncalled_and_prospective() -> None:
    """AC: ``paired_verdict``'s own docstring states it has no production caller
    and that the live paired verdict was hand-encoded under #403, not minted
    here — so the mapping is prospective."""
    doc = _norm(_paired_doc())
    assert "no production caller" in doc or "prospective" in doc, (
        "paired_verdict docstring does not state the mapping is uncalled / prospective"
    )
    assert "#403" in _paired_doc(), (
        "paired_verdict docstring does not name the #403 hazard-not-met ruling"
    )


def test_module_docstring_names_the_sized_receipt_and_403_ruling() -> None:
    """AC: the module docstring points a reader at the live paired data and the
    ruling that produced its verdict — the sized receipt under
    ``docs/sers/receipts/`` and the #403 hazard-not-met ruling — instead of
    asserting the mapping is 'unexercised on live paired data'."""
    doc = _module_doc()
    assert "docs/sers/receipts/" in doc, "module docstring does not point at docs/sers/receipts/"
    assert _RECEIPT in doc, "module docstring does not name the sized paired receipt"
    assert "#403" in doc, "module docstring does not name the #403 ruling"


def test_the_cited_receipt_is_a_real_cant_tell_yet_hazard_not_met_record() -> None:
    """The receipt the docstring cites must exist and carry the verdict the
    docstring describes (CANT_TELL_YET, hazard not met). A docstring pointing
    at a missing or differently-valued receipt would be a checkable false
    claim, and this pins the referent."""
    import json

    path = _REPO_ROOT / _RECEIPT
    assert path.is_file(), f"cited receipt {_RECEIPT} is not on disk"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["verdict"] == "CANT_TELL_YET"
    assert payload["value_class"] == "trap-discipline"


def test_module_docstring_retains_the_firing_trigger_text() -> None:
    """AC: the FIRING TRIGGER text is retained — only the stale 'never fired /
    unexercised' framing is replaced, not the trigger that defines when Path B
    would launch."""
    doc = _norm(_module_doc())
    assert "firing trigger" in doc, "module docstring dropped the FIRING TRIGGER label"
    assert "p0 < 1" in doc, "module docstring dropped the p0 < 1 trigger condition"


def test_paired_verdict_has_no_production_caller_under_src() -> None:
    """The docstring's 'no production caller' claim must be mechanically true:
    no Call node under ``src/`` names ``paired_verdict`` outside its own
    definition file. A future wiring would make this fail, which is the prompt
    to update the docstring rather than let it drift again."""
    callers: list[str] = []
    for py in sorted(_SRC_ROOT.rglob("*.py")):
        rel = py.relative_to(_REPO_ROOT).as_posix()
        if rel.endswith("aggregation/verdict.py"):
            continue  # the definition site; its match-arm calls are not calls to paired_verdict
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func
                if (isinstance(name, ast.Name) and name.id == "paired_verdict") or (
                    isinstance(name, ast.Attribute) and name.attr == "paired_verdict"
                ):
                    callers.append(f"{rel}:{node.lineno}")
    assert not callers, (
        "paired_verdict docstring claims no production caller, but calls exist: "
        + ", ".join(callers)
    )


@pytest.mark.parametrize(
    "doc_name,doc", [("module", _norm(_module_doc())), ("paired", _norm(_paired_doc()))]
)
def test_no_docstring_quotes_a_run_count_that_goes_stale(doc_name: str, doc: str) -> None:
    """AC: the docstrings do not state a run count in prose that a later run
    would make stale; they point at the receipts directory instead. A bare
    'fired once' or 'has fired N times' claim is the shape that rots."""
    assert "has fired once" not in doc
    assert "has fired " not in doc  # 'has fired N times' / 'has fired once'
