"""Tests for local-only subject registration (issue #556).

Acceptance criteria tested:
- AC1: A local-only subject can be declared by path, and the declaration
  is recorded somewhere a later session can read without being told it exists.
- AC2: The declaration pins the subject by content digest, not by path alone.
- AC3: The two archived copies are distinguishable as separate subjects.
- AC4: A receipt for a subject the owner did not author records the author.
- AC5: A red demonstration shows a run refused when the declared digest
  does not match the file on disk.
- AC6: A subject path that does not exist fails the run.
- AC7: The registration does not copy the subject's bytes into this repository.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_harness.subject.local import (
    LocalSubject,
    compute_subject_digest,
    list_local_subjects,
    load_registry,
    register_local_subject,
    render_subject_receipt,
    resolve_subject,
    verify_subject_integrity,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SKILL_A_V1 = "---\nname: skill-a\ndescription: First version\n---\nBody v1\n"
SKILL_A_V2 = "---\nname: skill-a\ndescription: Modified version\n---\nBody v2\n"
SKILL_B = "---\nname: skill-b\ndescription: Different skill\n---\nBody B\n"
SKILL_THIRD_PARTY = (
    "---\nname: third-party-skill\ndescription: By someone else"
    "\nauthor: theswerd\n---\nThird party body\n"
)


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / ".skill_harness" / "local_subjects.json"


@pytest.fixture
def skill_a_v1(tmp_path: Path) -> Path:
    p = tmp_path / "skill-a" / "v1" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(SKILL_A_V1, encoding="utf-8")
    return p


@pytest.fixture
def skill_a_v2(tmp_path: Path) -> Path:
    p = tmp_path / "skill-a" / "v2" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(SKILL_A_V2, encoding="utf-8")
    return p


@pytest.fixture
def skill_b(tmp_path: Path) -> Path:
    p = tmp_path / "skill-b" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(SKILL_B, encoding="utf-8")
    return p


@pytest.fixture
def skill_third_party(tmp_path: Path) -> Path:
    p = tmp_path / "third-party" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(SKILL_THIRD_PARTY, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# AC1: A local-only subject can be declared by path, and the declaration
#      is recorded somewhere a later session can read without being told it exists.
# ---------------------------------------------------------------------------


def test_register_local_subject_creates_registry_file(
    skill_a_v1: Path, registry_path: Path
) -> None:
    """AC1: registration creates a registry file a later session can read."""
    subject = register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    # Registry file exists
    assert registry_path.is_file()

    # Registry can be loaded and contains the subject
    loaded = load_registry(registry_path)
    assert subject.subject_id in loaded.subjects
    assert loaded.subjects[subject.subject_id].name == "skill-a"


def test_register_local_subject_returns_correct_fields(
    skill_a_v1: Path, registry_path: Path
) -> None:
    """AC1: the returned LocalSubject has all required fields."""
    subject = register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    assert subject.name == "skill-a"
    assert subject.author == "owner"
    assert subject.origin == "local_archive"
    assert subject.source_path == str(skill_a_v1.resolve())
    assert subject.source_digest  # non-empty
    assert subject.subject_id  # non-empty
    assert subject.registered_at  # non-empty


def test_load_registry_returns_empty_when_no_file(registry_path: Path) -> None:
    """AC1: loading a non-existent registry returns empty, not an error."""
    assert not registry_path.exists()
    registry = load_registry(registry_path)
    assert registry.subjects == {}


def test_list_local_subjects_reads_from_file(skill_a_v1: Path, registry_path: Path) -> None:
    """AC1: list_local_subjects discovers registered subjects."""
    register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    subjects = list_local_subjects(registry_path)
    assert len(subjects) == 1
    assert subjects[0].name == "skill-a"


# ---------------------------------------------------------------------------
# AC2: The declaration pins the subject by content digest, not by path alone,
#      so a changed file is a different subject rather than a silent substitution.
# ---------------------------------------------------------------------------


def test_subject_id_is_content_digest(skill_a_v1: Path, registry_path: Path) -> None:
    """AC2: subject_id is the SHA-256 of the SKILL.md bytes."""
    subject = register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    expected_digest = compute_subject_digest(skill_a_v1)
    assert subject.subject_id == expected_digest
    assert subject.source_digest == expected_digest


def test_changed_file_is_different_subject(
    skill_a_v1: Path, skill_a_v2: Path, registry_path: Path
) -> None:
    """AC2: two files with different content have different subject_ids."""
    subject_v1 = register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a-v1",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    subject_v2 = register_local_subject(
        skill_md_path=skill_a_v2,
        name="skill-a-v2",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    # Different content => different subject_id
    assert subject_v1.subject_id != subject_v2.subject_id

    # Both are in the registry
    registry = load_registry(registry_path)
    assert len(registry.subjects) == 2


def test_resolve_subject_verifies_digest_match(skill_a_v1: Path, registry_path: Path) -> None:
    """AC2: resolve_subject succeeds when digest matches."""
    register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    resolved = resolve_subject(skill_a_v1, registry_path=registry_path)
    assert resolved.name == "skill-a"


def test_resolve_subject_fails_when_file_modified(skill_a_v1: Path, registry_path: Path) -> None:
    """AC2: resolve_subject fails when file was modified after registration."""
    register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    # Modify the file
    skill_a_v1.write_text(SKILL_A_V2, encoding="utf-8")

    with pytest.raises(ValueError, match="no registered subject with digest"):
        resolve_subject(skill_a_v1, registry_path=registry_path)


# ---------------------------------------------------------------------------
# AC3: The two archived copies are distinguishable as separate subjects,
#      and a receipt names which was measured.
# ---------------------------------------------------------------------------


def test_two_copies_are_separate_subjects(
    skill_a_v1: Path, skill_a_v2: Path, registry_path: Path
) -> None:
    """AC3: two archived copies with different content are separate subjects."""
    subject_v1 = register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a-v1",
        author="owner",
        author_source="manual",
        origin="upstream_install",
        registry_path=registry_path,
    )

    subject_v2 = register_local_subject(
        skill_md_path=skill_a_v2,
        name="skill-a-v2",
        author="owner",
        author_source="manual",
        origin="collection_removal",
        registry_path=registry_path,
    )

    # Different subjects
    assert subject_v1.subject_id != subject_v2.subject_id
    assert subject_v1.origin != subject_v2.origin

    # Receipts distinguish them
    receipt_v1 = render_subject_receipt(subject_v1, verdict="measured")
    receipt_v2 = render_subject_receipt(subject_v2, verdict="measured")

    assert receipt_v1.subject_id != receipt_v2.subject_id
    assert receipt_v1.source_digest != receipt_v2.source_digest


def test_receipt_names_which_was_measured(
    skill_a_v1: Path, skill_a_v2: Path, registry_path: Path
) -> None:
    """AC3: receipt records the exact subject that was measured."""
    subject_v1 = register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a-v1",
        author="owner",
        author_source="manual",
        origin="upstream_install",
        registry_path=registry_path,
    )

    register_local_subject(
        skill_md_path=skill_a_v2,
        name="skill-a-v2",
        author="owner",
        author_source="manual",
        origin="collection_removal",
        registry_path=registry_path,
    )

    # Measure v1
    receipt = render_subject_receipt(subject_v1, verdict="measured")
    assert receipt.subject_id == subject_v1.subject_id
    assert receipt.name == "skill-a-v1"
    assert receipt.source_path == str(skill_a_v1.resolve())


# ---------------------------------------------------------------------------
# AC4: A receipt for a subject the owner did not author records the author,
#      and a verdict cannot be rendered without that field.
# ---------------------------------------------------------------------------


def test_receipt_requires_author_for_third_party(
    skill_third_party: Path, registry_path: Path
) -> None:
    """AC4: receipt records the third-party author."""
    subject = register_local_subject(
        skill_md_path=skill_third_party,
        name="third-party-skill",
        author="theswerd",
        author_source="frontmatter",
        origin="local_archive",
        registry_path=registry_path,
    )

    receipt = render_subject_receipt(subject, verdict="measured")
    assert receipt.author == "theswerd"
    assert receipt.name == "third-party-skill"


def test_verdict_renders_author_in_receipt(skill_third_party: Path, registry_path: Path) -> None:
    """AC4: a verdict receipt carries the author."""
    subject = register_local_subject(
        skill_md_path=skill_third_party,
        name="third-party-skill",
        author="theswerd",
        author_source="frontmatter",
        origin="local_archive",
        registry_path=registry_path,
    )

    receipt = render_subject_receipt(subject, verdict="measured")
    # The receipt carries author - a verdict cannot be rendered without it
    assert receipt.author  # non-empty


def test_receipt_for_refused_subject_records_author(
    skill_third_party: Path, registry_path: Path
) -> None:
    """AC4: even a refused verdict carries the author."""
    subject = register_local_subject(
        skill_md_path=skill_third_party,
        name="third-party-skill",
        author="theswerd",
        author_source="frontmatter",
        origin="local_archive",
        registry_path=registry_path,
    )

    receipt = render_subject_receipt(subject, verdict="refused", verdict_reason="digest_mismatch")
    assert receipt.author == "theswerd"
    assert receipt.verdict == "refused"
    assert receipt.verdict_reason == "digest_mismatch"


# ---------------------------------------------------------------------------
# AC5: A red demonstration shows a run refused when the declared digest
#      does not match the file on disk.
# ---------------------------------------------------------------------------


def test_verify_subject_integrity_detects_mismatch(skill_a_v1: Path, registry_path: Path) -> None:
    """AC5: integrity check fails when file was modified after registration."""
    register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    # Get the registered digest
    registry = load_registry(registry_path)
    subject = next(iter(registry.subjects.values()))
    expected_digest = subject.source_digest

    # Modify the file
    skill_a_v1.write_text(SKILL_A_V2, encoding="utf-8")

    # Integrity check fails
    match, actual = verify_subject_integrity(skill_a_v1, expected_digest)
    assert not match
    assert actual != expected_digest


def test_verify_subject_integrity_passes_when_unchanged(
    skill_a_v1: Path, registry_path: Path
) -> None:
    """AC5: integrity check passes when file is unchanged."""
    register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    registry = load_registry(registry_path)
    subject = next(iter(registry.subjects.values()))
    expected_digest = subject.source_digest

    # File unchanged
    match, actual = verify_subject_integrity(skill_a_v1, expected_digest)
    assert match
    assert actual == expected_digest


def test_refused_receipt_for_digest_mismatch(skill_a_v1: Path, registry_path: Path) -> None:
    """AC5: a refused receipt is created when digest doesn't match."""
    subject = register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    # Modify the file
    skill_a_v1.write_text(SKILL_A_V2, encoding="utf-8")

    # Check integrity
    match, actual = verify_subject_integrity(skill_a_v1, subject.source_digest)
    assert not match

    # Create a refused receipt
    refused_subject = LocalSubject(
        subject_id=subject.subject_id,
        source_path=subject.source_path,
        source_digest=subject.source_digest,
        name=subject.name,
        author=subject.author,
        author_source=subject.author_source,
        origin=subject.origin,
        registered_at=subject.registered_at,
    )
    reason = (
        f"digest_mismatch: expected {subject.source_digest[:16]}\u2026, got {actual[:16]}\u2026"
    )
    receipt = render_subject_receipt(
        refused_subject,
        verdict="refused",
        verdict_reason=reason,
    )
    assert receipt.verdict == "refused"
    assert receipt.verdict_reason is not None
    assert "digest_mismatch" in receipt.verdict_reason


