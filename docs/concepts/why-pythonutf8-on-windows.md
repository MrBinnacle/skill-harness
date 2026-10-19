# Why PYTHONUTF8=1 and PYTHONHASHSEED=0 are required on Windows

## PYTHONUTF8=1

Windows uses cp1252 as the default console codepage. The Rich library (used for terminal
output by the harness) emits Unicode characters — including box-drawing characters for
tables and warning symbols like U+26A0. When Python's stdout is bound to a cp1252
terminal, any character outside the cp1252 range raises:

```
UnicodeEncodeError: 'charmap' codec can't encode character '⚠' in position N:
character maps to <undefined>
```

Setting `PYTHONUTF8=1` switches Python to UTF-8 mode for all I/O, which resolves
this. This was observed during the dogfooding run on 2026-06-07
(`docs/dogfooding-ai-slop-sentinel-2026-06-07.md`, gotcha 1 — internal
record, not published; citation retained as a provenance marker).

```powershell
$env:PYTHONUTF8 = "1"
```

## PYTHONHASHSEED=0

Python randomizes hash seeds across interpreter invocations by default. This affects
dictionary iteration order, which flows into JSON serialization. Without a fixed seed,
the JSON output of `run evaluate-skill --format=json` is not byte-stable across
re-runs on the same evidence — the keys may be sorted differently in nested structures
that pass through dict intermediaries.

Setting `PYTHONHASHSEED=0` pins the hash seed to zero, making JSON output
deterministic. This matters for:

- Reproducibility: the case study claims byte-stable JSON output. That claim holds
  only when `PYTHONHASHSEED=0`.
- CI: diffing output across runs requires stable serialization.
- Developers: test fixtures that compare JSON bytes fail non-deterministically without
  a fixed seed.

```powershell
$env:PYTHONHASHSEED = "0"
```

## Setting both together

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONHASHSEED = "0"
$env:PYTHONPATH = "src"
$py = ".venv\Scripts\python.exe"
```

## Further reading

The `windows-claude-code-env` skill (at `~/.claude/skills/windows-claude-code-env/`)
documents the full set of Windows-specific traps for Python development in this
environment, including cp1252 mojibake detection, CRLF/LF line-ending issues, and
PowerShell here-string gotchas.
