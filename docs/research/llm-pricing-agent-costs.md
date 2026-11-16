# LLM API Pricing & Agent-Run Cost Research (late 2025 / 2026)

**Research date:** 2026-11-16 (all URLs accessed this date unless a publication date is noted)
**Scope:** current list prices per 1M tokens (input / output / cached input), deep-research product costs, typical token counts per agentic run, reasoning-token billing rules, multi-agent vs single-agent token multipliers.
**Rule applied:** every number carries a source. Anything not verifiable from a primary source is explicitly flagged.

---

## 1. API prices per 1M tokens (standard tier, USD)

### 1.1 OpenAI — source: https://developers.openai.com/api/docs/pricing (accessed 2026-11-16)

OpenAI now has a GPT-6 family. "Short context" = ≤272K input tokens; "Long context" = >272K (priced 2x input / 1.5x output for the whole request on 5.x).

| Model | Input $/M | Output $/M | Cached input $/M | Notes |
|---|---|---|---|---|
| gpt-6-astra (flagship) | $10.00 | $50.00 | $1.00 | long ctx: $20 / $75 / $2.00 |
| gpt-6.1-sol | $2.00 | $10.00 | $0.10 | long ctx: $4 / $15 / $0.20 |
| gpt-6.1-terra | $1.00 | $5.00 | $0.05 | long ctx: $2 / $7.50 / $0.10 |
| gpt-6-sol | $2.00 | $10.00 | $0.20 | long ctx: $4 / $15 / $0.40 |
| gpt-6-luna (cheap) | $0.10 | $0.50 | $0.01 | long ctx: $0.20 / $0.75 / $0.02 |
| gpt-5.6-sol | $4.00 | $20.00 | $0.40 | promo price until 2026-11-30; long ctx $8 / $30 |
| gpt-5.6-terra | $2.00 | $12.00 | $0.20 | long ctx $4 / $18 |
| gpt-5.6-luna | $0.20 | $1.20 | $0.02 | |
| gpt-5.5 | $5.00 | $30.00 | $0.50 | >272K: $10 / $45 / $1.00 |
| gpt-5.5-pro | $30.00 | $180.00 | – | |
| gpt-5.4 | $2.50 | $15.00 | $0.25 | >272K: $5 / $22.50 |
| gpt-5.4-pro | $30.00 | $180.00 | – | |
| gpt-5.4-mini | $0.75 | $4.50 | $0.075 | |
| gpt-5.4-nano | $0.20 | $1.25 | $0.02 | |
| gpt-5.2 | $1.75 | $14.00 | $0.175 | |
| gpt-5.1 | $1.25 | $10.00 | $0.125 | |
| gpt-5 | $1.25 | $10.00 | $0.125 | retirement date 2026-12-11 per aggregator aipricelog.com (flag: aggregator-sourced, not seen on OpenAI deprecations page) |
| gpt-5-mini | $0.25 | $2.00 | $0.025 | |
| gpt-5-nano | $0.05 | $0.40 | $0.005 | |
| gpt-5-pro | $15.00 | $120.00 | – | |
| o3 | $2.00 | $8.00 | $0.50 | |
| o3-pro | $20.00 | $80.00 | – | |
| gpt-5-search-api | $1.25 | $10.00 | $0.125 | |
| gpt-5.3-codex | $1.75 | $14.00 | $0.175 | |

- **Tiers:** Batch API = 50% off; "Fast" mode = 2x standard; "Ultrafast" = 6x standard; regional/data-residency endpoints +10%.
- **Web search tool:** $10.00 / 1K calls for reasoning models (retrieved search-content tokens billed at model input rates); $25.00 / 1K calls for non-reasoning models (content tokens free). Same page, accessed 2026-11-16.
- **Deep-research endpoints (June 2025 launch):** `o3-deep-research` $10 in / $2.50 cached / $40 out; `o4-mini-deep-research` $2 in / $0.50 cached / $8 out (source: community.openai.com announcement thread, June 2025; also listed on help.openai.com rate card). **Flag:** these models no longer appear on OpenAI's current pricing page (per hyperresearch.ai analysis) — they appear retired, with standard models + web search as the replacement path. LiteLLM still lists them (added Jul 2025).

