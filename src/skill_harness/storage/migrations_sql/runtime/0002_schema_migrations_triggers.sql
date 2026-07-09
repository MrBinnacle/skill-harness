-- Phase 1.5 council finding A21 (RELIABILITY-F1 + TEST-ARCH-F4 + SECURITY-F4):
-- runtime.schema_migrations is a META table — a tamper-evidence ledger for
-- "which migrations did this DB get?" Its append-only nature is independent
-- of the runtime/evidence DOMAIN partition: silently mutable ledger rows let
-- a rollback (deliberate or accidental) erase its own footprint, defeating
-- the SHA-256 verification on subsequent open.
--
-- evidence.schema_migrations already has these triggers (migration 0001).
-- The runtime side was missing them in v0.0 — SCHEMA framed that as
-- intentional partition asymmetry; TEST-ARCH + SECURITY + RELIABILITY
-- framed the ledger as META, not DOMAIN. Council vote 3-vs-1 adopted META.

CREATE TRIGGER schema_migrations_no_update BEFORE UPDATE ON schema_migrations
    BEGIN
        SELECT RAISE(ABORT, 'append_only_violation: schema_migrations');
    END;

CREATE TRIGGER schema_migrations_no_delete BEFORE DELETE ON schema_migrations
    BEGIN
        SELECT RAISE(ABORT, 'append_only_violation: schema_migrations');
    END;
