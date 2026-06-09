# reproduce-case-study.ps1
# One-shot reproduction of the ai-slop-sentinel case study.
#
# Prerequisites:
#   - Python 3.11+ with venv at .venv (run: python -m venv .venv && .venv\Scripts\pip install -e ".[dev]")
#   - ANTHROPIC_API_KEY set in the environment (the extractor on `skill init` is
#     currently Anthropic-direct; no OpenRouter fallback yet — v0.2 backlog).
#     `run ablation --execute` accepts OPENROUTER_API_KEY too (auto-routes via OpenRouter
#     with a stderr warning); -SubjectModel selects the model id.
#   - The ai-slop-sentinel SKILL.md (see examples/skills/ai-slop-sentinel-pointer.md)
#
# Usage:
#   .\examples\reproduce-case-study.ps1 -SkillPath <path-to-SKILL.md>
#   .\examples\reproduce-case-study.ps1 -SkillPath <path> -EvidenceDb repro-evidence.db -RuntimeDb repro-runtime.db
#   .\examples\reproduce-case-study.ps1 -SkillPath <path> -SubjectModel "anthropic/claude-sonnet-4-6"

param(
    [Parameter(Mandatory = $true)]
    [string]$SkillPath,

    [string]$EvidenceDb = ".\repro-evidence.db",
    [string]$RuntimeDb  = ".\repro-runtime.db",

    # W2 (commits a9bdacc + f6201a8) added --subject-model to `run ablation`.
    # Default matches the case-study subject. Examples of other values:
    #   claude-sonnet-4-6 (Anthropic direct, requires ANTHROPIC_API_KEY)
    #   gpt-5.5            (OpenAI direct, requires OPENAI_API_KEY)
    #   openai/gpt-5.5     (OpenAI via OpenRouter, requires OPENROUTER_API_KEY)
    #   anthropic/claude-sonnet-4-6 (Anthropic via OpenRouter — for subscription-auth users)
    [string]$SubjectModel = "claude-sonnet-4-6"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Required for cp1252 terminals and byte-stable JSON output
$env:PYTHONUTF8      = "1"
$env:PYTHONHASHSEED  = "0"
$env:PYTHONPATH      = "src"

$py = ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Error "Python venv not found at .venv — run: python -m venv .venv && .venv\Scripts\pip install -e `".[dev]`""
    exit 1
}

if (-not (Test-Path $SkillPath)) {
    Write-Error "Skill file not found: $SkillPath"
    exit 1
}

if (-not $env:ANTHROPIC_API_KEY) {
    Write-Error @"
ANTHROPIC_API_KEY is not set, and `skill init` requires it (the extractor calls
the Claude API directly; OpenRouter fallback for the extractor is a v0.2 backlog
candidate, not in the current build).

If you are on Claude Code subscription auth without a direct Anthropic key, the
`skill init` step is currently a hard wall — same asymmetry the case study's own
author hit and documented as HALT 2. The W2 work (commits a9bdacc + f6201a8) fixed
the analogous gap for `run ablation --execute`, which now accepts OPENROUTER_API_KEY
as a fallback. The extractor side remains.

Workarounds: (a) obtain a temporary Anthropic API key, (b) skip `skill init` and
seed evidence.db by hand (advanced), or (c) wait for v0.2 extractor OpenRouter
fallback. See README.md "API-key requirements" for the full asymmetry.
"@
    exit 1
}

Write-Host "==> skill init (extracting clauses from $SkillPath)"
& $py -m skill_harness skill init $SkillPath --execute --evidence-db $EvidenceDb --runtime-db $RuntimeDb
if ($LASTEXITCODE -ne 0) { Write-Error "skill init failed"; exit 1 }

# Retrieve the skill_id from the evidence DB
$skill_id = & $py -c @"
import sqlite3, sys
conn = sqlite3.connect('$EvidenceDb')
row = conn.execute('SELECT skill_id FROM skills ORDER BY imported_at DESC LIMIT 1').fetchone()
conn.close()
if row: print(row[0])
else: sys.exit(1)
"@
if ($LASTEXITCODE -ne 0) { Write-Error "Could not read skill_id from evidence DB"; exit 1 }
Write-Host "==> skill_id: $skill_id"

Write-Host "==> run ablation (dry-run projection)"
& $py -m skill_harness run ablation $skill_id --evidence-db $EvidenceDb --runtime-db $RuntimeDb

Write-Host "==> run ablation --execute (live run, subject model: $SubjectModel)"
& $py -m skill_harness run ablation $skill_id --execute --subject-model $SubjectModel --evidence-db $EvidenceDb --runtime-db $RuntimeDb

Write-Host "==> run evaluate-skill (Section 16 vector)"
& $py -m skill_harness run evaluate-skill $skill_id --evidence-db $EvidenceDb --runtime-db $RuntimeDb

Write-Host ""
Write-Host "==> JSON output (byte-stable with PYTHONHASHSEED=0)"
& $py -m skill_harness run evaluate-skill $skill_id --format json --evidence-db $EvidenceDb --runtime-db $RuntimeDb

Remove-Item Env:\PYTHONPATH
Remove-Item Env:\PYTHONUTF8
Remove-Item Env:\PYTHONHASHSEED
