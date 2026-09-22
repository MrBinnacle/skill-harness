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

import hashlib
import json
import os
import re
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
    "DC-16",
    "DC-17",
    "DC-18",
    "DC-19",
    "AC-1",
    "AC-2",
    "AC-3",
    "AC-4",
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
    "docs/ratifications/MIRROR-0001-on-irreducibility.md",
    "README.md",
    # DC-5's second registered site since 2026-09-13: the empirical record moved
    # off the front page under the S447 ruling and the registration followed it.
    "docs/what-the-instrument-has-found.md",
    # DC-16 reads the vendored word list; without it every synthetic tree
    # would fail on a missing manifest instead of the lane under test.
    "assets/words_to_avoid.json",
    # DC-19 reads the asset-pairs manifest; without it every synthetic tree
    # would fail on a missing manifest instead of the lane under test.
    "assets/asset-pairs.json",
    # DC-19 checks the sha256 of these pairs; without them every synthetic
    # tree would fail on a missing file instead of the lane under test.
    "assets/social-preview.svg",
    "assets/social-preview.png",
    # AC-2 reads the two assurance harnesses that RESTATE the schedule and the
    # pass-probability threshold (#545). The third harness named in that ticket,
    # tests/test_aggregation_cs_calibration.py, imports every constant it uses
    # and states no literal of its own, so the row has nothing to read there and
    # the synthetic tree does not need it.
    "tests/test_aggregation_aa.py",
    "tests/test_aggregation_calibration.py",
    # AC-3's two ValueSite legs read the calibration registry by FIELD (#543).
    # The row does not prose-scan docs/calibration/*.json; without this copy
    # every synthetic tree would fail on a missing value site instead of the
    # lane under test.
    "docs/calibration/vacuity-flag-calibration-2026-08-08.json",
    # AC-3's `requires` also covers pyproject.toml and the sitegen templates
    # (#565), two of the five surfaces the row's own summary names. Without
    # these two copies every synthetic tree would refuse on a missing surface
    # instead of the lane under test. One template file is enough to make the
    # sitegen directory exist; the predicate itself globs the rest.
    "pyproject.toml",
    "src/skill_harness/sitegen/templates/schema_vocabulary.html",
    # DC-18 reads the Vale version from ci.yml's curl URLs and the test file's
    # docstring. Without this copy every synthetic tree would fail on a missing
    # value site instead of the lane under test.
    "tests/test_vale_doctrine_agreement.py",
)

# AC-4 reads a DIRECTORY rather than a named file: its three delegates glob
# every workflow GitHub would run, both suffixes (#544). _LIVE_SURFACES copies
# named paths, so without this the row would refuse on a missing surface in
# every lane below instead of reporting the lane under test. That refusal is
# the vacuity control working; copying the directory is how a synthetic tree
# gets a workflow set to be green about.
_LIVE_SURFACE_DIRS = (".github/workflows",)


