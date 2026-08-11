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

A raw-byte digest cannot tell a reworded comment from a changed table, so that
refusal used to be permanent and total: a comment-only edit bricked every
existing store and no repair path shipped (#168 finding, CORRUPTION; fixed by
#169). The runner now also records a SEMANTIC digest per applied file and, when
a mismatch is provably confined to comments and whitespace, appends a
compensating restamp record instead of refusing. Both safeguards stay in force
-- a real schema change still locks the store.
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

# SQL migrations ship INSIDE the package (migrations_sql/) so installed copies
# work. A repo-root path here broke every `pip install`ed copy of v0.1 — the
# storage layer could not bootstrap outside a source checkout.
_SQL_ROOT = Path(__file__).resolve().parent / "migrations_sql"
EVIDENCE_MIGRATIONS_DIR = _SQL_ROOT / "evidence"
RUNTIME_MIGRATIONS_DIR = _SQL_ROOT / "runtime"

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
    "open_evidence_readonly",
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

    @property
    def semantic_sha256(self) -> str:
        """Digest of the file with comments stripped and whitespace collapsed.

        Deliberately NOT a replacement for ``sha256``. The raw digest stays the
        tamper detector; this one exists only to answer a second question the raw
        digest cannot -- *did the schema actually change?* -- so that a comment
        edit is repairable instead of terminal (#169).

        A derived property rather than a stored field on purpose. As a field it
        would need a default, and a defaulted empty string is a live corruption
        hazard: two unrelated migrations both carrying ``""`` would compare
        semantically equal, which is precisely the comparison that authorises a
        restamp. Derived from ``sql``, it cannot be absent or stale.
        """
        return _semantic_sha256(self.sql)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# SQLite's quoting characters, all of which escape by doubling. Handled
# uniformly: a `--` inside ANY of them is data or an identifier, not a comment.
_QUOTE_CHARS = frozenset({"'", '"', "`"})


def _semantic_sql(sql: str) -> str:
    """Strip comments and collapse whitespace OUTSIDE quoted spans.

    Two files that differ only in commentary must normalise to the same text;
    two that differ in any statement, identifier or literal must not. Both halves
    are load-bearing -- the first is what makes the repair possible, the second is
    what keeps it from becoming a bypass of safeguard A.

    A regex cannot do this. A ``--`` inside a quoted string is data, and in this
    schema that is not hypothetical: the append-only triggers raise messages like
    ``'append_only_violation: schema_migrations'``. Stripping from ``--`` to
    end-of-line would eat the rest of a trigger body and make two different
    triggers normalise alike.

    Quoted spans are copied BYTE FOR BYTE, whitespace included. An earlier draft
    collapsed whitespace across the whole file after stripping comments, which
    silently equated ``CHECK (k IN ('a b'))`` with ``CHECK (k IN ('a  b'))`` --
    two different constraints, one digest, so the runner would have accepted that
    edit as comment-only and restamped it. Collapsing is therefore per-segment.

    A segment that is *entirely* whitespace collapses to a single space rather
    than to nothing, because between two quoted spans its presence carries
    meaning: SQLite reads ``SELECT 'a' 'b'`` as ``'a'`` aliased to ``b``, which
    must not normalise to the single literal ``'a''b'``.
    """
    segments: list[tuple[bool, str]] = []
    plain: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch in _QUOTE_CHARS:
            segments.append((False, "".join(plain)))
            plain = []
            span = [ch]
            i += 1
            while i < n:
                c = sql[i]
                span.append(c)
                i += 1
                if c == ch:
                    if i < n and sql[i] == ch:  # doubled quote = escaped, not a terminator
                        span.append(ch)
                        i += 1
                        continue
                    break
            # An unterminated span reaches here verbatim. It is not this
            # function's job to reject it: _split_statements and the apply
            # itself will refuse a malformed migration.
            segments.append((True, "".join(span)))
            continue
        if sql.startswith("--", i):
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        plain.append(ch)
        i += 1
    segments.append((False, "".join(plain)))

    return "".join(text if quoted else _collapse_ws(text) for quoted, text in segments).strip()


def _collapse_ws(text: str) -> str:
    """Collapse whitespace runs to single spaces; keep pure whitespace as one space."""
    collapsed = " ".join(text.split())
    if collapsed:
        return collapsed
    return " " if text else ""


def _semantic_sha256(sql: str) -> str:
    return _sha256(_semantic_sql(sql))


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


# ---------------------------------------------------------------------------
# #169 -- repair bookkeeping for the store-bricking deadlock
#
# The deadlock: safeguard A (raw-byte digest of every applied file) detects that
# a shipped file changed; safeguard B (append-only triggers on the ledger)
# forbids correcting the record that would clear safeguard A. A comment-only
# edit therefore locked every existing store, permanently.
#
# Both safeguards are kept exactly as they are. What is added is a SECOND
# question -- "did the schema actually change?" -- and an APPENDED compensating
# record when the answer is no. The ledger row itself is never rewritten and no
# migration file is edited: editing a shipped ``.sql`` is the trigger condition
# for this very bug, so a repair delivered that way would brick every existing
# store on its way to fixing bricking.
#
# The tables are RUNNER-OWNED (``CREATE TABLE IF NOT EXISTS`` here) rather than
# shipped as a new migration file. The reproduction tests build synthetic
# migration directories holding only their own ``0001_initial.sql``; a fix
# shipped as ``0800_*.sql`` would not exist in those directories, so the fix
# would look broken while being correct. They carry their own append-only
# triggers, both because the store's contract requires it of every evidence
# table and because a correction ledger that could be quietly rewritten would
# be no safeguard at all.
# ---------------------------------------------------------------------------

_REPAIR_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS migration_semantic_digests (
    migration_id    TEXT NOT NULL,
    file_sha256     TEXT NOT NULL,
    semantic_sha256 TEXT NOT NULL,
    recorded_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (migration_id, file_sha256)
);
CREATE TRIGGER IF NOT EXISTS migration_semantic_digests_no_update
    BEFORE UPDATE ON migration_semantic_digests
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: migration_semantic_digests'); END;
CREATE TRIGGER IF NOT EXISTS migration_semantic_digests_no_delete
    BEFORE DELETE ON migration_semantic_digests
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: migration_semantic_digests'); END;
CREATE TABLE IF NOT EXISTS migration_sha_restamps (
    -- Declared INTEGER PRIMARY KEY, not left to the implicit rowid, because
    -- "latest restamp wins" resolves by this column. An explicit key is written
    -- out by .dump and so survives dump/restore/VACUUM; an implicit rowid does
    -- not, which is the same hazard the E3 ban-timestamp-final-order-by hook
    -- exists to catch. Ordering by recorded_at instead would tie at millisecond
    -- resolution.
    restamp_id        INTEGER PRIMARY KEY,
    migration_id      TEXT NOT NULL,
    superseded_sha256 TEXT NOT NULL,
    file_sha256       TEXT NOT NULL,
    semantic_sha256   TEXT NOT NULL,
    reason            TEXT NOT NULL,
    recorded_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TRIGGER IF NOT EXISTS migration_sha_restamps_no_update
    BEFORE UPDATE ON migration_sha_restamps
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: migration_sha_restamps'); END;
CREATE TRIGGER IF NOT EXISTS migration_sha_restamps_no_delete
    BEFORE DELETE ON migration_sha_restamps
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: migration_sha_restamps'); END;
"""

_COMMENT_ONLY_REASON = (
    "semantic digest unchanged: the edit altered comments or whitespace only, "
    "so no schema change occurred (#169)"
)


_REPAIR_OBJECTS = (
    "migration_semantic_digests",
    "migration_semantic_digests_no_update",
    "migration_semantic_digests_no_delete",
    "migration_sha_restamps",
    "migration_sha_restamps_no_update",
    "migration_sha_restamps_no_delete",
)


def _repair_tables_present(conn: sqlite3.Connection) -> bool:
    """True only when both tables AND all four triggers exist.

    Counting the triggers too, not just the tables: a store left half-created by
    a crash would otherwise be treated as complete and would carry a mutable
    table inside an append-only store.
    """
    # Placeholders written out rather than joined into an f-string: this repo bans
    # interpolated SQL, and a fixed-arity IN list needs no interpolation.
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name IN (?, ?, ?, ?, ?, ?)",
        _REPAIR_OBJECTS,
    ).fetchone()
    return bool(row[0] == len(_REPAIR_OBJECTS))


def _ensure_repair_tables(conn: sqlite3.Connection) -> None:
    """Create the repair bookkeeping tables and their triggers, atomically.

    One transaction for the whole set, deliberately: a table that arrived
    without its append-only triggers would be silently mutable inside an
    append-only store, which is the exact gap
    ``test_every_evidence_table_carries_both_append_only_triggers`` exists to
    close. ``IF NOT EXISTS`` throughout makes this idempotent on every open.

    Returns immediately when the whole set is already present. That guard is not
    a micro-optimisation: before #169, opening a fully-migrated store performed
    NO writes at all, and an unconditional ``BEGIN IMMEDIATE`` here would have
    made every open take a write lock -- adding contention between concurrent
    openers and breaking ``open_evidence`` against a store on read-only media.
    The steady state stays read-only.
    """
    if _repair_tables_present(conn):
        return
    statements = _split_statements(_REPAIR_TABLES_SQL)
    conn.execute("BEGIN IMMEDIATE")
    try:
        for stmt in statements:
            conn.execute(stmt)
        conn.execute("COMMIT")
    except Exception as exc:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")
        raise MigrationApplyError(f"failed to create migration repair tables: {exc}") from exc


def _effective_recorded_sha(conn: sqlite3.Connection, migration_id: str, ledger_sha: str) -> str:
    """The raw digest currently in force: latest restamp wins, else the ledger row.

    This is what makes acceptance idempotent. Once a comment-only edit has been
    restamped, the next open sees no mismatch at all and appends nothing.
    """
    row = conn.execute(
        "SELECT file_sha256 FROM migration_sha_restamps WHERE migration_id = ? "
        "ORDER BY restamp_id DESC LIMIT 1",
        (migration_id,),
    ).fetchone()
    return str(row[0]) if row is not None else ledger_sha


def _recorded_semantic(conn: sqlite3.Connection, migration_id: str, file_sha: str) -> str | None:
    row = conn.execute(
        "SELECT semantic_sha256 FROM migration_semantic_digests "
        "WHERE migration_id = ? AND file_sha256 = ?",
        (migration_id, file_sha),
    ).fetchone()
    return None if row is None else str(row[0])


def _verify_or_restamp(conn: sqlite3.Connection, m: Migration, ledger_sha: str) -> None:
    """Verify an already-applied migration, repairing a comment-only edit.

    Raises ``MigrationTamperedError`` whenever the current file's SEMANTIC digest
    differs from the one recorded against the digest in force, or when no
    semantic digest was ever recorded for it. Safeguard A is not weakened: a real
    schema change still locks the store, and it is still the raw digest that
    detects the change in the first place.
    """
    in_force = _effective_recorded_sha(conn, m.migration_id, ledger_sha)

    if in_force == m.sha256:
        # The raw digest matched, so the file on disk IS the recorded one and its
        # semantic digest is trustworthy. Recording it here is the backfill that
        # heals stores created before this repair existed: their first open after
        # upgrading -- BEFORE any edit -- gives every applied migration a
        # semantic digest, so a later comment edit is repairable rather than
        # terminal.
        #
        # Read before writing, so a healthy store's open stays read-only (see
        # _ensure_repair_tables). Only the one healing open does any work.
        if _recorded_semantic(conn, m.migration_id, m.sha256) is None:
            _append_semantic_digest(conn, m.migration_id, m.sha256, m.semantic_sha256)
        return

    known_semantic = _recorded_semantic(conn, m.migration_id, in_force)
    if known_semantic is not None and known_semantic == m.semantic_sha256:
        _append_restamp(conn, m, superseded=in_force)
        return

    detail = (
        "no semantic digest was recorded for the digest in force, so this store "
        "predates the #169 repair and the edit cannot be shown to be harmless; "
        "restore the file's original bytes to reopen it"
        if known_semantic is None
        else "the schema itself changed, not only commentary"
    )
    raise MigrationTamperedError(
        f"migration {m.migration_id} sha256 mismatch: "
        f"recorded={in_force[:12]} current={m.sha256[:12]} -- {detail}"
    )


def _append_semantic_digest(
    conn: sqlite3.Connection, migration_id: str, file_sha: str, semantic_sha: str
) -> None:
    """Record a ``(migration_id, file_sha) -> semantic_sha`` mapping if absent.

    ``INSERT OR IGNORE`` rather than an upsert: the primary key already pins one
    semantic digest per raw digest, and a raw digest cannot correspond to two
    different file bodies. There is nothing to overwrite, and the table's own
    triggers would refuse the attempt anyway.
    """
    conn.execute(
        "INSERT OR IGNORE INTO migration_semantic_digests "
        "(migration_id, file_sha256, semantic_sha256) VALUES (?, ?, ?)",
        (migration_id, file_sha, semantic_sha),
    )


def _append_restamp(conn: sqlite3.Connection, m: Migration, *, superseded: str) -> None:
    """Append the compensating record that clears a comment-only mismatch.

    Nothing is rewritten and nothing is removed: the correction is an appended
    row, which is how append-only ledgers have always handled corrections. The
    superseded digest stays on the record, so the edit remains auditable rather
    than being erased by its own repair.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO migration_sha_restamps "
            "(migration_id, superseded_sha256, file_sha256, semantic_sha256, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (m.migration_id, superseded, m.sha256, m.semantic_sha256, _COMMENT_ONLY_REASON),
        )
        _append_semantic_digest(conn, m.migration_id, m.sha256, m.semantic_sha256)
        conn.execute("COMMIT")
    except Exception as exc:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")
        raise MigrationApplyError(
            f"failed to append restamp for migration {m.migration_id}: {exc}"
        ) from exc


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

    Raises ``MigrationTamperedError`` if a previously-applied file's SHA-256 no
    longer matches the digest in force AND the change is not provably confined to
    comments and whitespace. A comment-only edit is repaired by appending a
    restamp record rather than by refusing forever (#169); see the repair
    bookkeeping section above.
    """
    _ensure_repair_tables(conn)
    applied = applied_records(conn)
    newly: list[str] = []
    for m in migrations:
        recorded = applied.get(m.migration_id)
        if recorded is not None:
            _verify_or_restamp(conn, m, recorded)
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
            # Inside the SAME transaction as the ledger row, so the two can never
            # disagree. A store is therefore repairable from its very first open
            # rather than from its second; the backfill in _verify_or_restamp
            # exists for stores that predate this code, not for new ones.
            _append_semantic_digest(conn, m.migration_id, m.sha256, m.semantic_sha256)
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


def open_db(
    path: str | Path,
    *,
    synchronous: str = "NORMAL",
    _uri: bool = False,
) -> sqlite3.Connection:
    """Open a SQLite connection with the harness's standard pragmas.

    ``synchronous`` is the load-bearing knob: ``FULL`` is required for the
    append-only evidence DB (RELIABILITY-F5; never lose committed audit data
    on power loss); ``NORMAL`` is the right default for runtime state, which
    can be re-derived from evidence after a crash.

    journal_mode=WAL is set OUTSIDE of any transaction — it is a persistent
    PRAGMA, so this matters on first open of the file.

    ``_uri`` (private — only for ``open_evidence_readonly``): when True, the
    path is passed as a SQLite URI (e.g. ``file:/path?mode=ro``) and
    ``sqlite3.connect`` is called with ``uri=True``.  External callers must
    NOT use this flag directly; it exists solely to let the council-sanctioned
    read-only helper reuse the pragma/FK discipline of this function.
    """
    # synchronous is interpolated into a PRAGMA; validate against an allowlist
    # so a typo can't enable e.g. OFF and silently degrade durability.
    if synchronous not in _VALID_SYNCHRONOUS:
        raise ValueError(
            f"synchronous must be one of {sorted(_VALID_SYNCHRONOUS)}, got {synchronous!r}"
        )
    conn = sqlite3.connect(str(path), isolation_level=None, uri=_uri)  # autocommit
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


def open_evidence_readonly(path: str | Path) -> sqlite3.Connection:
    """Open ``evidence.db`` READ-ONLY for dry-run clause enumeration (A51 / council-sanctioned).

    Contract (ratified by A51 micro-council 2026-06-06 RATIFY-WITH-AMENDMENT, 3-0):
    - Opens ``file:<path>?mode=ro`` through ``open_db`` (reuses pragma/FK discipline).
    - Sets ``PRAGMA query_only = ON`` as a defence-in-depth write barrier.
    - Does NOT call ``apply_pending`` — read-only open must not write schema_migrations.
    - Raises ``BootstrapError`` (does NOT create) when the file is absent.

    This is the ONLY sanctioned way to open evidence.db read-only.  Callers must
    NOT use raw ``sqlite3.connect()`` (A23 §3 — bypasses FK enforcement and durability
    pragmas).

    Use case: ``run ablation --dry-run`` enumerates clauses from the evidence DB without
    any API calls, writes, or migration-apply.  The caller must close the connection when
    done.
    """
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise BootstrapError(
            f"evidence.db not found at {resolved}; "
            "skill not imported — run 'skill init <path>' first"
        )
    # Build SQLite URI for read-only access. mode=ro (NOT immutable=1) — correct for a
    # possibly-concurrent WAL DB where a concurrent --execute may be writing.
    uri = f"file:{resolved.as_posix()}?mode=ro"
    conn = open_db(uri, synchronous="NORMAL", _uri=True)
    # Defence-in-depth: PRAGMA query_only prevents any write even if caller makes mistake.
    conn.execute("PRAGMA query_only = ON")
    return conn
