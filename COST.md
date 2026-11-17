# COST.md — учёт стоимости прогонов (оба контура)

> Правило (PO R1): каждый прогон пишется сюда — шаг, модель, токены
> in/out/reasoning, поисковые вызовы, оценка $ по прайсам из
> `docs/research/llm-pricing-agent-costs.md`. Dev-контур: без ограничений,
> но учёт обязателен. Prod-цель: ≤$2–5 за полный прогон (mid-tier),
> council-off ≤$1. Сводка: `python3 scripts/cost_report.py`.
> Строки prod-таблицы дописывает хук `cost_append` (вставка между маркерами
> `<!-- cost-rows:begin -->` / `<!-- cost-rows:end -->`, идемпотентно по sessionID).

## Контур разработки (dev) — метрика «сколько стоило исследование»

| Дата | Что | Модель | Токены in | Токены out | Оценка $ | Источник данных |
|---|---|---|---|---|---|---|
| 2026-11-16 | День 1: research (2 сабагента, 23 API-вызова) | Sonnet 5.5 (list, без кэша) | 4,189,926 | 48,802 | ~8.87 | appendix `docs/research/llm-pricing-agent-costs.md` |
| 2026-11-16 | День 2: постановка, скелет, демо-задача (оркестратор) | step-5-preview (Hermes) | — | — | не метрится рантаймом | отмечено честно, не оцениваем |
| 2026-11-16 | Мета: делегация OpenCode #1 — скрипты check_sources/check_state + тесты | step-5-preview (OpenCode) | 10 963 | 41 221 | ~0.23 | сессия ses_e1b51dc58ffeiR65GfbdYjCQtd (cache-read 1 099 264) |
| 2026-11-16 | Мета: делегация OpenCode #2 — скрипт cost_report | step-5-preview (OpenCode) | 55 806 | 7 369 | ~0.19 | сессия ses_e1b5e2a23ffe20FR6AxEXLK50r (cache-read 1 186 112) |
| 2026-11-16 | Мета: пробы инфраструктуры OpenCode (3 сессии: auth, attach, однократный ответ) | step-5-preview (OpenCode) | 45 658 | 119 | ~0.05 | ses_e1b5784c9ffe…, ses_e1b44b564ffe…, ses_e1b5e3d92ffe… (cache-read 4 224 суммарно) |

Примечания к dev-таблице: в контуре OpenCode reasoning-токены провайдером не сепарированы (учтены в output, колонка reasoning = 0); поисковых вызовов не было — в прогонах OpenCode не подключён web-search (MCP web-search — решение PO R5, более поздняя очередь). Оценка $ — по прайсам §1.8 (R1): input (cache-miss) × $1.00/M + cache-read × $0.10/M + output × $2.70/M; input в метриках OpenCode excludes cache-read. Сверка: внутренний cost OpenCode (по прайсам models.dev) для тех же сессий — $0.2497 / $0.2045 / $0.0463; разница — курсовые коэффициенты агрегатора, оба варианта в пределах 10%.
| 2026-11-16 | Продолжение прерванного прогона: cost_report.py + починка тестового контракта (44/44 зелёные), пробы CLI | step-5-preview (Hermes) | — | — | не метрится рантаймом | отмечено честно, не оцениваем; поисковых вызовов: 0 |
| 2026-11-16 | О4: стенд критиков — матрица 26 сессий (13 артефактов × critic/self), рубрика + навык critic | step-5-preview (OpenCode, хук cost-append) | ~190K in / ~330K out (cache-read включён) | — | ~$1.30 (21 строка с меткой «О4: m-…» = $1.10 + 5 ранних прогонов без метки ≈ $0.2, атрибуция по порядку) | прогон `eval/runs/critic-matrix/`, строки — prod-таблица |
| 2026-11-16 | О4: бенчмарк DABstep dev-10 в Docker (прямой вызов API, не через хук) | step-5-preview (API) | 1,437,351 (cache-miss 794,343 + cache-read 643,008) | 150,746 | $1.27 | `eval/benchmarks/dabstep/runs/2026-11-16-dev10/results.json` |
| 2026-11-16 | О4: A/B прогоны рук шага 3 — демо + held-out (skill / critic-loop / council-lite, 16 сессий) | step-5-preview (OpenCode, хук) | ~330K in / ~140K out | — | $0.98 (demo $0.53 + held-out $0.45, атрибуция по меткам) | `eval/runs/ab-options-*/`, метрики `metrics.md` |
| 2026-11-16 | О4: скоринг рук (критик на финалах, 6 сессий) + проба H3 (критик + дайджест) | step-5-preview (OpenCode, хук) | — | — | $0.38 | `eval/runs/ab-options-*/critic-final/`, `eval/runs/h3-probe/` |
| 2026-11-16 | О4: дизайн навыков — руки lean + hybrid на демо (2 сессии) + скоринг (2) | step-5-preview (OpenCode, хук) | — | — | $0.37 | `eval/runs/ab-skills-demo-retention/` |
| 2026-11-17 | TASK-hermes-7: бенчмарк DABstep — 3 повтора dev-10 (r2/r3 улучшенный агент best-effort + применимость, r4 база — шум-контроль; прямой вызов API, не через хук) | step-5-preview (API) | 1,730,700 (cache-miss 303,948 + cache-read 1,426,752) | 274,396 | $2.61 | `eval/benchmarks/dabstep/runs/2026-11-17-t7-run2|run3-improved|run4-baseline/results.json` (разбор: r2 $0.86 + r3 $1.10 + r4 $0.66) |

| 2026-11-17 | TASK-hermes-10: генерация слоёв абляции L0–L3, демо + held-out (прямой вызов API /chat/completions, 8 артефактов; хуки не при чём — как DABstep) | step-5-preview (API) | 70 162 (cache-miss; кэша префикса нет) | 143 528 (включая reasoning) | ~0 | $0.46 | `eval/runs/t10-ablation/*/meta.json` (usage ответа) |
| 2026-11-17 | TASK-hermes-10: смоук-прогон L0 прямым вызовом (артефакт перезаписан фоновым прогоном — точные токены не сохранены) | step-5-preview (API) | — | — | — | ~$0.04 (оценка по выводу прогона) | отмечено честно |
| 2026-11-17 | TASK-hermes-10: пробы изоляции и отвергнутые opencode-прогоны абляции (вне репозитория, 01:52–02:38) — 22 сессии, учтены хуком через persistent server (строки прод-таблицы с меткой «О4: t10-ablation (отвергнутые, вне репо)») | step-5-preview (OpenCode) | ~66K in | ~2.5K out (пробы) + выходы рук в тех же строках | 0 | см. строки прод-таблицы | релейбл: раннер не ставил run-метку, хук брал шаг из STATE.md |
| 2026-11-17 | TASK-hermes-11: серия k=3 — генерация L2×3 + L3×3 на демо прямым вызовом API (6 цепочек, среда = промпт; run_ablation --repeat) + доборная цепочка L3 после сбоя провайдера (HTTP 502) — `eval/merge_l3_retry.py` | step-5-preview (API) | 57 236 (измерение: 20 685 L2 + 36 550 L3; добор 15 001 входит в L3) | 117 051 (измерение) | ~0 | $0.43 всего (в измерение вошло $0.37: L2 $0.145 + L3 $0.229; first-run L3 $0.173 включал упавшую цепочку ~$0.06 + добор $0.114 — оценка разностью) | `eval/runs/t11-k3/demo-retention/{L2,L3}/meta.json`, `.../demo-retention-l3retry/L3/meta.json` |
| 2026-11-17 | TASK-hermes-11: пробы изоляции стенда §23.0 (`eval/iso_probe.py`, 3 сессии opencode) | step-5-preview (OpenCode) | — | — | — | ~$0.01 (строки прод-таблицы, метки «О4: t11-iso-…») | `eval/runs/t11-iso/{in,out,out-inrepo-subdir}/` |
| 2026-11-17 | TASK-hermes-12: серия k=3 по дизайну навыков + О5 — генерация 27 цепочек прямым вызовом API (среда = промпт; research 9: curation $0.1492 / lean $0.1603 / hybrid $0.1326; options 9: curation $0.1631 / lean $0.1207 / hybrid $0.1346; o5a 3 — research lean на step-3.7-flash $0.0564; o5b-P 3 и o5b-F 3 — шаг 3 skill с research.md от step-5 / от flash: $0.1234 / $0.1605) | step-5-preview + step-3.7-flash (API) | 251 421 (измерение: usage ответов, кэша префикса нет) | 387 184 (включая reasoning; reasoning не сепарирован — 0) | ~0 | $1.2007 (формула §1.8 под модель) | `eval/runs/t12-skills/*/{curation,lean,hybrid,skill}/meta*.json`, манифест `eval/runs/t12-skills/manifest.md`; предрегистрация §25.1/§25.2 |
| 2026-11-17 | TASK-hermes-13: held-out-симметрия серии навыков — генерация 18 цепочек прямым вызовом API (среда = промпт; research 9: curation $0.1814 / lean $0.2360 / hybrid $0.2014; options 9: curation $0.1174 / lean $0.1095 / hybrid $0.1245; 0 провалов) | step-5-preview (API) | 245 253 (измерение: usage ответов, кэша префикса нет) | 268 528 (reasoning не сепарирован — 0) | ~0 | $0.9703 (формула §1.8) | `eval/runs/t13-skills-heldout/*/{curation,lean,hybrid}/meta.json`, манифест `eval/runs/t13-skills-heldout/manifest.md`; предрегистрация §27.2/§27.2-А |
## Контур прода (prod) — метрика $/прогон для пользователя

Прайс целевой среды (OpenCode, dev-контур прогонов): `step-5-preview` —
$1.00/M input (cache miss), $0.10/M cache hit, $2.70/M output
(output включает reasoning — reasoning не добавляется поверх output).
Источник: `docs/research/llm-pricing-agent-costs.md` §1.8 (StepFun,
international price list, доступ 2026-11-16).

