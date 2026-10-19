"""Ablation runner — Track D.

D.1 provides:
  - AblationOperator: versioned matched-length neutral substitution (operator.py)
  - ConditionRenderer: renders Full/Ablated_k/Null conditions (render.py)

D.2 provides:
  - AblationRunner: deterministic orchestration engine (runner.py)
  - SubjectClient: subject model wrapper (subject.py)
  - BetaBinomialAccumulator, StoppingReason: sequential stopping (stopping.py)
  - NullAccumulator, detect_confounds, ConfoundEvent: confound monitoring (confound.py)
  - reconcile_run_cost: cost reconciler (reconciler.py)

D.3 will add: CLI wiring in src/skill_harness/cli/main.py
"""
