# Supply Chain Risk Report

---

## Metadata

- **Scan Date**: 2026-06-03
- **Project**: Skill Harness (`youwontdoit`) — Python 3.13 LLM-skill evaluation framework
- **Repositories Scanned**: 10 direct dependencies (4 production, 6 dev)
- **Total Dependencies**: 10 direct (plus transitive deps scoped out per audit charter)
- **Scan Duration**: Single-session audit

---

## Executive Summary

The Skill Harness depends on a small, well-curated set of mature Python packages. All ten audited direct dependencies are actively maintained (last commit ≤ 35 days as of scan), none are archived, and none carry an active critical or high-severity CVE. The headline finding is the **anthropic-sdk-python** Memory Tool advisories published 2026-03-31 (two medium-severity issues): these do not affect the Skill Harness directly **unless** the harness opts into the Memory Tool, which is not in the locked scope (Anthropic API + SQLite evidence only). They are noted as a future scope-creep tripwire.

Three risk factors recurred across the audited set:
1. **No security contact** for several pytest-ecosystem and HypothesisWorks projects (no `SECURITY.md`, no org-level fallback). These are dev-only dependencies, so the practical risk is bounded to the local build environment.
2. **Single-individual maintainer concentration** for `rich` — Will McGugan / Textualize. The "well-known prolific contributor" mitigation applies but does not eliminate the bus-factor and credential-compromise risk.
3. **High-risk feature surface** in `anthropic` (network I/O, auth tokens, optional file-system Memory Tool) and `pydantic` (deserialization is the project's purpose). These are intrinsic to the harness's design and cannot be substituted away.

No production-direct dependency triggers a BLOCKER. The harness may proceed under the mitigations listed in Recommendations.

### Counts by Risk Factor

| Risk Factor                | Dependencies                                          | Total |
|----------------------------|-------------------------------------------------------|-------|
| Single maintainer / team   | rich                                                  | 1     |
| Unmaintained               | (none)                                                | 0     |
| Low popularity             | (none — pytest-cov / pytest-xdist borderline @ ~2k)   | 0     |
| High-risk features         | anthropic, pydantic                                   | 2     |
| Past CVEs                  | anthropic (2 medium, 2026-03), pydantic (1 medium, 2021) | 2     |
| Absence of security contact| pytest, pytest-cov, pytest-xdist, hypothesis          | 4     |
| **Total flagged deps**     | —                                                     | **6** |

### High-Risk Dependencies

The following dependencies have one or more risk factors. Production dependencies are listed first; dev dependencies are tagged `[dev]`.

| Dependency Name | Risk Factors | Notes | Suggested Alternative |
|-----------------|--------------|-------|-----------------------|
| anthropic (anthropics/anthropic-sdk-python) | High-risk features; Past CVEs | ~3.6k stars, ~300 open issues, last commit 2026-06-02 (active). Repo-level SECURITY.md present. Two medium CVEs published 2026-03-31 against the optional Memory Tool: "Insecure Default File Permissions" + "Path Validation Race Condition Allows Sandbox Escape". SDK is org-maintained by Anthropic (locked context: this is the API we're integrating against). Risk is intrinsic to the API client function. | **None — no drop-in substitute.** This is the official Anthropic SDK; the integration is the product. Mitigation: pin to a patched version (post-2026-03-31 release line), do NOT enable the Memory Tool surface, and treat the SDK as a trust boundary for outbound network calls. |
| pydantic (pydantic/pydantic) | High-risk features | ~28k stars, ~600 open issues, last commit 2026-06-03 (active). Org-level pydantic/.github/SECURITY.md present. One historic medium CVE from 2021 (infinity input → infinite loop in datetime parsing) — long since patched. Deserialization is the project's purpose, so the high-risk-feature flag is structural, not a deficiency. | **None — no drop-in substitute at this maturity tier.** `attrs` + `cattrs` is an option for narrower validation needs but is not a drop-in. Mitigation: validate untrusted input only at well-defined boundaries; do not feed model output directly into Pydantic constructors that allow arbitrary type instantiation. |
| rich (Textualize/rich) | Single maintainer / team | ~56.5k stars, ~340 open issues, last commit 2026-04-12 (active). Repo-level SECURITY.md present. Last 20 commits 100% authored by `willmcgugan` (Will McGugan, founder of Textualize). The "extremely prolific and well-known contributor" mitigation per skill guidance partially offsets the bus-factor risk, but a single individual with publish authority remains a credential-compromise vector. Used only for terminal formatting — non-security-critical surface. | **No substitute warranted.** `colorama` + `tabulate` cover ~20% of rich's surface but are not a drop-in. Mitigation: pin exact version; treat the dependency as terminal-output-only, never as a parser or input handler. |
| pytest (pytest-dev/pytest) `[dev]` | Absence of security contact | ~13.9k stars, ~1.0k open issues, last commit 2026-06-03 (active). No `SECURITY.md` at repo or `pytest-dev` org level (the org has no `.github` repo). pytest-dev is a healthy multi-maintainer collective and the test runner is dev-only, so blast radius is bounded to local test execution. | **No substitute.** pytest is the de facto Python test runner. Mitigation: vendor-locked via lockfile; vulnerability monitoring via `pip-audit` in CI. |
| pytest-cov (pytest-dev/pytest-cov) `[dev]` | Absence of security contact | ~2.0k stars, ~160 open issues, last commit 2026-04-24 (active). Borderline popularity but pytest-dev backed. No SECURITY.md. Recent commits show 3 active human contributors. Dev-only coverage plugin. | **`coverage` directly** (the underlying tool, pytest-cov is a thin pytest plugin around it) — slightly higher integration cost but a more focused dependency. Mitigation as for pytest. |
| pytest-xdist (pytest-dev/pytest-xdist) `[dev]` | Absence of security contact; near-single-maintainer | ~1.9k stars, ~300 open issues, last commit 2026-06-02 (active). No SECURITY.md. Recent commits dominated by RonnyPfannschmidt (well-known pytest-dev core maintainer) + bots. Parallel-test plugin, dev-only. | **No substitute warranted.** Mitigation as for pytest. If parallel test execution is not load-bearing for the harness, consider removing this dep entirely to shrink the dev attack surface. |
| hypothesis (HypothesisWorks/hypothesis) `[dev]` | Absence of security contact | ~8.7k stars, ~50 open issues, last commit 2026-05-30 (active). No SECURITY.md at repo or org level. Recent commits show 5 unique contributors (healthy). Property-based testing library; dev-only; generates test inputs (lower risk-feature surface than deserialization). | **No substitute at parity.** No equivalent property-based testing library exists for Python at this maturity. Mitigation: dev-only, no production runtime exposure; lockfile pin. |

## Suggested Alternatives

See the Suggested Alternative column in the High-Risk Dependencies table above. In all six cases, no credible drop-in replacement exists for the production path; the dev-tier dependencies could be partially substituted (`pytest-cov` → `coverage` directly) or removed if not load-bearing (`pytest-xdist`), but doing so does not eliminate the parent risk factor (the absence of `SECURITY.md` is a pytest-dev org-level pattern, not a per-package issue).

## Recommendations

1. **Pin anthropic SDK to a release dated on or after 2026-04-01** (post the two Memory Tool advisories), and do not enable the Memory Tool feature unless and until the harness explicitly opts in via a values-decision gate. Add `anthropic >= <patched-version>` to the lockfile constraint and add a CI check that fails the build if the lockfile version regresses below the patched line.
2. **Treat pydantic input boundaries as adversarial**. Anthropic API responses are the highest-risk input source. Validate model output via `BaseModel.model_validate` with `strict=True` where applicable, and never use Pydantic v2's discriminated-union arbitrary-type construction with untrusted input.
3. **Add `pip-audit` (or `safety`) to the CI pipeline** to catch future advisories on these six flagged dependencies (and their transitive deps) without depending on per-repo SECURITY.md presence. This compensates for the four pytest-ecosystem / HypothesisWorks deps that lack a security contact.
4. **Consider removing `pytest-xdist`** from dev dependencies if parallel test execution is not required by the harness's evaluation throughput targets. This is the lowest-popularity, single-effective-maintainer dev dependency in the set.
5. **Document the rich-as-output-only constraint** in the project's CONTRIBUTING.md or CLAUDE.md delta: rich is for terminal formatting only and must not be used to parse or interpret input, ensuring the single-maintainer risk is bounded to a non-security-critical surface.
6. **Re-run this audit at each major dependency version bump** of anthropic, pydantic, or pytest, and on a calendar cadence of no less than quarterly.

## Report Generated By

Supply Chain Risk Auditor Skill
Generated: 2026-06-03
