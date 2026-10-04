# #722: rename the domain glossary to GLOSSARY.md

skill-harness's domain glossary carries the name Pocock v1.3.1 reads. A reader
following any live pointer to the glossary lands on `GLOSSARY.md`.

Parent: research-repo ticket #403 (v1.3 migration; facts at comment
5983509597; the parent lives in the owner's research repository, not in
skill-harness). This PR does not merge before the upgrade-window ticket: the
merge happens in that window so no session runs half-migrated.

## Acceptance criteria

### 1. `CONTEXT.md` renamed to `GLOSSARY.md` with `git mv`; title names the glossary; content otherwise unchanged

Built: `git mv CONTEXT.md GLOSSARY.md` on commit `0175b30`. The title line is
now `# GLOSSARY.md — skill-harness`. Every other byte is unchanged: body
sha256 `d8179d5194856d82f9a7ebef77eebbc78730d0b52bc0a24f6ddd6a40ebdd532e`
over the 67 body lines, matching the pre-rename file. Git records the move as a
rename (`rename CONTEXT.md => GLOSSARY.md (99%)`), not a delete-plus-add.

Pinned by `tests/test_glossary_rename_722.py`:

- `test_glossary_exists_and_context_is_gone`
- `test_glossary_title_names_the_glossary`
- `test_glossary_body_is_unchanged`
- `test_glossary_body_keeps_the_glossary_entries`
- `test_git_history_records_a_rename`

Red phase: all five failed. `test_glossary_exists_and_context_is_gone` raised
`FileNotFoundError: GLOSSARY.md` (and would also have caught a leftover
`CONTEXT.md`). `test_glossary_title_names_the_glossary` and the body tests
failed on the missing file. `test_git_history_records_a_rename` failed because
no rename was staged or committed. Green after `0175b30`.

### 2. `docs/agents/domain.md` replaced with the v1.3.1 setup template

Built: `docs/agents/domain.md` is now byte-identical to
`skills/engineering/setup-matt-pocock-skills/domain.md` at
`github.com/mattpocock/skills` tag `v1.3.1` (sha256
`593a7042218689f1d24df89df14eaf0a20e19e0d0a7d479a01947ac78f0784b9`, 2042
bytes). The template names `GLOSSARY.md` and `GLOSSARY-MAP.md`. This repo
carries no local additions in that file: #677 aligned it verbatim to an earlier
template, and the only delta that matters is the v1.3.1 rename plus the
template's own punctuation updates (colon where the old file had an em dash).
The vendored template copy lives at
`tests/fixtures/domain-docs/setup-matt-pocock-skills-domain-v1.3.1.md`.

Pinned by `test_domain_doc_is_the_v1_3_1_setup_template` (byte equality to the
vendored template plus the pinned digest) and
`test_domain_doc_names_glossary_not_context` (names the new files, not the old).

Red phase: both failed. The file still named `CONTEXT.md` / `CONTEXT-MAP.md`
and its digest did not match the v1.3.1 template. Green after `42c6e59`.

### 3. Live references to `CONTEXT.md` name `GLOSSARY.md`

Built: `AGENTS.md` lines 17 and 19 now name `GLOSSARY.md`. The domain-doc
consumer guide names `GLOSSARY.md` throughout (covered by criterion 2). No other
instruction surface referenced the old name: `tests/`, `src/`, `scripts/`,
`.github/workflows/`, README, CONTRIBUTING, DESIGN, PRODUCT, SECURITY, and the
ADR directory did not carry a live pointer. CHANGELOG entries stay as written.

Pinned by `test_agents_md_names_the_glossary_not_context` and
`test_no_live_file_still_names_context_md`.

Red phase: `test_agents_md_names_the_glossary_not_context` failed because
`AGENTS.md` still said `CONTEXT.md` on both lines. `test_no_live_file_still_names_context_md`
listed `AGENTS.md` as an offender. Green after `77934ef`.

### 4. `grep -rn "CONTEXT\.md"` over live files returns nothing; remaining hits listed as dated records

Built: every tracked live file outside `CHANGELOG.md` is free of the old
glossary path. The test module constructs the old name as `"CONTEXT" + ".md"`
so the pin does not name the token it forbids. Remaining hits, each a dated
record or the rename announcement itself:

