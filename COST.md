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