### 1.2 Anthropic — source: https://platform.claude.com/docs/en/about-claude/pricing (accessed 2026-11-16)

| Model | Input $/M | Output $/M | 5m cache write | 1h cache write | Cache hit (read) |
|---|---|---|---|---|---|
| Claude Fable 5.2 | $8 | $40 | $10 | $16 | $0.20 |
| Claude Mythos 5.2 (limited availability) | $8 | $40 | $10 | $16 | $0.20 |
| Claude Fable 5.1 / Mythos 5.1 | $10 | $50 | $12.50 | $20 | $0.25 |
| Claude Opus 5.5 | $4 | $20 | $5 | $8 | $0.20 |
| Claude Opus 5 / 4.8 | $5 | $25 | $6.25 | $10 | $0.50 |
| Claude Sonnet 5.5 | $2 | $10 | $2.50 | $4 | $0.10 |
| Claude Sonnet 5 | $2 | $10 | $2.50 | $4 | $0.20 |
| Claude Sonnet 4.6 | $3 | $15 | $3.75 | $6 | $0.30 |
| Claude Haiku 5.5 (prompt ≤100K) | $0.10 | $0.50 | $0.125 | $0.20 | $0.01 |
| Claude Haiku 5.5 (prompt >100K) | $0.50 | $2.50 | $0.625 | $1.00 | $0.05 |
| Claude Haiku 4.5 | $1 | $5 | $1.25 | $2 | $0.10 |

- Cache reads: 0.1x base input on most models; 0.05x on Opus 5.5 / Sonnet 5.5; 0.025x on Fable/Mythos 5.x. Batch = 50% off. US-only inference (`inference_geo`) = 1.1x all categories. "Fast mode" = 2x (e.g., Opus 5.5 fast: $8 / $40 — Anthropic list-price PDF, 2026-11-09, assets.claude.com).
- **Cost-modeling gotcha (official):** Claude 4.7+ models use a new tokenizer that produces ~30% more tokens for the same text. Same page.
- Claude Managed Agents: tokens at standard rates + session runtime (docs example: $0.08/hour); web search inside a session $10 / 1K searches. Same page.
- Sonnet 5's $2/$10 was introductory pricing made permanent (scheduled increase to $3/$15 cancelled). Same page footnote.

### 1.3 Google — source: https://aistudio.google.com/docs/pricing (accessed 2026-11-16)

Output prices **include thinking tokens**. Note the dated price steps (relevant for a 2026-12+ production circuit).

| Model | Input $/M | Output $/M (incl. thinking) | Cached input $/M |
|---|---|---|---|
| Gemini 4 Carbon | $2.00 → $4.00 (2026-12-01) | $10.00 → $20.00 | $0.10 → $0.20 |
| Gemini 4 Argon | $2.00 → $4.00 (2026-12-01) | $10.00 → $20.00 | $0.10 → $0.20 |
| Gemini 4 Hydrogen | $1.50 | $7.50 | $0.075 |
| Gemini 3.8 Flash | $0.75 → $1.50 (2027-01-01) | $3.75 → $7.50 | $0.075 → $0.15 |
| Gemini 3.6 Flash | same as 3.8 Flash | same | same |
| Gemini 3 Flash (legacy) | $0.50 | $3.00 | $0.05 |
| Gemini 3.5 Flash-Lite | $0.30 | $2.50 | $0.03 |
| Gemini 3.1 Flash-Lite | $0.25 | $1.50 | $0.025 |
| Gemini 3.1 Pro Preview | $2.00 (≤200K) / $4.00 (>200K) | $12.00 / $18.00 | $0.20 / $0.40 |
| Gemini 2.5 Pro | $1.25 (≤200K) / $2.50 (>200K) | $10.00 / $15.00 | $0.125 / $0.25 |
| Gemini 2.5 Flash | $0.30 | $2.50 | $0.03 |
| Gemini 2.5 Flash-Lite | $0.10 | $0.40 | $0.01 |

