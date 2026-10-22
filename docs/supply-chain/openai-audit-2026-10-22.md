# Supply-chain audit: openai Python SDK 3.x (2026-10-22)

## Disposition

**CLEARS the 3.x major at openai 3.36.1. Keep the range `openai>=3.15.0,<4`, and raise its floor to `>=3.17.0`.**

This audit reviews `openai` 3.36.1. It is the newest release in the 3.x line on 2026-10-22. PyPI published it at 2026-10-22T03:33Z, and no 4.x release exists. The range `>=3.15.0,<4` resolves to 3.36.1 today.

No advisory names the `openai` package in the 24-month window (2024-10 to 2026-10). GHSA, OSV and NVD each return zero. The harness path is one call, `client.chat.completions.create(...)`, with no tools. That path reaches none of the new 3.x surfaces. These surfaces are the Agents API, the browser and computer toolsets, the tool runners and the WebSocket sessions.

The 3.x line moved the HTTP transport from `httpx` to `httpx2`. `httpx2` has five published advisories. All five are fixed in `httpx2` 2.12.0. openai 3.36.1 requires `httpx2>=2.12.0`, so the audited version is clean, transitives included. The current floor, 3.15.0, requires only `httpx2>=2.7.0`. That floor permits a vulnerable transport. openai 3.17.0 is the first release that requires `httpx2>=2.12.0`. The floor change is a mitigation inside the cleared major. It is not a cap change.

This audit applies the standard of the 2026-06-08 audit. A surface counts as reached when the harness call path executes it. A surface does not count as reached when the package only installs it.

## Verified CVE findings (24-month window)

**Zero advisories affect the `openai` PyPI package in the window 2024-10-22 to 2026-10-22.** Four primary sources agree:

1. GitHub Advisory Database, global. `gh api "/advisories?ecosystem=pip&affects=openai&per_page=100"` returns `[]`.
2. GitHub repository advisories. `gh api "repos/openai/openai-python/security-advisories?per_page=100"` returns `[]` across all states.
3. OSV.dev. `POST https://api.osv.dev/v1/query` with body `{"package":{"name":"openai","ecosystem":"PyPI"}}` returns `{}`, which means no vulns.
4. NVD. Keyword searches `openai-python` and `openai python sdk` each return `totalResults: 0`.

### Transitive finding: httpx2

openai 3.x depends on `httpx2` (`pydantic/httpx2` on GitHub, author Tom Christie). The GHSA global query `affects=httpx2` and the OSV query for `httpx2` return the same five advisories. GHSA published all five on 2026-09-08.

| GHSA | CVE | Severity | Affected httpx2 | Fixed | Summary |
|---|---|---|---|---|---|
| GHSA-8xx6-hgc6-gc2m | CVE-2026-84382 | high | < 2.12.0 | 2.12.0 | Streaming response decompression does not bound peak memory |
| GHSA-7mj9-2mp8-4m2p | CVE-2026-84381 | high | >= 2.6.0, < 2.10.0 | 2.10.0 | Secure WebSocket traffic sent without TLS through SOCKS proxies |
| GHSA-pf96-p4fj-6566 | CVE-2026-84380 | medium | < 2.11.0 | 2.11.0 | Conflicting Content-Length and Transfer-Encoding headers can be auto-generated |
| GHSA-h4x7-gw46-3wm6 | CVE-2026-84379 | medium | < 2.11.0 | 2.11.0 | Multipart part header injection via file Content-Type and custom headers |
| GHSA-f2fp-rgf2-35cp | CVE-2026-84378 | medium | >= 2.5.0, < 2.10.0 | 2.10.0 | Quadratic SSE line buffering can cause CPU denial of service |

OSV also lists PYSEC aliases for these five: PYSEC-2026-3844 through PYSEC-2026-3849.

The `httpx2` floor that each openai release declares, read from PyPI per-version JSON:

| openai | `httpx2` requirement | Permits a vulnerable httpx2 |
|---|---|---|
| 3.15.0 (current floor) | `>=2.7.0` | yes |
| 3.16.2 | `>=2.7.0` | yes |
| 3.17.0 | `>=2.12.0` | no |
| 3.36.1 (audited) | `>=2.12.0` | no |

GHSA-8xx6-hgc6-gc2m matters most to the harness. It affects the plain response path that a chat completions call uses. The multipart, WebSocket and SSE advisories need uploads, `wss://` connections or streaming. The harness uses none of them.

## Maintainer / org profile

