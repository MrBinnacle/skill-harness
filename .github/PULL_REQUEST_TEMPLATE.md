<!--
Thanks for the PR.

Before you submit, please confirm:

- [ ] You read `CONTRIBUTING.md` and `CLAUDE.md`
- [ ] `ruff check src tests` is clean
- [ ] `ruff format --check src tests` is clean
- [ ] `mypy src tests` is clean
- [ ] `pytest -q` is green
- [ ] New tests cover the new behavior (TDD discipline — see CONTRIBUTING.md)

If this PR touches PRD §-tagged invariants, link the relevant
docs/PRD.md section.
-->

## Summary

<!-- 1–3 sentences. What changed and why. -->

## Track / scope

<!-- Which build track does this land in? A=storage, B=extractor, C=oracle,
D=runner, E=aggregation, CLI=cli, DOCS=docs, CI=ci, OTHER=specify. -->

- [ ] A — Storage
- [ ] B — Extractor
- [ ] C — Oracle library
- [ ] D — Ablation runner
- [ ] E — Aggregation + CLI
- [ ] DOCS / CI / OTHER (specify):

## Invariant / decision reference

<!-- If this PR realizes or modifies a locked invariant (docs/PRD.md) or a
published finding (docs/findings/), name it. Otherwise: N/A. -->

## Test plan

- [ ] Unit tests added/updated
- [ ] Integration tests added (where applicable)
- [ ] `pytest -q` green locally
- [ ] Manual verification (describe):

## Breaking change?

- [ ] No
- [ ] Yes (describe migration path in body below)

## Notes for the reviewer

<!-- Edge cases, alternative designs considered, follow-up work. -->
