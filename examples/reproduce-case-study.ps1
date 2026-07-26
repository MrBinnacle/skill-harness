# reproduce-case-study.ps1
# One-shot reproduction of the ai-slop-sentinel case study.
#
# Prerequisites:
#   - Python 3.12+ with venv at .venv (run: python -m venv .venv && .venv\Scripts\pip install -e ".[dev]")
#   - ANTHROPIC_API_KEY (Anthropic direct) OR OPENROUTER_API_KEY (auto-routed via
#     OpenRouter's Anthropic-compatible endpoint, with a stderr warning) set in the
#     environment. Both `skill init` and `run ablation --execute` accept either key
#     (extractor fallback landed on main 2026-06-09, b5b9fe6 — not in the v0.1.0 tag).
#     -SubjectModel selects the model id for `run ablation --execute`.
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

if (-not $env:ANTHROPIC_API_KEY -and -not $env:OPENROUTER_API_KEY) {
    Write-Error @"
Neither ANTHROPIC_API_KEY nor OPENROUTER_API_KEY is set, and `skill init` requires
one of the two. The extractor auto-detects which key is present and routes via
OpenRouter (with a stderr warning) when only OPENROUTER_API_KEY is set — see
extractor/claude.py::_make_extractor_client().

Set ANTHROPIC_API_KEY for direct Anthropic billing, or OPENROUTER_API_KEY if you
only hold OpenRouter credentials. See examples/README.md "API-key requirements
(honest)" for the full matrix — the rest of this script (`run ablation --execute`)
accepts either key the same way.
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
