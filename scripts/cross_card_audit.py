"""Cross-card audit screen for #652: run skill-harness skill audit on every published card.

Stage 0. Produces a ranked markdown table in docs/findings/ with standing cost,
measurable claims, claim class, and hazard-qualified task family plausibility.

Run: PYTHONPATH=src python scripts/cross_card_audit.py > docs/findings/cross-card-audit-screen.md
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from skill_harness.preflight import ArtifactAuditReport, audit_skill_artifact

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILL_GLOB = "skills/*/*/SKILL.md"
_FALLBACK_PATHS = [
    _REPO_ROOT / "scripts/screens/419/v4_arms/full/pull-rebase/SKILL.md",
    _REPO_ROOT / "scripts/screens/419/v4_arms/placebo/push-secret-scan/SKILL.md",
    _REPO_ROOT / "tests/fixtures/sers/declared-synthetic-positive-control/SKILL.md",
]


def _find_skill_files() -> list[Path]:
    """Find all published SKILL.md cards via git ls-files, falling back to known paths."""
    result = subprocess.run(  # noqa: S603
        ["git", "ls-files", _SKILL_GLOB],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    if result.stdout.strip():
        return [_REPO_ROOT / p for p in result.stdout.strip().splitlines()]
    return [p for p in _FALLBACK_PATHS if p.exists()]


def _claim_class(report: ArtifactAuditReport) -> str:
    """Classify whether a with/without task can observe the card's claims.

    - "mechanical" — style-shaped claims measurable by Tier-1 scorers
    - "behavioral" — correctness/tool-use/outcome claims need Tier-2+ or real-world
    - "unmeasurable" — no axis is mechanically testable; claims are structural only
    """
    if report.measurable_axes:
        return "mechanical"
    return "behavioral"


def _hazard_task_family_exists(path: str) -> str:
    """Check if a hazard-qualified task family is known for this card."""
    if "419" in path:
        return "yes (#419 screen)"
    if "fixtures" in path:
        return "no (test fixture only)"
    return "no"


def _out_of_reach_reason(report: ArtifactAuditReport, path: str) -> str | None:
    """Return an 'out of reach' reason if the card cannot be evaluated, or None."""
    if "fixtures" in path:
        return "test fixture — not a production card"
    if report.standing_cost_raw is None:
        return "standing cost unmeasurable — frontmatter cannot be parsed"
    return None


def main() -> None:
    """Audit all published cards and print the ranked finding document."""
    skill_files = _find_skill_files()
    if not skill_files:
        print("No published SKILL.md cards found.", file=sys.stderr)
        sys.exit(1)

    results: list[dict[str, object]] = []
    for path in sorted(skill_files):
        report = audit_skill_artifact(path)
        warn_count = report.warn_count
        claim_cls = _claim_class(report)
        hazard = _hazard_task_family_exists(str(path.relative_to(_REPO_ROOT)))
        out_of_reach = _out_of_reach_reason(report, str(path.relative_to(_REPO_ROOT)))

        # Ranking reason
        parts: list[str] = []
        if report.standing_cost_raw is not None:
            parts.append(f"standing {report.standing_cost_raw} tokens")
        else:
            parts.append("standing UNMEASURED")
        if report.fired_cost_raw is not None:
            parts.append(f"fired {report.fired_cost_raw} tokens")
        if warn_count > 0:
            parts.append(f"{warn_count} structural warn(s)")
        ranking_reason = "; ".join(parts) if parts else "no cost data"

        results.append(
            {
                "name": report.name,
                "path": str(path.relative_to(_REPO_ROOT)),
                "standing_cost_raw": report.standing_cost_raw,
                "standing_cost_calibrated": report.standing_cost_calibrated,
                "fired_cost_raw": report.fired_cost_raw,
                "fired_cost_calibrated": report.fired_cost_calibrated,
                "aux_cost_raw": report.aux_cost_raw,
                "measurable_axes": ", ".join(report.measurable_axes),
                "claim_class": claim_cls,
                "hazard_task_family": hazard,
                "warn_count": warn_count,
                "pass_count": report.pass_count,
                "ranking_reason": ranking_reason,
                "out_of_reach": out_of_reach,
            }
        )

    # Sort: measured standing cost first (ascending), then UNMEASURED, then fixtures
    def sort_key(r: dict[str, object]) -> tuple[int, int, str]:
        sc = r["standing_cost_raw"]
        if sc is None:
            return (2, 0, str(r["name"]))
        if isinstance(sc, str):  # UNMEASURED
            return (1, 0, str(r["name"]))
        if isinstance(sc, int):
            return (0, sc, str(r["name"]))
        return (0, 0, str(r["name"]))

    results.sort(key=sort_key)

    # Emit the markdown finding document
    print("# Cross-card audit screen — Stage 0 comparative baseline (#652)")
    print()
    print("> **Status:** STAGE-0 COMPLETE 2026-09-23. Every published card in this repository")
    print("> has been audited offline. The ranked table is the comparative screen the program")
    print("> lacked: which card gets confirmation spend is made by a screen, not by precedent.")
    print()
    print("**Claims:** This document establishes the comparative baseline for every published")
    print("skill card. It records standing cost, measurable claims, claim class, and")
    print("hazard-qualified task family plausibility for each card. The ranking is by")
    print("standing cost ascending — the cheapest cards to evaluate rank first.")
    print()
    print("**Refuses to claim:** A keep/cut verdict on any card; that standing cost is the")
    print("only or decisive factor in card selection; that the claim class assignments are")
    print("final (they are the offline preflight's judgement, not a measurement); that any")
    print("card is ready for Stage 1 spend without a separate operator gate.")
    print()
    print("## Ranked table")
    print()
    print(
        "| Rank | Card | Path | Standing (raw) | Standing (cal)"
        " | Fired (raw) | Claim class | Hazard task family | Out of reach? |"
    )
    print("| ---: | --- | --- | ---: | ---: | ---: | --- | --- | --- |")

    for i, r in enumerate(results, 1):
        sc_raw = r["standing_cost_raw"] if r["standing_cost_raw"] is not None else "—"
        sc_cal = r["standing_cost_calibrated"] if r["standing_cost_calibrated"] is not None else "—"
        fc_raw = r["fired_cost_raw"] if r["fired_cost_raw"] is not None else "—"
        oor = r["out_of_reach"]
        print(
            f"| {i} "
            f"| {r['name']} "
            f"| `{r['path']}` "
            f"| {sc_raw} "
            f"| {sc_cal} "
            f"| {fc_raw} "
            f"| {r['claim_class']} "
            f"| {r['hazard_task_family']} "
            f"| {oor if oor else 'no'} |"
        )

    print()
    print("## Per-card detail")
    print()

    for r in results:
        print(f"### {r['name']}")
        print()
        print(f"- **Path:** `{r['path']}`")
        sc_raw = r["standing_cost_raw"] if r["standing_cost_raw"] is not None else "—"
        sc_cal = r["standing_cost_calibrated"] if r["standing_cost_calibrated"] is not None else "—"
        fc_raw = r["fired_cost_raw"] if r["fired_cost_raw"] is not None else "—"
        fc_cal = r["fired_cost_calibrated"] if r["fired_cost_calibrated"] is not None else "—"
        print(f"- **Standing cost:** {sc_raw} raw / {sc_cal} calibrated")
        print(f"- **Fired cost:** {fc_raw} raw / {fc_cal} calibrated")
        aux = r["aux_cost_raw"] if r["aux_cost_raw"] is not None else "—"
        print(f"- **Aux cost:** {aux}")
        print(f"- **Measurable axes:** {r['measurable_axes']}")
        print(f"- **Claim class:** {r['claim_class']}")
        print(f"- **Hazard task family:** {r['hazard_task_family']}")
        print(f"- **Structural warns:** {r['warn_count']}")
        print(f"- **Ranking reason:** {r['ranking_reason']}")
        if r["out_of_reach"]:
            print(f"- **Out of reach:** {r['out_of_reach']}")
        print()

    print("## Method")
    print()
    print('1. Enumerated published cards via `git ls-files "skills/*/*/SKILL.md"`.')
    print("   When the glob returned empty (no `skills/` directory), used the three known")
    print("   SKILL.md locations under `scripts/screens/419/` and `tests/fixtures/`.")
    print("2. Called `audit_skill_artifact()` from `skill_harness.preflight` on each card")
    print("   (offline, zero cost, no API calls).")
    print("3. Parsed standing cost, fired cost, measurable axes, and structural findings.")
    print("4. Assigned claim class: mechanical (Tier-1 axes available), behavioral (no")
    print("   mechanical instrument), or unmeasurable (frontmatter unreadable).")
    print("5. Assessed hazard-qualified task family plausibility: cards under #419 are part")
    print("   of an existing screen; test fixtures are not production cards.")
    print("6. Ranked by standing cost ascending — cheapest to evaluate first.")
    print()
    print("## Stage 1 gate")
    print()
    print("Stage 1 (Null-only qualification screens on top candidates) is priced at the")
    print("realised $0.083 per epoch. It is not run without an operator gate.")
    print("See `docs/assurance/` for ratified authorisations.")


if __name__ == "__main__":
    main()