def _run(
    root: Path | None = None,
    *,
    ticket_states: dict[str, str] | None = None,
    script: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the drift check as a subprocess.

    ``ticket_states`` fills DC-17's injected seam, so a control that asserts
    what a closed ticket does makes no network call. A control that reaches
    api.github.com proves the network worked; it does not prove the rule.

    ``script`` runs a COPY of the drift check from somewhere else, which is how
    the AC-3 dead-row lane reaches a guard module it has renamed:
    _load_guard_module resolves the guard against the script's own parent
    directory, so relocating the script relocates its guard lookup.

    The DEFAULT holds every ticket open. DC-17 now fails closed on a ticket
    state it cannot read, and the fixture tree carries a live ``UNLANDED
    #514`` row, so without this default every drift-check test in this file,
    including the ones about token bans and estimand vocabulary, would go red
    whenever api.github.com was unreachable. The live lookup has its own
    tests; it is not every other test's dependency.
    """
    cmd = [sys.executable, str(_SCRIPT if script is None else script)]
    if root is not None:
        cmd += ["--root", str(root)]
    states = {"*": "open"} if ticket_states is None else ticket_states
    env = {**os.environ, "SKILL_HARNESS_TICKET_STATES": json.dumps(states)}
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO_ROOT),
        check=False,
        env=env,
    )


def _git(root: Path, *args: str) -> None:
    """Run one git command in the synthetic tree, failing loudly.

    ``core.excludesFile`` is pointed at an empty file so a developer's global
    ignore rules cannot change which fixture files land in the index: the
    tracked set is the thing under test in every DC-16 case below, and a
    fixture whose contents depend on the machine running it measures nothing."""
    empty_excludes = root.parent / "empty-global-excludes"
    empty_excludes.touch()
    subprocess.run(
        ["git", "-c", f"core.excludesFile={empty_excludes}", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )


def _make_tree(tmp_path: Path) -> Path:
    """A synthetic tree that is a real git repository with every live surface
    TRACKED.

    DC-16 selects the files it scans with ``git ls-files`` (#471), so a
    synthetic tree with no index is a tree DC-16 refuses to scan rather than a
    tree it finds clean. The fixture stages the surfaces; it does not commit
    them, because ``git ls-files`` reads the index and a commit would add a
    required identity the fixture has no reason to invent."""
    root = tmp_path / "tree"
    for rel in _LIVE_SURFACES:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_REPO_ROOT / rel, dst)
    for rel in _LIVE_SURFACE_DIRS:
        shutil.copytree(_REPO_ROOT / rel, root / rel)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    return root


def _write_tracked(root: Path, rel: str, text: str) -> None:
    """Write a file into the synthetic tree and stage it, so DC-16's tracked-set
    selection reaches it."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "--", rel)


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
    # AC-1 reads the report-column order from cli/main.py, so it reddens too (#574).
    assert _failed_row_ids(r.stdout) == {"AC-1", "DC-6"}, r.stdout


def test_spend_gating_sentence_mutation_blocks(tmp_path: Path) -> None:
    """#469: the registered sentence is now the scoped claim, not the blanket one.

    The wording this mutates changed because the old registered sentence was
    false for two of the three `run` subcommands, and registering it made DC-6
    hold the false version in place.
    """
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "README.md",
        "are the subcommands that spend",
        "are the subcommand that spends",
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
    # DC-7 pins the grid constants in oc/conventions.py, so it reddens too (#574).
    assert _failed_row_ids(r.stdout) == {"DC-7", "DC-8"}, r.stdout


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
    # docs/ratifications is also DC-17's registered surface (#574).
    assert _failed_row_ids(r.stdout) == {"DC-12", "DC-17"}, r.stdout


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
    # DC-12 reads worst_case_cost_usd for its cap check, so it reddens too (#574).
    assert _failed_row_ids(r.stdout) == {"DC-12", "DC-15"}, r.stdout


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


def test_dc15_printed_in_green_listing() -> None:
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


# ---------------------------------------------------------------------------
# AC-2: assurance-harness schedule agreement (#248 candidate, ratified in
# docs/ASSURANCE.md; activated by #545)
#
# This row guards the HARNESS side only. DC-1 and DC-2 already pin the
# production constants in src/skill_harness/ablation/stopping.py, so every
# demonstration below mutates a HARNESS site and asserts that AC-2 is the row
# that names it. Mutating production instead would turn DC-1 or DC-2 red and
# prove nothing about this row.
# ---------------------------------------------------------------------------


def test_ac2_aa_harness_threshold_drift_blocks(tmp_path: Path) -> None:
    """The A/A harness restates the pass-probability threshold as its own module
    constant. Moving it away from the registered 0.95 must block, naming the
    harness file."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "tests/test_aggregation_aa.py",
        "PROB_THRESHOLD = 0.95",
        "PROB_THRESHOLD = 0.90",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("AC-2" in line and "test_aggregation_aa.py" in line for line in fail_lines), r.stdout


def test_ac2_calibration_harness_threshold_drift_blocks(tmp_path: Path) -> None:
    """The coverage-calibration harness restates the same threshold. It drifts
    independently of the A/A harness, so it is demonstrated independently."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "tests/test_aggregation_calibration.py",
        "PROB_THRESHOLD = 0.95",
        "PROB_THRESHOLD = 0.99",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-2" in line and "test_aggregation_calibration.py" in line for line in fail_lines
    ), r.stdout


def test_ac2_harness_docstring_schedule_drift_blocks(tmp_path: Path) -> None:
    """A production re-tune that leaves the harness prose behind is the drift
    this row exists for. The harness then describes a schedule it does not run,
    and a reader of the test file cannot see the difference.

    The mutation moves only the harness sentence, so the red must come from
    AC-2. DC-2 reads the production module and stays green here, which is what
    makes this demonstration attributable to one row."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "tests/test_aggregation_calibration.py",
        "(``N_MIN=8``, ``N_INC=4``, ``N_MAX=40``)",
        "(``N_MIN=8``, ``N_INC=4``, ``N_MAX=60``)",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-2" in line and "test_aggregation_calibration.py" in line for line in fail_lines
    ), r.stdout
    # The control asserts on the line's ROW ID, not on the token "DC-2"
    # appearing anywhere in it. AC-2's own summary names DC-1 and DC-2 as the
    # production side, so a substring test matches AC-2's own failure line and
    # the control fires on a tree where nothing is wrong.
    assert not any(re.match(r"FAIL\s+DC-2\b", line.strip()) for line in fail_lines), (
        "The harness sentence moved and the production module did not, so DC-2 "
        "must stay green. A red DC-2 here would mean this demonstration is "
        "killed by the wrong row.\n" + r.stdout
    )


def test_ac2_aa_harness_delta_and_threshold_sentence_drift_blocks(tmp_path: Path) -> None:
    """The A/A harness states its registered constants in prose as well as in
    code. The sentence is registered, so moving it alone must block."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "tests/test_aggregation_aa.py",
        "``delta=0.1``, ``prob_threshold=0.95``",
        "``delta=0.1``, ``prob_threshold=0.90``",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("AC-2" in line and "test_aggregation_aa.py" in line for line in fail_lines), r.stdout


def test_ac2_calibration_harness_delta_drift_blocks(tmp_path: Path) -> None:
    """delta is the other two-arm gate constant, and it lives ONLY here.

    two_arm.py:18 records delta and prob_threshold as the caller's
    pre-registered constants and holds no default for either, so each harness
    states its own. There is no production site to compare against and no other
    row reads these files, which makes AC-2 their only guard."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "tests/test_aggregation_calibration.py",
        "DELTA = 0.1",
        "DELTA = 0.2",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-2" in line and "test_aggregation_calibration.py" in line for line in fail_lines
    ), r.stdout


def test_ac2_does_not_fire_on_a_compliant_tree(tmp_path: Path) -> None:
    """A false-positive control, and it is worth saying what it does not do.

    It proves AC-2 stays green on a harness edit that touches no registered
    constant and no registered sentence. It does NOT bind AC-2: deleting the
    row leaves this test passing, because a row that never fires cannot
    over-fire either. The four tests above carry the binding."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        "tests/test_aggregation_aa.py",
        "NOMINAL_ALPHA = 1.0 - PROB_THRESHOLD",
        "NOMINAL_ALPHA = 1.0 - PROB_THRESHOLD  # derived, not registered",
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# AC-3 (#543): the public vacuity-claim row. It delegates to the narrow
# vacuity scanner in tests/test_structural_bans.py, which is the same predicate
# .pre-commit-config.yaml runs. These lanes prove THE ROW reddens: the script
# runs as a subprocess, so no pytest case from that module is in scope, and the
# poison lives in a tmp tree nothing else reads. If the subprocess exits 1 and
# prints a FAIL line whose row id is AC-3, the only code that can have produced
# it is _check_delegated_guard running the delegate.
#
# Every poison APPENDS to README.md rather than replacing it. A replaced README
# loses DC-5's registered sentences, DC-5 reddens too, and the demonstration
# stops naming one row.
# ---------------------------------------------------------------------------

_FAIL_ROW_RE = re.compile(r"^\s*FAIL\s+((?:DC|AC)-\d+)")


def _append_tracked(root: Path, rel: str, extra: str) -> None:
    """Append to an existing surface in the synthetic tree and re-stage it."""
    path = root / rel
    assert path.is_file(), f"{rel} is not in _LIVE_SURFACES"
    path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")
    _git(root, "add", "--", rel)


def _failed_row_ids(stdout: str) -> set[str]:
    """Every row id the run printed a FAIL for.

    Both FAIL shapes main() prints carry the id right after the word: the row
    header line and each indented detail line. Collecting from both means a row
    that failed cannot be missed by reading only one shape.
    """
    ids = set()
    for line in stdout.splitlines():
        match = _FAIL_ROW_RE.match(line)
        if match is not None:
            ids.add(match.group(1))
    return ids


def test_ac3_poison_readme_bare_precision_reddens_ac3_and_only_ac3(tmp_path: Path) -> None:
    """Poison leg 1. A generation-2 kind-precision aggregate with no class split
    beside it, appended to the README, and AC-3 reddens naming the file and the
    line. The reddened SET is asserted, so a lane that went red for some other
    row's reason cannot pass as this one."""
    root = _make_tree(tmp_path)
    _append_tracked(
        root,
        "README.md",
        "\n## Appendix\n\nThe kind-precision aggregate over the corpus is 0.9667.\n",
    )
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-3" in line and "README.md" in line and "bare kind-precision aggregate" in line
        for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-3"}, r.stdout


def test_ac3_poison_readme_bare_recall_reddens_ac3_and_only_ac3(tmp_path: Path) -> None:
    """Poison leg 2. A measured detector-recall figure without the registered
    intervals or the sample and skill denominators. The word 'measured' in the
    context window is what forbids it; UNMEASURED would have been compliant."""
    root = _make_tree(tmp_path)
    _append_tracked(
        root,
        "README.md",
        "\n## Appendix\n\nThe vacuity-flag detector's recall was measured at 0.74.\n",
    )
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-3" in line and "README.md" in line and "recall not stated as UNMEASURED" in line
        for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-3"}, r.stdout


def test_ac3_poison_in_docs_names_the_docs_file_not_the_readme(tmp_path: Path) -> None:
    """Scope control. The row scans the whole public-copy surface set, not the
    README alone, and the failure names the surface that actually carries the
    claim. A row that only ever reported README.md would pass the two lanes
    above while guarding one file."""
    root = _make_tree(tmp_path)
    _write_tracked(
        root,
        "docs/appendix.md",
        "Kind-precision 0.835 held across the run.\n",
    )
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("AC-3" in line and "docs/appendix.md" in line for line in fail_lines), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-3"}, r.stdout


def test_ac3_compliant_readme_appendix_stays_green(tmp_path: Path) -> None:
    """Green control for both legs, mirroring DC-16's. The SAME two figures as
    the poison lanes, written the way the live README writes them: the aggregate
    beside both class splits, the recall named UNMEASURED."""
    root = _make_tree(tmp_path)
    _append_tracked(
        root,
        "README.md",
        "\n## Appendix\n\nKind-precision 0.9667: `not_a_directive` matched 255/255, while\n"
        "`weak_directive` matched 6/15. The vacuity-flag detector's recall is UNMEASURED.\n",
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ac3_vacuity_prose_without_a_figure_does_not_fire(tmp_path: Path) -> None:
    """False-positive control, required by #543. A sentence that names the
    vacuity flag and the detector but states no figure is not a claim, and a
    rule that fired on it would be untrue to its own summary."""
    root = _make_tree(tmp_path)
    _append_tracked(
        root,
        "README.md",
        "\n## Appendix\n\nThe vacuity flag marks clauses the detector could not resolve.\n",
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ac3_registry_kind_precision_split_drift_blocks(tmp_path: Path) -> None:
    """The registry leg. docs/calibration/*.json is not prose-scanned, so the
    two figures it holds are pinned as VALUES instead. Move one class
    denominator and AC-3 reddens naming the file and both readings."""
    root = _make_tree(tmp_path)
    registry = "docs/calibration/vacuity-flag-calibration-2026-08-08.json"
    # No staging: DC-16 selects only markdown from the tracked set, and a
    # ValueSite reads the worktree file, so the index copy is nothing's input.
    _mutate(root, registry, '"weak_directive_n": 20,', '"weak_directive_n": 21,')
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-3" in line and registry in line and "0.835/77/77/4/20" in line for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-3"}, r.stdout


def test_ac3_registry_recall_claim_drift_blocks(tmp_path: Path) -> None:
    """The registry's recall field is the one word the public claim rests on.
    Changing UNMEASURED to anything else reddens AC-3, because the row reads the
    field rather than the prose that quotes it."""
    root = _make_tree(tmp_path)
    registry = "docs/calibration/vacuity-flag-calibration-2026-08-08.json"
    _mutate(root, registry, '"recall": "UNMEASURED",', '"recall": "MEASURED",')
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-3" in line and registry in line and "expected UNMEASURED" in line for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-3"}, r.stdout


def test_ac3_refuses_when_its_surface_is_gone(tmp_path: Path) -> None:
    """The vacuity control for the delegation kind itself.

    The delegate builds its surface set by globbing. A tree with no README and
    no docs makes it return zero violations, which without `requires` prints as
    OK. This lane deletes the surface and asserts the row REFUSES, in the
    table's own wording, naming the missing path.

    The reddened SET is not asserted here: removing README.md is also DC-5's and
    DC-16's business, and it is correct that they notice. What must hold is that
    AC-3 does not go quietly green.
    """
    root = _make_tree(tmp_path)
    (root / "README.md").unlink()
    shutil.rmtree(root / "docs")
    _git(root, "add", "-A")
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("AC-3" in line and "has no surface to scan" in line for line in fail_lines), r.stdout


def test_ac3_refuses_when_the_named_predicate_is_gone(tmp_path: Path) -> None:
    """The dead-row control for the delegation kind.

    A row that names a symbol is only a guard while that symbol exists. This
    lane copies the script into a scratch repo root whose guard module has the
    predicate renamed, and asserts the row says so rather than reporting zero
    violations.

    Without this lane, deleting `vacuity_claim_violations_for_repo` from
    tests/test_structural_bans.py would leave AC-3 printing OK forever, which is
    precisely the dead control this repository exists to refuse. It works
    because _load_guard_module resolves the guard against the SCRIPT's own
    parent directory, so relocating the script relocates its guard lookup.

    Every OTHER guard module a row names is copied into the scratch root
    unrenamed, so the run reddens on this symbol and nothing else, and the
    reddened set says so. Without those copies AC-4's three delegates would
    fail to load here and redden alongside AC-3 (#544): the lane would still
    pass on its any(...) clause while quietly proving less than it claims.
    """
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "tests").mkdir()
    shutil.copyfile(_SCRIPT, fake_repo / "scripts" / "drift_check.py")
    for rel in (
        "scripts/release_gate.py",
        "tests/test_assurance_supply_chain_172.py",
    ):
        shutil.copyfile(_REPO_ROOT / rel, fake_repo / rel)
    guard = (_REPO_ROOT / "tests" / "test_structural_bans.py").read_text(encoding="utf-8")
    (fake_repo / "tests" / "test_structural_bans.py").write_text(
        guard.replace(
            "def vacuity_claim_violations_for_repo",
            "def vacuity_claim_violations_for_repo_RENAMED",
        ),
        encoding="utf-8",
    )
    root = _make_tree(tmp_path)
    r = _run(root, script=fake_repo / "scripts" / "drift_check.py")
    assert r.returncode == 1, r.stdout + r.stderr
    assert any(
        "AC-3" in line and "is absent or not callable" in line
        for line in r.stdout.splitlines()
        if line.strip().startswith("FAIL")
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-3"}, r.stdout


def test_ac3_undecodable_file_reddens_ac3_instead_of_crashing(tmp_path: Path) -> None:
    """The predicate-exception refusal (#565).

    A doc the delegate cannot decode is unreachable in the same sense as a
    missing surface or an unloadable module. Before the fix, `predicate(root,
    failures)` ran outside any try, so this file aborted the whole subprocess
    with an unhandled UnicodeDecodeError: exit 1, a traceback on stderr, and
    no rows at all. After the fix the row itself reddens, names the guard and
    the exception, and every other row still prints.
    """
    root = _make_tree(tmp_path)
    path = root / "docs" / "undecodable.md"
    path.write_bytes("Some heading\n\xe9 not utf8\n".encode("latin-1"))
    _git(root, "add", "--", "docs/undecodable.md")
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-3" in line and "vacuity_claim_violations_for_repo raised" in line for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-3"}, r.stdout
    ok_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("OK")]
    assert any("DC-1 " in line for line in ok_lines), r.stdout
    assert "DRIFT CHECK: BLOCKED" in r.stdout, r.stdout


