"""Verbosity Tier-1 metric — token count via tiktoken (A35).

Verbosity = number of tokens in ``text`` using the cl100k_base encoding.

Design decisions (A35 verbatim):
- Uses tiktoken ``cl100k_base`` encoding (Claude/GPT-4 base tokenizer).
- Offline after first use — tiktoken caches the BPE vocabulary locally, but
  fetches it over the network on a cold cache (pre-seed ``TIKTOKEN_CACHE_DIR``
  for air-gapped machines). The encoding loads lazily on first tokenization so
  merely importing this module (e.g. via ``skill audit``) never touches the
  network.
- Version-pinned in pyproject.toml: ``tiktoken>=0.7,<1.0``.
- DO NOT replace with ``client.messages.count_tokens()`` — that is a
  network call and violates the Tier-1 offline invariant (A33).

PYTHONHASHSEED=0 discipline: tiktoken tokenisation is deterministic and
does not depend on Python's hash randomisation.  The PYTHONHASHSEED=0
assertion in tests/oracles/tier1/conftest.py still applies globally to
the Tier-1 test session.
"""

from __future__ import annotations

from typing import Final

import tiktoken

# ---------------------------------------------------------------------------
# Encoding constant (A35)
# ---------------------------------------------------------------------------

ENCODING_NAME: Final[str] = "cl100k_base"

# Loaded lazily on first tokenization, then cached for the process lifetime.
# NOT at module import: tiktoken fetches the BPE file over the network on a
# cold cache, and this module is imported by get_default_tier1_scorers(),
# which the fully-offline `skill audit` path calls just to enumerate axis
# names — an eager load here made `skill audit` crash on air-gapped machines
# without ever needing to tokenize anything.
_enc: tiktoken.Encoding | None = None


def get_encoding() -> tiktoken.Encoding:
    """Return the canonical cl100k_base tiktoken encoding (F-7, S55 hostile review).

    This is the SINGLE source of truth for "which tiktoken encoding the harness
    uses" — every other module that needs to tokenize (e.g.
    ``ablation.operator.AblationOperator``, which needs ``.encode()`` for its
    matched-length placeholder algorithm, not just a token count) must call this
    instead of its own ``tiktoken.get_encoding(...)`` call. Before this fix,
    ``ablation/operator.py`` independently called ``tiktoken.get_encoding()``
    with its own hand-duplicated ``"cl100k_base"`` literal (twice, in fact —
    once at module load for ``FILLER_UNIT_TOKENS`` and once per instance in
    ``__init__``) — a name change here would silently NOT propagate there.
    Returns the same cached ``Encoding`` object every call (tiktoken's own
    internal cache plus this module's ``_enc`` memo).
    """
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding(ENCODING_NAME)
    return _enc


# ---------------------------------------------------------------------------
# Public metric function
# ---------------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """Return the number of cl100k_base tokens in ``text``.

    Returns
    -------
    int
        Token count.  0 for empty strings.

    Notes
    -----
    tiktoken is deterministic for a given encoding.  The same ``text``
    input always produces the same token list.  This satisfies the A33
    bit-equality requirement.
    """
    if not text:
        return 0
    return len(get_encoding().encode(text))
