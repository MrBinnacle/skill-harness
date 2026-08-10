"""Receipts-index completeness (#184).

Every receipt file under the named directories must appear in
``docs/receipts-index.md``, and every indexed entry must carry both a
claims line and a refuses-to-claim line. A new receipt cannot land
unindexed without failing CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_INDEX = _REPO_ROOT / "docs" / "receipts-index.md"

# (kind_label, relative_dir, glob) — receipt files only (not ledger READMEs /
# templates). SERS instances are JSON; everything else is Markdown prose.
_RECEIPT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("case-studies", "docs/case-studies", "*.md"),
    ("findings", "docs/findings", "*.md"),
    ("observations", "docs/observations", "OBS-*.md"),
    ("assurance", "docs/assurance", "*.md"),
    ("ratifications", "docs/ratifications", "RAT-*.md"),
    ("sers", "docs/sers/receipts", "*.json"),
)

_CLAIMS_RE = re.compile(r"(?i)\*\*claims:\*\*")
_REFUSES_RE = re.compile(r"(?i)\*\*refuses(?: to claim)?:\*\*")


def _receipt_paths() -> list[Path]:
    paths: list[Path] = []
    for _kind, rel_dir, pattern in _RECEIPT_SPECS:
        directory = _REPO_ROOT / rel_dir
        assert directory.is_dir(), f"missing receipt directory {rel_dir}"
        paths.extend(sorted(directory.glob(pattern)))
    return paths


def _posix_rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def test_receipts_index_exists() -> None:
    assert _INDEX.is_file(), "docs/receipts-index.md is missing"


def test_every_receipt_file_is_indexed() -> None:
    """Completeness: every on-disk receipt path string appears in the index."""
    index_text = _INDEX.read_text(encoding="utf-8")
    missing = [rel for path in _receipt_paths() if (rel := _posix_rel(path)) not in index_text]
    assert not missing, "receipt file(s) not listed in docs/receipts-index.md:\n" + "\n".join(
        f"  - {m}" for m in missing
    )


def test_index_entries_carry_claims_and_refuses() -> None:
    """Each receipt path's entry block must state claims and refuses-to-claim."""
    index_text = _INDEX.read_text(encoding="utf-8")
    # Split on headings that introduce path-bearing entries; also accept bare
    # path mentions followed by the two required lines within a short window.
    failures: list[str] = []
    for path in _receipt_paths():
        rel = _posix_rel(path)
        pos = index_text.find(rel)
        if pos < 0:
            failures.append(f"{rel}: path absent from index")
            continue
        window = index_text[pos : pos + 1200]
        if _CLAIMS_RE.search(window) is None:
            failures.append(f"{rel}: missing **Claims:** line near entry")
        if _REFUSES_RE.search(window) is None:
            failures.append(f"{rel}: missing **Refuses:** line near entry")
    assert not failures, "index entry contract failures:\n" + "\n".join(
        f"  - {f}" for f in failures
    )


def test_sers_entries_state_verdict_and_sub_reason() -> None:
    """SERS instances must surface verdict + sub-reason schema vocabulary."""
    index_text = _INDEX.read_text(encoding="utf-8")
    sers_dir = _REPO_ROOT / "docs" / "sers" / "receipts"
    for path in sorted(sers_dir.glob("*.json")):
        rel = _posix_rel(path)
        pos = index_text.find(rel)
        assert pos >= 0, f"{rel} missing from index"
        window = index_text[pos : pos + 1200]
        assert re.search(r"\bverdict\b", window, re.IGNORECASE), (
            f"{rel}: SERS entry must state verdict"
        )
        assert re.search(
            r"\b(cut_sub_reason|unmeasured_sub_reason|sub-reason)\b",
            window,
            re.IGNORECASE,
        ), f"{rel}: SERS entry must state sub-reason field(s)"


def test_skill_audit_extraction_join_surface_is_indexed() -> None:
    """The cost-beside-evidence join surface is not a file; pin it by name."""
    index_text = _INDEX.read_text(encoding="utf-8")
    assert "skill audit --extraction" in index_text
    # Find the join-surface section and require claims/refuses nearby.
    pos = index_text.find("skill audit --extraction")
    window = index_text[pos : pos + 1500]
    assert _CLAIMS_RE.search(window), "skill audit --extraction missing **Claims:**"
    assert _REFUSES_RE.search(window), "skill audit --extraction missing **Refuses:**"


def test_completeness_detector_fires_on_omitted_entry(tmp_path: Path) -> None:
    """Red-phase guard: a deliberately omitted path must be detected.

    This is the meta-check that the completeness assertion is not vacuous —
    it must fail when a known receipt path is stripped from the index text.
    """
    real = _INDEX.read_text(encoding="utf-8")
    paths = _receipt_paths()
    assert paths, "need at least one receipt file to plant an omission"
    target = _posix_rel(paths[0])
    assert target in real, f"precondition: {target} must be indexed"
    poisoned = real.replace(target, "docs/RECEIPT_DELIBERATELY_OMITTED.md")
    assert target not in poisoned
    missing = [rel for path in paths if (rel := _posix_rel(path)) not in poisoned]
    assert target in missing, "detector failed to notice the deliberately omitted entry"


@pytest.mark.parametrize(
    ("kind", "rel_dir", "pattern"),
    _RECEIPT_SPECS,
    ids=[spec[0] for spec in _RECEIPT_SPECS],
)
def test_receipt_kind_section_present(kind: str, rel_dir: str, pattern: str) -> None:
    """Index groups by receipt kind; each kind has a section heading."""
    del rel_dir, pattern  # discovery only; heading is by kind label
    index_text = _INDEX.read_text(encoding="utf-8")
    # Accept several human headings that name the kind.
    markers = {
        "case-studies": r"case stud",
        "findings": r"finding",
        "observations": r"observation",
        "assurance": r"assurance",
        "ratifications": r"ratification",
        "sers": r"SERS",
    }
    assert re.search(markers[kind], index_text, re.IGNORECASE), (
        f"docs/receipts-index.md missing a section for kind {kind!r}"
    )
