"""SQLite migration runner.

Two-database design (per ADR in docs/COUNCIL_FINDINGS.md):

* ``evidence.db`` — append-only. Schema lives in ``migrations/evidence/``.
  Every evidence table carries BEFORE UPDATE/DELETE triggers that
  ``RAISE(ABORT, 'append_only_violation: <table>')``.
* ``runtime.db`` — mutable. In-flight run progress, cost ledger, current
  calibration pointer. Schema lives in ``migrations/runtime/``.

Migrations are numbered SQL files (``NNNN_<snake_name>.sql``) applied in
ascending order. Each application records the file SHA-256 in
``schema_migrations``; on startup the runner refuses to proceed if a
previously-applied file has been mutated (SCHEMA-F5 tamper-evidence).
"""

from __future__ import annotations

import contextlib
import hashlib
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from skill_harness.storage.errors import (
    BootstrapError,
    MigrationApplyError,
    MigrationTamperedError,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_MIGRATIONS_DIR = REPO_ROOT / "migrations" / "evidence"
RUNTIME_MIGRATIONS_DIR = REPO_ROOT / "migrations" / "runtime"

# Re-export so existing `from skill_harness.storage.migrations import
# MigrationTamperedError` callers keep working.
__all__ = [
    "EVIDENCE_MIGRATIONS_DIR",
    "RUNTIME_MIGRATIONS_DIR",
    "BootstrapError",
    "Migration",
    "MigrationApplyError",
    "MigrationTamperedError",
    "applied_records",
    "apply_pending",
    "discover",
    "open_db",
    "open_evidence",
    "open_runtime",
]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    sha256: str

    @property
    def migration_id(self) -> str:
        return f"{self.version:04d}_{self.name}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def discover(directory: Path) -> list[Migration]:
    """Find numbered ``.sql`` files in ascending version order.

    Raises ``BootstrapError`` if any version number appears more than once in
    the same directory (A30 duplicate-version guard).  The check runs BEFORE
    filename validation so a duplicate-version error is distinguishable from a
    malformed-filename error.
    """
    if not directory.exists():
        return []
    paths = sorted(directory.glob("*.sql"))

    # A30 duplicate-version guard — group by the leading digit sequence.
    # Run this pass BEFORE parsing stems so the error type is unambiguous.
    version_to_paths: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        version_str = path.stem.split("_")[0]
        if version_str.isdigit():  # skip non-numeric stems (caught below)
            version_to_paths[version_str].append(path.name)
    for version_str, names in version_to_paths.items():
        if len(names) > 1:
            raise BootstrapError(
                f"duplicate migration version {version_str} in {directory}: "
                + ", ".join(sorted(names))
            )

    out: list[Migration] = []
    for path in paths:
        stem = path.stem
        version_str, _, name = stem.partition("_")
        if not version_str.isdigit():
            raise ValueError(f"migration filename must start with digits: {path}")
        sql = path.read_text(encoding="utf-8")
        out.append(
            Migration(
                version=int(version_str),
                name=name,
                sql=sql,
                sha256=_sha256(sql),
            )
        )
    return out


def applied_records(conn: sqlite3.Connection) -> dict[str, str]:
    """Return ``{migration_id: file_sha256}`` for applied migrations.

    The very first migration on a fresh DB creates the ``schema_migrations``
    table itself, so we tolerate its absence on the first read.
    """
    try:
        cur = conn.execute("SELECT migration_id, file_sha256 FROM schema_migrations")
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return {}
        raise
    return {row[0]: row[1] for row in cur.fetchall()}


def _split_statements(sql: str) -> list[str]:
    """Split a multi-statement SQL script into individual statements.

    ``sqlite3.complete_statement`` honors SQLite's parser semantics, including
    embedded semicolons inside trigger ``BEGIN ... END`` bodies — which our
    append-only enforcement triggers all have. Naive ``str.split(";")`` would
    shatter every trigger body.

    Accumulates lines until the buffer ends in a complete statement, then
    emits the buffer and resets. Trailing comments / whitespace are tolerated;
    a trailing partial statement (e.g. a missing ``;``) raises so that a
    malformed migration cannot apply silently.
    """
    statements: list[str] = []
    buf = ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            stmt = buf.strip()
            if stmt:
                statements.append(stmt)
            buf = ""
    leftover_non_comment = [
        ln for ln in buf.splitlines() if ln.strip() and not ln.lstrip().startswith("--")
    ]
    if leftover_non_comment:
        raise MigrationApplyError(
            f"trailing incomplete SQL (missing ';'?): {leftover_non_comment[0][:120]!r}"
        )
    return statements


def apply_pending(conn: sqlite3.Connection, migrations: list[Migration]) -> list[str]:
    """Apply migrations not yet recorded; return the migration_ids applied.

    Per RELIABILITY-F1: each migration applies in an explicit
    ``BEGIN IMMEDIATE`` / ``COMMIT`` transaction with the schema_migrations
    INSERT inside the same transaction. On any failure the transaction is
    rolled back and ``MigrationApplyError`` is raised, leaving the DB in the
    pre-migration state with NO ledger row written. The prior implementation
    used ``with conn:`` + ``executescript`` which, in ``isolation_level=None``
    autocommit mode, did not actually bracket the apply + ledger-write inside
    a transaction — a crash between the two left the DB schema applied but
    unrecorded, and the ledger lied on next startup.

    Raises ``MigrationTamperedError`` if a previously-applied file's SHA-256
    no longer matches the recorded value.
    """
    applied = applied_records(conn)
    newly: list[str] = []
    for m in migrations:
        recorded = applied.get(m.migration_id)
        if recorded is not None:
            if recorded != m.sha256:
                raise MigrationTamperedError(
                    f"migration {m.migration_id} sha256 mismatch: "
                    f"recorded={recorded[:12]} current={m.sha256[:12]}"
                )
            continue

        statements = _split_statements(m.sql)
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in statements:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_migrations (migration_id, file_sha256) VALUES (?, ?)",
                (m.migration_id, m.sha256),
            )
            conn.execute("COMMIT")
        except Exception as exc:
            # ROLLBACK may itself fail if the transaction was already rolled
            # back implicitly by the failing statement; that is benign here.
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            if isinstance(exc, MigrationApplyError):
                raise
            raise MigrationApplyError(f"failed to apply migration {m.migration_id}: {exc}") from exc
        newly.append(m.migration_id)
    return newly


