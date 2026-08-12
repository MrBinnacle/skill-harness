# Fuzzing report (#170)

Parent: assurance-pass spec (#160). Sibling mutation: #166 / `mutation-report.md`.

Container-side **atheris 3.1.0** (`requirements-assurance-container.txt`) coverage-guided
fuzzing of the SKILL.md parser and the extractor JSON ingestion models. Host/Windows
is out of scope; targets import-guard via skip when atheris is absent.

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

| Target | Wall (s) | Budget (s) | Executions | Corpus | Crashes |
|--------|---------:|-----------:|-----------:|-------:|--------:|
| parser | 1802.6 | 1800 | 10375786 | 167 | 0 |
| json_ingestion | 1803.6 | 1800 | 140340401 | 165 | 0 |
| **total** | **3606.2** | **3600** | | | **0** |

Total fuzz wall time: **60.1 minutes** (acceptance floor: ≥ 60 minutes at default budget).

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