- **Owner.** OpenAI (GitHub `openai`, account type Organization). Stainless generates most of the code. The top two contributors are `stainless-app[bot]` (704) and `stainless-bot` (276).
- **Repository.** `https://github.com/openai/openai-python`. License Apache-2.0. 31,910 stars, 8,057 forks, 147 open issues. Not archived. The last commit is `7db9d884` on 2026-10-22 ("chore(api): preserve file and video polling helpers (#4155)").
- **Human contributors in the top ten.** `apcha-oai` (114), `RobertCraigie` (96), `jbeckwith-oai` (83), `markstuart-oai` (55), `hallacy` (29), `marcuswood-oai` (23). The bot accounts `openai-sdks[bot]` (48) and `dependabot[bot]` (23) complete the list. No single person carries the project.
- **Release cadence.** 47 releases in the 3.x line, from 3.0.0 on 2026-08-12 to 3.36.1 on 2026-10-22. Eight releases shipped between 2026-10-14 and 2026-10-22.
- **Security policy.** `SECURITY.md` (1,881 bytes) routes reports through OpenAI's coordinated vulnerability disclosure process. The contact is `disclosure@openai.com`. The 2026-06-08 audit recorded `security@stainless.com`. That contact is no longer current. `SECURITY.md` now points to a canonical threat model at `docs/architecture/security-model.md` (75,546 bytes at v3.36.1). This audit did not read that file. See Deferrals.
- **Publishing provenance.** PyPI serves a PEP 740 attestation for `openai-3.36.1-py3-none-any.whl`. The publisher is GitHub repository `openai/openai-python`, workflow `create-releases.yml`, environment `publish`. This confirms the trusted-publishing move that the 2026-06-08 audit asked the next audit to re-check.
- **Comparison with anthropic.** The anthropic SDK has the same Stainless generator. PyPI serves no provenance for anthropic 1.15.0 or 1.17.0. See `anthropic-audit-2026-10-22.md`.

## High-risk surface analysis

Top-level resources under `src/openai/resources/` at tag v3.36.1:

```
admin  audio  batches.py  beta  chat  completions.py  containers
content_provenance_checks.py  conversations  decisions.py  embeddings.py
evals  files.py  fine_tuning  images.py  live  models.py  moderations.py
realtime  responses  safety  skills  uploads  vector_stores  videos.py  webhooks
```

Sub-resources under `src/openai/resources/beta/`: `agents`, `assistants.py`, `beta.py`, `chatkit`, `realtime`, `responses`, `threads`.

Helper modules under `src/openai/lib/` include `browser.py`, `computer.py`, `responses_tool_runner.py`, `decisions_tool_runner.py`, `_tool_lifecycle.py`, `_websocket.py`, `live`, `responses_websocket`, `_files.py`, `_uploads.py` and `_vector_stores.py`.

### New surfaces in the 3.x line

The release notes for v3.0.0 through v3.36.1 add these surfaces:

- **httpx2 transport (3.0.0).** A breaking change. `httpx` is no longer installed. Custom HTTPX clients must move to HTTPX2.
- **Agents API (3.13.0).** Later releases add credentials and session options (3.20.0), computer use in beta agents (3.22.0), file staging and turn-artifact downloads (3.23.0), and agent environment suspension (3.28.0).
- **Local tool execution (3.25.0).** "agents: run local tools during streamed session creation". The 2026-06-08 audit said the SDK does not auto-execute tool calls. That statement was true of 2.41. It is false for the 3.x Agents and tool-runner helpers.
- **Browser and computer toolsets (3.31.0).** "add browser and computer toolsets (1/4)". `lib/browser.py` exposes browser actions as Responses function tools. Its docstring says, "Only direct URLs are checked here; network isolation belongs to the driver." `lib/computer.py` runs the computer tool against a driver that the caller owns.
- **WebSocket sessions.** Managed Responses WebSocket sessions (3.15.0), Live sessions, and Realtime Translation sessions (3.34.0). Releases 3.32.0 through 3.36.1 carry many WebSocket fixes.

These surfaces belong to the archetype family of the 2026-03 anthropic Memory Tool CVEs. They handle local files, local execution and long-lived protocol state. They are the main reason the 3.x line is riskier than 2.41 as installed code.

### Function-calling and tool-execution surface

Chat completions still accept `tools=` and `tool_choice=`. Those parameters only serialize tool calls. The execution helpers live in `lib/browser.py`, `lib/computer.py` and the two tool runners. A caller reaches them only by importing them or by touching the lazy exports. `openai/__init__.py` loads `lib.computer` through a module `__getattr__`, only when code reads one of `ComputerToolset`, `AsyncComputerToolset`, `ComputerDriver` or `AsyncComputerDriver`. `import openai` alone does not load `lib/computer.py`.

### Deserialization paths

Responses still parse through Pydantic (`_models.py`, `lib/_pydantic.py`, `lib/_parsing/`). The 2026-06-08 audit covered this risk under the existing pydantic boundary rule. Nothing in 3.x changes that conclusion.