- **Search grounding:** 5,000 free requests/month (Gemini 3+ models), then **$14 / 1,000 requests** (daily cap 1,500 RPD on the Developer API; Vertex quota 1M/day). Gemini 2.5 models: 1,500 RPD free, then $35 / 1,000 grounded prompts. Retrieved grounding context is not billed as input tokens.
- Agent pricing (same page): "Gemini Deep Research agent" and managed agents bill all inference at standard list rates, **including intermediate input / reasoning tokens generated during agentic loops**, plus tool fees.

### 1.4 DeepSeek — source: https://api-docs.deepseek.com/quick_start/pricing/ (accessed 2026-11-16)

Peak = 01:00–04:00 and 06:00–10:00 UTC Mon–Fri; off-peak = half price.

| Model | Input cache-hit (off-peak / peak) | Input cache-miss (off-peak / peak) | Output (off-peak / peak) |
|---|---|---|---|
| deepseek-flash (V4.1-Flash-1017), 1M ctx | $0.003 / $0.006 | $0.15 / $0.30 | $0.60 / $1.20 |
| deepseek-v4-pro (V4-Pro-0813), 1M ctx | $0.022 / $0.044 | $0.66 / $1.32 | $1.98 / $3.96 |

- Context caching is automatic (disk-based prefix cache); no SDK changes. Thinking mode is default-on; **reasoning tokens are billed as output** (deepseek.ai/pricing, verified 2026-09-18 per that page).
- Tools: web search $0.75 / 1K searches; web fetch $0.75 / 1K; file parsing/OCR $0.225 / 1K pages; TTS $0.45 / 10K chars; ASR $0.116 / hour. Same page.

### 1.5 xAI (Grok) — sources: https://x.ai/api and https://models.litellm.ai/models/grok-4.7 (accessed 2026-11-16)

| Model | Input $/M | Output $/M | Cached input $/M | Notes |
|---|---|---|---|---|
| grok-4.7 (flagship) | $2.00 | $6.00 | $0.50 | 500K ctx; batch $1.60 / $4.80; >200K input: $4 / $12 |

- x.ai landing page states "usage-based pricing from $2/M tokens" and confirms grok-4.7 at $2 in / $6 out. docs.x.ai is region-blocked from this environment — full model table unverified (flag).

### 1.6 Qwen (Alibaba) — sources: https://help.aliyun.com/en/model-studio/model-pricing (CNY, accessed 2026-11-16) and https://models.litellm.ai/providers/dashscope (USD aggregator)

| Model | Input | Output | Notes |
|---|---|---|---|
| qwen3.8-max | CNY 12 / M | CNY 36 / M (≈ $1.7 / $5.1 at ~7.1 CNY/USD) | International USD price $2 / $6 per LiteLLM (flag: aggregator) |
| qwen4-max | CNY 10 / M | CNY 30 / M | newest Max on Alibaba's page |
| qwen3.8-flash | CNY 0.8 / M | CNY 2.7 / M | intl $0.15 / $0.47 per LiteLLM (flag) |
| qwen3.7-flash | CNY 0.2 / 0.6 / 1.2 (tiered ≤32K / ≤256K / ≤1M) | CNY 0.8 / 2.4 / 4.8 | |

- Output price = "Chain of thought + answer" (reasoning billed as output). Batch = 50% off. Context cache: explicit cache creation billed at 125% of input price, cache hits at 10%.

### 1.7 Perplexity (search-augmented models) — sources: litellm/llmprices snapshots Oct 2026 + cabina.ai pricing guide (accessed 2026-11-16; token prices cross-checked across two aggregators, request fees single-source — flag)

