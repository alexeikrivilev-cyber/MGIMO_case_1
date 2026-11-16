# ev-001: отраслевые бенчмарки удержания Mixpanel (2025 State of Media & Entertainment)

> Запись доказательства шага 1 (навык `evidence`), демо-задача
> `eval/tasks/demo-retention`. Шаблон — `templates/evidence-record.md`.

## Факт (формулировка)

- Mixpanel опубликовал отчёт «2025 State of Media & Entertainment Product
  Analytics»: анализ 3.72 трлн событий, 14.16 млрд уникальных пользователей
  и 2 713 медиа-и развлекательных компаний; отчёт покрывает три области —
  acquisition, engagement и retention — с разбивкой по субиндустриям,
  включая streaming; среди отслеживаемых метрик — churn rate.
- Страница-анонс НЕ содержит конкретных бенчмаркных величин удержания:
  числа — внутри скачиваемого отчёта (см. «Пробелы»).

## Источник

- URL: https://mixpanel.com/blog/2025-state-of-media-entertainment-product-analytics-report-benchmarks/
- Дата доступа: 2026-11-16
- Что подтверждает (цитата / число / таблица): «We crunched the numbers and
  analyzed 3.72 trillion events across 14.16 billion unique users from 2,713
  media and entertainment companies»; «focuses on three key areas of product
  success—acquisition, engagement, and retention»; «key sectors—social media,
  publishers, streaming, gaming, creative, broadcasting»; «Key metrics to
  track like app install rate, session duration, DAU, WAU, MAU, CLTV, user
  login sessions, churn rate…»
- Автор/организация: Brandon Weaver (Senior Content Marketing Manager),
  Mixpanel; опубликовано Dec 13, 2024, последняя правка Dec 16, 2024.

## Тип

- [x] факт (есть источник)
- [ ] гипотеза (предположение, помечено)
- [ ] прогноз (помечено)

## Связь с задачей

- Решающий вопрос из brief.md: №4 — «Насколько кривая удержания сервиса
  отличается от отраслевых бенчмарков streaming (Mixpanel)?»
- Как используется в артефакте: внешняя точка сравнения для шага 2 —
  отраслевой ориентир, НЕ данные «МегаТВ Онлайн». Связь «наш сервис =
  эталонная совокупность Mixpanel» — [гипотеза] переносимости, проверяется
  в исследовании.
- Оговорка демо: «МегаТВ Онлайн» — вымышленный сервис, его цифры — сценарий
  [допущение]; бенчмарки Mixpanel используются как внешний ориентир с
  пометкой источника.

## Конфликты

- Конфликтов с другими источниками шага 1 не выявлено. Название отчёта
  «2025» при публикации анонса в декабре 2024 — аномалии нет (отчёт назван
  по охватываемому году), зафиксировано для точности.

## Пробелы

- Конкретные величины бенчмарков удержания (retention) по субиндустриям и
  streaming на странице отсутствуют: только анонс со ссылкой на скачивание
  отчёта (https://mixpanel.com/m/benchmarks-report-2025-media-entertainment/).
  Попытка получить числа со страницы — недоступность (требуется загрузка
  отчёта). Форму/ регистрацию для скачивания не обходили. Пробел назван
  явно: на шаге 2 сравнение с отраслевым уровнем возможно только после
  получения полного отчёта — иначе сравнивать будет не с чем.
- Методология отчёта (как считается retention, определения когорт) на
  странице не раскрыта.

## Сырой материал

- `project/materials/mixpanel-media-ent-report.txt` (снимок страницы,
  источник и дата доступа — в шапке файла)

## Ре-проверка 2026-11-16 (О4, браузер, живая страница)

- URL блога резолвится (200), все проверенные цитаты совпадают дословно:
  3.72 trillion / 14.16 billion / 2,713 компании / три области / streaming /
  churn rate / автор Brandon Weaver / дата Dec 13, 2024. Артефакт прогона —
  `eval/runs/browser-live-check-2026-11-16/results.md`.
- Дрейф страницы (зафиксирован, не усреднён): URL скачивания
  https://mixpanel.com/m/benchmarks-report-2025-media-entertainment/
  резолвится, но его заголовок теперь «Mixpanel | State of Digital
  Analytics 2026» — страница ведёт на более новый отчёт. Пробел
  «величины бенчмарков недоступны» остаётся открытым и становится
  строже: Numbers за формой скачивания, канон года — не наш.
