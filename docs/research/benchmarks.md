# Benchmark Research: Measuring a Folder-Based Strategy Agent (2025–2026)

**Prepared for:** hackathon deliverable — folder-based strategy agent for product managers (MegaFon "Фабрика Продуктов" case).
**Research date:** 2026-11-16. All URLs retrieved this date from live search; publication dates noted per source.
**Scope rule:** only sources actually retrieved and read. Where a benchmark was not found or not verifiable, that is stated explicitly rather than guessed.
**Companion docs:** `agentic-ecosystem.md` (folder-agent mechanisms), `llm-pricing-agent-costs.md` (cost data), `hypothesis-validation.md` (approach-level verdicts), `council-design.md` (Консилиум measurement plan).

---

## 0. Executive summary — what we will measure with, and the honest gap

1. **No public benchmark measures what our agent produces.** Agentic benchmarks measure *task completion* (GAIA, τ-bench, BrowseComp, OSWorld); research-quality benchmarks measure *report quality / citation accuracy* (DeepResearch Bench ×2, ResearchQA); LLM-as-judge benchmarks measure *chat preference* (MT-Bench, Arena-Hard, AlpacaEval). None measures "did a product manager end up with a defensible product + communication strategy with ≥3 substantively different options and a verification plan". **Our primary evaluation must be our own suite**: a demo task + held-out PM tasks, scored with (a) deterministic artifact checks, (b) expert rubric aligned to the hackathon criteria, (c) LLM-judge *pairwise* A/B with order balancing as a cheap secondary signal.
2. **The most relevant existing benchmarks for our agent's sub-capabilities**: BrowseComp (persistence of evidence search), ResearchQA rubric coverage + FACT citation accuracy (evidence discipline), τ-bench/τ² (multi-turn agent-user interaction with a policy — our human-in-the-loop workflow), MINT (multi-turn interaction with tools + natural-language feedback — our clarification loop), GAIA2 (ambiguity handling, noise tolerance, resumability of long scenarios).
3. **LLM-as-judge is usable but has a measured noise floor**: pointwise 0–5 rubric scoring under a single judge cannot reliably separate systems closer than ~0.4–1.2 points on a 5-point scale (arXiv 2609.27787), pinned T=0 judges still flip 4.9–5.3% of pairwise verdicts per item and ~40% on close calls (arXiv 2609.33044), and correlations collapse when compared systems are close in capability (AlpacaEval τ 0.86 → 0.19, EMNLP Findings 2025). **Design consequence:** pairwise protocol, both orders, multiple judges or expert spot-checks, report uncertainty; never claim a feature win from one judge run.
4. **Human baseline data exists and is humbling**: humans 92% vs best agent 74.5% on GAIA (Sep 2025); on FutureSearch's DeepResearch Bench, frontier agents under low elicitation still lose to "smart generalist researchers given ample time" (o3 agent 0.51 vs estimated noise ceiling ~0.8); ResearchQA best system covers only 75% of expert rubric items, <11% of citation items. **This is our competitive framing**: the agent's value is speed/cost/structure, not superhuman analysis — and our measurement must show where it matches a careful analyst and where it does not.
5. **Cost measurement is a first-class metric** (owner requirement): see `llm-pricing-agent-costs.md` for per-token prices and published per-task deep-research costs ($0.92–$10/query depending on model; ~$1.27 ± $0.26 for o3-deep-research on DeepResearchBench; Google's own estimate $1–3/task standard, $3–7 Max). Every feature row in §4 carries a cost/run estimate.

---

## 1. Agentic / analytical benchmarks — what they measure and whether they apply

Legend for relevance: **A** = adopt as a real measurement in our dev contour · **B** = borrow the *method* (rubrics, harness) but not the task set · **C** = context/positioning only (do not run).

### 1.1 GAIA (Meta/HF/AutoGPT, 2023) — relevance: **B/C**
- **What it measures:** 466 real-world assistant questions with unique verifiable answers; reasoning, multi-modality, web browsing, tool use; 3 difficulty levels. Humans 92%, GPT-4+plugins 15% (paper). By Sep 2025 the best entry reached 74.5% (Claude Sonnet 4.5) — still 17.5pp below humans.
- Sources: https://arxiv.org/abs/2311.12983 · https://hal.cs.princeton.edu/gaia · https://aiadoption.org/data/gaia-ai-assistant-benchmark (Sep 2025 score history).
- **Why relevant:** the canonical "assistant that must combine tools + browsing + files" benchmark; its level-2/3 tasks (multi-hop, multi-source) resemble our "collect materials → synthesize" step. HAL's leaderboard also reports **cost per full benchmark run** — a model for our cost transparency.
- **Why not directly:** answers are short facts, not strategies; it cannot score option quality, objections, or a communication strategy. **Use:** sanity-check the agent's evidence-retrieval sub-skill on a small GAIA-validation sample (dev contour only), and cite the human-vs-agent gap in our comparison section.

### 1.2 GAIA2 + ARE (Meta, Sep 2025) — relevance: **B**
- **What it measures:** 1,120 scenarios in a simulated mobile environment, **asynchronous** (environment time advances independently), 7 capability groups: Execution, Search, Ambiguity Handling, Adaptability, Time/temporal reasoning, Agent2Agent collaboration, Noise tolerance (API failures). Best model Sep 2025: GPT-5 high; no system dominates — "stronger reasoning often comes at the cost of efficiency; budget scaling curves plateau".
- Sources: https://arxiv.org/html/2509.17158v1 · https://huggingface.co/blog/gaia2.
- **Why relevant:** Ambiguity Handling + Noise Tolerance + long scenarios are exactly our "human-in-the-loop clarification" and "resume after break" requirements. Its verification system (soft LLM-judge or hard match per argument type) is a good pattern for our artifact checks.
- **Why not directly:** environment is a phone simulator, not a knowledge folder. **Use:** borrow the ambiguity/noise scenario *design* for our own robustness probes (Day 4).

### 1.3 τ-bench / τ²-bench (Sierra, 2024–2025; τ³ 2026) — relevance: **A (method), C (tasks)**
- **What it measures:** tool-agent-**user** interaction in real domains (airline, retail, **telecom**, banking) with a policy the agent must follow; pass^k metrics over k trials; τ² adds dual-control (user can also act), multi-language, voice, and post-hoc judges. 2026 frontier range for retail/airline ≈ 55–70% (futureagi table).
- Sources: https://github.com/sierra-research/tau2-bench · https://arxiv.org/abs/2406.12045 · https://arxiv.org/abs/2506.07982.
- **Why relevant:** our agent is also a *policy-following agent in dialogue with a user* (the PM), and a **telecom domain exists** — MegaFon's industry. The dual-control frame (agent and user both act) mirrors our human-checkpoint workflow.
- **Why not directly:** tasks are customer-service transactions, not strategy work. **Use:** adopt the *evaluation protocol* (policy adherence + multi-trial pass^k) for our workflow-compliance checks; telecom domain useful for flavored demo data only.

### 1.4 AgentBench (2023) — relevance: **C**
- 8 environments (OS shell, DB, KG, card game, puzzles, household, web shopping, browsing). "Submissions have run cold since 2025… largely superseded by τ-bench, GAIA L3, SWE-bench Verified, OSWorld for frontier-model differentiation; remains a useful sanity check."
- Sources: https://arxiv.org/abs/2308.03688 · https://futureagi.com/glossary/agentbench-agent-benchmark (2026 status).
- **Use:** none beyond citation. Listed here because the task asked; verdict: superseded, do not run.

### 1.5 WebArena / VisualWebArena / OSWorld / OSWorld 2.0 — relevance: **C** (except as failure-mode evidence)
- WebArena: 812 tasks, self-hosted sites, script-based verification; 2026 frontier ≈ 35–50%. OSWorld: desktop VM tasks; OSWorld-Verified (Jul 2025). **OSWorld 2.0** (arXiv 2606.29537, 2026): 108 long-horizon workflows (median 1.6h human time, ~318 tool calls with Claude Opus 4.7 max thinking); best agent (Claude Opus 4.8) completes only **20.6%** (54.8% partial); GPT-5.5 plateaus ~13%. Documented failure modes: *losing track of constraints, missing mid-task information, guessing instead of asking the user, skipping verification*.
- Sources: https://arxiv.org/abs/2407.01694 (WebArena) · https://osworld-v1.xlang.ai · https://arxiv.org/html/2606.29537v2.
- **Use:** failure-mode list is a direct checklist for our STATE.md/checkpoint design (Day 2–4). Not run.

### 1.6 ClawBench (2026) — relevance: **C**
- 153 real-web, write-heavy everyday tasks across 144 sites; Claude Sonnet 4.6 33.3%, GPT-5.4 6.5% — vs 65–75% on OSWorld/WebArena. Shows sandbox benchmarks overstate readiness for real, authenticated, dynamic web work.
- Source: https://arxiv.org/html/2604.08523v1.
- **Use:** cite when justifying why our agent stores sources with URL + retrieval date + excerpt rather than trusting live re-fetch; and why "collect materials" must tolerate fetch failures.

### 1.7 BrowseComp (OpenAI, Apr 2025) — relevance: **A (small sample, dev contour)**
- 1,266 questions requiring persistent, creative browsing for hard-to-find facts; short verifiable answers. GPT-4o 0.6%, o1 9.9%, Deep Research 51.5% (calibration error 91% — overconfident). OpenAI explicitly accepts the short-answer tradeoff: "unclear how much performance on BrowseComp correlates with a real user distribution".
- Sources: https://openai.com/index/browsecomp · https://arxiv.org/pdf/2504.12516.
- **Why relevant:** it is the best public proxy for our "research" step's persistence + search creativity. **Use:** run a small sample (e.g., 30–50 questions) as a *sub-skill* benchmark for the evidence-collection step when comparing search strategies/routing in the dev contour. Cost per run is measurable (HAL-style reporting).

### 1.8 DeepResearch Bench — TWO different benchmarks (both 2025) — relevance: **B/A**
- **(a) USTC "DeepResearch Bench"** (arXiv 2506.11763, Jun 2025): 100 PhD-level tasks, 22 fields; **RACE** (reference-based adaptive criteria: Comprehensiveness, Insight/Depth, Instruction-Following, Readability) + **FACT** (citation accuracy, effective citations). Gemini-2.5-Pro DR 48.9 overall; Perplexity DR best citation accuracy (90.2%).
  Source: https://arxiv.org/abs/2506.11763 · https://github.com/Ayanami0730/deep_research_bench.
- **(b) FutureSearch "Deep Research Bench"** (arXiv 2506.06287, May 2025): 89 analyst-style tasks in 8 categories (Find Number, Derive Number, Gather Evidence, Validate Claim, Compile Dataset, Populate Reference Class, Find Original Source, Find Dataset) with a frozen **RetroSearch** environment; binary/partial scoring; leaderboard at drb.futuresearch.ai. Top: o3 ReAct agent 0.51; estimated noise ceiling ~0.8; "frontier agents under low elicitation substantially underperform smart generalist researchers who are given ample time"; ~45% of the GPT-4-Turbo→human gap was closed in one year (their own caveat: this likely overstates).
  Source: https://arxiv.org/abs/2506.06287.
- **Why relevant (a):** RACE is directly reusable as our *report-quality* rubric (comprehensiveness/depth/instruction-following/readability map onto our strategy artifacts); FACT is directly reusable as our *evidence-discipline* metric (citation accuracy + effective citations per artifact) — FACT-style automated claim→URL support verification is implementable in a script.
- **Why relevant (b):** its task taxonomy is the closest public formalization of "analyst research" (derive a number from multiple sources, validate a claim, populate a reference class) — a good source of held-out probe tasks for our agent, and its RetroSearch design (frozen scraped web) is the answer to "the web changes under us" — we can freeze a small local corpus for reproducible dev runs.
- **Use:** adopt RACE-style + FACT-style scoring for our demo artifacts; optionally run 10–20 FutureSearch-category tasks as held-out probes (dev contour; no budget limit per owner).

### 1.9 ResearchQA (UPenn, Sep 2025) — relevance: **B**
- 21.4K queries + 160K rubric items mined from 75 fields' survey articles; metrics = rubric coverage % and Elo via ensemble LLM-judge; best system (sonar-deep-research) 75.3% coverage, 82% win rate over next; deep research >+6.7–9.1pp coverage vs parametric; naive retrieval loses 7.6pp vs production retrieval. Error analysis: best system fully addresses <11% of citation items, 48% of limitation items, 49% of comparison items.
- Source: https://arxiv.org/abs/2509.00496.
- **Use:** rubric-coverage is our most transferable *report quality* metric — we will author rubrics for our strategy artifacts the same way (from expert-written "what a good strategy must contain"). The <11% citation-item finding justifies our hard hook: every substantial claim carries a source link.

### 1.10 MINT (2023) — relevance: **A (method)**
- Multi-turn interaction with tools + GPT-4-simulated user feedback; gains 1–8pp per tool turn, 2–17pp with natural-language feedback; better single-turn ≠ better multi-turn; SIFT/RLHF hurt multi-turn.
- Source: https://arxiv.org/abs/2309.10691.
- **Use:** the design template for our *clarification-loop* evaluation: simulate a PM user giving feedback, measure whether the agent's artifacts improve. Also evidence that our "ask only what changes the next step" behavior is measurable (feedback utilization rate).

### 1.11 TheAgentCompany (2025) — relevance: **C**
- 175 sandboxed software-company tasks, checkpoint-based verification. Not our domain; cited in ClawBench's comparison table.
- Source: https://arxiv.org/abs/2412.14161 (via https://arxiv.org/html/2604.08523v1 comparison table).
- **Use:** none.

### 1.12 Benchmarks we looked for and did NOT find (honest gaps)
- **No benchmark for "folder/repository agent" quality** (AGENTS.md/skills-driven agents on non-coding work). The 2026 AGENTS.md ablations are software tasks (see `agentic-ecosystem.md` §1.4). Gap → our own suite.
- **No benchmark for multi-role expert councils producing strategy options.** Adjacent: Virtual Roundtable (arXiv 2606.05178, case study only), Creative-MAD (arXiv 2609.00683, diversity metrics for creative generation), medical council audit (ACL 2026, arXiv-style proceedings 2026.emnlp-main.2164). Gap → our own A/B (see `council-design.md`).
- **No benchmark for resumability quality** (file-state resume vs native session resume). Gap → our own A/B on the demo project (Day 4).
- **No public per-report cost disclosures by consumer deep-research products** (only APIs + third-party DR vendors publish $/task — see `llm-pricing-agent-costs.md` §2). Gap → our own COST.md instrumentation.

---

## 2. Measuring the quality of research/strategy work — LLM-as-judge and rubrics

### 2.1 The judge instruments themselves
| Instrument | What it is | Key reliability facts (2025–2026) | Our use |
|---|---|---|---|
| MT-Bench (Zheng et al. 2023) | 80 two-turn prompts, 8 categories, 1–10 single-judge scores; >80% GPT-4↔human agreement (original claim) | Single-judge pointwise ceiling measured at **Eρ²=0.600** (all 9 judges) to 0.798 (current-gen 6 judges); MDD 0.63 points at n=42; all 17 recovered published MT-Bench improvements fall below the benchmark's own noise floor (arXiv 2609.27787) | Do not use raw MT-Bench-style scores for feature claims; if used, pairwise + multi-judge |
| Arena-Hard (Li et al. 2024) | 500 live Chatbot Arena prompts, fixed baseline, win-rate | Ceiling 0.792–0.918; pairwise order-balanced single judge reaches Eρ²≈0.86–0.93 — the honest exception among pointwise benchmarks (arXiv 2609.27787) | **Our primary LLM-judge protocol template**: pairwise, both orders |
| AlpacaEval 2 | length-controlled win-rate vs reference | τ=0.86 in standard meta-eval but **0.19** when ranking models <2 points apart (EMNLP Findings 2025, aclanthology 2025.findings-emnlp.1036) | Cautionary citation for close-comparison claims |
| G-Eval (Liu et al. 2023) | LLM judge with weighted criteria + form-filling probability | Superseded in practice by rubric/checklist judging; same reliability caveats | Criteria list borrowed for our expert rubric |
| RACE (DeepResearch Bench, 2025) | reference-based adaptive criteria w/ dynamic weights | Validated against human judgment in the paper | **Adopt for strategy artifact quality** |
| FACT (DeepResearch Bench, 2025) | claim→URL support verification | Citation accuracy 39–94% across evaluated systems | **Adopt for evidence discipline** (scriptable) |
| ResearchQA rubrics (2025) | survey-mined per-query criteria, coverage % | Best system 75.3% coverage; <11% citation items | **Adopt rubric-coverage authoring pattern** |
| "Pinned and still unstable" (arXiv 2609.33044, 2026) | meta-study of judge determinism | Pinned T=0 judges: 4.94–5.29% per-item flip, ~40% conditional on close calls; 2–7 of 9 adjacent ranks indistinguishable; cross-judge Kendall τ as low as 0.42–0.64 | **Report uncertainty; never single-run judge verdicts** |
| "Sizing benchmarks scored by an LLM" (arXiv 2609.27787, 2026) | resolution analysis of judged benchmarks | MDD 0.41–1.24 points (0–5) at native item counts; median published improvement 0.28 < floor; protocol design (pairwise, reference answers) moves the ceiling more than panel size | **Protocol > panel; pre-register our MDD** |

### 2.2 The judge protocol we will use (pre-registered)
1. **Pairwise, order-balanced** (both A-B and B-A), because order-balanced pairwise raises the single-judge ceiling to ~0.95–0.99 (arXiv 2609.27787) and cancels the measured 8.6pp first-position advantage.
2. **Rubric-based pointwise scoring only for artifact checklists** (deterministic parts automated by script; e.g., "≥3 options present", "status-quo option present", "every claim has a source link" — these are hook/script checks, not judge calls).
3. **Expert panel as ground truth** for the 3–5 headline comparisons (demo task + held-out tasks); LLM judges used only for cheap iteration signal, with ≥2 judge models and reported disagreement. Rationale: arXiv 2606.06454 shows judge verdicts collapse under real controls; human top-3 recovery on SummEval is only 23–32% even at high reliability (arXiv 2609.27787) — so we treat expert scoring as the decision-grade instrument and say so.
4. **Pre-registered minimum detectable difference**: at our item counts (≈2–4 tasks × 2–3 artifacts), only differences larger than ~1 point on a 5-point rubric (or a full rank swap in pairwise) will be claimed; smaller effects are reported as "no detectable difference".

---

## 3. Human / baseline comparators (owner requirement: compare vs manual analyst and vs plain chat)

| Comparator | Evidence | What we will measure on the demo task |
|---|---|---|
| **Manual analyst** | GAIA: humans 92% vs agents 74.5% (Sep 2025). FutureSearch DRB: agents lose to smart generalists given ample time (0.51 vs ~0.8 ceiling); ~45% of the 2024→2025 gap closed (authors' own caveat: overstated). ResearchQA: best system 75% rubric coverage | Time-to-first-draft (minutes vs hours), rubric coverage vs an expert-written reference strategy, citation accuracy, cost (analyst-hours × rate vs $/run) |
| **Plain chat with an AI (no folder)** | No public benchmark; mechanism evidence: generic context files don't beat well-specified tasks (arXiv 2602.11988, 2607.27250); ChatEval/debate token multipliers 1.39–4.34× (arXiv 2606.05670) | Same rubric, same task, no workflow/state/evidence discipline: expect failures in source-tracking, continuation, cost visibility — measure artifact check failures + resume loss + missing cost log |
| **Commercial deep research (OpenAI/Gemini/Perplexity DR)** | DRB(a): Gemini DR 48.9 RACE overall, 111–165 effective citations, citation accuracy 77.96–81.44%; Perplexity DR best citation accuracy 90.24%; ResearchQA: sonar-DR 82% win rate | Run the demo task through 1–2 commercial DR tools (dev contour, no budget limit); score with our rubric; record $/run and time. This is the "state of the art" bar we position against |

---

## 4. Feature → measurement matrix (every backlog feature gets a metric)

Format: **feature → primary metric (instrument) → method → cost/time of measurement → dependency.**
"Script check" = deterministic verifier in `scripts/` (hook-enforced); "A/B" = dev-contour comparison vs the stated baseline; "Expert" = rubric scored by a human expert panel; "Judge" = pairwise LLM-judge protocol §2.2.

### Mandatory minimum
| # | Feature | Primary metric | Method | Baseline | Est. measurement cost (dev) |
|---|---|---|---|---|---|
| M1 | Task framing (brief + decision frame) | (a) % frames confirmed by simulated/human PM without edit; (b) # of clarification questions that were decision-relevant (expert-rated); (c) feedback-utilization gain (MINT method: 2–17pp expected from good feedback use) | A/B: framed vs unframed prompt on same task; MINT-style simulated feedback loop | none (raw request) | ~10–20 LLM calls + 1 expert hour |
| M2 | Materials collection + evidence log | (a) Citation accuracy (FACT method, script-verifiable); (b) % substantial claims with URL + retrieval date; (c) effective citations per artifact | Script check on every artifact + FACT spot audit | plain chat output | script: minutes; audit: ~1 hour |
| M3 | Research step (plan, source triangulation, named gaps) | Rubric coverage (RACE/ResearchQA-style rubric authored from expert reference) + gap recall (expert-named gaps found) | Expert rubric on demo + 1 held-out task | commercial DR report (DRB-style) | 2–3 expert hours; DR runs $1–10 each |
| M4 | Options ≥3 incl. status quo + objections | (a) script: ≥3 options, status-quo present, facts/hypotheses labeled; (b) diversity: pairwise semantic distance of option embeddings (Creative-MAD metric); (c) objection strength: expert rubric | Script check + diversity metric + Expert | single-agent baseline | embeddings: minutes; expert: 1–2 hours |
| M5 | Product + communication strategy + verification plan | (a) artifact checklist (script); (b) RACE-style expert rubric (comprehensiveness/depth/instruction-following/readability) mapped to hackathon criteria; (c) product↔comms consistency (promises match product) — script + expert | Expert rubric (primary); pairwise Judge (secondary, order-balanced) | commercial DR + plain chat | 3–5 expert hours |
| M6 | Workflow with human checkpoints | (a) workflow-compliance pass^k (τ-bench method): % runs where all mandatory checkpoints honored; (b) # unnecessary interruptions | 5–10 scripted runs on demo + held-out | — | ~10 runs × $0.5–5 |
| M7 | Knowledge separation (4 layers) | (a) context tokens per step (instrumented); (b) correctness delta on artifact checks vs monolithic-prompt variant | A/B on held-out tasks (mirrors 2026 AGENTS.md ablations) | monolithic AGENTS.md | ~20 runs |
| M8 | Continuation after break | (a) information-loss score: resumed artifact vs uninterrupted reference (expert diff); (b) time-to-resume; (c) token overhead of re-seeding | A/B: fresh-chat resume vs native session resume vs restart-from-scratch | restart-from-scratch | 1–2 expert hours + ~6 runs |
| M9 | Transparency (LOG/COST/grounds) | (a) script: every run has complete LOG + COST; (b) cost prediction error (COST.md estimate vs metered); (c) grounds coverage = % conclusions traceable to logged evidence | Script check; compare estimated vs actual (Stanford 2026: models underestimate own token use 30× variance) | — | script: minutes |

### Additional level (each needs a measured justification — owner rule #7)
| # | Feature | Primary metric | Method | Baseline | Est. cost (dev) |
|---|---|---|---|---|---|
| B1 | Консилиум (council) | (a) option diversity (semantic distance, Creative-MAD); (b) objection quality (expert rubric); (c) strategy quality (expert); (d) cost multiplier; (e) *cheap-alternative delta*: multi-lens single-agent prompt | A/B full factorial: {single, self-critique, multi-lens single-model, council} × {full, optimized} | single agent | see `council-design.md` (~$20–60 dev) |
| B2 | Routing (model/tool/process) | (a) quality delta vs cost delta (Pareto); (b) route accuracy: % tasks where cheap tier sufficed (expert check); (c) $/run at target quality | A/B on 3 tasks × 3 tiers; Sber data point: 50–60% requests to junior models at near-max quality | single frontier model | ~30 runs |
| B3 | Knowledge base (navigation/search/stale correction) | (a) retrieval precision@k for skill/entry routing (note: pools >100 collapse to 3.3% — arXiv 2608.14036); (b) stale-entry detection rate; (c) time-to-find (scripted grep probes) | Scripted probe set; A/B vs "read everything" | read-everything | minutes (script) |
| B4 | MCP web search/fetch | (a) citation accuracy with vs without live search; (b) fetch-failure resilience; (c) $/search | A/B; BrowseComp sample as sub-skill probe | parametric-only | 50 BrowseComp items ≈ $1–5 |
| B5 | Resilience (retry/degraded/state validation) | (a) % runs completing with injected failures (GAIA2 noise-tolerance method); (b) state-file validity rate (hook) | Fault-injection runs | no-fault baseline | ~10 runs |
| B6 | Post-decision support (decision record, review triggers) | (a) % decisions with owner+metric+review condition (script); (b) revision correctness when new data arrives (expert) | Script check + 1 expert-scored revision scenario | — | 1 expert hour |
| B7 | Synthetic interviews (labeled non-real) | (a) labeling compliance (script: every synthetic answer marked); (b) usefulness: hypothesis-generation count/quality vs no-interview | A/B; honesty rubric | none | ~10 calls |
| B8 | Data analysis (reproducible calcs) | (a) reproducibility: script re-run → identical numbers; (b) numeric correctness vs expert calc | Script + expert | ad-hoc LLM math | 1 expert hour |
| B9 | UX/interface analysis | expert rubric on a known-bad interface (break/variant probe) | Expert | — | 1 hour |
| B10 | Comparison vs manual analyst / plain chat | §3 table: time, rubric score, citation accuracy, $/run | Side-by-side on demo task | — | included above |
| B11 | Portability (Cursor/Claude Code/Codex/GigaCode) | % target environments where AGENTS.md + skills load unchanged (smoke test per IDE) | Manual smoke matrix | — | 2–3 hours |

---

## 5. What we will actually run in the 5 days (dev contour — no budget limit)

1. **Our eval suite (primary):** demo task + 2 held-out PM tasks (one retention/churn-flavored, one launch/comms-flavored — aligned to MegaFon's published brief when it appears). Artifacts scored by (a) deterministic script checks, (b) expert rubric (hackathon criteria 1:1), (c) pairwise order-balanced LLM judges for iteration only. Rubrics pre-registered in `eval/rubrics/` on Day 4; results land in `docs/research/measurements.md` on Day 5 (see ROADMAP).
2. **Sub-skill probes:** 30–50 BrowseComp items (evidence-search persistence); 10–20 FutureSearch-DRB-category tasks (analyst reasoning); optional GAIA validation sample. Each reports score **and $/run** (HAL-style).
3. **Feature A/Bs:** M1/M4/M5 baselines vs full agent; B1 council factorial; B2 routing Pareto; M7 monolithic vs layered; M8 resume vs restart.
4. **Cost ledger:** every dev run logged in `COST.md` with model, tokens, $ (from `llm-pricing-agent-costs.md` rates). The dev-circuit total is reported in the final description document as "what the research cost".
5. **Not run (stated honestly):** AgentBench, WebArena/OSWorld, TheAgentCompany, MT-Bench/AlpacaEval leaderboards — superseded or out-of-scope for a strategy artifact (see §1).

---

## 6. Key citations (quick list)

- GAIA: https://arxiv.org/abs/2311.12983 · leaderboard: https://hal.cs.princeton.edu/gaia · 2025 scores: https://aiadoption.org/data/gaia-ai-assistant-benchmark
- GAIA2/ARE: https://arxiv.org/html/2509.17158v1 · https://huggingface.co/blog/gaia2
- τ-bench/τ²: https://arxiv.org/abs/2406.12045 · https://arxiv.org/abs/2506.07982 · https://github.com/sierra-research/tau2-bench
- AgentBench: https://arxiv.org/abs/2308.03688 · 2026 status: https://futureagi.com/glossary/agentbench-agent-benchmark
- BrowseComp: https://arxiv.org/pdf/2504.12516 · https://openai.com/index/browsecomp
- DeepResearch Bench (RACE/FACT): https://arxiv.org/abs/2506.11763 · code: https://github.com/Ayanami0730/deep_research_bench
- Deep Research Bench (FutureSearch): https://arxiv.org/abs/2506.06287 · leaderboard: https://drb.futuresearch.ai/
- ResearchQA: https://arxiv.org/abs/2509.00496
- MINT: https://arxiv.org/abs/2309.10691
- OSWorld 2.0: https://arxiv.org/html/2606.29537v2 · ClawBench: https://arxiv.org/html/2604.08523v1
- Judge reliability: https://arxiv.org/html/2609.27787 · https://arxiv.org/pdf/2609.33044v2 · https://aclanthology.org/2025.findings-emnlp.1036.pdf
- Multi-agent/council evidence: ACL 2026 council audit https://aclanthology.org/2026.emnlp-main.2164.pdf · debate analysis https://arxiv.org/html/2609.08016v1 · Creative-MAD https://arxiv.org/html/2609.00683 · Virtual Roundtable https://arxiv.org/html/2606.05178v1 · MAST https://arxiv.org/abs/2503.13657 · BenchAgent https://arxiv.org/html/2606.05670 (via llm-pricing doc)
- Human/analyst comparison anchors: FutureSearch DRB §4 (agents vs researchers), GAIA human 92%, ResearchQA 75% coverage.