| Model | Input $/M | Output $/M | Request fee / 1K calls (low/med/high) |
|---|---|---|---|
| sonar | $1.00 | $1.00 | $5 / $8 / $12 |
| sonar-pro | $3.00 | $15.00 | $6 / $10 / $14 |
| sonar-reasoning-pro | $2.00 | $8.00 | $6 / $10 / $14 |
| sonar-deep-research | $2.00 | $8.00 | no request fee; instead: citation tokens $2/M, reasoning tokens $3/M, search queries $5/1K |

- Perplexity Agent API: model tokens + $0.0025 / web search + $0.0005 / URL fetch (hyperresearch.ai comparison page, accessed 2026-11-16).
- Consumer: Pro $20/mo, Max $200/mo (claude.com-style plans; perplexity pricing via hyperresearch comparison).

### 1.8 StepFun — source: https://platform.stepfun.ai/docs/en/guides/pricing/details (accessed 2026-11-16)

| Model | Input (cache miss) $/M | Input (cache hit) $/M | Output $/M |
|---|---|---|---|
| step-5-preview | $1.00 | $0.10 | $2.70 |
| step-3.7-flash | $0.20 | $0.04 | $1.15 |
| step-3.5-flash | $0.10 | $0.02 | $0.30 |

- Дословно со страницы прайса: для step-5-preview цена cache-miss включает
  запись нового контента в кэш; выходные токены включают и reasoning, и
  финальный ответ (reasoning не тарифицируется поверх output).
- Кросс-проверка двумя агрегаторами (accessed 2026-11-16): artificialanalysis.ai
  и pricepertoken.com дают те же $1.00 / $0.10 / $2.70 для step-5-preview.
- Это международный прайс-лист; целевая среда демо (OpenCode) обращается к
  `https://api.stepfun.ai/step_plan/v1`. Оценки в `COST.md` считаются по этой
  таблице.

---

## 2. Deep-research product costs (published per-task figures)

| Product | Published cost | Source |
|---|---|---|
| OpenAI Deep Research API, o3-deep-research | $10 / $40 per 1M in/out ($2.50 cached in). Measured: **~$100 for 10 test queries (~$10/query), single calls up to ~$30** | Artificial Analysis, X post, 2025-07-05 (x.com/ArtificialAnlys/status/1940896348364210647) |
| OpenAI o4-mini-deep-research | $2 / $8 per 1M. Measured: **$9.18 for 10 queries (~$0.92/query)** | same |
| OpenAI Deep Research (ChatGPT consumer) | 5–30 min per task (OpenAI, launch Feb 2025). Quotas: Free 5 "lightweight"/mo; Plus 10/mo (2026) or 25/mo (June 2025 per Wikipedia); Pro $200: 250/mo; Business/Enterprise ≈ 50 credits per task | fastcompany.com 2025-02; en.wikipedia.org/wiki/ChatGPT_Deep_Research (June 2025); valueaddvc.com blog 2026 (flag: blog); help.openai.com rate card |
| OpenAI DR inference cost on a benchmark | **$1.80 / query** (ScholarQA-CSv2); Ai2 ScholarQA on Claude Sonnet $1.30 / query | arXiv 2511.19399 (DR Tulu), Nov 2025 |
| o3-deep-research on DeepResearchBench | **$1.27 ± $0.26 / query**, 10.5 ± 4.2 min, 4,135 ± 1,081 reasoning tokens + 15,249 ± 5,511 output tokens | UCSD NIPS ERW 2025 paper (cseweb.ucsd.edu/~yiying/2025_NIPS_ERW_Deep_Research_Perf_Study.pdf) |
| GPT-5 (same benchmark) | $0.28 / query, 5.5 min | same |
| **Gemini Deep Research agent** | **Google's own estimate: ~$1.00–$3.00 per task (standard agent), ~$3.00–$7.00 per task (Max agent)**; billed at standard Gemini rates incl. intermediate reasoning tokens | aistudio.google.com/docs/deep-research (accessed 2026-11-16) |
| Perplexity Deep Research | No published $/report; API = sonar-deep-research rates above; Agent API ~$0.12–$0.14 per request on Perplexity's own benchmarks | hyperresearch.ai/alternatives/deep-research-pricing (accessed 2026-11-16) |
| Parallel Task API | $0.10 (pro) to $2.40 (ultra processors) per completed task | same |
| Valyu DeepResearch | ~$0.63 standard / $3.13 heavy / $15.63 max per task (pay-as-you-go) | same |
| Hyperresearch (third-party) | $9 Light / $49 Deep flat per run | same |