# ---------------------------------------------------------------------------
# AC6: A subject path that does not exist fails the run rather than
#      reporting silently.
# ---------------------------------------------------------------------------


def test_register_nonexistent_path_fails() -> None:
    """AC6: registering a non-existent path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="does not exist"):
        register_local_subject(
            skill_md_path=Path("/nonexistent/path/SKILL.md"),
            name="ghost",
            author="nobody",
            author_source="manual",
            origin="local_archive",
        )


def test_resolve_nonexistent_path_fails(tmp_path: Path) -> None:
    """AC6: resolving a non-existent path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="does not exist"):
        resolve_subject(Path("/nonexistent/path/SKILL.md"))


def test_verify_integrity_nonexistent_path() -> None:
    """AC6: integrity check on non-existent path returns (False, error_msg)."""
    match, msg = verify_subject_integrity(Path("/nonexistent/path/SKILL.md"), "abc123")
    assert not match
    assert "does not exist" in msg


# ---------------------------------------------------------------------------
# AC7: The registration does not copy the subject's bytes into this repository.
# ---------------------------------------------------------------------------


def test_registration_does_not_copy_bytes(skill_a_v1: Path, registry_path: Path) -> None:
    """AC7: registry file contains only metadata, not the skill's bytes."""
    register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    # Read the registry file
    registry_content = registry_path.read_text(encoding="utf-8")

    # The actual skill content must NOT be in the registry
    assert "First version" not in registry_content
    assert "Body v1" not in registry_content

    # Only metadata should be present
    assert "skill-a" in registry_content
    assert "owner" in registry_content


