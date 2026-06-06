# Skill Harness — Competitive Landscape & Buildability Report

**Prepared for:** feasibility + GTM SMEs
**Date:** 2026-06-06
**Synthesis basis:** research fleet (16 tool verdicts, 5 academic angles, 4 market angles, 5 build analyses, 3 adversarial twin-hunts) — 34 agents, ~1.6M tokens
**Convention:** **CONFIRMED** = grounded in a primary source or directly inspected repo/source file. **INFERENCE** = synthesis judgment. **STALE-RISK** = field moves monthly; flagged where load-bearing.

---

## 1. Twin Verdict — NO TRUE TWIN (high confidence)

The defining test: a competitor is a true twin only if it does **P1 (clause-level differential ablation)** AND at least one of **P2 (directional-only pairwise verdicts)** or **P3 (admissibility-gated tiered oracles)**. **Nothing in the searched corpus passes.**

**Why this is high-confidence, not hopeful:** three *independent* adversarial twin-hunts each went in assuming a twin existed, searched 8+ varied angles (academic arXiv, the Agent-Skills eval ecosystem, OSS tooling, obscure GitHub, falsifiability-specific queries), and *all three returned `found_twin=false`*. They converged on the same structural finding: **the field has every ingredient scattered across separate projects, but no system fuses them.**

The three best candidates and why each fails (CONFIRMED via the cited sources):

| Candidate | Has | Fails | Verdict |
|---|---|---|---|
| **Scylla** (arXiv:2602.08765) — ablates a real CLAUDE.md into blocks B01-B18 | Same product category; ablation *shape* | **Inverts P1** (additive T0-T6 tiering from empty baseline, not leave-one-out removal); multi-judge holistic rubric/consensus scoring (violates P2); no P3/P4; primary metric is Cost-of-Pass (efficiency, not contribution) | Same-category *cousin*, shares the word "ablation," inverts both the direction and the verdict philosophy |
| **AttriBoT** (ICLR 2025) | **Genuine P1 mechanism** (true single-span leave-one-out) | Delta is a *likelihood/saliency score* on arbitrary context spans, not a directional verdict on a named axis from a decomposed contract; no P2/P3/P4 | Strongest P1-mechanism match; an **academic anti-twin** (P1 and neither P2 nor P3) |
| **Shapley/regression prompt-component papers** (2312.15395, 2603.26830) | Decompose prompts, measure marginal contribution | Produce scalar values/coefficients, not directional deltas; no P2/P3/P4 | P1-partial only |

**The single most decisive negative (CONFIRMED):** the P4 evidentiary signature — *"no admissible evidence ⇒ no claim"*, *"vacuous clause"*, *write-time admissibility snapshot*, *append-only evidence* — returns **zero hits in the LLM-eval domain** (only unrelated formal-methods/smart-contract testing). This is the strongest evidence the *combination* is unoccupied.

**Residual risk (honest):** a sub-search-visibility stealth startup. The market cluster mitigates this independently — ~$1B+ funding flowed exclusively to output-quality eval, **$0 visibly to clause-level ablation** (§4).

---

## 2. Adjacent-Tool Map — closest, by primitive

The whole adjacency cluster touches **only P2's *shape*** (comparison) and never P2's *discipline* (single-axis attribution, calibration, tie-as-first-class). **No adjacent tool touches P1 or P4 in any real form.**

