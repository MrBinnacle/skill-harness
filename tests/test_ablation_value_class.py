"""Ablation-script smoke: one synthetic receipt that must change, one that must not.

Feeds the ablation logic two hand-built SERS receipt dicts and asserts the
registered outcome for each.  The test exercises the recomputation path
directly (no subprocess, no I/O) so it fails for the right reason when the
value_class branch is not ablated.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from skill_harness.aggregation.verdict import ValueClass, screen_verdict

_SCREEN_RECEIPT_TEMPLATE: dict[str, Any] = {
    "sers_version": "1.0.0",
    "skill_name": "test-skill",
    "verdict": "CANT_TELL_YET",
    "cut_sub_reason": None,
    "unmeasured_sub_reason": None,
    "value_class": None,
    "wrong_instrument": False,
    "declared_synthetic_control": True,
    "measurements": {
        "p0": {"value": 0.5, "passes": 4, "epochs": 8},
        "go_nogo": "NOT_APPLICABLE",
    },
}


def _make_receipt(
    skill_name: str,
    value_class: str | None,
    p0: float,
) -> dict[str, Any]:
    """Build a minimal screen-path SERS receipt dict."""
    r: dict[str, Any] = dict(_SCREEN_RECEIPT_TEMPLATE)
    r["skill_name"] = skill_name
    r["value_class"] = value_class
    r["measurements"] = dict(_SCREEN_RECEIPT_TEMPLATE["measurements"])
    r["measurements"]["p0"] = {"value": p0, "passes": int(p0 * 8), "epochs": 8}
    return r


def _recompute(
    p0: float, value_class: str | None
) -> tuple[tuple[str, str | None], tuple[str, str | None]]:
    """Run the ablation's recomputation logic for a single receipt."""
    vc_map: dict[str, ValueClass] = {
        "transformative-lift": ValueClass.TRANSFORMATIVE_LIFT,
        "trap-discipline": ValueClass.TRAP_DISCIPLINE,
        "calibration": ValueClass.CALIBRATION,
    }
    vc_enum = vc_map.get(value_class) if value_class else None

    shipped = screen_verdict(p0, value_class=vc_enum)
    ablated = screen_verdict(p0, value_class=ValueClass.TRANSFORMATIVE_LIFT)

    return (
        shipped.verdict.value,
        shipped.cut_sub_reason.value if shipped.cut_sub_reason else None,
    ), (
        ablated.verdict.value,
        ablated.cut_sub_reason.value if ablated.cut_sub_reason else None,
    )


def test_trap_discipline_above_bar_must_change() -> None:
    """A trap-discipline receipt at p0=1.0 MUST change under ablation.

    Shipped: CANT_TELL_YET (wrong instrument -- the transformative-lift
    instrument cannot see a trap skill's value).
    Ablated: CUT(subsumed) -- the ablated path treats every class as
    transformative-lift, so above-bar p0 maps to subsumed.
    """
    receipt = _make_receipt("test-trap-skill", "trap-discipline", p0=1.0)
    p0_val = receipt["measurements"]["p0"]["value"]
    vc = receipt["value_class"]

    (s_verdict, _s_sub), (a_verdict, _a_sub) = _recompute(p0_val, vc)

    assert s_verdict == "CANT_TELL_YET", (
        f"shipped verdict must be CANT_TELL_YET for trap-discipline at p0=1.0, got {s_verdict}"
    )
    assert a_verdict == "CUT", (
        f"ablated verdict must be CUT for above-bar p0 under TRANSFORMATIVE_LIFT, got {a_verdict}"
    )
    assert s_verdict != a_verdict, (
        "trap-discipline above-bar receipt did NOT change under ablation -- "
        "the value_class branch has no effect, which contradicts the instrument"
    )


def test_transformative_lift_below_bar_must_not_change() -> None:
    """A transformative-lift receipt at p0=0.0 MUST NOT change under ablation.

    Below the transformative ceiling (0.3), both shipped and ablated paths
    yield CANT_TELL_YET (sourced candidate). The value_class branch only
    fires above the ceiling, so ablating it cannot affect this receipt.
    """
    receipt = _make_receipt("test-lift-skill", "transformative-lift", p0=0.0)
    p0_val = receipt["measurements"]["p0"]["value"]
    vc = receipt["value_class"]

    (s_verdict, _s_sub), (a_verdict, _a_sub) = _recompute(p0_val, vc)

    assert s_verdict == "CANT_TELL_YET", (
        f"shipped verdict must be CANT_TELL_YET for below-bar p0, got {s_verdict}"
    )
    assert a_verdict == "CANT_TELL_YET", (
        f"ablated verdict must be CANT_TELL_YET for below-bar p0, got {a_verdict}"
    )
    assert s_verdict == a_verdict, (
        "transformative-lift below-bar receipt changed under ablation -- "
        "the below-bar path must not depend on value_class"
    )


def test_ablation_script_exits_zero(tmp_path: Path) -> None:
    """The script must exit 0 on a minimal receipt directory."""
    receipt_dir = tmp_path / "docs" / "sers" / "receipts"
    receipt_dir.mkdir(parents=True)
    receipt = _make_receipt("smoke-skill", "trap-discipline", p0=0.8)
    (receipt_dir / "smoke.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "scripts" / "ablation_value_class.py"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    result = subprocess.run(
        ["python", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(tmp_path),
        check=False,
    )
    assert result.returncode == 0, (
        f"script exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "CUT(subsumed)" in result.stdout, (
        "script output must show the ablated CUT(subsumed) verdict"
    )
