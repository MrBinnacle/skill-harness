# Supply-chain audit: openai Python SDK (2026-06-08)

## Disposition

**PROCEED-WITH-MITIGATIONS**

The `openai` Python SDK (PyPI: `openai`, GitHub: `openai/openai-python`,
Apache-2.0, OpenAI Inc. + Stainless Software Inc. as code generator) clears the
T1 gate for the harness's narrow use of `client.chat.completions.create(...)`.
Three independent primary sources — GitHub Security Advisories on the repo
(`gh api repos/openai/openai-python/security-advisories?per_page=100` →
`[]`), NVD keyword search (`totalResults: 0`), and OSV.dev PyPI query
(`vulns: 0`) — return **zero** advisories in the 24-month window
(2024-06 → 2026-06). The SDK is org-backed by OpenAI, code-gen-maintained by
Stainless, actively pushed (last commit 2026-06-05), and ships a `SECURITY.md`
with a security contact (`security@stainless.com`). The mitigations below
are precautionary: (a) pin `openai >= 2.41.0` to anchor a known-good version
that exists at audit time, mirroring the `anthropic >= 0.87` pattern, and
(b) exclude the high-risk sub-surfaces (`openai.beta.*`, `resources/realtime`,
`resources/assistants`, function-calling auto-execution helpers) from the
import path used by the subject-call worker. None of those surfaces are in
scope per the harness's stated usage (chat completions only).

## Verified CVE findings (24-month window)

**Zero advisories opened against `openai/openai-python` in the 24-month window
(2024-06 → 2026-06).** Verified via three independent primary sources:

1. **GitHub Security Advisories (repo-scoped)**: `gh api 'repos/openai/openai-python/security-advisories?per_page=100'` → `[]` (empty array, all states including draft / triage / published / closed). Confirmed 2026-06-08.
2. **NVD keyword search**: `https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=openai-python&resultsPerPage=50` → `totalResults: 0`, `vulnerabilities: []`. Confirmed 2026-06-08.
3. **OSV.dev PyPI query**: `POST https://api.osv.dev/v1/query` body `{"package":{"name":"openai","ecosystem":"PyPI"}}` → `vulns: []` (zero). Confirmed 2026-06-08.

Cross-check: the GitHub Advisory Database web UI returns 31 results for
`openai-python ecosystem:pip`, but every result is for a downstream
integrator package (PraisonAI, vLLM, LangChain, Langroid, Open WebUI, etc.)
— none affect the `openai` PyPI package itself.

The absence of any advisory across three independent registries within a
24-month window is the **strongest** form of "verified zero." This is a
sharper baseline than the `anthropic` audit produced (two Memory Tool CVEs
required a `>=0.87` floor); the `openai` SDK has no CVE-derived floor at all.

## Maintainer / org profile

- **Backing org**: OpenAI Inc. (GitHub `openai`, account type `Organization`).
  Code generation maintained by Stainless Software Inc.
  (`SECURITY.md` reports to `security@stainless.com`).
- **Repo**: `https://github.com/openai/openai-python` —
  Apache-2.0, ~30,941 stars, ~4,834 forks, ~527 open issues,
  default branch `main`, archived `false`. Last commit
  `3842a5ea` on 2026-06-05 (`ci: use PyPI trusted publishing`).
  Most recent release `v2.41.0` published 2026-06-03; release cadence
  is high (5 releases in ~3 weeks: v2.37.0 → v2.41.0).
- **Active contributor set (top 10 by contributions)**:
  `stainless-app[bot]` (679), `stainless-bot` (276), `RobertCraigie` (96),
  `apcha-oai` (37), `hallacy` (29), `rachellim` (14), `logankilpatrick` (13),
  `dtmeadows` (9), `kristapratico` (9), `ddeville` (7).
  Two bots + at least 8 human contributors with publish-affecting activity.
  **Bus factor**: structurally similar to `anthropic-sdk-python`
  (also Stainless-generated; same bot/human pattern). The "single-maintainer"
  risk does NOT apply — both individual humans AND the generating org
  (Stainless) AND the owning org (OpenAI) would all need to lapse
  simultaneously.
