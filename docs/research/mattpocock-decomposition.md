# Декомпозиция скиллов mattpocock/skills — устройство механик и адаптация под лидер-агента

> TASK-hermes-14 §1 (BRIEF п.26). Задача НЕ скопировать, а понять устройство и
> адаптировать под помощника руководителя (не код).
> Источник: https://github.com/mattpocock/skills («Skills For Real Engineers.
> Straight from my .agents directory» — дословно из README репозитория).
> Состояние репы на доступ 2026-11-17: 326 323 звезды, MIT, ветка main,
> последний пуш 2026-11-17T10:13:27Z (GitHub API, факт).
> Все цитаты — дословные span'ы из файлов репы по ссылкам
> `https://github.com/mattpocock/skills/blob/main/<path>` (дата доступа
> 2026-11-17). Разбор идёт по механикам, а не по скиллам: что в SKILL.md,
> что вынесено, что агент готовит сам, что проверяет, что не грузится.

## 0. Философия в одном абзаце (основание для всех механик)
Источник разбора: https://github.com/mattpocock/skills/blob/main/README.md (дата доступа 2026-11-17).

README репы называет четыре failure mode, против которых построены скиллы:
misalignment («No-one knows exactly what they want» — The Pragmatic
Programmer), разный язык агента и эксперта (« Agents are usually dropped into
a project and asked to figure out the jargon as they go. So they use 20 words
where 1 will do»), отсутствие обратной связи («Without feedback on how the
code it produces actually runs, the agent will be flying blind») и комок
грязи («agents can radically speed up coding, they also accelerate software
entropy»). Отсюда же и стиль: «These skills are designed to be small, easy to
adapt, and composable. They work with any model.»

Для лидер-агента перевод: (1) misalignment → grill-механика и ЧЕКПОИНТЫ;
(2) жаргон → единый словарь проекта (у нас — маркеры
[факт]/[гипотеза]/[прогноз]/[допущение] и STATE.md как словарь состояния);
(3) обратная связь → гейты check_* и критик с изолированным контекстом;
(4) энтропия → measurements.md и анти-круг (BRIEF п.20).

## 1. Карта механик (сводка)

| # | Механика | У mattpocock | Применимость к лидер-агенту |
|---|---|---|---|
| M1 | Progressive disclosure | тело SKILL.md миниатюрно, хвосты — в вынесенные файлы | ПРИМЕНЯТЬ (частично уже есть) |
| M2 | Роутер-скилл | ask-matt карта «ситуация → скилл» | ПРИМЕНЯТЬ (knowledge/index.md — наш роутер) |
| M3 | Buckets со стадированием | promoted / misc / in-progress / deprecated | АДАПТИРОВАТЬ (черновики навыков до замера) |
| M4 | Model- vs user-invoked | disable-model-invocation + policy | АДАПТИРОВАТЬ (скиллы, которые тянет только человек) |
| M5 | Файлы, которые агент готовит сам | GLOSSARY+ADR, workflows+NOTES, teaching-workspace, handoff, wayfinder-map, research-файл | АДАПТИРОВАТЬ (STATE/LOG — уже есть; пробелы ниже) |
| M6 | Wiki как долговременная память | chief-of-staff: index + страницы + ingest/query/lint, «write history, not the present» | АДАПТИРОВАТЬ (STATE.md + LOG.md по той же логике) |
| M7 | Grill-механика | раунды вопросов, frontier, рекомендованный ответ, факты — задача агента | ПРИМЕНЯТЬ (уже близко к ЧЕКПОИНТАМ) |
| M8 | Проверочные механики внутри скиллов | scripts/ в скилле: PreToolUse hook exit 2; hitl-loop.template.sh (человек в терминале → KEY=VALUE) | ПРИМЕНЯТЬ (у нас hooks + гейты; hitl-паттерн — пробел) |
| M9 | Retro как улучшение среды | категории: navigation pointer / automated check / standards / AGENTS.md hygiene / tool economy; mechanical → deterministic check | ПРИМЕНЯТЬ (аналог: очередь замеров; retro очереди — пробел) |
| M10 | Изоляция подзадач | «Start every subagent with a fresh context window»; code-review двумя параллельными субагентами | ПРИМЕНЯТЬ (уже: изолированный критик, два критика §26) |
| M11 | Инварианты поддержки репы скиллов | README/plugin.json/docs синхронны, «a router that lies», canonical install block | АДАПТИРОВАТЬ (гейт синхронности индекса) |
| M12 | Код-механики (tdd, pr, to-spec, to-tickets, implement, domain-modeling, diagnosing-bugs, code-review) | инженерные дисциплины | НЕПРИМЕНИМЫ буквально; переносимы принципы (см. §8) |