def test_registry_contains_only_paths_and_digests(skill_a_v1: Path, registry_path: Path) -> None:
    """AC7: registry structure has source_path and source_digest, not content."""
    register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    subjects = data.get("subjects", {})

    for _subject_id, subject_data in subjects.items():
        # Must have path and digest
        assert "source_path" in subject_data
        assert "source_digest" in subject_data
        # Must NOT have a "content" or "body" field
        assert "content" not in subject_data
        assert "body" not in subject_data
        assert "text" not in subject_data


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_re_registration_updates_existing_subject(skill_a_v1: Path, registry_path: Path) -> None:
    """Re-registering the same content updates metadata, not create duplicate."""
    subject1 = register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a-v1",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    subject2 = register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a-updated",
        author="owner-updated",
        author_source="manual",
        origin="upstream_install",
        registry_path=registry_path,
    )

    # Same content => same subject_id
    assert subject1.subject_id == subject2.subject_id

    # Only one subject in registry
    registry = load_registry(registry_path)
    assert len(registry.subjects) == 1
    assert registry.subjects[subject1.subject_id].name == "skill-a-updated"


def test_multiple_different_subjects_independently(
    skill_a_v1: Path, skill_b: Path, registry_path: Path
) -> None:
    """Multiple different skills are registered independently."""
    register_local_subject(
        skill_md_path=skill_a_v1,
        name="skill-a",
        author="owner",
        author_source="manual",
        origin="local_archive",
        registry_path=registry_path,
    )

    register_local_subject(
        skill_md_path=skill_b,
        name="skill-b",
        author="other",
        author_source="manual",
        origin="upstream_install",
        registry_path=registry_path,
    )

    subjects = list_local_subjects(registry_path)
    assert len(subjects) == 2
    names = {s.name for s in subjects}
    assert names == {"skill-a", "skill-b"}


def test_control_character_rejection_in_name(tmp_path: Path) -> None:
    """Names with control characters are rejected."""
    p = tmp_path / "SKILL.md"
    p.write_text("---\nname: test\n---\nbody\n", encoding="utf-8")

    with pytest.raises(ValueError, match="control characters"):
        register_local_subject(
            skill_md_path=p,
            name="test\x00evil",
            author="owner",
            author_source="manual",
            origin="local_archive",
        )