- **Comparison to anthropic SDK profile**:

  | Property | anthropic-sdk-python | openai-python |
  |---|---|---|
  | Backing org | Anthropic, PBC | OpenAI Inc. |
  | Code-gen | Stainless | Stainless |
  | License | MIT | Apache-2.0 |
  | Stars | ~3.6k | ~30.9k |
  | SECURITY.md | Present | Present |
  | Recent commit | 2026-06-02 | 2026-06-05 |
  | CVE count (24 mo) | 2 (Memory Tool, patched 0.87.0) | **0** |
  | Bus factor | org + Stainless | org + Stainless |

  Both SDKs share the same code-gen pipeline (Stainless), so the same class
  of supply-chain risk applies symmetrically. The relevant asymmetry is
  on the **feature surface**, not the maintainer profile.

## High-risk surface analysis

Top-level resources under `src/openai/resources/` (2026-06-08 snapshot):

```
admin/   audio/   batches.py   beta/   chat/   completions.py
containers/   conversations/   embeddings.py   evals/   files.py
fine_tuning/   images.py   models.py   moderations.py   realtime/
responses/   skills/   uploads/   vector_stores/   videos.py   webhooks/
```

Sub-resources under `src/openai/resources/beta/`:
`assistants.py`, `beta.py`, `chatkit/`, `realtime/`, `threads/`.

Helper modules under `src/openai/lib/`:
`_parsing/`, `_pydantic.py`, `_realtime.py`, `_tools.py`, `_validators.py`,
`azure.py`, `bedrock.py`, `streaming/`.

### Memory-Tool / sandbox-escape archetype match

The `anthropic` SDK's two 2026-03-31 CVEs (`GHSA-q5f5-3gjm-7mfm` insecure
default file perms; `GHSA-w828-4qhx-vxx3` path-validation race / sandbox
escape) targeted the **Memory Tool** surface — a feature where the SDK
mediates a filesystem-backed scratch space for the model.

The `openai` SDK has no exact one-to-one analog (no "Memory Tool" namespace),
but the **closest archetype matches** are:

- `resources/beta/assistants.py` + `resources/beta/threads/` — the Assistants
  API, which (server-side) gives the model persistent state and tool
  invocation. The SDK-side surface is a network client, not a filesystem
  mediator, so the local-side file-perm / path-race archetype does NOT
  directly apply at the SDK layer. The risk reappears if the harness ever
  starts using the **code interpreter** or **file_search** tools via this
  surface — both involve uploads, paths, and tool-driven state.
- `resources/vector_stores/` + `resources/files.py` — file upload paths.
  Same archetype family (path handling, multipart upload); same conclusion
  (out of scope for chat-completions-only).
- `resources/realtime/` + `lib/_realtime.py` — WebSocket-based bidirectional
  surface; introduces a different threat model (long-lived connection,
  protocol parsing) than HTTP chat completions.

### Function-calling / tool-execution surface

The chat completions API does support `tools=` / `tool_choice=` parameters,
and the SDK exposes `lib/_tools.py` and `lib/_parsing/` helpers that **parse
tool-call responses into Python objects**. Critically: **the SDK does NOT
auto-execute** tool calls. Execution is the caller's responsibility; the
helpers only handle (de)serialization. The harness's planned usage path
(`client.chat.completions.create(...)` with NO tools, NO functions) does not
touch this surface at all.

### Deserialization paths

