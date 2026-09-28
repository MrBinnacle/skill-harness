# Triage Labels

The triage vocabulary has two axes. The role axis says who acts next. The disposition axis says
what was decided. This file maps both to the actual label strings used in this repo's issue
tracker.

An issue needs a value from one axis. The issue-creation guard at
`~/.claude/hooks/guard-gh-issue-triage-label.py` reads this file live, hard-codes no value, and
refuses an issue carrying neither.

## Role axis

A role says who acts next. An issue carrying a role is still live work.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | An evaluation or decision is owed, and an agent adjudication session makes it down the QUESTION ROUTING ladder. Also the role for a decision ticket that is parked. The operator is not the evaluator. |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent. Read the BODY before launching: a body that states an outstanding decision is not agent-ready whatever the label says (S393). A `Blocked by #N` line makes the factory skip it. |
| `ready-for-human`          | `ready-for-human`    | Requires an action only a person can perform: spend authorization, a credential, a login, a dashboard. NOT a technical decision. Operator-lodged S394: *"I don't have enough information or technical subject matter expertise to make the right call"*, and that extends to almost every ticket that carried this label. A decision goes down the ladder; only the money/scope/values residue reaches the operator, as one plain yes/no with the amount in it. |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Measured 2026-09-02 (S394): seven open `ready-for-human` tickets across the three boards. Six were decidable by standing rules or were builds; one was a money question. The label had become the sink for decisions an agent deferred, which is the failure the QUESTION ROUTING ladder exists to prevent.

Edit the right-hand column to match whatever vocabulary you actually use.

## Disposition axis

A disposition records what was decided. An issue carrying a disposition carries no role, because a
decided issue has no next actor. The issue-creation guard accepts a disposition in place of a role
for exactly that reason. An issue filed with neither is still refused.

The values are borrowed from `skill-harness`'s ratified verdict vocabulary rather than invented, so
the board reads in the same terms as the instrument that judges the work. The verdict enum is
`KEEP`, `CUT` with a sub-reason, and `CANT_TELL_YET`, at
`src/skill_harness/aggregation/verdict.py:121-148` (read 2026-09-13).

| Verdict in skill-harness | Label in our tracker | Meaning |
| ------------------------ | -------------------- | ------- |
| `CUT`                    | `declined`           | Decided against. A registry row holds the condition that would reverse it. |
| `CUT(subsumed)`          | `subsumed`           | Superseded by other work. A registry row names what would reopen it. |
| `CANT_TELL_YET`          | `cant-tell-yet`      | Undecidable on present information. A registry row names what would make it decidable. |
| no counterpart           | `wontfix`            | Terminal. Not actioned, not watched, and requiring no registry row. |

`declined`, `subsumed` and `cant-tell-yet` are non-terminal. Each one requires a row in the
revisit-conditions registry, `.claude/state/revisit-conditions.json` in the steering repository,
naming the condition that would reverse the decision. A decline with no registry row is a decision nothing
is watching, which is the failure this axis exists to prevent.

`wontfix` is terminal. It records that the work will not be done and that nothing will reopen it. It
requires no registry row, and that is the whole difference between it and `declined`.

`wontfix` moved to this axis from the role axis. The label itself is unchanged and every issue
carrying it keeps it. What changed is which question it answers: it says what was decided, not who
acts next.
