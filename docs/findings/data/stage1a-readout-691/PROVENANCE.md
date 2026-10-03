# Provenance of the #691 stand-in readout

**File:** `docs/findings/data/stage1a-readout-691/readout.json`.

The real S486 Stage 1A readout lives on the operator's disk at
`.../eval-runs/S486-stage1a/run.log` (untracked). This container holds no copy.
The JSON in this directory is a declared stand-in. It carries the observed S486
margins and a stated joint structure. It is not the measurement of record.

## Observed margins

These counts are observed facts about the S486 run. They appear in ticket #691
and in `docs/findings/stage1a-regime-operating-characteristics.md` (#684):

| Arm | n | Correct | manifest_read |
| --- | --- | --- | --- |
| Full | 97 | 50 | 32 |
| Placebo | 97 | 34 | 28 |
| Null-A | 97 | 34 | — |

## Stated joint structure (stand-in only)

Correctness and manifest_read flags are placed at the launch indices below.
This structure is chosen so every printed number is auditable by hand. It is
not claimed to be the true S486 joint.

| Quantity | Stand-in placement |
| --- | --- |
| Full correct | epochs 1–50 |
| Full manifest_read | epochs 1–32 |
| Placebo correct | epochs 1–34 |
| Placebo manifest_read | epochs 1–28 |
| Null-A correct | epochs 1–34 |

Consequences of this structure, visible in the screen output:

- Every Full and Placebo reader is correct (read flag sits inside the correct
  prefix). The read-to-outcome sub-rates of 100% among readers are an artifact
  of this stand-in, not a finding about the real run.
- Full and Placebo correctness are nested (Placebo correct ⊆ Full correct), so
  the within-pair table is both_correct=34, full_only=16, placebo_only=0,
  neither=47 and phi is strongly positive. The real run's concordance is
  different; only the real readout can measure it.
- Placebo and Null-A streams are identical, so the observed difference is 0.

## Order conventions

- The anytime-valid interval is computed from the launch-order streams in the
  readout. This stand-in uses successes first in launch order.
- The n-to-exclude search scales the same rates (34/97) and places successes
  at evenly-spaced launch indices. That convention is named in the screen
  output. The real readout's launch order replaces the stand-in order when the
  script is run against the operator's path.

## How to replace this stand-in

```bash
PYTHONPATH=src python scripts/screens/419/stage1a_readout_691.py \
  /path/to/S486-stage1a/run.log
```

The script accepts a `.json` file, a `run.log` whose tail carries a JSON block
with per-epoch rows, or a directory holding either. It prints the three
sections. The findings record quotes the numbers that run produces.
