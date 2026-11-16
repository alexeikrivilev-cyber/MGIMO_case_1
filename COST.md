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
| 2026-11-16 | Продолжение прерванного прогона: cost_report.py + починка тестового контракта (44/44 зелёные), пробы CLI | step-5-preview (Hermes) | — | — | не метрится рантаймом | отмечено честно, не оцениваем; поисковых вызовов: 0 |

## Контур прода (prod) — метрика $/прогон для пользователя

Прайс целевой среды (OpenCode, dev-контур прогонов): `step-5-preview` —
$1.00/M input (cache miss), $0.10/M cache hit, $2.70/M output
(output включает reasoning — reasoning не добавляется поверх output).
Источник: `docs/research/llm-pricing-agent-costs.md` §1.8 (StepFun,
international price list, доступ 2026-11-16).

| Дата | Прогон (sessionID) | Шаг | Модель | in | out | reasoning | cache read | cache write | поиск | Оценка $ |
|---|---|---|---|---|---|---|---|---|---|---|
<!-- cost-rows:begin -->
<!-- cost-rows:end -->
