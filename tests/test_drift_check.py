"""Drift-check script seam tests (#53; contract list ratified on #43).

Seam (ratified in spec #49 testing decision 4): run the script against a tree ->
full contract listing. Everything here exercises the subprocess CLI surface —
printed output + exit code — never script internals, mirroring how CI consumes
it. Synthetic trees (copies of the real surfaces under tmp_path, then mutated)
prove the failure lanes without touching the repo.

Pinned AC behaviors (#53): green-prints-everything, coverage-boundary line,
PLANNED-row rendering, all-failures-listed (never first-fail), empty-allowlist
printing.

This file carries the banned decision term as test data by necessity and is
structurally exempt from both scanners (the E1b definition-site pattern used by
tests/test_semantics.py — NOT an allowlist entry; the allowlist stays empty).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "drift_check.py"

_LIVE_IDS = (
    "DC-1",
    "DC-2",
    "DC-3",
    "DC-4",
    "DC-5",
    "DC-6",
    "DC-7",
    "DC-8",
    "DC-9",
    "DC-10",
    "DC-11",
    "DC-12",
    "DC-14",
    "DC-15",
    "AC-1",
)
_PLANNED_IDS = ("DC-13",)

# Every file a live row reads; copied verbatim into synthetic trees so each
# failure test starts from a tree that is green by construction. The whole oc
# package is copied because DC-8, DC-9 and DC-11 scan every .py under it
# (DC-9 scans all of src/skill_harness/, which in the synthetic tree is
# exactly these copies).
_LIVE_SURFACES = (
    "src/skill_harness/aggregation/fit.py",
    "src/skill_harness/aggregation/status.py",
    "src/skill_harness/aggregation/confidence_sequence.py",
    "src/skill_harness/aggregation/report.py",
    "src/skill_harness/ablation/stopping.py",
    "src/skill_harness/semantics.py",
    "src/skill_harness/cli/main.py",
    "src/skill_harness/oc/__init__.py",
    "src/skill_harness/oc/conventions.py",
    "src/skill_harness/oc/crosschecks.py",
    "src/skill_harness/oc/exact.py",
    "src/skill_harness/oc/frontier.py",
    "src/skill_harness/oc/gate1.py",
    "src/skill_harness/oc/gate2.py",
    "src/skill_harness/oracles/calibration/cost_projection.py",
    "src/skill_harness/ratification.py",
    "docs/sers/sers.schema.json",
    "docs/sers/README.md",
    "docs/INVARIANTS.md",
    "docs/PLAN.md",
    "docs/PRD.md",
    "docs/assurance/calibration-report.md",
    "docs/ratifications/README.md",
    "README.md",
)


def _run(root: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(_SCRIPT)]
    if root is not None:
        cmd += ["--root", str(root)]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO_ROOT),
        check=False,
    )


def _make_tree(tmp_path: Path) -> Path:
    root = tmp_path / "tree"
    for rel in _LIVE_SURFACES:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_REPO_ROOT / rel, dst)
    return root


def _mutate(root: Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, f"mutation anchor {old!r} not found in {rel}"
    path.write_text(text.replace(old, new), encoding="utf-8")


# ---------------------------------------------------------------------------
# Green lane — the real tree passes and prints the full F7 report
# ---------------------------------------------------------------------------


def test_real_tree_is_green_and_exits_zero() -> None:
    r = _run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DRIFT CHECK: PASS" in r.stdout


def test_green_prints_every_live_contract() -> None:
    """#43 F7: a green run prints every covered contract ID + one-line summary."""
    r = _run()
    ok_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("OK")]
    for dc_id in _LIVE_IDS:
        assert any(f"{dc_id} " in line for line in ok_lines), (
            f"{dc_id} missing from OK listing:\n{r.stdout}"
        )


def test_green_prints_coverage_boundary_line() -> None:
    r = _run()
    assert (
        "Coverage boundary: coverage is EXACTLY the list above; "
        "no other doc claim is checked." in r.stdout
    )


