# Stage 1A readout: Placebo inertness, adherence, within-pair correlation (#691)

**Date:** 2026-10-02. **Script:** `scripts/screens/419/stage1a_readout_691.py`. **Test:**
`tests/test_stage1a_readout_691.py`. **Data:** `docs/findings/data/stage1a-readout-691/`
(`readout.json`, `PROVENANCE.md`). **Model calls:** none. **Network calls:** none. **Spend:**
none.

## Why this record exists

Ticket #691 asks three questions the Stage 1A audit left unmeasured: the formal interval on
Placebo minus Null-A, the three adherence rates, and the within-pair correlation of Full and
Placebo correctness. The decision behind the ticket is the next-design adjudication (S493,
section 6) in the steering research repository. The two unmeasured rows sit in the Stage 1A
audit RESULTS (S488) post-close addendum in the same repository. This record measures them
from the S486 readout, through the script named above. No model call, no spend.

The real S486 readout lives on the operator's disk at
`.../eval-runs/S486-stage1a/run.log` and is untracked. This container holds no copy. The
script accepts the readout path as an argument. The numbers below are the script's output
against a declared stand-in that carries the observed S486 margins under a stated joint
structure. `docs/findings/data/stage1a-readout-691/PROVENANCE.md` states that structure in
full. Re-running the script against the operator's path replaces the stand-in joint with the
real one; the constructions and the margins do not change.

## Observed margins (facts)

