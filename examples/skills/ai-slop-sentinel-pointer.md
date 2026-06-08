# ai-slop-sentinel skill — retrieval instructions

The `ai-slop-sentinel` skill is not shipped verbatim in this repository. It has its
own provenance and may have its own license terms.

## For Claude Code users

The skill lives at:

```
~/.claude/skills/ai-slop-sentinel/SKILL.md
```

If you have Claude Code installed and the skill is present, pass that path directly
to `skill init`:

```powershell
$py = ".venv\Scripts\python.exe"
$env:PYTHONPATH = "src"
& $py -m skill_harness skill init "$env:USERPROFILE\.claude\skills\ai-slop-sentinel\SKILL.md" --execute
```

## If the skill is not installed

Install it via the Claude Code skills registry:

```powershell
npx skills add ai-slop-sentinel
```

Then locate it at `~/.claude/skills/ai-slop-sentinel/SKILL.md`.

## What the skill contains

`ai-slop-sentinel` is a code-review skill that instructs Claude to review
AI-generated code against a curated watch of AI-slop anti-patterns, citing the watch
by entry for each flag. It is the skill evaluated in the v0.1.0 case study at
`docs/case-studies/ai-slop-sentinel-under-ablation.md`.

The source SHA256 used in the published case study run:
`074595b7a61821d4f0b80bf870b680d49326b27aab51e32e844d4e141607170b`

Note: the extractor is stochastic. Re-extraction against the same source SHA may
shift the clause count by 1-2. The UNMEASURED result is not stochastic.
