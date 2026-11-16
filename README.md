# strategy-agent

Хакатон «Фабрика Продуктов» (МегаФон), кейс «Стратег Фабрики продуктов».

Папочный ИИ-агент: репозиторий с инструкциями, базой знаний и инструментами,
который ведёт руководителя цифрового продукта от размытого запроса до
обоснованной продуктовой и коммуникационной стратегии — и остаётся с ним
после принятия решения.

Агент открывается в средах типа Cursor / Claude Code / GigaCode / Codex
(единый формат инструкций — `AGENTS.md`); это НЕ программа и НЕ автономный агент.

## Карта документов

| Документ | Что внутри |
|---|---|
| [BRIEF.md](BRIEF.md) | Кейс хакатона, ТЗ, требования владельца, критерии оценки (первоисточник) |
| [PRD.md](PRD.md) | Продуктовое и архитектурное решение: workflow, разделение знаний, routing, Консилиум, двухконтурная стоимость, риски, DoD |
| [ROADMAP.md](ROADMAP.md) | План по дням (16–21.11.2026) с проверяемым артефактом на день; бэклог фич с измерениями |
| [docs/research/benchmarks.md](docs/research/benchmarks.md) | Бенчмарки агентных/исследовательских систем 2025–2026: что измеряют, применимость, матрица «фича → измерение» |
| [docs/research/hypothesis-validation.md](docs/research/hypothesis-validation.md) | Проверка гипотез (persona, мультиагентность, CoT, skills, адвокат дьявола…) с вердиктами и ссылками |
| [docs/research/council-design.md](docs/research/council-design.md) | Фича «Консилиум»: роли, протокол, два контура (dev/prod), план измерений |
| [docs/research/agentic-ecosystem.md](docs/research/agentic-ecosystem.md) | Экосистема «агент-как-папка» 2025–2026: AGENTS.md, skills, hooks, subagents, MCP — что оправдано |
| [docs/research/llm-pricing-agent-costs.md](docs/research/llm-pricing-agent-costs.md) | Актуальные цены API и стоимость агентных прогонов (для двухконтурной модели стоимости) |

## Статус

**День 1 (16.11.2026) — завершён:** исследование, PRD, ROADMAP, research-документы.
**День 2 (16.11.2026) — завершён:** скелет агента, навыки framing/evidence/resume,
скрипты-проверки (44/44 тестов зелёные), 3 хука OpenCode, прогон шагов 0–1
на демо-задаче `demo-retention` с ЧЕКПОИНТОМ 1, прерыванием и возобновлением
из STATE.md.
**Очередь О2 — в работе:** навыки шагов 2–4 (`options`, `strategy-product`,
`strategy-comms`, `verification` + раздел «Шаг 2» в навыке `evidence`),
шаблоны артефактов шагов 2–4, проверка `check_options.py` (67/67 тестов
зелёные). Дальше — по [ROADMAP.md](ROADMAP.md): полный прогон демо-задачи
(`research.md` → `options.md` → `strategy-product.md` → `strategy-comms.md`
→ `verification-plan.md`), затем очередь О3.

## Быстрый старт (целевая среда — OpenCode)

```bash
# 1. Ключ провайдера — только через окружение, никогда в репозиторий:
export STEPFUN_API_KEY=<ключ StepFun>        # прайс и причины: COST.md, §1.8 прайс-документа

# 2. Зависимости плагина хуков (один раз):
cd .opencode && npm install && cd ..

# 3. Прогон агента из корня репозитория:
opencode run "Выполни шаг 0 (рамка) по демо-задаче eval/tasks/demo-retention/task.md"
```

Что происходит внутри: инструкции агента грузятся из `AGENTS.md`
(постоянные инструкции; рабочий черновик, из которого он размещён, — в
`docs/agents-md-staged.md`). Хуки (`.opencode/plugins/strategy-hooks.ts`):
после записи `project/*.md` — `check_sources.py`; после записи `STATE.md` и в
конце сеанса — `check_state.py`; на каждом ассистентском сообщении — строка
учёта в прод-таблицу `COST.md`. Лог хуков — `.opencode/hooks.log` (вне git).

Проверки вручную:

```bash
python3 tests/test_scripts.py                  # 67/67 (stdlib, без зависимостей)
uv run --with pytest python -m pytest tests/ -q # то же через pytest
python3 scripts/check_sources.py project/evidence/*.md
python3 scripts/check_options.py project/options.md  # шаг 3: варианты и возражения
python3 scripts/check_state.py
python3 scripts/cost_report.py
```

Прерывание и возобновление: остановите прогон на середине шага (Ctrl-C или
внешний kill) — затем новый чат: `opencode run "Прочитай STATE.md и LOG.md
(навык resume) и продолжи с места остановки"`.

## Инструменты и шаблоны (очередь О2)

| Что | Файл | Зачем |
|---|---|---|
| Проверка вариантов | `scripts/check_options.py` | ≥3 варианта, среди них «оставить как есть»; у каждого возражение и маркер типа утверждения |
| Навыки шагов 3–4 | `knowledge/skills/options|strategy-product|strategy-comms|verification/SKILL.md` | методика шага; карта «вопрос → навык» — `knowledge/index.md` |
| Шаблоны шагов 2–4 | `templates/research.md`, `options.md`, `strategy-product.md`, `strategy-comms.md`, `verification-plan.md` | копия файла → `project/<артефакт>.md`; шапка каждого шаблона указывает навык и проверки |

## Портируемость (Cursor / Claude Code / Codex / GigaCode / Gemini CLI)

Единый источник истины — `AGENTS.md` (стандарт agents.md). Матрица сред,
замер лимита Codex и адаптеры — `docs/portability.md`. Навыки видны
средам через симлинки `.claude/skills` и `.agents/skills` →
`knowledge/skills`.

**Gemini CLI** (не в целевом списке, но документируется): по умолчанию
грузит `GEMINI.md` и игнорирует `AGENTS.md`. Однострочная настройка —
добавить наш файл в список имён контекста:

```json
{ "context": { "fileName": ["AGENTS.md", "GEMINI.md"] } }
```

(источник: документация Gemini CLI + issue google-gemini/gemini-cli#28227,
проверено 2026-11-16).
