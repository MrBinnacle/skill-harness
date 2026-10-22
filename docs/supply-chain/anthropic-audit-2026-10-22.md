# Supply-chain audit: anthropic Python SDK 1.x (2026-10-22)

## Disposition

**CLEARS the 1.x major at anthropic 1.17.0. The range as written does not stay inside it. Cap the range to `anthropic>=1.15.0,<2`.**

This audit reviews `anthropic` 1.17.0. It is the newest release in the 1.x line. PyPI published it at 2026-10-20T22:13Z.

The pin in `pyproject.toml` is `anthropic>=1.15.0`. It has no upper bound. PyPI published anthropic 2.0.0 on 2026-10-21 and 2.1.0 later that day. The 2.0.0 release notes open with a "BREAKING CHANGES" header. A fresh resolve today installs 2.1.0, which no audit has reviewed. That breaks the audited-version-drift rule in `SECURITY.md`. So "keep the range" is not available here, even though the 1.x line clears. Add the `<2` cap until a 2.x audit exists.

Two advisories name the `anthropic` package in the 24-month window. Both affect only 0.86.x and are fixed in 0.87.0. The 1.15.0 floor is far above the fix. The harness calls `messages.create` at three sites. Two of them pass a client-defined tool schema with a forced `tool_choice`, and the harness parses the returned `tool_use` input. The SDK executes nothing locally on that path. The harness reaches no beta surface, no tool runner, no Memory Tool and no agent toolset.

The 1.x line moved the HTTP transport to `httpx2`. Every anthropic version checked declares `httpx2>=2.0.0`, which permits all five published `httpx2` advisories. The openai floor, not the anthropic metadata, is what keeps a patched `httpx2` installed. See Specific mitigations.

This audit applies the standard of the 2026-06-08 openai audit. A surface counts as reached when the harness call path executes it. A surface does not count as reached when the package only installs it.

## Verified CVE findings (24-month window)

**Two advisories affect the `anthropic` PyPI package in the window 2024-10-22 to 2026-10-22. Neither affects any version at or above the 1.15.0 floor.**

| GHSA | CVE | PYSEC | Severity | Affected | Fixed | Summary |
|---|---|---|---|---|---|---|
| GHSA-q5f5-3gjm-7mfm | CVE-2026-34450 | PYSEC-2026-2114 | medium | >= 0.86.0, < 0.87.0 | 0.87.0 | Insecure default file permissions in the local filesystem Memory Tool |
| GHSA-w828-4qhx-vxx3 | CVE-2026-34452 | PYSEC-2026-2115 | medium | >= 0.86.0, < 0.87.0 | 0.87.0 | Memory Tool path validation race condition allows sandbox escape |

Four primary sources agree:

1. GitHub Advisory Database, global. `gh api "/advisories?ecosystem=pip&affects=anthropic&per_page=100"` returns these two records. GHSA lists them as published 2026-04-01.
2. GitHub repository advisories. `gh api "repos/anthropics/anthropic-sdk-python/security-advisories?per_page=100"` returns the same two, state `published`, dated 2026-03-31.
3. OSV.dev. The PyPI query for `anthropic` returns four records. They are the two GHSA records and their PYSEC aliases. Every record gives the range introduced 0.86.0, fixed 0.87.0.
4. NVD. Keyword search `anthropic python sdk` returns CVE-2026-34450 and CVE-2026-34452 only. Keyword search `anthropic-sdk-python` returns zero.

The 1.x line has no advisory of its own.

### Transitive finding: httpx2

anthropic 1.x depends on `httpx2`. The GHSA and OSV queries for `httpx2` return five advisories, all published 2026-09-08 and all fixed by `httpx2` 2.12.0:

