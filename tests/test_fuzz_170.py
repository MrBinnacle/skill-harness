"""Atheris fuzz harness pins for #170.

The long runs live under ``@pytest.mark.assurance`` and are excluded from the
default CI matrix cell. Environments without atheris (Windows, host machines
without ``requirements-assurance-container.txt``) skip cleanly.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_FUZZ = _REPO / "fuzz"
_PARSER_TARGET = _FUZZ / "parser_target.py"
_JSON_TARGET = _FUZZ / "json_ingestion_target.py"
_PARSER_CORPUS = _FUZZ / "corpus" / "parser"
_JSON_CORPUS = _FUZZ / "corpus" / "json"
_PARSER_CRASHES = _FUZZ / "crashes" / "parser"
_JSON_CRASHES = _FUZZ / "crashes" / "json"
_ARTIFACTS = _FUZZ / "artifacts"
_REPORT = _REPO / "docs" / "assurance" / "fuzz-report.md"

# Default long-lane budget: 30 minutes per target = 60 minutes total.
# Overridable for local smoke (FUZZ_MAX_TOTAL_TIME_SEC) without changing AC.
_DEFAULT_PER_TARGET_SEC = 30 * 60


def _atheris_available() -> bool:
    return importlib.util.find_spec("atheris") is not None


def _require_atheris() -> None:
    if not _atheris_available():
        pytest.skip("atheris not installed (see requirements-assurance-container.txt)")


def _per_target_seconds() -> int:
    raw = os.environ.get("FUZZ_MAX_TOTAL_TIME_SEC")
    if raw is None or raw == "":
        return _DEFAULT_PER_TARGET_SEC
    return max(1, int(raw))


def _run_target(
    target: Path,
    corpus: Path,
    crashes: Path,
    *,
    max_total_time: int,
    runs: int | None = None,
) -> subprocess.CompletedProcess[str]:
    crashes.mkdir(parents=True, exist_ok=True)
    corpus.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(target),
        f"-max_total_time={max_total_time}",
        f"-artifact_prefix={crashes}/",
        str(corpus),
    ]
    if runs is not None:
        cmd.insert(-1, f"-runs={runs}")
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=str(_REPO),
        timeout=max_total_time + 120,
    )


def _crash_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir() if p.is_file() and p.name not in {".gitkeep", ".gitignore"}
    )


# ---------------------------------------------------------------------------
# Structure pins (default lane — no atheris required)
# ---------------------------------------------------------------------------


def test_fuzz_targets_checked_in() -> None:
    """Both atheris entry points and seed corpora exist under fuzz/."""
    assert _PARSER_TARGET.is_file()
    assert _JSON_TARGET.is_file()
    assert _PARSER_CORPUS.is_dir()
    assert _JSON_CORPUS.is_dir()
    assert any(_PARSER_CORPUS.iterdir()), "parser seed corpus must be non-empty"
    assert any(_JSON_CORPUS.iterdir()), "json seed corpus must be non-empty"


def test_fuzz_dir_outside_default_pytest_collection() -> None:
    """Harness lives outside testpaths so default collection never loads it."""
    # pyproject testpaths = ["tests"]; fuzz/ is a sibling, not a child.
    assert _FUZZ.parent == _REPO
    assert "tests" not in _FUZZ.parts
    assert not str(_FUZZ).startswith(str(_REPO / "tests"))


def test_fuzz_targets_import_guard_atheris() -> None:
    """Targets import atheris at module level — missing atheris fails import, not collection."""
    parser_src = _PARSER_TARGET.read_text(encoding="utf-8")
    json_src = _JSON_TARGET.read_text(encoding="utf-8")
    assert "import atheris" in parser_src
    assert "import atheris" in json_src
    assert "MalformedSkillError" in parser_src
    assert "ExtractedClause" in json_src
    assert "ExtractionResult" in json_src


def test_fuzz_report_path_reserved() -> None:
    """Report location is the ticket-named path (may be written by the long lane)."""
    assert _REPORT.parent.is_dir()
    assert _REPORT.name == "fuzz-report.md"


# ---------------------------------------------------------------------------
# Short atheris smoke (skips without atheris; stays well under 60s)
# ---------------------------------------------------------------------------


def test_fuzz_parser_smoke_skips_or_runs() -> None:
    """A few thousand runs through the parser target; skip if no atheris."""
    _require_atheris()
    result = _run_target(
        _PARSER_TARGET,
        _PARSER_CORPUS,
        _PARSER_CRASHES,
        max_total_time=5,
        runs=2000,
    )
    combined = result.stderr + result.stdout
    assert "Done " in combined or "DONE" in combined or "INITED" in combined, combined[-1500:]
    # Clean budget exhaustion is 0; a found crash is non-zero — both mean the harness ran.
    assert result.returncode is not None


def test_fuzz_json_smoke_skips_or_runs() -> None:
    """A few thousand runs through the JSON ingestion target; skip if no atheris."""
    _require_atheris()
    result = _run_target(
        _JSON_TARGET,
        _JSON_CORPUS,
        _JSON_CRASHES,
        max_total_time=5,
        runs=2000,
    )
    combined = result.stderr + result.stdout
    assert "Done " in combined or "DONE" in combined or "INITED" in combined, combined[-1500:]
    assert result.returncode is not None


def test_fuzz_skips_cleanly_when_atheris_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-atheris environments skip the atheris-gated helpers without raising."""
    monkeypatch.setattr(
        "tests.test_fuzz_170.importlib.util.find_spec",
        lambda _name: None,
    )
    assert _atheris_available() is False
    with pytest.raises(pytest.skip.Exception, match="atheris not installed"):
        _require_atheris()


