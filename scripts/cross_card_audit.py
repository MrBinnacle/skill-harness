"""Cross-card audit screen for #652.

Run the offline skill audit on every published card in the declared ``skills``
population. The screen refuses claims that the audit cannot establish, rather
than substituting fixture cards or inferred task families.

Run: PYTHONPATH=src python scripts/cross_card_audit.py > docs/findings/cross-card-audit-screen.md
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from skill_harness.preflight import ArtifactAuditReport, audit_skill_artifact

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILL_GLOB = "skills/*/*/SKILL.md"


def _find_skill_files() -> list[Path]:
    """Return exactly the published-card population declared by #652."""
    result = subprocess.run(  # noqa: S603
        ["git", "ls-files", _SKILL_GLOB],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "git ls-files failed"
        raise RuntimeError(f"Cannot establish the published-card population: {message}")
    return [_REPO_ROOT / p for p in result.stdout.splitlines()]


def _run_skill_audit(path: Path) -> None:
    """Run the public audit command before rendering its structured report."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "skill_harness", "skill", "audit", str(path)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "skill audit failed"
        raise RuntimeError(f"skill audit failed for {path.relative_to(_REPO_ROOT)}: {message}")


def _unmeasured_claims() -> str:
    """Name the audit boundary instead of inferring a card's claims."""
    return "UNMEASURED - skill audit does not extract a card's claims"


def _claim_class(report: ArtifactAuditReport) -> str:
    """Refuse classification because the audit exposes axes, not card claims."""
    del report
    return _unmeasured_claims()


def _hazard_task_family_assessment() -> str:
    """Refuse an assessment without a card-to-task-family evidence register."""
    return "UNMEASURED - no card-to-task-family evidence register"


def _out_of_reach_reason(report: ArtifactAuditReport) -> str:
    """Name the audit limits that prevent a confirmation-spend comparison."""
    limits = [
        "claim class is UNMEASURED because skill audit does not extract claims",
        "hazard task family is UNMEASURED because no evidence register exists",
    ]
    if report.standing_cost_raw is None:
        limits.append("standing cost is UNMEASURED because frontmatter cannot be parsed")
    return "; ".join(limits)


def main() -> None:
    """Audit all published cards and print the ranked finding document."""
    skill_files = _find_skill_files()

    results: list[dict[str, object]] = []
    for path in sorted(skill_files):
        _run_skill_audit(path)
        report = audit_skill_artifact(path)

        results.append(
            {
                "name": report.name,
                "path": str(path.relative_to(_REPO_ROOT)),
                "standing_cost_raw": report.standing_cost_raw,
                "measurable_claims": _unmeasured_claims(),
                "measurable_axes": ", ".join(report.measurable_axes),
                "claim_class": _claim_class(report),
                "hazard_plausible": _hazard_task_family_assessment(),
                "hazard_exists": _hazard_task_family_assessment(),
                "out_of_reach": _out_of_reach_reason(report),
            }
        )

    # Stable cost order makes the display reproducible without claiming priority.
    def sort_key(r: dict[str, object]) -> tuple[int, int, str]:
        sc = r["standing_cost_raw"]
        if sc is None:
            return (2, 0, str(r["name"]))
        if isinstance(sc, int):
            return (0, sc, str(r["name"]))
        return (1, 0, str(r["name"]))

    results.sort(key=sort_key)

    # Emit the markdown finding document
    print("# Cross-card audit screen - Stage 0 comparative baseline (#652)")
    print()
    print("> **Status:** STAGE-0 COMPLETE 2026-09-23. The declared population is")
    print(f'> `git ls-files "{_SKILL_GLOB}"`: {len(results)} published card(s).')
    print()
    print("**Claims:** This document records the published-card population and runs the")
    print("public `skill-harness skill audit` command on each member. The table reports")
    print("standing cost and the Tier-1 axes available to the instrument. Rank is a")
    print("reproducible cost order, not a confirmation-spend recommendation.")
    print()
    print("**Refuses to claim:** A claim class, because skill audit does not extract a")
    print("card's claims; hazard-qualified task-family plausibility or existence, because")
    print("the repository supplies no card-to-task-family evidence register; a keep/cut")
    print("verdict; or any card's readiness for Stage 1 spend.")
    print()
    print("## Ranked table")
    print()
    print(
        "| Rank | Card | Path | Standing (raw) | Measurable claims | Available Tier-1 axes"
        " | Claim class | Hazard family plausible? | Hazard family exists?"
        " | Out of reach, because |"
    )
    print("| ---: | --- | --- | ---: | --- | --- | --- | --- | --- | --- |")

    for i, r in enumerate(results, 1):
        sc_raw = r["standing_cost_raw"] if r["standing_cost_raw"] is not None else "—"
        print(
            f"| {i} "
            f"| {r['name']} "
            f"| `{r['path']}` "
            f"| {sc_raw} "
            f"| {r['measurable_claims']} "
            f"| {r['measurable_axes']} "
            f"| {r['claim_class']} "
            f"| {r['hazard_plausible']} "
            f"| {r['hazard_exists']} "
            f"| {r['out_of_reach']} |"
        )

    print()
    if not results:
        print(f'No published cards matched `git ls-files "{_SKILL_GLOB}"`.')
        print("No card can be ranked for confirmation spend from this repository state.")
        print()

    print("## Method")
    print()
    print(f'1. Enumerated the declared population via `git ls-files "{_SKILL_GLOB}"`.')
    print("   The screen refuses to substitute fixtures or screen copies when that set is empty.")
    print("2. Ran `python -m skill_harness skill audit <card>` on each member, then used")
    print("   its `audit_skill_artifact()` report to render the table (offline, zero cost).")
    print("3. Reported Tier-1 axis availability, but refused measurable claims and a claim")
    print("   class because the audit does not parse claims from a card.")
    print("4. Refused the hazard-family questions because no evidence register maps cards to")
    print("   task families.")
    print("5. Sorted readable standing costs ascending only for stable display order.")


if __name__ == "__main__":
    main()
