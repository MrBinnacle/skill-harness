# Issue #733 — CHANGELOG [Unreleased] records the user-visible range since v0.3.0

## What this PR does

It rewrites the `[Unreleased]` section of `CHANGELOG.md` so that every
user-visible change in `v0.3.0..HEAD` is recorded under the right heading,
related commits are grouped, and internal test/CI/docs-only commits are omitted
unless they change a published surface. It drops the stale commit-count
sentence, records every changed runtime floor and the new `geometry` extra at
the values `pyproject.toml` declares at the PR head, and adds one
reader-facing line each for SERS 1.6.0 and SERS 1.7.0. The 0.4.0 heading is
not cut here; the version PR rolls the section.

It also adds `tests/test_changelog_unreleased_733.py`, which pins those
behaviours against the live `CHANGELOG.md` and `pyproject.toml`.

## Acceptance criteria

### Criterion 1 — PR body table of every commit in `v0.3.0..HEAD`

Satisfied by the table below. `git rev-list --count v0.3.0..HEAD` at the PR
head is **213** (not 133, not the 207 measured at `origin/main=b48ee47`;
six commits landed after that evidence snapshot). Every row names either the
CHANGELOG line that covers it or the reason it needs none.

Spot-check rows a verifier can jump to: `c879633` (SERS 1.6.0), `bd3467c`
(SERS 1.7.0 + ledger), `a9fb533` (ingest fix), `6505b42` (Stage 1A reader),
`e235bc6` (urllib3 CVE), `3f8d4a90` (claim-level ladder), `ef69c192`
(delivered surface), `2787c13c` (random-half arm), `4d9e6d5b` (anthropic
floor), `a8ee4d7d` (openai floor), `2396b3ed` (click floor), `ca4d49bd`
(statsmodels floor), `8260d27f` (geometry extra), `ef68b56c` (glossary
rename), `03ee27d3` (BREAKING rename), `bda56e55` (Layer 3, already under
Fixed).

### Criterion 2 — `[Unreleased]` no longer contains "133"

Dropped. The sentence now reads "This section records the user-visible changes
on `main` since v0.3.0." The count is stated once, above, with the command
that produced it.

Pinned by `tests/test_changelog_unreleased_733.py::test_unreleased_carries_no_stale_commit_count`.
Observed red on the pre-change CHANGELOG (the sentence was still there);
observed green after the rewrite.

### Criterion 3 — runtime floors and the geometry extra match `pyproject.toml` at the PR head

Recorded under Changed:

- `anthropic>=1.11.0` (was `>=1.2.0`)
- `openai>=3.15.0,<4` (was `>=2.41,<4`)
- `click>=8.5.0` (was `>=8.1`)
- `scipy>=1.18.1` (was `>=1.11`)
- `statsmodels>=0.15.0` (was `>=0.14`)

Recorded under Added:

- `[geometry]` extra: `pip install "skill-harness[geometry]"` pulls
  `playwright>=1.63.0`

