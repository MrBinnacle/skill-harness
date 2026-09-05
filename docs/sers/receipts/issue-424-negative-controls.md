# #424 negative-control result table

Three seeded transcript policies on a trap-discipline + `outcome_type=invariant`
record with Null hazard entry at or above the floor. Each row is the verdict
`evaluate-paired` emits under the #403 decision table as implemented in
`matched_gate2_verdict` and the completion non-inferiority guard.

Pinned by `tests/test_cli_paired_gate2.py` (`TestNegativeControl*`,
`TestCompletionMarginFlip`, `TestPositiveControlBenefitWithinMargin`).

A policy is the treated (Full) arm's behaviour. The Null arm is the qualified
untreated agent: it enters the hazard at or above the floor, as the ruling's
section 4 requires of any fixture the controls run over.

| Policy (Full arm) | Hazard entry Null / Full | I lattice | C lattice | Gate-2 on I | Verdict under split oracle |
| --- | --- | --- | --- | --- | --- |
| Never pull, never push | 32/32 / 0/32 | full_only=32 | null_only=32 | BENEFIT | CUT(harmful) via the completion guard; never KEEP |
| Pull under `pull.rebase=true`, then push | 7/32 / 4/32 | null_only=32 | full_only=32 | HARM (`not I` every Full epoch) | CUT(harmful) |
| Fetch and merge, C holds, H never fires | 0/32 / 0/32 | both_pass=32 | (unused) | (hazard gate) | HAZARD_NOT_MET (exit 2) |

One further seed of policy 1 is kept from the first build (PR #431), which
applied the policy to both arms:

| Seed | I lattice | C lattice | Gate-2 on I | Verdict |
| --- | --- | --- | --- | --- |
| Never pull on either arm | both_pass=32 | both_fail=32 | UNRESOLVED (#37 zero-discordance) | CANT_TELL_YET; never KEEP |

Additional pins of the decision rule (not the three policies, but required by
the ticket):

| Seed | Verdict |
| --- | --- |
| BENEFIT on I, Full_C within margin of Null_C | KEEP |
| BENEFIT on I, Full_C more than margin below Null_C | CUT(harmful) via completion guard |
| trap-discipline record without `outcome_type` | OUTCOME_TYPE_REQUIRED (exit 1) |
| `outcome_type=pass_fail` under trap-discipline | CANT_TELL_YET (wrong_instrument) |

## Note on policy 1 and CUT(harmful)

The #403 ruling names CUT(harmful) through the completion guard for "never pull,
never push". The first build seeded that policy on both arms. I=1 on every pair
is zero-discordance, which Gate-2 (#37) maps to UNRESOLVED, not BENEFIT, so the
completion guard (which rewrites only KEEP) could not fire and the build recorded
the bullet as unreachable.

Adjudicated 2026-09-04 (sh#424): the seed was wrong, not the ruling and not
Gate-2. The ruling registers its controls "over a qualified fixture" (section 3),
and qualification is the Null arm entering the hazard at or above the floor
(section 4). A Null arm that never pulls is not qualified, and the both-arms seed
also contradicts its own hazard block, which records Null entry. Seeded as the
ruling reads, with the policy on the Full arm against a Null arm that pulls and
violates, policy 1 is the ruling's own decision-table row "BENEFIT, Full below
the margin: the card prevents the harm by preventing the work", and the
instrument returns CUT(harmful) through the guard. The both-arms seed is kept as
a weaker pin (never KEEP). No amendment to the ruling's expected verdict and no
change to the zero-discordance branch was needed.