def test_green_prints_planned_rows() -> None:
    """DC-13 is registered-but-inactive and must render as PLANNED
    (DC-7/DC-8 went live with #54; DC-11 with #55; DC-9/DC-10 with #56;
    DC-12 with #57)."""
    r = _run()
    planned_lines = [line for line in r.stdout.splitlines() if "PLANNED" in line]
    for dc_id in _PLANNED_IDS:
        assert any(f"{dc_id} " in line for line in planned_lines), (
            f"{dc_id} missing from PLANNED listing:\n{r.stdout}"
        )


def test_planned_dc13_names_the_owed_activation() -> None:
    """DC-13's surface (docs/observations/) landed in PR #60 before this script
    existed, so the #43 same-PR activation rule could not fire; the PLANNED line
    must say activation is owed rather than implying the surface is unlanded."""
    r = _run()
    dc13 = [line for line in r.stdout.splitlines() if "DC-13" in line]
    assert dc13 and "owed" in dc13[0], r.stdout


def test_green_prints_allowlist_even_when_empty() -> None:
    r = _run()
    allow = [line for line in r.stdout.splitlines() if "allowlist" in line.lower()]
    assert allow and "EMPTY" in allow[0], r.stdout


def test_green_prints_structural_exemptions() -> None:
    """F7 visibility: the E1b structural carve-outs are printed too, so the
    EMPTY allowlist line can never overstate the ban's true coverage — the
    union across ALL live token bans, including DC-11's definition site."""
    r = _run()
    exempt_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("EXEMPT")]
    for rel in (
        "src/skill_harness/semantics.py",
        "tests/test_semantics.py",
        "scripts/drift_check.py",
        "tests/test_drift_check.py",
        "src/skill_harness/oc/crosschecks.py",
    ):
        assert any(rel in line for line in exempt_lines), r.stdout


# ---------------------------------------------------------------------------
# Failure lanes — synthetic trees; failures are ALL listed, never first-fail
# ---------------------------------------------------------------------------


