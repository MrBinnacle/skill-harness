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

  Local-only subject registration (issue #556):
  register_local_subject() — register a local-only subject by path.
  resolve_subject() — resolve a subject by verifying its digest matches.
  compute_subject_digest() — compute SHA-256 digest of a SKILL.md file.
  render_subject_receipt() — create a receipt for a subject measurement.
  load_registry() — load the local subject registry.

  Git origin sidecar (issue #620):
  OriginSidecar        — a seed directory (bare repo + hooks) named by its digest;
                         passed to build_paired_tasks(origin=...), it is served
                         from a second container the agent can push to but not read.
  prove_seed_only_twins() — check two sidecar composes differ only in the seed.
  SeedTwinProof / TwinComposeError — that check's result and its refusal.
"""

from skill_harness.subject.inspect_adapter import (
    NormalisedSkillResult,
    SkillCorpusCoverage,
    build_paired_tasks,
    normalise_skill_frontmatter,
    skill_corpus_coverage,
)
from skill_harness.subject.local import (
    compute_subject_digest,
    list_local_subjects,
    load_registry,
    register_local_subject,
    render_subject_receipt,
    resolve_subject,
)
from skill_harness.subject.origin_sidecar import (
    OriginSidecar,
    SeedTwinProof,
    TwinComposeError,
    prove_seed_only_twins,
)
from skill_harness.subject.pin import HarnessPin

__all__ = [
    "HarnessPin",
    "NormalisedSkillResult",
    "OriginSidecar",
    "SeedTwinProof",
    "SkillCorpusCoverage",
    "TwinComposeError",
    "build_paired_tasks",
    "compute_subject_digest",
    "list_local_subjects",
    "load_registry",
    "normalise_skill_frontmatter",
    "prove_seed_only_twins",
    "register_local_subject",
    "render_subject_receipt",
    "resolve_subject",
    "skill_corpus_coverage",
]
