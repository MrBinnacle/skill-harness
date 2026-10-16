"""StorageContext: dual-DB connection lifecycle manager.

Use case: CLI commands instantiate ``with StorageContext(evidence_path, runtime_path) as ctx:``
and call repository functions passing ``ctx.evidence_conn`` / ``ctx.runtime_conn``.

This isolates connection open/close from business logic and ensures both
connections are closed even when an exception propagates from the with-body.
"""

from __future__ import annotations

import contextlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from skill_harness.storage.migrations import open_evidence, open_runtime


@dataclass
class StorageContext:
    """Context manager that opens both evidence and runtime DB connections.

    Usage::

        with StorageContext(evidence_path, runtime_path) as ctx:
            skills_repo.insert_skill(ctx.evidence_conn, skill)
            budget_repo.insert_run_budget(ctx.runtime_conn, budget)

    ``evidence_conn`` and ``runtime_conn`` are only valid inside the ``with`` block.
    Both connections are closed in ``__exit__`` regardless of whether the body
    raised.  ``contextlib.suppress(sqlite3.Error)`` around each close prevents a
    close-error from masking a body exception.
    """

    evidence_path: Path | str
    runtime_path: Path | str
    evidence_conn: sqlite3.Connection = field(init=False)
    runtime_conn: sqlite3.Connection = field(init=False)

    def __enter__(self) -> StorageContext:
        self.evidence_conn = open_evidence(self.evidence_path)
        try:
            self.runtime_conn = open_runtime(self.runtime_path)
        except BaseException:
            # If runtime open fails, close the already-opened evidence connection.
            with contextlib.suppress(sqlite3.Error):
                self.evidence_conn.close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        with contextlib.suppress(sqlite3.Error):
            self.evidence_conn.close()
        with contextlib.suppress(sqlite3.Error):
            self.runtime_conn.close()