# ---------------------------------------------------------------------------
# Long lane — ≥1h total wall, assurance-marked
# ---------------------------------------------------------------------------


def _write_stats(name: str, payload: dict[str, object]) -> Path:
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = _ARTIFACTS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _parse_libfuzzer_stats(stderr: str) -> dict[str, int | str]:
    """Best-effort extract of exec count / corpus size from libFuzzer summary lines."""
    out: dict[str, int | str] = {}
    # e.g. "stat::number_of_executed_units: 12345"
    for key, pat in (
        ("executions", r"(?:stat::number_of_executed_units|Done\s+(\d+)\s+runs|exec/s)"),
        ("corpus_size", r"(?:stat::new_units_added|corp:\s*(\d+)|#(\d+))"),
    ):
        m = re.search(pat, stderr)
        if m:
            for g in m.groups():
                if g and g.isdigit():
                    out[key] = int(g)
                    break
    # Final "DONE" style: look for "#12345" last pulse
    pulses = re.findall(r"#(\d+)", stderr)
    if pulses:
        out.setdefault("executions", int(pulses[-1]))
    corp = re.findall(r"corp:\s*(\d+)", stderr)
    if corp:
        out["corpus_size"] = int(corp[-1])
    out["raw_tail"] = stderr[-2000:] if stderr else ""
    return out


@pytest.mark.assurance
def test_fuzz_parser_long_lane() -> None:
    """Run the parser atheris target for half the one-hour budget."""
    _require_atheris()
    budget = _per_target_seconds()
    t0 = time.monotonic()
    result = _run_target(
        _PARSER_TARGET,
        _PARSER_CORPUS,
        _PARSER_CRASHES,
        max_total_time=budget,
    )
    elapsed = time.monotonic() - t0
    stats = _parse_libfuzzer_stats(result.stderr + result.stdout)
    payload = {
        "target": "parser",
        "max_total_time_sec": budget,
        "elapsed_sec": elapsed,
        "returncode": result.returncode,
        "crash_count": len(_crash_files(_PARSER_CRASHES)),
        "corpus_files": len(list(_PARSER_CORPUS.iterdir())),
        "stats": stats,
        "stderr_tail": (result.stderr or "")[-4000:],
        "stdout_tail": (result.stdout or "")[-1000:],
    }
    _write_stats("parser_run", payload)
    # Soft floor: when running the full default budget, require real wall time.
    if budget >= _DEFAULT_PER_TARGET_SEC:
        assert elapsed >= budget * 0.9, f"parser fuzz wall {elapsed:.1f}s < 90% of {budget}s"


