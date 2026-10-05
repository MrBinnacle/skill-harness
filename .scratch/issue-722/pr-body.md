# #722: rename the domain glossary to GLOSSARY.md (v1.3.1 name)

## Summary

skill-harness's domain glossary now carries the name Pocock v1.3.1 reads. `CONTEXT.md` was renamed to `GLOSSARY.md` with `git mv` in commit `0175b30`; the cumulative diff from `origin/main` shows `rename CONTEXT.md => GLOSSARY.md (99%)` with only the title line changed. `docs/agents/domain.md` is replaced with the v1.3.1 `setup-matt-pocock-skills` template. Live instruction surfaces name `GLOSSARY.md`. The rename is announced under CHANGELOG `[Unreleased]`. This rework round repaired the CI-red depth-1 test pin and regenerated this evidence body.

Branch tip for the counts below: `feb87ea`.

## Files changed

`git diff --name-only origin/main...HEAD` at `feb87ea` (7 files; `git diff --stat origin/main...HEAD`: 7 files changed, 292 insertions(+), 14 deletions(-)):

- `AGENTS.md`
- `CHANGELOG.md`
- `GLOSSARY.md`
- `docs/agents/domain.md`
- `tests/fixtures/domain-docs/context-md-body-base.json`
- `tests/fixtures/domain-docs/setup-matt-pocock-skills-domain-v1.3.1.md`
- `tests/test_glossary_rename_722.py`

## Acceptance criteria

### AC1: `CONTEXT.md` is renamed to `GLOSSARY.md` with `git mv` (history preserved); its title line names the glossary; content otherwise unchanged

**What satisfies it:** Commit `0175b30` ran the rename as `git mv`. At `feb87ea`, `git diff -M origin/main...HEAD --summary` reports `rename CONTEXT.md => GLOSSARY.md (99%)`. The only content delta is the title line: `# CONTEXT.md — skill-harness` became `# GLOSSARY.md — skill-harness`. The body after that title line has sha256 `d8179d5194856d82f9a7ebef77eebbc78730d0b52bc0a24f6ddd6a40ebdd532e`, identical to `origin/main`'s `CONTEXT.md` body after its title line. That base body is stored at `tests/fixtures/domain-docs/context-md-body-base.json` so a depth-1 checkout can pin it without `git log --follow`.

**Tests that pin it:** `test_glossary_exists_and_context_is_gone`, `test_glossary_title_names_the_glossary`, `test_glossary_body_is_unchanged`, `test_glossary_body_keeps_the_glossary_entries`, `test_rename_body_matches_base_fixture`.

**Observation:** Against a checkout of `origin/main` (no rename), those five fail: `GLOSSARY.md` is absent; the title line still names the old path; the body pin and the term inventory cannot be read from the new path. Before this rework round, the branch's git-history rename pin failed on CI because every CI checkout uses `fetch-depth: 1` and `git log --follow` sees no rename there (review comment 5984831762: 1 failed, 3845 passed on `Test (ubuntu-latest · py3.12)`). This rework replaced that pin with `test_rename_body_matches_base_fixture`, which asserts only depth-1-safe facts: `GLOSSARY.md` exists, the old path does not, and the body after the title line equals the base fixture. On a `--depth 1` clone of this branch the new test passes. I watched it fail for the right reason when the body was mutated on that clone (`**Skill**:` became `**Skill (mutated)**:`), and pass again after restore.

### AC2: `docs/agents/domain.md` is the v1.3.1 setup template, with this repo's existing local additions kept

**What satisfies it:** `docs/agents/domain.md` is byte-identical to the vendored copy at `tests/fixtures/domain-docs/setup-matt-pocock-skills-domain-v1.3.1.md`, which is `skills/engineering/setup-matt-pocock-skills/domain.md` from `github.com/mattpocock/skills` at tag `v1.3.1`. This repo carries no local additions in that file; the template is the whole content.

**Test that pins it:** `test_domain_doc_is_the_v1_3_1_setup_template` (byte compare against the vendored fixture, plus a pinned sha256).

**Observation:** Against `origin/main`, that test fails — `docs/agents/domain.md` still used the pre-v1.3.1 wording that named the old glossary path. After commit `42c6e59` landed the template, the test passes on this branch; this rework kept it green.

### AC3: Every live reference to the old glossary name names `GLOSSARY.md`

**What satisfies it:** `AGENTS.md` lines 17 and 19 name `GLOSSARY.md`. `docs/agents/domain.md` names `GLOSSARY.md` on every instruction line that points a reader at the glossary. No other live instruction surface still points at the old path.