- GHSA-8xx6-hgc6-gc2m (CVE-2026-84382, high). Streaming response decompression does not bound peak memory. Fixed in 2.12.0.
- GHSA-7mj9-2mp8-4m2p (CVE-2026-84381, high). Secure WebSocket traffic sent without TLS through SOCKS proxies. Fixed in 2.10.0.
- GHSA-pf96-p4fj-6566 (CVE-2026-84380, medium). Conflicting Content-Length and Transfer-Encoding headers. Fixed in 2.11.0.
- GHSA-h4x7-gw46-3wm6 (CVE-2026-84379, medium). Multipart part header injection. Fixed in 2.11.0.
- GHSA-f2fp-rgf2-35cp (CVE-2026-84378, medium). Quadratic SSE line buffering. Fixed in 2.10.0.

anthropic 1.15.0, 1.17.0 and 2.1.0 each require `httpx2<3,>=2.0.0`. No anthropic release in this range forces a patched `httpx2`. GHSA-8xx6-hgc6-gc2m affects the plain response path that `messages.create` uses. The other four need WebSockets, multipart uploads or SSE streaming, and the harness uses none of them.

## Maintainer / org profile

- **Owner.** Anthropic (GitHub `anthropics`, account type Organization). Stainless generates most of the code. The top contributors are `stainless-app[bot]` (671), `stainless-bot` (341) and `anthropic-sdks-writer[bot]` (208).
- **Repository.** `https://github.com/anthropics/anthropic-sdk-python`. License Apache-2.0 on GitHub and on PyPI. 3,993 stars, 892 forks, 213 open issues. Not archived. The last commit is `9313f13a` on 2026-10-21 ("release: 2.1.0").
- **Human contributors in the top ten.** `RobertCraigie` (91), `dtmeadows-ant` (33), `dtmeadows` (32), `craigie-ant` (20), `mikelambert` (15), `karpetrosyan` (15). `claude[bot]` (44) is also in the list. Two account pairs probably belong to the same people (`RobertCraigie` and `craigie-ant`, `dtmeadows` and `dtmeadows-ant`). That is a guess from the names. The human set is still several people, backed by an org and a generator vendor.
- **Release cadence.** 19 releases in the 1.x line, from 1.0.0 on 2026-08-20 to 1.17.0 on 2026-10-20. The 2.x line began one day after 1.17.0.
- **Security policy.** `SECURITY.md` (773 bytes) routes reports to Anthropic's HackerOne program. It names no email contact.
- **Publishing provenance.** PyPI serves no provenance for `anthropic-1.15.0-py3-none-any.whl` or `anthropic-1.17.0-py3-none-any.whl`. The integrity endpoint answers "No provenance available". The openai SDK, from the same generator, ships PEP 740 attestations. This asymmetry is measured, not inferred.
- **Runtime dependencies at 1.17.0.** `anyio`, `docstring-parser`, `httpx2`, `jiter`, `opentelemetry-api`, `pydantic`, `sniffio`, `typing-extensions`. `docstring-parser` and `opentelemetry-api` are runtime dependencies that the openai SDK does not carry.

## High-risk surface analysis

Top-level resources under `src/anthropic/resources/` at tag v1.17.0:

```
beta  files.py  messages  models.py  organization  skills  user_profiles
```

Sub-resources under `src/anthropic/resources/beta/`:

```
agents  beta.py  deployment_runs.py  deployments.py  dreams.py  environments
files.py  memory_stores  messages  models.py  organization  sessions  skills
tunnels  user_profiles  vaults  webhooks.py
```

Helper modules under `src/anthropic/lib/` include `credentials`, `environments`, `sessions`, `middleware`, `streaming`, `tools`, `aws`, `bedrock`, `google_cloud` and `vertex`.

Helper modules under `src/anthropic/lib/tools/`:

```
_beta_builtin_memory_tool.py  _beta_functions.py  _beta_runner.py
_beta_session_runner.py  _file_store.py  _files.py  _memories.py  _skills.py
_tool_dispatch.py  _tool_params.py  _toolsets  agent_toolset.py  mcp.py
```

### Memory Tool and local-execution surfaces

The two CVEs above came from the local filesystem Memory Tool. That helper still ships in 1.x as `lib/tools/_beta_builtin_memory_tool.py`.

