"""Atheris fuzz harness pins for #170.

The long runs live under ``@pytest.mark.assurance`` and are excluded from the
default CI matrix cell. Environments without atheris (Windows, host machines
without ``requirements-assurance-container.txt``) skip cleanly.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any, TypedDict, cast

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
# Overridable for local smoke (FUZZ_MAX_TOTAL_TIME_SEC). A below-default budget
# writes its report and stats to tmp, never over the checked-in receipts: the AC
# floor is what makes those receipts evidence.
_DEFAULT_PER_TARGET_SEC = 30 * 60


class _RunPayload(TypedDict):
    target: str
    max_total_time_sec: int
    elapsed_sec: float
    returncode: int | None
    crash_count: int
    corpus_files: int
    stats: dict[str, Any]
    stderr_tail: str
    stdout_tail: str


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


_SHA1_NAME_RE = re.compile(r"^[0-9a-f]{40}$")
_CRASH_NAME_RE = re.compile(r"^(?:crash|leak|timeout|oom|slow-unit)-([0-9a-f]{40})$")


def _misnamed_artifacts(directory: Path) -> list[str]:
    """libFuzzer-named files in ``directory`` whose bytes no longer match the name.

    libFuzzer names a new corpus unit after the SHA-1 of its content, and a crash
    reproducer ``<kind>-<sha1>``, so the file name IS a checksum of the artifact.
    Hand-written seeds are not sha1-named and are not claimed by that convention.
    """
    out: list[str] = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        crash = _CRASH_NAME_RE.match(path.name)
        if crash is None and not _SHA1_NAME_RE.match(path.name):
            continue
        expected = crash.group(1) if crash else path.name
        actual = hashlib.sha1(path.read_bytes()).hexdigest()
        if actual != expected:
            out.append(f"{path.as_posix()} holds the bytes of {actual}")
    return out


def test_corpus_units_match_their_libfuzzer_names() -> None:
    """Every evolved corpus unit is still the bytes libFuzzer named it after.

    The artifact half of the ticket ("keep the corpus and any crashing inputs as
    artifacts"). Whitespace/eol normalisation rewrites these files silently —
    pre-commit's end-of-file-fixer and trailing-whitespace did rewrite 124 of them
    before they were excluded, and git's own ``* text=auto eol=lf`` would — and a
    rewritten unit is no longer the input the run found.
    """
    mismatched = _misnamed_artifacts(_PARSER_CORPUS) + _misnamed_artifacts(_JSON_CORPUS)
    assert not mismatched, "corpus units rewritten since the run:\n" + "\n".join(mismatched)


def test_crash_reproducers_match_their_libfuzzer_names() -> None:
    """The same guard over crash inputs, where a rewritten byte loses the repro.

    AC3 pairs a severity with "its input artifact"; that pairing is only worth
    anything while the artifact still reproduces.
    """
    mismatched = _misnamed_artifacts(_PARSER_CRASHES) + _misnamed_artifacts(_JSON_CRASHES)
    assert not mismatched, "crash inputs rewritten since the run:\n" + "\n".join(mismatched)


def test_artifact_name_guard_fires_on_a_rewritten_unit(tmp_path: Path) -> None:
    """Positive control: the two guards above must not pass by being vacuous.

    ``fuzz/crashes/`` is empty after a clean run, so its guard is only evidence if
    the check is shown to fire. One appended newline — exactly what
    end-of-file-fixer does — has to be enough to trip it, while a hand-written
    seed must stay exempt.
    """
    body = b"---\nname: x\n"
    digest = hashlib.sha1(body).hexdigest()
    unit = tmp_path / digest
    unit.write_bytes(body)
    assert _misnamed_artifacts(tmp_path) == []

    unit.write_bytes(body + b"\n")
    assert len(_misnamed_artifacts(tmp_path)) == 1

    (tmp_path / "seed_handwritten.md").write_bytes(b"not sha1-named\n")
    assert len(_misnamed_artifacts(tmp_path)) == 1

    (tmp_path / f"crash-{digest}").write_bytes(body.replace(b"\n", b"\r\n"))
    assert len(_misnamed_artifacts(tmp_path)) == 2


def test_fuzz_dir_outside_default_pytest_collection() -> None:
    """Harness lives outside every configured testpath, so default collection skips it."""
    config = tomllib.loads((_REPO / "pyproject.toml").read_text(encoding="utf-8"))
    testpaths = config["tool"]["pytest"]["ini_options"]["testpaths"]
    assert testpaths, "pyproject must pin testpaths for this guard to mean anything"
    for entry in testpaths:
        root = (_REPO / entry).resolve()
        assert root.is_dir(), entry
        assert not _FUZZ.is_relative_to(root), f"fuzz/ must not sit under testpath {entry}"


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


def _scratch_corpus(seeded_from: Path, tmp_path: Path, pattern: str = "seed_*") -> Path:
    """A throwaway copy of a corpus directory.

    Nothing below the ≥1h floor may point libFuzzer at the checked-in corpus: it
    writes newly-interesting units into whatever directory it is given, and
    replaces units it can shrink, so a smoke run would otherwise leave tracked
    evidence modified for the next commit to pick up.
    """
    scratch = tmp_path / seeded_from.name
    scratch.mkdir()
    for seed in sorted(seeded_from.glob(pattern)):
        (scratch / seed.name).write_bytes(seed.read_bytes())
    return scratch


def _dir_fingerprint(directory: Path) -> dict[str, tuple[int, int]]:
    """Name -> (size, mtime_ns) for every file in ``directory``."""
    if not directory.is_dir():
        return {}
    return {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in directory.iterdir()}


def test_fuzz_parser_smoke_skips_or_runs(tmp_path: Path) -> None:
    """A few thousand runs through the parser target; skip if no atheris."""
    _require_atheris()
    tracked_before = _dir_fingerprint(_PARSER_CORPUS)
    scratch = _scratch_corpus(_PARSER_CORPUS, tmp_path)
    seeded = len(_dir_fingerprint(scratch))
    result = _run_target(
        _PARSER_TARGET,
        scratch,
        tmp_path / "crashes",
        max_total_time=5,
        runs=2000,
    )
    combined = result.stderr + result.stdout
    assert "Done " in combined or "DONE" in combined or "INITED" in combined, combined[-1500:]
    # Clean budget exhaustion is 0; a found crash is non-zero — both mean the harness ran.
    assert result.returncode is not None
    # libFuzzer writes newly-interesting units into whatever corpus directory it is
    # handed — demonstrated by the scratch copy growing in this very run. The default
    # lane must therefore never be handed the checked-in corpus.
    assert len(_dir_fingerprint(scratch)) > seeded
    assert _dir_fingerprint(_PARSER_CORPUS) == tracked_before


def test_fuzz_json_smoke_skips_or_runs(tmp_path: Path) -> None:
    """A few thousand runs through the JSON ingestion target; skip if no atheris."""
    _require_atheris()
    tracked_before = _dir_fingerprint(_JSON_CORPUS)
    scratch = _scratch_corpus(_JSON_CORPUS, tmp_path)
    seeded = len(_dir_fingerprint(scratch))
    result = _run_target(
        _JSON_TARGET,
        scratch,
        tmp_path / "crashes",
        max_total_time=5,
        runs=2000,
    )
    combined = result.stderr + result.stdout
    assert "Done " in combined or "DONE" in combined or "INITED" in combined, combined[-1500:]
    assert result.returncode is not None
    assert len(_dir_fingerprint(scratch)) > seeded
    assert _dir_fingerprint(_JSON_CORPUS) == tracked_before


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


def _write_stats(name: str, payload: dict[str, object], into: Path) -> Path:
    into.mkdir(parents=True, exist_ok=True)
    path = into / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _parse_libfuzzer_stats(stderr: str) -> dict[str, int | str]:
    """Extract libFuzzer's own final counters from a run's stderr/stdout.

    ``cov`` / ``features`` / ``corpus_size`` are read from the LAST line that
    carries them (the ``DONE`` line), because those are the counters the run
    finished with. ``corpus_size`` is libFuzzer's live unit count, which is not
    the file count left on disk: superseded ``REDUCE`` units stay as files.
    """
    out: dict[str, int | str] = {}
    done = re.search(r"Done\s+(\d+)\s+runs", stderr)
    if done:
        out["executions"] = int(done.group(1))
    else:
        pulses = re.findall(r"#(\d+)", stderr)
        if pulses:
            out["executions"] = int(pulses[-1])
    for key, pat in (
        ("cov", r"cov:\s*(\d+)"),
        ("features", r"ft:\s*(\d+)"),
        ("corpus_size", r"corp:\s*(\d+)"),
    ):
        found = re.findall(pat, stderr)
        if found:
            out[key] = int(found[-1])
    out["raw_tail"] = stderr[-2000:] if stderr else ""
    return out


def _run_one_target(
    name: str,
    target: Path,
    corpus: Path,
    crashes: Path,
    budget: int,
    *,
    artifact_stem: str,
    artifacts_dir: Path,
) -> _RunPayload:
    t0 = time.monotonic()
    result = _run_target(target, corpus, crashes, max_total_time=budget)
    elapsed = time.monotonic() - t0
    stats = _parse_libfuzzer_stats(result.stderr + result.stdout)
    payload: _RunPayload = {
        "target": name,
        "max_total_time_sec": budget,
        "elapsed_sec": elapsed,
        "returncode": result.returncode,
        "crash_count": len(_crash_files(crashes)),
        "corpus_files": len(list(corpus.iterdir())),
        "stats": cast(dict[str, Any], stats),
        "stderr_tail": (result.stderr or "")[-4000:],
        "stdout_tail": (result.stdout or "")[-1000:],
    }
    _write_stats(artifact_stem, cast(dict[str, object], payload), artifacts_dir)
    return payload


def _rel(path: Path) -> str:
    """Repo-relative path when possible; the raw path otherwise.

    ``-artifact_prefix`` is a caller-supplied directory. An hour of fuzz must not
    be lost to a ``ValueError`` in the report writer because a crash landed
    outside the repo.
    """
    try:
        return path.relative_to(_REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _findings_block(parser_crashes: list[Path], json_crashes: list[Path]) -> str:
    """Triage lines: one severity-tagged entry per crashing input artifact (AC3)."""
    if not parser_crashes and not json_crashes:
        return "None. No uncaught exceptions, hangs, or memory faults observed."
    lines: list[str] = []
    for label, paths in (("parser", parser_crashes), ("json_ingestion", json_crashes)):
        for p in paths:
            lines.append(
                f"- **CRASH** (`{label}`): `{_rel(p)}` "
                f"({p.stat().st_size} bytes). Uncaught fault under atheris; "
                "fix out of scope for #170 unless trivial with a failing unit test."
            )
    return "\n".join(lines)


def _render_fuzz_report(
    parser: _RunPayload,
    json_run: _RunPayload,
    parser_crashes: list[Path],
    json_crashes: list[Path],
) -> str:
    """Render docs/assurance/fuzz-report.md from two run payloads.

    Pure function of its arguments: the checked-in report is re-derivable from the
    checked-in artifacts, and ``test_fuzz_report_matches_checked_in_artifacts``
    holds it to that.
    """
    total_elapsed = parser["elapsed_sec"] + json_run["elapsed_sec"]

    p_stats = parser["stats"]
    j_stats = json_run["stats"]
    p_exec = p_stats.get("executions", "n/a")
    j_exec = j_stats.get("executions", "n/a")
    p_wall = parser["elapsed_sec"]
    j_wall = json_run["elapsed_sec"]
    p_budget = parser["max_total_time_sec"]
    j_budget = json_run["max_total_time_sec"]
    p_crash = parser["crash_count"]
    j_crash = json_run["crash_count"]
    total_budget = p_budget + j_budget
    total_crash = p_crash + j_crash
    minutes = total_elapsed / 60.0
    findings_block = _findings_block(parser_crashes, json_crashes)

    def cov_row(name: str, payload: _RunPayload) -> str:
        stats = payload["stats"]
        return (
            f"| {name} | {stats.get('cov', 'n/a')} | {stats.get('features', 'n/a')} "
            f"| {stats.get('corpus_size', 'n/a')} | {payload['corpus_files']} |"
        )

    lines = [
        "# Fuzzing report (#170)",
        "",
        "Parent: assurance-pass spec (#160). Sibling mutation: #166 / `mutation-report.md`.",
        "",
        "Container-side **atheris 3.1.0** (`requirements-assurance-container.txt`) fuzzing of the",
        "SKILL.md parser and the extractor JSON ingestion models. The parser target is",
        "coverage-guided; the JSON target is not guided over the surface it names — see",
        "[Coverage feedback](#coverage-feedback) before reading its execution count as reach.",
        "Host/Windows is out of scope; targets import-guard via skip when atheris is absent.",
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
        "| Target | Wall (s) | Budget (s) | Executions | Crashes |",
        "|--------|---------:|-----------:|-----------:|--------:|",
        f"| parser | {p_wall:.1f} | {p_budget} | {p_exec} | {p_crash} |",
        f"| json_ingestion | {j_wall:.1f} | {j_budget} | {j_exec} | {j_crash} |",
        f"| **total** | **{total_elapsed:.1f}** | **{total_budget}** | | **{total_crash}** |",
        "",
        f"Total fuzz wall time: **{minutes:.1f} minutes** "
        "(acceptance floor: ≥ 60 minutes at default budget).",
        "",
        "## Coverage feedback",
        "",
        "libFuzzer's own final counters, parsed from each run's recorded summary line",
        "(`fuzz/artifacts/*.json` → `stats`). **Live corpus** is the unit count the run",
        "finished with; **corpus files** is the file count left on disk, which is larger",
        "because superseded (`REDUCE`d) units are not deleted. The corpus size of record is",
        "the live unit count.",
        "",
        "| Target | Edges (`cov`) | Features (`ft`) | Live corpus (units) | Corpus files |",
        "|--------|--------------:|----------------:|--------------------:|-------------:|",
        cov_row("parser", parser),
        cov_row("json_ingestion", json_run),
        "",
        "The parser target is genuinely coverage-guided: `parse_skill_file` and",
        "`MalformedSkillError` are imported under `atheris.instrument_imports`, so the",
        "parser's own branches drive the search.",
        "",
        "The JSON target is **not** guided over the validation surface it names.",
        "`model_validate` / `model_validate_json` execute inside `pydantic_core`, a compiled",
        "Rust extension that atheris's bytecode instrumentation cannot see, so the only",
        "feedback reaching the mutator comes from the Python-level code around it",
        "(`instrument_from_mapping` plus the target's own branching). That is why `cov` and",
        "the live corpus do not move across the run: past the opening seconds this target is",
        "high-throughput random-input testing, not a coverage-guided search. It still drives",
        "real bytes through the ingestion path and would still surface an uncaught fault; it",
        "does not support a coverage claim over the models.",
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
    return "\n".join(lines)


def _write_fuzz_report(
    parser: _RunPayload,
    json_run: _RunPayload,
    report: Path,
    parser_crashes: Path,
    json_crashes: Path,
) -> None:
    """Synthesize the fuzz report (+ triage any crash artifacts)."""
    report.write_text(
        _render_fuzz_report(
            parser,
            json_run,
            _crash_files(parser_crashes),
            _crash_files(json_crashes),
        ),
        encoding="utf-8",
    )


_MINUTES_RE = re.compile(r"Total fuzz wall time: \*\*([0-9.]+) minutes\*\*")


def _recorded_minutes(text: str) -> float:
    """Total fuzz minutes as stated by the report itself."""
    match = _MINUTES_RE.search(text)
    assert match is not None, "report must state 'Total fuzz wall time: **N minutes**'"
    return float(match.group(1))


def _load_run_payload(path: Path) -> _RunPayload:
    return cast(_RunPayload, json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.assurance
def test_fuzz_long_lane_one_hour(tmp_path: Path) -> None:
    """Run both atheris targets (30m each) and write the fuzz report.

    Single test so pytest-randomly cannot reorder the report ahead of the runs.

    Only a run that meets the ≥1h acceptance floor may touch the evidence of
    record. A reduced-budget local smoke (``FUZZ_MAX_TOTAL_TIME_SEC``) gets tmp
    copies of the report, the stats, the corpus and the crash directories:
    overriding the budget must not be able to replace an hour of recorded evidence
    with six seconds of it, nor leave the tracked corpus modified.
    """
    _require_atheris()
    budget = _per_target_seconds()
    full_budget = budget >= _DEFAULT_PER_TARGET_SEC
    artifacts_dir = _ARTIFACTS if full_budget else tmp_path
    report = _REPORT if full_budget else tmp_path / _REPORT.name
    if full_budget:
        parser_corpus, json_corpus = _PARSER_CORPUS, _JSON_CORPUS
        parser_crashes, json_crashes = _PARSER_CRASHES, _JSON_CRASHES
    else:
        parser_corpus = _scratch_corpus(_PARSER_CORPUS, tmp_path, "*")
        json_corpus = _scratch_corpus(_JSON_CORPUS, tmp_path, "*")
        parser_crashes = tmp_path / "crashes-parser"
        json_crashes = tmp_path / "crashes-json"
    parser = _run_one_target(
        "parser",
        _PARSER_TARGET,
        parser_corpus,
        parser_crashes,
        budget,
        artifact_stem="parser_run",
        artifacts_dir=artifacts_dir,
    )
    json_run = _run_one_target(
        "json_ingestion",
        _JSON_TARGET,
        json_corpus,
        json_crashes,
        budget,
        artifact_stem="json_run",
        artifacts_dir=artifacts_dir,
    )
    if full_budget:
        assert parser["elapsed_sec"] >= budget * 0.9
        assert json_run["elapsed_sec"] >= budget * 0.9
    _write_fuzz_report(parser, json_run, report, parser_crashes, json_crashes)
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "Executions" in text
    assert "corpus" in text.lower()
    assert "crash" in text.lower()
    if full_budget:
        assert _recorded_minutes(text) >= 60.0


def test_fuzz_report_checked_in_with_stats() -> None:
    """Default-lane pin: the report exists and records run statistics."""
    assert _REPORT.is_file(), "docs/assurance/fuzz-report.md must be checked in"
    text = _REPORT.read_text(encoding="utf-8")
    assert "Executions" in text
    assert "Live corpus" in text
    assert "Crashes" in text
    assert "atheris" in text.lower()
    # At least one hour of recorded wall time in the committed report (AC: >=1h).
    # Read as a number, never as substring presence: the surrounding sentence is
    # emitted unconditionally by the template and so cannot witness the hour.
    assert _recorded_minutes(text) >= 60.0


_LIBFUZZER_DONE_RE = re.compile(r"Done\s+(\d+)\s+runs\s+in\s+(\d+)\s+second\(s\)")


def test_recorded_hour_agrees_with_libfuzzers_own_summary() -> None:
    """AC (≥1h of fuzz), read off libFuzzer's summary instead of off our own.

    ``elapsed_sec`` and ``stats.executions`` are figures this harness wrote; the
    ``Done N runs in M second(s)`` line is libFuzzer's, kept verbatim in the same
    artifact. Holding one to the other means the acceptance floor cannot be met by
    editing the harness's numbers into the record — only by running the fuzzer.
    """
    fuzzer_seconds = 0
    for stem in ("parser_run", "json_run"):
        payload = _load_run_payload(_ARTIFACTS / f"{stem}.json")
        recorded = f"{payload['stats'].get('raw_tail', '')}{payload['stderr_tail']}"
        match = _LIBFUZZER_DONE_RE.search(recorded)
        assert match is not None, f"{stem}: no libFuzzer 'Done N runs in M second(s)' line"
        runs, seconds = int(match.group(1)), int(match.group(2))
        assert runs == payload["stats"]["executions"], f"{stem}: executions disagree with libFuzzer"
        # The subprocess wall clock brackets libFuzzer's own: never shorter than
        # the fuzzing it reports, never inflated far past process startup.
        wall = payload["elapsed_sec"]
        assert seconds <= wall < seconds + 60, f"{stem}: wall clock {wall}s is not the run"
        fuzzer_seconds += seconds
    assert fuzzer_seconds >= 3600, f"libFuzzer reports {fuzzer_seconds}s of fuzz, floor is 3600s"


def test_fuzz_report_matches_checked_in_artifacts() -> None:
    """The report is re-derivable from the checked-in artifacts and crash inputs.

    Drift guard on the receipt: every number in the report has to come from a
    machine-readable run record in the tree, so the prose cannot claim an hour, a
    corpus size, or a crash count the artifacts do not carry.
    """
    parser = _load_run_payload(_ARTIFACTS / "parser_run.json")
    json_run = _load_run_payload(_ARTIFACTS / "json_run.json")
    rendered = _render_fuzz_report(
        parser,
        json_run,
        _crash_files(_PARSER_CRASHES),
        _crash_files(_JSON_CRASHES),
    )
    assert rendered == _REPORT.read_text(encoding="utf-8")
    # The corpus size of record is libFuzzer's live unit count, not the file count.
    assert parser["stats"]["corpus_size"] <= parser["corpus_files"]
    assert json_run["stats"]["corpus_size"] <= json_run["corpus_files"]
    # And the corpus the receipt counts is the one in the tree: a deleted unit must
    # not leave the recorded file count standing behind it.
    assert parser["corpus_files"] == len(list(_PARSER_CORPUS.iterdir()))
    assert json_run["corpus_files"] == len(list(_JSON_CORPUS.iterdir()))


def test_fuzz_report_triages_every_crash_with_severity_and_input(tmp_path: Path) -> None:
    """AC: every crash is triaged with a severity AND its input artifact."""
    parser = _load_run_payload(_ARTIFACTS / "parser_run.json")
    json_run = _load_run_payload(_ARTIFACTS / "json_run.json")
    parser_crash = tmp_path / "crash-abc123"
    parser_crash.write_bytes(b"---\n\x80")
    json_crash = tmp_path / "crash-def456"
    json_crash.write_bytes(b"{}{")

    rendered = _render_fuzz_report(parser, json_run, [parser_crash], [json_crash])

    findings = rendered.split("## Findings", 1)[1].split("## Artifacts", 1)[0]
    assert "No uncaught exceptions" not in findings
    for label, crash in (("parser", parser_crash), ("json_ingestion", json_crash)):
        assert f"**CRASH** (`{label}`)" in findings, findings
        assert crash.as_posix() in findings, findings
        assert f"({crash.stat().st_size} bytes)" in findings, findings


def test_fuzz_report_findings_say_none_only_when_no_crash_input_exists(tmp_path: Path) -> None:
    """The empty-findings line is reserved for a run with zero crash artifacts."""
    crash = tmp_path / "crash-000"
    crash.write_bytes(b"\x00")
    assert "None." in _findings_block([], [])
    assert "None." not in _findings_block([crash], [])