- **Key structural finding (hyperresearch.ai, accessed 2026-11-16):** none of the consumer apps (ChatGPT, Claude, Gemini, Perplexity) publishes a dollar cost per report or a report count per plan — only the APIs and third-party DR vendors publish per-task numbers.

---

## 3. Typical token counts per agentic run

| Measurement | Value | Source |
|---|---|---|
| Agentic coding task vs. single-round reasoning / multi-round chat | **~3,500x more tokens** than single-round reasoning; **~1,200x more** than multi-round chat; input tokens dominate cost even with caching | arXiv 2604.22750 "How Do AI Agents Spend Your Money?" (Stanford Digital Economy Lab), 2026 |
| Run-to-run variance (same task, same agent) | up to **30x** difference in total tokens; most expensive problem ~7M more tokens than cheapest | same |
| Model efficiency spread (same tasks) | Kimi-K2 and Claude Sonnet 4.5 consumed >1.5M more tokens per task than GPT-5 on average | same |
| Enterprise agentic task (22 locked tasks, 6 models) | **14.2K tokens / task, $0.21 blended cost / task** under a conventional agent loop ($0.16–$0.25 by model); orchestration "harness" cut it to 8.8K tokens / $0.12 per task (−41% cost, −38% tokens) at equal quality | arXiv 2607.06906 "The Harness Effect", 2026 |
| Deep-research run (o3-deep-research) | ~4.1K reasoning + ~15.2K output tokens per query on DeepResearchBench; retrieved context (input side) dominates total tokens — "final answer generation consumes most tokens due to the lengthy retrieved context" | UCSD NIPS ERW 2025 |
| Long research report output size (worked example, assumed counts) | 50K output tokens per research report | hyperresearch.ai example (flag: assumed, not measured) |
| Multi-agent research session (Anthropic Research) | "a single Research session can use millions of tokens" (subagent waves each run their own context) | anthropic.com/engineering/built-multi-agent-research-system, 2025-06-13 |
| Worked cost example: research call on gpt-5.6-sol, 50 searches + 1M input + 50K output | 50 × $0.01 + 1M × $4 + 50K × $20 = **$5.50 per call** | hyperresearch.ai/alternatives/openai-deep-research-api (accessed 2026-11-16; token counts assumed) |

**No vendor publishes tokens-per-report figures.** Treat the table above as the best available anchors; instrument your own runs (the Stanford paper notes even frontier models cannot predict their own token usage — they systematically underestimate).

---

## 4. Reasoning-token pricing notes

- **OpenAI:** reasoning tokens are counted in `output_tokens` (itemized in `output_tokens_details.reasoning_tokens`) and **billed at the output rate; there is no separate reasoning price**. A 300-token visible answer after 3,000 reasoning tokens bills ~3,300 output tokens. Sources: help.openai.com/en/articles/4936856; developers.openai.com reasoning guide (via community.openai.com billing explainer, 2026).
- **Anthropic:** thinking tokens are **billed as output tokens** even when not returned; current-turn thinking also counts toward `max_tokens`; prior-turn thinking blocks that are preserved are billed as **input** tokens. With summarized thinking you pay for the full internal thinking tokens, not the summary. Source: docs.anthropic.com extended-thinking page (accessed 2026-11-16).
- **Google:** output price explicitly "**includes thinking tokens**" on every Gemini 3/4 model (aistudio pricing page).
- **DeepSeek:** in thinking mode (default), **reasoning tokens are billed as output** (deepseek.ai/pricing).
- **Qwen:** output price = "**Chain of thought + answer**" (help.aliyun.com pricing page).
- **Perplexity sonar-deep-research:** unusual split — reasoning tokens billed separately at $3/M, citation tokens at $2/M, plus $5/1K search queries (cabina.ai guide; flag: single third-party source).
- **Implication for the production circuit:** reasoning effort is a direct cost dial on every provider. OpenAI/Azure docs suggest reserving ≥25K tokens of output budget for reasoning+output on new workloads (learn.microsoft.com Azure Foundry reasoning guide, 2026).