The 1.x line adds a wider local-execution surface. `lib/tools/agent_toolset.py` implements the `agent_toolset_20260401` tools: `bash`, `read`, `write`, `edit`, `glob` and `grep`. Its docstring says that `bash` "owns a persistent `/bin/bash` subprocess". It also says, "the file tools confine to `workdir` plus any `allowed_roots` (symlink-aware) and are safe without a sandbox; `bash` is unrestricted and should run inside one." The module is kept out of `anthropic.lib.tools.__init__` because it imports `subprocess`. A caller reaches it only through an explicit import. `import anthropic` does load `anthropic.lib.tools`, because `__init__.py` imports `beta_tool` and `beta_async_tool` from it. That import does not load `agent_toolset.py`.

Other 1.x additions in the same family, from the release notes: the session tool runner, MCP helpers and MCP tunnels (beta), Managed Agents with "auto mode tool permissions", memory stores, and "typed computer and browser toolset tool calls".

### Credential resolution

The 1.x line adds `lib/credentials`. The default `Anthropic()` constructor resolves credentials in this order, per its docstring at v1.17.0:

1. Explicit constructor arguments.
2. The `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` environment variable.
3. The `ANTHROPIC_PROFILE` environment variable, which loads `<config_dir>/configs/<profile>.json`.
4. Workload identity federation variables, including `ANTHROPIC_IDENTITY_TOKEN_FILE`.
5. The active profile on disk, named by `<config_dir>/active_config`, or `default`.

So the default constructor can read local files when no key is in the environment. The release notes add two defences: "refuse credentials files accessible by group or others" and "refuse config files that group or others can write".

### Deserialization paths

Responses parse through Pydantic, as in 0.x. The pydantic boundary rule recorded in the 2026-06-08 openai audit covers this surface. The harness also reads `tool_use.input` from model output. That input is untrusted data. The extractor and the judge each check its type with `isinstance` before they read any field.

### Harness path assessment

This audit read every anthropic call site in `src/` at `origin/main` `0bf00f9`. Three modules import `anthropic`, and each uses `import anthropic`:

- `src/skill_harness/ablation/subject.py`. `AnthropicSubjectClient` builds `anthropic.Anthropic()` at line 443 when no client is injected. At line 466 it calls `messages.create(model=..., max_tokens=..., system=system_blocks, messages=[...])`. It passes no tools. It catches `anthropic.APIStatusError` and `anthropic.APIConnectionError`, and it reads `response.content[].text` and `response.usage`.
- `src/skill_harness/extractor/claude.py`. `_make_extractor_client` builds `anthropic.Anthropic()` at line 268 when `ANTHROPIC_API_KEY` is set. When only `OPENROUTER_API_KEY` is set, it builds `anthropic.Anthropic(api_key=..., base_url="https://openrouter.ai/api/v1")` at line 278. At line 342 it calls `messages.create` with `tools=` and `tool_choice={"type": "tool", "name": "extract_clauses"}`. It catches `anthropic.APIError`.
- `src/skill_harness/oracles/tier2/judge.py`. `JudgeClient` builds `anthropic.Anthropic()` at line 196 when no client is injected. At line 436 it calls `messages.create` with `thinking={"type": "disabled"}`, one tool schema, and a forced `tool_choice` for `report_verdict`. The CLI checks for `ANTHROPIC_API_KEY` before it builds the judge (`src/skill_harness/cli/main.py`, near line 2789).

**This path reaches:** `resources/messages/` (`messages.create` only), `_client.py` with its credential resolution, `_base_client.py`, `_response.py`, `_models.py`, `_exceptions.py`, the `anthropic.types` param types, and the `httpx2` transport for non-streaming HTTPS requests.

The `tools=` parameter on the extractor and judge calls is a server-side tool definition. The model returns a `tool_use` block, and the harness parses its `input`. The SDK runs no tool code on this path.

**This path does not reach:** `client.beta.*`, `messages.tool_runner`, `lib/tools/_beta_runner.py`, `lib/tools/_beta_session_runner.py`, `lib/tools/_beta_builtin_memory_tool.py`, `lib/tools/agent_toolset.py`, `lib/tools/_file_store.py`, `lib/tools/mcp.py`, `lib/environments`, `lib/sessions`, `resources/files.py`, `resources/skills`, streaming helpers, or `count_tokens`. The harness `verbosity.py` module notes that it does not call `messages.count_tokens()`.