### Harness path assessment

The harness has one openai call site, `OpenAISubjectClient` in `src/skill_harness/ablation/subject.py`. This audit read it at `origin/main` `0bf00f9`.

- Imports (lines 47 to 49): `from openai import OpenAI`, `APIStatusError`, `APIConnectionError`. No other module in `src/` imports `openai`.
- Construction (lines 605 and 608): `OpenAI(api_key=..., base_url=...)` for OpenRouter, or `OpenAI()` for direct OpenAI.
- Call (line 647): `self._client.chat.completions.create(model=..., messages=..., max_tokens=...)`. The call passes no `tools`, no `tool_choice`, no `stream` and no `response_format`.
- Reads: `response.choices[0].message.content`, `response.usage.prompt_tokens`, `completion_tokens`, `prompt_tokens_details.cached_tokens`, and `usage.cost` on the OpenRouter path.
- Errors: `APIStatusError` and `APIConnectionError`.

The issue statement holds. The harness uses chat completions only, through the T3 tracer adapter.

**This path reaches:** `resources/chat/`, `_base_client.py`, `_client.py`, `_response.py`, `_models.py`, `_exceptions.py`, and the `httpx2` transport for non-streaming HTTPS requests.

**This path does not reach:** `resources/beta/` (agents, assistants, chatkit, realtime, responses, threads), `resources/responses/`, `resources/realtime/`, `resources/live/`, `resources/files.py`, `resources/uploads/`, `resources/vector_stores/`, `resources/webhooks/`, `resources/containers/`, `resources/skills/`, `resources/decisions.py`, `lib/browser.py`, `lib/computer.py`, `lib/responses_tool_runner.py`, `lib/decisions_tool_runner.py`, `lib/_websocket.py`, `lib/live`, or any `httpx2` WebSocket, multipart or SSE code.

No harness call site reaches a high-risk 3.x surface.

## Specific mitigations

### 1. Raise the openai floor to 3.17.0

Change the pin from `openai>=3.15.0,<4` to `openai>=3.17.0,<4`. openai 3.17.0 is the first release whose metadata requires `httpx2>=2.12.0`. That version fixes all five `httpx2` advisories. Dependabot PR #787 bumps the CI pin to 3.31.0, which also satisfies this floor. Keep the `<4` cap. A 4.x release needs its own audit before the cap moves.

### 2. Constrain httpx2 directly, or record why not

The anthropic SDK requires only `httpx2>=2.0.0` in every version checked (1.15.0, 1.17.0, 2.1.0). Once the openai floor is 3.17.0, openai's metadata is the only thing that forces a patched `httpx2`. A direct runtime pin of `httpx2>=2.12.0` in `pyproject.toml` removes that coupling. Adding a direct dependency is an ask-first change in this repository. If the pin is not added, record in `SECURITY.md` that openai's floor enforces the `httpx2` fix.

### 3. Constrain httpx2 in CI

`requirements-ci.txt` has no `httpx2` or `httpcore2` line. It pins the old `httpx==0.28.1` and `httpcore==1.0.9`, which the 3.x SDK no longer uses. CI therefore resolves `httpx2` without a constraint. Today that gives 2.16.0, which is past every fix. The file's own header names unconstrained resolution as the drift it exists to stop. The next regeneration of `requirements-ci.txt` must capture `httpx2` and `httpcore2`.

### 4. Keep the sub-surface exclusion, and add the 3.x surfaces to it

The import restriction in `src/skill_harness/ablation/subject.py` (lines 42 to 46 and 550 to 554) lists the 2.41 exclusions. Add the 3.x surfaces to that list: `openai.lib.browser`, `openai.lib.computer`, `openai.lib.responses_tool_runner`, `openai.lib.decisions_tool_runner`, `openai.resources.live`, `openai.resources.responses`, and the `ComputerToolset` and `ComputerDriver` lazy exports. The 2026-06-08 audit proposed an optional CI grep ban for `openai.beta` and `openai.resources.realtime` in `src/`. Add that ban now, because 3.x ships local execution helpers.

### 5. Pydantic boundary rule

No change. The existing pydantic boundary rule covers response parsing.

## Deferrals

- **OpenAI's canonical threat model.** `docs/architecture/security-model.md` at v3.36.1 is 75,546 bytes. This audit did not read it. Read it at the next re-audit, or sooner if the harness adopts any surface outside chat completions.
- **Stale path in source comments.** `src/skill_harness/ablation/subject.py` lines 46 and 51 cite `.supply-chain-risk-auditor/openai-audit-2026-06-08.md`. The audit file lives at `docs/supply-chain/openai-audit-2026-06-08.md`. This audit's write grant covers only the two audit files, so the comment is unchanged here.
- **`SECURITY.md` and the `pyproject.toml` comment.** Issue #732 steps 3 and 4 own these edits. The `pyproject.toml` comment beside the openai pin still says "Capped <3". It must cite this file.
- **Stainless pipeline integrity.** The 2026-06-08 deferral stands. One generator serves both LLM SDKs, so one pipeline compromise would reach both.
- **Re-audit triggers.** Re-audit on any of these: a 4.x release that a cap change would admit, a new advisory on `openai` or `httpx2`, any harness use of a surface outside chat completions, or the quarterly calendar (next 2027-01-22).

