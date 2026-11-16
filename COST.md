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