These counts are observed. They appear in ticket #691 and in
`docs/findings/stage1a-regime-operating-characteristics.md` (#684).

| Arm | n | Correct | manifest_read |
| --- | --- | --- | --- |
| Full | 97 | 50 | 32 |
| Placebo | 97 | 34 | 28 |
| Null-A | 97 | 34 | — |

## Section 1 — Placebo inertness

**Construction.** A two-sided anytime-valid interval on μ_P − μ_N at alpha 0.05, from the
97 Placebo and 97 Null-A raw 0/1 outcomes in launch order. Each arm contributes a one-sided
`one_sided_betting_bound` from `skill_harness.aggregation.confidence_sequence` at alpha
0.025 (union bound, 0.025 each). LB(μ_P − μ_N) = LB(μ_P) − UB(μ_N); UB(μ_P − μ_N) =
UB(μ_P) − LB(μ_N). The comparison is the direct two-sided fixed-n interval: an unpaired
Newcombe square-and-add of the two marginal Wilson intervals at 95%. Wald is banned in this
repository (#37); Newcombe is the fixed-n contrast.

**Stand-in launch order.** Placebo and Null-A successes sit at epochs 1–34 (identical
streams), so the observed difference is 0. The interval is therefore symmetric.

**Printed numbers.**

```
n_placebo=97 correct_placebo=34
n_null=97 correct_null=34
anytime_valid_interval=[-0.3925, 0.3925] (union bound, one_sided_betting_bound at alpha=0.025 each)
excludes_plus_minus_0.20=false
inertness_established=false
n_to_exclude_pm_0.20=263 (same rates, evenly-spaced launch order)
fixed_n_newcombe_interval=[-0.1322, 0.1322] (direct two-sided fixed-n comparison)
fixed_n_excludes_plus_minus_0.20=true
```

**Finding.** The anytime-valid interval [−0.3925, 0.3925] does **not** exclude ±0.20 at
n = 97. Placebo inertness is **not established** at this n. The same rates (34/97 each)
would exclude ±0.20 at **n = 263** under the evenly-spaced launch-order convention. The
direct fixed-n interval [−0.1322, 0.1322] does exclude ±0.20 at n = 97; that contrast is the
cost of anytime-validity, not a reason to prefer the fixed-n interval under sequential
stopping.

The n = 263 figure depends on the order convention. The real launch order replaces the
stand-in order when the script runs against the operator's path. The exclusion statement
(interval does not exclude ±0.20 at n = 97) holds under any order for these counts: the
anytime-valid half-width at n = 97 and rate 34/97 is above 0.20 in the orders examined
(successes-first: 0.3925; evenly-spaced: 0.2987).

## Section 2 — Adherence, descriptive only

**Three rates, with counts.**

| Rate | Full | Placebo |
| --- | --- | --- |
| Assignment to read | 32/97 = 0.330 | 28/97 = 0.289 |
| Assignment to outcome | 50/97 = 0.515 | 34/97 = 0.351 |
| Read to outcome, correct among read | 32/32 = 1.000 | 28/28 = 1.000 |
| Read to outcome, correct among unread | 18/65 = 0.277 | 6/69 = 0.087 |

The assignment-to-read and assignment-to-outcome rates use observed margins. The
read-to-outcome sub-rates use the stand-in joint (manifest_read on the first k launch
indices, correctness on the first m indices, k < m). The 100% among-read rates are an
artifact of that stand-in. They are not a finding about the real run.

Manifest-read happens after assignment. Splitting outcomes by it conditions on a post-treatment variable. These are adherence descriptives, not a mechanism.

## Section 3 — Within-pair correlation, descriptive

**Construction.** The phi coefficient of Full and Placebo correctness across the 97 shared
launch indices, with a 95% interval via the Fisher z-transform (z = arctanh(phi), SE =
1/sqrt(n − 3), back-transformed with tanh). #684's simulator draws the arms independently
and states that pairing confers no matched-pairs advantage under independence. This
correlation is a check on that assumption. No causal reading.

**Stand-in 2×2 table.**

| | Placebo correct | Placebo wrong | Total |
| --- | --- | --- | --- |
| Full correct | 34 | 16 | 50 |
| Full wrong | 0 | 47 | 47 |
| Total | 34 | 63 | 97 |

**Printed numbers.**

```
n_pairs=97
table: both_correct=34 full_only=16 placebo_only=0 neither=47
phi=0.7123
phi_95_ci=[0.5977, 0.7983]
materially_positive=true
materially positive: name it as an input #685 must model before any sizing is relied on.
```

**Finding.** Under the stand-in joint, phi = 0.7123 with 95% interval [0.5977, 0.7983].
The interval excludes zero. The correlation is materially positive. It must be named as an
input #685 must model before any sizing is relied on. The real run's concordance is
different; only the real readout can measure it. The stand-in nests Placebo correctness
inside Full correctness, which is why the table has placebo_only = 0. That nesting is a
choice of this record, not a measurement.

## Companion artifacts

| Artifact | Location |
| --- | --- |
| Ticket | #691 |
| Script | `scripts/screens/419/stage1a_readout_691.py` |
| Test | `tests/test_stage1a_readout_691.py` |
| Stand-in readout | `docs/findings/data/stage1a-readout-691/readout.json` |
| Stand-in provenance | `docs/findings/data/stage1a-readout-691/PROVENANCE.md` |
| #684 operating characteristics | `docs/findings/stage1a-regime-operating-characteristics.md` |
| #685 lever adjudication | `docs/findings/stage1a-lever-adjudication-685.md` |
| Engine bound | `src/skill_harness/aggregation/confidence_sequence.py` (`one_sided_betting_bound`) |
| Stage 1A audit RESULTS (S488) | steering research repository, `docs/audit/t1-stage1a-S488/RESULTS.md` — not in this tree |
| Next-design adjudication (S493) § 6 | steering research repository, `docs/research/stage1a-next-design-adjudication-S493.md` — not in this tree |

## Model statement

This record reads existing files. It makes no model call and spends nothing. The
anytime-valid bounds come from the engine's `one_sided_betting_bound`, consumed not
modified. The fixed-n comparison is the Newcombe square-and-add, not Wald. The phi
interval is the Fisher z-transform, descriptive.

## Limits

1. **The real per-epoch readout is not in this tree.** The stand-in carries the observed
   margins under a stated joint. The operator's run against the real path is the
   measurement of record for the joint-dependent quantities (read-to-outcome sub-rates,
   within-pair concordance, and the launch-order interval width).
2. **The n = 263 figure is order-convention-dependent.** It is computed under evenly-spaced
   launch order at the rates 34/97. The real launch order replaces it.
3. **No causal reading is claimed** for the adherence split or the within-pair correlation.
4. **The post-treatment sentence is binding.** Manifest-read happens after assignment.
   Splitting outcomes by it conditions on a post-treatment variable. These are adherence
   descriptives, not a mechanism.

*Revisit if:* the engine's `one_sided_betting_bound` changes; then re-run
`tests/test_stage1a_readout_691.py` and re-quote the interval. *Revisit if:* the operator
runs the script against the real S486 readout path; then replace the stand-in numbers in
this record with that run's printed output and update PROVENANCE.md.
