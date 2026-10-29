"""The workflow audit's required-check boundary matches ci.yml's `all-green` job (#825)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/assurance/workflows-audit.md"
CI = ROOT / ".github/workflows/ci.yml"
ORIGINAL_SENTENCE = (
    "The new `dependency-audit` job is intentionally absent from\n`all-green`'s `needs` list"
)


def _all_green_needs() -> set[str]:
    text = CI.read_text(encoding="utf-8")
    match = re.search(r"(?m)^  all-green:\n(?:    .*\n)*?    needs: \[([^\]]*)\]", text)
    assert match, "ci.yml has no all-green job with an inline needs list"
    return {name.strip() for name in match.group(1).split(",")}


def _addendum() -> str:
    text = AUDIT.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^Addendum \(added \d{4}-\d{2}-\d{2}, #817\).*?(?=\n\n)", text)
    assert match, "no dated #817 addendum in the required-check boundary"
    return match.group(0)


def test_original_sentence_is_kept_as_written() -> None:
    assert ORIGINAL_SENTENCE in AUDIT.read_text(encoding="utf-8")


def test_addendum_matches_all_green_membership() -> None:
    needs = _all_green_needs()
    assert "dependency-audit" in needs
    assert "linkcheck" not in needs
    addendum = " ".join(_addendum().split())
    assert "`dependency-audit` is in `all-green`'s `needs`" in addendum
    assert "`linkcheck` stays out" in addendum
    assert "sentence above" in addendum
    assert "blocks the merge" not in addendum
    assert "not a required status check" in addendum