def test_ac3_refuses_when_a_named_surface_beyond_readme_and_docs_is_gone(
    tmp_path: Path,
) -> None:
    """The coverage-widening control (#565).

    `requires` used to name only README.md and docs, two of the five surfaces
    the row's own summary claims. Deleting the sitegen templates, one of the
    other three, used to leave the row scanning nothing and printing OK. This
    lane proves the widened `requires` catches it: the row refuses, in the
    table's own wording, naming the missing path.
    """
    root = _make_tree(tmp_path)
    shutil.rmtree(root / "src" / "skill_harness" / "sitegen")
    _git(root, "add", "-A")
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-3" in line and "has no surface to scan" in line and "src/skill_harness/sitegen" in line
        for line in fail_lines
    ), r.stdout


# ---------------------------------------------------------------------------
# AC-4 (#544): the workflow configuration contract. Three legs, three
# delegates, one per defect: action references pinned to a full commit SHA
# (release_gate.py's G5), a workflow-level permissions baseline with no write
# grant, and no pull_request_target trigger (the two predicates in
# tests/test_assurance_supply_chain_172.py).
#
# Every poison ADDS a workflow file rather than editing a live one. Editing
# ci.yml in the synthetic tree would reach whatever else reads that file and
# stop the demonstration naming one row. Each poison file is compliant on the
# two legs it is not testing, so the reddened line attributes to one leg.
#
# The live workflows are copied into the tree by _make_tree, so the green
# arm of each lane is the real workflow set, not an empty directory.
# ---------------------------------------------------------------------------

_COMPLIANT_WORKFLOW = """\
name: Compliant
on:
  push:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
"""