Like the `anthropic` SDK, `openai` uses Pydantic v2 (`_models.py`,
`lib/_pydantic.py`, `lib/_parsing/`) to validate API responses. This is
the same intrinsic deserialization risk that the existing audit already
mitigated for `pydantic` (see Appendix A — "Treat pydantic input boundaries
as adversarial"). No new mitigation required; the existing rule
("validate via `BaseModel.model_validate` with `strict=True`, never use
discriminated-union arbitrary-type construction with untrusted input")
covers this surface for both SDKs.

### Harness path assessment

The harness usage is: `client.chat.completions.create(...)`, parse
`response.usage.{prompt_tokens,completion_tokens}`, parse
`response.choices[0].message.content`, handle `openai.APIError` /
`openai.RateLimitError` / `openai.APIConnectionError`. **This path touches**:

- `resources/chat/` (top-level call entry)
- `_base_client.py` + `_client.py` + `_response.py` (HTTP transport, headers, streaming)
- `_models.py` + `lib/_pydantic.py` (response model parsing)
- `_exceptions.py` (error types)

**This path does NOT touch**: `resources/beta/`, `resources/realtime/`,
`resources/assistants/` (server-side feature; SDK access lives in
`resources/beta/`), `resources/vector_stores/`, `resources/files.py`,
`resources/audio/`, `resources/images/`, `resources/videos.py`,
`resources/embeddings.py`, `resources/uploads/`, `resources/webhooks/`,
`resources/evals/`, `resources/fine_tuning/`, `resources/batches.py`,
`resources/containers/`, `resources/skills/`, `resources/admin/`.

The high-risk-archetype surfaces (Assistants, Files, Realtime,
VectorStores, Webhooks) are **all** out of the harness path.

## Specific mitigations

### 1. `pyproject.toml` lower-bound pin

Mirror the `anthropic >= 0.87` pattern:

```toml
# openai >=2.41 anchors a known-good version at audit time (2026-06-08).
# Zero CVEs in the 24-month window (GHSA + NVD + OSV all return 0). The pin
# is precautionary, not CVE-derived. Harness uses chat completions only;
# beta/assistants/threads/realtime/files/vector_stores surfaces are out of
# scope. Re-audit on next major bump or quarterly (whichever first).
"openai>=2.41",
```

**Justification for `>= 2.41`**: this is the most recent release
(`v2.41.0` published 2026-06-03) and is what the harness will install
from a fresh resolve today. Pinning the lower bound at the audit-time
release establishes the baseline for the next re-audit (any version below
this floor must be re-audited; any version at-or-above this floor is
covered until the next re-audit cadence fires). This is **not** a
CVE-patch floor (no CVEs exist); it is a known-good anchor.

### 2. Sub-surface exclusion rule (Skill Harness CLAUDE.md amendment)

Add to the project delta or the subject-call module docstring:

> The subject-call worker imports `openai.OpenAI` and calls
> `client.chat.completions.create(...)` only. Importing or using
> `openai.beta.*` (Assistants, Threads, ChatKit), `openai.resources.realtime`,
> `openai.resources.assistants`, `openai.resources.files`,
> `openai.resources.vector_stores`, `openai.resources.uploads`, or
> `openai.resources.webhooks` is out of scope for v0.1 and requires
> a re-fire of the supply-chain audit + a values-decision gate.
> Rationale: these surfaces match the archetype family of the two 2026-03
> `anthropic` Memory Tool CVEs (file paths, persistent state, async/streaming
> protocols); they are not load-bearing for the harness's chat-completions
> evaluation path.

Optional structural enforcement (parallels A28's grep-ban pattern):
add a pre-commit/CI grep that fails if `openai.beta` or `openai.resources.realtime`
appears in `src/` outside an explicitly-scoped module.

### 3. Pydantic-boundary discipline already covers response parsing

The existing Appendix A mitigation rule for `pydantic` ("validate Anthropic
API responses via `BaseModel.model_validate` with `strict=True`; never use
discriminated-union arbitrary-type construction with untrusted input")
applies symmetrically to OpenAI API responses. No new rule needed.

## Deferrals

- **`pip-audit` in CI for `openai`**: same deferral as Appendix A
  (`pip-audit` was deferred until CI exists; no CI workflows yet, out of
  v0.1 scope per §D). When CI lands, the existing `pip-audit` step covers
  both SDKs uniformly.
- **Quarterly re-audit + major-version-bump re-audit**: the next re-audit
  on the `anthropic` cadence is **2026-09-03**. The `openai` audit
  cadence is aligned to the same date (single quarterly re-audit covers
  both production LLM-SDK deps). Trigger conditions: (a) calendar (2026-09-03),
  (b) `openai` major bump (next will be `v3.x`), or (c) any new advisory
  surfacing on `gh api repos/openai/openai-python/security-advisories`.
- **Stainless-pipeline integrity audit**: both `anthropic` and `openai` SDKs
  are generated by Stainless. A compromise of Stainless's build pipeline
  would affect both SDKs simultaneously. A dedicated audit of the Stainless
  supply chain (e.g., GitHub Actions used in their generation pipeline,
  npm-side dependencies of their generator) is deferred — out of v0.1
  scope; treated as a shared-upstream risk noted for the threat model
  (SECURITY.md update).
- **Stainless trusted-publishing transition**: the last commit on
  `openai-python` (2026-06-05) is `ci: use PyPI trusted publishing`. This
  is a **positive** signal (eliminates long-lived PyPI tokens), but the
  transition itself is recent. Re-confirm at next re-audit that no
  publishing-pipeline regressions occurred.

## Citation verification

Per `subagent-research-reliability` discipline, every CVE-specific claim
in this audit was verified at primary source before the audit was written.
Queries run on 2026-06-08:

- `gh api repos/openai/openai-python/security-advisories?state=published&per_page=100` → `[]`
- `gh api repos/openai/openai-python/security-advisories?per_page=100` (all states) → `[]` (count 0)
- `gh api repos/openai/openai-python` → metadata snapshot
  (stars 30941, forks 4834, license Apache-2.0, archived false, last push
  2026-06-05, owner type Organization)
- `gh api repos/openai/openai-python/releases?per_page=5` → v2.41.0 (2026-06-03),
  v2.40.0 (2026-06-01), v2.39.0 (2026-06-01), v2.38.0 (2026-05-21),
  v2.37.0 (2026-05-15)
- `gh api repos/openai/openai-python/contributors?per_page=10` → bot-dominated
  but multi-human contributor set
- `gh api repos/openai/openai-python/contents/SECURITY.md` → present, 1331 bytes,
  contact `security@stainless.com`
- `gh api repos/openai/openai-python/contents/src/openai` → top-level package
  structure (`resources/`, `lib/`, `_base_client.py`, `_client.py`,
  `_models.py`, `_exceptions.py`, etc.)
- `gh api repos/openai/openai-python/contents/src/openai/resources` → resource
  inventory (chat, completions, beta, realtime, assistants, files,
  vector_stores, etc.)
- `gh api repos/openai/openai-python/contents/src/openai/resources/beta` →
  beta surface (assistants, threads, chatkit, realtime)
- `gh api repos/openai/openai-python/commits?per_page=1` → last commit
  `3842a5ea` on 2026-06-05 (`ci: use PyPI trusted publishing (#3365)`)
- NVD REST API (WebFetch):
  `https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=openai-python&resultsPerPage=50`
  → `totalResults: 0`, `vulnerabilities: []`
- OSV.dev REST API (Bash + curl):
  `POST https://api.osv.dev/v1/query` body
  `{"package":{"name":"openai","ecosystem":"PyPI"}}` → `vulns: []`
- GitHub Advisory Database (web search via WebFetch):
  `https://github.com/advisories?query=openai-python+ecosystem%3Apip` →
  31 results, **zero** attributable to the `openai` PyPI package itself
  (all downstream integrators: PraisonAI, vLLM, LangChain, etc.)

### Citation-verification caveat

A PyPI-metadata WebFetch
(`https://pypi.org/pypi/openai/json`) returned **release timestamps**
(`upload_time` values like `2024-12-19`, `2025-01-14`) that contradict
the authoritative `gh api .../releases` timestamps (`2026-06-03` for
v2.41.0). Behavior consistent with the WebFetch summarizer model
hallucinating older years; the **GitHub release timestamps are
authoritative** and are what this audit cites. The PyPI version string
itself (`2.41.0`), license (`Apache-2.0`), author (`OpenAI`), and
`requires_python` (`>=3.9`) were consistent across sources and are
retained as facts.

---

**Audit author**: supply-chain-risk-auditor skill, dispatched by orchestrator
for Tier 1 of T3 tracer round.
**Audit gate cleared**: CLAUDE.md ALWAYS section
("Run `supply-chain-risk-auditor` before any new ML/AI dependency lands.").
**Disposition**: PROCEED-WITH-MITIGATIONS (pin `openai >= 2.41`; document
sub-surface exclusion; no CI/code commits in this audit).
