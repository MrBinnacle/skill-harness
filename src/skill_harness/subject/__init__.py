"""Agentic subject layer (v0.2) — Inspect-based paired Full/Null execution.

skill-harness does not run agents itself; it delegates the agentic subject to
Inspect (`inspect_ai`) + `inspect_swe.claude_code()` and keeps what it is
actually for: pairing, evidence admissibility, and evidence. Install the subject layer
with the optional extra:

    pip install "skill-harness[inspect]"

Public surface:
  HarnessPin           — frozen record of the exact subject-harness configuration;
                         an unpinned or cross-arm-drifted harness renders a trial
                         inadmissible (v0.2 gate, "Harness pin" field).
  build_paired_tasks() — the Full-vs-Null contrast as two Inspect tasks that are
                         identical except for the one skill under test.
"""

from skill_harness.subject.inspect_adapter import build_paired_tasks
from skill_harness.subject.pin import HarnessPin

__all__ = ["HarnessPin", "build_paired_tasks"]
