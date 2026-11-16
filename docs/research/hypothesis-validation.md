# Hypothesis Validation: Which AI-Approaches Still Work (2025–2026 evidence)

**Prepared for:** hackathon deliverable — folder-based strategy agent. **Research date:** 2026-11-16.
**Owner requirement (BRIEF §3.3):** every new approach must first be checked for whether it still works; many assumed hypotheses no longer do (e.g., "assign a profession"). Below: hypothesis → sources → verdict → design consequence → how we will falsify/confirm it ourselves in the dev contour.
**Verdict scale:** WORKS · WORKS CONDITIONALLY · DOES NOT WORK · UNVERIFIABLE (no adequate public evidence).
**Rule:** no claim without a source. Where a source is a blog or vendor post, it is labelled as such.

---

## H1. "Assigning a profession/persona in the prompt improves the result"
**Verdict: DOES NOT WORK (for accuracy on objective tasks). WORKS CONDITIONALLY for tone/perspective-framing only.**

Sources:
- Zheng et al., *When "A Helpful Assistant" Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of LLMs* (EMNLP Findings 2024; arXiv 2311.10054): 162 personas × 4 model families × 2,410 factual questions — adding personas "does not improve model performance… compared to the control setting"; effect sizes small; best-persona selection performs ~randomly. https://aclanthology.org/anthology-files/pdf/findings/2024.findings-emnlp.888.pdf
- *Prompting Science Report 4: Playing Pretend — Expert Personas Don't Improve Factual Accuracy* (arXiv 2512.05858, Dec 2025): six models on GPQA-Diamond + MMLU-Pro; in-domain expert personas ≈ no significant effect; domain-mismatched personas marginal/negative; low-knowledge personas harmful. https://arxiv.org/abs/2512.05858
- Hu & Collier 2024 (arXiv 2402.10811): persona effect in LLM simulations is weak/inconsistent (cited in the above).

Design consequence:
- The agent's **main workflow prompt carries no fake profession** ("you are a senior analyst" is banned). Accuracy-relevant steps rely on method + evidence, not role labels.
- Roles in the Консилиум are **not** used as accuracy boosters. They are used as *cognitive lenses* for divergence and critique (see H4/H7) — and even that must earn its cost via measurement (council-design.md).
- Where persona *does* have measured value (sycophancy reduction, H7), we use the specific critical-role framing, not generic expertise claims.

Our falsification test: on the demo + held-out tasks, A/B the strategy artifacts with vs. without role labels in the main prompt; expect ≤ noise. If a label shows a robust expert-rubric gain (>1 point, consistent across both orders), we revisit.

---

## H2. "A multi-agent system (council of roles) beats a single agent"
**Verdict: WORKS CONDITIONALLY — and the conditions are narrow.** Multi-agent wins for *parallel, independent work strands* (research fan-out) and for *read-only critique feeding a single writer*. It does **not** reliably beat a single agent for consensus reasoning, and costs 1.4–15× tokens.

Sources:
- Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (arXiv 2503.13657, Mar 2025; NeurIPS 2025 D&B): 5 MAS frameworks, 150+ tasks, 14 failure modes (specification, inter-agent misalignment, verification/termination); "performance gains across popular benchmarks remain minimal compared to single-agent frameworks"; role-prompt and orchestration fixes alone rarely prevent failures. https://arxiv.org/abs/2503.13657
- Cognition, *Don't Build Multi-Agents* (blog, 2025-06-12): parallel agents make conflicting implicit decisions; default to single-threaded linear agents; subagents are good for "answering a well-defined question" and keeping investigative work out of the main history. https://cognition.ai/blog/dont-build-multi-agents
- Cognition, *Multi-Agents: What's Actually Working* (blog, 2026): the pattern that works = **writes stay single-threaded while extra agents contribute intelligence, not actions**; "a clean-context reviewer catches bugs the coder can't see"; most real deployments are limited to read-only search subagents that "resemble tool calls". https://cognition.com/blog/multi-agents-working
- Anthropic, *How we built our multi-agent research system* (blog, 2025-06-13): Opus-lead + Sonnet-subagents beat single-agent Opus by **90.2%** on an internal research eval; token usage explains ~80% of BrowseComp variance; multi-agent uses **3–10×** tokens (research feature ~15× chat); explicitly "less effective for tightly interdependent tasks". https://anthropic.com/engineering/built-multi-agent-research-system
- Cost multipliers: BenchAgent (arXiv 2606.05670, 2026): ChatEval 4.34× tokens vs single-agent Core; LLM-Debate 1.39×; only 1 of 6 MAS configs beat Core accuracy (+3.05 pts), others trailed by 1.71–8.76 pts. MAST trace analysis: 86%/72% token duplication from context rebroadcast (flat/linear topologies). Systima (blog, Jul 2026): Claude Code subagent fan-outs 2.6–5.9× input tokens, never faster. (All via `llm-pricing-agent-costs.md` §5.)

