# Mutation receipt: hazard-entry segmentation and the undecided verdict (#438)

**Standard:** #341. **Repair:** #438, the hazard-entry counting instrument.
**Generator:** `scripts/mutation_receipt.py --select 438`. **Machine-readable record:**
`docs/assurance/hazard-entry-segmentation-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/subject/paired_launch.py` at
`sha256:6b04484e151e017c0b000f3326df7309a9eb93025a14b25294db1477fd41bd3a`.
**Commit at generation:** `57aed6b` - informational only. A rebase rewrites it and later commits
move HEAD past it, so currency is checked against the digest above by
`tests/test_mutation_receipt.py`. **Python:** 3.13.1.

Each case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. `PYTHONPATH` pins every case to its own sources, because the editable install would
otherwise resolve `skill_harness` to the main repository and each case would silently test
another tree's code.

Per case the generator records and asserts: the worktree HEAD, the `module.__file__` actually
imported, the clean and mutant source digests, that those digests differ, that the clean
baseline **passes first** with **nonzero collection**, the failing test node under the mutant,
that the mutant **imports** (a stillborn mutant is not a kill), and that the production tree is
byte-unchanged afterwards. All three cases resolved `skill_harness.subject.paired_launch` inside
their own worktree, and the production digest was identical before and after.

## What the repair was, and what it can therefore lose

`hazard_entry_counts` decides whether an epoch entered a registered hazard. Before #438 it matched
the record's `hazard_action` regex against the whole command string one bash tool call carries.
Two things were wrong at once. The pattern registered for the `git-pull-rebase-trap` family
matched explicit-strategy pulls, which the card rates MUST PASS; and matching against the whole
string cannot tell one command of a chain from the next, so the pilot Null arm read 3 of 8 entered
against zero real entries.

The repair segments each command string into simple commands, normalises each through `shlex`, and
matches the pattern against that. It also makes the verdict three-valued: a command the segmenter
cannot read is UNDECIDED rather than a silent avoidance.

Three properties can be lost silently, and each has a mutant here.

- **Segmentation.** Delete it and the instrument is the pre-#438 one, byte for byte in behaviour.
  Every anchored pattern stops matching a chained command.
- **The whole-string refusal.** An unterminated quote or a heredoc becomes an avoidance. This is
  the loud half: it changes the verdict for inputs a reader is likely to try.
- **The per-segment refusal.** A chain whose sibling command is unreadable becomes an avoidance
  while the whole-string refusal keeps working. This is the quiet half, and it is the reason M-H3
  exists: at first writing, the case table's two UNDECIDED cases both went through the
  whole-string return, so the per-segment branch had **no detector at all** and this mutant would
  have SURVIVED. The case that kills it (`echo foo\`, a trailing backslash that segments cleanly
  and then defeats `shlex`) was added because the campaign found the gap.

## Results

| mutant | obligation | mutation | verdict | killing tests |
|---|---|---|---|---|
| M-H1 | 438-simple-command-segmentation | Return the whole command string as one segment: chained commands are matched as a blob again | **KILLED** | `test_paired_launch.py::TestSimpleCommands::test_splits_a_chain_on_every_unquoted_operator`; `TestHazardCommandCases::test_case[cd /root/project && git pull]`; `TestHazardCommandCases::test_case[cd /root/project; git pull origin main]`; `TestHazardCommandCases::test_a_match_wins_over_an_unreadable_sibling_command`; `TestHazardCommandCases::test_a_config_write_beside_the_pull_is_counted_as_an_entry` |
| M-H2 | 438-undecided-whole-string | Return `AVOIDED` when the string cannot be segmented at all: a heredoc or an unterminated quote reads as the trap avoided | **KILLED** | `test_paired_launch.py::TestHazardCommandCases::test_case[echo "unterminated]`; `test_case[cat > note.txt <<'EOF' ...]` |
| M-H3 | 438-undecided-per-segment | Return `AVOIDED` when a SEGMENT cannot be read, keeping the whole-string refusal so the loss is invisible in the common case | **KILLED** | `test_paired_launch.py::TestHazardCommandCases::test_case[echo foo\]` |

## What this receipt does not attest

- **The pattern of record.** The regex registered for the `git-pull-rebase-trap` family lives in
  RAT-0001 Amendment 5 and in the test module, not in production code, so no mutant here can
  target it. Its evidence is the measurement in that amendment: eight logs read at source, pilot
  Null 3 of 8 under the shipped pattern and 0 of 8 under the pattern of record.
- **The private-log fixture.** `TestPilotLogsUnderThePatternOfRecord` reads logs that are not in
  the repository and SKIPS where they are absent, so it cannot be a killing test for any mutant
  here and is not named as one.
- **Anything about repository state.** The instrument reads commands only. A strategy established
  by `git config pull.rebase` in a separate tool call is invisible to it, by construction and not
  by defect.