def test_synthetic_tree_is_green_by_construction(tmp_path: Path) -> None:
    r = _run(_make_tree(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr


def test_two_independent_drifts_are_both_listed(tmp_path: Path) -> None:
    """All-failures-listed: a DC-1 constant drift AND a DC-5 sentence mutation
    in one tree must both appear in one run's output, exit 1."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/ablation/stopping.py",
        "WIN_RATE_THRESHOLD: Final[float] = 0.60",
        "WIN_RATE_THRESHOLD: Final[float] = 0.61",
    )
    _mutate(
        root,
        "README.md",
        "returns a pass rate below 1",
        "returns a pass rate below 2",
    )
    r = _run(root)
    assert r.returncode == 1
    assert "DRIFT CHECK: BLOCKED" in r.stdout
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-1" in line for line in fail_lines), r.stdout
    assert any("DC-5" in line for line in fail_lines), r.stdout


def test_banned_token_anywhere_blocks_with_location(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    (root / "docs" / "note.md").write_text("analysis was per-protocol here\n", encoding="utf-8")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-3" in line and "note.md" in line for line in fail_lines), r.stdout


def test_registry_definition_site_stays_exempt_structurally(tmp_path: Path) -> None:
    """semantics.py + the scan machinery carry the token by necessity; the
    exemption is structural (E1b), not an allowlist entry — so a green run on a
    tree containing them still prints the allowlist as EMPTY."""
    r = _run(_make_tree(tmp_path))
    assert r.returncode == 0
    allow = [line for line in r.stdout.splitlines() if "allowlist" in line.lower()]
    assert allow and "EMPTY" in allow[0]


def test_invented_third_estimand_blocks(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/semantics.py",
        '    TREATMENT_POLICY = "treatment-policy"',
        '    TREATMENT_POLICY = "treatment-policy"\n    INVENTED_THIRD = "invented-third"',
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-4" in line for line in fail_lines), r.stdout


def test_unregistered_estimand_token_in_docs_blocks(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    (root / "docs" / "obs.md").write_text("estimand: as-treated\n", encoding="utf-8")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-4" in line and "obs.md" in line for line in fail_lines), r.stdout


def test_schedule_drift_blocks(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/aggregation/status.py",
        "N_MIN: int = 8",
        "N_MIN: int = 6",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-2" in line for line in fail_lines), r.stdout


def test_missing_enforcement_pointer_blocks(tmp_path: Path) -> None:
    """DC-6 pointer-liveness: INVARIANTS points at cli/main.py; a tree where
    that file is gone must block."""
    root = _make_tree(tmp_path)
    (root / "src/skill_harness/cli/main.py").unlink()
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-6" in line and "main.py" in line for line in fail_lines), r.stdout


def test_spend_gating_sentence_mutation_blocks(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "README.md",
        "dry-run by default",
        "dry-run by preference",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-6" in line for line in fail_lines), r.stdout


def test_grid_constant_drift_blocks(tmp_path: Path) -> None:
    """DC-7 (activated by the oc-landing PR per the #43 same-PR rule): moving
    a grid constant off the #40-ratified value must block."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/oc/conventions.py",
        "GRID_N_MAX: Final[int] = 40",
        "GRID_N_MAX: Final[int] = 39",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-7" in line for line in fail_lines), r.stdout


def test_grid_provenance_comment_drift_blocks(tmp_path: Path) -> None:
    """DC-7: the #40-provenance comment at the definition site is part of the
    contract - rewording it away must block."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/oc/conventions.py",
        "Provenance: ratified decision #40",
        "Provenance: team preference",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-7" in line and "conventions.py" in line for line in fail_lines), r.stdout


def test_grid_doc_quote_drift_blocks(tmp_path: Path) -> None:
    """DC-7: the locked INVARIANTS grid quote drifting must block."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "docs/INVARIANTS.md",
        "`GRID_N_MIN = 6` / `GRID_N_MAX = 40`",
        "`GRID_N_MIN = 8` / `GRID_N_MAX = 40`",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-7" in line and "INVARIANTS" in line for line in fail_lines), r.stdout


def test_forbidden_import_inside_oc_blocks(tmp_path: Path) -> None:
    """DC-8: any import of ablation/subject/stopping inside oc/ must block,
    naming the file and line."""
    root = _make_tree(tmp_path)
    (root / "src/skill_harness/oc/helper.py").write_text(
        "from skill_harness.ablation.stopping import N_MAX\n", encoding="utf-8"
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-8" in line and "helper.py" in line for line in fail_lines), r.stdout


def test_empty_oc_package_blocks_import_ban(tmp_path: Path) -> None:
    """DC-8: a tree where the oc package is gone must block - a ban with no
    surface to guard is drift, not a pass."""
    root = _make_tree(tmp_path)
    for rel in (
        "src/skill_harness/oc/__init__.py",
        "src/skill_harness/oc/conventions.py",
        "src/skill_harness/oc/crosschecks.py",
        "src/skill_harness/oc/exact.py",
        "src/skill_harness/oc/frontier.py",
        "src/skill_harness/oc/gate1.py",
        "src/skill_harness/oc/gate2.py",
    ):
        (root / rel).unlink()
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-8" in line for line in fail_lines), r.stdout


def test_banned_method_identifier_in_oc_blocks(tmp_path: Path) -> None:
    """DC-11 (activated by the Gate-2 PR per the #43 same-PR rule): a Wald
    implementation appearing anywhere in oc/ must block with the location."""
    root = _make_tree(tmp_path)
    (root / "src/skill_harness/oc/intervals.py").write_text(
        "def wald_interval(x: int, n: int) -> tuple[float, float]:\n    ...\n",
        encoding="utf-8",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-11" in line and "intervals.py" in line for line in fail_lines), r.stdout


def test_exact_conditional_token_in_oc_blocks(tmp_path: Path) -> None:
    """DC-11: both the prose form and the identifier form of the banned exact
    conditional test are caught inside oc/."""
    root = _make_tree(tmp_path)
    (root / "src/skill_harness/oc/extra.py").write_text(
        "USE_EXACT_CONDITIONAL = True  # switch to the exact conditional test\n",
        encoding="utf-8",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-11" in line and "extra.py" in line for line in fail_lines), r.stdout


def test_banned_method_token_outside_oc_does_not_fire_dc11(tmp_path: Path) -> None:
    """DC-11's registered scope is oc/ exactly — the same token at repo level
    or in docs/ must NOT fire this row (scan_repo_level off)."""
    root = _make_tree(tmp_path)
    (root / "docs" / "method-note.md").write_text(
        "Newcombe beats the Wald interval at small n.\n", encoding="utf-8"
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_crosschecks_definition_site_stays_exempt(tmp_path: Path) -> None:
    """crosschecks.py names the banned methods and quotes FLL 2013 verbatim by
    necessity (E1b definition site) — the synthetic tree containing it is
    green, and the exemption is printed rather than silent."""
    r = _run(_make_tree(tmp_path))
    assert r.returncode == 0
    assert "src/skill_harness/oc/crosschecks.py" in r.stdout


def test_hardcoded_pair_dollar_constant_blocks(tmp_path: Path) -> None:
    """DC-9 (activated by the frontier PR per the #43 same-PR rule): any
    reappearance of the prototype's hard-coded per-pair dollar constant
    inside src/skill_harness/ must block with the location (#40(c): costs
    live from PRICE_PER_MTOK)."""
    root = _make_tree(tmp_path)
    (root / "src/skill_harness/tuning.py").write_text(
        "PAIR_COST = 0.77  # measured v0.2 snapshot\n", encoding="utf-8"
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-9" in line and "tuning.py" in line for line in fail_lines), r.stdout


def test_pair_dollar_token_outside_src_does_not_fire_dc9(tmp_path: Path) -> None:
    """DC-9's registered scope is src/skill_harness/ exactly — the token in
    docs/ (e.g. quoting the prototype's history) must NOT fire this row."""
    root = _make_tree(tmp_path)
    (root / "docs" / "history.md").write_text(
        "The prototype hard-coded PAIR_COST = 0.77 as a v0.2 snapshot.\n",
        encoding="utf-8",
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_evaluation_cap_drift_blocks(tmp_path: Path) -> None:
    """DC-10 (activated by the frontier PR): moving the $35 per-evaluation
    cap off the #40-ratified value must block."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/oracles/calibration/cost_projection.py",
        "EVALUATION_HARD_CAP_USD: float = 35.0",
        "EVALUATION_HARD_CAP_USD: float = 30.0",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-10" in line and "cost_projection.py" in line for line in fail_lines), r.stdout


def test_daily_ceiling_drift_blocks(tmp_path: Path) -> None:
    """DC-10: the $100 daily calibration ceiling is pinned by the same row."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/oracles/calibration/cost_projection.py",
        "DAILY_CAP_HARD_CEILING_USD: float = 100.0",
        "DAILY_CAP_HARD_CEILING_USD: float = 150.0",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-10" in line for line in fail_lines), r.stdout


def test_budget_doc_quote_drift_blocks(tmp_path: Path) -> None:
    """DC-10: the locked INVARIANTS budget quote drifting must block."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "docs/INVARIANTS.md",
        "$35 per skill-task evaluation",
        "$40 per skill-task evaluation",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-10" in line and "INVARIANTS" in line for line in fail_lines), r.stdout


def test_missing_value_site_pattern_blocks(tmp_path: Path) -> None:
    """A renamed constant is drift too: the site pattern failing to match at
    all must block, not silently pass."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/aggregation/fit.py",
        "WIN_RATE_THRESHOLD: float = 0.60",
        "WIN_THRESHOLD_RATE: float = 0.60",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-1" in line for line in fail_lines), r.stdout


# ---------------------------------------------------------------------------
# DC-12: ratification-ledger internal consistency (#47; activated by #57)
# ---------------------------------------------------------------------------

_RAT_RECORD = """---
rat: RAT-0001
status: RATIFIED
skill_id: skill-abc
task_family: example-family
estimand: treatment-policy
gate: gate2
n: 20
worst_case_cost_usd: {worst}
hard_cap_usd: {cap}
cost_provenance: project_pair_usd
sme_status: {sme}
ratified_date: "2026-08-02"
---

# RAT-0001 - example row-pick (drift-lane fixture)
{body}
"""


def _write_rat_record(
    root: Path,
    *,
    worst: str = "15.55",
    cap: str = "15.55",
    sme: str = "deliberated",
    body: str = "",
) -> None:
    path = root / "docs" / "ratifications" / "RAT-0001-skill-abc.md"
    path.write_text(_RAT_RECORD.format(worst=worst, cap=cap, sme=sme, body=body), encoding="utf-8")


def test_rat_ledger_zero_records_is_green(tmp_path: Path) -> None:
    """DC-12 is zero-tolerant by design: records land later via docs-only
    operator row-picks; an empty ledger with the README present is green."""
    r = _run(_make_tree(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    ok_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("OK")]
    assert any("DC-12" in line for line in ok_lines), r.stdout


def test_rat_ledger_missing_dir_blocks(tmp_path: Path) -> None:
    """The registered surface itself going missing is drift (DC-8 empty-package
    precedent), even with zero records."""
    import shutil as _shutil

    root = _make_tree(tmp_path)
    _shutil.rmtree(root / "docs" / "ratifications")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-12" in line for line in fail_lines), r.stdout


def test_rat_valid_record_is_green(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _write_rat_record(root)
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_rat_cap_above_ceiling_blocks(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _write_rat_record(root, worst="35.01", cap="35.01")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-12" in line and "RAT-0001" in line for line in fail_lines), r.stdout


def test_rat_cap_below_worst_case_blocks(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _write_rat_record(root, worst="15.56", cap="15.55")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-12" in line for line in fail_lines), r.stdout


def test_rat_self_certified_without_disclosure_blocks(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _write_rat_record(root, sme="self-certified")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-12" in line and "disclosure" in line for line in fail_lines), r.stdout


def test_rat_self_certified_with_disclosure_is_green(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _write_rat_record(
        root,
        sme="self-certified",
        body="This record is internally derived, not externally deliberated.",
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_rat_unparseable_record_blocks(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    path = root / "docs" / "ratifications" / "RAT-0002-broken.md"
    path.write_text("# no front-matter at all\n", encoding="utf-8")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-12" in line and "RAT-0002" in line for line in fail_lines), r.stdout


# ---------------------------------------------------------------------------
# DC-15: cache-aware record consistency (#436)
# ---------------------------------------------------------------------------

_CACHE_AWARE_RAT_RECORD = """---
rat: RAT-0001
status: RATIFIED
skill_id: skill-abc
task_family: example-family
estimand: treatment-policy
gate: gate2
n: 20
worst_case_cost_usd: {worst}
hard_cap_usd: {cap}
cost_provenance: project_pair_usd
sme_status: {sme}
ratified_date: "2026-08-02"
cache_aware_cost_usd: {cache_aware}
cache_read_share: {share}
---

# RAT-0001 - cache-aware record (DC-15 fixture)
{body}
"""


def _write_cache_aware_rat_record(
    root: Path,
    *,
    worst: str = "15.55",
    cap: str = "15.55",
    sme: str = "deliberated",
    cache_aware: str = "4.93",
    share: str = "0.85",
    body: str = "",
) -> None:
    path = root / "docs" / "ratifications" / "RAT-0001-skill-abc.md"
    path.write_text(
        _CACHE_AWARE_RAT_RECORD.format(
            worst=worst, cap=cap, sme=sme, cache_aware=cache_aware, share=share, body=body
        ),
        encoding="utf-8",
    )


def test_dc15_valid_cache_aware_record_is_green(tmp_path: Path) -> None:
    """A RAT record quoting a cache-aware figure alongside worst case and
    declared share is green — all three fields present and reconcilable."""
    root = _make_tree(tmp_path)
    _write_cache_aware_rat_record(root)
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dc15_cache_aware_without_worst_case_blocks(tmp_path: Path) -> None:
    """A record quoting cache_aware_cost_usd without worst_case_cost_usd
    must block — the worst case is the cap-tested figure."""
    root = _make_tree(tmp_path)
    path = root / "docs" / "ratifications" / "RAT-0001-skill-abc.md"
    path.write_text(
        "---\n"
        "rat: RAT-0001\n"
        "status: RATIFIED\n"
        "skill_id: skill-abc\n"
        "task_family: example-family\n"
        "estimand: treatment-policy\n"
        "gate: gate2\n"
        "n: 20\n"
        "hard_cap_usd: 15.55\n"
        "cost_provenance: project_pair_usd\n"
        "sme_status: deliberated\n"
        'ratified_date: "2026-08-02"\n'
        "cache_aware_cost_usd: 4.93\n"
        "cache_read_share: 0.85\n"
        "---\n\n"
        "# RAT-0001 - missing worst_case_cost_usd\n",
        encoding="utf-8",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-15" in line and "worst_case_cost_usd" in line for line in fail_lines), r.stdout


def test_dc15_cache_aware_without_share_blocks(tmp_path: Path) -> None:
    """A record quoting cache_aware_cost_usd without cache_read_share
    must block — the share is the registered assumption the projector
    needs."""
    root = _make_tree(tmp_path)
    path = root / "docs" / "ratifications" / "RAT-0001-skill-abc.md"
    path.write_text(
        "---\n"
        "rat: RAT-0001\n"
        "status: RATIFIED\n"
        "skill_id: skill-abc\n"
        "task_family: example-family\n"
        "estimand: treatment-policy\n"
        "gate: gate2\n"
        "n: 20\n"
        "worst_case_cost_usd: 15.55\n"
        "hard_cap_usd: 15.55\n"
        "cost_provenance: project_pair_usd\n"
        "sme_status: deliberated\n"
        'ratified_date: "2026-08-02"\n'
        "cache_aware_cost_usd: 4.93\n"
        "---\n\n"
        "# RAT-0001 - missing cache_read_share\n",
        encoding="utf-8",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-15" in line and "cache_read_share" in line for line in fail_lines), r.stdout


def test_dc15_cache_aware_exceeding_worst_case_blocks(tmp_path: Path) -> None:
    """A cache-aware figure must not exceed the worst case — caching
    reduces cost, so cache_aware <= worst_case."""
    root = _make_tree(tmp_path)
    _write_cache_aware_rat_record(root, worst="4.92", cache_aware="4.93")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-15" in line and "exceeds" in line for line in fail_lines), r.stdout


def test_dc15_no_cache_aware_fields_is_green(tmp_path: Path) -> None:
    """A record without cache_aware_cost_usd is not subject to DC-15 —
    the row only fires when the cache-aware figure is quoted."""
    root = _make_tree(tmp_path)
    _write_rat_record(root)
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dc15_printed_in_green_listing(tmp_path: Path) -> None:
    """DC-15 must appear in the OK listing on a green run."""
    r = _run()
    assert r.returncode == 0
    ok_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("OK")]
    assert any("DC-15" in line for line in ok_lines), r.stdout


def test_dc15_share_out_of_range_blocks(tmp_path: Path) -> None:
    """A cache_read_share outside [0.0, 1.0] must block — the share is the
    registered assumption and must be a fraction."""
    root = _make_tree(tmp_path)
    _write_cache_aware_rat_record(root, share="1.5")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-15" in line and "cache_read_share" in line for line in fail_lines), r.stdout


def test_dc15_unreadable_share_blocks(tmp_path: Path) -> None:
    """A non-numeric cache_read_share must block the same way unreadable
    cost fields do."""
    root = _make_tree(tmp_path)
    _write_cache_aware_rat_record(root, share="not-a-fraction")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-15" in line and "unreadable" in line for line in fail_lines), r.stdout


# ---------------------------------------------------------------------------
# AC-1: calibrated-interval primacy (#160 close-out candidate, ratified in
# docs/ASSURANCE.md; activated by #248)
# ---------------------------------------------------------------------------


def test_ac1_method_replacement_blocks(tmp_path: Path) -> None:
    """AC-1 replacement leg: swapping the production confidence-sequence method
    id for anything else must block, naming the definition site."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/aggregation/confidence_sequence.py",
        'INTERVAL_METHOD_V1: str = "predictable_plugin_betting_cs_v1"',
        'INTERVAL_METHOD_V1: str = "legacy_posterior_v1"',
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("AC-1" in line and "confidence_sequence.py" in line for line in fail_lines), r.stdout


def test_ac1_public_report_demotion_blocks(tmp_path: Path) -> None:
    """AC-1 demotion leg: the rendered per-clause report leads with the
    anytime-valid CS column (#187). Moving the legacy posterior CrI column in
    front of it demotes the calibrated interval on the surface a reader sees,
    so the row must block."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/cli/main.py",
        '    clause_table.add_column("CS 95% (anytime-valid)", min_width=18, justify="right")\n'
        '    clause_table.add_column("posterior CrI 95%", min_width=16, justify="right")',
        '    clause_table.add_column("posterior CrI 95%", min_width=16, justify="right")\n'
        '    clause_table.add_column("CS 95% (anytime-valid)", min_width=18, justify="right")',
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("AC-1" in line and "main.py" in line for line in fail_lines), r.stdout


def test_ac1_cs_column_rename_blocks(tmp_path: Path) -> None:
    """AC-1 demotion leg: renaming the CS column so it no longer announces the
    anytime-valid interval is drift too — the reader loses the same claim the
    column order carries."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/cli/main.py",
        '"CS 95% (anytime-valid)"',
        '"CI 95%"',
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("AC-1" in line and "main.py" in line for line in fail_lines), r.stdout


def test_ac1_schema_preference_reversal_blocks(tmp_path: Path) -> None:
    """AC-1 schema leg: the report schema states which interval is preferred and
    which is compatibility-only. Reversing that statement must block."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/aggregation/report.py",
        "Retained for compatibility; prefer sequential_confidence_sequence_95",
        "Preferred interval; sequential_confidence_sequence_95 is supplementary",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("AC-1" in line and "report.py" in line for line in fail_lines), r.stdout


def test_ac1_published_method_id_removal_blocks(tmp_path: Path) -> None:
    """AC-1 publication leg: the calibration report names the production method
    id. Losing that quote must block — an unpublished method is unauditable."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "docs/assurance/calibration-report.md",
        "predictable_plugin_betting_cs_v1",
        "some_other_cs",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("AC-1" in line and "calibration-report.md" in line for line in fail_lines), r.stdout


def test_ac1_does_not_fire_on_promoting_the_cs_in_the_json_dict(tmp_path: Path) -> None:
    """AC-1 must never punish compliance. The JSON wire order is alphabetical
    (to_json_bytes uses sort_keys=True), so the key order inside
    _clause_to_dict carries no claim; reordering those two keys is not drift and
    must stay green."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "src/skill_harness/aggregation/report.py",
        '"posterior_credible_interval_95": list(clause.posterior_credible_interval_95),\n'
        '        "sequential_confidence_sequence_95": list(seq) if seq is not None else None,',
        '"sequential_confidence_sequence_95": list(seq) if seq is not None else None,\n'
        '        "posterior_credible_interval_95": list(clause.posterior_credible_interval_95),',
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr
