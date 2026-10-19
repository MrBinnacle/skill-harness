# Fuzzing report (#170)

Parent: assurance-pass spec (#160). Sibling mutation: #166 / `mutation-report.md`.

Container-side **atheris 3.1.0** (`requirements-assurance-container.txt`) fuzzing of the
SKILL.md parser and the extractor JSON ingestion models. The parser target is
coverage-guided; the JSON target is not guided over the surface it names — see
[Coverage feedback](#coverage-feedback) before reading its execution count as reach.
Host/Windows is out of scope; targets import-guard via skip when atheris is absent.

## How to reproduce

```bash
pip install -r requirements-ci.txt -r requirements-assurance-container.txt
pip install -e .

# Half-hour per target (one hour total). Artifacts under fuzz/artifacts/.
FUZZ_MAX_TOTAL_TIME_SEC=1800 pytest -q -m assurance tests/test_fuzz_170.py --tb=short

# Or invoke libFuzzer entry points directly:
python fuzz/parser_target.py -max_total_time=1800 \
    -artifact_prefix=fuzz/crashes/parser/ fuzz/corpus/parser
python fuzz/json_ingestion_target.py -max_total_time=1800 \
    -artifact_prefix=fuzz/crashes/json/ fuzz/corpus/json
```

## Targets

| # | Target | Entry | Surface under test |
|---|--------|-------|--------------------|
| 1 | parser | `fuzz/parser_target.py` | `parse_skill_file` on arbitrary bytes |
| 2 | json_ingestion | `fuzz/json_ingestion_target.py` | extraction-output pydantic models |

Expected-error paths (`MalformedSkillError`, pydantic `ValidationError`,
`json.JSONDecodeError`, and related type errors) are **not** crashes.

## Run statistics

| Target | Wall (s) | Budget (s) | Executions | Crashes |
|--------|---------:|-----------:|-----------:|--------:|
| parser | 1802.6 | 1800 | 10375786 | 0 |
| json_ingestion | 1803.6 | 1800 | 140340401 | 0 |
| **total** | **3606.2** | **3600** | | **0** |

Total fuzz wall time: **60.1 minutes** (acceptance floor: ≥ 60 minutes at default budget).

## Coverage feedback

libFuzzer's own final counters, parsed from each run's recorded summary line
(`fuzz/artifacts/*.json` → `stats`). **Live corpus** is the unit count the run
finished with; **corpus files** is the file count left on disk, which is larger
because superseded (`REDUCE`d) units are not deleted. The corpus size of record is
the live unit count.

| Target | Edges (`cov`) | Features (`ft`) | Live corpus (units) | Corpus files |
|--------|--------------:|----------------:|--------------------:|-------------:|
| parser | 14 | 42 | 20 | 167 |
| json_ingestion | 14 | 18 | 5 | 165 |

The parser target is genuinely coverage-guided: `parse_skill_file` and
`MalformedSkillError` are imported under `atheris.instrument_imports`, so the
parser's own branches drive the search.

The JSON target is **not** guided over the validation surface it names.
`model_validate` / `model_validate_json` execute inside `pydantic_core`, a compiled
Rust extension that atheris's bytecode instrumentation cannot see, so the only
feedback reaching the mutator comes from the Python-level code around it
(`instrument_from_mapping` plus the target's own branching). That is why `cov` and
the live corpus do not move across the run: past the opening seconds this target is
high-throughput random-input testing, not a coverage-guided search. It still drives
real bytes through the ingestion path and would still surface an uncaught fault; it
does not support a coverage claim over the models.

## Severity vocabulary

| Rank | Severity | Meaning |
|-----:|----------|---------|
| 1 | WRONG_NUMBER | Silent wrong numeric / identity result |
| 2 | CORRUPTION | Provenance or body corrupted without refusal |
| 3 | CRASH | Uncaught exception, hang, or memory fault |
| 4 | HYGIENE | Noise / non-load-bearing fault |

## Findings

None. No uncaught exceptions, hangs, or memory faults observed.

## Artifacts

| Path | Role |
|------|------|
| `fuzz/corpus/parser/` | Parser seed + evolved corpus |
| `fuzz/corpus/json/` | JSON seed + evolved corpus |
| `fuzz/crashes/parser/` | Parser crashing inputs (if any) |
| `fuzz/crashes/json/` | JSON crashing inputs (if any) |
| `fuzz/artifacts/parser_run.json` | Machine-readable parser run stats |
| `fuzz/artifacts/json_run.json` | Machine-readable JSON run stats |

## Default suite / CI matrix

- Harness directory `fuzz/` is **outside** `testpaths = ["tests"]`.
- Long tests carry `@pytest.mark.assurance` and are deselected by
  `pytest -m "not live and not calibration and not assurance"`.
- Without atheris, assurance tests `pytest.skip` cleanly (Windows / host).
- Long lane workflow: `.github/workflows/assurance.yml` (`workflow_dispatch` only).