---

## 5. Multi-agent vs single-agent cost data (2025–2026)

| Finding | Multiplier / data | Source |
|---|---|---|
| Anthropic Research system (orchestrator + parallel subagents) | Agents use **~4x more tokens than chat**; **multi-agent systems ~15x more tokens than chat**. Multi-agent (Opus 4 lead + Sonnet 4 subagents) beat single-agent Opus 4 by **90.2%** on internal research eval; token usage alone explains **80%** of BrowseComp performance variance | anthropic.com/engineering/built-multi-agent-research-system, 2025-06-13 |
| BenchAgent study (6 MAS configs vs single-agent Core, GPT-4.1) | ChatEval: **4.34x tokens** of Core; LLM-Debate: **1.39x tokens**. Only EvoAgent beat Core accuracy (+3.05 pts); the other five MAS trailed by 1.71–8.76 pts | arXiv 2606.05670, 2026 |
| MAST failure analysis (1,642 traces, 7 production MAS frameworks) | Task failure rates 41%–86.7%; measured **token duplication of 86% (flat topologies) / 72% (linear)** — redundant context retransmission, not generation, is the dominant cost driver | Cemri et al. (MAST), cited in arXiv 2603.15183, 2026 |
| Broadcast synchronization overhead model | Naive full-state rebroadcast costs O(n × S × \|D\|): 5 agents × 50 steps × 8,192-token artifact = **2.05M tokens**, mostly unchanged context resent | arXiv 2603.15183 "Token Coherence", 2026 |
| Clinical-workload study (orchestrated multi-agent vs single agent, batches of 5–80 tasks) | At 80 tasks: multi-agent GPT-4.1-mini used **60K tokens** vs single-agent **3.9M tokens (65x gap)** while single-agent accuracy collapsed (96% → 33.9%) | medRxiv doi 10.1101/2025.08.22.25334049, 2025 |
| Parallelization hidden costs (SquidAgent) | Parallel multi-agent runs introduce re-exploration + alignment token costs that can erase speedup; token-budget scheduling recovers 2.2x throughput vs Claude Code | arXiv 2610.08647, 2026 |

**Reading for the "Консилиум" (council) design:** multi-agent overhead is real and large (1.4x–15x depending on architecture), but it is architecture-driven, not inherent: the duplication comes from rebroadcasting shared context, which artifact-passing / coherent invalidation designs largely eliminate (95% token savings in simulation). A council of 4–5 roles run as independent single-shot evaluations (no shared-state rebroadcast) costs ~4–5x a single call; a recursive orchestrator-worker loop is what produces the 15x figure.

---

## 6. Cheapest-to-frontier ladder (for the two-circuit cost model)

