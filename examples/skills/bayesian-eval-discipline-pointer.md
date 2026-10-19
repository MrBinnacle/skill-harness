# bayesian-eval-discipline skill — retrieval instructions

The `bayesian-eval-discipline` skill is not shipped verbatim in this repository. It
has its own provenance and may have its own license terms.

## For Claude Code users

The skill lives at:

```
~/.claude/skills/bayesian-eval-discipline/SKILL.md
```

If you have Claude Code installed and the skill is present, pass that path directly
to `skill init`:

```powershell
$py = ".venv\Scripts\python.exe"
$env:PYTHONPATH = "src"
& $py -m skill_harness skill init "$env:USERPROFILE\.claude\skills\bayesian-eval-discipline\SKILL.md" --execute
```

## If the skill is not installed

Install it via the Claude Code skills registry:

```powershell
npx skills add bayesian-eval-discipline
```

Then locate it at `~/.claude/skills/bayesian-eval-discipline/SKILL.md`.

## What the skill contains

`bayesian-eval-discipline` encodes the Beta-Binomial pass rule and the statistical
discipline used by Skill Harness itself: N_min floors, multiplicity correction, and
the specific `P(win_rate > 0.60) >= 0.95` threshold. It is used in the evaluation
framework as a reference document and can itself be evaluated as a skill artifact to
test whether the harness is self-consistent.
