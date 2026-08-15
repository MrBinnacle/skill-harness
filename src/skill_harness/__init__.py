"""Skill Harness — an evaluation harness for reusable AI agent skills.

Answers the slot question with one of three verdicts — KEEP / CUT /
CAN'T-TELL-YET — via a paired with-vs-without comparison; when the evidence
doesn't support a verdict, the answer is UNMEASURED, never a manufactured
score.

NOTE: ``__version__`` hand-syncs with ``pyproject.toml`` — the release gate
(``scripts/release_gate.py``, run in CI and as the first job of the publish
pipeline) blocks any tag where the two disagree.
"""

__version__ = "0.2.3"