## 2. Progressive disclosure (M1) — что в SKILL.md, что вынесено
Источник разбора: https://github.com/mattpocock/skills/blob/main/skills/engineering/prototype/SKILL.md, https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/SKILL.md, https://github.com/mattpocock/skills/blob/main/.agents/invocation.md (дата доступа 2026-11-17).

Устройство у источника: тело SKILL.md — короткая дисциплина, ссылки ведут в
файлы того же скилла, которые читаются только по надобности. Примеры:

- `skills/engineering/prototype/SKILL.md` (2 923 байта): «Pick a branch …
**"Does this logic / state model feel right?"** → [LOGIC.md](LOGIC.md) …
**"What should this look like?"** → [UI.md](UI.md)» — развилка вынесена в
  два файла (6 036 и 6 913 байт), тело остаётся картой.
- `skills/engineering/tdd/SKILL.md` (3 629 байт) + `tests.md` (2 214) +
  `mocking.md` (1 481) — уточнения читаются по ситуации.
- `skills/engineering/diagnosing-bugs/SKILL.md` (8 664) +
  `scripts/hitl-loop.template.sh` (1 312).
- `skills/engineering/wayfinder/SKILL.md` (12 408) — самый большой;
  шаблон тела тикета и карты вынесен в блоки кода внутри SKILL.md, но
  трекер-специфика — «Consult the tracker doc's "Wayfinding operations"
  section», то есть в вынесенный трекер-документ.
- `skills/engineering/software-factory/SKILL.md` (6 108) +
  `RUNNERS.md` / `TICKET-TRACKERS.md` / `GIT-HOSTS.md` /
  `OBSERVABILITY-PLATFORMS.md` / `EXAMPLE-TASKS.md` — «словарь» разбит на
  файлы по поддоменам.

Почему это работает (механика, а не стиль): тело скилла грузится целиком при
входе, хвост — только когда задача дошла до него. CLAUDE.md фиксирует
обратное правило для ссылок между скиллами: «Shared reference docs live
inside the skill that owns them; other skills reach that material by calling
the Skill tool with it, not by linking across folders»
(`.agents/invocation.md`).