Design consequence:
- **Architecture: one writer, many read-only critics.** The main agent owns all file writes; council roles never write artifacts.
- **Subagents only for research fan-out** (independent evidence strands), each with a full delegation brief (objective, output format, source guidance, boundaries — Anthropic's discipline), read-only, routed to cheaper models.
- **No agent teams, no inter-agent messaging, no dynamic workflows** (overhead without measured value; not portable across Cursor/Codex/GigaCode).
- Council is a *measured feature*, not a default: it ships in prod only if the A/B shows quality/diversity gain that survives its cost multiplier (see council-design.md).

Our falsification test: council vs single-agent vs self-critique vs multi-lens-single-model, on the demo + 2 held-out tasks, expert rubric + diversity metric + cost ledger. If council ≤ multi-lens single-agent within noise, council is demoted to the cheap equivalent.

---

## H3. "Chain-of-thought / long reasoning chains improve strategy quality"
**Verdict: WORKS CONDITIONALLY.** Longer chains do not reliably improve accuracy; gains depend on the regime (retrieval in the loop vs closed-book), and there is an inverted-U in CoT length. Reasoning effort is a cost dial, not a free lunch.

Sources:
- *Test-Time Scaling in Reasoning Models Is Not Effective for Knowledge-Intensive Tasks Yet* (arXiv 2509.06861, Sep 2025): 14 reasoning models; more compute "does not consistently improve accuracy and often leads to more hallucinations"; o4-mini: 8× reasoning tokens, accuracy ~unchanged; GPT-5-mini: hallucinations +15% as reasoning grows 300→3,300 tokens. **With a search tool** (BrowseComp-Plus), scaling improves accuracy 41.2%→53.0% and cuts hallucinations 16.6%→8.0%; **without search**, ~20× more tokens, no accuracy change, +10% hallucinations. Information-theoretic argument: compute-only scaling cannot add information the model lacks. https://arxiv.org/html/2509.06861v3
- *Not All Test-Time Compute Is Evidence* (arXiv 2610.23213, Oct 2026): same-model errors are correlated across samples/depth/self-evaluation — "more compute from the same model is not more evidence"; a heterogeneous small panel beats full CoT in 12/14 settings (MuSiQue 59.0→66.0) using up to 47.2% fewer tokens than a multi-agent baseline. https://arxiv.org/abs/2610.23213
- *Longer CoTs… do not consistently enhance accuracy* (arXiv 2502.12215): correct solutions are often shorter than incorrect ones for the same question; longer chains contain more self-revisions that degrade performance. https://arxiv.org/pdf/2502.12215v1
- *To Backtrack or Not to Backtrack* (arXiv 2504.07052): sequential search/backtracking is not universally better than parallel sampling (better on Sudoku, worse on CountDown). https://arxiv.org/pdf/2504.07052
- Wu et al. 2026 (cited in 2610.23213): inverted-U between CoT length and accuracy. Also *Scaffold, Not Vocabulary?* (arXiv 2606.06454): with real controls, celebrated prompt effects shrink — "CoT ≈ 0% average, p=.8". https://arxiv.org/pdf/2606.06454v1

Design consequence:
- **Retrieval before reasoning**: the workflow front-loads material collection (evidence in context), which is exactly the regime where test-time compute pays (41.2→53.0%). The agent is instructed to gather evidence first, then reason.
- **Default reasoning effort = medium**, escalated only for the synthesis step; effort level is recorded in COST.md (reasoning tokens bill as output on every major provider — `llm-pricing-agent-costs.md` §4).
- **Heterogeneity over depth**: where extra quality is needed, prefer a second model's independent read (cheap panel) over longer same-model chains — directly shapes the council's model routing.
- Strategy artifacts must **separate facts / hypotheses / forecasts** (brief requirement) — this also mitigates the confirmation-bias failure mode of long chains (fabricated details supporting early beliefs).

Our falsification test: on held-out tasks, run the synthesis step at low/medium/high reasoning effort; measure expert-rubric delta and $/run. If high effort ≤ medium within noise, ship medium in prod.

---

## H4. "A council of expert personas generates more diverse options than a single agent"
**Verdict: UNVERIFIABLE as stated / WORKS CONDITIONALLY with structural fixes.** Persona labels alone do not create real diversity; naive debate actively *suppresses* the diversity we need. The mechanisms that preserve diversity (cognitive-lens anchoring, quotas, no cross-reading before divergence, model heterogeneity) are supported by 2025–2026 work but never tested on strategy generation.

Sources:
- *Creative Generation via Multi-Agent Debate: Does Debate Suppress Diversity?* (arXiv 2609.00683, Sep 2026): MAD's convergence dynamics **suppress cross-run output diversity** — the opposite of what option generation needs; preserving within-session agent diversity is a *necessary condition* for cross-run diversity; Creative-MAD fixes it with **Cognitive Lens Assignment** (each agent anchored to a distinct persistent cognitive mode) + **Embedding-based Peer Selection** (each agent sees only its most semantically distant peers). https://arxiv.org/html/2609.00683
- *What Does Multi-Agent LLM Debate Actually Change?* (arXiv 2609.08016, Sep 2026): debate changes what agents *say* far more than what they persistently endorse; on 299 pairs the debated answer scored **no better** than the no-debate answer; tone controls surface disagreement (friendly↔hostile moves reported agreement by 50.4pp) — i.e., disagreement can be performed. Language Model Council (Zhao et al. 2024) is a voting jury: its edge over the best single judge is *separability* (90.5 vs 50.5), not human correlation (0.92 ≈ 0.917). https://arxiv.org/html/2609.08016v1
- Council audit, English medical QA (ACL 2026 main, 2026.emnlp-main.2164): council beats every member on 5/6 datasets, but 67% of verdicts settle before debate; on the hardest benchmark **agreement is worth less than disagreement** (all-agree questions correct 6.6% vs 14.6% otherwise); council trails a larger single model by up to 16.2pts at 7× model calls. https://aclanthology.org/2026.emnlp-main.2164.pdf
- llm-council-governance (andybhall, code, 2025, cited in 2609.08016): single-model prompt/persona diversity does **not** substitute for a multi-model council — "surface diversity ≠ real diversity".
- *The Virtual Roundtable* (arXiv 2606.05178, Jun 2026): persona roundtable with **divergent phase → convergent phase**, facilitator guarding against groupthink, per-persona idea quotas — produced diverse, relevant ideas in a consumer-products case study (single case study, no control). https://arxiv.org/html/2606.05178v1
- Du et al., *Multiagent Debate* (ICML 2024, arXiv 2305.14325): the original positive result — debate beats single agent on arithmetic/GSM/chess strategy (67→81.8, 77→85) — but on **verifiable** tasks where convergence is the goal. https://arxiv.org/abs/2305.14325

Design consequence (this is why the Council protocol is designed the way it is — full spec in `council-design.md`):
- **Divergence-first, no debate-to-consensus.** Roles generate independently (no cross-reading) → cross-critique → single-writer synthesis that *preserves dissent*.
- **Cognitive Lens Assignment**: each role gets a distinct, persistent lens (product economics / communication & barrier / data & evidence / adversarial), not a job title.
- **Quotas + mandatory dissent**: devil's advocate must produce the strongest case against the leading option; facilitator (main agent) checks groupthink.
- **Model heterogeneity preferred** where budget allows (dev contour: different model families per role when available); same-model fallback is explicitly weaker evidence-wise.
- **Measurement gate**: diversity (semantic distance + count of substantively different options), objection quality, expert strategy score, cost. If ≤ the multi-lens single-agent baseline, ship the baseline instead.

Our falsification test: 2×2 A/B (single vs council) × (same-model vs heterogeneous) on 3 tasks; diversity + objection + strategy metrics. Pre-registered in measurements plan.

---

## H5. "Self-critique / reflection improves the agent's output"
**Verdict: DOES NOT WORK alone (intrinsic self-correction). External critique works.**

Sources:
- Huang et al., *Large Language Models Cannot Self-Correct Reasoning Yet* (ICLR 2024, arXiv 2310.01798): without external feedback, LLMs "struggle to self-correct… at times performance even degrades after self-correction". https://arxiv.org/abs/2310.01798
- Du et al. 2023 (arXiv 2305.14325): single-agent reflection 72.1 vs 67.0 baseline (modest); debate 81.8 — external viewpoints beat introspection.
- EMNLP 2026 council audit (2026.emnlp-main.2164): on the hardest set, unanimous agreement correlated with *lower* accuracy (6.6% vs 14.6%) — self-agreement is a biased signal.
- *Playing Devil's Advocate* (arXiv 2605.21006, May 2026): steering toward critical personas (Skeptic/Judge/Devil's Advocate) reduces sycophancy to 68–98% of the targeted-steering effect while preserving accuracy on factual probes; conformist personas do not mirror the effect. https://arxiv.org/html/2605.21006v1

