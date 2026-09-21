"""Local-only subject registration for third-party skill artifacts.

When a skill is not published but preserved locally (e.g., archived at a path
outside this repository), the harness needs a way to discover it without being
told. This module provides that mechanism: register a local-only subject by
path, record its content digest, and make it discoverable to later sessions.

Design constraints:
- The registration does NOT copy the subject's bytes into this repository
  (this repository is public; copying a third-party package here is
  republication, which the owner's ruling refuses).
- The declaration pins the subject by content digest (SHA-256 of SKILL.md),
  not by path alone — a changed file is a different subject.
- Two archived copies with different content are distinguishable as separate
  subjects (different digests).
- A receipt for a subject the owner did not author records the author; a
  verdict cannot be rendered without that field.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Registry location
# ---------------------------------------------------------------------------

DEFAULT_REGISTRY_PATH = Path(".skill_harness") / "local_subjects.json"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LocalSubject(BaseModel):
    """A local-only subject declaration.

    Fields:
        subject_id: Content-based identifier (SHA-256 of SKILL.md bytes).
        source_path: Absolute or relative path to the subject's SKILL.md.
        source_digest: SHA-256 hex digest of the file at registration time.
        name: Human-readable name (from SKILL.md frontmatter).
        author: The original author of the skill. Required for third-party
            subjects; the owner's own work can be empty.
        author_source: How the author was determined (e.g., "frontmatter",
            "registry", "manual").
        origin: Where this subject came from (e.g., "local_archive",
            "upstream_install", "manual").
        registered_at: ISO 8601 timestamp of registration.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    subject_id: str  # SHA-256 of SKILL.md bytes
    source_path: str
    source_digest: str
    name: str
    author: str
    author_source: str
    origin: str
    registered_at: str

    @field_validator(
        "subject_id", "source_path", "source_digest", "name", "author", "author_source", "origin"
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        if "\x00" in v or any("\x00" <= ch < "\x20" and ch not in ("\t", "\n", "\r") for ch in v):
            raise ValueError(f"{field_name}: contains forbidden control characters")
        return v


class LocalSubjectRegistry(BaseModel):
    """Registry of local-only subject declarations.

    Stored as a JSON file; a later session reads it to discover registered
    subjects without being told they exist.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    subjects: dict[str, LocalSubject] = Field(default_factory=dict)


class SubjectReceipt(BaseModel):
    """A receipt for a subject measurement.

    Records the subject's identity, author, and which copy was measured.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    subject_id: str  # SHA-256 of the measured SKILL.md bytes
    source_path: str  # path that was measured
    source_digest: str  # digest that was verified
    name: str
    author: str  # REQUIRED for third-party subjects
    measured_at: str  # ISO 8601
    verdict: str  # e.g., "measured", "refused"
    verdict_reason: str | None = None


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def compute_subject_digest(skill_md_path: Path) -> str:
    """Compute SHA-256 digest of a SKILL.md file.

    :raises FileNotFoundError: if the file does not exist.
    """
    if not skill_md_path.is_file():
        raise FileNotFoundError(f"subject file does not exist: {skill_md_path}")
    content = skill_md_path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def compute_subject_id(digest: str) -> str:
    """Derive a stable subject_id from the content digest.

    The subject_id IS the digest — content-addressed, so different content
    yields a different subject.
    """
    return digest


def register_local_subject(
    *,
    skill_md_path: Path,
    name: str,
    author: str,
    author_source: str,
    origin: str,
    registry_path: Path | None = None,
) -> LocalSubject:
    """Register a local-only subject by path.

    Records the subject's identity (content digest) without copying its
    bytes into this repository. The subject is later discoverable by reading
    the registry file.

    :param skill_md_path: Path to the SKILL.md file.
    :param name: Human-readable name of the skill.
    :param author: The original author. Required for third-party subjects.
    :param author_source: How the author was determined.
    :param origin: Where this subject came from.
    :param registry_path: Path to the registry file. Defaults to
        .skill_harness/local_subjects.json in the current directory.
    :returns: The registered LocalSubject.
    :raises FileNotFoundError: if skill_md_path does not exist.
    :raises ValueError: if author is empty for a third-party subject.
    """
    if not skill_md_path.is_file():
        raise FileNotFoundError(f"subject file does not exist: {skill_md_path}")

    digest = compute_subject_digest(skill_md_path)
    subject_id = compute_subject_id(digest)

    subject = LocalSubject(
        subject_id=subject_id,
        source_path=str(skill_md_path.resolve()),
        source_digest=digest,
        name=name,
        author=author,
        author_source=author_source,
        origin=origin,
        registered_at=datetime.now(UTC).isoformat(),
    )

    # Write to registry
    reg_path = registry_path or DEFAULT_REGISTRY_PATH
    reg_path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_registry(reg_path)
    # Replace if same subject_id already exists (e.g., re-registration)
    updated_subjects = {k: v for k, v in existing.subjects.items() if k != subject_id}
    updated_subjects[subject_id] = subject
    updated = LocalSubjectRegistry(subjects=updated_subjects)

    reg_path.write_text(
        json.dumps(updated.model_dump(), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return subject


def load_registry(registry_path: Path | None = None) -> LocalSubjectRegistry:
    """Load the local subject registry.

    Returns an empty registry if the file does not exist.
    """
    reg_path = registry_path or DEFAULT_REGISTRY_PATH
    if not reg_path.is_file():
        return LocalSubjectRegistry()

    content = reg_path.read_text(encoding="utf-8")
    return LocalSubjectRegistry.model_validate_json(content)


def resolve_subject(
    skill_md_path: Path,
    *,
    registry_path: Path | None = None,
) -> LocalSubject:
    """Resolve a subject by verifying its digest matches the registered declaration.

    This is the verification function that ensures a changed file is detected
    as a different subject rather than silently substituted.

    :param skill_md_path: Path to the SKILL.md file to verify.
    :param registry_path: Path to the registry file.
    :returns: The matching LocalSubject.
    :raises FileNotFoundError: if the file does not exist.
    :raises ValueError: if the file's digest does not match any registered subject.
    """
    if not skill_md_path.is_file():
        raise FileNotFoundError(f"subject file does not exist: {skill_md_path}")

    current_digest = compute_subject_digest(skill_md_path)
    registry = load_registry(registry_path)

    # Look for a subject with this digest
    for subject in registry.subjects.values():
        if subject.source_digest == current_digest:
            # Also verify the path matches
            if subject.source_path == str(skill_md_path.resolve()):
                return subject
            # Digest matches but path differs — same content at different location
            # This is still a valid resolution (two copies of same content)
            return subject

    raise ValueError(
        f"no registered subject with digest {current_digest[:16]}… found in registry; "
        f"file may have been modified or was never registered"
    )


def verify_subject_integrity(
    skill_md_path: Path,
    expected_digest: str,
) -> tuple[bool, str]:
    """Verify that a file's digest matches an expected value.

    :returns: (match, actual_digest) — True if match, False if mismatch.
    """
    try:
        actual = compute_subject_digest(skill_md_path)
    except FileNotFoundError as exc:
        return False, str(exc)

    return actual == expected_digest, actual


def render_subject_receipt(
    subject: LocalSubject,
    *,
    verdict: Literal["measured", "refused"],
    verdict_reason: str | None = None,
) -> SubjectReceipt:
    """Create a receipt for a subject measurement.

    This is the evidence of which subject was measured and by whom.
    """
    return SubjectReceipt(
        subject_id=subject.subject_id,
        source_path=subject.source_path,
        source_digest=subject.source_digest,
        name=subject.name,
        author=subject.author,
        measured_at=datetime.now(UTC).isoformat(),
        verdict=verdict,
        verdict_reason=verdict_reason,
    )


def list_local_subjects(registry_path: Path | None = None) -> list[LocalSubject]:
    """List all registered local subjects."""
    registry = load_registry(registry_path)
    return list(registry.subjects.values())
