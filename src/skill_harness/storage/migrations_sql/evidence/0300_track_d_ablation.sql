-- Track D migration — ablation runner schema extensions.
-- Adopted findings: A39 (operator provenance), A40 (sample idempotency), A41 (cost re-derivable).
-- Track D range: 0300-0399 (per A30 range guard).
-- Depends on: 0001_initial.sql (samples + oracle_verdicts tables + append-only triggers).
--
-- Summary of additions:
--
--   samples.sample_index INTEGER NOT NULL (A40)
--   + UNIQUE(run_id, clause_id, condition, sample_index) — idempotency key for resume.
--     Resume = set-difference of existing tuples vs the frozen plan in runs.config_json.
--     Double-INSERT on the same tuple raises UNIQUE constraint → prevents double-counting
--     w/n in the Beta-Binomial under append-only (crash-resume safety, A40).
--
--   Per-call cost columns on samples (A41):
--     input_tokens, cache_read_input_tokens, cache_creation_input_tokens, output_tokens, usd
--   Written from the actual response usage block inside the evidence transaction
--   (synchronous=FULL) so spend is durable at power loss and re-derivable.
--   cost_ledger is thereafter a projection; a reconciler back-fills any run whose
--   sum(evidence.usd) ≠ sum(cost_ledger.usd).
--
--   oracle_verdicts.ablation_operator_id TEXT (A39)
--   oracle_verdicts.ablation_operator_hash TEXT (A39)
--   Operator provenance stamped at write-time — mirrors metric_versions discipline.
--
-- Trigger coverage:
--   The existing BEFORE UPDATE / BEFORE DELETE triggers on samples and oracle_verdicts
--   (from 0001_initial.sql) use whole-row RAISE(ABORT) — they fire on ANY UPDATE/DELETE
--   regardless of which columns are affected. New columns are therefore already covered
--   by the existing triggers. No trigger changes required.
--   A22 synchronous=FULL is a connection-level PRAGMA set by open_db() — it is not
--   affected by schema migrations.
--
-- NOT NULL on sample_index:
--   SQLite ALTER TABLE ADD COLUMN supports NOT NULL with a DEFAULT expression.
--   We use DEFAULT -1 as the sentinel for pre-migration rows (none expected in production
--   at Track D dispatch time; the unique constraint rejects duplicate -1 sentinels within
--   the same (run_id, clause_id, condition) so the sentinel doesn't mask bugs).
--   The application layer (Track D runner) always supplies a non-negative index.
--   Explicitly inserting NULL raises sqlite3.IntegrityError: NOT NULL constraint.

ALTER TABLE samples ADD COLUMN sample_index INTEGER NOT NULL DEFAULT -1;

-- Idempotency key: duplicate (run_id, clause_id, condition, sample_index) is a
-- crash-resume double-count → UNIQUE violation prevents corrupting the Beta-Binomial.
CREATE UNIQUE INDEX idx_samples_idempotency
    ON samples(run_id, clause_id, condition, sample_index);

-- Per-call cost columns (A41): written from actual response usage inside the evidence
-- transaction. All default NULL so pre-migration rows and rows from non-API-generating
-- operations (e.g., Tier-1 verdicts over cached outputs) remain valid.
ALTER TABLE samples ADD COLUMN input_tokens INTEGER DEFAULT NULL;
ALTER TABLE samples ADD COLUMN cache_read_input_tokens INTEGER DEFAULT NULL;
ALTER TABLE samples ADD COLUMN cache_creation_input_tokens INTEGER DEFAULT NULL;
ALTER TABLE samples ADD COLUMN output_tokens INTEGER DEFAULT NULL;
ALTER TABLE samples ADD COLUMN usd REAL DEFAULT NULL;

-- Ablation operator provenance (A39): mirrors metric_versions.implementation_hash discipline.
-- Both default NULL so pre-migration rows (non-ablation verdicts) remain valid.
ALTER TABLE oracle_verdicts ADD COLUMN ablation_operator_id TEXT DEFAULT NULL;
ALTER TABLE oracle_verdicts ADD COLUMN ablation_operator_hash TEXT DEFAULT NULL;

-- New index for cost reconciliation: sum per run across evidence rows (A41 reconciler).
CREATE INDEX idx_samples_run_cost ON samples(run_id) WHERE usd IS NOT NULL;