_VALID_SYNCHRONOUS = frozenset({"NORMAL", "FULL"})


def open_db(path: str | Path, *, synchronous: str = "NORMAL") -> sqlite3.Connection:
    """Open a SQLite connection with the harness's standard pragmas.

    ``synchronous`` is the load-bearing knob: ``FULL`` is required for the
    append-only evidence DB (RELIABILITY-F5; never lose committed audit data
    on power loss); ``NORMAL`` is the right default for runtime state, which
    can be re-derived from evidence after a crash.

    journal_mode=WAL is set OUTSIDE of any transaction — it is a persistent
    PRAGMA, so this matters on first open of the file.
    """
    # synchronous is interpolated into a PRAGMA; validate against an allowlist
    # so a typo can't enable e.g. OFF and silently degrade durability.
    if synchronous not in _VALID_SYNCHRONOUS:
        raise ValueError(
            f"synchronous must be one of {sorted(_VALID_SYNCHRONOUS)}, got {synchronous!r}"
        )
    conn = sqlite3.connect(str(path), isolation_level=None)  # autocommit
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA synchronous = {synchronous}")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def open_evidence(path: str | Path) -> sqlite3.Connection:
    migrations = discover(EVIDENCE_MIGRATIONS_DIR)
    if not migrations:
        raise BootstrapError(
            f"no evidence migrations discovered at {EVIDENCE_MIGRATIONS_DIR}; "
            "the append-only DB cannot be opened without its schema + triggers"
        )
    conn = open_db(path, synchronous="FULL")
    try:
        apply_pending(conn, migrations)
    except BaseException:
        conn.close()
        raise
    return conn


def open_runtime(path: str | Path) -> sqlite3.Connection:
    migrations = discover(RUNTIME_MIGRATIONS_DIR)
    if not migrations:
        raise BootstrapError(f"no runtime migrations discovered at {RUNTIME_MIGRATIONS_DIR}")
    conn = open_db(path, synchronous="NORMAL")
    try:
        apply_pending(conn, migrations)
    except BaseException:
        conn.close()
        raise
    return conn
