# Stage 1A readout: Placebo inertness, adherence, within-pair correlation (#691)

**Date:** 2026-10-05. **Script:** `scripts/screens/419/stage1a_readout_691.py`. **Test:**
`tests/test_stage1a_readout_691.py`. **Model calls:** none. **Network calls:** none.
**Spend:** none.

## Why this record exists

Ticket #691 asks three questions that the Stage 1A audit left unmeasured: the formal
interval on Placebo minus Null-A, the three adherence rates, and the within-pair correlation
of Full and Placebo correctness. The decision behind the ticket is the next-design
adjudication (S493, section 6) in the steering research repository. This record measures
all three from the S486 Stage 1A logs, through the script named above, run on the host that
holds the logs.

An earlier version of this record (PR #710 at `0a8c7c0`) reported numbers from a substitute
readout, because the build container could not reach the logs. That readout and its
provenance file are removed. No number below comes from it.

## Inputs

Both inputs are untracked or live in another repository, so neither is committed here. The
three launch-order streams are quoted in full under "Script output", so a reader without the
operator's disk can recompute every figure.

| Input | Location on the operator's host | Read with |
| --- | --- | --- |
| S486 Stage 1A run: `run.log` and the per-look `.eval` logs under `run/look-001` to `run/look-097` | steering research repository, `.claude/state/eval-runs/S486-stage1a/` (untracked) | `v5_cue_stage1a._read_rows_by_launch` and `_manifest_reads` |
| Reused Null-A epochs (looks 1 to 7 hold no Null-A log) | steering research repository, `.claude/state/eval-runs/S475-cue-stage1/readout.json` | `v5_cue_stage1a.load_null_a` |

The Null-A stream is the seven reused outcomes followed by the 90 new outcomes in launch
order, the order the run records ("Null-A reused epochs then new epochs in launch order").
The JSON summary at the tail of `run.log` carries no per-epoch rows. The script reads it
only to cross-check its own counts and bounds, and it refuses on any disagreement. All
eleven cross-checks agree. They include the run's recorded `f_minus_n.lb_mu_f`
(0.3847973934509016) and `f_minus_n.ub_mu_n` (0.46318463383223085), which depend on the
order of the Full and Null-A streams.

## Command

`<RESEARCH_REPO>` is the steering research repository's working tree on the operator's host.

```
PYTHONPATH=src python scripts/screens/419/stage1a_readout_691.py \
    <RESEARCH_REPO>/.claude/state/eval-runs/S486-stage1a/run.log \
    --null-readout <RESEARCH_REPO>/.claude/state/eval-runs/S475-cue-stage1/readout.json
```

Exit code 0. Most of the run time goes to the linear scans for "n to exclude".

## Script output

```
=== Launch-order streams (epoch 1 to n; 1 = world correct) ===
P 0000001000100010010110011011011111010000001101100000011000000100101010111010000011000010010000000
N 0000010000000100011000100100000010000000010011010111010000010000101110110101111110011000101001000
F 1110111101110010001110001100001111110010010000011101010110011111001000011101000101011000110100011
null_order: Null-A reused epochs then new epochs in launch order
void_epochs: none

=== Placebo inertness (Placebo - Null-A) ===
n_placebo=97 correct_placebo=34
n_null=97 correct_null=34
point_estimate=0.0000
[alpha reading: 0.025 per one-sided bound: each endpoint at 0.05, the interval at 0.10 by the union bound]
  anytime_valid_interval=[-0.2818, 0.3601]
  the interval does not exclude +/-0.20
  placebo inertness is not established at this n under this reading
  n_to_exclude_pm_0.20=263 (convention: same rates at evenly-spaced launch indices)
  n_to_exclude_pm_0.20=488 (convention: real launch order repeated to length n)
[alpha reading: 0.0125 per one-sided bound: 0.05 in total over the four bounds]
  anytime_valid_interval=[-0.3042, 0.3825]
  the interval does not exclude +/-0.20
  placebo inertness is not established at this n under this reading
  n_to_exclude_pm_0.20=314 (convention: same rates at evenly-spaced launch indices)
  n_to_exclude_pm_0.20=570 (convention: real launch order repeated to length n)
n_to_exclude is a property of the convention, not of the data; no convention is chosen
fixed_n_newcombe_interval=[-0.1322, 0.1322] (direct two-sided fixed-n comparison, unpaired, 95%)
fixed_n_excludes_plus_minus_0.20=true

=== Adherence (descriptive only) ===
assignment_to_read:
  full: 32/97 = 0.330
  placebo: 28/97 = 0.289
assignment_to_outcome:
  full: 50/97 = 0.515
  placebo: 34/97 = 0.351
read_to_outcome:
  full_correct_among_read: 22/32 = 0.688
  full_correct_among_unread: 28/65 = 0.431
  placebo_correct_among_read: 5/28 = 0.179
  placebo_correct_among_unread: 29/69 = 0.420
Manifest-read happens after assignment. Splitting outcomes by it conditions on a post-treatment variable. These are adherence descriptives, not a mechanism.

=== Within-pair correlation (Full x Placebo, descriptive) ===
n_pairs=97 (paired by launch index; void epochs excluded)
table: both_correct=18 full_only=32 placebo_only=16 neither=31
phi=0.0205
phi_95_ci=[-0.1797, 0.2191] (Fisher z)
materially_positive=false
the interval includes zero; #684's independence assumption is not contradicted at this n

cross_check full correct: run.log=50, logs agree
cross_check placebo correct: run.log=34, logs agree
cross_check full manifest_read: run.log=32, logs agree
cross_check placebo manifest_read: run.log=28, logs agree
cross_check null-a n: run.log=97, logs agree
cross_check null-a correct: run.log=34, logs agree
cross_check null-a order: run.log='Null-A reused epochs then new epochs in launch order', logs agree
cross_check pairs: run.log=97 keys, logs agree
cross_check void_epochs: run.log=0, logs agree
cross_check f_minus_n.lb_mu_f: run.log=0.3847973934509016, logs agree
cross_check f_minus_n.ub_mu_n: run.log=0.46318463383223085, logs agree
```

## Section 1: Placebo inertness

**Construction.** Each arm contributes one-sided `one_sided_betting_bound` values from
`skill_harness.aggregation.confidence_sequence` on its raw 0/1 outcomes in launch order. A
union bound combines them: LB(μ_P − μ_N) = LB(μ_P) − UB(μ_N) and UB(μ_P − μ_N) = UB(μ_P) −
LB(μ_N). The fixed-n comparison is an unpaired Newcombe square-and-add of the two Wilson
intervals at 95%.

**Two alpha readings.** The ticket says "two-sided ... at alpha 0.05 ... (union bound, 0.025
each)". That wording supports two readings, and the bar owner has not chosen between them.
This record reports both and chooses neither.