def test_ac4_compliant_workflow_stays_green(tmp_path: Path) -> None:
    """Green control for all three legs. A workflow that pins its action to a
    full SHA, declares a read-only baseline and triggers on push is added to the
    tree and nothing reddens. Without this, the three poison lanes below would
    pass on a row that reddened at any added workflow whatsoever."""
    root = _make_tree(tmp_path)
    _write_tracked(root, ".github/workflows/compliant.yml", _COMPLIANT_WORKFLOW)
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ac4_tag_pinned_action_reddens_ac4_and_only_ac4(tmp_path: Path) -> None:
    """Poison leg 1, the SHA pin. The workflow is compliant on the permissions
    baseline and the trigger, so the single reddened line is the action pin.
    The failure carries release_gate.py's own G5 wording, which is the point of
    delegating: one defect reads as one sentence whichever caller found it."""
    root = _make_tree(tmp_path)
    _write_tracked(
        root,
        ".github/workflows/poison.yml",
        _COMPLIANT_WORKFLOW.replace(
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
            "actions/checkout@v5",
        ),
    )
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-4" in line and "poison.yml:10 action not SHA-pinned" in line for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-4"}, r.stdout


def test_ac4_missing_permissions_baseline_reddens_ac4_and_only_ac4(tmp_path: Path) -> None:
    """Poison leg 2, first half. No workflow-level permissions block at all.
    The action stays SHA-pinned and the trigger stays push, so the reddened line
    attributes to the baseline."""
    root = _make_tree(tmp_path)
    _write_tracked(
        root,
        ".github/workflows/poison.yml",
        _COMPLIANT_WORKFLOW.replace("permissions:\n  contents: read\n", ""),
    )
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-4" in line
        and ".github/workflows/poison.yml: no workflow-level permissions block" in line
        for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-4"}, r.stdout


def test_ac4_write_baseline_reddens_ac4_and_only_ac4(tmp_path: Path) -> None:
    """Poison leg 2, second half. A baseline that is present but broader than
    read. A rule checking only for presence would pass this, which is why the
    leg has two lanes rather than one: `permissions: write-all` is a block, and
    it is the opposite of the least-privilege claim the audit makes."""
    root = _make_tree(tmp_path)
    _write_tracked(
        root,
        ".github/workflows/poison.yml",
        _COMPLIANT_WORKFLOW.replace("permissions:\n  contents: read\n", "permissions: write-all\n"),
    )
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-4" in line and "workflow-level write grant 'write-all'" in line for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-4"}, r.stdout


def test_ac4_pull_request_target_reddens_ac4_and_only_ac4(tmp_path: Path) -> None:
    """Poison leg 3, the trigger. The workflow is SHA-pinned and read-only
    baselined, so the reddened line attributes to the trigger alone."""
    root = _make_tree(tmp_path)
    _write_tracked(
        root,
        ".github/workflows/poison.yml",
        _COMPLIANT_WORKFLOW.replace("on:\n  push:\n", "on:\n  pull_request_target:\n"),
    )
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-4" in line
        and ".github/workflows/poison.yml:3 carries the pull_request_target trigger" in line
        for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-4"}, r.stdout


def test_ac4_compliant_yaml_workflow_stays_green(tmp_path: Path) -> None:
    """The green arm for the widened glob, and it is half of a pair.

    The lane below proves the three delegates SEE a `.yaml` file. On its own
    that cannot tell a rule reading the new surface correctly from one that
    fires on everything it can now reach, and the widening's whole defence is
    that it costs nothing on a compliant tree. This lane writes a `.yaml`
    workflow that satisfies all three legs and asserts the row stays green.
    """
    root = _make_tree(tmp_path)
    _write_tracked(root, ".github/workflows/compliant.yaml", _COMPLIANT_WORKFLOW)
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ac4_reads_yaml_workflows_as_well_as_yml(tmp_path: Path) -> None:
    """The scope control. GitHub runs both suffixes, and all three delegates
    glob both. A `.yaml` workflow carrying all three defects reddens the row.

    This lane is the reason the glob widening in the commit before this one is
    a control rather than a tidy-up: no `.yaml` workflow is tracked here, so a
    narrow glob finds nothing to miss and the row prints OK either way. The
    fixture supplies the file the tree does not have."""
    root = _make_tree(tmp_path)
    _write_tracked(
        root,
        ".github/workflows/poison.yaml",
        "name: Poison\non:\n  pull_request_target:\njobs:\n"
        "  build:\n    steps:\n      - uses: actions/checkout@v5\n",
    )
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    for fragment in (
        "poison.yaml:7 action not SHA-pinned",
        ".github/workflows/poison.yaml: no workflow-level permissions block",
        ".github/workflows/poison.yaml:3 carries the pull_request_target trigger",
    ):
        assert any("AC-4" in line and fragment in line for line in fail_lines), (
            f"{fragment} missing:\n{r.stdout}"
        )
    assert _failed_row_ids(r.stdout) == {"AC-4"}, r.stdout


def test_ac4_refuses_when_its_surface_is_gone(tmp_path: Path) -> None:
    """The vacuity control for all three delegates at once.

    Each one builds its surface set by globbing a directory. A tree with no
    .github/workflows makes all three return zero violations, which without
    `requires` prints as OK: a row reporting that every workflow is compliant
    in a tree that has no workflows. This lane deletes the directory and
    asserts the row refuses, in the table's own wording, naming the path.

    The reddened SET is asserted here. Two rows read that directory: AC-4, and
    DC-18, whose value sites are the Vale pins in ci.yml (#488). Removing it
    must redden both and nothing else."""
    root = _make_tree(tmp_path)
    shutil.rmtree(root / ".github" / "workflows")
    _git(root, "add", "-A")
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "AC-4" in line and "has no surface to scan" in line and ".github/workflows" in line
        for line in fail_lines
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-4", "DC-18"}, r.stdout


def test_ac4_refuses_when_the_named_release_gate_predicate_is_gone(tmp_path: Path) -> None:
    """The dead-row control for AC-4's cross-file delegation.

    AC-4's SHA-pin leg is the first entry in this table to name a symbol in
    scripts/, so it is the one whose lookup is worth proving. A row that names a
    symbol is only a guard while that symbol exists. This lane copies the script
    into a scratch repo root whose release_gate.py has the gate renamed, and
    asserts the row says so rather than reporting zero violations.

    It works because _load_guard_module resolves the guard against the SCRIPT's
    own parent directory, so relocating the script relocates its guard lookup.
    The two #172 predicates and the AC-3 guard are copied unrenamed, so the run
    reddens on the renamed symbol and nothing else. That last clause is
    asserted rather than stated: a docstring claiming a reddened set the lane
    never compares is the same defect this row exists to refuse."""
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "tests").mkdir()
    shutil.copyfile(_SCRIPT, fake_repo / "scripts" / "drift_check.py")
    shutil.copyfile(
        _REPO_ROOT / "tests" / "test_structural_bans.py",
        fake_repo / "tests" / "test_structural_bans.py",
    )
    shutil.copyfile(
        _REPO_ROOT / "tests" / "test_assurance_supply_chain_172.py",
        fake_repo / "tests" / "test_assurance_supply_chain_172.py",
    )
    gate = (_REPO_ROOT / "scripts" / "release_gate.py").read_text(encoding="utf-8")
    (fake_repo / "scripts" / "release_gate.py").write_text(
        gate.replace("def gate_workflows_sha_pinned", "def gate_workflows_sha_pinned_RENAMED"),
        encoding="utf-8",
    )
    root = _make_tree(tmp_path)
    r = _run(root, script=fake_repo / "scripts" / "drift_check.py")
    assert r.returncode == 1, r.stdout + r.stderr
    assert any(
        "AC-4" in line
        and "scripts/release_gate.py:gate_workflows_sha_pinned is absent or not callable" in line
        for line in r.stdout.splitlines()
        if line.strip().startswith("FAIL")
    ), r.stdout
    assert _failed_row_ids(r.stdout) == {"AC-4"}, r.stdout