@pytest.mark.assurance
def test_fuzz_json_long_lane() -> None:
    """Run the JSON ingestion atheris target for half the one-hour budget."""
    _require_atheris()
    budget = _per_target_seconds()
    t0 = time.monotonic()
    result = _run_target(
        _JSON_TARGET,
        _JSON_CORPUS,
        _JSON_CRASHES,
        max_total_time=budget,
    )
    elapsed = time.monotonic() - t0
    stats = _parse_libfuzzer_stats(result.stderr + result.stdout)
    payload = {
        "target": "json_ingestion",
        "max_total_time_sec": budget,
        "elapsed_sec": elapsed,
        "returncode": result.returncode,
        "crash_count": len(_crash_files(_JSON_CRASHES)),
        "corpus_files": len(list(_JSON_CORPUS.iterdir())),
        "stats": stats,
        "stderr_tail": (result.stderr or "")[-4000:],
        "stdout_tail": (result.stdout or "")[-1000:],
    }
    _write_stats("json_run", payload)
    if budget >= _DEFAULT_PER_TARGET_SEC:
        assert elapsed >= budget * 0.9, f"json fuzz wall {elapsed:.1f}s < 90% of {budget}s"


@pytest.mark.assurance
def test_fuzz_report_written_after_long_lane() -> None:
    """Synthesize docs/assurance/fuzz-report.md from artifact JSON (+ triage crashes)."""
    _require_atheris()
    parser_path = _ARTIFACTS / "parser_run.json"
    json_path = _ARTIFACTS / "json_run.json"
    if not parser_path.is_file() or not json_path.is_file():
        pytest.skip("long-lane artifacts missing; run parser/json long tests first")

    parser = json.loads(parser_path.read_text(encoding="utf-8"))
    json_run = json.loads(json_path.read_text(encoding="utf-8"))
    total_elapsed = float(parser["elapsed_sec"]) + float(json_run["elapsed_sec"])

    parser_crashes = _crash_files(_PARSER_CRASHES)
    json_crashes = _crash_files(_JSON_CRASHES)

    findings_lines: list[str] = []
    if not parser_crashes and not json_crashes:
        findings_lines.append("None. No uncaught exceptions, hangs, or memory faults observed.")
    else:
        for label, paths in (("parser", parser_crashes), ("json_ingestion", json_crashes)):
            for p in paths:
                # Severity default CRASH until human re-triage; wrong-number /
                # corruption need semantic analysis beyond the harness.
                rel = p.relative_to(_REPO).as_posix()
                findings_lines.append(
                    f"- **CRASH** (`{label}`): `{rel}` "
                    f"({p.stat().st_size} bytes). Uncaught fault under atheris; "
                    "fix out of scope for #170 unless trivial with a failing unit test."
                )

    p_stats = parser.get("stats") if isinstance(parser.get("stats"), dict) else {}
    j_stats = json_run.get("stats") if isinstance(json_run.get("stats"), dict) else {}
    p_exec = p_stats.get("executions", "n/a")
    j_exec = j_stats.get("executions", "n/a")
    p_wall = float(parser["elapsed_sec"])
    j_wall = float(json_run["elapsed_sec"])
    p_budget = int(parser["max_total_time_sec"])
    j_budget = int(json_run["max_total_time_sec"])
    p_corp = parser["corpus_files"]
    j_corp = json_run["corpus_files"]
    p_crash = int(parser["crash_count"])
    j_crash = int(json_run["crash_count"])
    total_budget = p_budget + j_budget
    total_crash = p_crash + j_crash
    minutes = total_elapsed / 60.0
    findings_block = "\n".join(findings_lines)

    lines = [
        "# Fuzzing report (#170)",
        "",
        "Parent: assurance-pass spec (#160). Sibling mutation: #166 / `mutation-report.md`.",
        "",
        "Container-side **atheris 3.1.0** (`requirements-assurance-container.txt`) coverage-guided",
        "fuzzing of the SKILL.md parser and the extractor JSON ingestion models. Host/Windows",
        "is out of scope; targets import-guard via skip when atheris is absent.",
        "",
        "## How to reproduce",
        "",
        "```bash",
        "pip install -r requirements-ci.txt -r requirements-assurance-container.txt",
        "pip install -e .",
        "",
        "# Half-hour per target (one hour total). Artifacts under fuzz/artifacts/.",
        "FUZZ_MAX_TOTAL_TIME_SEC=1800 pytest -q -m assurance tests/test_fuzz_170.py --tb=short",
        "",
        "# Or invoke libFuzzer entry points directly:",
        "python fuzz/parser_target.py -max_total_time=1800 \\",
        "    -artifact_prefix=fuzz/crashes/parser/ fuzz/corpus/parser",
        "python fuzz/json_ingestion_target.py -max_total_time=1800 \\",
        "    -artifact_prefix=fuzz/crashes/json/ fuzz/corpus/json",
        "```",
        "",
        "## Targets",
        "",
        "| # | Target | Entry | Surface under test |",
        "|---|--------|-------|--------------------|",
        "| 1 | parser | `fuzz/parser_target.py` | `parse_skill_file` on arbitrary bytes |",
        "| 2 | json_ingestion | `fuzz/json_ingestion_target.py` | "
        "extraction-output pydantic models |",
        "",
        "Expected-error paths (`MalformedSkillError`, pydantic `ValidationError`,",
        "`json.JSONDecodeError`, and related type errors) are **not** crashes.",
        "",
        "## Run statistics",
        "",
        "| Target | Wall (s) | Budget (s) | Executions | Corpus | Crashes |",
        "|--------|---------:|-----------:|-----------:|-------:|--------:|",
        f"| parser | {p_wall:.1f} | {p_budget} | {p_exec} | {p_corp} | {p_crash} |",
        f"| json_ingestion | {j_wall:.1f} | {j_budget} | {j_exec} | {j_corp} | {j_crash} |",
        f"| **total** | **{total_elapsed:.1f}** | **{total_budget}** | | | **{total_crash}** |",
        "",
        f"Total fuzz wall time: **{minutes:.1f} minutes** "
        "(acceptance floor: ≥ 60 minutes at default budget).",
        "",
        "## Severity vocabulary",
        "",
        "| Rank | Severity | Meaning |",
        "|-----:|----------|---------|",
        "| 1 | WRONG_NUMBER | Silent wrong numeric / identity result |",
        "| 2 | CORRUPTION | Provenance or body corrupted without refusal |",
        "| 3 | CRASH | Uncaught exception, hang, or memory fault |",
        "| 4 | HYGIENE | Noise / non-load-bearing fault |",
        "",
        "## Findings",
        "",
        findings_block,
        "",
        "## Artifacts",
        "",
        "| Path | Role |",
        "|------|------|",
        "| `fuzz/corpus/parser/` | Parser seed + evolved corpus |",
        "| `fuzz/corpus/json/` | JSON seed + evolved corpus |",
        "| `fuzz/crashes/parser/` | Parser crashing inputs (if any) |",
        "| `fuzz/crashes/json/` | JSON crashing inputs (if any) |",
        "| `fuzz/artifacts/parser_run.json` | Machine-readable parser run stats |",
        "| `fuzz/artifacts/json_run.json` | Machine-readable JSON run stats |",
        "",
        "## Default suite / CI matrix",
        "",
        '- Harness directory `fuzz/` is **outside** `testpaths = ["tests"]`.',
        "- Long tests carry `@pytest.mark.assurance` and are deselected by",
        '  `pytest -m "not live and not calibration and not assurance"`.',
        "- Without atheris, assurance tests `pytest.skip` cleanly (Windows / host).",
        "- Long lane workflow: `.github/workflows/assurance.yml` (`workflow_dispatch` only).",
        "",
    ]
    _REPORT.write_text("\n".join(lines), encoding="utf-8")
    assert _REPORT.is_file()
    text = _REPORT.read_text(encoding="utf-8")
    assert "Executions" in text
    assert "corpus" in text.lower()
    assert "crash" in text.lower()
    if float(parser["max_total_time_sec"]) >= _DEFAULT_PER_TARGET_SEC:
        assert total_elapsed >= 3600 * 0.9