| Дата | Прогон (sessionID) | Шаг | Модель | in | out | reasoning | cache read | cache write | поиск | Оценка $ |
|---|---|---|---|---|---|---|---|---|---|---|
<!-- cost-rows:begin -->
| 2026-11-16 | ses_e1b3f4ed5ffePUQ15wNbJpyZiy | Шаг 0 + ЧЕКПОИНТ 1 | step-5-preview | 29775 | 46821 | 0 | 2365504 | 0 | 0 | $0.39 |
| 2026-11-16 | ses_e1b383769ffeBhM11dq3gyfWi9 | Шаг 1 (скорректировано) | step-5-preview | 41420 | 24279 | 0 | 1757824 | 0 | 0 | $0.28 |
| 2026-11-16 | ses_e1b345cf1ffe7gMpPaxqOaYKzc | проверка мержа хука (скорректировано) | step-5-preview | 115 | 52 | 0 | 36672 | 0 | 0 | $0.00 |
| 2026-11-16 | ses_e1b2ed595ffetRIQcJzHUUXuNU | проба целевой среды (проверка модели) (скорректировано) | step-5-preview | 60 | 3 | 0 | 18304 | 0 | 0 | $0.00 |
| 2026-11-16 | ses_e1b2d5cc8ffe4OA7wYRI8UkGol | О2 инфраструктура: навыки, шаблоны, check_options (делегация OpenCode) (скорректировано) | step-5-preview | 63538 | 50872 | 0 | 7257664 | 0 | 0 | $0.93 |
| 2026-11-16 | ses_e1b1903a6ffeJ0RzpozjLwP9St | Шаг 2 (ИССЛЕДОВАНИЕ) (скорректировано) | step-5-preview | 60736 | 43648 | 0 | 3752576 | 0 | 0 | $0.55 |
| 2026-11-16 | ses_e1b1269a4ffe5gJIhbGoK6LnQl | Шаг 3 (скорректировано) | step-5-preview | 67547 | 47454 | 0 | 3143424 | 0 | 0 | $0.51 |
| 2026-11-16 | ses_e1b0c278effeAbKyzmO0FRkI0u | Шаг 4 (скорректировано) | step-5-preview | 49397 | 27610 | 0 | 1871808 | 0 | 0 | $0.31 |
| 2026-11-16 | ses_e1b028d8bffe08bN4OAwxu0QGs | О3: проба среды, smoke (скорректировано) | step-5-preview | 20054 | 61 | 0 | 0 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e1afcabdeffeYW6z5I82ScNSSD | О3: проба аргументов -f (скорректировано) | step-5-preview | 3289 | 25 | 0 | 20032 | 0 | 0 | $0.01 |
| 2026-11-16 | ses_e1afc85fbffeNDjfry2WlfAUl9 | О3: council r1-product (скорректировано) | step-5-preview | 516 | 13604 | 0 | 23296 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1afb39feffeGGF2XIetj9r2uq | О3: council r1-comms (скорректировано) | step-5-preview | 455 | 2887 | 0 | 23360 | 0 | 0 | $0.01 |
| 2026-11-16 | ses_e1afae402ffemXJFblQcpshand | О3: council r1-devil (скорректировано) | step-5-preview | 435 | 9612 | 0 | 23360 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1af9ff34ffea5ObW6HyJwhq73 | О3: council r1-data (скорректировано) | step-3.7-flash | 51461 | 21184 | 0 | 225664 | 0 | 0 | $0.13 |
| 2026-11-16 | ses_e1af6cb75ffeNDe8RBZcnLYpdZ | О3: council r1-user (скорректировано) | step-3.7-flash | 774 | 3874 | 0 | 22912 | 0 | 0 | $0.01 |
| 2026-11-16 | ses_e1af5106cffe8ZWLLZ7ZBBHKFh | О3: council r2-product (скорректировано) | step-5-preview | 21586 | 11823 | 0 | 52672 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1af3f9c7ffesTHq5Z6ZqZlnFl | О3: council r2-comms (скорректировано) | step-5-preview | 11798 | 7427 | 0 | 20032 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1af32b41ffeTA7esn5XKvclxc | О3: council r2-devil (скорректировано) | step-5-preview | 6768 | 18202 | 0 | 63104 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1af1a6a6ffejWmi42B287SGbD | О3: council r2-data (скорректировано) | step-3.7-flash | 18442 | 8345 | 0 | 51072 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1af06389ffePzHp8ul3Xz52Dh | О3: council r2-user (скорректировано) | step-3.7-flash | 7618 | 13341 | 0 | 61952 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1aee454fffeZ35gbQv8lecrMA | О3: council r3-devil (скорректировано) | step-5-preview | 42816 | 16767 | 0 | 218240 | 0 | 0 | $0.11 |
| 2026-11-16 | ses_e1ae98037ffe58j4YJkcY3UaQ4 | О3: council arm-a0 (скорректировано) | step-5-preview | 243 | 16135 | 0 | 23296 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1ae82643ffe7CsjWCB7D73j4c | О3: council arm-a1 (скорректировано) | step-5-preview | 385 | 18083 | 0 | 23360 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1ae3b3c8ffeQdp67jOAaJsrJ3 | О3: проба фикса дедупа (скорректировано) | step-5-preview | 26 | 56 | 0 | 20032 | 0 | 0 | $0.00 |
| 2026-11-16 | ses_e1ae324d1ffe0y4Yojh71spEhJ | О3: проба сырых событий (скорректировано) | step-5-preview | 25 | 48 | 0 | 20032 | 0 | 0 | $0.00 |
| 2026-11-16 | ses_e1ae2da50ffeyjkZ7VOcFibMX4 | О3: проба отладочных событий (скорректировано) | step-5-preview | 27 | 104 | 0 | 20032 | 0 | 0 | $0.00 |
| 2026-11-16 | ses_e1ae22b21ffeWpHsxNxu1yT7We | О3: верификация фикса учёта (post-fix) | step-5-preview | 26 | 25 | 0 | 20032 | 0 | 0 | $0.00 |
| 2026-11-16 | ses_e1ad81ebbffehgUnIdZ9E3eURy | О3 | step-5-preview | 34495 | 15684 | 0 | 519296 | 0 | 0 | $0.13 |
| 2026-11-16 | ses_e1ac6cdeeffeWHOLxCrhdnsMzO | О3: held-out step0 | step-5-preview | 52925 | 19833 | 0 | 1816320 | 0 | 0 | $0.29 |
| 2026-11-16 | ses_e1ac3d094ffeJyxH1sP6AxNaHf | О3: held-out step1 | step-5-preview | 73810 | 51037 | 0 | 4569152 | 0 | 0 | $0.67 |
| 2026-11-16 | ses_e1abd9520ffeYM6hPYbCI7oJjG | О3: held-out step2 | step-5-preview | 68381 | 65949 | 0 | 4839104 | 0 | 0 | $0.73 |
| 2026-11-16 | ses_e1ab684c3ffecrHULwEBV64Nio | О3: held-out step3 | step-5-preview | 98032 | 43616 | 0 | 3950464 | 0 | 0 | $0.61 |
| 2026-11-16 | ses_e1ab0c984ffecDOVBmvN2uL2jz | О3: held-out step4 | step-5-preview | 118392 | 50834 | 0 | 7959744 | 0 | 0 | $1.05 |
| 2026-11-16 | ses_e1a9e1d52ffeRNgDnIu1SZHQUP | О3 ЗАКРЫТ | step-5-preview | 21135 | 360 | 0 | 0 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e1a9d1059ffeODWw77Pe6kwU40 | О3 ЗАКРЫТ | step-5-preview | 26485 | 16331 | 0 | 640 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a9b3e5effeX5XEeTunJWLsuH | О3 ЗАКРЫТ | step-5-preview | 53 | 9588 | 0 | 27072 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1a9a5c5effe41VJhhODsMorRK | О3 ЗАКРЫТ | step-5-preview | 25274 | 11377 | 0 | 1792 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a997442ffeL7UBHLKRFbDsFn | О3 ЗАКРЫТ | step-5-preview | 7653 | 2600 | 0 | 21248 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e1a992b69ffeSi95uHJqfrOYnf | О3 ЗАКРЫТ | step-5-preview | 7712 | 21753 | 0 | 21248 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a975150ffeqEG3cVw91DO6Lb | О3 ЗАКРЫТ | step-5-preview | 6297 | 19725 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a95952cffecwyM1KB7DmutwD | О4: m-demo-options-self | step-5-preview | 6302 | 19966 | 0 | 23040 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a93e217ffe2C202doiGlI7Bb | О4: m-demo-strategy-product-self | step-5-preview | 26066 | 15306 | 0 | 1792 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a927ea5ffeSRTNcqpd8liQeQ | О4: m-demo-strategy-product-critic | step-5-preview | 4811 | 18213 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a90f210ffe4rbCnxllUYxpvX | О4: m-demo-strategy-comms-critic | step-5-preview | 3465 | 24157 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a8f1a3fffe27PyDIDAP8tETu | О4: m-demo-strategy-comms-self | step-5-preview | 3470 | 19470 | 0 | 23040 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a8d85ebffe0y0fMsdxPEhpn1 | О4: m-demo-verification-plan-self | step-5-preview | 3235 | 9246 | 0 | 23040 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1a8cb850ffeeEoz9mKgWrTQGc | О4: m-demo-verification-plan-critic | step-5-preview | 3230 | 6517 | 0 | 23104 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e1a8bdc59ffeUiDMKx5JnQ6rvb | О4: m-demo-decisions-critic | step-5-preview | 2370 | 24012 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a89fb2dffeeWU1teOQOiCXR3 | О4: m-demo-decisions-self | step-5-preview | 2375 | 7925 | 0 | 23040 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1a894570ffeFFelX58j0krpn5 | О4: m-heldout-brief-self | step-5-preview | 4676 | 1141 | 0 | 23040 | 0 | 0 | $0.01 |
| 2026-11-16 | ses_e1a891b38ffejuYNR5CN1AF1sC | О4: m-heldout-brief-critic | step-5-preview | 4671 | 10618 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1a882277ffepT1KjVH69IMQmD | О4: m-heldout-research-critic | step-5-preview | 8272 | 12126 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1a8729ccffe6VBaXQ0GY77T9F | О4: m-heldout-research-self | step-5-preview | 8277 | 26869 | 0 | 23040 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e1a8532faffeLp3kZiNFPQ5lbC | О4: m-heldout-options-self | step-5-preview | 9188 | 13270 | 0 | 23040 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1a83f627ffen7P5QwaNyx1CK2 | О4: m-heldout-options-critic | step-5-preview | 32290 | 15133 | 0 | 0 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a82b72affeAW2rwwV7zfpdyf | О4: m-heldout-strategy-product-critic | step-5-preview | 6136 | 28862 | 0 | 23104 | 0 | 0 | $0.09 |
| 2026-11-16 | ses_e1a805f95ffepAm7vV8tDYARKw | О4: m-heldout-strategy-product-self | step-5-preview | 6141 | 18133 | 0 | 23040 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a7ebf95ffewHVHM9VXdUGTOP | О4: m-heldout-strategy-comms-self | step-5-preview | 4253 | 8845 | 0 | 23040 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1a7dfb84ffeYkdcUhb8p2qeIm | О4: m-heldout-strategy-comms-critic | step-5-preview | 4248 | 12506 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1a7ce8c2ffe0uWa8wiIxq81q6 | О4: m-heldout-verification-plan-critic | step-5-preview | 12888 | 21066 | 0 | 14464 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a7b0badffeW4HoGrGvPrXvDR | О4: m-heldout-verification-plan-self | step-5-preview | 4252 | 15912 | 0 | 23040 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1a6fadd7ffehyjk7KaloPLxNi | О4: ab-session | step-5-preview | 4682 | 12202 | 0 | 45696 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1a6eab2bffeQ95kybahEYFcNe | О4: ab-session1 | step-5-preview | 1496 | 19321 | 0 | 48960 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a6d1e32ffe40zerSZ5LBWieE | О4: ab-critic-ab-options-demo-retention- | step-5-preview | 6042 | 23045 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a6b49a4ffeQd0DGPclN90cxE | О4: ab-session2 | step-5-preview | 59918 | 45809 | 0 | 194432 | 0 | 0 | $0.20 |
| 2026-11-16 | ses_e1a67bb0affeKr66TR1jnpJxzU | О4: ab-role-product | step-5-preview | 3152 | 13172 | 0 | 21248 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1a66a9e6ffeuKiODbDK1dOBaS | О4: ab-role-devil | step-5-preview | 3159 | 12727 | 0 | 21248 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1a65a4ecffelgTxaMa9iJw8k9 | О4: ab-role-data | step-3.7-flash | 24301 | 7998 | 0 | 0 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1a64b91affeZsVx7m33Ae84dj | О4: ab-synthesizer | step-5-preview | 11392 | 6530 | 0 | 21248 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1a629539ffeRWSa6O9f1jXxP0 | О4: ab-score-ab-options-demo-retention-c | step-5-preview | 6808 | 14084 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1a615d5affeBKk7FMGatNxzT7 | О4: ab-score-ab-options-demo-retention-c | step-5-preview | 2757 | 20517 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a5fb3a4ffeEGfW1dVOIRnmNd | О4: ab-score-ab-options-demo-retention-s | step-5-preview | 5280 | 16964 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1a58e099ffer4hM3W7za6T88e | О4: ab-council-lite-role-product | step-5-preview | 4680 | 10018 | 0 | 21248 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1a58043afferF8ri3V3XpWCZi | О4: ab-council-lite-role-devil | step-5-preview | 11114 | 11564 | 0 | 140608 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a56f9b7ffe3TsgwPFHumMGvD | О4: ab-council-lite-role-data | step-3.7-flash | 4837 | 9500 | 0 | 20992 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1a55e550ffeCG1DYunn7NAXG7 | О4: ab-council-lite-synthesizer | step-5-preview | 11566 | 30712 | 0 | 21248 | 0 | 0 | $0.10 |
| 2026-11-16 | ses_e1a53c0fbffeD5zacHIaGKxkvX | О4: ab-critic-loop-session1 | step-5-preview | 6992 | 16227 | 0 | 47296 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a523627ffeoCn1A19XO5JVen | О4: ab-critic-ab-options-heldout-growth- | step-5-preview | 8116 | 23581 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a508493ffelkiXAKPGOwMuxe | О4: ab-critic-loop-session2 | step-5-preview | 10007 | 22756 | 0 | 21248 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a4eceb4ffeFId0A9V3TM1rQF | О4: ab-skill-session | step-5-preview | 6087 | 8255 | 0 | 47424 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1a4b0627ffe38c0x903Z67HZm | О4: ab-score-ab-options-heldout-growth-s | step-5-preview | 8431 | 13290 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1a49cdf2ffe2KLf09uxTuW48J | О4: ab-score-ab-options-heldout-growth-s | step-5-preview | 10624 | 10711 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1a48b01bffeVt3rSdzUxJhPX0 | О4: ab-score-ab-options-heldout-growth-s | step-5-preview | 6556 | 19631 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1a3b2de4ffe6fr61VHNbyOmro | О4: h3-research-citations | step-5-preview | 8930 | 23240 | 0 | 21248 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a3595b2ffe1dP8sXxs7PD29O | О4: ab-ab-skills-demo-retention-lean-ses | step-5-preview | 3199 | 9538 | 0 | 21248 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1a34b27dffeItOXQ1bpNRocQg | О4: ab-ab-skills-demo-retention-hybrid-s | step-5-preview | 28286 | 35936 | 0 | 1081984 | 0 | 0 | $0.23 |
| 2026-11-16 | ses_e1a2f98deffetllu0n0K84EeUZ | О4: ab-score-ab-skills-demo-retention-hy | step-5-preview | 5682 | 21890 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a2e036bffeKYBHF7w1Hbhv5v | О4: ab-score-ab-skills-demo-retention-le | step-5-preview | 5155 | 11539 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1a0d53adffefXEuqBWeNy4Q2n | О4 | step-5-preview | 21265 | 23 | 0 | 0 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e1a0c770dffeR1hWmLj8xhF5eh | О4: ab-cf-heldout-council-full-role-prod | step-5-preview | 22584 | 17152 | 0 | 200192 | 0 | 0 | $0.09 |
| 2026-11-16 | ses_e1a0afa09ffealzV2894HjpdYz | О4: ab-cf-heldout-council-full-role-comm | step-5-preview | 21333 | 22271 | 0 | 576704 | 0 | 0 | $0.14 |
| 2026-11-16 | ses_e1a08af28ffexTVLafbPXZOIkI | О4: ab-cf-heldout-council-full-role-data | step-3.7-flash | 25829 | 9455 | 0 | 0 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1a07c04bffejhIOx0xdt8V34O | О4: ab-cf-heldout-council-full-role-devi | step-5-preview | 38496 | 19108 | 0 | 251776 | 0 | 0 | $0.12 |
| 2026-11-16 | ses_e1a06033affe4ej4366vvN1ai8 | О4: ab-cf-heldout-council-full-role-user | step-3.7-flash | 15457 | 7227 | 0 | 10368 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1a054365ffe3OR27vDfV2Uoxt | О4: ab-cf-heldout-council-full-cross-pro | step-5-preview | 42228 | 26054 | 0 | 552320 | 0 | 0 | $0.17 |
| 2026-11-16 | ses_e1a02c0d9ffedLOCqfpXLCOjir | О4: ab-cf-heldout-council-full-cross-com | step-5-preview | 15563 | 17641 | 0 | 21248 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1a01552effeUXift2cIEtEK5K | О4: ab-cf-heldout-council-full-cross-dat | step-3.7-flash | 17384 | 9470 | 0 | 20864 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1a0076e1ffemkiyPduL70AfDc | О4: ab-cf-heldout-council-full-cross-dev | step-5-preview | 51425 | 25077 | 0 | 357184 | 0 | 0 | $0.15 |
| 2026-11-16 | ses_e19fe5c3effeeb5K1Ny4eWOLPN | О4: ab-cf-heldout-council-full-cross-use | step-3.7-flash | 16691 | 16549 | 0 | 20864 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e19ed0cd2ffeyYtmPKKSn6WV8T | О4 | step-5-preview | 36 | 125 | 0 | 21248 | 0 | 0 | $0.00 |
| 2026-11-16 | ses_e19ec5a0affeYXyIxb6l0URvgG | О4: ab-cf-heldout-council-full-adversari | step-5-preview | 64422 | 32000 | 0 | 1792 | 0 | 0 | $0.15 |
| 2026-11-16 | ses_e19e9d336ffezMx8hOKyjpBz4H | О4: ab-cf-heldout-council-full-synthesiz | step-5-preview | 73001 | 32000 | 0 | 0 | 0 | 0 | $0.16 |
| 2026-11-16 | ses_e19e786d8ffetL6AqLsrlXqbTB | О4: ab-score-cf-heldout-council-full | step-5-preview | 30467 | 19753 | 0 | 640 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e19e5aa01ffegHatxIE9AoVnar | О4: ab-cl2-demo-critic-loop2-session1 | step-5-preview | 7618 | 6508 | 0 | 42560 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e19e4fd2fffeMPSvFoWt461nOg | О4: cl2-demo-critic | step-5-preview | 6603 | 21401 | 0 | 21248 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e19e385e7ffe7RH1q9ljp0D2vJ | О4: ab-cl2-demo-critic-loop2-session2 | step-5-preview | 6639 | 16709 | 0 | 21248 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e19dd53f9ffeIBce8CXF47ygOM | О4: ab-score-cl2-demo-critic-loop2 | step-5-preview | 5524 | 15798 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e19dc1fe5ffebTVWF4i3mtU5F1 | О4: ab-cl2-heldout-critic-loop2-session1 | step-5-preview | 6186 | 15727 | 0 | 47232 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e19dac8faffeWwVUYaKbTnC8Uy | О4: cl2-heldout-critic | step-5-preview | 6671 | 11094 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e19d9fbb4ffeQV7TB2ep1kVkHP | О4: ab-cl2-heldout-critic-loop2-session2 | step-5-preview | 8373 | 23986 | 0 | 21248 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e19d3b68affetA0F1IVovwp55r | О4: ab-score-cl2-heldout-critic-loop2 | step-5-preview | 7391 | 16703 | 0 | 23296 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e19d122a5ffebl2R65MhPuWTvE | О4: ab-rd-demo-curation-session | step-5-preview | 25551 | 25879 | 0 | 56768 | 0 | 0 | $0.10 |
| 2026-11-16 | ses_e19cf63ddffeESY5DdCOSu03rv | О4: ab-rd-demo-lean-session | step-5-preview | 11281 | 15368 | 0 | 21248 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e19ce4ae7ffeDLV6dPXgKr3Hww | О4: ab-rd-demo-hybrid-session | step-5-preview | 17685 | 8450 | 0 | 89024 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e19cb7e94ffeUl9MeDwShgyuMl | О4: ab-score-rd-demo-curation | step-5-preview | 7092 | 20888 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e19c9de8fffeAtJuXcI4uVsQEr | О4: ab-score-rd-demo-hybrid | step-5-preview | 26238 | 15328 | 0 | 1792 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e19c8b153ffeAfD7ehzpxDYpxI | О4: ab-score-rd-demo-lean | step-5-preview | 5760 | 32000 | 0 | 23104 | 0 | 0 | $0.09 |
| 2026-11-16 | ses_e19c65522ffePMdkjIMuo8bJkt | О4: ab-rh-heldout-hybrid-session | step-5-preview | 65282 | 51330 | 0 | 849088 | 0 | 0 | $0.29 |
| 2026-11-16 | ses_e19c2f606ffeBWbEdGfgda9KEJ | О4: ab-rh-heldout-lean-session | step-5-preview | 50502 | 45865 | 0 | 248896 | 0 | 0 | $0.20 |
| 2026-11-16 | ses_e19bfe872ffe4ob8C2gfCwPTrN | О4: ab-rh-heldout-curation-session | step-5-preview | 75945 | 37870 | 0 | 393792 | 0 | 0 | $0.22 |
| 2026-11-16 | ses_e19badc01ffeXGgRlj55xNLfrb | О4: ab-score-rh-heldout-curation | step-5-preview | 8965 | 20602 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e19b9626affeUCF9Id7vp7St9S | О4: ab-score-rh-heldout-hybrid | step-5-preview | 9497 | 18031 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e19b8072bffejV5kxNHXihXsOS | О4: ab-score-rh-heldout-lean | step-5-preview | 10527 | 32000 | 0 | 23104 | 0 | 0 | $0.10 |
| 2026-11-16 | ses_e19b5328cffeRdhcwqAs36tCBE | О4: ab-score-rh-heldout-lean-retry | step-5-preview | 31 | 1953 | 0 | 33600 | 0 | 0 | $0.01 |
| 2026-11-16 | ses_e19a3afe0ffeXE3n4nyaZ8kvWl | О4-хвост | step-5-preview | 17 | 3 | 0 | 21248 | 0 | 0 | $0.00 |
| 2026-11-16 | ses_e19a37984ffe6J2U27HYNbT0de | О4: h2-research-unified | step-5-preview | 5856 | 18382 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e19a1752cffeIqO7Azzjuk0SLr | О4: h2-research-unified | step-5-preview | 17 | 3 | 0 | 21248 | 0 | 0 | $0.00 |
| 2026-11-16 | ses_e19a2418effeDh4lQw5pjS31rc | О4: h2-research-unified | step-5-preview | 32 | 24402 | 0 | 28928 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e19a03389ffesqcduFELRzx1C7 | О4: h2-research-typed | step-5-preview | 7259 | 14028 | 0 | 21248 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e199ef9cdffeXnI9Zk7C2VplOD | О4: h2-options-unified | step-5-preview | 6297 | 26713 | 0 | 23104 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e199cc769ffeiiZjVRCMnt6KYE | О4: h2-options-typed | step-5-preview | 7629 | 21259 | 0 | 21376 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e199b421effe1LAduqOVZeb9u7 | О4: h4-package | step-5-preview | 49199 | 11768 | 0 | 0 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e19983307ffeQYMd786wthgMkq | О4: ab-clf-demo-council-lite-flash-role- | step-5-preview | 3152 | 11747 | 0 | 21248 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e19973975ffe5HwEbFPcBcowos | О4: ab-clf-demo-council-lite-flash-role- | step-3.7-flash | 24302 | 13267 | 0 | 0 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1995d651ffeQwUCCTaDY9VEZ3 | О4: ab-clf-demo-council-lite-flash-role- | step-3.7-flash | 3437 | 10068 | 0 | 20864 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1994db0bffeLKiP5hB0q9e0oX | О4: ab-clf-demo-council-lite-flash-synth | step-5-preview | 46840 | 37433 | 0 | 100864 | 0 | 0 | $0.16 |
| 2026-11-16 | ses_e1992220cffe5nSbLLqG3q2pr0 | О4: ab-clf-heldout-council-lite-flash-ro | step-5-preview | 8 | 10410 | 0 | 25920 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1991295affeX6xBNtRVFi3I7V | О4: ab-clf-heldout-council-lite-flash-ro | step-3.7-flash | 4838 | 7133 | 0 | 20992 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1990445effejzpnvRM3AP9cJ8 | О4: ab-clf-heldout-council-lite-flash-ro | step-3.7-flash | 4837 | 4738 | 0 | 20992 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e198fa3f8ffe3D2utBraeH0BHg | О4: ab-clf-heldout-council-lite-flash-sy | step-5-preview | 25234 | 38144 | 0 | 414144 | 0 | 0 | $0.17 |
| 2026-11-16 | ses_e198cc65bffepO2uaP5QZetfOE | О4: o5-trigger-audit | step-5-preview | 1221 | 3587 | 0 | 21248 | 0 | 0 | $0.01 |
| 2026-11-16 | ses_e198c7e55ffemVvj3zEVQQuT5I | О4: b11-plainchat | step-5-preview | 24889 | 4682 | 0 | 190976 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e19893865ffe9TAMb1HfeI9lUI | О4: ab-score-clf-demo-council-lite-flash | step-5-preview | 10807 | 17989 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1987aa6cffepFLSKGanl0HdcM | О4: ab-score-clf-heldout-council-lite-fl | step-5-preview | 9418 | 11673 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e198670a0ffewrkXKivhqjBti0 | О4: b11-plainchat-critic | step-5-preview | 2147 | 18269 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e197c605effee5cFZGanHIs02X | О4: t7-opt-demo-skill | step-5-preview | 6612 | 17179 | 0 | 21376 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e197b33acffe9CF3ATmOfTBCU9 | О4: t7-opt-demo-criticloop | step-5-preview | 2745 | 14660 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e197a350dffer0trIdmvRaIMrZ | О4: t7-opt-demo-councillite | step-5-preview | 6796 | 9513 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e197979dcffewmt25WwBptiY4c | О4: t7-opt-heldout-skill | step-5-preview | 6544 | 14295 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e19787e2dffe3jrIQ31R97z6Rz | О4: t7-digest-research | step-5-preview | 10612 | 24048 | 0 | 22720 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e1976c571ffeIz57pnaHnXQe2S | О4: t7-opt-heldout-councillite | step-5-preview | 8419 | 12970 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1975c8eeffeGqIfiy4GMB0Fr7 | О4: t7-opt-heldout-councilfull | step-5-preview | 7991 | 26299 | 0 | 22720 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e1974110affeH0KjAPfNLiniJT | О4: t7-opt-demo-criticloop2 | step-5-preview | 5512 | 11468 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e19732679ffedxHx3QZ9p4eUqc | О4: t7-opt-heldout-criticloop2 | step-5-preview | 7571 | 6699 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e1972ab5cffey5DOwgXA4u0bMU | О4: t7-opt-demo-clf | step-5-preview | 10795 | 16671 | 0 | 22720 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e19719954ffeoKDeC51KnpXeTQ | О4: t7-opt-heldout-clf | step-5-preview | 9406 | 13117 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1970aac1ffe6xgE8AcbgixqgI | О4: t7-opt-demo-skills-lean | step-5-preview | 5143 | 12745 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e196faebcffeY0VY7lU0Vjh4So | О4: t7-opt-demo-skills-hybrid | step-5-preview | 5670 | 21150 | 0 | 22720 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e196e3a8cffeK6BUv61kfPxiU7 | О4: t7-res-demo-curation | step-5-preview | 8367 | 27276 | 0 | 21376 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e196c756affeB8gGA4m4FzhrzA | О4: t7-res-demo-lean | step-5-preview | 5755 | 12069 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e196b9efcffeM50pUPRgg4RtFG | О4: t7-res-demo-hybrid | step-5-preview | 16380 | 6623 | 0 | 45376 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e196b18daffebAG2mcrryi3j9i | О4: t7-res-heldout-curation | step-5-preview | 8960 | 11111 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e196a574bffeUp9u7aglGGs9Nm | О4: t7-res-heldout-lean | step-5-preview | 10522 | 17096 | 0 | 22656 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e19692790ffeBBYDVObEs71JQR | О4: t7-res-heldout-hybrid | step-5-preview | 9492 | 10259 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e19686c7cffeA6mCvVeLiId1ij | О4: t7-b11-plainchat | step-5-preview | 2135 | 23113 | 0 | 22720 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e1966beadffev0pfxDbUXEbPky | О4: t7-cvs-demo-research-self | step-5-preview | 7200 | 12309 | 0 | 21248 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1965c456ffeFA5TchoiUH1Cua | О4: t7-cvs-demo-options-self | step-5-preview | 7698 | 9457 | 0 | 21248 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e19650897ffeF4Papyw5ifFtlF | О4: t7-cvs-heldout-research-critic | step-5-preview | 8267 | 11341 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e19644063ffeZSsSYHJeB9qZ6C | О4: t7-cvs-heldout-research-self | step-5-preview | 9552 | 11172 | 0 | 21312 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e19634308ffeY1AlGD3q7M6Tan | О4: t7-cvs-heldout-options-critic | step-5-preview | 9171 | 8942 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e19628b07ffeSG5R7BZbchdqvz | О4: t7-cvs-heldout-options-self | step-5-preview | 10520 | 10541 | 0 | 21312 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e195fed12ffezxB2rrhRiGXWKt | О4: ab-t7-clc-demo-council-lite-critic-r | step-5-preview | 3024 | 5400 | 0 | 21376 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e195f7a84ffelgkrClrAqE66W4 | О4: ab-t7-clc-demo-council-lite-critic-r | step-5-preview | 3159 | 7207 | 0 | 21248 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e195eed05ffeDcWeVtQwbl10xf | О4: ab-t7-clc-demo-council-lite-critic-r | step-3.7-flash | 24301 | 10965 | 0 | 0 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e195ddf69ffeT5xm3ONgfljMxt | О4: ab-t7-clc-demo-council-lite-critic-s | step-5-preview | 40023 | 22660 | 0 | 92416 | 0 | 0 | $0.11 |
| 2026-11-16 | ses_e195c44bbffeDPwumcSuk24XBl | О4: t7-clc-demo-critic | step-5-preview | 9717 | 17345 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e195af750ffe8zDtSXiG1qmei2 | О4: ab-t7-clc-demo-council-lite-critic-r | step-5-preview | 11185 | 3279 | 0 | 21568 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e195ab5baffeuhmdA8gdFcWTg9 | О4: ab-t7-clc-heldout-council-lite-criti | step-5-preview | 9249 | 10748 | 0 | 169920 | 0 | 0 | $0.06 |
| 2026-11-16 | ses_e1959cfacffequJjdLsBlJdTpl | О4: ab-t7-clc-heldout-council-lite-criti | step-5-preview | 4559 | 12430 | 0 | 21376 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e1958f501ffe3WUhjQqhdNn6l0 | О4: ab-t7-clc-heldout-council-lite-criti | step-3.7-flash | 4837 | 6300 | 0 | 20992 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e19585e13ffebJ3gggz03dJwAr | О4: ab-t7-clc-heldout-council-lite-criti | step-5-preview | 12063 | 18981 | 0 | 21312 | 0 | 0 | $0.07 |
| 2026-11-16 | ses_e195725ccffef3GZDNPK9iPxAC | О4: t7-clc-heldout-critic | step-5-preview | 5902 | 15840 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1956080fffegn2LDPblM8tYFC | О4: ab-t7-clc-heldout-council-lite-criti | step-5-preview | 6961 | 12112 | 0 | 21568 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e195224f6ffehjVqyMTYC3ITZz | О4: ab-score-t7-clc-demo-council-lite-cr | step-5-preview | 10690 | 24420 | 0 | 23104 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e19509289ffe6a9k25PnY528b7 | О4: ab-score-t7-clc-heldout-council-lite | step-5-preview | 6558 | 14487 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e194f7185ffewQdgZ1gTYxX9Cz | О4: t7-clc-demo-final-typical | step-5-preview | 10678 | 15314 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e194e5f5dffek3bYvbHQUKFwFB | О4: t7-clc-heldout-final-typical | step-5-preview | 6546 | 10840 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e194d9adbffe0tBHEuVXirgcq3 | О4: t7-digest-research | step-5-preview | 13 | 29946 | 0 | 34240 | 0 | 0 | $0.08 |
| 2026-11-16 | ses_e19394f1bffe6fUhnmslIiDLGG | О4: t8-noise-run1 | step-5-preview | 13 | 18748 | 0 | 28992 | 0 | 0 | $0.05 |
| 2026-11-16 | ses_e1937ee64ffeHhW19u1gGEzJs3 | О4: t8-noise-run2 | step-5-preview | 13 | 12957 | 0 | 28992 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e193702a2ffezMdUu46cUAne32 | О4: t8-noise-run3 | step-5-preview | 13 | 12022 | 0 | 28992 | 0 | 0 | $0.04 |
| 2026-11-16 | ses_e19362e7bffeiRAFmNMb1yB4eY | О4: t8-noise-run4 | step-5-preview | 13 | 9537 | 0 | 28992 | 0 | 0 | $0.03 |
| 2026-11-16 | ses_e193586b0ffe1CHdLAyBWMTply | О4: t8-noise-run5 | step-5-preview | 13 | 6808 | 0 | 28992 | 0 | 0 | $0.02 |
| 2026-11-16 | ses_e193499c6ffeEMNxSFNB1LyZ0J | О4: t8-step4-critic-draft | step-5-preview | 4811 | 17921 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e19336d97ffeSK3Vp7EV5mInFo | О4: ab-runs-t8-step4-revision | step-5-preview | 58030 | 21452 | 0 | 386176 | 0 | 0 | $0.15 |
| 2026-11-17 | ses_e19318e70ffeEwfX72w9eWDMk2 | О4: t8-step4-score-draft | step-5-preview | 11 | 28437 | 0 | 27904 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e192f9e50fferb97AZVWp4OJA2 | О4: t8-step4-score-final | step-5-preview | 28506 | 14404 | 0 | 0 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e19215f16ffe42UKnJ5PWXtsIV | О4: t9-step4-demo-run2-critic-draft | step-5-preview | 11 | 1706 | 0 | 27904 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e19212721ffeB3cLOMolShSFjy | О4: ab-runs-t9-step4-demo-run2-revision | step-5-preview | 34180 | 19881 | 0 | 286080 | 0 | 0 | $0.12 |
| 2026-11-17 | ses_e191fac48ffewHFvhsTjKuxzYj | О4: t9-step4-demo-run2-score-draft | step-5-preview | 11 | 26776 | 0 | 27904 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e191de6e0ffebdeGKIWr0HbHC6 | О4: t9-step4-demo-run2-score-final | step-5-preview | 29392 | 21798 | 0 | 46464 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e191c5848ffeZGJuy8V0aA2rcS | О4: t9-step4-demo-run3-critic-draft | step-5-preview | 11 | 14850 | 0 | 27904 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e191b6125ffezq5OAhTNwxo0lJ | О4: ab-runs-t9-step4-demo-run3-revision | step-5-preview | 3450 | 21612 | 0 | 117632 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e191a0680ffe9yvMzJxWVJYXkW | О4: t9-step4-demo-run3-score-draft | step-5-preview | 11 | 24251 | 0 | 27904 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e1917efa0ffeqpLJDqf61UiLSY | О4: t9-step4-demo-run3-score-final | step-5-preview | 5441 | 2110 | 0 | 23360 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e1917af14ffe1YcPqfV2fE609T | О4: t9-step4-demo-run4-critic-draft | step-5-preview | 11 | 32000 | 0 | 27904 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e191500deffeo1mfcYE0ytG4fp | О4: ab-runs-t9-step4-demo-run4-revision | step-5-preview | 48 | 17937 | 0 | 26176 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e1913bf0affecbmNrpfpIWNWRp | О4: t9-step4-demo-run4-score-draft | step-5-preview | 11 | 22839 | 0 | 27904 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e19121765ffefurySXFTULexhf | О4: t9-step4-demo-run4-score-final | step-5-preview | 4362 | 21799 | 0 | 23552 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e190e11aeffeqb6hMnP2oiS74L | О4: t9-step4-heldout-run1-critic-draft | step-5-preview | 6136 | 16781 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e190ce098ffePMKeG24qzT4BHx | О4: ab-runs-t9-step4-heldout-run1-revisi | step-5-preview | 32453 | 13105 | 0 | 83328 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e190bf9c3ffe8CZu8q5fdnfgwy | О4: t9-step4-heldout-run1-score-draft | step-5-preview | 56 | 22007 | 0 | 29184 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e190a58cdffe0PkAq1bb1VVeXS | О4: t9-step4-heldout-run1-score-final | step-5-preview | 7118 | 16081 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e19094a3fffe1UtxYEmtd6UNDm | О4: t9-step4-heldout-run2-critic-draft | step-5-preview | 56 | 19351 | 0 | 29184 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e1907eb0bffe2UKVUmiwsyUp9t | О4: ab-runs-t9-step4-heldout-run2-revisi | step-5-preview | 16971 | 28972 | 0 | 266880 | 0 | 0 | $0.12 |
| 2026-11-17 | ses_e1905e1a3ffetjoPb3ogZAmNcd | О4: t9-step4-heldout-run2-score-draft | step-5-preview | 56 | 15809 | 0 | 29184 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e190495f5ffeVzHFt6cUwmqIvX | О4: t9-step4-heldout-run2-score-final | step-5-preview | 7216 | 13490 | 0 | 23296 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e190383c7ffeos03n5TgNnzaif | О4: t9-step4-heldout-run3-critic-draft | step-5-preview | 56 | 17952 | 0 | 29184 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e1902430effee0ETK0pozDuvVl | О4: ab-runs-t9-step4-heldout-run3-revisi | step-5-preview | 7425 | 8491 | 0 | 21632 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e1901b5ddffec2QwuyFlDnFPwC | О4: t9-step4-heldout-run3-score-draft | step-5-preview | 56 | 17503 | 0 | 29184 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e19008a71ffe63rLsZ3nc6tt1K | О4: t9-step4-heldout-run3-score-final | step-5-preview | 7104 | 18621 | 0 | 23232 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e18ff39b2ffez2tBBAQjX1hmdl | О4: t9-step4-heldout-run4-critic-draft | step-5-preview | 56 | 19578 | 0 | 29184 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e18fdefcfffeNQEIsTzrbcjWYH | О4: ab-runs-t9-step4-heldout-run4-revisi | step-5-preview | 38682 | 35095 | 0 | 732800 | 0 | 0 | $0.21 |
| 2026-11-17 | ses_e18fb5324ffewByS8YelzXazC1 | О4: t9-step4-heldout-run4-score-draft | step-5-preview | 56 | 23483 | 0 | 29184 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e18f9b81bffebDt4WhOpbMVG5X | О4: t9-step4-heldout-run4-score-final | step-5-preview | 30208 | 22407 | 0 | 640 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e18f6977cffeTA9wYCnDrXApVb | О4: t9-step4-demo-run4b-critic-draft | step-5-preview | 11 | 22496 | 0 | 27904 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e18f50999ffesktXr1YbD5tzoK | О4: ab-runs-t9-step4-demo-run4b-revision | step-5-preview | 23735 | 17092 | 0 | 144192 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e18f3d1ddffeDuORV9no4Ms2Z3 | О4: t9-step4-demo-run4b-score-draft | step-5-preview | 11 | 8482 | 0 | 27904 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e18f306eaffeFVdnZq7TvTtson | О4: t9-step4-demo-run4b-score-final | step-5-preview | 4861 | 10326 | 0 | 23552 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e18f196f4ffeiqwlbMG75LBMEn | О4: t9-gate-strategy-product | step-5-preview | 11 | 16720 | 0 | 27904 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e18f07b37ffeOhPfL89aDovprl | О4: t9-gate-strategy-comms | step-5-preview | 3465 | 16394 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e18ef6533ffeZ46Ov0tC3tVAyu | О4: t9-gate-verification-plan | step-5-preview | 3230 | 22794 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e18ede4dbffeeA2UKUOvfjTa9h | О4: t9-gate-strategy-product | step-5-preview | 27449 | 31167 | 0 | 1792 | 0 | 0 | $0.11 |
| 2026-11-17 | ses_e18ebcd81ffe6p3KIqIugkJDZ6 | О4: t9-gate-strategy-comms | step-5-preview | 4248 | 14156 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e18ead30dffe2ClA6JhsYbEBzX | О4: t9-gate-verification-plan | step-5-preview | 25560 | 14334 | 0 | 1792 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e18dc7dcbffem2QQxr6fPrAEoO | О4: t9-gate-demo-strategy-product | step-5-preview | 11 | 15233 | 0 | 27904 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e18db43feffev2uZjh43RduPyk | О4: t9-gate-demo-strategy-comms | step-5-preview | 9 | 10734 | 0 | 26560 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e18da86cfffeoWhDDVajJ1s93i | О4: t9-gate-demo-verification-plan | step-5-preview | 30 | 12725 | 0 | 26304 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e18cc0ff9ffeCS6Muk73na5KB7 | О4: t10-probe | step-5-preview | 52 | 294 | 0 | 21248 | 0 | 0 | $0.00 |
| 2026-11-17 | ses_e18c67235ffekkr5qt8RbB8TFj | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 21274 | 12686 | 0 | 182912 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e18c5588cffeC4qF3LqYVdktxE | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 4820 | 16468 | 0 | 21248 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e18c424d9ffemMVs55qIGR1e0w | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 6895 | 21684 | 0 | 21248 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e18c29f27ffe0B4ziCJrD7gOD7 | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 78710 | 21761 | 0 | 169280 | 0 | 0 | $0.15 |
| 2026-11-17 | ses_e18c107d4ffeSMcVo5fzsuYaNa | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 63901 | 58871 | 0 | 1350464 | 0 | 0 | $0.36 |
| 2026-11-17 | ses_e18b9102effeczRnXmyYN9qzJr | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 17 | 7820 | 0 | 24256 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e18b87489ffe07uJJ3jhuPL5Zy | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 25427 | 19207 | 0 | 640 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e18b6eaecffeiBQNuLjJf7QiVx | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 31791 | 8814 | 0 | 145280 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e18b62913ffeOEAeoG9WgTZRtz | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 10031 | 20988 | 0 | 18112 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e18b4761effeM04741mHC93HY7 | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 20456 | 25725 | 0 | 289088 | 0 | 0 | $0.12 |
| 2026-11-17 | ses_e18b2caf9ffez9eUwOhibza4A7 | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 9716 | 7693 | 0 | 1856 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e18b22e17ffeIZTT5if6NzbYUs | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 7351 | 18974 | 0 | 6016 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e18b0822bffeq7IDHHgtvsQ1UF | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 31514 | 30750 | 0 | 252864 | 0 | 0 | $0.14 |
| 2026-11-17 | ses_e18ae34baffeUiCyPglcL5QNYH | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 6866 | 24750 | 0 | 8576 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e18ac73fbffeCAGJNQ0EIGB2X1 | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 6474 | 6115 | 0 | 8512 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e18ac09c9ffe5M6IChVtut8kA7 | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 26736 | 9442 | 0 | 234880 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e18a9050cffeOZG0TnGMDcU6Ju | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 3060 | 6686 | 0 | 8512 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e18a85eadffeblj6JlZhtXL8qC | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 4791 | 9745 | 0 | 8576 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e18a7ae32ffex3IbhbTH3YKX4v | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 18 | 19807 | 0 | 15424 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e18a64f6fffe833pWuR5fQ3549 | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 18 | 17545 | 0 | 15424 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e18a51753ffe6nUzy5WmMmqlcd | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 32494 | 35546 | 0 | 322176 | 0 | 0 | $0.16 |
| 2026-11-17 | ses_e18a2ca1fffeRdy8uUwztw0jA9 | О4: t10-ablation (отвергнутые, вне репо) | step-5-preview | 30730 | 14466 | 0 | 478976 | 0 | 0 | $0.12 |
| 2026-11-17 | ses_e188d5dbdffee4AxIUsAsnt4bP | О4: t10-score-demo-L0-unified | step-5-preview | 3526 | 32000 | 0 | 23104 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e188b0a7affeH8QompiKCiNaEu | О4: t10-score-demo-L0-typical | step-5-preview | 3514 | 8975 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e188a5285ffePhNujXcGHc5Cuh | О4: t10-score-demo-L1-unified | step-5-preview | 3861 | 18065 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e1888f817ffeyKL1ICenRBm8UA | О4: t10-score-demo-L1-typical | step-5-preview | 3849 | 5807 | 0 | 22720 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e18887fb6ffeevyBNBA9DbqWBD | О4: t10-score-demo-L2-unified | step-5-preview | 4588 | 11893 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e1887852bfferx7CEYWOPDBnrB | О4: t10-score-demo-L2-typical | step-5-preview | 4576 | 16097 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e18866020ffeD5cVc5LekQzFjn | О4: t10-score-demo-L3-unified | step-5-preview | 5330 | 20106 | 0 | 23168 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e1884d5a1ffeWXtdu2wT8Tx9j9 | О4: t10-score-demo-L3-typical | step-5-preview | 5382 | 10145 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e188401b8ffe5PE3rt0QTF07as | О4: t10-score-demo-L4-unified | step-5-preview | 6297 | 25784 | 0 | 23104 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e188235eeffevZcTR6pn91pJb4 | О4: t10-score-demo-L4-typical | step-5-preview | 13 | 13915 | 0 | 28992 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e18811ec6ffesiWFikVgIfJXqZ | О4: t10-score-heldout-L0-unified | step-5-preview | 2009 | 17094 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e187fd09effeoeMF60Z0HhUqLP | О4: t10-score-heldout-L0-typical | step-5-preview | 1997 | 8573 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e187f332fffeIv7W0rYBBsvtSf | О4: t10-score-heldout-L1-unified | step-5-preview | 3433 | 25288 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e187d75f7ffeC3YTYiLZw0JeXH | О4: t10-score-heldout-L1-typical | step-5-preview | 3421 | 16482 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e187c3c1effexSnHbvD4KE3w09 | О4: t10-score-heldout-L2-unified | step-5-preview | 4747 | 14964 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e187b0a9cffeSCcTOeimmXb4ze | О4: t10-score-heldout-L2-typical | step-5-preview | 4735 | 9583 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e187a2823ffeozo8AZnDY09FhN | О4: t10-score-heldout-L3-unified | step-5-preview | 38610 | 12555 | 0 | 30016 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e18791e57ffe6k1bfHxbMDu7f6 | О4: t10-score-heldout-L3-typical | step-5-preview | 5115 | 5555 | 0 | 22720 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e187889feffenzlDsXqS5gnAPi | О4: t10-score-heldout-L4-unified | step-5-preview | 9183 | 19472 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e187732dcffeScoMMscWihO1Zx | О4: t10-score-heldout-L4-typical | step-5-preview | 9171 | 22233 | 0 | 22720 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e18714e59ffeveY7pXqAzEwLMo | О4: t10-score-demo-L0-unified-r2 | step-5-preview | 6 | 1953 | 0 | 26624 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e186f9470ffeb3Xs9k2ffjEjTt | О4: t10-cl2r2-demo-critic2 | step-5-preview | 27925 | 22760 | 0 | 51712 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e186e0308ffesSTnFAEl1WxBaW | О4: t10-cl2r2-t10-cl2-r2-session-r2 | step-5-preview | 15251 | 16336 | 0 | 96000 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e186cf221ffe6eIelYi9Gfazct | О4: t10-cl2r2-demo-score-unified | step-5-preview | 6406 | 1273 | 0 | 23104 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e186cc859ffebrQLRNnU4fxuwc | О4: t10-cl2r2-demo-score-typical | step-5-preview | 27323 | 17644 | 0 | 1792 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e186b57eeffeAaEAmf3niHxsac | О4: t10-cl2r2-heldout-critic2 | step-5-preview | 7583 | 19385 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e1869b907ffevjhS9GNnPGVzZg | О4: t10-cl2r2-t10-cl2-r2-session-r2 | step-5-preview | 8974 | 25575 | 0 | 21568 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e1868099cffeq014Ott7e5hNUp | О4: t10-cl2r2-heldout-score-unified | step-5-preview | 8415 | 15963 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e1866b834ffeNYjubIOkN1dgEK | О4: t10-cl2r2-heldout-score-typical | step-5-preview | 8403 | 11352 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e185698dfffeiA1vW25LiUSkrw | Очередь TASK-hermes-10 закрыта | step-5-preview | 19559 | 655 | 0 | 1792 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e1856793affel8M1SPMaZ5BBt5 | О4: t11-iso-out | step-5-preview | 104 | 607 | 0 | 21248 | 0 | 0 | $0.00 |
| 2026-11-17 | ses_e18549a13ffeIIBxwOaMcqlNw2 | О4: t11-iso-in | step-5-preview | 40 | 513 | 0 | 21312 | 0 | 0 | $0.00 |
| 2026-11-17 | ses_e18548192ffe9zJgAuEAfQjKRi | О4: t11-iso-out | step-5-preview | 40 | 889 | 0 | 21312 | 0 | 0 | $0.00 |
| 2026-11-17 | ses_e1852d489ffewJV3DIcGrjRqPg | О4: t11-k3-demo-L4-0-unified | step-5-preview | 25 | 20278 | 0 | 29376 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e1851522bffe2vk98dXW0aGmE1 | Очередь TASK-hermes-10 закрыта | step-5-preview | 13 | 9794 | 0 | 28992 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e18509984ffePkG4ZGDNz6XJ8b | О4: t11-k3-demo-L4-1-unified | step-5-preview | 25 | 9704 | 0 | 29376 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e184fda2cffelTSrJ5lCoQs4ik | О4: t11-k3-demo-L4-1-typical | step-5-preview | 13 | 13432 | 0 | 28992 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e184ed086ffe06HLHbf5A0GQSL | О4: t11-k3-demo-L4-2-unified | step-5-preview | 25 | 11168 | 0 | 29376 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e184def94ffeebZTf5UibzaTy3 | О4: t11-k3-demo-L4-2-typical | step-5-preview | 13 | 13262 | 0 | 28992 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e184c724bffeIFUbfw78u0k501 | О4: t11-k3-demo-L2-0-unified | step-5-preview | 26078 | 22186 | 0 | 50688 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e184ac81bffedwiWZDGJimwXEY | О4: t11-k3-demo-L2-0-typical | step-5-preview | 4453 | 12937 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e1849bdaaffeQByuOFJBkzH5tE | О4: t11-k3-demo-L3-0-unified | step-5-preview | 4017 | 11880 | 0 | 23168 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e184984eaffeGiPgKS3WrF02uo | О4: t11-k3-demo-L3-0-typical | step-5-preview | 49 | 10969 | 0 | 27136 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e1848c2c4ffeCoa3E2IncASx52 | О4: t11-k3-demo-L3-0-typical | step-5-preview | 4069 | 8327 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e18489c15ffeEGdVA7ObARfH0i | Очередь TASK-hermes-10 закрыта | step-5-preview | 37 | 18249 | 0 | 26752 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e18453919ffeX9d30sNcA7WL0r | О4: t11-k3-demo-L2-1-unified | step-5-preview | 4095 | 7652 | 0 | 23104 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e18448dd6ffeiOzjy7QWV6hP0t | О4: t11-k3-demo-L2-1-typical | step-5-preview | 4083 | 32000 | 0 | 22720 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e18422938ffeW2k00Y0eOcjbcJ | О4: t11-k3-demo-L2-2-unified | step-5-preview | 4387 | 11110 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e18413a25ffeQ6fWSX6BoB7qPy | О4: t11-k3-demo-L2-2-typical | step-5-preview | 14768 | 12688 | 0 | 89600 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e184035a9ffeCWKB24ss8ekj61 | О4: t11-k3-demo-L3-1-unified | step-5-preview | 3643 | 15339 | 0 | 23168 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e183f08b1ffeq3fGvX44npI58Y | О4: t11-k3-demo-L3-1-typical | step-5-preview | 3695 | 13370 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e183da234ffeQjssj7knDcm8HD | О4: t11-k3-demo-L3-2-unified | step-5-preview | 3800 | 9938 | 0 | 23104 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e183cd5e2ffe3drbpw92uLb9i9 | О4: t11-k3-demo-L3-2-typical | step-5-preview | 3788 | 9965 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e1839e250ffejP5G0A52SyC4xE | О4: t11-k3-demo-L2-1-typical | step-5-preview | 51 | 12719 | 0 | 26752 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17f78581ffemmsP3MJB9Dgjn9 | О4: t12-res-curation-0-unified | step-5-preview | 4691 | 22069 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e17f5b2d3ffewnzA5gFs0QUkLs | О4: t12-res-curation-0-typical | step-5-preview | 6094 | 25546 | 0 | 21248 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e17f3aff6ffe6Atr3teTEe9RMs | О4: t12-res-curation-1-unified | step-5-preview | 4426 | 1248 | 0 | 23104 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e17f3745fffefYM8r6zC0k53by | О4: t12-res-curation-1-typical | step-5-preview | 5701 | 12519 | 0 | 21376 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17f23f23ffeLS7nAX7Jdz63qS | О4: t12-res-curation-2-unified | step-5-preview | 4006 | 10728 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17f150f3ffeHj4Tin02BwtnNJ | О4: t12-res-curation-2-typical | step-5-preview | 4001 | 19028 | 0 | 22656 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e17efd9f2ffepF7ydrq9kzLqWE | О4: t12-res-lean-0-unified | step-5-preview | 4730 | 23680 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e17ee065effeVFIlX8qyEIhBYE | О4: t12-res-lean-0-typical | step-5-preview | 4725 | 17904 | 0 | 22656 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e17ec9644ffel4cORv7Aiedenh | О4: t12-res-lean-1-unified | step-5-preview | 4360 | 14432 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17eb5e4cfferjPt9ILWp30dqW | О4: t12-res-lean-1-typical | step-5-preview | 4355 | 22603 | 0 | 22656 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e17e982eeffeeBVw7b2OF8Ji1K | О4: t12-res-lean-2-unified | step-5-preview | 5474 | 17457 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17e81828ffeGFxdIhXYy1ZAc1 | О4: t12-res-lean-2-typical | step-5-preview | 5469 | 16253 | 0 | 22656 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17e6f213ffeJE6J5dlHEPvyH3 | О4: t12-res-hybrid-0-unified | step-5-preview | 4118 | 14678 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17e57344ffeXe6ugTxmsHCGyd | О4: t12-res-hybrid-0-typical | step-5-preview | 4113 | 4617 | 0 | 22656 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e17e4fde6ffe90LtltA9Nku5lz | О4: t12-res-hybrid-1-unified | step-5-preview | 4512 | 32000 | 0 | 23104 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e17e237ecffevM7N7xRJk4PX6E | О4: t12-res-hybrid-1-typical | step-5-preview | 4507 | 16304 | 0 | 22656 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17e05fd3ffeLNk725v0kLqpYg | О4: t12-res-hybrid-2-unified | step-5-preview | 4039 | 15577 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17df0b60ffewrcihTJWqXifsc | О4: t12-res-hybrid-2-typical | step-5-preview | 4034 | 8614 | 0 | 22656 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17de5694ffeiKBCd6O9QB3sX8 | О4: t12-opt-curation-0-unified | step-5-preview | 3264 | 28161 | 0 | 23104 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e17dbada0ffeBxBKDEvgnDBN19 | О4: t12-opt-curation-0-typical | step-5-preview | 4596 | 5842 | 0 | 21376 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e17db0bf0ffe9rL27y4HAJSq2m | О4: t12-opt-curation-1-unified | step-5-preview | 5790 | 11207 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17d9efabffe5sMV8U7eP1xk66 | О4: t12-opt-curation-1-typical | step-5-preview | 5778 | 9155 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17d9059dffeZpfITKA4jaFrO6 | О4: t12-opt-curation-2-unified | step-5-preview | 4496 | 28057 | 0 | 23104 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e17d63f92ffepguLID7CzfcHRb | О4: t12-opt-curation-2-typical | step-5-preview | 4484 | 10260 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17d54b7dffejx6uvjTtGzqa8O | О4: t12-opt-lean-0-unified | step-5-preview | 25818 | 17668 | 0 | 0 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e17d3898affeKAeqa3m6w5dxjW | О4: t12-opt-lean-0-typical | step-5-preview | 2703 | 8063 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17d2aad8ffefRiHjt5Ithk2eP | О4: t12-opt-lean-1-unified | step-5-preview | 3345 | 12163 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17d1726effeV7aVi7F8umXJHp | О4: t12-opt-lean-1-typical | step-5-preview | 3333 | 16015 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17cfdc82ffeFdU4TrgKk39F6m | О4: t12-opt-lean-2-unified | step-5-preview | 2596 | 24160 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e17cdd0e0ffeYKqCeyUXEfweuq | О4: t12-opt-lean-2-typical | step-5-preview | 2584 | 8949 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17cd1682ffe2L4XBc64Xpnykk | О4: t12-opt-hybrid-0-unified | step-5-preview | 2368 | 1391 | 0 | 23168 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e17cce983ffehLQnNEsDLM2R6w | О4: t12-opt-hybrid-0-typical | step-5-preview | 2420 | 5831 | 0 | 22720 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e17cc5fdfffe7D5KkaqpBnRG77 | О4: t12-opt-hybrid-1-unified | step-5-preview | 3343 | 17295 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17caf433ffekTJlIjuhX3YTS6 | О4: t12-opt-hybrid-1-typical | step-5-preview | 3331 | 13312 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17c9b722ffeR04Cp96glQc06c | О4: t12-opt-hybrid-2-unified | step-5-preview | 3176 | 18770 | 0 | 23168 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e17c7d957ffenRrVyRDVvKwPsI | О4: t12-opt-hybrid-2-typical | step-5-preview | 3228 | 16693 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17c62332ffeSICEeq8nKxzii5 | О4: t12-o5a-lean-0-unified | step-5-preview | 4912 | 11316 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17c5076effe2Y4QwxFevlQ6e5 | О4: t12-o5a-lean-0-typical | step-5-preview | 4907 | 12098 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17c3f42affeGvCPr5SH7tvjUv | О4: t12-o5a-lean-1-unified | step-5-preview | 4745 | 11000 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17c28274ffeJyVcsemr3Z967W | О4: t12-o5a-lean-1-typical | step-5-preview | 4740 | 15744 | 0 | 22656 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17c0feeaffetSouLPl08tNfKi | О4: t12-o5a-lean-2-unified | step-5-preview | 4873 | 8207 | 0 | 23104 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17c022d2ffeZHZFOn1SifNYUZ | О4: t12-o5a-lean-2-typical | step-5-preview | 4868 | 13753 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17bed47affe0gTzP7h1G2jkGL | О4: t12-o5bP-skill-0-unified | step-5-preview | 4270 | 20239 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e17bcbb84ffePqh0x0x6ChI2ts | О4: t12-o5bP-skill-0-typical | step-5-preview | 4258 | 17562 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17bb48abffeDboLjodYCgfN0b | О4: t12-o5bP-skill-1-unified | step-5-preview | 4622 | 27384 | 0 | 23104 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e17b908edffeZ9uReZ5aMZGnaa | О4: t12-o5bP-skill-1-typical | step-5-preview | 4610 | 16583 | 0 | 22720 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17b7c789ffeo7gXH0kWvGjty7 | О4: t12-o5bP-skill-2-unified | step-5-preview | 4150 | 16184 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17b66345ffewbDfn0bgfxh27t | О4: t12-o5bP-skill-2-typical | step-5-preview | 4138 | 23924 | 0 | 22720 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e17b41680ffeHgX075Qj6kFV2O | О4: t12-o5bF-skill-0-unified | step-5-preview | 4302 | 1977 | 0 | 23104 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e17b3ced2ffeZKP4HaPDgeeaMe | О4: t12-o5bF-skill-0-typical | step-5-preview | 4480 | 6239 | 0 | 49984 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17b320b0ffe6XcR7YWbTdR2Bf | О4: t12-o5bF-skill-1-unified | step-5-preview | 3347 | 10108 | 0 | 23104 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17b23108ffeVafp6QdM2FM0iA | О4: t12-o5bF-skill-1-typical | step-5-preview | 3335 | 6221 | 0 | 22720 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e17b1ab1fffejPbkVzENNr92NE | О4: t12-o5bF-skill-2-unified | step-5-preview | 4558 | 24928 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e17afa9b8ffe2EHzjHAtRWOJSW | О4: t12-o5bF-skill-2-typical | step-5-preview | 4546 | 12532 | 0 | 22720 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17ad6ceeffeSSc6esAyqU8C1X | О4: t12-res-hybrid-1-unified | step-5-preview | 32 | 12646 | 0 | 27584 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17ac599affe6YpTLyHBkh76N4 | О4: t12-hc2-draft-0-critic | step-5-preview | 53 | 16593 | 0 | 27328 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17aaff2affe6Q6aujnV54ZWwu | О4: t12-hc2-rev-0-patch | step-5-preview | 6211 | 13276 | 0 | 21248 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17aa0c0bffeJdLdh7MSRp08E5 | О4: t12-hc2-draft-1-critic | step-5-preview | 3 | 10447 | 0 | 27008 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17a8ece7ffeiC4IQ4mJpIHCfY | О4: t12-hc2-rev-1-patch | step-5-preview | 5895 | 7723 | 0 | 21248 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17a84b65ffeZhDYLiTjZtxzRL | О4: t12-hc2-draft-2-critic | step-5-preview | 29 | 19126 | 0 | 28096 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17a68035ffe9l349gritM7tbz | О4: t12-hc2-rev-2-patch | step-5-preview | 6764 | 1982 | 0 | 21632 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e17a36ae9ffeOYXK83bjUIk0RS | О4: t12-hc2-revised-0-unified | step-5-preview | 4730 | 18531 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e17a1d54affePrmBTG4wgpaRMn | О4: t12-hc2-revised-0-typical | step-5-preview | 53 | 21635 | 0 | 27328 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e179fad87ffebqPfSyqAQcDcB1 | О4: t12-hc2-revised-1-unified | step-5-preview | 4893 | 25985 | 0 | 23104 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e179d1994ffeLYCU9BsgrtvfZ4 | О4: t12-hc2-revised-1-typical | step-5-preview | 13208 | 10735 | 0 | 14336 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e179c03b6ffemFVJkuqmgbFjsi | О4: t12-hc2-revised-2-unified | step-5-preview | 5474 | 27099 | 0 | 23104 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e1799855affeIaHXPKPRbmaNT6 | О4: t12-hc2-revised-2-typical | step-5-preview | 29 | 11818 | 0 | 28096 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e178a01b1ffe3qjU9scUg7TNx9 | О4: t13-c2-research-curation-0-unified | step-5-preview | 4691 | 29106 | 0 | 23104 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e17857a14ffeJw2CBuHwsh85OM | О4: t13-c2-options-curation-0-unified | step-5-preview | 3264 | 12824 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17830bc0ffecGpaJYVvH3Gpqb | О4: t13-c2-research-curation-1-unified | step-5-preview | 4426 | 1744 | 0 | 23104 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e1782c9e4ffeZcsC4BzW8IsEHf | О4: t13-c2-options-curation-1-unified | step-5-preview | 5790 | 18427 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e17805adfffelTA11IInXvX0gm | О4: t13-c2-research-curation-2-unified | step-5-preview | 25322 | 24460 | 0 | 1792 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e177cecbfffemQXpk0tuy2kOi9 | О4: t13-c2-options-curation-2-unified | step-5-preview | 4496 | 10735 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e177b7d1fffeKMNGEs8R8UtRZL | О4: t13-c2-research-lean-0-unified | step-5-preview | 4730 | 1415 | 0 | 23104 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e177b359effeSZ2OiqtfTcbPfO | О4: t13-c2-options-lean-0-unified | step-5-preview | 2715 | 21334 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e1777f9c6ffeJTtyNFCkOkEsJq | О4: t13-c2-research-lean-1-unified | step-5-preview | 4360 | 27865 | 0 | 23104 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e177411f8ffeFs4YrQBvnX2eGT | О4: t13-c2-options-lean-1-unified | step-5-preview | 3345 | 25302 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e177048f2ffe2YKA1IGkJH25lU | О4: t13-c2-research-lean-2-unified | step-5-preview | 5474 | 16558 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e176df150ffe7dfgUHP5pFqvo2 | О4: t13-c2-options-lean-2-unified | step-5-preview | 2596 | 17343 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e176b3639ffeGgt8Qi5AqEfqIu | О4: t13-c2-research-hybrid-0-unified | step-5-preview | 4118 | 17680 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17682667ffel7VBg5bKCUfjBa | О4: t13-c2-options-hybrid-0-unified | step-5-preview | 2368 | 21767 | 0 | 23168 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e17643e89ffe2V0eCtAc27ycRV | О4: t13-c2-research-hybrid-1-unified | step-5-preview | 4512 | 22444 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e176087b7ffesWjWOrOdD5SUSK | О4: t13-c2-options-hybrid-1-unified | step-5-preview | 3343 | 17531 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e175e1c6effe6Pu1CMklWcTg37 | О4: t13-c2-research-hybrid-2-unified | step-5-preview | 4039 | 13060 | 0 | 23104 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e175c5bf2fferuAdFbV1KFcXiT | О4: t13-c2-options-hybrid-2-unified | step-5-preview | 3176 | 18274 | 0 | 23168 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e1759c215ffe2FC7oqqfRWy7qK | О4: t13-c2-reslean-typ-0 | step-5-preview | 26741 | 5316 | 0 | 640 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17590c87ffeScR4eoEVnO9xAD | О4: t13-c2-o5alean-typ-0 | step-5-preview | 6187 | 11834 | 0 | 21376 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e17571bfaffecICL3VG7tYqZXa | О4: t13-c2-o5bF-typ-0 | step-5-preview | 5634 | 14584 | 0 | 21376 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17551466ffeSPlRH4txMS37C1 | О4: t13-c2-reslean-typ-1 | step-5-preview | 4355 | 13459 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e1752fd48ffeghfmgXWnw66DLr | О4: t13-c2-o5alean-typ-1 | step-5-preview | 4740 | 9369 | 0 | 22656 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17516a62ffemVrtMKn3u5fo6B | О4: t13-c2-o5bF-typ-1 | step-5-preview | 4679 | 15657 | 0 | 21376 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e174ef574ffeUFh038xLECMNAs | О4: t13-c2-reslean-typ-2 | step-5-preview | 6955 | 13036 | 0 | 62208 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e174cf1c2ffeSH3O1sUNlfDCrm | О4: t13-c2-o5alean-typ-2 | step-5-preview | 4868 | 18279 | 0 | 22656 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e174a3580ffenVGDRFWRA2csL6 | О4: t13-c2-o5bF-typ-2 | step-5-preview | 4546 | 8510 | 0 | 22720 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e17465ce5ffeCUMrdKkna5Vlu7 | О4: t13-trigger-heldout | step-5-preview | 5170 | 280 | 0 | 16960 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e1743b516ffeelV7ApLTD3AD99 | О4: t13hc1-res-curation-0-unified | step-5-preview | 4791 | 21935 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e17406229ffeNVgGXJjk7b7cJN | О4: t13hc1-res-curation-0-typical | step-5-preview | 4786 | 9467 | 0 | 22656 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e173ead3effevZDnDxNyzbX3aR | О4: t13hc1-res-curation-1-unified | step-5-preview | 6316 | 19134 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e173b91a1ffePbAQ4inzWL0czV | Очередь TASK-hermes-12 закрыта | step-5-preview | 6311 | 9521 | 0 | 22656 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e173a1437ffe37Xxhdyq3doELx | Очередь TASK-hermes-12 закрыта | step-5-preview | 4829 | 19249 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e17372c89ffeNNyOm6zs7B46x8 | О4: t13hc1-res-curation-2-typical | step-5-preview | 4824 | 9060 | 0 | 22656 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e1735e4a0ffeKa2CL1WvQnKG9t | О4: t13hc1-res-lean-0-unified | step-5-preview | 4909 | 16524 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17334de1ffeoLJhRErBbeUY6j | О4: t13hc1-res-lean-0-typical | step-5-preview | 4904 | 13627 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e1730e290ffeJpascjBzH80N5b | О4: t13hc1-res-lean-1-unified | step-5-preview | 6614 | 13603 | 0 | 23104 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e172eca96ffew9tE8haT4aqoXH | О4: t13hc1-res-lean-1-typical | step-5-preview | 6609 | 12498 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e172ce854ffeAu7aoUbag3rgkR | О4: t13hc1-res-lean-2-unified | step-5-preview | 7505 | 21382 | 0 | 23104 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e1728ef45ffedtZBcGRjJTN2U7 | О4: t13hc1-res-lean-2-typical | step-5-preview | 7500 | 12317 | 0 | 22656 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e1726acd9ffe0zAshx0Cg2uPQa | О4: t13hc1-res-hybrid-0-unified | step-5-preview | 5710 | 20113 | 0 | 23104 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e17225a45ffewnO4K3uCryNkq4 | О4: t13hc1-res-hybrid-0-typical | step-5-preview | 30648 | 15513 | 0 | 0 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e171f8a7fffe6SJH5U72NIObeH | О4: t13hc1-res-hybrid-1-unified | step-5-preview | 30664 | 22296 | 0 | 0 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e171bd4a0ffeYMkJMvS5IuPI7w | О4: t13hc1-res-hybrid-1-typical | step-5-preview | 29570 | 14586 | 0 | 640 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e171933f0ffe3LkkpktwerpsES | О4: t13hc1-res-hybrid-2-unified | step-5-preview | 28349 | 27698 | 0 | 1792 | 0 | 0 | $0.10 |
| 2026-11-17 | ses_e171451d9ffed7woqzXQKHbjLg | О4: t13hc1-res-hybrid-2-typical | step-5-preview | 5816 | 7032 | 0 | 23872 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e1712ec63ffeFr8k5u8qfIQU51 | О4: t13hc1-opt-curation-0-unified | step-5-preview | 5290 | 19247 | 0 | 23872 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e170f65bcffem5xRPzNb1o4brg | О4: t13hc1-opt-curation-0-typical | step-5-preview | 4894 | 12643 | 0 | 23872 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e170dbb5bffeK8M5ktY3cU2LOZ | О4: t13hc1-opt-curation-1-unified | step-5-preview | 4327 | 13076 | 0 | 25600 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e170c0888ffeLGMW2lSKCbu8As | О4: t13hc1-opt-curation-1-typical | step-5-preview | 5659 | 22317 | 0 | 23872 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e1708eda3ffexhvXySgjJNEnaF | О4: t13hc1-opt-curation-2-unified | step-5-preview | 28552 | 14184 | 0 | 640 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e1706ded9ffezNsQJ13YvyeZHf | О4: t13hc1-opt-curation-2-typical | step-5-preview | 28197 | 9080 | 0 | 640 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e17052d0dffekPzMZSMJh9JSUm | О4: t13hc1-opt-lean-0-unified | step-5-preview | 26512 | 12810 | 0 | 1856 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e170334b1ffeIJoArzJO5nYwrO | О4: t13hc1-opt-lean-0-typical | step-5-preview | 9839 | 11345 | 0 | 59136 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e170173e8ffeqFYylV0VBiKXxS | О4: t13hc1-opt-lean-1-unified | step-5-preview | 4281 | 15243 | 0 | 24064 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e16feed09ffegvIBbvJMw21PHz | О4: t13hc1-opt-lean-1-typical | step-5-preview | 2541 | 11430 | 0 | 25408 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e16fd5789ffedVCC2ncSjUofPS | О4: t13hc1-opt-lean-2-unified | step-5-preview | 3168 | 30945 | 0 | 25792 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e16f86c89ffe4pfbjxqTeiLGXN | О4: t13hc1-opt-lean-2-typical | step-5-preview | 3156 | 20579 | 0 | 25408 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16f59e22ffeubFwFN4lbUeL6N | О4: t13hc1-opt-hybrid-0-unified | step-5-preview | 3286 | 11939 | 0 | 25792 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e16f3d390ffegCd7wYfsRwo5kN | О4: t13hc1-opt-hybrid-0-typical | step-5-preview | 3274 | 11859 | 0 | 25408 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e16f20829ffeSkOh7KpF9nKZE4 | О4: t13hc1-opt-hybrid-1-unified | step-5-preview | 4046 | 14802 | 0 | 25792 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e16f001bfffefIszKz2eaKsCPi | О4: t13hc1-opt-hybrid-1-typical | step-5-preview | 4034 | 11325 | 0 | 25408 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e16ee4ef9ffe6bWPjiRhr329oi | О4: t13hc1-opt-hybrid-2-unified | step-5-preview | 3862 | 19833 | 0 | 25856 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16ebaf47ffeOLIJDUS0hTYNHN | О4: t13hc1-opt-hybrid-2-typical | step-5-preview | 3914 | 8586 | 0 | 25408 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e16e6aa06ffeR6eb7A9iZ2Z8bK | Очередь TASK-hermes-12 закрыта | step-5-preview | 4778 | 14175 | 0 | 25792 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e16e4d428ffeVyWsBFdh9pyi0U | Очередь TASK-hermes-12 закрыта | step-5-preview | 29477 | 9984 | 0 | 640 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16e37f66ffe4u51jrw6mSHrwu | О4: t13hc2-res-curation-1-unified | step-5-preview | 6303 | 32000 | 0 | 25792 | 0 | 0 | $0.10 |
| 2026-11-17 | ses_e16df466dffe83LadCzfh3IATj | О4: t13hc2-res-curation-1-typical | step-5-preview | 7578 | 13600 | 0 | 24064 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e16dd44e0ffe8rEYe3QTJeqrgK | О4: t13hc2-res-curation-2-unified | step-5-preview | 4816 | 25032 | 0 | 25792 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e16d9e12affetDdxCN139cm683 | О4: t13hc2-res-curation-2-typical | step-5-preview | 4811 | 16305 | 0 | 25344 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e16d7f82affeSvFlfRWRzPPng1 | О4: t13hc2-res-lean-0-unified | step-5-preview | 4896 | 1675 | 0 | 25792 | 0 | 0 | $0.01 |
| 2026-11-17 | ses_e16d7ada7ffe3d8Lm6s5ChKEMW | О4: t13hc2-res-lean-0-typical | step-5-preview | 4891 | 8998 | 0 | 25344 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e16d6913affeunxu4LgLrtm6en | О4: t13hc2-res-lean-1-unified | step-5-preview | 6601 | 18553 | 0 | 25792 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16d40194ffeh1fznwEl93KXUA | О4: t13hc2-res-lean-1-typical | step-5-preview | 6596 | 3759 | 0 | 25344 | 0 | 0 | $0.02 |
| 2026-11-17 | ses_e16d367faffeAQOpM1Q1pPZhca | О4: t13hc2-res-lean-2-unified | step-5-preview | 7492 | 15992 | 0 | 25792 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e16d0e938ffeqrztoy9kTXArFK | О4: t13hc2-res-lean-2-typical | step-5-preview | 32443 | 11884 | 0 | 0 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16cef02cffe3vEUO5NX14dVPn | О4: t13hc2-res-hybrid-0-unified | step-5-preview | 30461 | 11269 | 0 | 640 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16cd4a3cffeuIpVXKv52ZIuiN | О4: t13hc2-res-hybrid-0-typical | step-5-preview | 6968 | 7981 | 0 | 23680 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e16cc2608ffecx8QxSUo2jWK4B | О4: t13hc2-res-hybrid-1-unified | step-5-preview | 6782 | 26350 | 0 | 23680 | 0 | 0 | $0.08 |
| 2026-11-17 | ses_e16c89b0fffe41g43ad8IzabaI | О4: t13hc2-res-hybrid-1-typical | step-5-preview | 30010 | 9369 | 0 | 0 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16c73846ffeZ1ERBCw9GbBxxx | О4: t13hc2-res-hybrid-2-unified | step-5-preview | 4532 | 14929 | 0 | 25408 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e16c4d689ffeqZ7ICyiGdgVmcW | Очередь TASK-hermes-12 закрыта | step-5-preview | 4527 | 24043 | 0 | 24960 | 0 | 0 | $0.07 |
| 2026-11-17 | ses_e16c16aa3ffejScJJ02PJTUDdm | О4: t13hc2-opt-curation-0-unified | step-5-preview | 3553 | 8210 | 0 | 25408 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e16c01932ffegb2T2BN0j52gCm | О4: t13hc2-opt-curation-0-typical | step-5-preview | 4885 | 6765 | 0 | 23680 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e16beec90ffeqJzUly7teFSbM8 | О4: t13hc2-opt-curation-1-unified | step-5-preview | 4318 | 21044 | 0 | 25408 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16bc3f8affe4CRQSBkWOv0jyR | О4: t13hc2-opt-curation-1-typical | step-5-preview | 5650 | 12081 | 0 | 23680 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e16ba9350ffeYTz3RYvkgRDBl8 | О4: t13hc2-opt-curation-2-unified | step-5-preview | 3437 | 8179 | 0 | 25408 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e16b972fdffeK688GmTnnLQyS4 | О4: t13hc2-opt-curation-2-typical | step-5-preview | 3425 | 10678 | 0 | 25024 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e16b7ad65ffeJDLL0BE5PqoTXG | Очередь TASK-hermes-12 закрыта | step-5-preview | 2572 | 14757 | 0 | 25408 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e16b5d88bffe8f0tHIRfmE18l1 | О4: t13hc2-opt-lean-0-typical | step-5-preview | 2560 | 18028 | 0 | 25024 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e16b378dcffeSAAnbPRmWy50ex | О4: t13hc2-opt-lean-1-unified | step-5-preview | 2549 | 19038 | 0 | 25408 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16b0b8ebffeppaWKOSTHa2UR4 | О4: t13hc2-opt-lean-1-typical | step-5-preview | 2537 | 12951 | 0 | 25024 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e16af1bedffeLC8WmfJ19GPjQ2 | О4: t13hc2-opt-lean-2-unified | step-5-preview | 3164 | 14274 | 0 | 25408 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e16ad9398ffeN5N17DVpIgEsIY | О4: t13hc2-opt-lean-2-typical | step-5-preview | 26781 | 24114 | 0 | 53184 | 0 | 0 | $0.10 |
| 2026-11-17 | ses_e16ab15bdffepXYPceq2IuWgud | О4: t13hc2-opt-hybrid-0-unified | step-5-preview | 3282 | 8824 | 0 | 25408 | 0 | 0 | $0.03 |
| 2026-11-17 | ses_e16aa1c5dffe4mh83J3QF9EPHU | О4: t13hc2-opt-hybrid-0-typical | step-5-preview | 3270 | 17320 | 0 | 25024 | 0 | 0 | $0.05 |
| 2026-11-17 | ses_e16a84d88ffeVjwTVfZLaZ2sIN | О4: t13hc2-opt-hybrid-1-unified | step-5-preview | 4042 | 17993 | 0 | 25408 | 0 | 0 | $0.06 |
| 2026-11-17 | ses_e16a61d01ffenyebIEJRTnrJ2S | О4: t13hc2-opt-hybrid-1-typical | step-5-preview | 4030 | 30460 | 0 | 25024 | 0 | 0 | $0.09 |
| 2026-11-17 | ses_e16a296ffffenzJ7yKVvhJWMFT | О4: t13hc2-opt-hybrid-2-unified | step-5-preview | 3858 | 12524 | 0 | 25472 | 0 | 0 | $0.04 |
| 2026-11-17 | ses_e16a12325ffe3eUcnxH2BXG2vG | О4: t13hc2-opt-hybrid-2-typical | step-5-preview | 3910 | 16363 | 0 | 25024 | 0 | 0 | $0.05 |
<!-- cost-rows:end -->