Design consequence:
- The agent never "reviews its own strategy" alone. The review step is either (a) deterministic script checks (hooks), (b) a *different model* reading the artifact, or (c) the council's adversarial role.
- Agreement is never treated as evidence of correctness; disagreement is logged and preserved.

---

## H6. "Skills / separated methodological knowledge improve research-analysis quality"
**Verdict: WORKS CONDITIONALLY — only for curated, procedural, few-in-number skills.** Generic instruction/context content does not measurably improve correctness and adds >20% cost.

Sources:
- SkillsBench (arXiv 2602.12670, Feb 2026): curated skills +16.2pp average pass rate (86 tasks, 7 configs), largest in **knowledge-heavy domains (Healthcare +51.9pp)**, smallest in Software Engineering (+4.5pp); 16/84 tasks regress; **self-generated skills −1.3pp**. https://arxiv.org/html/2602.12670v1
- *Demystifying Agent Skills* (arXiv 2608.14036, Aug 2026): skills work as **procedural anchors** (65.7% of benefit) not knowledge injection (4.5%); retrieval precision collapses **29.6%→3.3%** as pools grow 5→100. https://arxiv.org/pdf/2608.14036v1
- Downstream-utility study (arXiv 2610.08875, Oct 2026): same skills help some configs and hurt others on 36.78% of tasks; reranking by "support for required operations" +4.35–5.80pp; ≥5 skills need a dependency DAG.
- AGENTS.md ablations (ETH SRI, arXiv 2602.11988, Feb 2026; two-agent ablation arXiv 2607.27250, Jul 2026): generic context files do **not** significantly change task success and add >20% cost; process/cost warnings *do* pay (full-suite runs fell 3.67→1.67, wall-clock −24%).
- (All summarized with URLs in `agentic-ecosystem.md` §1.4, §2.3.)

