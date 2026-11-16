# Консилиум (Council) — Feature Design & Measurement Plan

**Feature owner requirement (BRIEF §3.6):** take OpenClaw's own "council of expert roles" pattern into the product as an agent function — a board of several expert roles that generates and critiques options.
**Two circuits (owner clarification 2026-11-16):** in the **dev contour** the full version runs without budget saving (all roles, full protocol, all measurements); in the **prod contour** only the optimized version ships, and only if measurements show optimization does not kill quality.
**Evidence base:** `hypothesis-validation.md` H2/H4/H5/H7 and `benchmarks.md` §1.8/§4 — summarized in §1 below. Full protocol spec in §4; measurement plan in §6.

---

## 1. What the evidence says a council is (and is not) good for

| Finding | Source | Consequence for Консилиум |
|---|---|---|
| Multi-agent gains over single-agent are minimal on consensus reasoning; 14 failure modes; role prompts alone don't fix it | MAST, arXiv 2503.13657 (NeurIPS 2025) | The council is **not** a voting machine for "the right answer" |
| Debate changes what agents *say* more than what they endorse; on 299 pairs the debated answer scored no better than no-debate | arXiv 2609.08016 (2026) | **No debate-to-consensus rounds**; no "the council decided" claims |
| Debate *suppresses* output diversity — the exact resource option-generation needs | Creative-MAD, arXiv 2609.00683 (2026) | Divergence phase must be structurally protected (independent generation, no cross-reading) |
| Same-model persona diversity ≠ multi-model council ("surface diversity ≠ real diversity") | llm-council-governance (2025), cited in arXiv 2609.08016 | Prefer **heterogeneous models** per role in dev; same-model version is a fallback, not an equivalent |
| 67% of council verdicts settle before debate; unanimous agreement correlated with *lower* accuracy (6.6% vs 14.6%) | ACL 2026 council audit (2026.emnlp-main.2164) | Log Round-0 (pre-debate) positions; treat agreement as a warning signal, not validation |
| What works: writes single-threaded, extra agents contribute *intelligence*; "a clean-context reviewer catches what the writer can't see" | Cognition, 2026 (cognition.com/blog/multi-agents-working) | **One writer (main agent), read-only critic roles** |
| Devil's-advocate/critical personas cut sycophancy 68–98% of targeted steering while preserving accuracy | arXiv 2605.21006 (2026) | Adversarial role is the best-evidenced council component |
| Cost: multi-agent 1.4–15× tokens depending on architecture; duplication comes from context rebroadcast, largely eliminable | BenchAgent arXiv 2606.05670; MAST; Anthropic 3–10×/15× | Council = independent single-shot evaluations over one shared brief (no rebroadcast): ~N× a single call, not 15× |
| Persona labels don't improve accuracy | EMNLP Findings 2024 (arXiv 2311.10054); Prompting Science Report 4 (arXiv 2512.05858) | Roles are **cognitive lenses**, not expertise claims |

**Bottom line:** the Консилиум is justified **only** as a *divergence-and-critique* instrument for step 4 (options + objections) of the workflow, with dissent preserved into the final artifact. If our A/B shows it does not beat a cheap multi-lens single-agent prompt on diversity/objection/strategy quality, we ship the cheap equivalent and say so (owner rule: every component must justify its complexity with measured benefit).

---

## 2. Roles (5 lenses — cognitive modes, not job titles)