| Tool | Closest primitive | What it actually has | Funding / status |
|---|---|---|---|
| **promptfoo** | P2 (`select-best`) | N-way "pick the best," NOT pairwise {A,B,tie}; no position-swap; one assertion among ~50 absolute-scoring checks | **OpenAI-acquired Mar 2026**; OpenAI's official Evals-migration target |
| **DeepEval / Confident AI** | P2 (`ArenaGEval`) | "Blinded, randomized-position, n-pairwise" A-beats-B on a single named criterion — **closest tool to P2's position-swap discipline**; but whole-contestant, not Ablated_k | OSS + cloud |
| **LangSmith** | P2 | Genuine pairwise LLM-judge; cookbook **randomizes prediction order = real position-swap**; but pairwise is one optional evaluator, default is absolute scoring | LangChain $100M Series B @ ~$1.1-1.25B |
| **Anthropic skill-creator 2.0 / SkillsBench** | P1 (Full/Null *spine* only) | Whole-skill Full-vs-Null A/B; **no Ablated_k middle condition**; holistic 1-10 rubric (`comparator.md` `overall_score`) | **First-party; the commoditization vector** |
| **Inspect AI** (UK AISI) | P3 (oracle layer, ungated) | Strongest **build substrate**; append-only edit-log echoes P4 (post-hoc, not write-time gate); `model_graded_qa` ungated | Open-source (gov) |
| **Braintrust** | P2 (`Battle` scorer) | Pairwise A-vs-B but **scores not gates**, no position-swap, compares vs `expected` | $80M Series B @ $800M (Feb 2026) |
| **Patronus / Glider** | (instrument) | The Tier-2 judge the Harness treats as *inadmissible without calibration* | Component-to-framework, not competitor |

Also adjacent, shallower: OpenAI Evals (`battle.yaml`), HELM Instruct (rater-accuracy screening ≈ weak P3), Ragas/Langfuse/Arize Phoenix/W&B Weave/TruLens (observability + absolute quality scoring). DSPy & OpenAI Prompt Optimizer are **inverted** — they *optimize toward* a scalar metric; the Harness *attributes and gates* and refuses scalar metrics.

---

## 3. Build Blueprint

**Verdict: buildable to a credible v0.1, and this repo is already ~60-70% there.** None of the four primitives requires unsolved research; the difficulty is that it is an **assembly no one has shipped**, so estimation is from-scratch, not from-a-fork.

### Reference architecture (6 deterministic-orchestrator-wired parts)
1. **Clause extractor** + falsifiability gate (vacuous-clause pruning). *(CONFIRMED present: `src/skill_harness/extractor/`.)*
2. **Ablation runner** — render Full / Ablated_k / Null per clause. **CONFIRMED ABSENT — critical-path gap** (`run ablation` in `cli/main.py:131` is a stub; no `ablation/` package).
3. **Tier-1 mechanical oracles**. *(CONFIRMED present: `oracles/tier1/` — verbosity, hedge_index, structure_score, compliance_proxy + versioned registry with `implementation_hash`.)*
4. **Tier-2 judge** — position-swapped pairwise {A,B,tie}, admissible only with calibrated `(judge_id, axis)` record at Cohen's κ > 0.7. *(CONFIRMED present: `oracles/tier2/judge.py` + `injection_guard.py` + `oracles/calibration/`.)*
5. **Append-only SQLite evidence** with write-time admissibility snapshot, dual-DB asymmetric durability. *(CONFIRMED present: `storage/` repositories, migrations 0001-0003 + 0200, append-only triggers.)*
6. **Bayesian aggregation** — Beta(1,1)→Beta(1+w,1+n−w), pass at P(win_rate>0.60)≥0.95. **CONFIRMED ABSENT — critical-path gap** (~20 lines `scipy.stats.beta`; no `aggregation/`/`bayes/`/`stats/` package).

### Smallest version that proves the primitive ("hello-world ablation")
One skill, 3-4 clauses, **one Tier-1 axis** (e.g. hedge-index for a "be decisive" clause), the 3-condition runner, position-swapped Full-vs-Ablated_k on that axis, append-only write, one Beta-Binomial pass/fail. **No judge needed** — Tier-1 alone proves P1+P2+P3+P4 end-to-end and sidesteps the calibration bottleneck. A few hundred LOC on top of what exists.

