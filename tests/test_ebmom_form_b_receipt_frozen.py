"""The R = 40 form-B reproduction receipt is frozen, and says so (#458, resolving #450).

``docs/assurance/ebmom-form-b-reproduction-R40-SMOKE_NO.json`` was written at ``d39440d``
(#441) and records ``reproduces: true`` / ``total_differences: 0`` for the prototype's
``cand_bpB`` column. ``#442`` (``60a6548``) then replaced the plug-in on the admitted path with
the admission-conditioned bootstrap, so the receipt's own command line no longer reproduces it.

The defect #450 filed was not the staleness. It was the SILENCE: no file under ``tests/`` named
the receipt, so it stayed green while the claim it carries stopped being true. A receipt nobody
checks is indistinguishable from one that is still correct.

#450 accepts either a test that regenerates the receipt inside the gate, or a documented reason
it cannot. The reason is documented in the Markdown twin, and this module holds it down: the
receipt's bytes are pinned, and the twin must keep declaring the freeze. Regenerating or
editing the receipt turns this red, which forces whoever does it to state in the twin what the
new file measures.

Why not regenerate it here instead: the receipt's ``expected_file`` is not in the repository,
and it is not byte-reproducible if regenerated -- the prototype dump embeds a wall-clock
``seconds`` field per regime, so the receipt's ``expected_sha256`` can never be re-satisfied.
The twin carries that measurement in full.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ASSURANCE = _REPO_ROOT / "docs" / "assurance"

RECEIPT = _ASSURANCE / "ebmom-form-b-reproduction-R40-SMOKE_NO.json"
TWIN = _ASSURANCE / "ebmom-form-b-reproduction-R40-SMOKE_NO.md"

# Bytes of the receipt as written at d39440d and frozen at #458. Not a hash of a measurement
# this test performs -- a hash of the artifact this test refuses to let change silently.
FROZEN_RECEIPT_SHA256 = "c9d2246f2a5b5ac9934428b03ef44b06b4afe37ae5494b1609179ee2ade28e0a"

# The commits the twin must keep naming: the state the receipt holds for, and the change that
# superseded it. A twin that stops naming either has stopped explaining the freeze.
COMMIT_RECEIPT_HOLDS_FOR = "d39440d"
COMMIT_THAT_SUPERSEDED_IT = "60a6548"


def test_receipt_bytes_are_frozen() -> None:
    """The receipt is byte-for-byte what was frozen.

    If this goes red the receipt was regenerated or edited. That may well be right -- but it
    is not a silent operation, because the twin has to be rewritten to say what the new file
    measures, and this pin updated alongside it.
    """
    actual = hashlib.sha256(RECEIPT.read_bytes()).hexdigest()
    assert actual == FROZEN_RECEIPT_SHA256, (
        f"{RECEIPT.name} changed.\n"
        f"  frozen sha256 {FROZEN_RECEIPT_SHA256}\n"
        f"  actual sha256 {actual}\n"
        f"Update {TWIN.name} to state what the new file measures, then update this pin."
    )


def test_the_receipt_still_carries_the_claim_the_twin_explains() -> None:
    """The twin explains a specific claim; this asserts the receipt is still making it.

    Without this, the twin could go on describing a receipt whose contents had moved
    underneath it -- the same drift, one level up.
    """
    payload: dict[str, Any] = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert payload["expected_column"] == "cand_bpB"
    assert payload["replicates"] == 40
    assert payload["root_seed"] == "SMOKE_NOT_CONFIRMATORY"
    assert payload["is_confirmatory"] is False
    assert payload["reproduces"] is True
    assert payload["total_differences"] == 0


def test_the_twin_exists_and_declares_the_freeze() -> None:
    """A frozen record has to say it is frozen, where a reader will see it."""
    assert TWIN.is_file(), (
        f"{TWIN.name} is missing. The receipt asserts a reproduction that production stopped "
        f"performing at {COMMIT_THAT_SUPERSEDED_IT}; without the twin, a reader has no way to "
        f"learn that from the repository."
    )
    text = TWIN.read_text(encoding="utf-8")

    assert "FROZEN" in text, "the twin must state the receipt's status in terms a reader sees"
    for commit in (COMMIT_RECEIPT_HOLDS_FOR, COMMIT_THAT_SUPERSEDED_IT):
        assert commit in text, (
            f"the twin no longer names {commit}. A freeze is only meaningful with the commit "
            f"it holds for and the change that superseded it."
        )
