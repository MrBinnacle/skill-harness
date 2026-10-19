-- #209 -- repair bookkeeping for store-bricking deadlock instance 6b.
--
-- The deadlock: _oracle_implementation_hash() hashes the oracle module's raw
-- bytes (safeguard A) and the registered hash lives in append-only
-- metric_versions (safeguard B). A comment-only edit to the module therefore
-- refused every further verdict under the registered measurement identity, and
-- the row that would clear the refusal could not be corrected.
--
-- Both safeguards are kept exactly as they are. What is added is a SECOND
-- question -- "did the behaviour change?" -- answered by an AST-shape identity
-- digest, plus an APPENDED compensating record when the answer is no. Nothing in
-- metric_versions is ever rewritten or deleted.
--
-- DELIVERY NOTE, and it differs from 6a deliberately. #169's bookkeeping had to
-- be runner-owned (CREATE TABLE IF NOT EXISTS inside apply_pending) because its
-- reproduction tests build synthetic migration directories containing only their
-- own 0001_initial.sql, so a table shipped as a migration would not have existed
-- there. That constraint does not apply here: 6b's tests open the real evidence
-- chain through open_evidence(), so a numbered migration is both available and
-- the idiomatic way to add a table in this repo. Adding a NEW migration file is
-- also not the trigger condition for either deadlock -- EDITING a shipped one is.

-- Which AST identity digest was recorded for a given (metric_id, version, raw
-- hash). Written at registration and backfilled on a successful raw match, which
-- is the one moment the module on disk provably IS the registered one.
CREATE TABLE metric_semantic_digests (
    metric_id           TEXT NOT NULL,
    version             TEXT NOT NULL,
    implementation_hash TEXT NOT NULL,          -- the RAW digest this row describes
    semantic_digest     TEXT NOT NULL,          -- AST-shape identity digest
    -- A digest is only comparable against digests from the same algorithm. Stored
    -- per row rather than assumed globally so that a future algorithm change
    -- cannot silently compare across versions: a mismatch is a typed refusal.
    digest_algo_version TEXT NOT NULL,
    recorded_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (metric_id, version, implementation_hash)
);
CREATE TRIGGER metric_semantic_digests_no_update BEFORE UPDATE ON metric_semantic_digests
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: metric_semantic_digests'); END;
CREATE TRIGGER metric_semantic_digests_no_delete BEFORE DELETE ON metric_semantic_digests
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: metric_semantic_digests'); END;

-- The compensating correction. Appended, never an in-place fix: the superseded
-- hash stays on the record so the edit remains auditable rather than being
-- erased by its own repair.
CREATE TABLE metric_implementation_restamps (
    -- Declared INTEGER PRIMARY KEY, not left to the implicit rowid, because
    -- "latest restamp wins" resolves by this column. An explicit key is written
    -- out by .dump and survives dump/restore/VACUUM; an implicit rowid does not.
    -- Ordering by recorded_at instead would tie at millisecond resolution, and
    -- the E3 ban-timestamp-final-order-by hook exists for that hazard.
    restamp_id          INTEGER PRIMARY KEY,
    metric_id           TEXT NOT NULL,
    version             TEXT NOT NULL,
    superseded_hash     TEXT NOT NULL,          -- the raw digest that was in force
    implementation_hash TEXT NOT NULL,          -- the raw digest now in force
    semantic_digest     TEXT NOT NULL,          -- unchanged across the restamp
    digest_algo_version TEXT NOT NULL,
    reason              TEXT NOT NULL,
    recorded_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TRIGGER metric_implementation_restamps_no_update
    BEFORE UPDATE ON metric_implementation_restamps
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: metric_implementation_restamps'); END;
CREATE TRIGGER metric_implementation_restamps_no_delete
    BEFORE DELETE ON metric_implementation_restamps
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: metric_implementation_restamps'); END;
