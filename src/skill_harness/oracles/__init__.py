"""Oracle library for the Skill Harness evaluation framework.

Package structure (per Track C spec):
  tier1/   — Mechanical deterministic metrics (A14, A33).
             Each metric ships with offline validity tests under
             tests/oracles/tier1/ using pytest-socket + PYTHONHASHSEED=0.
  tier2/   — LLM judge module (C.2 scope — not yet implemented).
  calibration/ — Calibration command (C.3/C.4 scope — not yet implemented).

Control-flow invariant: the Python layer owns orchestration,
scoring, storage, and aggregation.  Stochastic model workers are content
generators only.  No module in this package may let a model decide what
gets stored or scored.
"""

__all__: list[str] = []