Design consequence:
- **4–6 curated skills max**, each <500 lines, each encoding *our* method (framing, evidence discipline, option generation, strategy synthesis, comms strategy, verification plan) — never generic best practices the model already knows.
- **The model never authors skills** (−1.3pp).
- AGENTS.md carries only non-obvious rules: workflow, state locations, citation discipline, cost warnings. No encyclopaedic context (it duplicates the knowledge base anyway).

Our falsification test: A/B layered (skills + minimal AGENTS.md) vs monolithic mega-prompt on held-out tasks; artifact-check pass rate + token cost. If layered ≤ monolithic, simplify.

---

## H7. "A devil's-advocate role improves decision quality"
**Verdict: WORKS (limited but consistent evidence).** This is the one council role with direct measured support.

Sources:
- Sycophancy: arXiv 2605.21006 (above) — critical personas cut agreement-with-wrong-user substantially while preserving accuracy.
- Council audit (ACL 2026): hostile/stress-test tone produces genuine pushback that survives blind re-reading (arXiv 2609.08016 Layer B); disagreement is more informative than agreement on hard items (6.6% vs 14.6%).
- Decision-science convention (premortem / consider-the-opposite) — domain practice, not LLM evidence; we treat the *brief's* "strong objections per option" requirement as the product requirement and the above as the mechanism evidence.

Design consequence: devil's advocate is a **mandatory, structurally-protected role** in the council (always runs, always last, always writes the strongest case against the leading option; cannot be skipped by the synthesizer). Its output is a first-class artifact section, not a footnote.

---

## H8. "Reasoning/thinking models are worth their cost for strategy synthesis"
**Verdict: WORKS CONDITIONALLY — measure effort level, don't max it by default.** See H3 for the underlying evidence; added here: pricing structure makes effort a direct $ dial (reasoning tokens billed as output on OpenAI, Anthropic, Google, DeepSeek, Qwen — `llm-pricing-agent-costs.md` §4).

Design consequence: routing table defines per-step effort (extraction: low/none; synthesis: medium; council critics: medium; final strategy: medium-high in dev, medium in prod unless A/B says otherwise).

---

## H9. "Tiered model routing preserves quality at lower cost"
**Verdict: WORKS (vendor + practitioner evidence), but must be re-measured on our tasks.**

