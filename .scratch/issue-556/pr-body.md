# Issue #556: Local-only subject registration

## Summary

This PR implements local-only subject registration for third-party skill
artifacts that are preserved locally but not published. The harness can now
discover, verify, and record measurements against these subjects without
copying their bytes into this public repository.

## What was built

A new module `skill_harness/subject/local.py` that provides:

- `register_local_subject()` — Register a local-only subject by path
- `resolve_subject()` — Verify a subject's digest matches its registration
- `compute_subject_digest()` — Compute SHA-256 of a SKILL.md file
- `render_subject_receipt()` — Create a receipt for a subject measurement
- `load_registry()` / `list_local_subjects()` — Read the registry

The registry is stored as `.skill_harness/local_subjects.json` — a JSON file
containing only metadata (paths and digests), never the subject's bytes.

## Acceptance criteria satisfaction

### AC1: A local-only subject can be declared by path, and the declaration is recorded somewhere a later session can read without being told it exists.

**What was built:** `register_local_subject()` writes a JSON registry file to
`.skill_harness/local_subjects.json`. The registry is keyed by subject_id
(SHA-256 of SKILL.md bytes) and contains all metadata needed to identify and
verify the subject.

**Test:** `test_register_local_subject_creates_registry_file` verifies the
registry file is created and can be loaded. `test_list_local_subjects_reads_from_file`
verifies later sessions can discover subjects without being told.

**Observation:** The registry file is created at the path and contains the
subject metadata. A fresh `load_registry()` call on the same path returns
the registered subject.

### AC2: The declaration pins the subject by content digest, not by path alone, so a changed file is a different subject rather than a silent substitution.

**What was built:** `subject_id` is the SHA-256 of the SKILL.md bytes. Two
different files produce different subject_ids. `resolve_subject()` verifies
the digest matches before returning a subject.

**Test:** `test_changed_file_is_different_subject` registers two versions of
the same skill with different content and verifies they get different
subject_ids. `test_resolve_subject_fails_when_file_modified` modifies a file
after registration and verifies resolution fails.

**Observation:** When the file is modified, `resolve_subject()` raises
`ValueError` with a message about the digest not matching. The silent
substitution is prevented.

### AC3: The two archived copies are distinguishable as separate subjects, and a receipt names which was measured.

**What was built:** Each registered subject has a unique subject_id based on
content. Receipts record the exact subject_id, source_path, and source_digest.

**Test:** `test_two_copies_are_separate_subjects` registers two copies with
different origins and verifies they are distinct. `test_receipt_names_which_was_measured`
verifies the receipt records the exact subject that was measured.

**Observation:** Two copies with different content get different subject_ids
and different receipts. The receipt unambiguously names which was measured.

### AC4: A receipt for a subject the owner did not author records the author, and a verdict cannot be rendered without that field.

**What was built:** `LocalSubject.author` is a required field. `SubjectReceipt.author`
is populated from the subject's author. `render_subject_receipt()` requires a
subject with an author.

**Test:** `test_receipt_requires_author_for_third_party` registers a third-party
skill and verifies the receipt carries the author. `test_verdict_renders_author_in_receipt`
verifies even a refused receipt carries the author.

**Observation:** The author field is always present in the receipt. A verdict
receipt cannot be created without going through a `LocalSubject` that has an
author.

### AC5: A red demonstration shows a run refused when the declared digest does not match the file on disk.

**What was built:** `verify_subject_integrity()` compares a file's current
digest against an expected value. `resolve_subject()` uses this to refuse
when the file has been modified.

**Test:** `test_verify_subject_integrity_detects_mismatch` modifies a file and
verifies the integrity check fails. `test_refused_receipt_for_digest_mismatch`
creates a refused receipt showing the mismatch.

**Observation:** After modifying the file, `verify_subject_integrity()` returns
`(False, actual_digest)`. The refused receipt records the mismatch reason.

### AC6: A subject path that does not exist fails the run rather than reporting silently.

**What was built:** `register_local_subject()` raises `FileNotFoundError` if
the path does not exist. `resolve_subject()` does the same. `verify_subject_integrity()`
returns `(False, error_message)` for missing files.

**Test:** `test_register_nonexistent_path_fails` verifies registration raises.
`test_resolve_nonexistent_path_fails` verifies resolution raises.
`test_verify_integrity_nonexistent_path` verifies integrity check returns False.

**Observation:** All three operations fail loudly for non-existent paths —
no silent failure.

### AC7: The registration does not copy the subject's bytes into this repository.

**What was built:** The registry contains only metadata: source_path,
source_digest, name, author, author_source, origin, registered_at. No skill
content is stored.

**Test:** `test_registration_does_not_copy_bytes` verifies the registry file
does not contain the skill's body text. `test_registry_contains_only_paths_and_digests`
verifies the JSON structure has no content field.

**Observation:** The registry JSON contains only paths and digests. The skill's
body text ("First version", "Body v1") is not present in the registry file.

## Gate results

- `ruff check`: clean
- `ruff format`: clean
- `mypy --strict`: clean (no issues found)

## Tests

24 tests covering all acceptance criteria:
- AC1: 4 tests (registry creation, field values, empty registry, listing)
- AC2: 4 tests (digest pinning, changed file detection, resolution, modification refusal)
- AC3: 2 tests (separate subjects, receipt naming)
- AC4: 3 tests (author recording, verdict author, refused author)
- AC5: 3 tests (integrity check, integrity pass, refused receipt)
- AC6: 3 tests (registration failure, resolution failure, integrity failure)
- AC7: 2 tests (no bytes copied, structure validation)
- Edge cases: 2 tests (re-registration, control characters)

All 24 tests pass.
