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
| [docs/research/measurements.md](docs/research/measurements.md) | Измерения фич (Консилиум, устойчивость, решения, портируемость, held-out, MCP): «фича → метрика → результат → решение» + стенд О4/О5 |
| [docs/research/prod-council-lite.md](docs/research/prod-council-lite.md) | Прод-конфигурация Консилиума (council-lite): триггер, роли, $/run по шагам, сверка оценки с metered |
| [docs/routing.md](docs/routing.md) | Маршрутные решения: процесс/модель/инструмент по шагу + лог решений с причинами |
| [docs/portability.md](docs/portability.md) | Портируемость: smoke-матрица сред, лимит Codex, адаптеры (GigaCode, Gemini CLI) |

## Статус

**День 1 (16.11.2026) — завершён:** исследование, PRD, ROADMAP, research-документы.
**День 2 (16.11.2026) — завершён:** скелет агента, навыки framing/evidence/resume,
скрипты-проверки, 3 хука OpenCode, прогон шагов 0–1 на демо-задаче
`demo-retention` с ЧЕКПОИНТОМ 1, прерыванием и возобновлением из STATE.md.
**О2 — завершён:** полный обязательный путь на демо-задаче (research →
options → 3 стратегии), 67/67 тестов на момент приёмки.
**О3 — завершён (ветка `feat/o3-extra-level`):** Консилиум полной версией
(протокол + лог фаз + замеры; прод-кандидат — мульти-линза одним вызовом),
routing-таблица, устойчивость (retry/деградация/восстановление STATE) +
3 fault-injection прогона, портируемость (адаптеры, матрица сред),
`project/decisions.md` + навык `decisions`, held-out задача
«ДомКниг» (полный путь, $3.35), решение по MCP web-search (осознанный
отказ с данными). 116/116 тестов зелёные. Следующие очереди — О4
(стенд измерений) и О5 (оптимизация прода) по [ROADMAP.md](ROADMAP.md).

**О4 — в работе (ветка `feat/o4-measurements`):** стенд измерений.
- Абляция слоёв L0–L4 (TASK-hermes-10): на одном замороженном брифе
  обычный чат даёт 24/25 по типовой рубрике, +AGENTS.md 30/32,
  +навыки 37/38, +гейт проверок 37/36, продукт 39/40 — прирост несут
  инструкции и навыки (выше MDD на обеих задачах), гейт проверок
  держит целостность, остаточная сложность агента — на границе шума
  (measurements.md §23.5; ответ на требование ТЗ «каждый компонент
  оправдывает сложность»).
- Агент-критик с изолированным контекстом: навык `critic` + рубрика
  `eval/rubrics/hackathon-criteria.md` (1:1 из критериев хакатона) +
  матрица 26 прогонов (critic vs self) — механизм **оправдан** по
  предрегистрированному правилу (measurements.md §12).
- Браузер: живая ре-проверка 11/11 URL из evidence и артефактов, 40+
  цитат сверены, 2 расхождения зафиксированы в evidence (§13).
- Мультинаправленные A/B-замеры (eval/run_ab.py): руки шага 3
  (skill / critic-loop / council-lite) на демо и held-out —
  council-lite бьёт базу на обеих задачах (+4/+4) (§14); итерация по
  дизайну навыков (lean / hybrid — гипотеза владельца, BRIEF п.21).
- Бенчмарк из открытого репозитория: DABstep (Adyen/HF, CC-BY-4.0) в
  Docker на step-5 — dev-10: 7/10, $1.27 (proxy, §15).
- 135/135 тестов зелёные. Решения для выбора владельца —
  `docs/research/o4-report.md`.

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
python3 -m pytest tests/ -q                        # 207/207 (или: python3 tests/test_scripts.py)
python3 scripts/check_sources.py project/brief.md project/evidence/*.md project/decisions.md
python3 scripts/check_options.py project/options.md  # шаг 3: варианты и возражения
python3 scripts/check_decisions.py project/decisions.md  # шаг 5: реестр решений
python3 scripts/council_quota.py project/council/run-*/  # протокол Консилиума
python3 scripts/check_citations.py project/evidence/*.md  # резолвимость ссылок
python3 scripts/check_evidence_links.py --task all  # число → содержание evidence (демо + held-out)
python3 scripts/check_state.py                     # демо-задача
python3 scripts/recover_state.py                   # если STATE.md битый — восстановит из git
python3 scripts/cost_report.py
```

Проверки held-out задачи (артефакты в `eval/tasks/heldout-growth-segment/artifacts/`):
`check_sources.py` по каждому артефакту, `check_options.py` по options.md,
`check_state.py` по `artifacts/STATE.md`, `check_evidence_links.py --task heldout-growth-segment`.

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
