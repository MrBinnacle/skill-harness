"""Reproduction of the store-bricking deadlock (issue #168).

The corruption shape, stated once: **safeguard A detects that a shipped file
changed; safeguard B forbids correcting the record that would clear it.** Editing
even a comment in a shipped file therefore locks every existing store, permanently,
because both safeguards hash raw file bytes.

Two independent instances of that shape exist. Both are reproduced here.

6a. migration sha ledger x ``schema_migrations`` append-only triggers
    ``discover()`` hashes the whole migration file text; ``apply_pending()`` refuses
    on mismatch; the recorded sha lives in ``schema_migrations``, which carries
    BEFORE UPDATE and BEFORE DELETE triggers. ``src/`` contains a SELECT and an
    INSERT against that table and no UPDATE path at all.

6b. ``subject/ingest.py`` self-hash x ``metric_versions`` append-only
    ``_oracle_implementation_hash()`` hashes its own module's bytes; the fail-closed
    re-check compares against a stored ``metric_versions`` row that is append-only.

These tests characterise the CURRENT behaviour. They are expected to pass on the
tree as it stands -- their job is to make the deadlock a pinned, named fact rather
than a workspace note, so that any future repair path has a test that changes when
it lands. The final test in each class is the one that states the absence of an
exit; those are the assertions a fix must flip.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from skill_harness.storage import migrations as migrations_module
from skill_harness.storage.errors import MigrationTamperedError
from skill_harness.storage.migrations import (
    apply_pending,
    discover,
    open_db,
    open_evidence,
    open_evidence_readonly,
)

SRC_ROOT = Path(migrations_module.__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 6a -- migration ledger deadlock
# ---------------------------------------------------------------------------


class TestMigrationLedgerDeadlock:
    """A comment-only edit to a shipped migration locks the store."""

    @staticmethod
    def _make_store(tmp_path: Path, migrations_dir: Path) -> Path:
        """Create a store under ``migrations_dir`` and close it."""
        db_path = tmp_path / "evidence.db"
        conn = open_db(db_path, synchronous="FULL")
        try:
            apply_pending(conn, discover(migrations_dir))
        finally:
            conn.close()
        return db_path

    @staticmethod
    def _seed_migrations(migrations_dir: Path) -> Path:
        """Write a minimal stand-in for the shipped ``0001_initial.sql``.

        It must create ``schema_migrations`` itself, exactly as the real first
        migration does: ``apply_pending`` writes the ledger row inside the same
        transaction that applies the file, so a synthetic migration that omits
        the ledger table cannot apply at all. The append-only triggers on
        ``schema_migrations`` are copied verbatim from the shipped migration --
        they are safeguard B, and the deadlock does not exist without them.
        """
        migrations_dir.mkdir(parents=True, exist_ok=True)
        shipped = migrations_dir / "0001_initial.sql"
        shipped.write_text(
            "-- a comment that carries no schema meaning whatsoever\n"
            "CREATE TABLE schema_migrations (\n"
            "    migration_id TEXT PRIMARY KEY,\n"
            "    applied_at   TEXT NOT NULL DEFAULT "
            "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),\n"
            "    file_sha256  TEXT NOT NULL,\n"
            "    notes        TEXT\n"
            ");\n"
            "CREATE TRIGGER schema_migrations_no_update BEFORE UPDATE ON schema_migrations\n"
            "    BEGIN SELECT RAISE(ABORT, 'append_only_violation: schema_migrations'); END;\n"
            "CREATE TRIGGER schema_migrations_no_delete BEFORE DELETE ON schema_migrations\n"
            "    BEGIN SELECT RAISE(ABORT, 'append_only_violation: schema_migrations'); END;\n"
            "CREATE TABLE thing (id INTEGER PRIMARY KEY);\n"
            "CREATE TRIGGER thing_no_update BEFORE UPDATE ON thing\n"
            "    BEGIN SELECT RAISE(ABORT, 'append_only_violation: thing'); END;\n"
            "CREATE TRIGGER thing_no_delete BEFORE DELETE ON thing\n"
            "    BEGIN SELECT RAISE(ABORT, 'append_only_violation: thing'); END;\n",
            encoding="utf-8",
        )
        return shipped

    def test_sha_covers_comments_not_just_schema(self, tmp_path: Path) -> None:
        """The hash is over raw file text, so a comment edit changes it.

        This is the whole reason the deadlock can be triggered by an edit that
        changes no schema. If this assertion ever fails, the deadlock's trigger
        condition has narrowed and the rest of this class should be revisited.
        """
        migrations_dir = tmp_path / "migrations"
        shipped = self._seed_migrations(migrations_dir)
        before = discover(migrations_dir)[0].sha256

        shipped.write_text(
            shipped.read_text(encoding="utf-8").replace(
                "-- a comment that carries no schema meaning whatsoever\n",
                "-- the same comment, reworded, with no schema meaning either\n",
            ),
            encoding="utf-8",
        )
        after = discover(migrations_dir)[0].sha256

        assert before != after, "comment-only edit did not change the recorded sha"

    def test_comment_edit_locks_an_existing_store(self, tmp_path: Path) -> None:
        """Safeguard A: the store refuses to open after a comment-only edit."""
        migrations_dir = tmp_path / "migrations"
        shipped = self._seed_migrations(migrations_dir)
        db_path = self._make_store(tmp_path, migrations_dir)

        # The store opens cleanly before the edit.
        conn = open_db(db_path, synchronous="FULL")
        try:
            apply_pending(conn, discover(migrations_dir))
        finally:
            conn.close()

        shipped.write_text(
            "-- reworded comment, identical schema below\n"
            + "".join(shipped.read_text(encoding="utf-8").splitlines(keepends=True)[1:]),
            encoding="utf-8",
        )

        conn = open_db(db_path, synchronous="FULL")
        try:
            with pytest.raises(MigrationTamperedError, match="0001_initial"):
                apply_pending(conn, discover(migrations_dir))
        finally:
            conn.close()

    def test_the_ledger_row_cannot_be_corrected(self, tmp_path: Path) -> None:
        """Safeguard B: the record that would clear the refusal is immutable.

        This is the half that turns a refusal into a deadlock. Both directions are
        asserted -- neither UPDATE nor DELETE can reach the recorded sha.
        """
        migrations_dir = tmp_path / "migrations"
        self._seed_migrations(migrations_dir)
        db_path = self._make_store(tmp_path, migrations_dir)

        conn = open_db(db_path, synchronous="FULL")
        try:
            with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
                conn.execute("UPDATE schema_migrations SET file_sha256 = 'corrected'")
            with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
                conn.execute("DELETE FROM schema_migrations")
        finally:
            conn.close()

    def test_no_restamp_path_exists_in_src(self) -> None:
        """There is no repair path anywhere in the shipped source.

        The deadlock is not merely "hard to fix from outside" -- the product ships
        no way to correct a stale sha. A fix for #169 should make this test fail,
        which is exactly why it is written as an assertion about absence.
        """
        offending: list[str] = []
        for py in SRC_ROOT.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "schema_migrations" not in text:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "schema_migrations" not in stripped:
                    continue
                upper = stripped.upper()
                if "UPDATE SCHEMA_MIGRATIONS" in upper or "DELETE FROM SCHEMA_MIGRATIONS" in upper:
                    offending.append(f"{py.relative_to(SRC_ROOT)}:{lineno}: {stripped}")

        assert offending == [], (
            "a re-stamp path now exists; the deadlock may be repairable and "
            "#169's fix should update this test: " + "; ".join(offending)
        )

    def test_readonly_access_survives_and_is_not_a_repair(self, tmp_path: Path) -> None:
        """The one escape hatch is read-only, so the store stays unwritable.

        Asserted behaviourally, against a bricked store. An earlier version of this
        test scanned ``migrations.py`` for the string ``apply_pending`` inside
        ``open_evidence_readonly`` and matched the docstring sentence that says it
        does NOT call it -- a source scan cannot tell a call from a mention of one.
        The observable contract is what matters: after the bricking edit the
        writable open refuses and the read-only open still succeeds, while staying
        unable to write.
        """
        migrations_dir = tmp_path / "migrations"
        shipped = self._seed_migrations(migrations_dir)
        db_path = self._make_store(tmp_path, migrations_dir)

        shipped.write_text(
            "-- reworded comment, identical schema below\n"
            + "".join(shipped.read_text(encoding="utf-8").splitlines(keepends=True)[1:]),
            encoding="utf-8",
        )

        # The writable path is bricked.
        conn = open_db(db_path, synchronous="FULL")
        try:
            with pytest.raises(MigrationTamperedError):
                apply_pending(conn, discover(migrations_dir))
        finally:
            conn.close()

        # The read-only path still opens the same file.
        ro = open_evidence_readonly(db_path)
        try:
            assert ro.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
            # ...and it is not a repair: the escape hatch cannot write.
            with pytest.raises(sqlite3.OperationalError):
                ro.execute("INSERT INTO thing (id) VALUES (1)")
        finally:
            ro.close()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Store-bricking deadlock (#168 finding, CORRUPTION). A comment-only edit to a "
        "shipped migration permanently locks every existing evidence store, and the "
        "product ships no repair path. #169 owns the fix; when it lands this test "
        "XPASSes and strict=True fails the suite, which is the point -- the regression "
        "cannot be fixed silently."
    ),
)
def test_a_comment_only_edit_should_not_brick_the_store(tmp_path: Path) -> None:
    """The behaviour the product SHOULD have, asserted so the fix has a target.

    Everything else in this module characterises the deadlock as it currently is.
    This one states the requirement instead: an edit that changes no schema must
    not cost an operator their evidence store. It is the assertion #169 has to
    flip.
    """
    migrations_dir = tmp_path / "migrations"
    shipped = TestMigrationLedgerDeadlock._seed_migrations(migrations_dir)
    db_path = TestMigrationLedgerDeadlock._make_store(tmp_path, migrations_dir)

    # The minimal edit: reword one comment. No schema change of any kind.
    shipped.write_text(
        "-- reworded comment, identical schema below\n"
        + "".join(shipped.read_text(encoding="utf-8").splitlines(keepends=True)[1:]),
        encoding="utf-8",
    )

    conn = open_db(db_path, synchronous="FULL")
    try:
        apply_pending(conn, discover(migrations_dir))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 6b -- oracle self-hash deadlock
# ---------------------------------------------------------------------------


class TestOracleSelfHashDeadlock:
    """The same shape, in a different subsystem."""

    def test_oracle_hash_covers_its_own_module_bytes(self) -> None:
        """A comment edit in ``ingest.py`` changes the pinned oracle hash."""
        from skill_harness.subject import ingest as ingest_module

        source = Path(ingest_module.__file__).read_text(encoding="utf-8")
        assert "Path(__file__).read_bytes()" in source, (
            "the oracle hash no longer covers raw module bytes; this deadlock's "
            "trigger condition has changed"
        )

    def test_metric_versions_is_append_only(self, tmp_path: Path) -> None:
        """Safeguard B for 6b: the stored oracle hash cannot be corrected."""
        conn = open_evidence(tmp_path / "evidence.db")
        try:
            triggers = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND tbl_name='metric_versions'"
                ).fetchall()
            }
            assert any("no_update" in t for t in triggers), (
                f"metric_versions lost its BEFORE UPDATE trigger: {triggers}"
            )
            assert any("no_delete" in t for t in triggers), (
                f"metric_versions lost its BEFORE DELETE trigger: {triggers}"
            )
        finally:
            conn.close()

    def test_the_named_escape_mints_a_new_measurement_identity(self) -> None:
        """The documented workaround forks the measurement rather than repairing it.

        Bumping ``ORACLE_METRIC_VERSION`` clears the refusal by declaring a new
        metric identity, so evidence recorded before and after the bump are no
        longer the same measurement. Pinned because it is easy to mistake for a fix.
        """
        from skill_harness.subject import ingest as ingest_module

        assert hasattr(ingest_module, "ORACLE_METRIC_VERSION"), (
            "ORACLE_METRIC_VERSION is gone; 6b's escape hatch has changed shape"
        )


# ---------------------------------------------------------------------------
# The invariant the state machine has to model
# ---------------------------------------------------------------------------


def test_runs_is_not_purely_append_only(tmp_path: Path) -> None:
    """``runs`` permits exactly one ``completed_at`` transition.

    The store's own docstring says "append-only" without qualification. It is not
    quite true, and a stateful machine written against the docstring rather than
    against the schema would report a false violation the first time a run
    completes. Pinned here so the exception is discoverable from the tests.
    """
    conn = open_evidence(tmp_path / "evidence.db")
    try:
        trigger_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='runs'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert any("no_delete" in name for name in trigger_names), (
        f"runs lost its delete guard: {trigger_names}"
    )
    assert not any(name.endswith("_no_update") for name in trigger_names), (
        "runs now carries a blanket no_update trigger; the single-shot completed_at "
        f"transition has been removed and the state machine must change: {trigger_names}"
    )


def test_every_evidence_table_carries_both_append_only_triggers(tmp_path: Path) -> None:
    """No evidence table may opt out of append-only by omission.

    Append-only is enforced per table, by hand, in whichever migration created that
    table. Nothing checks that a new table remembered its triggers, and the existing
    property suite enumerates nine tables by name rather than reading the schema. A
    table added tomorrow without its triggers would be silently mutable inside the
    append-only store; this test is the structural check that closes that gap.

    ``runs`` is the one sanctioned carve-out (see the test above) and is asserted
    there instead.
    """
    single_shot_carve_outs = {"runs"}

    conn = open_evidence(tmp_path / "evidence.db")
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        triggers_by_table: dict[str, set[str]] = {}
        for name, tbl in conn.execute(
            "SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'"
        ).fetchall():
            triggers_by_table.setdefault(tbl, set()).add(name)
    finally:
        conn.close()

    missing: dict[str, list[str]] = {}
    for table in sorted(tables - single_shot_carve_outs):
        names = triggers_by_table.get(table, set())
        gaps = []
        if not any("no_update" in n for n in names):
            gaps.append("BEFORE UPDATE")
        if not any("no_delete" in n for n in names):
            gaps.append("BEFORE DELETE")
        if gaps:
            missing[table] = gaps

    assert missing == {}, (
        "evidence tables are missing append-only triggers, so they are silently "
        f"mutable inside an append-only store: {missing}"
    )