# ---------------------------------------------------------------------------
# DC-16 (#462): the collection's words_to_avoid list, refused in every markdown
# file in the tree. The poison fixture is written into a synthetic tree rather
# than committed: a committed markdown file carrying a listed word would make
# the live tree red, which is the state this row exists to refuse.
# ---------------------------------------------------------------------------


def test_dc16_poison_markdown_blocks(tmp_path: Path) -> None:
    """The poison fixture. One listed word in one markdown file, and the row
    reddens naming the file and the line."""
    root = _make_tree(tmp_path)
    _write_tracked(
        root, "docs/poison.md", "This paragraph is decoration.\nThe guard is load-bearing.\n"
    )
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-16" in line and "docs/poison.md:2" in line for line in fail_lines), r.stdout


def test_dc16_clean_markdown_is_green(tmp_path: Path) -> None:
    """The control for the poison above: the same file, the same sentence, the
    listed word replaced by the concrete noun it stood for."""
    root = _make_tree(tmp_path)
    _write_tracked(
        root, "docs/poison.md", "This paragraph is decoration.\nThe guard is what refuses here.\n"
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dc16_matches_case_insensitively(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _write_tracked(root, "docs/poison.md", "## Load-Bearing seams\n")
    r = _run(root)
    assert r.returncode == 1
    assert any("DC-16" in line and "Load-Bearing" in line for line in r.stdout.splitlines())


def test_dc16_does_not_fire_on_words_that_merely_contain_one(tmp_path: Path) -> None:
    """Whole-word, hyphen-aware. 'learn' contains 'earn', 'unlocked' contains
    'unlock', and 'load-bearing' contains 'earing' -- none of them is a hit.
    Without this the row would redden on ordinary prose and get muted."""
    root = _make_tree(tmp_path)
    _write_tracked(
        root,
        "docs/ordinary.md",
        "We learn from unlocked doors, yearning for earnest robustness.\n"
        "Curatorial powerlessness is unlockable but never seamlessly earnable.\n",
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dc16_digest_mismatch_blocks(tmp_path: Path) -> None:
    """Editing the vendored array without editing its digest is drift, caught
    here rather than waiting for the scheduled cross-repository read."""
    root = _make_tree(tmp_path)
    _mutate(root, "assets/words_to_avoid.json", '"robust"', '"robust",\n    "invented"')
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-16" in line and "recorded sha256" in line for line in fail_lines), r.stdout


def test_dc16_missing_manifest_blocks(tmp_path: Path) -> None:
    """An unreadable expectation is a refusal to report, never a pass."""
    root = _make_tree(tmp_path)
    (root / "assets" / "words_to_avoid.json").unlink()
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-16" in line and "missing" in line for line in fail_lines), r.stdout


def test_dc16_excluded_path_is_not_scanned(tmp_path: Path) -> None:
    """CHANGELOG.md is named in the exclusion list, so a listed word there does
    not redden the row. The exclusion is proved minimal in
    tests/test_words_to_avoid_ban.py, which asserts every excluded file really
    carries a hit."""
    root = _make_tree(tmp_path)
    _write_tracked(root, "CHANGELOG.md", "- the guard is load-bearing\n")
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dc16_scans_only_the_tracked_set(tmp_path: Path) -> None:
    """The #471 regression control. Three markdown files, one listed word each,
    differing only in what git knows about them:

      tracked/   staged, so a commit here publishes it   -> in scope
      untracked/ on disk, never added                    -> out of scope
      ignored/   matched by .gitignore                   -> out of scope

    The assertion names the file rather than only counting the failures. A
    count of one is satisfied by a scan that reports the wrong file, which is
    the failure this control exists to see. Before the fix DC-16 walked the
    filesystem, so all three reddened the row; on a working clone that meant
    264 failures locally against 0 in CI, and a gate a reader learns to mute."""
    root = _make_tree(tmp_path)
    _write_tracked(root, ".gitignore", "ignored/\n")
    _write_tracked(root, "tracked/note.md", "The guard is load-bearing.\n")
    (root / "untracked").mkdir()
    (root / "untracked" / "note.md").write_text("The guard is load-bearing.\n", encoding="utf-8")
    (root / "ignored").mkdir()
    (root / "ignored" / "note.md").write_text("The guard is load-bearing.\n", encoding="utf-8")

    r = _run(root)

    assert r.returncode == 1, r.stdout + r.stderr
    dc16_failures = [
        line
        for line in r.stdout.splitlines()
        if line.strip().startswith("FAIL DC-16:") and "words_to_avoid" in line
    ]
    assert any("tracked/note.md:1" in line for line in dc16_failures), r.stdout
    assert not any("untracked/note.md" in line for line in dc16_failures), r.stdout
    assert not any("ignored/note.md" in line for line in dc16_failures), r.stdout
    assert len(dc16_failures) == 1, r.stdout


def test_dc16_refuses_when_the_tracked_set_cannot_be_read(tmp_path: Path) -> None:
    """No index, no scan, and the row says so.

    A tree git cannot describe is not a clean tree. Falling back to a
    filesystem walk here would run a different check under the same row name,
    and reporting an empty scan would print as a pass -- the exact shape of
    failure DC-16's manifest lane already refuses (#471)."""
    root = _make_tree(tmp_path)
    # Renamed, not deleted. Git marks its loose object files read-only, and
    # shutil.rmtree on Windows raises PermissionError on the first one.
    (root / ".git").rename(root / "git-directory-moved-aside")
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "DC-16" in line and "cannot select the scanned set" in line for line in fail_lines
    ), r.stdout


def test_dc16_prints_its_scope_on_a_green_run(tmp_path: Path) -> None:
    """F7 visibility, the same reason the structural exemptions are printed:
    DC-16 claims a scope, so both halves of it are printed -- the command that
    selects the files, and the tracked files that selection then drops."""
    r = _run(_make_tree(tmp_path))
    assert r.returncode == 0
    assert any(
        line.startswith("DC-16 markdown scan selection:") and "git ls-files" in line
        for line in r.stdout.splitlines()
    ), r.stdout
    exclude_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("EXCLUDE")]
    for rel in (
        "CHANGELOG.md",
        "docs/PLAN.md",
        "docs/findings/v0.2-preregistration.md",
        "docs/findings/v0.2-reaim-gate.md",
        "docs/ratifications/MIRROR-0001-on-irreducibility.md",
    ):
        assert any(rel in line for line in exclude_lines), r.stdout


# ---------------------------------------------------------------------------
# DC-17: mirror records — landed_as symbol existence + UNLANDED ticket status
# (#514)
# ---------------------------------------------------------------------------


def _write_mirror_record(
    root: Path,
    *,
    additions: str = "",
    body: str = "",
) -> None:
    path = root / "docs" / "ratifications" / "MIRROR-0001-test-slug.md"
    path.write_text(
        "---\n"
        "mirror: MIRROR-0001\n"
        'source_page: "Test Page"\n'
        'source_last_edited: "2026-08-11T00:00:00.000Z"\n'
        'ratified_date: "2026-09-13"\n'
        "status: RATIFIED\n"
        "---\n\n"
        "# MIRROR-0001 -- test mirror record\n\n"
        f"{additions}\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_dc17_valid_mirror_record_is_green(tmp_path: Path) -> None:
    """A MIRROR record where every landed_as symbol exists under the search
    roots is green."""
    root = _make_tree(tmp_path)
    _write_mirror_record(
        root,
        additions=("### Addition 1\n\n- `landed_as: WIN_RATE_THRESHOLD`\n"),
    )
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dc17_nonexistent_symbol_blocks(tmp_path: Path) -> None:
    """Control: pointing one landed_as at a symbol that does not exist must
    turn DC-17 red, naming the record and the symbol."""
    root = _make_tree(tmp_path)
    _write_mirror_record(
        root,
        additions=("### Addition 1\n\n- `landed_as: NONEXISTENT_SYMBOL_XYZ`\n"),
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-17" in line and "NONEXISTENT_SYMBOL_XYZ" in line for line in fail_lines), (
        r.stdout
    )


def _drop_live_mirror(root: Path) -> None:
    """Remove the real MIRROR record the fixture copies in.

    It carries ``UNLANDED #514``, so leaving it in place makes every DC-17
    case below depend on a second ticket's state as well as the one it is
    actually testing.
    """
    live = root / "docs" / "ratifications" / "MIRROR-0001-on-irreducibility.md"
    if live.exists():
        live.unlink()


def test_dc17_unlanded_closed_ticket_blocks(tmp_path: Path) -> None:
    """Control: an UNLANDED row naming a closed ticket must turn DC-17 red.

    The ticket state is INJECTED, not fetched. The previous version of this
    control read issue #1 from api.github.com, so it asserted that the network
    worked and that the rule held, and could not tell those apart. It went red
    on one of four CI cells when the unauthenticated rate budget ran out
    (PR #518), which reads as flakiness and invites a re-run rather than a fix.
    """
    root = _make_tree(tmp_path)
    _drop_live_mirror(root)
    _write_mirror_record(
        root,
        additions=("### Addition 1\n\n- `landed_as: UNLANDED #1`\n"),
    )
    r = _run(root, ticket_states={"1": "closed"})
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any(
        "DC-17" in line and "closed ticket" in line and "#1" in line for line in fail_lines
    ), r.stdout


def test_dc17_unlanded_open_ticket_is_green(tmp_path: Path) -> None:
    """The other arm of the same control: an OPEN ticket must NOT block.

    Without this arm, a DC-17 that failed on every UNLANDED row whatever its
    state would satisfy the closed-ticket control above while measuring
    nothing about ticket state at all.
    """
    root = _make_tree(tmp_path)
    _drop_live_mirror(root)
    _write_mirror_record(
        root,
        additions=("### Addition 1\n\n- `landed_as: UNLANDED #1`\n"),
    )
    r = _run(root, ticket_states={"1": "open"})
    assert r.returncode == 0, r.stdout + r.stderr


def test_dc17_unreadable_ticket_state_blocks(tmp_path: Path) -> None:
    """Control: a ticket state that cannot be READ must turn DC-17 red.

    This is the defect that opened PR #518 red. ``_check_ticket_closed``
    returned ``None`` on any network error and the caller tested ``is True``,
    so an unreachable API produced a clean run. "Could not read" and "no
    problem found" are different findings, and the check now says which one
    it has.
    """
    root = _make_tree(tmp_path)
    _drop_live_mirror(root)
    _write_mirror_record(
        root,
        additions=("### Addition 1\n\n- `landed_as: UNLANDED #1`\n"),
    )
    r = _run(root, ticket_states={"1": "unreadable"})
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-17" in line and "unreadable" in line and "#1" in line for line in fail_lines), (
        r.stdout
    )


def test_dc17_malformed_seam_is_unreadable_not_absent(tmp_path: Path) -> None:
    """A malformed seam value must block, never fall through to the network.

    A test that believes it is isolated and silently is not is the whole class
    of defect this seam exists to end, so a typo in the seam is treated as
    unreadable rather than as an absent override.
    """
    root = _make_tree(tmp_path)
    _drop_live_mirror(root)
    _write_mirror_record(
        root,
        additions=("### Addition 1\n\n- `landed_as: UNLANDED #1`\n"),
    )
    env = {**os.environ, "SKILL_HARNESS_TICKET_STATES": "{not json"}
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO_ROOT),
        check=False,
        env=env,
    )
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-17" in line and "unreadable" in line for line in fail_lines), r.stdout