| File:line | Text | Why it stays |
| --- | --- | --- |
| `CHANGELOG.md:19` | `- **The domain glossary is renamed from \`CONTEXT.md\` to \`GLOSSARY.md\`** (#722).` | The criterion-5 announcement. A rename entry must state both paths. CHANGELOG is the release-convention surface, not a live instruction pointer. |
| `CHANGELOG.md:280` | `- **Docs of record:** \`CONTEXT.md\` domain glossary wired as the vocabulary of record;` | Dated record in the 0.3.0-era section. The ticket says CHANGELOG entries stay as written. |

`CHANGELOG.md` is the only remaining hit surface. The test allowlists it as a
dated-record file and asserts zero hits everywhere else.

Pinned by `test_no_live_file_still_names_context_md`. Red phase: it listed
`AGENTS.md` (and, before criterion 2, `docs/agents/domain.md`) as offenders.
Green after `77934ef`.

### 5. CHANGELOG entry announces the rename, per this repo's release convention

Built: `CHANGELOG.md` `[Unreleased]` → `### Changed` carries
`- **The domain glossary is renamed from \`CONTEXT.md\` to \`GLOSSARY.md\`** (#722).`
The entry names both paths, states that the move is a `git mv`, and records
that existing CHANGELOG entries that name the old path stay as written. The
repo's convention is Keep a Changelog under `## [Unreleased]`, rolling to
`## [X.Y.Z] - YYYY-MM-DD` at the tag; `scripts/release_gate.py` G2 reads that
surface.

Pinned by `test_changelog_announces_the_rename` (the `[Unreleased]` section
must contain both names and rename language). Red phase: it failed because
`[Unreleased]` carried no `GLOSSARY.md` announcement. Green after `77934ef`.

### 6. Do not merge before the upgrade-window ticket

No code work. This PR is left unmerged. The merge happens in the upgrade window
so no session runs half-migrated.

## Which test covers which criterion

| Criterion | Test(s) in `tests/test_glossary_rename_722.py` |
| --- | --- |
| 1 rename, title, unchanged body | `test_glossary_exists_and_context_is_gone`, `test_glossary_title_names_the_glossary`, `test_glossary_body_is_unchanged`, `test_glossary_body_keeps_the_glossary_entries`, `test_git_history_records_a_rename` |
| 2 v1.3.1 domain template | `test_domain_doc_is_the_v1_3_1_setup_template`, `test_domain_doc_names_glossary_not_context` |
| 3 live pointers name GLOSSARY.md | `test_agents_md_names_the_glossary_not_context`, `test_domain_doc_names_glossary_not_context` |
| 4 live-file grep clean | `test_no_live_file_still_names_context_md` |
| 5 CHANGELOG announcement | `test_changelog_announces_the_rename` |
| 6 merge-window | none (process constraint; not merged) |

## Gate

Run on this branch before each commit, and again after the last:

- `ruff check src tests scripts` — pass
- `ruff format --check src tests scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py` — pass
- `mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py` — pass, 387 source files
- `python scripts/drift_check.py` — `DRIFT CHECK: PASS - all 22 live contracts hold.`
- `python scripts/release_gate.py` — `RELEASE GATE: PASS (7 of 8 gates ran; skipped G6)`
- `pytest tests/test_glossary_rename_722.py tests/test_structural_bans.py tests/test_receipts_index.py` — pass
- `pytest` over the non-live top-level test modules — pass

No mutation campaign: the ticket names no mutation receipt, and no
`scripts/mutation_receipt.py --select` obligation is registered for this change.
The pins above are behavioural: file existence, byte digests, git rename
summary, tracked-file scan, and CHANGELOG section content.

## Registry note

`tests/test_receipts_index.py` enumerates six receipt directories under `docs/`
(`case-studies`, `findings`, `observations`, `assurance`, `ratifications`,
`sers/receipts`). Neither `GLOSSARY.md` (repo root) nor `docs/agents/domain.md`
nor `tests/fixtures/domain-docs/` is a registered receipt directory. No
`docs/receipts-index.md` entry is required. Companion artifacts this PR cites:
issue `#722` (this ticket); parent research-repo ticket #403 (named in the
ticket text; not readable from this container); template tag `v1.3.1` at
`github.com/mattpocock/skills` (fetched over HTTPS, vendored under
`tests/fixtures/domain-docs/`). No upgrade-window ticket number was supplied in
the ticket text; it does not exist yet in this container's record.
