# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Report security issues privately via GitHub's [Security Advisory](https://github.com/MrBinnacle/skill-harness/security/advisories/new) feature. We aim to acknowledge reports within 72 hours and provide a remediation timeline within 7 days.

For sensitive disclosures that should not transit GitHub, contact the maintainer through the email listed on their GitHub profile.

## Supported versions

Skill Harness is currently in pre-alpha (`0.1.0a0`). Until a stable release is tagged, only the `main` branch receives security fixes. After `1.0.0`:

| Version | Supported |
|---------|-----------|
| Latest minor | ✅ |
| Previous minor | ✅ for 90 days |
| Older | ❌ |

## Supply-chain discipline

This project takes dependency provenance seriously. The discipline:

- **All production dependencies pinned above their last CVE-patched version.** The current `anthropic` pin (`>=0.87`) reflects the patches for GHSA-q5f5-3gjm-7mfm and GHSA-w828-4qhx-vxx3 (Memory Tool, 2026-03-31). See [`docs/supply-chain/`](docs/supply-chain/) for the per-dependency audit records that ARE tracked (e.g. `inspect-audit-2026-07-09.md`, `openai-audit-2026-06-08.md`).
- **Supply-chain audit re-run quarterly** and at every major version bump of `anthropic`, `pydantic`, or `pytest`. The `anthropic`-pin audit (see `CHANGELOG.md`'s `0.1.0a0` Security entry) was run with the `supply-chain-risk-auditor` tool at scaffold time (2026-06-03); its output directory (`.supply-chain-risk-auditor/`) is local-only and gitignored — not a tracked artifact, so the full results are not published in this repo.
- **Dependabot enabled** for `pip`, `github-actions`, and `pre-commit` ecosystems. See `.github/dependabot.yml`.
- **CodeQL** runs via GitHub's default code-scanning setup (Python + GitHub Actions queries, weekly) — not a tracked workflow file. An advanced-configuration `codeql.yml` was removed (`a917765`) because its SARIF uploads are rejected while default setup is enabled on this repo; one scanner, the working one. Scan status is visible on the repo's Security tab.
- **No deps with active high/critical CVEs.** Any introduction of such a dep requires PR-level justification + mitigation.
- **CI reproducibility (S4): `requirements-ci.txt`.** `pyproject.toml`'s runtime deps stay open-ended (`>=`) by design — this is a library, and downstream installers need to resolve compatible versions in their own environment, not inherit our exact pins. That openness has a supply-chain cost on its own: an audit like `openai-audit-2026-06-08.md` anchors a known-good floor version, but an unbounded `>=` lets the resolver drift arbitrarily far past it, including into an unaudited next major — which is why `openai` is now capped `<3` (audited-version-drift rule: a dependency's version range must never extend past the highest major actually reviewed in its audit doc; raising the cap requires a new audit entry, not just a version bump). CI's OWN installs are additionally pinned via `requirements-ci.txt` + `pip install -c requirements-ci.txt`, so a fresh CI run resolves the same transitive versions every time instead of "latest at run time" — this file constrains CI only and does not change what a downstream `pip install skill-harness` resolves.

## Surfaces explicitly NOT used

The harness explicitly avoids:

- **Anthropic Memory Tool** — current threat model puts this surface out of scope. CVE history above; constraint enforced by code review.
- **Pydantic loose-validation paths** — model output is validated with `strict=True` at API boundaries. Arbitrary type instantiation from untrusted input is forbidden.
- **Dynamic SQL on evidence tables** — every write goes through repository APIs in `src/skill_harness/storage/`.

## Threat model (informal)

The harness runs locally, hits the Anthropic API, and writes to SQLite. The default v0.1 trust model is **local-trust**: single operator, single host, evidence and runtime DB files live in the operator's filesystem. Remote network attackers, multi-tenant DB hosting, and hostile model providers replacing the SDK at runtime are out of scope. In scope: accidental developer mutation, dependency-tree compromise (passive), and filesystem-adjacent attackers with the same UID as the harness process.