def test_dc17_zero_mirror_files_blocks(tmp_path: Path) -> None:
    """A check that scans nothing passes trivially: DC-17 must refuse when
    the mirror surface has zero MIRROR-*.md files."""
    root = _make_tree(tmp_path)
    # Remove the MIRROR file that _make_tree copies
    mirror = root / "docs" / "ratifications" / "MIRROR-0001-on-irreducibility.md"
    if mirror.exists():
        mirror.unlink()
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-17" in line and "no MIRROR-*.md files found" in line for line in fail_lines), (
        r.stdout
    )


def test_dc17_mirror_with_zero_landed_as_blocks(tmp_path: Path) -> None:
    """A MIRROR file with front-matter but no landed_as entries is the same
    trivial-pass hole as an empty glob: DC-17 must refuse it."""
    root = _make_tree(tmp_path)
    live = root / "docs" / "ratifications" / "MIRROR-0001-on-irreducibility.md"
    if live.exists():
        live.unlink()
    _write_mirror_record(root, additions="### Addition 1\n\nNo landed_as field here.\n")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-17" in line and "no landed_as" in line for line in fail_lines), r.stdout


def test_dc17_missing_ledger_dir_blocks(tmp_path: Path) -> None:
    """The registered surface itself going missing is drift."""
    import shutil as _shutil

    root = _make_tree(tmp_path)
    _shutil.rmtree(root / "docs" / "ratifications")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-17" in line and "ledger dir missing" in line for line in fail_lines), r.stdout
    # docs/ratifications is also DC-12's registered surface (#574).
    assert _failed_row_ids(r.stdout) == {"DC-12", "DC-17"}, r.stdout


def test_dc17_printed_in_green_listing() -> None:
    """DC-17 must appear in the OK listing on a green run."""
    r = _run()
    assert r.returncode == 0
    ok_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("OK")]
    assert any("DC-17" in line for line in ok_lines), r.stdout


