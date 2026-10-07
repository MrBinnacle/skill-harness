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

**6a is FIXED by #169; 6b is not.** For 6a these tests now do two jobs: the ones
that characterise the deadlock's trigger condition (the raw digest moves under a
comment edit, the ledger row cannot be corrected) still hold and still matter --
they are what the repair had to work around rather than remove -- while the
requirement test and its companions pin the repaired behaviour. For 6b they
characterise a deadlock that still stands.

The repair, stated once: a SEMANTIC digest (comments stripped, whitespace
collapsed) is recorded alongside the raw one, and a mismatch provably confined to
commentary is cleared by APPENDING a compensating restamp record. Neither
safeguard is weakened -- a real schema change still locks the store, and the
ledger row is never rewritten.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from skill_harness.storage import migrations as migrations_module
from skill_harness.storage.errors import MigrationTamperedError
from skill_harness.storage.migrations import (
    _semantic_sha256,
    _semantic_sql,
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

    def test_schema_edit_locks_an_existing_store(self, tmp_path: Path) -> None:
        """Safeguard A: the store refuses to open after a real schema change.

        Re-pointed by #169. This test previously asserted that a COMMENT-ONLY edit
        raises, which is the direct negation of the requirement the fix had to
        satisfy -- the two could not both hold. Deleting it instead of re-pointing
        it would have silently removed the only behavioural coverage of safeguard
        A, so the assertion is kept and aimed at an edit that must still lock the
        store: an added column. If this ever stops raising, the semantic digest
        has stopped distinguishing schema from commentary and the repair has
        become a bypass.
        """
        migrations_dir = tmp_path / "migrations"
        shipped = self._seed_migrations(migrations_dir)
        db_path = self._make_store(tmp_path, migrations_dir)

        # The store opens cleanly before the edit.
        conn = open_db(db_path, synchronous="FULL")
        try:
            apply_pending(conn, discover(migrations_dir))
        finally:
            conn.close()

        original = shipped.read_text(encoding="utf-8")
        changed = original.replace(
            "CREATE TABLE thing (id INTEGER PRIMARY KEY);",
            "CREATE TABLE thing (id INTEGER PRIMARY KEY, smuggled TEXT);",
        )
        assert changed != original, "the schema edit did not apply to the fixture"
        shipped.write_text(changed, encoding="utf-8")

        conn = open_db(db_path, synchronous="FULL")
        try:
            with pytest.raises(MigrationTamperedError, match="0001_initial"):
                apply_pending(conn, discover(migrations_dir))
        finally:
            conn.close()

    def test_a_comment_only_edit_is_repaired_rather_than_refused(self, tmp_path: Path) -> None:
        """The repair is a restamp, and it is idempotent and auditable.

        Companion to the requirement test at module level, which only asserts that
        the open succeeds. This one pins HOW: exactly one compensating row is
        appended, it names the digest it supersedes, and a second open appends
        nothing because the restamped digest is now the one in force.
        """
        migrations_dir = tmp_path / "migrations"
        shipped = self._seed_migrations(migrations_dir)
        db_path = self._make_store(tmp_path, migrations_dir)
        before = discover(migrations_dir)[0].sha256

        shipped.write_text(
            "-- reworded comment, identical schema below\n"
            + "".join(shipped.read_text(encoding="utf-8").splitlines(keepends=True)[1:]),
            encoding="utf-8",
        )
        after = discover(migrations_dir)[0].sha256

        conn = open_db(db_path, synchronous="FULL")
        try:
            apply_pending(conn, discover(migrations_dir))
            rows = conn.execute(
                "SELECT migration_id, superseded_sha256, file_sha256, reason "
                "FROM migration_sha_restamps ORDER BY restamp_id"
            ).fetchall()
            assert len(rows) == 1, f"expected exactly one restamp, got {rows}"
            assert rows[0][0] == "0001_initial"
            assert rows[0][1] == before, "the restamp does not name the digest it supersedes"
            assert rows[0][2] == after
            assert "comments or whitespace only" in rows[0][3]

            # Idempotent: the restamped digest is now in force, so there is no
            # mismatch left to compensate for.
            apply_pending(conn, discover(migrations_dir))
            assert conn.execute("SELECT COUNT(*) FROM migration_sha_restamps").fetchone()[0] == 1, (
                "a second open appended a duplicate restamp"
            )

            # The ledger row itself was never touched -- the correction is an
            # appended record, not a rewrite.
            ledger = conn.execute(
                "SELECT file_sha256 FROM schema_migrations WHERE migration_id = ?",
                ("0001_initial",),
            ).fetchone()
            assert ledger[0] == before, "the original ledger row was modified"
        finally:
            conn.close()

    def test_a_healthy_store_opens_without_writing(self, tmp_path: Path) -> None:
        """The repair must not turn every open into a write.

        Before #169 a fully-migrated store was opened with SELECTs only. Bookkeeping
        that ran unconditionally would take a write lock on every open -- contention
        between concurrent openers, and outright failure on read-only media. Asserted
        the only way that cannot be faked: forbid writes at the connection level and
        require the open to succeed anyway.
        """
        migrations_dir = tmp_path / "migrations"
        self._seed_migrations(migrations_dir)
        db_path = self._make_store(tmp_path, migrations_dir)

        conn = open_db(db_path, synchronous="FULL")
        try:
            conn.execute("PRAGMA query_only = ON")
            apply_pending(conn, discover(migrations_dir))
        finally:
            conn.close()

    def test_a_store_predating_the_repair_is_healed_on_first_open(self, tmp_path: Path) -> None:
        """The backfill is what actually saves stores created before the fix.

        Simulated by deleting the semantic digests a pre-#169 store would never
        have had, then opening cleanly BEFORE any edit. That open must re-record
        them, so the subsequent comment edit is repairable rather than terminal.
        Without the backfill this store would be bricked by the same edit the test
        above repairs.
        """
        migrations_dir = tmp_path / "migrations"
        shipped = self._seed_migrations(migrations_dir)
        db_path = self._make_store(tmp_path, migrations_dir)

        # Regress the store to its pre-repair shape. The bookkeeping table is
        # append-only, so its own trigger has to be dropped to forge this state --
        # which is itself evidence that nothing in the product can reach these rows.
        conn = open_db(db_path, synchronous="FULL")
        try:
            conn.execute("DROP TRIGGER migration_semantic_digests_no_delete")
            conn.execute("DELETE FROM migration_semantic_digests")
            conn.execute("DROP TABLE migration_sha_restamps")
        finally:
            conn.close()

        # The healing open: no edit yet, raw digest still matches.
        conn = open_db(db_path, synchronous="FULL")
        try:
            apply_pending(conn, discover(migrations_dir))
            assert (
                conn.execute("SELECT COUNT(*) FROM migration_semantic_digests").fetchone()[0] == 1
            ), "the clean open did not backfill a semantic digest"
        finally:
            conn.close()

        shipped.write_text(
            "-- reworded comment, identical schema below\n"
            + "".join(shipped.read_text(encoding="utf-8").splitlines(keepends=True)[1:]),
            encoding="utf-8",
        )

        conn = open_db(db_path, synchronous="FULL")
        try:
            apply_pending(conn, discover(migrations_dir))  # healed, so it opens
        finally:
            conn.close()

    def test_an_already_bricked_store_is_still_refused(self, tmp_path: Path) -> None:
        """The repair is not retroactive, and that is deliberate.

        A store whose semantic digests were never recorded and which was edited
        before it could be healed has no evidence that the edit was harmless. The
        runner refuses rather than trusting the current file, because trusting it
        would mean accepting whatever is on disk now -- which is safeguard A
        deleted, not repaired. The named remedy is to restore the original bytes.
        """
        migrations_dir = tmp_path / "migrations"
        shipped = self._seed_migrations(migrations_dir)
        db_path = self._make_store(tmp_path, migrations_dir)
        original = shipped.read_text(encoding="utf-8")

        conn = open_db(db_path, synchronous="FULL")
        try:
            conn.execute("DROP TRIGGER migration_semantic_digests_no_delete")
            conn.execute("DELETE FROM migration_semantic_digests")
        finally:
            conn.close()

        shipped.write_text(
            "-- reworded comment, identical schema below\n"
            + "".join(original.splitlines(keepends=True)[1:]),
            encoding="utf-8",
        )

        conn = open_db(db_path, synchronous="FULL")
        try:
            with pytest.raises(MigrationTamperedError, match="predates the #169 repair"):
                apply_pending(conn, discover(migrations_dir))
        finally:
            conn.close()

        # ...and the documented remedy works: restore the bytes, reopen.
        shipped.write_text(original, encoding="utf-8")
        conn = open_db(db_path, synchronous="FULL")
        try:
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
        """No code path rewrites or removes a ledger row -- still true after #169.

        Written as an assertion about absence, with the stated expectation that
        #169's fix would make it fail. It does not, and that is a better outcome
        than the one anticipated: the repair appends a compensating record to a
        separate table instead of reaching into the ledger, so the append-only
        guarantee on ``schema_migrations`` is never relaxed. Kept, because it still
        guards the thing worth guarding -- if a mutating path ever appears here,
        safeguard B has been traded away rather than worked around.
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

        Re-pointed by #169 for the same reason as ``test_schema_edit_locks_an
        _existing_store``: this test needs a genuinely bricked store to reason
        about, and a comment-only edit no longer produces one. A real schema change
        does, so the read-only escape hatch still has something to escape from.
        """
        migrations_dir = tmp_path / "migrations"
        shipped = self._seed_migrations(migrations_dir)
        db_path = self._make_store(tmp_path, migrations_dir)

        shipped.write_text(
            shipped.read_text(encoding="utf-8").replace(
                "CREATE TABLE thing (id INTEGER PRIMARY KEY);",
                "CREATE TABLE thing (id INTEGER PRIMARY KEY, smuggled TEXT);",
            ),
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


def test_a_comment_only_edit_should_not_brick_the_store(tmp_path: Path) -> None:
    """The requirement, now met: a comment-only edit must not cost a store.

    Was a ``strict=True`` xfail while the deadlock stood, so that the fix could
    not land silently -- an XPASS would have failed the suite. #169's repair makes
    it pass, so the marker is gone and this is a plain regression test. The name is
    deliberately unchanged: it is cited by the finding, the ticket and the PR, and
    renaming it would break the trail from the reproduction to the fix.
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
# The semantic digest itself -- the discriminator the whole repair rests on
# ---------------------------------------------------------------------------


class TestSemanticDigest:
    """If this normalisation is wrong, the repair is either a bypass or useless."""

    def test_comment_and_whitespace_edits_normalise_together(self) -> None:
        base = "-- header\nCREATE TABLE t (id INTEGER);\n"
        variants = [
            "-- a completely different header\nCREATE TABLE t (id INTEGER);\n",
            "CREATE TABLE t (id INTEGER);\n",  # comment deleted outright
            "CREATE   TABLE t (id   INTEGER);\n",  # whitespace collapsed
            "-- header\nCREATE TABLE t (id INTEGER); -- trailing note\n",
        ]
        expected = _semantic_sha256(base)
        for variant in variants:
            assert _semantic_sha256(variant) == expected, (
                f"variant should be semantically identical to base: {variant!r}"
            )

    def test_a_dashdash_inside_a_string_literal_is_not_a_comment(self) -> None:
        """The reason this is a scanner and not a regex.

        Not hypothetical in this schema: the append-only triggers raise messages
        like ``'append_only_violation: schema_migrations'``, and a literal is free
        to contain ``--``. A regex stripping from ``--`` to end-of-line would eat
        the rest of a trigger body, making two genuinely different triggers
        normalise to the same digest -- which would authorise a restamp between
        them. That is the failure mode that turns the repair into a bypass.
        """
        keeps_literal = "SELECT RAISE(ABORT, 'boom -- not a comment');\n"
        assert "-- not a comment" in _semantic_sql(keeps_literal)

        differing = "SELECT RAISE(ABORT, 'boom -- also not a comment');\n"
        assert _semantic_sha256(keeps_literal) != _semantic_sha256(differing), (
            "two different string literals collapsed to one semantic digest"
        )

    def test_an_escaped_quote_does_not_end_the_literal(self) -> None:
        """``''`` is an escaped quote in SQL, not a terminator.

        Mis-handling it flips the scanner's in-string state for the rest of the
        file, so every subsequent comment would be preserved and every subsequent
        literal stripped -- silently, with no error.
        """
        sql = "SELECT RAISE(ABORT, 'it''s -- fine'); -- real comment\n"
        normalised = _semantic_sql(sql)
        assert "it''s -- fine" in normalised
        assert "real comment" not in normalised, (
            f"the scanner lost its place after an escaped quote: {normalised!r}"
        )

    @pytest.mark.parametrize("which", ["evidence", "runtime"])
    def test_the_real_shipped_chain_still_applies_after_normalisation(self, which: str) -> None:
        """The end-to-end guarantee, against the REAL migrations rather than fixtures.

        If the scanner ever ate a string literal or truncated a trigger body, the
        normalised text would either fail to execute or build a different schema.
        Comparing the resulting ``sqlite_master`` object identities is the check
        that cannot be satisfied by accident. ``sqlite_master.sql`` itself is
        excluded from the comparison because SQLite stores the original text, which
        differs in exactly the commentary this normalisation removes.

        Run against both chains: the runtime DB carries the same ledger triggers as
        evidence (migration ``0002_schema_migrations_triggers.sql``), so it is
        subject to the same deadlock and the same repair.
        """
        directory = (
            migrations_module.EVIDENCE_MIGRATIONS_DIR
            if which == "evidence"
            else migrations_module.RUNTIME_MIGRATIONS_DIR
        )
        chain = discover(directory)
        assert chain, f"no {which} migrations discovered"

        def objects(scripts: list[str]) -> set[tuple[str, str]]:
            # open_db, not raw sqlite3.connect: E1 / A23 §3 bans the raw call
            # outside migrations.py, and test_structural_bans enforces it.
            conn = open_db(":memory:", synchronous="FULL")
            try:
                for script in scripts:
                    conn.executescript(script)
                return {
                    (row[0], row[1])
                    for row in conn.execute("SELECT type, name FROM sqlite_master").fetchall()
                }
            finally:
                conn.close()

        raw = objects([m.sql for m in chain])
        normalised = objects([_semantic_sql(m.sql) for m in chain])
        assert normalised == raw, (
            "stripping commentary changed the schema the chain builds: "
            f"only-raw={sorted(raw - normalised)} only-normalised={sorted(normalised - raw)}"
        )

    def test_every_shipped_migration_has_a_distinct_semantic_digest(self) -> None:
        """A collision would make two real files interchangeable to the repair.

        Two migrations sharing a semantic digest would let the runner accept a swap
        between them as a comment-only edit. Checked across both chains together,
        since the digest carries no directory scoping.
        """
        chain = discover(migrations_module.EVIDENCE_MIGRATIONS_DIR) + discover(
            migrations_module.RUNTIME_MIGRATIONS_DIR
        )
        by_digest: dict[str, list[str]] = {}
        for m in chain:
            by_digest.setdefault(m.semantic_sha256, []).append(m.migration_id)
        collisions = {d: ids for d, ids in by_digest.items() if len(ids) > 1}
        assert collisions == {}, f"shipped migrations share a semantic digest: {collisions}"

    def test_any_schema_difference_survives_normalisation(self) -> None:
        pairs = [
            ("CREATE TABLE t (id INTEGER);\n", "CREATE TABLE t (id TEXT);\n"),
            ("CREATE TABLE t (id INTEGER);\n", "CREATE TABLE u (id INTEGER);\n"),
            ("CREATE TABLE t (id INTEGER);\n", "CREATE TABLE t (id INTEGER, x TEXT);\n"),
        ]
        for left, right in pairs:
            assert _semantic_sha256(left) != _semantic_sha256(right), (
                f"a real schema difference normalised away: {left!r} vs {right!r}"
            )

    def test_whitespace_inside_a_literal_is_not_collapsed(self) -> None:
        """The collision that made the first draft of this repair a bypass.

        Whitespace is collapsed OUTSIDE quoted spans and preserved byte-for-byte
        inside them. A whole-file collapse (the obvious implementation, and the one
        this repair originally shipped in draft) equated these two CHECK
        constraints, which admit different values. The runner would then have read a
        real constraint change as comment-only and restamped it -- safeguard A
        deleted, not repaired.
        """
        one_space = "CREATE TABLE t (k TEXT CHECK (k IN ('a b')));\n"
        two_spaces = "CREATE TABLE t (k TEXT CHECK (k IN ('a  b')));\n"
        assert _semantic_sha256(one_space) != _semantic_sha256(two_spaces), (
            "whitespace inside a string literal was collapsed away"
        )

    def test_whitespace_around_a_literal_is_still_collapsed(self) -> None:
        """The other half: reformatting outside literals must stay repairable.

        Preserving literals byte-for-byte must not make the normalisation so strict
        that ordinary reformatting bricks the store -- that would trade one
        deadlock for a narrower one.
        """
        tight = "CREATE TABLE t (k TEXT DEFAULT ('x'));\n"
        loose = "CREATE   TABLE t (k TEXT DEFAULT (   'x'   ));\n"
        assert _semantic_sha256(tight) == _semantic_sha256(loose), (
            "whitespace outside literals is no longer normalised"
        )

    def test_an_aliased_literal_is_not_an_escaped_quote(self) -> None:
        """A pure-whitespace gap between two quoted spans carries meaning.

        SQLite reads ``SELECT 'a' 'b'`` as ``'a'`` aliased to ``b``. Collapsing that
        gap to nothing would produce ``'a''b'`` -- the single literal ``a'b`` -- so
        two different statements would share one digest.
        """
        aliased = "SELECT 'a' 'b';\n"
        escaped = "SELECT 'a''b';\n"
        assert _semantic_sha256(aliased) != _semantic_sha256(escaped), (
            "an aliased literal collapsed into an escaped-quote literal"
        )

    def test_a_dashdash_inside_a_quoted_identifier_is_not_a_comment(self) -> None:
        """Double quotes and backticks quote identifiers in SQLite, and also escape by doubling.

        The shipped migrations happen to use neither in live SQL today -- both
        appear only inside ``--`` comments as prose punctuation -- so this is
        forward cover: a future migration quoting an identifier must not have half
        of it treated as commentary.
        """
        for quote in ('"', "`"):
            kept = f"CREATE TABLE {quote}odd -- name{quote} (id INTEGER);\n"
            other = f"CREATE TABLE {quote}odd -- other{quote} (id INTEGER);\n"
            assert "-- name" in _semantic_sql(kept), (
                f"{quote} did not protect an identifier from comment stripping"
            )
            assert _semantic_sha256(kept) != _semantic_sha256(other), (
                f"two different {quote}-quoted identifiers shared a digest"
            )

    def test_block_comments_are_stripped_too(self) -> None:
        """``/* ... */`` is a comment in SQLite, so an edit inside one is repairable.

        No shipped migration uses block comments today (checked across both
        ``migrations_sql`` directories), so this is forward cover as well. Handling
        them makes "comments are stripped" true rather than "line comments are
        stripped"; leaving them unhandled would have been safe but would refuse a
        genuinely harmless edit.
        """
        base = "/* header */ CREATE TABLE t (id INTEGER);\n"
        reworded = "/* an entirely different header */ CREATE TABLE t (id INTEGER);\n"
        assert _semantic_sha256(base) == _semantic_sha256(reworded)
        assert _semantic_sql(base) == "CREATE TABLE t (id INTEGER);"

        # ...but a /* inside a literal is data, not a comment opener.
        literal = "SELECT RAISE(ABORT, 'not /* a comment */ really');\n"
        assert "/* a comment */" in _semantic_sql(literal)


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