**One reached surface reads local files.** Each default `anthropic.Anthropic()` above runs the credential chain. When `ANTHROPIC_API_KEY` is set, the key wins and the profile files are not loaded. The constructor still checks for profile signals in the environment and on disk, so that it can warn when the key shadows a profile. When no key is set and the constructor runs anyway, the SDK can load a profile JSON or an identity-token file from disk. This is a file-reading surface on the harness path. It is not a write or execution surface. Its trust boundary is the operator's own config directory.

No harness call site reaches the Memory Tool, the agent toolset, a tool runner or any beta surface.

## Specific mitigations

### 1. Cap the anthropic range at <2

Change the pin from `anthropic>=1.15.0` to `anthropic>=1.15.0,<2`. Today the uncapped range resolves to 2.1.0, which is unaudited, and 2.0.0 is a breaking release. Keep the 1.15.0 floor. It sits well above the 0.87.0 fix for both Memory Tool CVEs. Update the `pyproject.toml` comment to cite this file. Raising the cap to `<3` needs a 2.x audit.

### 2. Keep a patched httpx2 installed

No anthropic release forces `httpx2>=2.12.0`. Today the openai pin keeps it patched only if its floor rises to 3.17.0 (see `openai-audit-2026-10-22.md`). Do one of these two things:

- Add a direct runtime pin `httpx2>=2.12.0` to `pyproject.toml`. This is a new direct dependency, so it is an ask-first change in this repository.
- Record in `SECURITY.md` that the openai floor is what enforces the `httpx2` fix, so that a later change to the openai pin does not drop it silently.

`requirements-ci.txt` has no `httpx2` or `httpcore2` line, so CI resolves them without a constraint. Today CI gets `httpx2` 2.16.0, which is past every fix. The next regeneration of that file must capture both.

### 3. Sub-surface exclusion for anthropic

The openai adapter in `subject.py` carries an import restriction. The anthropic call sites carry none. Record the same rule for anthropic. Harness code calls `messages.create` only. Importing or calling `anthropic.lib.tools` (the tool runners, the Memory Tool, `agent_toolset`, MCP helpers), `anthropic.lib.environments`, `anthropic.lib.sessions` or `client.beta.*` requires a new audit. A CI grep ban for `anthropic.lib.tools`, `agent_toolset`, `tool_runner` and `.beta.` in `src/` would enforce it.

### 4. Credential chain

When a harness command needs the Anthropic API, check for `ANTHROPIC_API_KEY` before building the client. The judge path already does this in the CLI. A missing key then fails fast and does not fall through to profile files on disk.

### 5. Pydantic boundary rule

No change. The existing rule covers response parsing and the `tool_use.input` payload.

## Deferrals

- **anthropic 2.x audit.** Out of scope for issue #732. The cap in mitigation 1 holds the range at 1.x until a 2.x audit runs.
- **Missing PyPI provenance.** anthropic wheels carry no PEP 740 attestation. This audit cannot verify that a wheel came from the GitHub release workflow. Re-check at the next audit. Raise it upstream if it stays absent.
- **Credential resolution internals.** This audit read the `_client.py` docstring and `_has_auto_discoverable_credentials` at v1.17.0. It did not read `lib/credentials` in full, including the file-mode checks.
- **`SECURITY.md` and the `pyproject.toml` comment.** Issue #732 steps 3 and 4 own these edits. `SECURITY.md` still states the old `>=0.87` pin.
- **Stainless pipeline integrity.** The 2026-06-08 deferral stands. One generator serves both LLM SDKs.
- **Re-audit triggers.** Re-audit on any of these: a proposal to raise the cap to admit 2.x, a new advisory on `anthropic` or `httpx2`, any harness use of a surface outside `messages.create`, or the quarterly calendar (next 2027-01-22).

## Citation verification