Sources:
- BrowseComp practitioner result (via `agentic-ecosystem.md` §3.2): Fable orchestrator delegating to Sonnet workers scored **96% of Fable-alone at 46% of the price**.
- Sber GigaCode docs (https://gitverse.ru/docs/ai/ai-assistant-gigacode/gigacode-for-vscode/rules; https://habr.com/ru/companies/sberbank/articles/1104670): auto-routing moved **50–60% of requests to junior models while holding quality near max**.
- Anthropic subagent docs: cost control via cheaper models is a documented subagent benefit.

Design consequence: the routing table (PRD §8) assigns cheap models to extraction/classification/formatting, mid to synthesis, frontier to strategy synthesis + council critics in dev. Prod target: blended $/run with quality held within ~1 rubric point of the all-frontier baseline.

Our falsification test: 3 tasks × 3 tiers; Pareto curve; route-accuracy audit (expert checks whether cheap-tier outputs were actually acceptable).

---

## H10. "Hooks / deterministic checks improve reliability"
**Verdict: WORKS (mechanism-level; cheap).** Deterministic enforcement is the only guarantee the LLM cannot be talked out of; judge-faithfulness literature (arXiv 2606.06454, 2609.33044) shows model self-verification is unreliable, so verification must be externalized.

Sources: Claude Code hooks docs (PreToolUse can block; PostToolUse/Stop deterministic) — https://docs.anthropic.com/en/docs/claude-code/hooks ; skill/hook taxonomy — https://docs.anthropic.com/en/docs/claude-code/features-overview. Plus the judge-reliability papers above.

Design consequence: 2–4 hooks: (1) every substantial claim in a strategy artifact carries a source link (block on violation); (2) STATE.md schema-valid before session end; (3) COST.md append on every model-call-bearing step; (4) artifact checklist (≥3 options, status-quo present, facts/hypotheses separated).

---

## H11. "File-based state resume is as good as native session resume"
**Verdict: UNVERIFIABLE publicly — no benchmark exists. Anthropic's own SDK docs say "don't rely on session resume"; capture results as application state and seed a fresh session.**

Sources: https://docs.anthropic.com/en/agent-sdk/sessions ("Sessions persist the conversation, not the filesystem"); filesystem-based-agent-state pattern (awesome-agentic-patterns); ATWZ checkpoint schema (arXiv 2607.22917) — all via `agentic-ecosystem.md` §7.

Design consequence: STATE.md (objective, step, completed steps, decisions+reasons, open questions, commitments, file refs, failed approaches, cost) + append-only journal; resume = fresh chat seeded from STATE.md; portability requirement makes this the only viable mechanism anyway.

Our falsification test: uninterrupted vs resumed-vs-restarted artifacts on the demo task; expert diff + information-loss score + token overhead (Day 4).

---

## Summary table

| # | Hypothesis | Verdict | Core design consequence |
|---|---|---|---|
| H1 | Persona/profession in prompt | DOES NOT WORK (accuracy) | no role labels in main prompt; roles = lenses only |
| H2 | Multi-agent > single | WORKS CONDITIONALLY (fan-out + read-only critique only; 1.4–15× cost) | one writer, read-only critics, subagents for fan-out |
| H3 | Long CoT improves strategy | WORKS CONDITIONALLY (retrieval first; inverted-U) | evidence-before-reasoning; medium effort default |
| H4 | Persona council → diverse options | UNVERIFIABLE as stated; WORKS CONDITIONALLY with structural fixes | divergence-first, lens assignment, quotas, heterogeneity; measure |
| H5 | Self-critique improves output | DOES NOT WORK alone | external critique: scripts, other model, adversarial role |
| H6 | Skills/knowledge separation | WORKS CONDITIONALLY (curated, few, procedural) | 4–6 skills; minimal AGENTS.md; no self-authored skills |
| H7 | Devil's advocate improves decisions | WORKS (limited evidence) | mandatory protected role; dissent preserved |
| H8 | Reasoning models worth cost | WORKS CONDITIONALLY | per-step effort dial; record in COST.md |
| H9 | Tiered routing preserves quality | WORKS (re-measure on our tasks) | routing table; prod blended-$ target |
| H10 | Hooks/deterministic checks | WORKS (cheap) | 2–4 hooks for citation/state/cost/checklist |
| H11 | File-state resume ≈ native resume | UNVERIFIABLE | STATE.md + fresh-chat seeding; own A/B |

## What we could not verify (flagged, per owner rule "если не нашёл — так и напиши")
- No public study tests a **council of roles on strategy/option generation** (closest: Virtual Roundtable case study without control; Creative-MAD on creative generation).
- No public benchmark for **resume quality** (H11).
- No independent replication of the "subagent tax" (one vendor benchmark + practitioner reports, directionally consistent with Anthropic's 3–10×).
- Persona evidence is about *accuracy on objective tasks*; effects on *creative/divergent* output are the opposite direction in some studies (Virtual Roundtable) — hence H4's "unverifiable as stated" rather than "does not work".
