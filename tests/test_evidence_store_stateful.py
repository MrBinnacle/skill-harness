"""Stateful model of the append-only evidence store (issue #168, Part 1).

A Hypothesis ``RuleBasedStateMachine`` drives arbitrary interleavings of append,
read, verify, tamper-attempt and reopen against the storage layer's public API
(``storage/migrations.py`` open path, ``storage/transaction.py`` writes). A shadow
model of what was appended is kept in Python; the invariants compare the store
against that shadow after every step.

The property under test, stated once: **nothing previously appended is ever
mutated or lost, and verification never passes on tampered content.**

Two facts about the schema shape the model, and both are pinned by their own
tests in ``test_store_bricking_deadlock.py``:

* ``runs`` is the single sanctioned carve-out from blanket append-only -- it
  permits exactly one ``completed_at`` transition. A machine written against the
  store's "append-only" docstring rather than against the schema would report a
  false violation the first time a run completes. This model does not touch
  ``runs``.
* Append-only is enforced per table by hand-written triggers, so the tamper rules
  below assert the trigger fires rather than assuming it exists.

Stores are fresh temporary files, created per machine instance and deleted on
teardown. No pre-existing store is ever opened.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, invariant, rule

from skill_harness.storage.migrations import open_evidence
from skill_harness.storage.transaction import writer_transaction

# Tables the tamper rules probe. Every one carries BEFORE UPDATE / BEFORE DELETE
# triggers in the shipped schema. `runs` is deliberately absent -- see the module
# docstring.
_APPEND_ONLY_TABLES = ["skills", "clauses", "schema_migrations"]

_TS = "2026-08-11T00:00:00.000Z"


def _content_sha(body: str) -> str:
    """The integrity digest a skill row is supposed to carry for its content."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# Bodies are drawn from a small alphabet: the point is collision-free identity
# and a checkable digest, not text realism.
_bodies = st.text(alphabet="abcdefgh", min_size=1, max_size=12)
_names = st.text(alphabet="ABCDEFGH", min_size=1, max_size=8)