Применимость: у нас progressive disclosure заявлен в `knowledge/index.md»
(«индекс всегда в контексте, тел навыков нет») — подход подтверждён внешним
живым образцом. Адаптация: (а) выносить хвосты навыков шагов в
`references/` внутри навыка (сейчас курация держит всё в одном SKILL.md —
это измерено как лучшее качество, human ground truth 3:0, BRIEF п.27, но
объём тела — отдельный риск: шаблон skills_k3 stats растёт); (б) синхронный
индекс (M11). Неприменимо буквально: `agents/openai.yaml` — метаданные
Codex-ханессера, у нас такого слоя нет.

## 3. Роутер (M2) и инвариант «роутер не врёт» (M11)
Источник разбора: https://github.com/mattpocock/skills/blob/main/CLAUDE.md, https://github.com/mattpocock/skills/blob/main/.agents/invocation.md, https://github.com/mattpocock/skills/blob/main/.agents/install-block.md (дата доступа 2026-11-17).

ask-matt описан в CLAUDE.md как «the router that maps every user-reachable
skill and how they relate», с правилом поддержки: «whenever you add, rename,
remove, or change how a user-reachable skill fits the flows, re-read
`ask-matt`'s `SKILL.md` and update it so the map stays accurate: a new skill
it never mentions, or a stale one it still routes to, is a router that lies.»

Порядок «один источник правды» держится и для остального: «Each skill entry
in the top-level `README.md` must link the skill name to its `SKILL.md`»;
«Every `SKILL.md` is either user-invoked … or model-invoked»; канонический
install-block живёт в одном файле (`.agents/install-block.md`: «One install
story, one wording … Change it here first, then propagate»).

Применимость: knowledge/index.md — наш ask-matt. Пробел: у нас НЕТ механики,
которая ловит рассинхрон индекса и навыков (скилл добавлен, строка в индексе
не появилась). Адаптация — дёшево: гейт `scripts/check_skill_index.py`
(индекс ↔ фактические SKILL.md, обе стороны). Buckets и README-зеркала
не нужны: у нас один knowledge-слой.

## 4. Buckets и стадирование (M3) — как скиллы не перегружают репу
Источник разбора: https://github.com/mattpocock/skills/blob/main/CLAUDE.md, https://github.com/mattpocock/skills/blob/main/skills/in-progress/README.md (дата доступа 2026-11-17).

CLAUDE.md: «`engineering/`: daily code work; `productivity/`: daily non-code
workflow tools; `misc/`: kept around but rarely used, not promoted;
`in-progress/`: beta: public on purpose, feedback wanted, not shipped in the
plugin; `deprecated/`: no longer used». И правило проводки: «The Claude Code
plugin ships exactly the promoted set. Skills in `misc/`, `in-progress/`, and
`deprecated/` must not appear in either» (README.md и plugin.json).

Механика перегрузки: плагин/установка везёт ТОЛЬКО promoted; беты публичны
в репе, но не устанавливаются; `.agents/in-progress/README.md`: «They're
excluded from the plugin and the top-level README until they graduate to a
stable bucket». Симлинки делают установку обновляемой: «Each entry is a
symlink into this repo, so a `git pull` keeps installed skills current»
(CLAUDE.md, про `scripts/link-skills.sh`).

Применимость: для strategy-agent полезен принцип «новый навык живёт в
черновиках, пока не доказан». У нас этот принцип уже возник эмпирически
(серия курация/lean/гибрид, BRIEF п.27: курация 3:0 осталась стандартом).
Адаптация: `knowledge/skills/_draft/<name>/` — не в индексе, не в проверки
шагов, выпуск — только после решения владельца/PO. Неприменимо: маркетплейс
и плагины — у нас нет дистрибуции скиллов вне репозитория.

## 5. Model- vs user-invoked (M4)
Источник разбора: https://github.com/mattpocock/skills/blob/main/.agents/invocation.md (дата доступа 2026-11-17).

`.agents/invocation.md`: «**User-invoked**: reachable **only by the human
typing its name**. Set `disable-model-invocation: true` … The `description`
is **human-facing** … **Model-invoked**: reachable by **model or user** …
The test for whether a skill should stay model-invoked: _could the model
usefully reach for this autonomously?_ (Reuse is the reason to extract a
skill, not the test.)» Плюс инвариант: «A user-invoked skill may invoke
model-invoked skills, but it can never reach another user-invoked skill.»

Применимость: у нас все навыки model-invoked (AGENTS.md велит открывать
навык на шаге). Адаптация под лидера: часть «скиллов» продукта по природе
user-only — например, выпуск решения владельцу (brief на выбор) не должен
срабатывать автономно; механика «только человек» реализуется у нас
чекпоинтами, а не флагом. Прямой перенос флага не имеет смысла без
харнес-поддержки; переносим РАЗДЕЛЕНИЕ: назвать в knowledge/index.md, какие
навыки оркестратор может применить autonomously, а какие ждут человека.

## 6. Файлы, которые агент готовит сам (M5) — карта по скиллам
Источник разбора: https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/SKILL.md, https://github.com/mattpocock/skills/blob/main/skills/in-progress/loop-me/SKILL.md, https://github.com/mattpocock/skills/blob/main/skills/productivity/teach/SKILL.md, https://github.com/mattpocock/skills/blob/main/skills/engineering/research/SKILL.md, https://github.com/mattpocock/skills/blob/main/skills/engineering/wayfinder/SKILL.md, https://github.com/mattpocock/skills/blob/main/skills/productivity/handoff/SKILL.md (дата доступа 2026-11-17).

| Скилл | Что агент создаёт/правит | Зачем (цитата) |
|---|---|---|
| grill-with-docs | `GLOSSARY.md` + ADR'ы inline | «helps you build a shared language with the AI, and document hard-to-explain decisions in ADR's» (README) |
| loop-me | `workflows/*.md` (спеки), `NOTES.md` (мир пользователя) | «Workflows live in `workflows/*.md` and are the source of truth»; NOTES — «raw notes on the user's world» |
| teach | `MISSION.md`, `./reference/*.html`, `RESOURCES.md`, `./learning-records/*.md` (`0001-<name>.md`), `./lessons/*.html`, `NOTES.md` | «The state of their learning is captured in this directory» |
| research | один Markdown-файл находок с цитатами | «Write the findings to a single Markdown file, citing each claim's source» |
| wayfinder | map-issue + дочерние тикеты решений на трекере | «The map is a single issue … labelled `wayfinder:map`, the canonical artifact» |
| handoff | handoff-документ в системный временный каталог (TMPDIR) | «Save to the temporary directory … - not the current workspace» + секция «suggested skills» |
| domain-modeling | `GLOSSARY.md`, ADR'ы | «Only the active build/sharpen discipline … is `domain-modeling`» (invocation.md) |

Общие свойства (то, что делаем выводом адаптации): файлы состояния живут
РЯДОМ с работой, а не в контексте; агент пишет их САМ, без просьбы
пользователя; источник правды один (workflows, map), индекс — отдельно
(index.md списка страниц вики); handoff намеренно НЕ в workspace, чтобы не
засорять репу.

## 7. Wiki как долговременная память (M6) — chief-of-staff
Источник разбора: https://github.com/mattpocock/skills/blob/main/skills/in-progress/chief-of-staff/SKILL.md (дата доступа 2026-11-17).

`skills/in-progress/chief-of-staff/SKILL.md` (4 729 байт): «Keep your memory
in a **wiki**: a folder of interlinked markdown pages that outlives this
session. Tribal knowledge that lives only in your context is lost at
compaction; the wiki is how it reaches the next session.» Операции:
«**Ingest.** When you learn something durable … update every page it touches
and the index, not only a new page. **Query.** Before a decision, read
`index.md` and the pages it points to … **Lint.** Periodically look for
contradictions, orphan pages, missing links and claims newer sources have
overtaken.» И правило историчности: «**Write history, not the present** …
Date every claim … When something changes, add a new dated claim and mark the
old one superseded. Don't rewrite the old one.»

Применимость: это почти дословно наш STATE.md + LOG.md (append-only,
датирование, «свежие записи дословно»). Подтверждение подхода извне.
Адаптации-пробелы: (а) Lint вики — у нас нет периодической проверки
противоречий STATE ↔ LOG ↔ measurements (STATE может врать о шаге, если
LOG не дописан — инциденты возобновлений это показывают); кандидат —
`scripts/check_state.py` расширить сверкой «последняя запись LOG ↔ шаг в
STATE»; (б) «update every page it touches» — у нас это обеспечено лишь частично: STATE.md
обновляется на границе шага, но measurements.md правится отдельно; правило
«правка измерения → правка STATE-ссылки в том же turn» стоит записать в
навык resume.

## 8. Grill-механика (M7)
Источник разбора: https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md, https://github.com/mattpocock/skills/blob/main/skills/productivity/grill-me/SKILL.md (дата доступа 2026-11-17).

`skills/productivity/grilling/SKILL.md` (2 065 байт): «Interview the user
relentlessly until you reach a shared understanding. Map this as a **design
tree** … Work the tree in **rounds**. The **frontier** is every decision
whose prerequisites are already settled … Ask the whole frontier in one
round: number each question and give your recommended answer. Then wait …
Word each question so "yes" accepts your recommended answer.» И разделение
труда: «Finding _facts_ is your job, never the user's. When a frontier
question needs a fact from the environment … dispatch a sub-agent … Don't
block on it … The _decisions_ are the user's.»

Применимость: высокая. Наши ЧЕКПОИНТЫ 1–3 — та же механика, но без явного
«design tree» и без «рекомендованный ответ» в каждом вопросе (AGENTS.md §1
требует «не больше 3 обязательных чекпоинтов», сводку «что известно / чего
не знаем / что решаем»). Адаптация: (а) в framing-навык добавить правило
«каждому уточняющему вопросу — рекомендованный ответ и почему» (сейчас
вопросы задаются без рекомендации — владелец тратит свой бюджет мышления);
(б) «don't block on facts» — поиск фактов у нас и так внутри сессии, но при
количестве материалов > контекста применять вынесенный сабагент (прецедент:
два сабагента Дня 1, COST.md). grill-me — user-invoked обёртка из 157 байт:
«Call the Skill tool with "grilling"» — приём «тонкий пользовательский
вход → дисциплина» переносим буквально (скиллы-обёртки для РП-команд).

## 9. Проверочные механики внутри скиллов (M8)
Источник разбора: https://github.com/mattpocock/skills/blob/main/skills/misc/git-guardrails-claude-code/scripts/block-dangerous-git.sh, https://github.com/mattpocock/skills/blob/main/skills/engineering/diagnosing-bugs/scripts/hitl-loop.template.sh (дата доступа 2026-11-17).

Два паттерна в репе:

1. **Хук-скрипт, блокирующий опасное действие.** `skills/misc/git-guardrails-claude-code/scripts/block-dangerous-git.sh` (507 байт) — PreToolUse-хук читает JSON команды из stdin, матчит опасные паттерны и «echo "BLOCKED: …" >&2; exit 2». SKILL.md описывает установку и проверку: «Run a quick test: `echo '{"tool_input":{"command":"git push origin main"}}' | <path>` Should exit with code 2 and print a BLOCKED message».
2. **HITL-цикл для шагов, доступных только человеку.** `skills/engineering/diagnosing-bugs/scripts/hitl-loop.template.sh` — «The agent runs the script; the user follows prompts in their terminal … `capture` prints its value back to the terminal, where the agent reads it, so capture observations, and leave signing in to the user as a `step`»; итог — «Captured KEY=VALUE for the agent to parse».

Применимость: (1) у нас уже есть хуки в `.opencode/plugins/strategy-hooks.ts` (sources-guard, state-guard, cost-append) — тот же паттерн; вывод: продолжать проводить проверки как скрипты с кодом возврата, а не как prose-правила (это ровно принцип retro, §10). (2) HITL-паттерн — пробел для лидера: шаги, которые может сделать только человек (доступ к внутренним данным сервиса, пароли, подтверждение в системе), у нас описываются прозой. Адаптация: `templates/hitl-loop.sh` — агент готовит скрипт под ситуацию, человек выполняет в терминале, агент парсит KEY=VALUE. Приоритет — средний (нет шагов, требующих логина, кроме сигнала владельца).

## 10. Retro как механику улучшения среды (M9)
Источник разбора: https://github.com/mattpocock/skills/blob/main/skills/engineering/retro/SKILL.md, https://github.com/mattpocock/skills/blob/main/skills/in-progress/chief-of-staff/SKILL.md (дата доступа 2026-11-17).

`skills/engineering/retro/SKILL.md` (4 369 байт): «You are suggesting
improvements to the coding agent's **environment** to improve future runs.»
Категории кандидатов (дословно): **Navigation** («Would a **navigation
pointer** make it easier?»), **Automated checks** («Read the repo's own
check command first … so a check that already exists but sits unwired or
silently broken is the finding, not a reinvention … A repo with no
**guardrail** … is itself a finding: an un-linted repo is a standing missed
opportunity, not a neutral default»), **Coding standards** («Classify the
violation first: a **mechanical** one … gets a deterministic check, full
stop … Default to building the check over writing the rule. Reserve
`CODING_STANDARDS.md` for genuine **judgement calls**»), **Global AGENTS.md**
(«should they be moved to coding standards (or automated checks) instead?
_Use when_ the AGENTS.md file is particularly large»), **Tool economy**.
chief-of-staff добавляет стратегический трек: «FIRST consider how the
environment the agents operate in might be improved … pit of success …
Lint rules which force correctness … "no workarounds" rule».

Применимость: это ядро адаптации для TASK-hermes-14 §2. У нас аналог ретро
есть по содержанию (measurements.md как evidence, очередь замеров), но нет
ПРОЦЕДУРЫ «ретро очереди → кандидаты в проверки». Адаптация: навык `retro`
(кандидат в _draft): после закрытия задачи — разбор серии на категории
(навигация по STATE, автоматические проверки, стандарты/навыки, объём
AGENTS.md, экономия инструментов), механическая находка → скрипт-гейт, а не
prose-правило. Прямой перенос код-категорий (lint/typing) неприменим —
заменяются на check_sources/check_state/check_evidence_links/гейты шагов.

## 11. Изоляция подзадач (M10)
Источник разбора: https://github.com/mattpocock/skills/blob/main/CLAUDE.md, https://github.com/mattpocock/skills/blob/main/skills/engineering/code-review/SKILL.md (дата доступа 2026-11-17).

CLAUDE.md: «Every skill that dispatches a subagent says to start it with a
fresh context window. Some harnesses (Codex, for one) fork the parent
conversation by default, and a fork inherits the parent's context, which is
what the subagent was meant to escape.» code-review: «Both axes run as
**parallel sub-agents** so they don't pollute each other's context … Start
every sub-agent with a fresh context window.»

Применимость: прямое подтверждение наших механизмов — изолированный критик
(навык critic), два изолированных критика (§26), генерация out-of-repo
(§24.3: in-repo сессии несут AGENTS.md — конфундиннг). Вывод для адаптации:
любой новый оценочный/генеративный подагент обязан (а) свежий контекст,
(б) проверку ослепления (как в second_critic.py: 0 токенов рук в артефакте).

## 12. Код-механики (M12): что переносится принципом, а что нет
Источник разбора: https://github.com/mattpocock/skills/blob/main/README.md, https://github.com/mattpocock/skills/blob/main/skills/engineering/wayfinder/SKILL.md (дата доступа 2026-11-17).

НЕПРИМЕНИМЫ буквально (продукт не пишет код): tdd (red-green-refactor),
to-spec/to-tickets/implement/implement-spec/pr, code-review двухосевой
(как код-ревью), diagnosing-bugs (как отладка кода), domain-modeling (как
модель кода), prototype (как UI), wizard (как провизинг инфры),
setup-matt-pocock-skills (как настройка трекера).

ПЕРЕНОСИМЫЕ ПРИНЦИПЫ (адаптация под лидера):
- red-green-refactor → **предрегистрация → замер → вердикт** (measurements.md
  §16–§27): «red» = предрегистрированная гипотеза, «green» = замер, откат
  фичи по правилу (прецедент: devil→flash откат, BRIEF/O5).
- feedback loop («the rate of feedback is your speed limit») → наши
  check_*-гейты на каждом шаге + критик; цена гейта ≈ 0.
- «deep modules, simple interface» (Ousterhout, цитируется в README) →
  навыки как глубокие модули: маленький вход (триггер в индексе), большая
  методика внутри.
- wayfinder «Plan, don't do» → наш аналог: шаги 0–3 производят РЕШЕНИЯ,
  шаг 4 — план; артефакт шага 3 намеренно не план (human ground truth п.27:
  чат обошёл артефакт, потому что чат дал план — поэтому план стал
  ответственностью шагов 4–5, приёмный чек-лист, TASK-14 §3).
- grilling «finding facts is your job» → дисциплина доказательств AGENTS.md
  §2 (гипотеза ≠ факт; пробел именуется).
- «Ask which skill fits» (ask-matt) → для РП: knowledge/index.md как
  человекочитаемая карта «вопрос → что сделает агент».

## 13. Что береём в работу (итог адаптации, с приоритетами)

1. **Гейт синхронности индекса навыков** (M2/M11): `scripts/check_skill_index.py`
   — индекс ↔ SKILL.md обе стороны; дешёвый, снимает класс «роутер врёт».
2. **Навык-ретро очереди** (M9, в `_draft` до замера): после задачи —
   разбор по категориям среды; механическое → скрипт, судейское → навык;
   анти-круг (BRIEF п.20) соблюдается через measurements.md.
3. **HITL-шаблон** (M8): `templates/hitl-loop.sh` — для шагов, доступных
   только человеку; сейчас такого класса шагов нет, шаблон — на будущее.
4. **Рекомендованный ответ в уточняющих вопросах** (M7): правка навыка
   framing — каждый вопрос несёт рекомендацию и цену неверного ответа.
5. **Правило ingest'а вики** (M6): правка measurements/артефакта → в том же
   turn правка затронутых страниц STATE/LOG (правило в навык resume).
6. **Черновики навыков** (M3): `knowledge/skills/_draft/`, выпуск по
   решению владельца/PO с замером (курация 3:0 — человеческий ground truth
   этого правила).

Не берём: buckets/marketplace/plugin-инфраструктуру (нет дистрибуции),
openai.yaml-метаданные (нет харнеса), code-дисциплины буквально (продукт не
кодит), teach-workspace (обучение РП — вне текущей цели; отложено как
кандидат при цели «агент объясняет свои решения», BRIEF п.26).

## 14. Ограничения этого документа

- Источник один: репозиторий mattpocock/skills на 2026-11-17 (MIT). Внешних
  сравнений с другими skill-репозиториями не делалось [ограничение named].
- Цитаты — дословные span'ы; перевод/адаптация — наша интерпретация, не
  утверждения автора [разграничение сохранено].
- Замеров пользы адаптаций (п. 1–6 §13) здесь НЕТ — они кандидаты в очередь
  TASK-hermes-15 с предрегистрацией (правило BRIEF п.20: новая итерация =
  новая гипотеза; «внедрить без замера» = дрейф, против которого написан
  предохранитель TASK-14 §2).
- Звёздный рейтинг (326 323) — факт GitHub API (https://api.github.com/repos/mattpocock/skills, доступ 2026-11-17); в BRIEF п.21 владельцем назван «325k» — расхождение 0.4% [факт, https://api.github.com/repos/mattpocock/skills].
