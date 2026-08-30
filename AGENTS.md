# AGENTS.md

Agent-facing configuration for this repo.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`MrBinnacle/skill-harness`), operated via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` — with label strings equal to role names. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root, maintained by `/domain-modeling`. See `docs/agents/domain.md`.

`CONTEXT.md` is the vocabulary of record: use its terms in prose and identifiers, respect its Avoid-notes, and when code and glossary disagree, the code is the primary source — fix the glossary, then decide whether the code's term deserves a rename of its own.

## Prose voice — literal-humanist register

Instance of the **Register** row of the taste doctrine, class 2 (public prose in `skill-harness`). It lives in `TASTE.md` in the owner's private research repository. The test is stated there once; this section is its application to this repository.

Default register for every substantive prose artifact in this repo: README, docs, ADRs,
issues, pull requests, release notes, review comments, commit bodies, diagnostics. It does
not restyle source code.

For substantive prose:

1. State what happened — dates, amounts, versions, quoted terms.
2. Name the mechanism — translate each label into the action it performs.
3. State the consequence and its allocation — who gained, who paid.
4. State the finding. Never leave the operative conclusion for the reader to infer.
5. Attach uncertainty only to the proposition that is actually uncertain.
6. End with the next action, test, or decision.

Syntax: short sentences, concrete nouns, direct verbs, active voice, one step per
sentence. Never: euphemism after the underlying action is known; "perhaps",
"possibly", or "arguably" as cushioning for a supported claim; "readers may
conclude"; sarcasm or victory laps; passive voice that hides the responsible
component; abstractions that erase the person affected.