| Reading | Per one-sided bound | Error of the interval | Interval | Excludes ±0.20 |
| --- | --- | --- | --- | --- |
| A | 0.025 | each endpoint at 0.05; the interval at 0.10 by the union bound | [−0.2818, 0.3601] | no |
| B | 0.0125 | 0.05 in total over the four bounds | [−0.3042, 0.3825] | no |

The point estimate is 0.0000 (34/97 against 34/97). Under both readings the interval does
not exclude ±0.20, so **placebo inertness is not established at n = 97**. The fixed-n
Newcombe interval [−0.1322, 0.1322] does exclude ±0.20. That difference is the cost of
anytime validity. It is not a reason to use the fixed-n interval under sequential stopping.

**"n to exclude ±0.20" depends on a convention.** The ticket asks for the n at which the
same counts would exclude ±0.20. The answer depends on how the same rates are spread over a
longer stream, because the betting bound depends on order. The script prints two
conventions under each reading and chooses neither:

| Convention | Reading A | Reading B |
| --- | --- | --- |
| Same rates at evenly-spaced launch indices | 263 | 314 |
| Real launch order repeated to length n | 488 | 570 |

The non-author verifier's recompute found 272 at reading A with a different even spacing.
These figures are properties of the conventions, not of the data.

**Search method.** Each figure is the smallest n found by a linear scan from 97. Exclusion
is not monotone in n under the repeated-order convention: the phase of the stream at n moves
the bounds. At `0a8c7c0` the script used doubling and bisection, which assumes monotonicity.
On the repeated-order convention at reading A that search returned 535 in this rework's
first host run; the linear scan returns 488, which matches the verifier's figure.

## Section 2: Adherence, descriptive only

| Rate | Full | Placebo |
| --- | --- | --- |
| Assignment to read | 32/97 = 0.330 | 28/97 = 0.289 |
| Assignment to outcome | 50/97 = 0.515 | 34/97 = 0.351 |
| Read to outcome: correct among read | 22/32 = 0.688 | 5/28 = 0.179 |
| Read to outcome: correct among unread | 28/65 = 0.431 | 29/69 = 0.420 |

A read is any tool call whose arguments name the trace file (`release-manifest.json`), as
`v5_cue_stage1a._manifest_reads` defines it.

Manifest-read happens after assignment. Splitting outcomes by it conditions on a post-treatment variable. These are adherence descriptives, not a mechanism.

## Section 3: Within-pair correlation, descriptive

**Construction.** Full and Placebo are paired by launch index (the look number), matching
the run's `pairing_key`. A pair is dropped when either epoch is void. S486 has no void
epochs, so all 97 pairs stand. The interval on phi uses the Fisher z-transform.

| | Placebo correct | Placebo wrong | Total |
| --- | --- | --- | --- |
| Full correct | 18 | 32 | 50 |
| Full wrong | 16 | 31 | 47 |
| Total | 34 | 63 | 97 |

phi = 0.0205, 95% interval [−0.1797, 0.2191]. The interval includes zero, so the correlation
is not materially positive. #684's simulator draws the arms independently, and this data does
not contradict that assumption at n = 97. It also does not establish independence: the
interval admits a correlation up to about 0.22. No causal reading is claimed.

## Limits

1. **The inputs are not in this tree.** The streams are quoted above so that every figure
   can be recomputed. The `.eval` logs remain the measurement of record.
2. **No alpha reading and no n convention is chosen.** Those choices belong to the bar
   owner.
3. **No causal reading** is claimed for the adherence split or the within-pair correlation.
4. **The post-treatment sentence is binding.** Manifest-read happens after assignment.
   Splitting outcomes by it conditions on a post-treatment variable. These are adherence
   descriptives, not a mechanism.

## Companion artifacts

| Artifact | Location |
| --- | --- |
| Ticket | #691 |
| Script | `scripts/screens/419/stage1a_readout_691.py` |
| Test | `tests/test_stage1a_readout_691.py` |
| Stage 1A readers | `scripts/screens/419/v5_cue_stage1a.py` |
| #684 operating characteristics | `docs/findings/stage1a-regime-operating-characteristics.md` |
| #685 lever adjudication | `docs/findings/stage1a-lever-adjudication-685.md` |
| Engine bound | `src/skill_harness/aggregation/confidence_sequence.py` (`one_sided_betting_bound`) |

*Revisit if:* the engine's `one_sided_betting_bound` or the `v5_cue_stage1a` readers change;
then re-run the command above and re-quote its output.
