"""Receipts-index completeness (#184) and its population integrity (#453).

Every receipt file under the named directories must appear in
``docs/receipts-index.md``, and every indexed entry must carry both a
claims line and a refuses-to-claim line. A new receipt cannot land
unindexed without failing CI.

Population integrity (#453)
---------------------------
This module is enumeration-driven: ``_receipt_paths`` globs six directories and
submits whatever it finds to the detectors below. It can therefore execute
perfectly over the wrong universe, and did. During #444 a section 7 mutation
index landed in ``docs/assurance/`` unregistered, which broke five tests -- and
two of the five were this module's own negative controls. Those two still ran
and still reported, and they established nothing, because the input they exist
to be exposed to was never enumerated::

    negative control present   !=   negative control exercised

So the control now states the population it analysed and checks it against the
population the index declares, in BOTH directions. The completeness detector
already checks on-disk against the index; nothing checked the other way, so an
index entry naming a receipt that no longer exists on disk would have gone
unnoticed while every test still passed over a smaller universe.

The two sides share one kind predicate, ``_matches_a_receipt_spec``, and that is
what keeps the check from being circular. ``_RECEIPT_SPECS`` defines the KIND --
which directories, which filename shape. The declaration is which files of that
kind the index says exist; the enumeration is which files of that kind are on
disk. Both are filtered by the same predicate and can still disagree on
membership, which is the disagreement worth detecting. Without the filter the
index's prose mentions of ``docs/ASSURANCE.md``, ``docs/INVARIANTS.md``,
``docs/ratifications/README.md`` and the three
``docs/sers/receipts/superseded/`` files would read as declared receipts the
enumeration had missed. Each is excluded by the predicate, and by a different
clause of it: the two top-level docs sit in no registered directory, the README
sits in one but does not match its ``RAT-*.md`` shape, and the superseded
receipts sit one level deeper than the deliberately non-recursive glob reaches.

When the two sets disagree the control reports ``UNINTERPRETABLE``, not a pass
and not an ordinary failure. A detector saying "no defect found in the cases I
received" may not become "no defect exists" while the universe it received is
unestablished.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import pytest

from skill_harness.population import (
    PopulationRecord,
    PopulationVerdict,
    build_population_record,
    interpret,
    posix_relative_ids,
    require_valid_population,
)

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


def _matches_a_receipt_spec(rel: str) -> bool:
    """Is this repo-relative path a receipt of one of the registered kinds?

    The one kind predicate both sides of the population check use: the
    enumeration globs with it, and the declaration is filtered by it. Directory
    membership is direct, never recursive, because the specs glob one level and
    ``docs/sers/receipts/superseded/`` is deliberately outside the population.
    """
    for _kind, rel_dir, pattern in _RECEIPT_SPECS:
        prefix = f"{rel_dir}/"
        if not rel.startswith(prefix):
            continue
        name = rel[len(prefix) :]
        if "/" in name:
            continue
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _declared_receipt_ids(index_text: str) -> tuple[str, ...]:
    """The receipt paths ``docs/receipts-index.md`` says exist.

    Matches any ``docs/...`` path the index names, then keeps the ones that are
    receipts of a registered kind. Matching broadly and filtering afterwards is
    deliberate: a narrow regex that only matched the registered directories
    would silently drop an index entry pointing somewhere unexpected, which is
    one of the disagreements this population check exists to surface.
    """
    named = set(re.findall(r"docs/[A-Za-z0-9._/-]+\.(?:md|json)", index_text))
    return tuple(sorted(rel for rel in named if _matches_a_receipt_spec(rel)))


def _population(index_text: str) -> PopulationRecord:
    """What this control analysed, against what the index declares."""
    return build_population_record(
        analyzed=posix_relative_ids(_receipt_paths(), _REPO_ROOT),
        declared=_declared_receipt_ids(index_text),
    )


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


def test_the_control_records_the_population_it_analyzed() -> None:
    """#453: cardinality and stable identity of the cases actually submitted.

    Asserts the shape of the record and a floor on its size, never a literal
    count. A test that pinned today's 42 would fail on the next receipt that
    lands, so the only thing it could enforce is its own staleness; the floor
    catches the failure that matters here, which is a glob that silently stopped
    matching and left the detectors running over a shrunken universe.
    """
    record = _population(_INDEX.read_text(encoding="utf-8"))
    assert record.population_count == len(record.population_ids)
    assert record.population_count >= 20, (
        f"only {record.population_count} receipt(s) reached the detectors; the "
        "enumeration has shrunk and every verdict below is over a smaller "
        "universe than the one this control is written for"
    )
    assert len(record.population_digest) == 64
    assert all(_matches_a_receipt_spec(rel) for rel in record.population_ids)


def test_the_analyzed_population_is_the_declared_population() -> None:
    """Fail closed: the index and the disk must name the same receipts, both ways.

    The completeness detector already checks on-disk against the index. This
    adds the direction nothing checked -- an index entry naming a receipt that
    is no longer on disk -- and reports either disagreement as a population
    failure rather than as an ordinary content failure.
    """
    record = _population(_INDEX.read_text(encoding="utf-8"))
    require_valid_population(record, "the receipts-index control")


def test_a_valid_population_and_a_clean_index_is_reported_as_a_pass() -> None:
    """The verdict layer, exercised on the real corpus rather than only in unit tests."""
    index_text = _INDEX.read_text(encoding="utf-8")
    record = _population(index_text)
    assert interpret(record, _contract_failures(index_text)) is PopulationVerdict.PASS


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
    # #453: gate on the population BEFORE the content precondition below. When
    # an unregistered receipt lands, both fail -- but only this one says the
    # control established nothing, which is the finding. The content
    # precondition alone reads as "the index is broken", and that reading is
    # what let two negative controls report while proving nothing during #444.
    require_valid_population(_population(real), "the omitted-entry negative control")
    paths = _receipt_paths()
    assert paths, "need at least one receipt file to plant an omission"
    target = _posix_rel(paths[0])
    assert target in real, f"precondition: {target} must be indexed"
    assert not _missing_receipts(real), "precondition: index is complete before poisoning"

    poisoned = real.replace(target, "docs/RECEIPT_DELIBERATELY_OMITTED.md")
    assert target in _missing_receipts(poisoned), (
        "completeness check failed to notice the deliberately omitted entry"
    )


def test_a_declared_receipt_the_glob_cannot_reach_fails_the_control_not_the_detector() -> None:
    """#453's required negative control, against this control's own enumeration.

    ::

        declared population:   the real 42, plus one the enumeration cannot reach
        enumerated population: the real 42
        detectors over those:  pass correctly, because the phantom is not on disk

    Expected result: the CONTROL fails. Both detectors iterate ``_receipt_paths``
    and therefore never look at the phantom, so a run where this test passes
    means the population check is decorative and a receipt could vanish from
    disk while the index still promised it.

    Distinct from ``test_completeness_detector_fires_on_omitted_entry``, which
    poisons the index and requires the DETECTOR to fire. This one leaves the
    detectors correct and requires the CONTROL to refuse.
    """
    real = _INDEX.read_text(encoding="utf-8")
    phantom = "docs/findings/F-453-NOT-ON-DISK.md"
    assert _matches_a_receipt_spec(phantom), "the phantom must be a receipt of a registered kind"
    assert not (_REPO_ROOT / phantom).exists(), "the phantom must not be on disk"

    poisoned = f"{real}\n- see `{phantom}` for the rest.\n"

    assert not _missing_receipts(poisoned), (
        "precondition: the completeness detector must still pass over what it "
        "received, so the only thing left to fail is the population"
    )
    assert not _contract_failures(poisoned), (
        "precondition: the entry-contract detector must still pass over what it received"
    )

    record = build_population_record(
        analyzed=posix_relative_ids(_receipt_paths(), _REPO_ROOT),
        declared=_declared_receipt_ids(poisoned),
    )
    assert record.missing == (phantom,)
    assert interpret(record, _contract_failures(poisoned)) is PopulationVerdict.UNINTERPRETABLE
    with pytest.raises(AssertionError, match="UNINTERPRETABLE"):
        require_valid_population(record, "the receipts-index control")


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
    # #453: the population gates the precondition, for the reason given on the
    # omitted-entry control above.
    require_valid_population(_population(real), "the stripped-line negative control")
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
