# Материалы демо-задачи demo-retention (открытые источники)

> Источники материалов для шага 1 (навык `evidence`). Все — открытые,
> проверены fetch 2026-11-16 (HTTP 200). Датасет — аналог структуры данных
> вымышленного сервиса «МегаТВ Онлайн», не его реальные данные (допущение
> демо помечается как гипотеза в evidence).

## Перечень источников

| # | Источник | URL | Что даёт | Дата доступа |
|---|---|---|---|---|
| 1 | Mixpanel — 2025 State of Media & Entertainment Product Analytics (benchmarks: retention по субиндустриям, streaming) | https://mixpanel.com/blog/2025-state-of-media-entertainment-product-analytics-report-benchmarks/ | Бенчмарки удержания индустрии для сравнения нашей кривой | 2026-11-16 |
| 2 | IBM Telco Customer Churn (открытый датасет, 7 043 клиента, 20 признаков + churn) — оригинал Kaggle; прямое скачивание (зеркало MLBookcamp) | https://www.kaggle.com/datasets/blastchar/telco-customer-churn ; https://raw.githubusercontent.com/alexeygrigorev/mlbookcamp-code/master/chapter-03-churn-prediction/WA_Fn-UseC_-Telco-Customer-Churn.csv | Структура данных для анализа драйверов оттока | 2026-11-16 |
| 3 | arXiv 2608.26151 — Explainable AI for Customer Churn Prediction in Telecommunications (CRM integration framework) | https://arxiv.org/abs/2608.26151 | Измеримые драйверы оттока (тип контракта: month-to-month 42.7% vs 2-year 2.8%) и рамка интервенций | 2026-11-16 |

## Как используются

- Источник 1 — внешняя точка сравнения: отраслевые бенчмарки удержания
  (не по нашему сервису; в evidence помечаются как внешний ориентир).
- Источник 2 — структура и драйверы оттока на аналогичных данных;
  в evidence связь «наш сервис = этот датасет» помечается гипотезой.
- Источник 3 — рамка измеримых драйверов оттока и интервенций.

## Ограничения

- Бенчмарки Mixpanel — отраслевые, не по нашему сервису.
- Датасет IBM Telco Churn — открытый аналог структуры, не данные сервиса.
- Внутренняя выгрузка когорт «МегаТВ Онлайн» — условная (сценарий демо),
  в evidence не выдаётся за реальные данные.