| Tier | Example models (in/out per 1M) |
|---|---|
| Ultra-cheap | gpt-5-nano $0.05/$0.40 · gpt-6-luna $0.10/$0.50 · Gemini 2.5 Flash-Lite $0.10/$0.40 · deepseek-flash $0.15/$0.60 (off-peak) |
| Cheap | gpt-5-mini $0.25/$2 · gpt-5.4-nano $0.20/$1.25 · Gemini 3.1 Flash-Lite $0.25/$1.50 · Gemini 3.5 Flash-Lite $0.30/$2.50 · Gemini 2.5/3.x Flash $0.30–0.75/$2.50–3.75 · qwen3.8-flash ~$0.15/$0.47 (aggregator) |
| Mid | gpt-5.1 $1.25/$10 · gpt-5-search-api $1.25/$10 · Gemini 2.5 Pro $1.25/$10 · Claude Sonnet 5.5 $2/$10 · Claude Haiku 5.5 $0.10/$0.50 (≤100K) · deepseek-v4-pro $0.66/$1.98 (off-peak) · grok-4.7 $2/$6 |
| Frontier | Claude Opus 5.5 $4/$20 · gpt-5.6-sol $4/$20 · gpt-6.1-sol $2/$10 · Gemini 4 Carbon/Argon $2/$10 (promo, doubling 2026-12-01) · gpt-5.5 $5/$30 |
| Max-reasoning "pro" tiers | gpt-5.5-pro $30/$180 · gpt-5-pro $15/$120 · o3-pro $20/$80 · Claude Fable 5.2 $8/$40 |

Cache economics matter as much as headline price: cached input is 10% of base on OpenAI/Anthropic (5% on Opus 5.5/Sonnet 5.5, 2.5% on Fable/Mythos), ~2% on DeepSeek cache-hit ($0.003 vs $0.15). For an agent that resends a large stable system prompt + knowledge base every turn, effective input cost can drop 50–98%.

---

## 7. Unverified / flagged items

1. **docs.x.ai full model table** — region-blocked from this environment; only grok-4.7 verified (x.ai landing FAQ + LiteLLM).
2. **Qwen USD prices** — official Alibaba page publishes CNY (Beijing region) only; USD figures are LiteLLM-sourced (aggregator).
3. **Perplexity request fees and sonar-deep-research surcharges** — single third-party source (cabina.ai); token rates cross-checked with two aggregators.
4. **gpt-5 retirement date 2026-12-11** — aggregator (aipricelog.com), not seen on OpenAI's deprecations page.
5. **o3-deep-research / o4-mini-deep-research current availability** — absent from OpenAI's current pricing page (per hyperresearch); June-2025 prices verified from OpenAI's own community announcement.
6. **ChatGPT consumer deep-research quotas** — OpenAI does not publish exact counts; Wikipedia (June 2025) and a 2026 blog disagree on Plus-tier counts (25 vs 10/mo).
7. **"Tokens for a long strategy report"** — no vendor-published figure exists; the 50K-output-token example is explicitly an assumption in the source. Recommend instrumenting your own runs.
8. **Gemini 4 price step on 2026-12-01** and **Gemini 3.x Flash price step on 2027-01-01** — verified on Google's page; production cost models after those dates must use the higher rates.
9. All Perplexity/Anthropic consumer plan prices are subscription features, not API rates; deep-research "per task" costs inside subscriptions are not published by any vendor.

---

## Appendix — Dev-contour cost ledger: Day-1 research (2026-11-16, metered)

Owner requirement: "фиксируем, сколько стоили исследования". Actual metered token usage of the two research subagents that produced `agentic-ecosystem.md` and this pricing file:

| Research stream | Input tokens | Output tokens | Est. cost @ Sonnet 5.5 list ($2/$10 per 1M, no cache discount) |
|---|---|---|---|
| Agentic ecosystem research (75+ sources, 23 API calls) | 3,170,802 | 25,055 | ~$6.59 |
| Pricing & agent-cost research (official pricing pages + papers) | 1,019,124 | 23,747 | ~$2.28 |
| **Subtotal (2 subagents)** | **4,189,926** | **48,802** | **~$8.87** |
| Orchestrator turns (search, verification, doc authoring) | not metered by runtime (cost_status: unknown) | — | not reported — see note |

Notes: (1) the $8.87 is an upper bound at full input price; with prompt-cache economics (0.05–0.1× input on repeated prefixes) the realistic figure is closer to ~$1.3–2. (2) The orchestrator's own usage is not metered by the current runtime and is therefore **not** estimated — flagged honestly rather than invented. (3) Total dev-contour spend will be accumulated in `COST.md` from Day 2 onward and reported in the final description document.