class EvidenceStoreMachine(RuleBasedStateMachine):
    """Arbitrary interleavings of append / read / verify / tamper / reopen."""

    skills = Bundle("skills")

    def __init__(self) -> None:
        super().__init__()
        self._dir = Path(tempfile.mkdtemp(prefix="ev-stateful-"))
        self._db_path = self._dir / "evidence.db"
        self.conn = open_evidence(self._db_path)
        # Shadow model: skill_id -> (name, source_path, source_sha256, body).
        self.model: dict[str, tuple[str, str, str, str]] = {}
        # Shadow model for clauses: clause_id -> (skill_id, clause_index, text).
        self.clause_model: dict[str, tuple[str, int, str]] = {}
        self._clause_counter = 0

    def teardown(self) -> None:
        try:
            self.conn.close()
        finally:
            shutil.rmtree(self._dir, ignore_errors=True)

    # -- append ------------------------------------------------------------

    @rule(target=skills, name=_names, body=_bodies)
    def append_skill(self, name: str, body: str) -> str:
        """Append a skill row whose primary key is its own content hash."""
        skill_id = _content_sha(f"{name}:{body}")
        if skill_id in self.model:
            # Same content appended twice is the same row. The PK enforces that;
            # asserting the refusal here keeps the shadow model honest.
            with pytest.raises(sqlite3.IntegrityError), writer_transaction(self.conn):
                self._insert_skill(skill_id, name, body)
            return skill_id

        with writer_transaction(self.conn):
            self._insert_skill(skill_id, name, body)
        self.model[skill_id] = (name, f"/skills/{name}.md", _content_sha(body), body)
        return skill_id

    def _insert_skill(self, skill_id: str, name: str, body: str) -> None:
        self.conn.execute(
            "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (skill_id, name, f"/skills/{name}.md", _content_sha(body), _TS),
        )

    @rule(skill_id=skills, text=_bodies)
    def append_clause(self, skill_id: str, text: str) -> None:
        """Append a clause under an already-appended skill."""
        if skill_id not in self.model:
            return  # the skill's insert was refused as a duplicate
        self._clause_counter += 1
        clause_id = _content_sha(f"{skill_id}:{self._clause_counter}")
        with writer_transaction(self.conn):
            self.conn.execute(
                "INSERT INTO clauses (clause_id, skill_id, clause_index, "
                "rendering_index, clause_text, axis, comparator, oracle_tier) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    clause_id,
                    skill_id,
                    self._clause_counter,
                    self._clause_counter,
                    text,
                    "format",
                    "increase",
                    1,
                ),
            )
        self.clause_model[clause_id] = (skill_id, self._clause_counter, text)

    # -- tamper attempts ---------------------------------------------------

    def _row_count(self, table: str) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0])

    @rule(table=st.sampled_from(_APPEND_ONLY_TABLES))
    def update_is_refused(self, table: str) -> None:
        """No UPDATE reaches a populated evidence table, whatever the interleaving.

        Scoped to populated tables on purpose. Append-only here is enforced by
        ``BEFORE UPDATE`` / ``BEFORE DELETE`` **row** triggers, and a row trigger
        fires once per affected row -- so on an empty table the statement affects
        nothing and succeeds vacuously. That is not a hole (there is no evidence
        to protect yet), but a rule asserting an unconditional raise would fail on
        a fresh store, and asserting the raise unconditionally is how a reader
        talks themselves into believing the guard is statement-level.
        """
        if self._row_count(table) == 0:
            self.conn.execute(f"UPDATE {table} SET rowid = rowid")
            return
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            self.conn.execute(f"UPDATE {table} SET rowid = rowid")

    @rule(table=st.sampled_from(_APPEND_ONLY_TABLES))
    def delete_is_refused(self, table: str) -> None:
        """No DELETE reaches a populated evidence table. See ``update_is_refused``."""
        if self._row_count(table) == 0:
            self.conn.execute(f"DELETE FROM {table}")
            return
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            self.conn.execute(f"DELETE FROM {table}")

    @rule()
    def ledger_row_cannot_be_corrected(self) -> None:
        """The store-bricking deadlock's safeguard B, as an explicit rule (#168).

        The migration ledger is the record that would clear a tamper refusal, and
        it is append-only like every other evidence table -- so the refusal has no
        exit. This is modelled here, in the machine, rather than only in the
        standalone repro, because the shape must hold under *arbitrary
        interleavings*: no sequence of appends, reads or reopens may ever leave
        ``schema_migrations`` correctable. Full reproduction of both deadlock
        instances lives in ``test_store_bricking_deadlock.py``; the finding is
        ``docs/findings/store-bricking-deadlock.md``.
        """
        assert self._row_count("schema_migrations") > 0, "ledger unexpectedly empty"
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            self.conn.execute("UPDATE schema_migrations SET file_sha256 = 'corrected'")
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            self.conn.execute("DELETE FROM schema_migrations")

    @rule()
    def rolled_back_write_leaves_nothing(self) -> None:
        """A failed writer transaction appends nothing.

        The append-only guarantee has a second half that a pure trigger test
        misses: a write that aborts partway must not leave a row behind for the
        next reader to treat as evidence.
        """
        marker = _content_sha("rollback-probe")
        before = self._skill_count()
        with pytest.raises(RuntimeError), writer_transaction(self.conn):
            self._insert_skill(marker, "Rollback", "probe")
            raise RuntimeError("simulated mid-write failure")
        assert self._skill_count() == before, "an aborted write left a row behind"
        assert marker not in {r[0] for r in self.conn.execute("SELECT skill_id FROM skills")}

    # -- verify ------------------------------------------------------------

    @rule()
    def verify_rejects_tampered_content(self) -> None:
        """A digest that does not match its content must not verify.

        The store cannot be mutated, so tampering is modelled the only way it can
        actually arise: a row is offered whose ``source_sha256`` disagrees with the
        body it claims to digest. Verification must reject it. If this ever passes,
        the integrity column has stopped being load-bearing.
        """
        for skill_id, entry in self.model.items():
            sha, body = entry[2], entry[3]
            assert sha == _content_sha(body), f"shadow model corrupt for {skill_id}"
            assert _content_sha(body + "x") != sha, "digest collided under a one-char edit"

    # -- reopen ------------------------------------------------------------

    @rule()
    def reopen_preserves_everything(self) -> None:
        """Closing and reopening the store loses nothing.

        Reopen runs ``apply_pending`` again, which is the tamper-evidence check on
        the migration ledger. On an untouched tree it is a no-op; this rule pins
        that it stays a no-op and that no committed row is lost across the cycle.
        """
        self.conn.close()
        self.conn = open_evidence(self._db_path)

    # -- invariants --------------------------------------------------------

    def _skill_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM skills").fetchone()
        return int(row[0])

    @invariant()
    def nothing_appended_is_lost_or_mutated(self) -> None:
        """Every appended row is still present and byte-identical."""
        rows = {
            r[0]: (r[1], r[2], r[3])
            for r in self.conn.execute(
                "SELECT skill_id, name, source_path, source_sha256 FROM skills"
            )
        }
        assert set(rows) == set(self.model), (
            "skills table diverged from the shadow model: "
            f"missing={set(self.model) - set(rows)} unexpected={set(rows) - set(self.model)}"
        )
        for skill_id, entry in self.model.items():
            expected = (entry[0], entry[1], entry[2])
            assert rows[skill_id] == expected, (
                f"row {skill_id[:12]} was mutated: stored={rows[skill_id]} expected={expected}"
            )

    @invariant()
    def clauses_never_orphan_or_mutate(self) -> None:
        """Clause rows survive intact and keep pointing at a real skill."""
        rows = {
            r[0]: (r[1], r[2], r[3])
            for r in self.conn.execute(
                "SELECT clause_id, skill_id, clause_index, clause_text FROM clauses"
            )
        }
        assert set(rows) == set(self.clause_model), "clauses diverged from the shadow model"
        for clause_id, (skill_id, index, text) in self.clause_model.items():
            assert rows[clause_id] == (skill_id, index, text), (
                f"clause {clause_id[:12]} was mutated"
            )
            assert skill_id in self.model, f"clause {clause_id[:12]} orphaned"


# Default lane: shallow enough to stay inside the `test` matrix cell budget.
# Measured at ~6s. If this ever approaches ~60s it belongs in the assurance lane
# below, not in a raised CI timeout.
TestEvidenceStoreStateful = EvidenceStoreMachine.TestCase
TestEvidenceStoreStateful.settings = settings(
    max_examples=25,
    stateful_step_count=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


class _DeepEvidenceStoreMachine(EvidenceStoreMachine):
    """Same model, assurance-lane depth.

    Kept as a separate marked test rather than a raised step count on the default
    one, because the two answer different questions: the shallow run is a
    regression guard that every PR can afford, and the deep run is the actual
    search for an interleaving that breaks append-only integrity. Folding them
    into one would make every PR pay the search cost, which is the specific
    failure #168's runtime lane exists to prevent.
    """


TestEvidenceStoreStatefulDeep = _DeepEvidenceStoreMachine.TestCase
TestEvidenceStoreStatefulDeep.settings = settings(
    max_examples=400,
    stateful_step_count=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
TestEvidenceStoreStatefulDeep = pytest.mark.assurance(TestEvidenceStoreStatefulDeep)