**Discrepancy on the ticket's anthropic figure.** The acceptance text names
`anthropic>=1.8.0`. That figure was measured at `origin/main=b48ee47`. This
branch's `pyproject.toml` at the PR head declares `anthropic>=1.11.0`
(bumped again in `4d9e6d5b`, #727). The governing rule in the Desired
behaviour section is "with its value as declared in `pyproject.toml` at the
PR head", and the acceptance criterion itself says the lines must match
`pyproject.toml` at the PR head. This PR records `anthropic>=1.11.0`. The
test reads `pyproject.toml` at run time and asserts the CHANGELOG matches it,
so the pair cannot drift.

Pinned by
`tests/test_changelog_unreleased_733.py::test_unreleased_records_every_changed_runtime_floor`
and
`tests/test_changelog_unreleased_733.py::test_unreleased_records_the_geometry_extra`.
Observed red before the rewrite (no floor lines, no geometry extra); observed
green after.

### Criterion 4 — SERS 1.6.0 and 1.7.0 appear in the SERS lines

Both appear under Added, each with one line on what a receipt reader must
handle:

- **1.6.0** (`c879633`, #654; finished `282a5064`, #660): three optional
  top-level objects absent on pre-1.6.0 receipts — `verdict_scope`
  (required on a 1.6.0 KEEP), `currentness` (VALIDATED / CARRIED_FORWARD /
  STALE), `drift_policy`.
- **1.7.0** (`bd3467c`, #686; ladder fields `3f8d4a90`, #671): a 1.7.0 KEEP
  carries a required `multiplicity` object and
  `verdict_scope.control_world_result == "pass"`; a 1.7.0 CUT must not carry
  `multiplicity`. KEEP receipts gain `designer`, `designer_independent`,
  `family_replication`, `model_replication`, `claim_level`.

Pinned by
`tests/test_changelog_unreleased_733.py::test_unreleased_records_sers_1_6_0_and_1_7_0`
and a companion pin on the schema enum
(`test_sers_schema_enum_still_ends_at_1_7_0`). Observed red before the
rewrite; observed green after.

### Criterion 5 — release gate and CI matrix

Measured in this container at the PR head, on a healthy workspace mount.

Gate commands run before every commit, in this order:

| Command | Result |
|---|---|
| `ruff check src tests scripts` | All checks passed. |
| `ruff format --check src tests scripts` | 432 files already formatted. |
| `mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py` | Success: no issues found in 389 source files. (Note: mypy reports unused override sections for `inspect_swe.*`, `playwright`, `yaml.*` — a pre-existing note, not an error.) |
| `python scripts/release_gate.py` | `RELEASE GATE: PASS (7 of 8 gates ran; skipped G6), public surfaces in lockstep at version 0.3.0.` G6 self-skips because this local run is not on a tag ref. |
| `python scripts/drift_check.py` | `DRIFT CHECK: PASS - all 22 live contracts hold.` CHANGELOG.md is on the DC-16 exclusion list (immutable record). |
| `tests/test_changelog_unreleased_733.py` + `tests/test_glossary_rename_722.py` | 15 passed. |
| `tests/test_structural_bans.py` | 28 passed. |

Full CI matrix (multi-Python, geometry browser cell, live API cell) is not
reproducible in this container. The local evidence is the release gate, the
lint/type gate on the tree, drift-check, structural bans, and the 15
CHANGELOG/glossary tests.

## Test that pins each criterion

| Criterion | Test | Fails without the change? |
|---|---|---|
| 2 | `test_unreleased_carries_no_stale_commit_count` | Yes — "133" still in the section on the pre-change CHANGELOG |
| 3 (floors) | `test_unreleased_records_every_changed_runtime_floor` | Yes — no floor lines on the pre-change CHANGELOG |
| 3 (geometry) | `test_unreleased_records_the_geometry_extra` | Yes — no geometry extra on the pre-change CHANGELOG |
| 4 | `test_unreleased_records_sers_1_6_0_and_1_7_0` | Yes — 1.6.0/1.7.0 absent on the pre-change CHANGELOG |
| 4 (companion) | `test_sers_schema_enum_still_ends_at_1_7_0` | No — schema already had the enum; pins the companion surface |
| Desired (no 0.4.0 cut) | `test_unreleased_does_not_cut_the_0_4_0_heading` | No — heading was never cut |
| 5 | `python scripts/release_gate.py` | Passes before and after; not a CHANGELOG-content gate |

Fail-before observation (this session): `git checkout HEAD -- CHANGELOG.md`
restores the committed pre-change section, which still says "the 133 commits
on `main` since v0.3.0" and carries no floor lines, no geometry extra and no
SERS 1.6.0/1.7.0 lines. Against that tree, four tests in
`tests/test_changelog_unreleased_733.py` fail (`test_unreleased_carries_no_stale_commit_count`,
`test_unreleased_records_every_changed_runtime_floor`,
`test_unreleased_records_the_geometry_extra`,
`test_unreleased_records_sers_1_6_0_and_1_7_0`) and two pass
(`test_unreleased_does_not_cut_the_0_4_0_heading`,
`test_sers_schema_enum_still_ends_at_1_7_0`). After restoring the rewritten
CHANGELOG, all six pass.

Existing test kept green, not edited:
`tests/test_glossary_rename_722.py::test_changelog_announces_the_rename` —
requires exactly one `[Unreleased]` bullet naming both `GLOSSARY.md` and
the pre-rename glossary path with rename language. The rewrite keeps that
bullet unchanged.

## Mutation campaign

Hand-run against the live `CHANGELOG.md` on this branch (the ticket names no
`scripts/mutation_receipt.py` obligation, so no `docs/assurance/` receipt is
written). Each mutant was applied to the file, the full
`tests/test_changelog_unreleased_733.py` module run, and the file restored.
Baseline before each campaign: 6 passed. After restore: 6 passed.

| Mutant | Applied | Killed by | Observed |
|---|---|---|---|
| Reintroduce the stale `133 commits` sentence | Yes | `test_unreleased_carries_no_stale_commit_count` | FAILED as required |
| Delete the whole `[geometry]` extra bullet | Yes | `test_unreleased_records_the_geometry_extra` | FAILED as required |
| Delete the SERS 1.6.0 bullet | Yes | `test_unreleased_records_sers_1_6_0_and_1_7_0` | FAILED as required |
| Delete the SERS 1.7.0 bullet | Yes | `test_unreleased_records_sers_1_6_0_and_1_7_0` | FAILED as required |
| Rewrite `anthropic>=1.11.0` to the stale `anthropic>=1.8.0` | Yes | `test_unreleased_records_every_changed_runtime_floor` | FAILED as required |
| Delete the `anthropic` floor line | Yes | `test_unreleased_records_every_changed_runtime_floor` | FAILED as required |
| Delete the `click>=8.5.0` floor line | Yes | `test_unreleased_records_every_changed_runtime_floor` | FAILED as required |
| Cut `## [0.4.0] - 2026-10-07` in place of `[Unreleased]` | Yes | `test_unreleased_does_not_cut_the_0_4_0_heading` (plus content pins that then leave the section) | FAILED as required |

After restore, all six tests in `test_changelog_unreleased_733.py` and the
glossary rename module (15 tests total across both modules) pass.

## Commit table — every commit in `v0.3.0..HEAD`

Legend for the Coverage column:

- `Changed — <name>` / `Added — <name>` / `Fixed — <name>`: the named
  `[Unreleased]` bullet covers it.
- `Internal — <reason>`: needs no user-visible line, with the reason.

Verified: the table has 213 rows; `git rev-list v0.3.0..HEAD` has 213
commits; the 8-character prefixes of the two sets are equal.

| Commit | Subject | Coverage |
|---|---|---|
| b477983b | docs(assurance): amended pre-registration for the EB-MoM peel (#360) | Internal — assurance docs |
| e50f112f | feat(aggregation): identify heterogeneity before fitting a hyperprior (#360) | Internal — EB-MoM rebuild; one visible consequence is the BREAKING rename |
| e260c6f5 | fix(aggregation): correct the null, the oracle and the bias collection (#360) | Internal — EB-MoM rebuild |
| f7ca1016 | test(assurance): mechanized mutation receipt (#360) | Internal — test/receipt only |
| 03305454 | fix(test): provenance field null_encoded_mean (#360) | Internal — test only |
| d836319c | docs(assurance): mutation receipt (#360) | Internal — assurance docs |
| 928325f7 | docs(assurance): stop overloading "estimand" (#360) | Internal — docs |
| 7d50b4a7 | docs(receipts-index): mutation entry (#360) | Internal — docs registry |
| b9099fe9 | fix(aggregation): heterogeneity target encoded mean (#360) | Internal — EB-MoM rebuild |
| 12df62f5 | docs(receipts-index): amendment entry (#360) | Internal — docs registry |
| 4bd46331 | docs(assurance): mutation receipt re-run (#360) | Internal — assurance docs |
| 6d6835a6 | docs(assurance): confirmatory run stub step 3 (#360, #405) | Internal — assurance docs |
| 5fa03c59 | docs(assurance): confirmatory run stub step 4 (#360, #405) | Internal — assurance docs |
| 13f0fbb5 | docs(assurance): confirmatory run REJECTED at R=1000 (#360, #405) | Internal — assurance docs; named in Internal section |
| e11e4e25 | docs(assurance): superseding pre-registration v2 DRAFT (#360, #405) | Internal — assurance docs |
| ec63e9be | docs(assurance): v2 section 0.4 measured (#360) | Internal — assurance docs |
| 20582960 | docs(assurance): section 0.6 mechanism class 2 (#360) | Internal — assurance docs |
| b6176b42 | docs(assurance): v2 section 4 S414 ruling (#360) | Internal — assurance docs |
| 397e840e | docs(assurance): v2 FREEZES on mechanism class 2 (#360) | Internal — assurance docs; named in Internal section |
| e3228764 | docs(assurance): vendor class-2 prototype (S414) | Internal — assurance docs |
| d0eb3bf7 | merge: bring agent/issue-360 level with main (#440) | Internal — merge |
| 569c1e1f | merge: bring agent/issue-360 level with main (#440) | Internal — merge |
| e69954e6 | docs(receipts): index ebmom-peel files (#184) | Internal — docs registry |
| d39440d8 | feat(aggregation): refused fit pools at admission bound (#441) | Changed — BREAKING bounded_pooling_refused |
| a7d94176 | docs(assurance): mutation receipt v2 §7 mutant 1 (#441) | Internal — assurance docs |
| 60a65488 | feat(aggregation): admitted fit integrates over hyperprior (#442) | Internal — EB-MoM rebuild; numbers may move, rename is the visible BREAKING |
| 0eac5f01 | docs(assurance): mutation receipt v2 §7 mutant 4 (#442) | Internal — assurance docs |
| 52ee261f | fix(deps): numpy stays out of runtime manifest (#442) | Fixed — numpy stays out of the runtime manifest |
| 3415f3eb | docs(assurance): v2 section 9 S417 ruling (#442) | Internal — assurance docs |
| 85ed54bb | feat(aggregation): acceptance matrix v2 per-path rows (#443) | Internal — assurance harness |
| 9d381c8a | feat(aggregation): reproduction reports port identity (#443) | Internal — assurance harness |
| 21f86365 | test(assurance): mutants 2 and 3 join receipt registry (#443) | Internal — test/receipt |
| 9a81e83e | test(assurance): mutant 2 control must survive (#443) | Internal — test only |
| 16da76bb | docs(assurance): mutation receipt v2 §7 mutant 2 (#443) | Internal — assurance docs |
| cbea9817 | docs(assurance): mutation receipt v2 §7 mutant 3 (#443) | Internal — assurance docs |
| 8cdda6ff | feat(assurance): emit receipt identities of amendment §8 (#443) | Internal — assurance harness |
| a8b90681 | docs(assurance): R=1000 and R=4000 reproductions (#443) | Internal — assurance docs |
| 43482752 | docs(assurance): regenerate CONFOUNDED receipt (#444) | Internal — assurance docs |
| 142fb7da | fix(assurance): EB-MoM gate generator emits target_digests (#444) | Internal — assurance harness |
| 36dcc228 | docs(assurance): re-run seven EB-MoM gate mutants (#444) | Internal — assurance docs; named in Internal section |
| 2cbb071d | docs(assurance): re-run v2 reproductions, index §7 mutants (#444) | Internal — assurance docs |
| d2d31a77 | docs(receipts): index §7 mutation index (#444) | Internal — docs registry |
| 7b083874 | fix(scripts): remove wall time from v2 receipt (#452) | Internal — scripts |
| 3fe50717 | Merge pull request #454 | Internal — merge |
| 0a308252 | docs: README run-ablation snippet ratification flags (#461) | Fixed — README snippet shows what `run ablation --execute` requires |
| b6ac69c1 | feat(prose): lines bind to words_to_avoid list (#470) | Internal — drift-check prose guard |
| 8dab4d39 | fix(docs): dry-run claim scoped to spending subcommand (#472) | Fixed — dry-run claim scoped to the subcommand that spends |
| b06272a6 | fix(drift-check): DC-16 selects tracked set (#471/#473) | Fixed — DC-16 selects the tracked set |
| 16bfaf69 | docs(readme): greenfield rewrite (S425) (#474) | Internal — docs-only README rewrite; PyPI description recorded separately under #497 |
| 2b81f15f | ci(deps): bump actions/deploy-pages (#468) | Internal — CI action pin |
| 95c88e19 | chore(deps): bump anthropic-stack (#463) | Changed — dependency floors (path to 1.11.0) |
| 33fec50b | chore(deps): bump coverage (#464) | Internal — dev/CI dep |
| 72946fe6 | chore(deps): bump openai 3.3.1→3.8.0 (#466) | Changed — dependency floors (path to 3.15.0) |
| b1972e3f | test(deps): assert pinning property (#475) | Internal — test only |
| 26328516 | chore(deps): bump pydantic pair (#476) | Internal — dep floors did not move in pyproject |
| 31778c48 | chore(deps): bump pytest-randomly (#467) | Internal — dev extra |
| 26915968 | design(banner): statement line replaces readout (#309/#477) | Internal — design snapshot |
| 43a2d7c5 | docs(context): define population integrity (#480) | Internal — glossary (pre-rename the pre-rename glossary path) |
| db3a688d | Two tests reported environment as code failure (#484) | Fixed — tests report environment correctly |
| 466e6293 | fix(design): design snapshot describes banner main draws (#481) | Fixed — design snapshot |
| 6225c665 | fix(assurance): frozen class-2 reference runnable (#458) | Fixed — frozen class-2 reference is runnable |
| 7c4d6c04 | docs(assurance): state the cost (#458) | Internal — assurance docs |
| 900002f1 | docs(receipts): index frozen R40 form-B receipt (#458) | Internal — docs registry |
| c398cca4 | feat(sers): split subject and extractor model roles 1.4.0 (#487) | Added — SERS 1.4.0 |
| 1a5027af | fix(hazard): count hazard entry per simple command (#438/#491) | Changed — paired-gate2 refuses undecided epochs |
| 5acbad68 | Merge pull request #489 | Internal — merge |
| 8a4e18ee | docs(findings): hazard entry not a prompt lever (#419/#486) | Internal — findings doc |
| 0274dd1a | Path C: tie-bearing decisions through Gate-2 discordant rule (#368/#493) | Changed — Tie-bearing ablation clause decisions |
| 6d7dd55f | chore: remove 14 agent PR bodies under .scratch/ (#494) | Internal — factory cleanup |
| 4d65e301 | feat(subject): Pi paired subject lane adapter | Added — pi-paired |
| 76f36baf | test(assurance): register Pi-adapter refusal predicates | Internal — mutation registration |
| 24773246 | docs(assurance): mutation receipt Pi-adapter | Internal — assurance docs |
| 9dc7a4ed | feat(subject): Pi paired lane production driver | Added — pi-paired |
| 4e535743 | docs(assurance): regenerate Pi mutation receipt | Internal — assurance docs |
| b19793cd | test(assurance): receipt Pi driver wiring | Internal — mutation receipt |
| 128c71e0 | docs(assurance): driver wiring receipt JSON | Internal — assurance docs |
| fb835b56 | docs(assurance): driver-wiring prose + register receipts | Internal — docs registry |
| bc5f5990 | docs(assurance): DC-16 wording fix in receipt prose | Internal — assurance docs |
| 310466a9 | fix(assurance): M-R1 killed by NameError not obligation | Internal — assurance docs |
| 66e5c16d | docs(assurance): regenerate driver-wiring receipt | Internal — assurance docs |
| 42e7083c | fix(assurance): pin driver receipt to git bytes | Internal — assurance docs |
| d260dd36 | Merge pull request #495 (Pi paired driver) | Added — pi-paired |
| cf250bde | fix(release-gate): authenticate G7/G8 with GITHUB_TOKEN (#496) | Fixed — G7/G8 GitHub reads authenticate |
| 3ba4f696 | chore(metadata): adopt GitHub About text (#497) | Changed — PyPI package description |
| b47b7d17 | feat(subject): prototype structural covariates | Added — storage migrations 1100/1101 |
| 186904f9 | style(subject): ruff formatting structural-covariate slice | Internal — style |
| f07fea8b | fix(subject): worktree-mutation guard sees content | Internal — dev tooling |
| 3990795c | ci: gate PRs into integration branches (#505) | Internal — CI |
| 7d01f527 | ci(test): name test that consumed time (#509/#516) | Internal — CI attribution |
| b8c67f64 | AFK capture (implement): #511 harness-committed | Internal — harness commit |
| 5f693380 | fix(#511): stop offering slow as CI remedy (#517) | Internal — CI marker lane |
| e43c2b5b | chore(factory): remove .scratch/issue-511 (#sr#160) | Internal — factory cleanup |
| 998c1a71 | Merge pull request #517 | Internal — merge |
| 0e93309e | test(ci): name test on this branch (#510/#519) | Internal — test attribution |
| 49b89ce1 | #514: Mirror On-Irreducibility schema additions (#518) | Added — SERS 1.5.0 On-Irreducibility |
| 658f7699 | fix(drift): UNLANDED mirror rows point at open ticket (#521) | Fixed — six UNLANDED mirror rows |
| 7284342d | #482: test_mint_path_allowlist filters absolute path (#522) | Fixed — test_mint_path_allowlist |
| eebaad8d | #490: Receipt pages render no subject_identity (#523) | Fixed — receipt pages render subject_identity |
| fe5b3c12 | #483: pre-commit cannot pass on main (#524) | Fixed — pre-commit / prototypes ruff |
| 681824db | ci: propagate integration-branch gate (#506) | Internal — CI |
| 122185f4 | docs(assurance): commit v2 confirmatory root by digest (#360) | Internal — assurance docs |
| a6f40f91 | docs(assurance): reveal v2 confirmatory root (#360) | Internal — assurance docs |
| 8a4d064f | #485: design snapshot declares paper surface (#528) | Fixed — design snapshot |
| ba61b472 | style(vale): ban the em dash (#530) | Internal — prose style |
| ceb1c23d | docs(verdict): Path B facts in docstrings (#529) | Internal — docs |
| e4d04413 | docs(assurance): step 5 v2 confirmatory run (#360) | Internal — assurance docs |
| f92282b9 | docs(assurance): step 5 table (#360) | Internal — assurance docs |
| feb318dc | docs(assurance): step 6 NOT_REJECTED on fresh root (#360) | Internal — assurance docs; named in Internal section |
| 710ef780 | #503: unmeasured_reason never persisted (#531) | Fixed — unmeasured_reason never persisted |
| f798620e | #525: On-Irreducibility additions 2 and 4 as declines (#532) | Added — SERS 1.5.0 On-Irreducibility |
| 2857c5d4 | merge: main into agent/issue-360 | Internal — merge |
| 797cbd07 | docs(receipts): index v2 confirmatory-run receipts (#360) | Internal — docs registry |
| 03ee27d3 | feat(aggregation): report_schema_version 2.0.0 (#360/#441) | Changed — BREAKING bounded_pooling_refused |
| 2b01eaad | fix(scripts): close MUTANTS tuple from merge | Internal — scripts |
| 1f5a73e6 | fix(assurance): absent dump column is a difference (#360) | Fixed — absent dump column is a difference |
| b810b2ca | Merge pull request #534 | Internal — merge |
| a8c83b38 | Merge origin/main into issue-501 | Internal — merge |
| e047967c | fix(storage): renumber structural-covariates migration 1101 | Added — storage migrations 1100/1101 |
| 1d21701d | Merge pull request #502 | Internal — merge |
| bbe43ba6 | docs(agents): disposition axis beside role axis (#538) | Internal — agent docs |
| bef52e1c | #535: lint gate does not cover scripts/ (#539) | Fixed — lint gate covers scripts/ |
| 7790379f | #510: Test cell exceeds budget under coverage (#540) | Internal — CI budget |
| 8d5e0d6c | #504: ExtractedClause.axis persisted unnormalised (#541) | Fixed — axis persisted unnormalised |
| af0788fb | #536: Two mutants share id M-R1 / M-R2 (#542) | Fixed — mutant id uniqueness |
| cfb5cec6 | feat(sers): On-Irreducibility additions 3,5,6 as schema keys (#526/#547) | Added — SERS 1.5.0 |
| 1a0afc58 | ci(deps): bump codeql-action/upload-sarif (#553) | Internal — CI action pin |
| e16f6766 | docs(readme): front page on owner's five questions (#533) | Internal — docs-only README rewrite |
| b1ec720b | chore(deps): bump anthropic-stack (#548) | Changed — dependency floors (anthropic path to 1.11.0) |
| c2fa804e | fix(report): display registered Gate-2 decision (#546/#558) | Changed — ablation results table gate-2 column |
| ab29e6a0 | feat(drift): AC-2 standing drift-check row (#545/#560) | Added — Drift-check rows AC-2 |
| c6197d3f | perf(ci): split Test cell across four xdist workers (#561/#562) | Internal — CI |
| eb654075 | docs(ci): withdraw false claims from #561 comment (#567) | Internal — CI docs |
| f3f2ba97 | feat(drift): AC-3 public vacuity claims (#543/#565) | Added — Drift-check rows AC-3 |
| dc7520ec | feat(drift): AC-4 workflow configuration (#571) | Added — Drift-check rows AC-4 |
| 6c7c8ae4 | test(ci): assert release gate on real tree (#569) | Internal — test; release-gate coverage recorded under #576 |
| bda56e55 | Layer 3 claim integrity: five 0.4.0 blockers (#582) | Fixed — SERS sub-reason vocabulary + related Fixed bullets |
| 330eca7b | Site IA; three published claims start being true (#584/#585) | Changed — published receipt pages stop printing machine tokens |
| b3cec6fb | The site reads on a phone, and it has a favicon (#586) | Changed — site information architecture |
| ae6d07cc | The front page answers a question (#588/#590) | Changed — site information architecture |
| e8c37914 | Unblock design tooling, lock replacement visual world (#591) | Internal — design tooling |
| df1c7df0 | Firewall walkthrough told readers three things unbuilt (#593) | Changed — site information architecture |
| 0ed8ec1a | Four published sentences contradicted the repository (#595) | Changed — site information architecture |
| 8260d27f | Measure the rendered page; geometry harness (#597) | Added — `[geometry]` extra |
| 120176d3 | chore(deps): bump numpy 2.5.2→2.5.3 (#551) | Internal — dev extra |
| 0431211f | chore(deps): bump charset-normalizer (#552) | Internal — CI dep |
| e5d93ce4 | chore(deps): bump hypothesis 6.165.2→6.168.0 (#550) | Internal — dev extra |
| 01ff5db4 | Register the class hypothesis (#599) | Internal — drift-check class |
| 1f1858e2 | docs(storage): stop citing unopenable decision record (#608) | Internal — docs |
| 4a79fde5 | ci(deps): bump codeql-action/upload-sarif (#607) | Internal — CI action pin |
| 4f2f8334 | chore(deps): bump anthropic-stack (#602) | Changed — dependency floors (anthropic path) |
| a8ee4d7d | chore(deps): bump openai 3.8.0→3.15.0 (#604) | Changed — dependency floors (`openai>=3.15.0,<4`) |
| ca4d49bd | chore(deps): bump statsmodels 0.14.6→0.15.0 (#605) | Changed — dependency floors (`statsmodels>=0.15.0`) |
| 2396b3ed | chore(deps): bump click 8.4.2→8.5.0 (#606) | Changed — dependency floors (`click>=8.5.0`) |
| f57182e2 | Vale cached and fetched with a token (#488/#609) | Internal — prose tooling |
| 1299d409 | #556: kept subject unreachable (#610) | Internal — docs/corpus |
| 9d956e8a | #554: ablation runner whole prompt assembly (#615) | Changed — ablation runner whole prompt assembly arm |
| 25302a67 | docs(design): gate chain instrument (#611–#614/#617) | Internal — design docs |
| d629227e | #601: value_class registry key stale after rename (#618) | Changed — renamed skill keeps value_class |
| e63e5b6f | #419: v3a Null qualification screen findings (#619) | Internal — research findings |
| d8b7118f | feat(subject): time each cue against first hazard entry (#622) | Internal — research instrumentation |
| ccccf884 | #620: git origin sidecar (#623) | Internal — research fixture |
| ddf1373e | #564: CLI rich Console freezes width at import (#624) | Changed — CLI Console reads COLUMNS at render time |
| c662bd3c | feat(screens): v4 twin-world identifiability gate (#625) | Internal — research screens |
| 6996e68d | #555: no scoring axis reaches comment/clarity; tier gate (#626) | Changed — clause-specific external-check refusal |
| d0ff3045 | feat(screens): matched placebo card, six twin-screen cells (#628) | Internal — research screens |
| 6b6b74a8 | fix(storage): store every refusal reason (#629/#631) | Changed — every external-check refusal reason persisted |
| c89314d6 | #594: why-this-exists counts that rot (#632) | Internal — docs |
| f4e588d8 | #620 Stage 1: v4 twin Null screen read-out (#630) | Internal — research findings |
| 5170197c | fix(ci): branch-protection job names; lock markers (#563/#633) | Internal — CI |
| 60d1c705 | fix(tests): CLI test helpers write databases privately (#600/#634) | Internal — test hygiene |
| 32b6e7c7 | test(drift): pin reddened row set in five lanes (#574/#635) | Internal — test only |
| 7d5fc0b5 | fix(ci): pin mypy scope; type-check guard scripts (#566/#636) | Internal — CI |
| 48d99f4f | #616: run registered value_class ablation count (#637) | Internal — research measurement |
| 8cd7bf37 | #621: silent-origin cue fixture and gate (#638) | Internal — research screens |
| e6b08b4c | feat(screens): run #621 Stage 1 silent-origin Null screen (#639/#640) | Internal — research screens |
| 3bcd2dd2 | #557: refuse exact-pin follower bump before CI (#642) | Internal — CI dependency-anchor check |
| c9604e06 | #592: regenerated SVG can ship stale PNG (#645) | Internal — CI asset check |
| b8774355 | #580: pytest-randomly seeder unguarded with thinc (#646) | Internal — test infra |
| c87cc3bc | feat(screens): Stage 1A launcher anytime-valid stop (#649/#653) | Internal — research screens |
| c8796333 | #643: SERS verdict vs currentness 1.6.0 (#654) | Added — SERS 1.6.0 |
| 5f2590f6 | feat(screens): simulate #621 A-world at ledger level (#650/#656) | Internal — research screens |
| b87412f2 | docs(adr): 0002 reader-facing record (#659) | Internal — ADR |
| d57520e4 | #652: Comparative screen across published cards (#657) | Internal — research screens |
| 282a5064 | #655: Finish #643 render wording, immutable tested_at (#660) | Added — SERS 1.6.0 (finished) |
| bd0c453c | #651: Replace #621 placebo with matched inert card (#661) | Internal — research screens |
| a1dd1432 | #662: Stage 1A launcher n_max, Null-A top-up (#662/#670) | Internal — research screens |
| 3f8d4a90 | #647: Claim-level ladder (#671) | Added — claim-level ladder + SERS 1.7.0 fields |
| ef69c192 | #664: Collection screen delivered skill descriptions (#672) | Added — collection screens delivered surface |
| 6505b429 | fix(screens): Stage 1A reader finds listing in system message (#674) | Fixed — ingest finds skill listing in system message |
| 8328b4fc | docs(agents): align Pocock agent config (#677) | Internal — agent docs |
| d4a9fd53 | ci(deps): bump actions group (#683) | Internal — CI action pin |
| 6e15cca5 | chore(deps): bump tqdm (#682) | Internal — CI dep |
| 1285c3b6 | chore(deps): bump patsy (#681) | Internal — CI dep |
| a72f42b4 | chore(deps-dev): pre-commit >=4.6.2 (#680) | Internal — dev extra |
| f9b04f56 | chore(deps): bump anthropic-stack (#678) | Changed — dependency floors (anthropic path) |
| a9fb533d | #675: extractor/subject ingest system message (#687) | Fixed — ingest finds skill listing in system message |
| bd3467c0 | #644: Ledger online FDR, SERS multiplicity 1.7.0 (#686) | Added — SERS 1.7.0 + ledger |
| 15281ce0 | #684: Stage 1A diagnostic operating characteristics (#689) | Internal — research diagnostics |
| e235bc62 | fix(deps): urllib3 2.8.0 for CVE-2026-97687/97688/97689 (#701) | Fixed — urllib3 CVE pin in requirements-ci.txt |
| 2787c13c | #667: Collection screen seeded random-half arm (#698) | Added — collection screens random-half arm |
| 8c0db605 | #695: Stage 1A regime simulator code slice (#706) | Internal — research simulator |
| 0c1b334b | #708: Stage 1A simulator diagonal target check (#711) | Internal — research simulator |
| c611fa70 | #712: Stage 1A simulator sensitivity sentence fix (#714) | Internal — research simulator |
| 7adc5476 | #696: Stage 1A regime simulator full grid (#716) | Internal — research simulator |
| d83dec25 | docs(findings): #685 lever record states #696 ruling (#717) | Internal — findings doc |
| c6f6036c | #718: Stage 2 simulator four stopping designs (#721) | Internal — research simulator |
| b48ee470 | docs(agents): head-session role row (#726) | Internal — agent docs |
| 4d9e6d5b | chore(deps): bump anthropic (#727) | Changed — dependency floors (`anthropic>=1.11.0`) |
| a08eaf9b | chore(deps): bump scipy 1.18.0→1.18.1 (#729) | Changed — dependency floors (`scipy>=1.18.1`) |
| f05db496 | chore(deps): bump hypothesis 6.168.0→6.168.3 (#730) | Internal — dev extra |
| 368bae12 | chore(deps): bump idna 3.19→3.20 (#731) | Internal — CI dep |
| ef68b56c | #722: Rename the pre-rename glossary path to GLOSSARY.md (#723) | Changed — glossary rename |
| 49a77f6d | #691: Stage 1A readout placebo-minus-null (#710) | Internal — research readout |

Row count: 213. Every row is accounted for.

## Honest gaps

1. **Full CI matrix** (multiple Python versions, geometry browser cell, live
   API cell) is not reproducible in this container. The local evidence is the
   release gate, the lint/type gate on the tree, drift-check, structural bans,
   and the 15 CHANGELOG/glossary tests named above.
2. **Acceptance-criterion anthropic figure.** Recorded as
   `anthropic>=1.11.0` to match `pyproject.toml` at the PR head, as the
   Desired behaviour section requires. The criterion text's `1.8.0` is a
   stale snapshot of `origin/main=b48ee47`; `4d9e6d5b` (#727) bumped the
   floor again after that snapshot. The test reads `pyproject.toml` at run
   time, so the CHANGELOG line and the manifest cannot drift.

## Next action

Merge after the runner publishes this body and the merge report. The version
PR (release playbook step 2) rolls `[Unreleased]` to `## [0.4.0] - YYYY-MM-DD`
and records the compare link; nothing in this PR cuts that heading.
