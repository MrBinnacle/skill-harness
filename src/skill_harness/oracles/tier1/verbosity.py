"""Verbosity Tier-1 metric — token count via tiktoken (A35).

Verbosity = number of tokens in ``text`` using the cl100k_base encoding.

Design decisions (A35 verbatim):
- Uses tiktoken ``cl100k_base`` encoding (Claude/GPT-4 base tokenizer).
- Fully offline — tiktoken uses a local BPE vocabulary file.
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

# Loaded once at module import — tiktoken caches the BPE data on first load.
_ENC: Final[tiktoken.Encoding] = tiktoken.get_encoding(ENCODING_NAME)


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
    return len(_ENC.encode(text))
