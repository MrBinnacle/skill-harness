"""Tier-1 mechanical oracle metrics.

Each metric in this package is:
- Deterministic: same input always produces the same output.
- Offline: no network calls permitted (enforced by pytest-socket in tests).
- Versioned: carries an implementation_hash (SHA-256 of frozen data files
  or implementation constants) so frozen regression cases can be re-audited
  when the metric changes.

Registry:
  register_metric()  — registers a Tier1Metric; auto-downgrades to TIER2 if
                       mechanical_validity_test_passed=False.
  get_metric()       — look up by name.
  list_metrics()     — enumerate all registered metrics.

Available metrics (registered on import of their respective modules):
  hedge_index.py     — Hedge Index (frozen wordlist SHA-256 pinned).
  verbosity.py       — Token count via tiktoken cl100k_base (offline).
  structure_score.py — Heading + paragraph-break density.
  compliance_proxy.py — Directive-keyword density (honest heuristic).
"""

__all__: list[str] = []
