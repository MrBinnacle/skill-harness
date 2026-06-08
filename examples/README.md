# examples/

This directory contains the materials needed to reproduce the v0.1.0 case study on
your own machine.

## Contents

- `skills/ai-slop-sentinel-pointer.md` — how to obtain the `ai-slop-sentinel` skill
  used in the case study, with retrieval instructions.
- `skills/bayesian-eval-discipline-pointer.md` — how to obtain the
  `bayesian-eval-discipline` skill (used in the evaluation discipline itself).
- `reproduce-case-study.ps1` — one-shot PowerShell script that runs the full
  case-study sequence given paths to the two skills above.

## Quick start

```powershell
# 1. Obtain the skill files (see skills/ pointer files)
# 2. Run the reproduction script:
.\examples\reproduce-case-study.ps1 `
    -SkillPath <path-to-ai-slop-sentinel-SKILL.md> `
    -EvidenceDb .\evidence-repro.db `
    -RuntimeDb .\runtime-repro.db
```

The script sets `PYTHONUTF8=1` and `PYTHONHASHSEED=0` before running. See
`docs/concepts/why-pythonutf8-on-windows.md` for why these are required.