## Citation verification

The Trail of Bits `supply-chain-risk-auditor` skill named in issue #732 is not installed in this environment. This audit was done by hand with `gh`, `curl` and Python. Every advisory ID in this file came from a query run in this session.

All fetches ran on 2026-10-22. The first batch completed at 17:42:24 UTC, and every later fetch ran after it on the same date.

- `curl https://pypi.org/pypi/openai/json`. Latest version 3.36.1, `requires_python >=3.10`, license expression Apache-2.0, 47 releases in 3.x, none at 4.x. The wheel for 3.36.1 was uploaded at 2026-10-22T03:33:14Z.
- `curl https://pypi.org/pypi/openai/{3.15.0,3.16.2,3.17.0,3.36.1}/json`. The `httpx2` requirements in the table above.
- `curl https://pypi.org/integrity/openai/3.36.1/openai-3.36.1-py3-none-any.whl/provenance`. One attestation bundle, publisher `openai/openai-python`, workflow `create-releases.yml`, environment `publish`.
- `gh api "/advisories?ecosystem=pip&affects=openai&per_page=100"`. Returns `[]`.
- `gh api "repos/openai/openai-python/security-advisories?per_page=100"`. Returns `[]`.
- `curl -s https://api.osv.dev/v1/query -d '{"package":{"name":"openai","ecosystem":"PyPI"}}'`. Returns `{}`.
- NVD REST API 2.0, `keywordSearch=openai-python` and `keywordSearch=openai%20python%20sdk`. Each returns `totalResults: 0`.
- `gh api "/advisories?ecosystem=pip&affects=httpx2&per_page=100"`. Returns the five GHSA records in the table, with severity, CVE, range and first patched version.
- `curl -s https://api.osv.dev/v1/query -d '{"package":{"name":"httpx2","ecosystem":"PyPI"}}'`. Returns the same five GHSA IDs and the PYSEC aliases PYSEC-2026-3844 through PYSEC-2026-3849.
- `curl https://pypi.org/pypi/httpx2/json`. Latest 2.16.0, author Tom Christie, source `https://github.com/pydantic/httpx2`.
- `gh api repos/openai/openai-python`. Stars, forks, open issues, license, archive state, owner type.
- `gh api "repos/openai/openai-python/commits?per_page=1"`. Last commit `7db9d884`.
- `gh api "repos/openai/openai-python/contributors?per_page=10"`. The contributor counts above.
- `gh api repos/openai/openai-python/contents/SECURITY.md`. 1,881 bytes, contact `disclosure@openai.com`.
- `gh api "repos/openai/openai-python/releases?per_page=60"` and `releases/tags/v3.0.0`, `releases/tags/v3.31.0`. The 3.x release notes quoted above.
- `gh api "repos/openai/openai-python/contents/src/openai/resources?ref=v3.36.1"`, and the same for `resources/beta` and `lib`. The inventories above.
- `gh api "repos/openai/openai-python/contents/src/openai/lib/browser.py?ref=v3.36.1"` and `lib/computer.py`. The docstrings quoted above.
- `gh api "repos/openai/openai-python/contents/src/openai/__init__.py?ref=v3.36.1"`. The lazy `__getattr__` export of `lib.computer`.
- `gh api "repos/openai/openai-python/contents/docs/architecture/security-model.md?ref=v3.36.1"`. Size only, 75,546 bytes.
- Local reads at `origin/main` `0bf00f9`: `grep` over `src/` for `import openai` and `from openai`, then `src/skill_harness/ablation/subject.py` lines 36 to 56, 545 to 560 and 595 to 700. Also `pyproject.toml` lines 25 to 45 and `requirements-ci.txt` lines 1 to 80.
- `gh pr view 787`. Title "chore(deps)(deps): bump openai from 3.15.0 to 3.31.0", state OPEN.

### Timestamp check

The 2026-06-08 audit distrusted PyPI timestamps because a summarizing fetch tool returned wrong years. This audit read PyPI JSON with `curl` and parsed it locally. The PyPI upload times match the GitHub release times within one minute. For example, v3.36.1 shows PyPI 2026-10-22T03:33:14Z and GitHub 2026-10-22T03:32:31Z. That caveat does not apply to this audit.