### Assemblable off-the-shelf vs net-new (CONFIRMED)
- **Assemblable (~20-30% effort saved):** Inspect AI or promptfoo for runner/model-plumbing/logging/sandbox; AlpacaEval's length-controlled GLM (arXiv:2404.04475, ships in `tatsu-lab/alpaca_eval`) for confound control; scipy for the posterior; Inspect's append-only edit-log *schema philosophy* (not its enforcement).
- **Net-new (the hard ~70%, irreducibly bespoke):** the differential-ablation control plane (no tool models "conditions compared against each other"), the directional-only verdict layer, the admissibility state machine, and the *write-time* admissibility snapshot that gates aggregation. **DSPy is the wrong tool for P1** — it optimizes toward a metric; ablation needs controlled single-clause removal holding everything fixed.

### THE genuine bottleneck (counterintuitive)
The build instinct fears the small-N statistics — but that is the **easiest** part (textbook conjugate Bayesian, already spec'd correctly). The **true bottleneck is reliable clause decomposition**: the *unit of measurement is itself non-deterministic to extract*, and 2026 literature directly undermines "just prompt an LLM" (no consistent granularity standard — humans AND LLMs disagree: Molecular Facts 2406.20079, Dissecting Atomic Facts 2509.01460; holistic rubric matches/beats self-decomposing atomic judges 2603.28005; decomposition degrades without granular aligned evidence 2602.10380). **The Harness already de-risks this** by requiring a *human-curated, frozen* clause set — converting an open-research problem into a one-time authoring cost. Consequence: the headline primitive's reproducibility is **bounded by the stability of the frozen clause inventory across skill revisions — a governance problem, not a compute one.**

### Effort (INFERENCE, grounded)
- Greenfield: **~3 months** to thin-but-honest v0.1 (manual clauses, 1-2 calibrated axes, Tier-1 + one judge axis); **~5 months** for auto-extraction + multiple calibrated axes.
- Team **~2.5 FTE**: senior eval/ML eng + backend/systems eng + 0.5 Bayesian statistician + part-time annotators. Sequencing is **gated, not parallel** (calibrate after pairwise harness runs; aggregate after write-time admissibility).
- **Given this repo's existing ~6k LOC** (storage complete, extractor + Tier-1/Tier-2 + calibration built), remaining critical path narrows to: ablation runner (~4-6 wks) + Bayesian aggregation (~2 wks) + first frozen clause set + wiring → plausibly a **4-8 week push** to the first end-to-end demo.
- Cost dominated by **senior-eng salary + human calibration labels**, NOT inference (hundreds-to-low-thousands $ at v0.1; paired-difference designs keep N-per-cell modest). Single biggest staffing risk: scarcity of people fluent in **both** rigorous Bayesian eval AND production systems engineering.

---

## 4. Defensibility

**The moat is methodology-discipline + a proprietary calibration/frozen-case corpus — NOT technology.**

**Commodity (replicable in a quarter, CONFIRMED published with reference impls):** P2 position-swap pairwise (Zheng 2306.05685; recipe in FutureAGI 2026), length-control (Dubois 2404.04475, ships in alpaca_eval), κ/gold-set calibration (Judge's Verdict 2510.09738), append-only audit ledgers (2601.20727; One-Eval 2603.09821), clause/component ablation *as a concept* (Shapley 2312.15395, llmSHAP 2511.01311), Beta-Binomial aggregation (textbook).

**Durable moat (ranked):**
1. **The frozen-regression + `(judge_id, axis)` calibration corpus** — append-only, accrues *only through operation*, uncloneable from a spec. Defensibility scales with operation-time. *Treat the corpus as the product; treat the code as replicable.*
2. **The integrated invariant set under an anti-quality-scoring posture** — replicating the *integration* is a quarter's work, but a competitor must first *believe* directional clause-ablation beats output-grading, and the field's center of gravity pulls the other way.
3. **The falsifiability/vacuity library** of constructed falsifying cases — craft, not algorithm.

**Commoditization risk (the key adversarial finding):** the threat is **first-party, but mis-aimed.** Anthropic shipped skill-creator 2.0 (Mar 2026) and Bloom (Dec 2025) — both free, inside the authoring loop. **CONFIRMED from reading the actual source** (`skill-creator/SKILL.md`, `comparator.md`): skill-creator does Full-vs-Null whole-skill A/B with a holistic 1-10 rubric; Bloom scores elicitation-rate ≥7/10. **Both are LLM-self-grading — the Harness's hard-forbidden anti-pattern.** Anthropic's roadmap ("skills that evaluate themselves") *structurally conflicts* with the Harness thesis. **Net: Anthropic is a category-validator, not a category-killer** — the more they invest, the more they validate the category while not competing for the Harness's actual job (an adversarial, falsifiable, third-party audit for a buyer who *distrusts the vendor's own optimizer*).

**The genuine kill-shot scenario (INFERENCE):** an incumbent who **owns the Agent Skills open standard** decides clause-attribution matters and bundles a free reference evaluator — *distribution*, not technology, crushes a standalone tool. **Watch items (STALE-RISK, monthly):** (a) Tessl (nearest commercial mover, ran 880 whole-skill on/off evals) pivoting to clause-attribution; (b) OpenAI's Promptfoo acquisition (Mar 2026) shipping pairwise as the default platform evaluator post-integration → P2 erosion (P1/P4 remain unaddressed).

---

## 5. Asymmetric Findings (outsized-value items)

### 5a. Thesis-UNDERMINING academic results (must be internalized)
The fleet's academic cluster delivered a **loud, convergent warning** on the headline primitive. This is the report's most important section for feasibility.

- **The headline method (P1 single-clause ablation = leave-one-out) is the *weakest member of its own method family* per published consensus.** ContextCite (NeurIPS 2024, 2409.00729) — the closest input-segment twin at the *exact granularity* — **deliberately rejects** one-at-a-time LOO, fitting a sparse linear surrogate over *random-subset* co-ablations because single removal cannot disentangle interacting sources. Shapley (2312.15395) exists precisely to fix LOO's additivity-axiom failure. **The product markets clause-ablation as its headline while the literature treats the exact method as the inferior estimator.**
- **XPrompt/JoPA (2405.20404) — the ONLY major paper in the Harness's exact substrate (prose, not internal neurons) — concludes per-component LOO is *invalid* under non-additivity.** Its doctor/patient case is a **silent false negative `FLAGGED_CONFOUNDED` structurally cannot catch**: two mutually-redundant clauses each show ~zero delta removed alone → the Harness marks them UNMEASURED despite being jointly load-bearing. The confound machinery defends against interaction that *moves other axes*; it is **blind to interaction that *cancels within* the target axis** (no contamination, only absence). **This under-credits defensively-redundant — i.e. well-engineered — skills.**
- **The ablation OPERATOR is an undocumented hole that swung measured importance 3-9x in the only paper that tested it.** Li & Janson "Optimal Ablation" (NeurIPS 2024, 2409.09951): naive deletion conflates the clause's contribution with prompt-coherence/length/format loss. **The repo has no documented ablation-operator policy (CONFIRMED: `run ablation` is a stub).**

**The mitigation already exists latent in the project, IF enforced.** CLAUDE.md mandates FLAGGED_CONFOUNDED on cross-axis delta and UNMEASURED on no-evidence — precisely the literature's prescribed guards. Three cheap, high-leverage moves convert a published anti-pattern into a defensible instrument:
1. **(Cheapest, highest-leverage)** Make the ablation operator an explicit, versioned decision — replace "delete the clause" with a principled neutral substitution (semantically-null placeholder of matched length).
2. **Add a paired/joint-ablation probe** for any clause returning UNMEASURED — remove pair {N,M}, compare to sum of singles — to distinguish "truly vacuous" from "redundant-and-load-bearing."
3. **Frame the LOO delta honestly** as the n=1 Shapley special case; document Contribution magnitude as a *lower-bound under redundancy*, not a fair-attribution guarantee. (A random-subset surrogate over clauses is a credible *upgrade path* that would *measure* under interactions instead of discarding confounded rows; full Shapley is O(m·2^m) — a documented-limitation call, not v0.1.)

### 5b. Thesis-VALIDATING academic results
The **judge-calibration stack (P2/P3/P4-judge) is mature, citable prior art** the Harness *composes* rather than invents: position-swap (Zheng 2306.05685; Shi 2406.07791; CalibraEval 2410.15393), length-control (Dubois 2404.04475), κ/agreement-gating + refusing-uncalibrated-judges (2510.09738, 2503.05965, 2508.18076, SIGIR-ICTIR 2025). Atomic mechanically-verifiable instruction units (IFEval 2311.07911, IFBench 2507.02833) validate the Tier-1 oracle + falsifiability gate. **This is a citation-defense asset, not a moat** — replicable in weeks; defensibility lives in the *system + corpus*.

### 5c. Roadmap / positioning signals
- **Anthropic first-party optimizes the OPPOSITE objective function** (§4) — structural conflict means category-validation, not competition.
- **OpenAI is *winding down* bespoke eval** (Evals + Agent Builder shut down 2026-11-30) and consolidating onto acquired Promptfoo — *not* building deeper proprietary skill-eval primitives. The P2-erosion watch is the Promptfoo-into-Frontier launch (STALE-RISK).
- **No analyst category yet exists** for skill/clause eval (no Gartner MQ / Forrester Wave); it is folded inside "LLM observability." Clause-level differential ablation is collectively uncontested as of mid-2026.

### 5d. Adjacent-market & demand signals
- **Demand-validation is genuinely ambiguous** (INFERENCE, important): ~$1B+ funded output-quality eval (Braintrust, LMArena $1.7B, Galileo, Patronus, LangChain), **$0 visibly to clause-ablation.** Either white space *or* unvalidated demand — **both readings are live; do not assume the favorable one.**
- **Skill security/supply-chain is the hot orthogonal lane** (Snyk audited 3,984 skills: 534 critical, 76 malicious payloads) — a possible *complementary* GTM surface, not a competitor.
- **The buyer question is load-bearing:** the Harness's value proposition only lands for someone who *distrusts the vendor's own optimizer* and needs an adversarial, falsifiable, third-party audit (regulated/safety review), not a pass-rate dashboard. GTM must identify and size this buyer before treating white space as a market.

---

## 6. Bottom Line

- **No true twin exists** (high confidence; 3/3 independent hunts agree). The integration — single-clause **removal** + directional-only verdicts + admissibility-gated tiered oracles + append-only Bayesian provenance + falsifiability gate — is unclaimed as of mid-2026.
- **Buildable**, and this repo is most of the way there; the two confirmed critical-path gaps are the **ablation runner** and the **Bayesian aggregation pass** (a 4-8 week push to first end-to-end demo).
- **The deepest risk is academic, not competitive:** the headline primitive is the inferior estimator in its own field, with two silent failure modes (redundancy cancellation, naive-deletion confound). The fixes are cheap and already latent in CLAUDE.md — **but they must be enforced and documented, or a measurement-theory reviewer lands the undermining blow first.**
- **The moat is the corpus + discipline, not the code.** Ship early, accumulate calibration/frozen-case data from day one, position on rigor, and watch a single competitor pivot (Tessl) plus the OpenAI/Promptfoo P2 vector.

---

## Source URLs

**Adjacent tools:** promptfoo.dev/docs/intro · github.com/promptfoo/promptfoo · promptfoo.dev/docs/configuration/expected-outputs/model-graded/select-best · github.com/openai/evals · github.com/confident-ai/deepeval · deepeval.com/docs/metrics-arena-g-eval · langchain.com/blog/pairwise-evaluations-with-langsmith · github.com/langchain-ai/langsmith-cookbook (comparing-qa.ipynb) · braintrust.dev/docs/evaluate · github.com/braintrustdata/autoevals (battle.yaml) · inspect.aisi.org.uk + github.com/UKGovernmentBEIS/inspect_ai · github.com/stanford-crfm/helm · crfm.stanford.edu/2024/02/18/helm-instruct.html · docs.ragas.io · github.com/truera/trulens · dspy.ai · langfuse.com/docs/evaluation · github.com/Arize-ai/phoenix · docs.patronus.ai · docs.wandb.ai/weave

**Academic (ablation validity — the undermining cluster):** arXiv:2405.20404 (XPrompt/JoPA) · 2409.00729 (ContextCite) · 2409.09951 (Optimal Ablation, NeurIPS 2024) · 2407.04690 (Missed Causes) · 2312.15395 (Shapley prompt valuation) · 2603.26830 (Regression framework for prompt component impact) · 2307.15771 (Hydra Effect) · 2211.00593 (IOI backup heads) · 2004.12265 (Causal Mediation, NeurIPS 2020) · 2310.15213 (Function Vectors)
**Academic (judge calibration — the validating cluster):** 2306.05685 (MT-Bench) · 2404.04475 (Length-Controlled AlpacaEval) · 2406.07791 (Position bias) · 2410.15393 (CalibraEval) · 2510.09738 (Judge's Verdict) · 2503.05965 · 2508.18076 · 2411.04424 (Bayesian win-rate calibration, EMNLP 2024)
**Academic (sensitivity + atomic-decomposition bottleneck):** 2310.11324 (FormatSpread) · 2306.04528 (PromptBench) · 2405.17202 (PromptEval) · 2603.28005 (Rethinking Atomic Decomposition) · 2602.10380 (Alignment Bottleneck) · 2406.20079 (Molecular Facts) · 2509.01460 (Dissecting Atomic Facts) · 2311.07911 (IFEval) · 2507.02833 (IFBench) · 2506.16697 (Dual-Validity Framework)

**Market / first-party:** techcrunch.com/2025/08/13 (Anthropic–Humanloop) · tessl.io/blog/anthropic-brings-evals-to-skill-creator · github.com/anthropics/skills (skill-creator/SKILL.md, comparator.md) · anthropic.com/engineering/demystifying-evals-for-ai-agents · anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills · anthropic.com/research/bloom · developers.openai.com/blog/eval-skills · openai.com/index/introducing-agentkit · developers.openai.com/api/docs/deprecations · openai.com/index/openai-to-acquire-promptfoo · a16z.com/announcement/investing-in-braintrust · braintrust.dev/blog/announcing-series-b · techcrunch.com/2026/01/06 (LMArena $1.7B) · prnewswire.com (Galileo $45M) · patronus.ai/blog/announcing-our-17-million-series-a · gartner.com/en/newsroom/press-releases/2026-03-30 (LLM observability) · tessl.io/blog (880 evals)

**Build / twin-hunt:** arXiv:2602.12670 (SkillsBench) · 2603.28815 (SkillTester) · 2602.08765 (Scylla) · 2411.15102 + github.com/r-three/AttriBoT · 2605.27621 (Agents that Matter, LOO cost) · 2505.20417 (SCAR) · 2601.22025 (When Better Prompts Hurt) · futureagi.com/blog/llm-as-judge-best-practices-2026 · github.com/tatsu-lab/alpaca_eval

**Repo (CONFIRMED by inspection):** `src/skill_harness/{extractor,oracles/tier1,oracles/tier2,oracles/calibration,storage}` · `migrations/evidence/{0001-0003,0200}` + `migrations/runtime/{0001-0002}` · `cli/main.py:131` (`run ablation` stub) · **gaps: no `ablation/` engine, no Bayesian `aggregation/` module.**

> **STALE-INFO RISK:** the eval field moves monthly. Braintrust Series B (Feb 2026), LMArena Series A (Jan 2026), OpenAI/Promptfoo integration (in-flight from Mar 2026), and Anthropic skill-creator 2.0 / Bloom (<6 months old) could all be superseded. Re-check first-party Agent-Skills tooling and the Promptfoo-into-Frontier launch before any GTM commitment.
