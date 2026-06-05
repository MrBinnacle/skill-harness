"""Skill Harness storage layer.

Two-database design (per ADR in docs/COUNCIL_FINDINGS.md):

* ``evidence.db`` — append-only. Schema lives in ``migrations/evidence/``.
  Every evidence table carries BEFORE UPDATE/DELETE triggers that
  ``RAISE(ABORT, 'append_only_violation: <table>')``.
* ``runtime.db`` — mutable. In-flight run progress, cost ledger, current
  calibration pointer. Schema lives in ``migrations/runtime/``.

Entry points:
  - ``open_evidence`` / ``open_runtime`` — open a DB connection with all
    migrations applied and the correct ``synchronous`` PRAGMA set.
  - ``StorageContext`` — context manager that opens both connections and
    closes them on exit; use in CLI commands.
  - ``writer_transaction`` — context manager for ``BEGIN IMMEDIATE`` /
    ``COMMIT`` / ``ROLLBACK`` on a single connection.
  - ``write_verdict_with_cost_entry``, ``write_run_start_with_budget``,
    ``write_calibration_event_with_pointer`` — dual-DB write helpers per A25.

Single-writer mechanism (A26): SQLite ``BEGIN IMMEDIATE`` + 5-second
``busy_timeout`` (already set in ``open_db()``) is THE writer-exclusion
mechanism for v0.1. No in-process ``queue.Queue`` + writer thread. Application
discipline: writes from a single thread per DB connection. ``threading.Lock``
per ``Connection`` MAY be adopted as belt-and-braces ONLY as a wrapper around
``BEGIN IMMEDIATE`` (not as a queue).
"""

from skill_harness.storage.context import StorageContext
from skill_harness.storage.dual_write import (
    write_calibration_event_with_pointer,
    write_run_start_with_budget,
    write_verdict_with_cost_entry,
)
from skill_harness.storage.transaction import writer_transaction

__all__ = [
    "StorageContext",
    "write_calibration_event_with_pointer",
    "write_run_start_with_budget",
    "write_verdict_with_cost_entry",
    "writer_transaction",
]