def test_dc17_multiple_additions_all_checked(tmp_path: Path) -> None:
    """Multiple landed_as entries in one record are all checked: one valid
    and one invalid must block."""
    root = _make_tree(tmp_path)
    _write_mirror_record(
        root,
        additions=(
            "### Addition 1\n\n"
            "- `landed_as: WIN_RATE_THRESHOLD`\n\n"
            "### Addition 2\n\n"
            "- `landed_as: TOTALLY_FAKE_SYMBOL`\n"
        ),
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-17" in line and "TOTALLY_FAKE_SYMBOL" in line for line in fail_lines), r.stdout


def test_dc17_real_mirror_names_source_and_six_unlanded_additions() -> None:
    """AC pin: the committed On-Irreducibility mirror names the source page
    and edit date, and accounts for all six additions -- not omitted, not
    fabricated as landed (#514).

    The tracking ticket number is deliberately NOT pinned. This assertion read
    ``== ["UNLANDED #514"] * 6`` until #520, and that literal made the test
    fail on its own correction: closing #514 turned DC-17 red on main, the
    repair was to repoint the rows at an open ticket, and this test blocked
    exactly that repair while asserting nothing DC-17 does not already check.

    What is pinned instead is the SHAPE the record must hold: six accounted
    additions, every UNLANDED row naming ONE ticket rather than drifting
    apart, and no row silently dropped. Which ticket is live is DC-17's job,
    and DC-17 reads it from the API.

    #525 cleared UNLANDED from declined additions 2 and 4. Those two are still
    accounted by heading; they no longer contribute a landed_as row, so the
    remaining open work was four UNLANDED rows, not six. A decline is a landed
    decision: leaving UNLANDED on it would re-break DC-17 when #520 closes.

    #526 landed additions 3, 5 and 6 as schema keys. Addition 1 remains
    UNLANDED. Addition 6 carries two landed_as entries (retest_triggers and
    expiry_state) because it adds two schema keys. The remaining open work is
    one UNLANDED row.
    """
    path = _REPO_ROOT / "docs" / "ratifications" / "MIRROR-0001-on-irreducibility.md"
    text = path.read_text(encoding="utf-8")
    assert 'source_page: "On Irreducibility"' in text
    assert 'source_last_edited: "2026-08-11T17:33:55.553Z"' in text
    assert "source_status: Done" in text
    assert "source_verdict: HOLDS" in text
    expected_headings = (
        "### 1. Activation-chain stages and failure location",
        "### 2. The tested component set",
        "### 3. The implementation family and alternatives considered",
        "### 4. The cost vector and dominance rule",
        "### 5. The claim scope and disturbance set",
        "### 6. The retest triggers and expiry state",
    )
    for heading in expected_headings:
        assert heading in text, f"missing addition heading: {heading}"
    landed = re.findall(r"landed_as:\s*(.+?)\s*`", text)
    # Five landed_as rows: addition 1 UNLANDED, additions 3 and 5 landed,
    # addition 6 landed with two keys (retest_triggers + expiry_state).
    assert len(landed) == 5, f"expected five landed_as rows, got {landed}"
    unlanded = [v for v in landed if v.startswith("UNLANDED ")]
    landed_symbols = [v for v in landed if not v.startswith("UNLANDED ")]
    for value in unlanded:
        assert re.fullmatch(r"UNLANDED #\d+", value), f"malformed UNLANDED row: {value}"
    assert len(set(unlanded)) <= 1, (
        f"UNLANDED rows name more than one ticket, so closing one leaves the rest stale: {unlanded}"
    )
    # Landed symbols must exist under docs/sers/ or src/skill_harness/.
    assert "implementation_family" in landed_symbols
    assert "claim_scope" in landed_symbols
    assert "retest_triggers" in landed_symbols
    assert "expiry_state" in landed_symbols


def test_dc17_additions_2_and_4_declined_with_reason() -> None:
    """AC (#525): additions 2 and 4 carry a decline with its stated reason,
    not UNLANDED. Each decline names a reversal condition specific enough
    that a reader can tell what would reverse it.

    Pins external behaviour of the mirror record: the section is a decline
    (not a deferral), the UNLANDED row is gone, and the reason states what
    would lapse the decline. DC-17 is not modified; clearing the row is the
    format change that keeps the check green with two fewer open-work rows.
    """
    path = _REPO_ROOT / "docs" / "ratifications" / "MIRROR-0001-on-irreducibility.md"
    text = path.read_text(encoding="utf-8")

    def _section(heading: str) -> str:
        """Return the text between one heading and the next ### or end."""
        pattern = re.compile(rf"(^{re.escape(heading)}\b.*?)(?=^### |\Z)", re.MULTILINE | re.DOTALL)
        m = pattern.search(text)
        assert m, f"heading {heading!r} not found"
        return m.group(1)

    section_2 = _section("### 2. The tested component set")
    section_4 = _section("### 4. The cost vector and dominance rule")

    for heading, section in (
        ("### 2. The tested component set", section_2),
        ("### 4. The cost vector and dominance rule", section_4),
    ):
        assert re.search(r"Declined", section), f"{heading}: no 'Declined' in section prose"
        assert re.search(r"Revisit if", section), (
            f"{heading}: no reversal condition ('Revisit if') in section prose"
        )
        assert not re.search(r"landed_as:\s*UNLANDED", section), (
            f"{heading}: still carries UNLANDED; a decline is a landed decision "
            "and must clear the open-work row (#525, S445)"
        )
        assert not re.search(r"landed_as:", section), (
            f"{heading}: carries a landed_as row; declined additions replace "
            "landed_as with a stated decline, they do not point at a symbol"
        )

    assert "component vocabulary" in section_2, (
        "addition 2 reason must name the missing component vocabulary"
    )
    assert "delivery.channel" in section_2, (
        "addition 2 reason must name the nearest non-match (delivery.channel)"
    )
    assert "cost dimensions" in section_4, "addition 4 reason must name the missing cost dimensions"
    assert "dominance rule" in section_4, "addition 4 reason must name the missing dominance rule"


# ---------------------------------------------------------------------------
# DC-18: Vale version pins — release URLs and cache keys cite 3.9.1 (#488)
# ---------------------------------------------------------------------------

_VALE_LINUX_URL = (
    "https://github.com/errata-ai/vale/releases/download/v3.9.1/vale_3.9.1_Linux_64-bit.tar.gz"
)
_VALE_WINDOWS_URL = (
    "https://github.com/errata-ai/vale/releases/download/v3.9.1/vale_3.9.1_Windows_64-bit.zip"
)
_VALE_CACHE_KEY = "key: vale-${{ runner.os }}-3.9.1"


def _replace_nth(text: str, old: str, new: str, n: int) -> str:
    """Replace the n-th occurrence of old (0-based) and leave the rest alone."""
    start = -1
    for _ in range(n + 1):
        start = text.find(old, start + 1)
        assert start != -1, f"occurrence {n} of {old!r} not found"
    return text[:start] + new + text[start + len(old) :]


def test_dc18_vale_version_pins_are_green(tmp_path: Path) -> None:
    """The default synthetic tree carries the real ci.yml and test file, so
    DC-18 is green by construction. This test pins that property."""
    root = _make_tree(tmp_path)
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr
    ok_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("OK")]
    assert any("DC-18" in line for line in ok_lines), r.stdout