**Tests that pin it:** `test_agents_md_names_the_glossary_not_context` and `test_no_live_file_still_names_context_md`.

**Observation:** Against `origin/main`, both fail — `AGENTS.md` still names the old path on both live lines, and the live-file scan lists `AGENTS.md`, `CONTEXT.md`, and `docs/agents/domain.md` as offenders. After commit `77934ef` named `GLOSSARY.md` on the live surfaces, both tests pass on this branch; this rework kept them green.

### AC4: `grep -rn "CONTEXT.md"` over live files returns nothing; this body lists every remaining hit with the reason it is a dated record

**What satisfies it:** At `feb87ea`, `grep -rn "CONTEXT.md"` over tracked files returns hits only in `CHANGELOG.md`. Those hits are dated records (listed below) and stay as written. `test_no_live_file_still_names_context_md` allowlists `CHANGELOG.md` and fails if any other tracked live file still names the old path.

**Test that pins it:** `test_no_live_file_still_names_context_md`.

**Observation:** Against `origin/main`, that test fails and names three offenders: `AGENTS.md`, `CONTEXT.md`, and `docs/agents/domain.md`. After this branch renamed the glossary, updated the live surfaces, and reworded the base-body fixture so its description does not carry the old token, the scan passes. A first pass of this rework failed the scan because the JSON fixture description named the old path; commit `feb87ea` reworded it to "pre-rename domain glossary" and the scan went green.

**Remaining hits (dated records):**

| Hit | Why it stays |
| --- | --- |
| `CHANGELOG.md:19` | The `[Unreleased]` announcement of this rename. It must name both the old and the new path to state what changed. |
| `CHANGELOG.md:280` | Pre-#722 historical entry: "Docs of record: `CONTEXT.md` domain glossary wired as the vocabulary of…" from an earlier release range. The ticket keeps dated CHANGELOG records as written. |

### AC5: A changeset or CHANGELOG entry announces the rename, per this repo's release convention

**What satisfies it:** `CHANGELOG.md` under `## [Unreleased]` → `### Changed` carries: "**The domain glossary is renamed from `CONTEXT.md` to `GLOSSARY.md`** (#722)." The entry names the mechanism (a `git mv` with the title line as the only content change), the consequence (a reader following any live pointer now lands on `GLOSSARY.md`), and the dated-record exception for existing CHANGELOG entries.

**Test that pins it:** `test_changelog_announces_the_rename`.

**Observation:** Against `origin/main`, that test fails — `[Unreleased]` has no rename entry and does not name `GLOSSARY.md`. After commit `77934ef` added the announcement, the test passes on this branch; this rework kept it green.

### AC6: Do not merge before the upgrade window ticket

**What satisfies it:** Operational, not test-pinned. This PR must not merge before the upgrade-window ticket. The merge happens in that window so no session runs half-migrated.

## Rework-round checks

- **Depth-1 CI pin (F1):** Replaced the branch's git-history rename pin with `test_rename_body_matches_base_fixture`. No shallow-clone skip. No workflow `fetch-depth` change. Local CI-equivalent suite at `feb87ea`: `PYTHONHASHSEED=0 pytest -q -n 4 -m "not live and not calibration and not assurance" --ignore=tests/test_ci_geometry_cell_589.py` → **3834 passed, 40 skipped, 2 xfailed**. Gate: `ruff check src tests scripts`, `ruff format --check src tests scripts`, `mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py` all green.
- **Evidence body (F2, F3):** This body names only tests that exist in `tests/test_glossary_rename_722.py` (9 tests). Every file listed exists in `git diff --name-only origin/main...HEAD` at `feb87ea`. Every count above was taken by command at that head. No earlier-round disagreement text remains.

## Test-to-criterion map

| Criterion | Test(s) in `tests/test_glossary_rename_722.py` |
| --- | --- |
| AC1 | `test_glossary_exists_and_context_is_gone`, `test_glossary_title_names_the_glossary`, `test_glossary_body_is_unchanged`, `test_glossary_body_keeps_the_glossary_entries`, `test_rename_body_matches_base_fixture` |
| AC2 | `test_domain_doc_is_the_v1_3_1_setup_template` |
| AC3 | `test_agents_md_names_the_glossary_not_context`, `test_no_live_file_still_names_context_md` |
| AC4 | `test_no_live_file_still_names_context_md` |
| AC5 | `test_changelog_announces_the_rename` |
| AC6 | none (operational) |

## Next action

Merge only in the upgrade window of the parent v1.3 migration ticket (#403). Do not merge before that window.
