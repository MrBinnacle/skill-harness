"""Typed exceptions for the storage layer.

Surfaces failure modes the Phase 1.5 council identified as silent in v0.0:
empty migration discovery (RELIABILITY-F2), mid-apply crash (RELIABILITY-F1),
sha256 ledger mismatch (SCHEMA-F5 / unchanged). Untyped `RuntimeError` would
let callers conflate these with unrelated failures.
"""

from __future__ import annotations


class StorageError(Exception):
    """Base class for storage-layer failures.

    Catch this if you want to handle all storage faults uniformly; catch the
    specific subclasses to discriminate.
    """


class BootstrapError(StorageError):
    """Database cannot be initialized.

    Raised by ``open_evidence`` / ``open_runtime`` when migration discovery
    returns no files. The append-only DB is meaningless without its triggers;
    silently opening an empty DB would let writes succeed that should have
    aborted, corrupting the audit story (RELIABILITY-F2).
    """


class MigrationApplyError(StorageError):
    """A migration failed mid-apply; the transaction was rolled back.

    Raised by ``apply_pending`` when a statement inside a migration fails.
    The accompanying transaction has been rolled back, so the DB is in the
    pre-migration state and the ``schema_migrations`` row was NOT written
    (RELIABILITY-F1: avoids the silent partial-apply / corrupted-ledger pair).
    """


class MigrationTamperedError(StorageError):
    """A previously-applied migration file's SHA-256 no longer matches.

    The runner refuses to proceed when the on-disk file diverges from the
    sha recorded in ``schema_migrations`` (SCHEMA-F5). Either the file was
    edited post-apply or the ledger was tampered with; either way, manual
    inspection is required.
    """
