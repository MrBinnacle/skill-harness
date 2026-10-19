# Docs map

Where to go depending on what you want:

**"I just have questions."** → [FAQ.md](FAQ.md) — the common ones: UNMEASURED, zero
measured KEEPs, KEEP vs CUT, why with-vs-without, running it in CI.

**"Convince me this matters."** Read the case studies:

- [The framework refusing to validate its own author's skill](case-studies/ai-slop-sentinel-under-ablation.md)
  — three halts before a contaminated result could ship. The deliverable is the chain of
  refusals, not a number.
- [The double ceiling](case-studies/double-ceiling-structurally-unmeasured.md) — a frontier
  agent passed 14/14 runs *without* the skill; on that task class there is nothing for a skill
  to improve, and honest measurement says so instead of inventing an effect.
- [Displaced enforcement](case-studies/displaced-enforcement-skill-ablation-blind-spot.md) — a
  scope boundary of skill-ablation itself: when a discipline's real firing lives in a *hook*,
  ablating the skill *text* measures the wrong layer, so a null there is not the discipline's
  verdict. Sibling to the double ceiling — that one is about the task class, this one about the
  skill class.

**"Why did my run say UNMEASURED?"** → [concepts/why-unmeasured.md](concepts/why-unmeasured.md)
— it means "couldn't be proven," not "went wrong." Short and worth reading once.

**"Why should I distrust the skill benchmarks I've seen?"** →
[findings/why-naive-skill-benchmarks-mislead.md](findings/why-naive-skill-benchmarks-mislead.md)
— the measured failure modes (noise, self-leaking oracles, cost-only test banks), each claim
carrying an evidence grade.

**"What exactly does the v0.2 screen measure?"** →
[findings/v0.2-preregistration.md](findings/v0.2-preregistration.md) — the measurement plan,
locked before data collection, plus the registered results of the sizing run. The entry gate
that forced the redesign: [findings/v0.2-reaim-gate.md](findings/v0.2-reaim-gate.md).

**"I want the full spec / I want to contribute."** → [PRD.md](PRD.md) (evidence model,
evidence admissibility rules, CLI surface) and [PLAN.md](PLAN.md) (build tracks; internal register),
plus [../CONTRIBUTING.md](../CONTRIBUTING.md).

**"I want to reproduce a result."** → [../examples/](../examples/) — step-by-step, with the
paid steps marked.

**"Why is the architecture shaped this way?"** → [adr/](adr/) — architectural decision
records. [ADR 0001](adr/0001-architecture-admitted-on-demonstrated-decision-requirement.md)
states the rule the others are judged against: a state, field, registry or distinction is
admitted only once a downstream decision is shown to require it. It also carries the three
decisions ratified under that rule, with their provenance marked.

Also here: [RELEASE-NOTES-v0.1.md](RELEASE-NOTES-v0.1.md) ·
[concepts/why-pythonutf8-on-windows.md](concepts/why-pythonutf8-on-windows.md) (Windows
terminal fix) · [`INVARIANTS.md`](INVARIANTS.md) (tracked pass-rule / evidence admissibility
invariants) · `supply-chain/` (per-dependency audit records).
