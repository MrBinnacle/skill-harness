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

_LIVE_IDS = ("DC-1", "DC-2", "DC-3", "DC-4", "DC-5", "DC-6")
_PLANNED_IDS = ("DC-7", "DC-8", "DC-9", "DC-10", "DC-11", "DC-12", "DC-13")

# Every file a live row reads; copied verbatim into synthetic trees so each
# failure test starts from a tree that is green by construction.
_LIVE_SURFACES = (
    "src/skill_harness/aggregation/fit.py",
    "src/skill_harness/aggregation/status.py",
    "src/skill_harness/ablation/stopping.py",
    "src/skill_harness/semantics.py",
    "src/skill_harness/cli/main.py",
    "docs/INVARIANTS.md",
    "docs/PRD.md",
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
    """DC-7..DC-13 are registered-but-inactive and must render as PLANNED."""
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
