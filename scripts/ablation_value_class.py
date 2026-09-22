"""Ablate the value_class branch across every verdict on disk and count changes.

Registered as the next observation in the class-hypothesis pre-registration
(docs/findings/class-hypothesis-preregistration.md, 2026-09-20): one static
run, no network, no model call.

For every SERS receipt that carries a screen measurement (p0), this script
recomputes the verdict twice:

  1. Shipped: verdict.py as-is, with the receipt's own value_class.
  2. Ablated: the value_class branch replaced by the TRANSFORMATIVE_LIFT path
     for every class (all above-bar p0 -> CUT(subsumed)).

Receipts without a screen measurement (p0) are listed as unrecomputable.
The paired-verdict path does not branch on value_class, so those receipts
are not affected by the ablation and are excluded from the count.

Usage:
    python scripts/ablation_value_class.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

_RECEIPT_DIRS = [
    _REPO_ROOT / "docs" / "sers" / "receipts",
    _REPO_ROOT / "docs" / "sers" / "receipts" / "superseded",
]


def _load_receipts() -> list[tuple[Path, dict[str, Any], bool]]:
    """Load every JSON receipt from the registered receipt directories.

    Returns (path, data, is_superseded) triples.
    """
    receipts: list[tuple[Path, dict[str, Any], bool]] = []
    for directory in _RECEIPT_DIRS:
        if not directory.is_dir():
            continue
        is_superseded = "superseded" in str(directory)
        for path in sorted(directory.glob("*.json")):
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            receipts.append((path, data, is_superseded))
    return receipts


def _has_screen_measurement(data: dict[str, Any]) -> bool:
    """True if this receipt carries a p0 measurement (screen path)."""
    measurements: dict[str, Any] = data.get("measurements", {})
    return "p0" in measurements


def _extract_p0(data: dict[str, Any]) -> float | None:
    """Return the p0 value from a screen-path receipt, or None."""
    measurements: dict[str, Any] = data.get("measurements", {})
    p0_field = measurements.get("p0")
    if p0_field is None:
        return None
    if isinstance(p0_field, dict):
        return p0_field.get("value")
    return None


def _extract_value_class(data: dict[str, Any]) -> str | None:
    """Return the value_class string from a receipt, or None."""
    return data.get("value_class")


def _recompute_screen_verdict(
    p0: float, value_class: str | None
) -> tuple[tuple[str, str | None], tuple[str, str | None]]:
    """Recompute the screen verdict for shipped and ablated paths.

    Returns ((shipped_verdict, shipped_sub), (ablated_verdict, ablated_sub)).
    """
    from skill_harness.aggregation.verdict import ValueClass, screen_verdict

    # Map receipt string to ValueClass enum
    vc_map: dict[str, ValueClass] = {
        "transformative-lift": ValueClass.TRANSFORMATIVE_LIFT,
        "trap-discipline": ValueClass.TRAP_DISCIPLINE,
        "calibration": ValueClass.CALIBRATION,
    }
    vc_enum = vc_map.get(value_class) if value_class else None

    # Shipped path
    shipped = screen_verdict(p0, value_class=vc_enum)
    # Ablated path: treat every class as TRANSFORMATIVE_LIFT
    ablated = screen_verdict(p0, value_class=ValueClass.TRANSFORMATIVE_LIFT)

    return (
        shipped.verdict.value,
        shipped.cut_sub_reason.value if shipped.cut_sub_reason else None,
    ), (
        ablated.verdict.value,
        ablated.cut_sub_reason.value if ablated.cut_sub_reason else None,
    )


def _short_name(path: Path, is_superseded: bool) -> str:
    """Return a short display name for a receipt path."""
    name = path.name.removesuffix(".json")
    if is_superseded:
        return f"{name} (superseded)"
    return name


def main() -> int:
    receipts = _load_receipts()
    if not receipts:
        print("No receipts found.", file=sys.stderr)
        return 1

    rows: list[dict[str, str]] = []
    changes = 0
    no_recompute = 0

    for path, data, is_superseded in receipts:
        name = _short_name(path, is_superseded)
        skill = data.get("skill_name", "?")
        stored_verdict = data.get("verdict", "?")

        if not _has_screen_measurement(data):
            rows.append(
                {
                    "receipt": name,
                    "skill": skill,
                    "stored": stored_verdict,
                    "shipped": "n/a",
                    "ablated": "n/a",
                    "changed": "no_recompute",
                }
            )
            no_recompute += 1
            continue

        p0 = _extract_p0(data)
        if p0 is None:
            rows.append(
                {
                    "receipt": name,
                    "skill": skill,
                    "stored": stored_verdict,
                    "shipped": "n/a",
                    "ablated": "n/a",
                    "changed": "no_recompute",
                }
            )
            no_recompute += 1
            continue

        value_class = _extract_value_class(data)
        result = _recompute_screen_verdict(p0, value_class)
        (s_verdict, s_sub), (a_verdict, a_sub) = result
        changed = s_verdict != a_verdict
        if changed:
            changes += 1

        rows.append(
            {
                "receipt": name,
                "skill": skill,
                "stored": stored_verdict,
                "shipped": s_verdict + (f"({s_sub})" if s_sub else ""),
                "ablated": a_verdict + (f"({a_sub})" if a_sub else ""),
                "changed": "YES" if changed else "no",
            }
        )

    # Print table
    header = f"{'Receipt':<50} {'Skill':<35} {'Shipped':<30} {'Ablated':<30} {'Changed':<12}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['receipt']:<50} {row['skill']:<35} {row['shipped']:<30} "
            f"{row['ablated']:<30} {row['changed']:<12}"
        )

    print()
    print(f"Total receipts:        {len(rows)}")
    print(f"Recomputable (screen): {len(rows) - no_recompute}")
    print(f"Not recomputable:      {no_recompute}")
    print(f"Verdicts changed:      {changes}")
    print(f"Verdicts unchanged:    {len(rows) - no_recompute - changes}")

    if changes == 0:
        print()
        print(
            "Zero verdicts changed: H1 is moot in the deployed instrument. "
            "The value_class branches are policy with no observed effect."
        )
    else:
        print()
        print(
            f"{changes} verdict(s) changed: the question is live. "
            f"The count ({changes}) measures how much rides on the "
            f"value_class branch in the shipped instrument."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
