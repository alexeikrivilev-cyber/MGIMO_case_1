# ev-001 — Bank Marketing (UCI id 222): состав, период и провенанс датасета

> Запись доказательства шага 1 (навык `knowledge/skills/evidence/SKILL.md`),
> шаблон `templates/evidence-record.md`. Задача:
> `eval/tasks/heldout-growth-segment` («ДомКниг»).

## Факт (формулировка)

- Датасет Bank Marketing (UCI, id 222) — результат телефонных
  маркетинговых кампаний португальского банка; цель — предсказать,
  подпишет ли клиент срочный депозит (переменная `y`); страница UCI:
  https://archive.ics.uci.edu/dataset/222/bank+marketing (ev-001).
- В zip четыре файла: `bank-additional-full.csv` — 41 188 строк и 20
  признаков, упорядочен по дате с мая 2008 по ноябрь 2010;
  `bank-full.csv` — та же выборка в старой версии из 17 признаков
  (45 211 строк на странице UCI) — источник: ev-001.
- Анализируемый файл этого прогона — `bank-additional-full.csv`
  (41 188 × 21 с `y`): собственный подсчёт, ev-002.
- Авторы и цитирование: Moro, S., Rita, P., Cortez, P. (2014), Decision
  Support Systems; DOI датасета 10.24432/C5K306; лицензия CC BY 4.0
  (источник: ev-001).

## Источник

- URL: https://archive.ics.uci.edu/dataset/222/bank+marketing
- Дата доступа: 2026-11-16
- Что подтверждает (цитата / число / таблица): страница UCI: «# Instances
  45211», «# Features 16», «ordered by date (from May 2008 to November
  2010)»; файл `bank-additional-names.txt` внутри zip: «Number of
  Instances: 41188 for bank-additional-full.csv», «The binary
  classification goal is to predict if the client will subscribe a bank
  term deposit (variable y)».
- Автор/организация: UCI Machine Learning Repository; авторы датасета —
  S. Moro, P. Rita, P. Cortez.

## Тип

- [x] факт (есть источник — URL выше, дата доступа 2026-11-16, ev-001)
- [ ] гипотеза
- [ ] прогноз

## Связь с задачей

- Решающий вопрос из brief.md: №2 «насколько переносим банковский аналог
  на сервис подписки на книги» — эта запись фиксирует, ЧТО именно
  загружено (период, объём, контекст), чтобы на шаге 2 числа
  использовались с оглядкой на границы применимости (ev-001).
- Как используется в артефакте: основание для выбора файла анализа
  (`bank-additional-full.csv`) и для маркировки [гипотеза] переносимости
  всех чисел отклика на «ДомКниг».

## Конфликты

- Страница UCI declares «Has Missing Values? No», а файл
  `bank-additional-names.txt` того же архива: «There are several missing
  values in some categorical attributes, all coded with the "unknown"
  label» (ev-001). Конфликт зафиксирован парой, не усреднён: пропуски
  маскированы меткой `unknown`, поэтому «нет пропусков» на странице —
  утверждение о формате хранения, не о полноте. Практическое следствие:
  категории `unknown` на шаге 2 не считать настоящим сегментом.

## Сырой материал

- `eval/tasks/heldout-growth-segment/artifacts/materials/page-uci-222-bank-marketing.txt`
  (снимок страницы, 2026-11-16, ev-001)
- `eval/tasks/heldout-growth-segment/artifacts/materials/bank-marketing.zip`
  (скачан `scripts/fetch_with_retry.py`, 1 023 843 байта, ev-001)