Примечания к прод-таблице:
- Строка `ses_e1b3f4ed5ffe…` сверена с БД OpenCode (session totals:
  29 775 in / 46 821 out / cache-read 2 365 504): агрегат хука жил в памяти
  процесса и при продолжении сессии новым запуском заменял строку вместо
  мержа (баг исправлен 18:40). В БД-итоге включены и токены прогона, убитого
  внешним прерыванием (хук пишет на session.idle — убитая сессия до события
  не дошла); восстановлено из БД как наиболее полный честный учёт.
  Внутренняя cost OpenCode по прайсам models.dev для этой сессии — $0.42;
  наша формула (§1.8) даёт $0.39 — разница ≤10%, как и в dev-таблице.
- `ses_e1b383769ffe…` — сессия возобновления шага 1 (новый чат после
  прерывания). Хук: 41 697 / 24 448; БД OpenCode: 41 420 / 24 279 —
  расхождение 0.7% (разные точки агрегации), в пределах шума.
- `ses_e1b345cf1ffe…` — проверка исправленного мержа: два последовательных
  прогона одной сессии дали 120/64 и 110/40; строка накопила 230/104
  (до фикса второй прогон заменил бы первый).
- **Корректировка учёта (2026-11-16, О3) — дефект хука cost-append.**
  Найдено при прогонах Консилиума: агрегат сессии инициализировался
  снимком токенов (`{...snap}`), а затем первое сообщение добавлялось
  ещё раз через counted-дельту (`+= snap`) — первое сообщение каждой
  сессии считалось дважды. Для сессии с ОДНИМ ассистентским сообщением
  (все ролевые прогоны Консилиума) строка была равна 2× истины; для
  многосообщений сессий (шаги 0–4, N сообщений) раздутие (N+1)/N ≈
  0–5%. Доказательство: отношение строка-хука / БД OpenCode = ровно
  2.000 на всех 13 прогонах Консилиума и 0–5% на шагах 0–4 (БД —
  таблица message, токены финального сообщения). Исправление: база
  агрегата — нули (`.opencode/plugins/strategy-hooks.ts`); верификация
  фикса: прогон `hook-fix-verify` дал строку 26/25 = БД 26/25 точно.
  Постфактум 25 строк таблицы переписаны на токены из БД OpenCode
  (источник истины), $ пересчитаны по формуле §1.8; шаги 0–4, которые
  проверял PO как «$2.06», после корректировки — $2.04 (Δ≤1%, в
  пределах заявленной кросс-проверки ±10%). Остаточная аппроксимация:
  цена §1.8 (step-5-preview) применена и к строкам step-3.7-flash —
  кросс-проверка с внутренним cost OpenCode (models.dev, per-model
  цены) — в `docs/research/measurements.md`.
