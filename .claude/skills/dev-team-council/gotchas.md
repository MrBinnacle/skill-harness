# Gotchas — dev-team-council

Append-only. Replace [ANTICIPATED] with [OBSERVED] + session date when confirmed.

---

[ANTICIPATED] Seats dispatched sequentially instead of in parallel. Multiple Agent
tool calls in one message run concurrently; multiple messages run serially. A
"parallel" council that fires seats one per turn is sequentially scheduled and
loses the cross-talk synthesis quality.

[ANTICIPATED] Cross-talk block dropped from prompts for brevity. The "predict what
the other seats will catch" block is the actual mechanism by which seats interpret
across each other instead of siloing — removing it converts the council to N
independent monologues that don't compose.

[ANTICIPATED] Synthesizer trusts subagent citations without verification. Per
`subagent-research-reliability`, LLM research subagents produce plausible-looking
citations that don't exist. Verify every arXiv ID, CVE ID, and URL via direct
query before adopting a finding.

[ANTICIPATED] Roster too large to actually fire. A 9-seat council on every
decision drowns signal in process. Use the standard templates; only fire the
expanded roster when the decision warrants it. The triggers are a contract,
not a wishlist.

[ANTICIPATED] Specialist seats never fire because triggers are vague. "Fires when
relevant" without a concrete trigger condition degenerates to "fires when the
assistant remembers." Triggers must name file paths, surface types, or specific
change shapes.

[ANTICIPATED] PRD amendments applied piecemeal during the build instead of in a
single locked PR. Council outputs queue PRD changes; the queue holds until a
doc-lock PR applies them all together. Piecemeal edits create a moving target
the build code can't trust.

[ANTICIPATED] OPERATOR-DX and DOCS-DX seats produce findings that the synthesizer
treats as MINOR by default. User-facing quality is not minor; the severity must
reflect blast radius for the user, not blast radius for the architecture.
