"""Agentic subject layer (v0.2) — Inspect-based paired Full/Null execution.

skill-harness does not run agents itself; it delegates the agentic subject to
Inspect (`inspect_ai`) + `inspect_swe.claude_code()` and keeps what it is
actually for: pairing, evidence admissibility, and the evidence store. Install
the subject layer with the optional extra:

    pip install "skill-harness[inspect]"

Public surface:
  HarnessPin           — frozen record of the exact subject-harness configuration;
                         an unpinned or cross-arm-drifted harness renders a trial
                         inadmissible (v0.2 gate, "Harness pin" field).
  build_paired_tasks() — the Full-vs-Null contrast as two Inspect tasks that are
                         identical except for the one skill under test.
  normalise_skill_frontmatter() — read SKILL.md, drop keys outside the
                         agentskills.io schema, write a temporary normalised
                         copy for task construction.
  NormalisedSkillResult — result of normalising a skill directory's frontmatter.
  SkillCorpusCoverage  — coverage report for a corpus of skill cards.
  skill_corpus_coverage() — measure how many cards in a directory can be
                         loaded by the harness.
"""

from skill_harness.subject.inspect_adapter import (
    NormalisedSkillResult,
    SkillCorpusCoverage,
    build_paired_tasks,
    normalise_skill_frontmatter,
    skill_corpus_coverage,
)
from skill_harness.subject.pin import HarnessPin

__all__ = [
    "HarnessPin",
    "build_paired_tasks",
    "normalise_skill_frontmatter",
    "NormalisedSkillResult",
    "SkillCorpusCoverage",
    "skill_corpus_coverage",
]
