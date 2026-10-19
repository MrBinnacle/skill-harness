"""The firewall walkthrough is on main and public; its claims must stay true.

Two defects, one test each:

* the script itself can silently regress -- the append-only guard it
  demonstrates could start failing open, and nothing would notice unless
  something actually runs it and checks what it printed.
* the script's own prose can go stale -- SCENE 6 used to name three open
  tickets as unbuilt work; all three closed while the sentence kept claiming
  otherwise. A walkthrough that lives on main and makes a claim with a shelf
  life will eventually be lying to whoever reads it next.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WALKTHROUGH = REPO_ROOT / "prototypes" / "PROTOTYPE_firewall_walkthrough.py"


def test_walkthrough_runs_and_every_attack_fails() -> None:
    """The three staged attacks must still fail, every time, with no silent pass.

    Runs the walkthrough end to end with newline input (accepting every
    "[Enter to continue]" prompt) and checks the printed record of what
    happened: three ATTACK FAILED lines, one REFUSED line, and zero
    occurrences of THE EDIT WENT THROUGH. The last assertion is the one that
    matters most -- it is the arm that would catch the append-only guard
    failing open and letting a rewrite through silently instead of raising
    append_only_violation.
    """
    result = subprocess.run(
        [sys.executable, str(WALKTHROUGH)],
        input="\n" * 12,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"walkthrough exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert result.stdout.count("ATTACK FAILED") == 3, (
        f"expected 3 'ATTACK FAILED' lines, found {result.stdout.count('ATTACK FAILED')}"
    )
    assert result.stdout.count("REFUSED") == 1, (
        f"expected 1 'REFUSED' line, found {result.stdout.count('REFUSED')}"
    )
    assert "THE EDIT WENT THROUGH" not in result.stdout, (
        "'THE EDIT WENT THROUGH' appeared in the walkthrough output -- "
        "an attack that should have failed appears to have succeeded"
    )


def test_walkthrough_claims_no_unbuilt_work() -> None:
    """SCENE 6 must not name open tickets as unbuilt work -- that claim expires.

    The walkthrough lives on main, not on a throwaway branch, so a reader can
    land on it at any time. Naming specific open tickets as "not built yet"
    is a claim with a shelf life: it goes stale the moment those tickets
    close, and nothing about running the script would tell you that had
    happened. This repository's standard is that a public claim survives
    being pulled on -- a perishable claim like this one does not survive,
    by construction, so it should not be made at all.
    """
    source = WALKTHROUGH.read_text(encoding="utf-8").lower()
    for phrase in ("not built yet", "stand between here and that"):
        assert phrase not in source, (
            f"found perishable unbuilt-work claim {phrase!r} in "
            f"{WALKTHROUGH.relative_to(REPO_ROOT)} -- a walkthrough on main that "
            "names open tickets as unbuilt goes stale silently once those "
            "tickets close, which is exactly what happened before this test "
            "was added"
        )
