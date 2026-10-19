# migrations_sql/

This directory (`src/skill_harness/storage/migrations_sql/`, shipped as package
data) contains SQL migration files for the Skill Harness storage layer.  There
are two sub-directories:

- **`evidence/`** — append-only evidence DB schema (triggers, indexes, VIEWs).
- **`runtime/`** — mutable runtime DB schema (in-flight state, cost ledger,
  calibration pointer).

## Per-track version number ranges (A30)

Migration version numbers are reserved by track to enable parallel Phase 2
development without collision.  Each track owns an exclusive range:

| Track | Range      | Concern                        |
|-------|------------|--------------------------------|
| A     | 0001–0099  | Storage primitives             |
| B     | 0100–0199  | Clause extractor               |
| C     | 0200–0299  | Oracle / calibration           |
| D     | 0300–0399  | Ablation runner                |
| E     | 0400–0499  | Aggregation / status reporting |
| v0.2  | 0500–0599  | Subject layer (harness pin, screen store) — per the A30 ledger note in `0500` |
| Board | 0600–0699  | Honest Live Board delivery spine (model pin / drift fingerprint, #75) |
| Frontier | 0700–0799 | Task-frontier spine — calibration/confirmation/matched phase partition (#89/#90) |

**Why this matters:**

1. **Parallel worktree safety** — Tracks B–E execute in separate git worktrees
   simultaneously.  Without reserved ranges, two tracks might independently
   choose version 0004 and create a conflict that cannot be cherry-picked
   cleanly.

2. **SHA-256 tamper-evidence ledger** — `schema_migrations` records the
   SHA-256 of every applied file.  Once a migration is applied to a DB, its
   file must not change.  Numbering gaps from the reserved ranges are
   intentional placeholders; do not fill them with unrelated migrations.

3. **`discover()` duplicate guard** — `migrations.py::discover()` raises
   `BootstrapError` if two `.sql` files in the same directory share the same
   four-digit version prefix (e.g., `0001_one.sql` and `0001_two.sql`).  The
   per-track ranges make such collisions impossible under normal operation and
   make them immediately diagnosable when they do occur.

## Naming convention

```
NNNN_<snake_case_description>.sql
```

- `NNNN` is zero-padded to four digits.
- The description uses `snake_case`.
- Every file must be parseable by `migrations.py::discover()`.

## CODEOWNERS gate

Any pull request that modifies files under `migrations_sql/` requires sign-off
from the SCHEMA + SECURITY review seats per A30 (`.github/CODEOWNERS`).  This
enforces the pre-merge council fire requirement from the project plan.
