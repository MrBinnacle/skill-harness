# Supply-chain review — `inspect-ai` + `inspect-swe` (optional `[inspect]` extra)

**Date:** 2026-07-09 · **Scope:** light manual review (provenance, maintenance,
install-time behavior), per the repo rule that no ML dependency lands unreviewed.
Not a source audit.

## What is being added, and where it can act

Both packages power the OPTIONAL `[inspect]` extra only (the v0.2 agentic subject
layer). The default install (`pip install skill-harness`) does not pull them and has
no agent-execution surface. When installed, `inspect-swe` downloads and executes the
Claude Code agent **inside a Docker sandbox** it manages; host-side it drives the
Docker API and bridges model calls.

## Provenance and maintenance

- `inspect-ai` — UK AI Security Institute (`UKGovernmentBEIS/inspect_ai`):
  institutional maintainer, ~2.3k stars, 6k+ commits, 200+ releases, active weekly.
  Reviewed version: 0.3.245.
- `inspect-swe` — same maintainer org (`meridianlabs-ai/inspect_swe` per PyPI
  metadata; the Inspect ecosystem's agent-adapter package), releasing in lockstep
  with inspect-ai. Reviewed version: 0.2.65. Pace is fast (60+ releases in months) —
  pin exact versions in the HarnessPin per trial; a version bump between arms is
  inadmissible anyway.

## Install-time behavior

Pure-Python wheels; no compiled postinstall hooks observed on install into a clean
venv (2026-07-09, Windows). Transitive surface is large (httpx, docker, textual,
etc.) — accepted for an opt-in research extra; NOT accepted into base dependencies.

## Residual risk and mitigations

- Agent binaries are fetched at run time by `inspect_swe` (versioned): mitigated by
  `claude_code(version=<exact>)` — `HarnessPin.capture()` refuses `"auto"`.
- Sandbox = Docker container, network-enabled by default: acceptable for the tracer;
  network-restricted sandbox configs are a pre-registration option for sized runs.
- Verdict: **ACCEPT as optional extra**; re-review if either package is promoted to a
  base dependency or starts executing agents outside a sandbox.
