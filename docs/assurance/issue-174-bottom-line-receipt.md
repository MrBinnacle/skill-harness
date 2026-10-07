# Receipt: the Phase 7 close-out bottom line, published on issue #174

**Ticket:** #354. **Close-out document:** `docs/ASSURANCE.md`, section "Bottom line".
**Published at:** https://github.com/MrBinnacle/skill-harness/issues/174#issuecomment-5496638740
**Comment id:** `5496638740`. **Posted:** 2026-09-01T15:52:27Z by `MrBinnacle`.
**Digest of the published paragraph:**
`sha256:5d270dbddca30eb93c8e57a0149794aae29ba29a126ba030c57a10c0c028dfed`

This file exists because the claim it records was previously checkable only by a caller holding a
GitHub credential, and was therefore not checked at all.

## What was wrong

`tests/test_assurance_closeout_174.py::test_issue_174_has_the_exact_bottom_line_comment` asserts
the close-out's bottom-line paragraph appears verbatim as a comment on issue #174. Issue #174 had
**zero comments**, so the assertion was false. It did not fail, because the test skips when `gh`
cannot read the issue, and the CI test job provisions no `GH_TOKEN`. The assertion ran only on a
machine where some earlier command happened to authenticate `gh`.

A contract enforced only when an unrelated side effect authenticates the caller is not enforced.
The suite reported green, the close-out claimed a published finding, and the finding was not
published.

## Whether the original comment was deleted is NOT established

The full paginated timeline of issue #174 carries no `commented` event. GitHub emits no timeline
event when a comment is deleted, so this absence is consistent with **both** "never posted" and
"posted and later removed". Recorded as unresolved rather than guessed. Nothing in this repository
distinguishes the two, and no claim here depends on which it was.

## What now holds the claim

Two surfaces, with different failure modes on purpose:

| Surface | Reads | Fails when |
| --- | --- | --- |
| This file plus `tests/test_assurance_closeout_174.py::test_bottom_line_receipt_matches_the_closeout` | no credential; runs in CI | the close-out's bottom line changes without this receipt being re-issued |
| `::test_issue_174_has_the_exact_bottom_line_comment` | needs `gh`; skips otherwise | the published comment is edited or deleted, wherever `gh` can read |

The credential-free check is the enforced contract. The remote check is corroboration: it is
strictly stronger where it runs, and it is explicitly not relied upon where it does not.

The digest above is over the paragraph as published. Re-deriving it is one command:

```bash
python -c "import hashlib,pathlib;t=pathlib.Path('docs/ASSURANCE.md').read_text(encoding='utf-8').rstrip();print(hashlib.sha256(t.rsplit('## Bottom line\n\n',1)[1].encode()).hexdigest())"
```

## What this receipt refuses to claim

That the bottom line was published on the close-out date — it was published 2026-09-01, sixteen
days after issue #174 was closed, and the comment says so in its own text. That the original
comment ever existed. That the published comment still matches: only the credentialed check can
see that, and it does not run in CI. That any figure inside the paragraph is correct — those carry
their own receipts, listed in `docs/receipts-index.md`.

*Revisit if:* the close-out's bottom line is edited. The digest and the published comment both go
stale in the same edit, and re-issuing means posting the new paragraph and updating this file
together. Also revisit if CI ever gains a credential that can read issues, at which point the
remote check stops being corroboration and becomes enforceable in the place it matters.
