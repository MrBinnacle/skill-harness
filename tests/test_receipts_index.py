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


def _entry_blocks(index_text: str) -> dict[str, str]:
    """Split the index into per-entry blocks keyed by the paths each mentions.

    Entries are `### `-headed. Splitting bounds every entry exactly, so a
    missing line cannot be satisfied by a neighbour. A fixed character window
    cannot do this: entries average ~625 b and the index is dense, so any
    window wide enough to hold one entry also reaches the next.

    The split accepts `##` OR `###` deliberately. Splitting on `###` alone lets
    the LAST entry in the document absorb every following `##` section - here
    the cost-beside-evidence join surface, which carries its own claims and
    refuses lines and would satisfy the contract for an entry that had lost
    them.
    """
    blocks: dict[str, str] = {}
    for chunk in re.split(r"(?m)^#{2,3} ", index_text)[1:]:
        for rel in re.findall(
            r"docs/(?:case-studies|findings|observations|assurance|ratifications"
            r"|sers/receipts)/[A-Za-z0-9._-]+\.(?:md|json)",
            chunk,
        ):
            blocks.setdefault(rel, chunk)
    return blocks


def _missing_receipts(index_text: str) -> list[str]:
    """Receipt paths present on disk but absent from the index text."""
    return [rel for path in _receipt_paths() if (rel := _posix_rel(path)) not in index_text]


def _contract_failures(index_text: str) -> list[str]:
    """Indexed entries that do not carry BOTH a claims and a refuses line."""
    blocks = _entry_blocks(index_text)
    failures: list[str] = []
    for path in _receipt_paths():
        rel = _posix_rel(path)
        block = blocks.get(rel)
        if block is None:
            failures.append(f"{rel}: no `### `-headed entry block found")
            continue
        if _CLAIMS_RE.search(block) is None:
            failures.append(f"{rel}: missing **Claims:** line in its entry")
        if _REFUSES_RE.search(block) is None:
            failures.append(f"{rel}: missing **Refuses:** line in its entry")
    return failures


def test_receipts_index_exists() -> None:
    assert _INDEX.is_file(), "docs/receipts-index.md is missing"


def test_every_receipt_file_is_indexed() -> None:
    """Completeness: every on-disk receipt path string appears in the index."""
    missing = _missing_receipts(_INDEX.read_text(encoding="utf-8"))
    assert not missing, "receipt file(s) not listed in docs/receipts-index.md:\n" + "\n".join(
        f"  - {m}" for m in missing
    )


def test_index_entries_carry_claims_and_refuses() -> None:
    """Each receipt path's entry block must state claims and refuses-to-claim."""
    failures = _contract_failures(_INDEX.read_text(encoding="utf-8"))
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


def test_completeness_detector_fires_on_omitted_entry() -> None:
    """Red-phase guard: a deliberately omitted path must be detected.

    Calls the SAME helper the real assertion calls. An earlier version of this
    guard re-implemented the comprehension inline, so it proved only that
    ``in`` works and would have stayed green if the real check were weakened.
    """
    real = _INDEX.read_text(encoding="utf-8")
    paths = _receipt_paths()
    assert paths, "need at least one receipt file to plant an omission"
    target = _posix_rel(paths[0])
    assert target in real, f"precondition: {target} must be indexed"
    assert not _missing_receipts(real), "precondition: index is complete before poisoning"

    poisoned = real.replace(target, "docs/RECEIPT_DELIBERATELY_OMITTED.md")
    assert target in _missing_receipts(poisoned), (
        "completeness check failed to notice the deliberately omitted entry"
    )


@pytest.mark.parametrize("line_kind", ["Claims", "Refuses to claim"])
def test_contract_detector_fires_on_stripped_line(line_kind: str) -> None:
    """Red-phase guard for the per-entry contract, one entry at a time.

    Strips a single entry's own ``**Claims:**`` / ``**Refuses to claim:**``
    line and requires the contract check to name THAT entry. Run over every
    indexed receipt, because the defect this replaces was invisible for all of
    them: a fixed 1200-char window reached into the neighbouring entry, whose
    lines satisfied the search, so 22/22 stripped lines went undetected.
    """
    real = _INDEX.read_text(encoding="utf-8")
    assert not _contract_failures(real), "precondition: index satisfies the contract"

    blocks = _entry_blocks(real)
    checked = 0
    for path in _receipt_paths():
        rel = _posix_rel(path)
        block = blocks[rel]
        marker = re.search(rf"(?im)^[ \t]*-[ \t]*\*\*{re.escape(line_kind)}:?\*\*.*$", block)
        assert marker is not None, f"{rel}: no {line_kind} line to strip"
        poisoned_block = block[: marker.start()] + block[marker.end() :]
        poisoned = real.replace(block, poisoned_block, 1)
        assert poisoned != real, f"{rel}: poisoning did not change the index text"

        failures = _contract_failures(poisoned)
        assert any(f.startswith(f"{rel}: missing") for f in failures), (
            f"{rel}: stripping its {line_kind} line went UNDETECTED - "
            f"the contract check is vacuous for this entry"
        )
        checked += 1

    assert checked >= 20, f"expected the full receipt set, only checked {checked}"


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
