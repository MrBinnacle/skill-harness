"""Tier-1 mechanical oracle metrics.

Each metric in this package is:
- Deterministic: same input always produces the same output.
- Offline: no network calls permitted (enforced by pytest-socket in tests).
- Versioned: carries an implementation_hash (SHA-256 of frozen data files
  or implementation constants) so frozen regression cases can be re-audited
  when the metric changes.

Provenance/versioning is recorded in the ``metric_versions`` evidence-DB table
(``storage/repositories/evidence/metric_versions.py``), written at ingest time
by ``subject/ingest.py`` — NOT by an in-process registry. (F1, S49 hostile
review: a module-level ``registry.py`` offering ``register_metric()`` /
``get_metric()`` / ``list_metrics()`` previously lived here, tested but with
zero production callers — none of the five metric modules below ever called
``register_metric()``, so the claimed "registered on import" auto-downgrade
behavior never ran. Deleted rather than wired: the provenance/tiering job it
was meant to do is already done, for real, by the DB-backed metric_versions
table, so wiring it would have been parallel machinery duplicating an
existing mechanism, not closing a gap.)

Registered ablation axes (``axis_registry.py`` is the single authority for this
list; ``ablation/confound.py`` and the extractor system prompt both derive from
it rather than restating it — #117):
  hedge_index.py     — Hedge Index (frozen wordlist SHA-256 pinned).
  verbosity.py       — Token count via tiktoken cl100k_base (offline).
  structure_score.py — Heading + paragraph-break density.
  compliance_proxy.py — Directive-keyword density (honest heuristic).
  citation_presence_per_flag.py — Flag-citation ratio for sentinel-style
                                   review outputs (ai-slop-sentinel clause 0).

Also in this package, deliberately NOT a registered axis:
  end_state_categorical.py — Categorical end-state scorer for instruction-
      conflict screens (DIF K5/K9). Not a ``(text) -> float`` metric: it
      consumes an ``EpochEndState`` of mechanical sandbox facts and returns a
      4-way category plus an evidence-admissibility flag, so it cannot enter ablation's
      Full-vs-Ablated text-delta path. See ``axis_registry.TIER1_AXES``.

``axis_registry.py`` is not a revival of the deleted ``registry.py`` described
above: it registers nothing at import time, carries no provenance, and is a
frozen name/description table with live production consumers.
"""

__all__: list[str] = []