The Trail of Bits `supply-chain-risk-auditor` skill named in issue #732 is not installed in this environment. This audit was done by hand with `gh`, `curl` and Python. Every advisory ID in this file came from a query run in this session.

All fetches ran on 2026-10-22. The first batch completed at 17:42:24 UTC, and every later fetch ran after it on the same date.

- `curl https://pypi.org/pypi/anthropic/json`. Latest version 2.1.0. 19 releases in 1.x, from 1.0.0 to 1.17.0. Versions 2.0.0 and 2.1.0 exist. The wheel for 1.17.0 was uploaded at 2026-10-20T22:13:32Z. `requires_python >=3.10`. The runtime dependencies listed above.
- `curl https://pypi.org/pypi/anthropic/{1.15.0,1.17.0,2.1.0}/json`. Each declares `httpx2<3,>=2.0.0`.
- `curl https://pypi.org/integrity/anthropic/{1.15.0,1.17.0}/...-py3-none-any.whl/provenance`. Each returns "No provenance available".
- `gh api "/advisories?ecosystem=pip&affects=anthropic&per_page=100"`. Returns GHSA-w828-4qhx-vxx3 and GHSA-q5f5-3gjm-7mfm with CVE, severity, range and first patched version.
- `gh api "repos/anthropics/anthropic-sdk-python/security-advisories?per_page=100"`. The same two, state `published`.
- `curl -s https://api.osv.dev/v1/query -d '{"package":{"name":"anthropic","ecosystem":"PyPI"}}'`. Four records: the two GHSA IDs and PYSEC-2026-2114 and PYSEC-2026-2115, each with range 0.86.0 to 0.87.0.
- NVD REST API 2.0, `keywordSearch=anthropic%20python%20sdk` (CVE-2026-34450 and CVE-2026-34452) and `keywordSearch=anthropic-sdk-python` (zero).
- `gh api "/advisories?ecosystem=pip&affects=httpx2&per_page=100"` and the OSV query for `httpx2`. The five `httpx2` advisories above.
- `gh api repos/anthropics/anthropic-sdk-python`. Stars, forks, open issues, license, archive state, owner type.
- `gh api "repos/anthropics/anthropic-sdk-python/commits?per_page=1"`. Last commit `9313f13a`.
- `gh api "repos/anthropics/anthropic-sdk-python/contributors?per_page=10"`. The contributor counts above.
- `gh api repos/anthropics/anthropic-sdk-python/contents/SECURITY.md`. 773 bytes, HackerOne only.
- `gh api "repos/anthropics/anthropic-sdk-python/releases?per_page=30"`. The 1.x and 2.x release notes quoted above.
- `gh api "repos/anthropics/anthropic-sdk-python/contents/src/anthropic/resources?ref=v1.17.0"`, and the same for `resources/beta`, `lib` and `lib/tools`. The inventories above.
- `gh api "repos/anthropics/anthropic-sdk-python/contents/src/anthropic/lib/tools/agent_toolset.py?ref=v1.17.0"`. The docstring quoted above.
- `gh api "repos/anthropics/anthropic-sdk-python/contents/src/anthropic/_client.py?ref=v1.17.0"` and `lib/credentials/_constants.py`. The credential order above.
- `gh api "repos/anthropics/anthropic-sdk-python/contents/src/anthropic/__init__.py?ref=v1.17.0"`. The top-level import of `beta_tool` and `beta_async_tool` from `lib.tools`.
- Local reads at `origin/main` `0bf00f9`: `grep` over `src/` for `import anthropic` and `from anthropic`, then the call sites in `src/skill_harness/ablation/subject.py`, `src/skill_harness/extractor/claude.py`, `src/skill_harness/oracles/tier2/judge.py` and `src/skill_harness/cli/main.py` named above. Also `pyproject.toml` lines 25 to 45 and `requirements-ci.txt` lines 1 to 80.

### Timestamp check

This audit read PyPI JSON with `curl` and parsed it locally. The PyPI upload times match the GitHub release times within one minute. For example, v1.17.0 shows PyPI 2026-10-20T22:13:32Z and GitHub 2026-10-20T22:13:01Z.