| Role | Cognitive lens (what it must do) | Output |
|---|---|---|
| **Продуктовщик (Product)** | Unit economics & audience jobs: who has the job-to-be-done, what they use today, what the benefit/cost/revenue link is | 2–3 options from a product-economics angle |
| **Коммуникатор (Comms)** | Barrier to understanding/choice: what blocks the audience, what message clears it, which channel plays which role, promise↔product match | 2–3 options from a communication angle |
| **Аналитик (Data/Evidence)** | What is known vs assumed: data quality, gaps, base rates, what measurement would change the decision | 2–3 options from an evidence angle + explicit gap list |
| **Адвокат дьявола (Devil's advocate)** | Strongest case *against* each leading option: failure modes, second-order effects, who is harmed, what would make this a regretted decision | Objections per option (mandatory, protected) |
| **Пользователь/Потребитель (User advocate)** *(optional 5th)* | Lived experience: real usage context, switching costs, trust | 1–2 options + usability objections |

Rules for roles (from evidence):
1. **Lens assignment is persistent** within a council run (Creative-MAD's Cognitive Lens Assignment) — a role never switches lens mid-run.
2. **No expertise boasting** ("you are a world-class CPO") — banned by H1 evidence; the lens description states *what to attend to*, not *who you are*.
3. **Model heterogeneity preferred** (dev): e.g. Product+Comms on model family A, Data+Devil's advocate on family B — per H4/andybhall finding. If only one model family is available, the council is flagged "same-model council (weaker diversity evidence)" in the run log.
4. **Read-only**: no role writes project files. Only the main agent (the writer) writes.

---

## 3. When the council activates (routing)

| Trigger | Council mode |
|---|---|
| Step 4 (options) on the **demo project** and on **held-out eval tasks** (dev contour) | **Full** (all roles, full protocol, all measurements) |
| Step 4 in prod, decision classified **high-stakes** (irreversible, >$ threshold, or cross-team) | **Optimized** (see §5) |
| Step 4 in prod, low-stakes | **Off** — multi-lens single-agent prompt only (cheap equivalent); logged as such |
| User explicitly requests `/council` | Full (dev) / Optimized (prod) |

The stakes classification is made by the main agent at the framing checkpoint and confirmed by the human — it is a routing decision, logged with its reason.

---

## 4. Protocol (full version — dev contour)

**Input:** the shared brief (framing artifact + evidence digest), identical for every role. **Output:** `project/council/` with per-role files + synthesis.

```
Phase 0 — Brief freeze (main agent)
  The brief + evidence digest are frozen and hashed. Every role receives the SAME frozen text.
  (Rationale: Cognition "share context"; prevents drifting briefs — a MAST failure mode.)

Phase 1 — Independent divergence (roles run in isolation, NO cross-reading)
  Each role independently produces its options/objections from the frozen brief.
  Roles cannot see each other's outputs in this phase.
  (Rationale: Creative-MAD — cross-reading causes convergence/majority pull; Round-0 positions
   are logged separately because pre-debate positions carry most of the signal — ACL 2026 audit.)

Phase 2 — Structured cross-critique (roles see all Phase-1 outputs)
  Each role reviews ALL options (own + others) against its lens and files objections.
  Mandatory quota: every option must receive ≥1 objection from ≥2 different lenses, or be marked
  "unchallenged" (unchallenged options are a listed risk in the synthesis, per the audit finding
  that agreement is worth less than disagreement).

Phase 3 — Adversarial pass (devil's advocate, always last, always protected)
  The devil's advocate writes the strongest case against the LEADING option (and the strongest
  case for the least-favored option, incl. "keep as is"). This text may not be summarized away
  by the synthesizer; it is included verbatim in the strategy artifact.

Phase 4 — Single-writer synthesis (main agent; the only writer)
  Consolidates options (merging only with explicit provenance), preserves dissent as a
  "разногласия" section, and produces the final option set with per-option objections.
  Agreement count is reported as a *bias warning*, never as validation.

Phase 5 — Human checkpoint
  The PM sees: options, per-option objections, disagreements, and the dissent record.
  The PM chooses or sends back.
```

**Logging (transparency requirement):** every phase writes to `project/council/run-<id>/`: frozen-brief hash, per-role raw outputs, phase timestamps, models used, tokens, and the Round-0 vs post-critique position changes (position-change rate is a council health metric — a council where nobody ever moved is probably performing agreement).

---

## 5. Optimized version (prod contour) — candidate levers, each gated by measurement

| Lever | Mechanism | Expected saving | Quality risk (what we measure) |
|---|---|---|---|
| O1. Fewer roles: Product + Comms + Devil's advocate (drop Data & User to on-demand) | 3 single-shot calls instead of 5 | ~40% | diversity (semantic distance), objection coverage |
| O2. Single round: Phase 1 + Phase 3 only (skip full cross-critique) | removes N² critique calls | ~50% | objection count/quality per option |
| O3. Model tiering: devil's advocate + data on cheap tier, product/comms on mid | tiered routing (H9) | ~40–60% | per-role output quality audit |
| O4. Trigger gating: high-stakes only (already in §3) | skips council entirely on routine tasks | up to 100% on those runs | classification accuracy (expert audit of 10 classifications) |
| O5. Cached brief: brief frozen once, roles called with cached prefix | cache-hit pricing (0.05–0.1× input) | 50–90% of input cost | none (identical tokens) |

Prod default proposal (to be confirmed by Day-5 measurements): **O2 + O3 + O4 + O5, roles = Product + Comms + Devil's advocate** — i.e., one mid-tier divergent pair + one cheap adversarial + cached shared brief, targeting **≤2× the cost of a single synthesis call** (vs 4–5× for the full council) at ≤0.5 rubric-point quality delta and ≥80% of the full council's option diversity.

---

## 6. Measurement plan (owner rule: every feature gets a benchmark)

**Design:** 2×2 A/B on 3 tasks (demo + 2 held-out), all runs logged with tokens/$:

| Arm | Configuration |
|---|---|
| A0 | Single agent (no council, no lenses) — baseline |
| A1 | Multi-lens single-agent prompt (one call, all lenses listed sequentially) — cheap equivalent |
| A2 | Same-model council, full protocol (dev) |
| A3 | Heterogeneous-model council, full protocol (dev) |
| A4 | Optimized council (§5 defaults) — the prod candidate |

**Metrics (pre-registered; report with uncertainty):**
1. **Option diversity** — pairwise semantic distance (embeddings) among final options + count of *substantively* different options (expert-labeled clusters). Rationale: this is what the council is *for* (Creative-MAD metric).
2. **Objection quality** — expert rubric: specificity, evidence-grounding, actionability of objections per option; devil's-advocate output scored separately (H7).
3. **Strategy quality** — expert rubric mapped 1:1 to hackathon criterion 1 (проработанность): facts↔hypotheses separated, options substantively different, objections strong, product↔comms consistency, verification plan present.
4. **Decision-usefulness (secondary)** — pairwise LLM-judge, order-balanced, 2 judge models (protocol in `benchmarks.md` §2.2); reported as iteration signal only, never as the claim.
5. **Cost** — tokens and $ per arm per task; cost per *accepted* option; cost per expert-rubric point (quality/$ Pareto).
6. **Council health** — Round-0 vs post-critique position-change rate; "unchallenged option" count; agreement-count bias warning frequency.

**Decision rule (pre-registered):** the council ships in prod **iff** A3/A4 beat A1 on diversity *and* objection quality by a margin larger than the pre-registered MDD (~1 rubric point / full rank swap), at a cost the prod budget accepts. If A1 ≈ A2/A3 within noise → ship A1 (multi-lens prompt) and record the negative result honestly in the description document. If A3 > A2 (heterogeneity matters) → prod uses heterogeneous-mini (2 families, 3 roles).

**What we will NOT claim:** that the council "thinks better" or reaches truth. Per the evidence, it diversifies and stress-tests; correctness still comes from evidence + deterministic checks + the human checkpoint.

---

## 7. Cost envelope (dev contour — no budget limit; recorded anyway)

Per full council run on one task: ~5 role calls (Phase 1) + ~10 critique calls (Phase 2, each role reads 4 others' outputs — input-heavy) + 1 adversarial + 1 synthesis. At mid-tier rates (~$2/$10 per 1M, cached brief ~$0.2/M): order of **$0.5–2 per full council run** per task — cheap enough to run the full factorial multiple times in dev. (Rates: `llm-pricing-agent-costs.md` §1, §6; cache economics §6.) These are estimates to be replaced by metered COST.md numbers on Day 4–5.

---

## 8. Failure modes we design against (from MAST + the 2026 audits)

| Failure mode | Mitigation in protocol |
|---|---|
| Premature termination (council stops early) | Phase quotas: every option ≥2-lens objections; hook validates phase completeness |
| Sycophantic convergence (roles agree to be polite) | Phase-1 isolation; devil's advocate protected; agreement logged as warning |
| Performed disagreement (tone-driven, not real) | Objections must cite the frozen brief or a logged source; unsupported objections are flagged by the source-check hook |
| Context drift (roles work from different briefs) | Frozen, hashed brief (Phase 0) |
| Lost dissent (synthesizer smooths over disagreement) | Verbatim dissent section mandated; hook checks its presence |
| Cost blowup (rebroadcast) | Artifact-passing, not shared-state rebroadcast; cached prefixes in prod |
