# examples/

A step-by-step walkthrough of a real measurement, start to finish — the same run described in
the [case study](../docs/case-studies/ai-slop-sentinel-under-ablation.md), reproducible on
your own machine. The offline parts are free; the live measurement steps need an API key and
spend real money (budget caps are enforced, and every command is dry-run unless you pass
`--execute`).

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

Both API surfaces accept EITHER `ANTHROPIC_API_KEY` (direct Anthropic) OR
`OPENROUTER_API_KEY` (auto-routed via OpenRouter's Anthropic-compatible endpoint):

- `skill init` — the extractor's OpenRouter fallback landed on `main` 2026-06-09
  (`b5b9fe6`). It is NOT in the `v0.1.0` tag; reproduce against `main`.
- `run ablation --execute` — accepts either key (OpenRouter routing emits a stderr
  warning). Pass `-SubjectModel` to vary the model id; the key/model matrix is
  documented in the script's header comments.

The reproduction script exits with a helpful error if neither key is present. The
case study's HALT 2 narrative records the author hitting the pre-fallback asymmetry
in real time — historical context, no longer a wall on `main`.