The primary threats:

1. **Evidence tampering** — addressed by append-only triggers + SHA-256 migration ledger (see *Filesystem substitution boundary* below for the scope of this defense).
2. **Calibration drift hidden as admissible** — addressed by `expires_at` on calibration events + write-time snapshot. The `current_calibration` runtime pointer can be rewritten by a filesystem-adjacent attacker, but this affects only FUTURE verdicts; past verdicts have already snapshotted their `admissibility_state` at write time and the append-only triggers on `oracle_verdicts` prevent rewriting them.
3. **API key exfiltration** — read from environment, never logged, never persisted.
4. **Cost overrun via prompt injection in judged outputs** — bounded by per-run hard cap (`--max-usd`) and per-day rolling cap.

### Subject-layer oracle trust boundary (`command_succeeds` / `file_contains`)

`src/skill_harness/subject/inspect_adapter.py`'s outcome oracles interpolate
`oracle_arg` directly into a shell command (`bash -lc <oracle_arg>`) and, for
`file_contains`, into an f-string sandbox path — neither escapes nor validates
the value. This is safe under the v0.1 threat model above because `oracle_arg`
is operator-authored harness configuration (part of the same task definition as
`prompt` and `skill_dir`), not content derived from a skill, an agent
transcript, or any other ingested/untrusted source. `network_mode: none` on the
sandbox bounds the blast radius of a compromised value but does not make
deriving `oracle_arg` from untrusted material safe — a future caller that does
so would need argv-based execution (no shell string) and path
normalization/validation added first. This is the same "local-trust, single
operator" boundary as the rest of this document; it does not extend to a
future design where task/skill content flows into oracle configuration.

### Trust partition between `evidence.db` and `runtime.db`

`evidence.db` is append-only, audited, and load-bearing. `runtime.db` is mutable by design (in-flight progress, current calibration pointer, cost ledger). Compromise of `runtime.db` affects only FUTURE evidence rows via `current_calibration` snapshot at verdict write time; past evidence rows are bounded by the write-time-admissibility-snapshot rule above. **Symmetry between the two databases is NOT a design goal.** A future contributor proposing to "harden runtime.db with triggers for symmetry" is going in the wrong direction; the only append-only structure on the runtime side is `schema_migrations` (the META tamper-evidence ledger, see A21), which is structurally distinct from the operational tables (`run_progress`, `current_calibration`, `cost_ledger`).

### Filesystem substitution boundary

The append-only triggers and SHA-256 migration ledger defend against **in-process** unauthorized writes — developer error, SQL-injection-style mutation, library bugs. They do **NOT** defend against an attacker who replaces the entire `evidence.db` file at the filesystem layer. The SHA ledger checks file contents against an SHA recorded *inside the DB*; if the whole DB is substituted, both the data and the baseline-it-is-checked-against come from the attacker. v0.1's threat model assumes filesystem integrity. Detection of file-replacement attacks is a v0.2 concern (candidate D6 `db_identity` row + cross-DB identity check).

### PRAGMA scope

Connections to `evidence.db` and `runtime.db` **MUST** go through `skill_harness.storage.migrations.open_db()`. `journal_mode = WAL` is persistent at the DB-file level (SQLite docs), but `foreign_keys = ON`, `synchronous`, and `busy_timeout` are **connection-scoped** — a future caller that opens a raw `sqlite3.Connection(path)` silently loses FK enforcement and the durability tier appropriate to the DB role. Repository APIs in `src/skill_harness/storage/` enforce this in code review; PRs that bypass `open_db()` are blocked at review.

The durability tier itself is asymmetric and intentional: `evidence` opens at `synchronous = FULL` (audit rows must survive power loss), `runtime` at `synchronous = NORMAL` (in-flight state can be re-derived from evidence after a crash).

If you identify a threat outside this model, please report it via the channels above.

## Acknowledgments

Contributors who responsibly disclose security issues will be credited in `CHANGELOG.md` and in the GitHub security advisory (with their permission).
