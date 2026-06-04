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

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_MIGRATIONS_DIR = REPO_ROOT / "migrations" / "evidence"
RUNTIME_MIGRATIONS_DIR = REPO_ROOT / "migrations" / "runtime"


class MigrationTamperedError(RuntimeError):
    """A migration file's SHA-256 no longer matches its applied record."""


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
    """Find numbered ``.sql`` files in ascending version order."""
    if not directory.exists():
        return []
    out: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
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


def apply_pending(conn: sqlite3.Connection, migrations: list[Migration]) -> list[str]:
    """Apply migrations not yet recorded; return the migration_ids applied.

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
        with conn:
            conn.executescript(m.sql)
            conn.execute(
                "INSERT INTO schema_migrations (migration_id, file_sha256) VALUES (?, ?)",
                (m.migration_id, m.sha256),
            )
        newly.append(m.migration_id)
    return newly


def open_db(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with the harness's standard pragmas.

    journal_mode=WAL is set OUTSIDE of any transaction (it is a persistent
    PRAGMA so this matters on first open of the file).
    """
    conn = sqlite3.connect(str(path), isolation_level=None)  # autocommit; `with conn` still works
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def open_evidence(path: str | Path) -> sqlite3.Connection:
    conn = open_db(path)
    apply_pending(conn, discover(EVIDENCE_MIGRATIONS_DIR))
    return conn


def open_runtime(path: str | Path) -> sqlite3.Connection:
    conn = open_db(path)
    apply_pending(conn, discover(RUNTIME_MIGRATIONS_DIR))
    return conn