def test_dc18_linux_url_drift_blocks(tmp_path: Path) -> None:
    """Control: changing every Linux release URL must turn DC-18 red."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        ".github/workflows/ci.yml",
        _VALE_LINUX_URL,
        "https://github.com/errata-ai/vale/releases/download/v3.9.2/vale_3.9.2_Linux_64-bit.tar.gz",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-18" in line for line in fail_lines), r.stdout


def test_dc18_single_linux_url_drift_blocks(tmp_path: Path) -> None:
    """Control: changing only the first Linux URL (test job) must turn DC-18 red.

    File order puts the test job before the vale job. A single drifted pin is
    the load-bearing case: one job installs 3.8.0 while the other and the
    cache key still say 3.9.1.
    """
    root = _make_tree(tmp_path)
    ci_path = root / ".github/workflows/ci.yml"
    text = ci_path.read_text(encoding="utf-8")
    mutated = _replace_nth(
        text,
        _VALE_LINUX_URL,
        "https://github.com/errata-ai/vale/releases/download/v3.8.0/vale_3.8.0_Linux_64-bit.tar.gz",
        0,
    )
    ci_path.write_text(mutated, encoding="utf-8")
    _git(root, "add", "--", ".github/workflows/ci.yml")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-18" in line for line in fail_lines), r.stdout


def test_dc18_windows_url_drift_blocks(tmp_path: Path) -> None:
    """Control: changing only the Windows zip URL must turn DC-18 red."""
    root = _make_tree(tmp_path)
    _mutate(
        root,
        ".github/workflows/ci.yml",
        _VALE_WINDOWS_URL,
        "https://github.com/errata-ai/vale/releases/download/v3.8.0/vale_3.8.0_Windows_64-bit.zip",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-18" in line for line in fail_lines), r.stdout


def test_dc18_cache_key_drift_blocks(tmp_path: Path) -> None:
    """Control: changing a cache key while the URLs stay put must turn DC-18 red.

    A lagging key restores a stale binary on hit and never re-fetches the
    version the curl URL names.
    """
    root = _make_tree(tmp_path)
    _mutate(
        root,
        ".github/workflows/ci.yml",
        _VALE_CACHE_KEY,
        "key: vale-${{ runner.os }}-3.8.0",
    )
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-18" in line for line in fail_lines), r.stdout


def test_dc18_registered_text_present_is_green(tmp_path: Path) -> None:
    """The registered sentence in test_vale_doctrine_agreement.py is present
    on a green tree. Presence is the green control; absence is the red one
    below."""
    root = _make_tree(tmp_path)
    test_file = root / "tests" / "test_vale_doctrine_agreement.py"
    assert test_file.exists()
    text = test_file.read_text(encoding="utf-8")
    assert "pinned to the same version the CI workflow installs" in text
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dc18_missing_registered_text_blocks(tmp_path: Path) -> None:
    """Control: removing the registered sentence from the test file must
    turn DC-18 red, because the test file no longer names the workflow as
    its source of truth."""
    root = _make_tree(tmp_path)
    test_file = root / "tests" / "test_vale_doctrine_agreement.py"
    text = test_file.read_text(encoding="utf-8")
    text = text.replace(
        "pinned to the same version the CI workflow installs",
        "pinned to version X.Y.Z",
    )
    test_file.write_text(text, encoding="utf-8")
    _git(root, "add", "--", "tests/test_vale_doctrine_agreement.py")
    r = _run(root)
    assert r.returncode == 1
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-18" in line for line in fail_lines), r.stdout


def test_dc18_install_steps_are_split_and_named() -> None:
    """Criterion 3/4: install failure and prose/test failure are different
    named steps on both the test job and the vale job.

    Reads the real ci.yml. Fails when either job collapses download and
    path-install into one step, or renames the path-install step so a check
    list no longer attributes the failure.
    """
    ci = (_REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    test_block = re.search(r"\n  test:\n(?P<body>.*?)(?=\n  [A-Za-z0-9_-]+:\n)", ci, re.DOTALL)
    vale_block = re.search(r"\n  vale:\n(?P<body>.*?)(?=\n  [A-Za-z0-9_-]+:\n)", ci, re.DOTALL)
    assert test_block is not None, "could not find the test job in ci.yml"
    assert vale_block is not None, "could not find the vale job in ci.yml"
    for name, body in (("test", test_block.group("body")), ("vale", vale_block.group("body"))):
        assert "- name: Install Vale\n" in body, f"{name} job missing 'Install Vale' step"
        assert "- name: Install Vale to system path\n" in body, (
            f"{name} job missing 'Install Vale to system path' step"
        )
        assert "cache-vale" in body, f"{name} job missing Vale binary cache step"
        assert "runner.temp" in body, (
            f"{name} job must cache under runner.temp so Windows restores the path"
        )


# ---------------------------------------------------------------------------
# DC-19 (#592): asset pairs — every source-export pair in the manifest
# matches its recorded sha256
# ---------------------------------------------------------------------------


def test_dc19_synthetic_tree_is_green(tmp_path: Path) -> None:
    """A tree where the manifest hashes agree with the files on disk is green."""
    root = _make_tree(tmp_path)
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr
    ok_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("OK")]
    assert any("DC-19" in line for line in ok_lines), r.stdout


def test_dc19_source_changed_without_export_reddens_dc19(tmp_path: Path) -> None:
    """Negative control: editing the SVG source without re-exporting the PNG
    must block, naming the file and both hashes. This is the exact defect
    #592 was filed to catch — a stale export ships alongside a new source,
    and nothing in the repository catches it today."""
    root = _make_tree(tmp_path)
    # Mutate the SVG source (change its content) so its hash no longer matches
    # the recorded source_sha256.
    svg_path = root / "assets" / "social-preview.svg"
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_path.write_text(svg_text.replace("skill-harness", "skill-harness-UNIQUE"), encoding="utf-8")
    manifest = json.loads((root / "assets" / "asset-pairs.json").read_text(encoding="utf-8"))
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-19" in line for line in fail_lines), r.stdout
    failure = next(line for line in fail_lines if "mismatched source" in line)
    pair = manifest["pairs"][0]
    assert "assets/social-preview.svg" in failure
    assert "assets/social-preview.png" in failure
    assert pair["source_sha256"][:16] in failure
    assert hashlib.sha256(svg_path.read_bytes()).hexdigest()[:16] in failure
    assert pair["export_sha256"][:16] in failure


def test_dc19_export_changed_without_source_reddens_dc19(tmp_path: Path) -> None:
    """Negative control: editing the PNG export without changing the SVG source
    must block. The manifest records both hashes; if the PNG drifts the
    recorded export_sha256 disagrees."""
    root = _make_tree(tmp_path)
    png_path = root / "assets" / "social-preview.png"
    # Write garbage at the start — the file is no longer the recorded PNG.
    data = png_path.read_bytes()
    png_path.write_bytes(b"GARBAGE" + data[7:])
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-19" in line for line in fail_lines), r.stdout
    assert any("social-preview.png" in line and "recorded hash" in line for line in fail_lines), (
        r.stdout
    )


def test_dc19_both_changed_together_is_green(tmp_path: Path) -> None:
    """Green control: changing both halves of a pair AND re-recording the hashes
    is the correct workflow. The manifest on disk has the right hashes, so the
    check passes."""
    import hashlib as _hashlib

    root = _make_tree(tmp_path)
    # Change both files.
    svg_path = root / "assets" / "social-preview.svg"
    svg_text = svg_path.read_text(encoding="utf-8")
    new_svg = svg_text.replace("skill-harness", "skill-harness-UNIQUE")
    svg_path.write_text(new_svg, encoding="utf-8")
    png_path = root / "assets" / "social-preview.png"
    data = png_path.read_bytes()
    new_png = b"MODIFIED" + data[8:]
    png_path.write_bytes(new_png)
    # Update the manifest with the new hashes.
    manifest_path = root / "assets" / "asset-pairs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pairs"][0]["source_sha256"] = _hashlib.sha256(new_svg.encode()).hexdigest()
    manifest["pairs"][0]["export_sha256"] = _hashlib.sha256(new_png).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dc19_manifest_missing_blocks(tmp_path: Path) -> None:
    """A missing manifest is a refusal, not a pass — same vacuity rule as DC-16."""
    root = _make_tree(tmp_path)
    (root / "assets" / "asset-pairs.json").unlink()
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-19" in line and "missing" in line for line in fail_lines), r.stdout


def test_dc19_manifest_empty_pairs_blocks(tmp_path: Path) -> None:
    """An empty pairs list is vacuous — the check must refuse, not pass."""
    root = _make_tree(tmp_path)
    manifest_path = root / "assets" / "asset-pairs.json"
    manifest_path.write_text('{"pairs": []}\n', encoding="utf-8")
    r = _run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    fail_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]
    assert any("DC-19" in line and "empty" in line for line in fail_lines), r.stdout


def test_dc19_printed_in_green_listing() -> None:
    """DC-19 must appear in the OK listing on a green run."""
    r = _run()
    assert r.returncode == 0
    ok_lines = [line for line in r.stdout.splitlines() if line.strip().startswith("OK")]
    assert any("DC-19" in line for line in ok_lines), r.stdout
