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

- **All production dependencies pinned above their last CVE-patched version.** The current `anthropic` pin (`>=0.87`) reflects the patches for GHSA-q5f5-3gjm-7mfm and GHSA-w828-4qhx-vxx3 (Memory Tool, 2026-03-31). See [`docs/COUNCIL_FINDINGS.md`](docs/COUNCIL_FINDINGS.md) Appendix A for the full audit record.
- **Supply-chain audit re-run quarterly** and at every major version bump of `anthropic`, `pydantic`, or `pytest`. The audit lives at `.supply-chain-risk-auditor/results.md`.
- **Dependabot enabled** for `pip`, `github-actions`, and `pre-commit` ecosystems. See `.github/dependabot.yml`.
- **CodeQL** runs on every PR and weekly on `main`. See `.github/workflows/codeql.yml`.
- **No deps with active high/critical CVEs.** Any introduction of such a dep requires PR-level justification + mitigation.

## Surfaces explicitly NOT used

The harness explicitly avoids:

- **Anthropic Memory Tool** — current threat model puts this surface out of scope. CVE history above; constraint enforced by code review.
- **Pydantic loose-validation paths** — model output is validated with `strict=True` at API boundaries. Arbitrary type instantiation from untrusted input is forbidden.
- **Dynamic SQL on evidence tables** — every write goes through repository APIs in `src/skill_harness/storage/`.

## Threat model (informal)

The harness runs locally, hits the Anthropic API, and writes to SQLite. The primary threats:

1. **Evidence tampering** — addressed by append-only triggers + SHA-256 migration ledger
2. **Calibration drift hidden as admissible** — addressed by `expires_at` on calibration events + write-time snapshot
3. **API key exfiltration** — read from environment, never logged, never persisted
4. **Cost overrun via prompt injection in judged outputs** — bounded by per-run hard cap (`--max-usd`) and per-day rolling cap

If you identify a threat outside this model, please report it via the channels above.

## Acknowledgments

Contributors who responsibly disclose security issues will be credited in `CHANGELOG.md` and in the GitHub security advisory (with their permission).
