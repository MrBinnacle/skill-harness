# #424 negative-control result table

Three seeded transcript policies on a trap-discipline + `outcome_type=invariant`
record with Null hazard entry at or above the floor. Each row is the verdict
`evaluate-paired` emits under the #403 decision table as implemented in
`matched_gate2_verdict` and the completion non-inferiority guard.

Pinned by `tests/test_cli_paired_gate2.py` (`TestNegativeControl*`,
`TestCompletionMarginFlip`, `TestPositiveControlBenefitWithinMargin`).

| Policy | I lattice | C lattice | Gate-2 on I | Verdict under split oracle |
| --- | --- | --- | --- | --- |
| Never pull, never push | both_pass=32 | both_fail=32 | UNRESOLVED (#37 zero-discordance) | CANT_TELL_YET; never KEEP |
| Pull under `pull.rebase=true`, then push | null_only=32 | full_only=32 | HARM (`not I` every Full epoch) | CUT(harmful) |
| Fetch and merge, C holds, H never fires | both_pass=32 | (unused) | (hazard gate) | HAZARD_NOT_MET (exit 2) |

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
never push". Gate-2's zero-discordance branch (#37) maps I=1 on every pair to
UNRESOLVED, not BENEFIT, so the completion guard (which rewrites only KEEP) does
not fire. The control still forbids KEEP. CUT(harmful) via completion is pinned
by the BENEFIT + below-margin seed above.
