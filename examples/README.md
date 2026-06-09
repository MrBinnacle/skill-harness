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

## API-key requirements (honest)

`skill init` calls the Claude API and **currently requires `ANTHROPIC_API_KEY`** — the
extractor has no OpenRouter fallback yet (v0.2 backlog). The reproduction script will
exit with a helpful error if the key is missing.

`run ablation --execute` (called by this script) accepts either `ANTHROPIC_API_KEY`
(direct) or `OPENROUTER_API_KEY` (auto-routed). Pass `-SubjectModel` to vary the
model id; see the script's `--help` for the matrix.

If you are on Claude Code subscription auth without a direct Anthropic key, the
`skill init` step is currently a hard wall. See the case study's HALT 2 narrative for
the full context (the case study's own author hit this same asymmetry).
