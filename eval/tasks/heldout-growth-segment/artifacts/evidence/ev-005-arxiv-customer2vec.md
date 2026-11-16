# ev-005 — arXiv 2012.11876: методика сегментации Customer2Vec

> Запись доказательства шага 1. Источник — страница abstract arXiv (полный текст PDF в этом прогоне не читался — именованный пробел ниже).

## Факт (формулировка)

- Работа: Mousaeirad, S. «Intelligent Vector-based Customer Segmentation in the Banking Industry», arXiv:2012.11876 [cs.IR], submitted 22 Dec 2020; https://arxiv.org/abs/2012.11876 (ev-005).
- Заявленный метод Customer2Vec: инженерия признаков из пула «demographics, geography, psychographics, behavioral» с подачей в нейро-эмбеддинг, сочетающий классификацию (supervised) и кластеризацию (unsupervised) (ev-005).
- Заявка авторов: подход «significantly improves the quality of the segmentation and detecting customer similarities»; сценарий проверки — банковский сектор (ev-005).
- Заявленная цель сегментации в работе: «enable an organization to effectively allocate marketing resources» и «identifying the customer cohorts that are most likely to benefit from a specific policy» (ev-005).

## Источник

- URL: https://arxiv.org/abs/2012.11876
- Дата доступа: 2026-11-16
- Что подтверждает (цитата / число / таблица): abstract на странице arXiv (снимок — `materials/page-arxiv-2012.11876.txt`, ev-005): «feed them into a neural embedding framework named Customer2Vec … combines the neural network classification and clustering methods as supervised and unsupervised learning techniques to embed the customer vector».
- Автор/организация: Salman Mousaeirad; arXiv (cs.IR); DOI 10.48550/arXiv.2012.11876.

## Тип

- [x] факт (о существовании и заявках метода; основание — URL выше, ev-005)
- [ ] гипотеза
- [ ] прогноз

## Связь с задачей

- Решающий вопрос из brief.md: №2 (переносимость и методология). Запись даёт МЕТОД построения сегментов для шагов 2–3: признаки → эмбеддинг → кластеры, пригодные для таргетирования (ev-005); применимость к «ДомКниг» — [гипотеза], отраслевой контекст источника — банк.
- Как используется в артефакте: обоснование выбора механизма сегментации на шаге 2 (векторные признаки вместо одной демографической переменной, ev-005) и напоминание, что «значимое улучшение» — заявка авторов в банковском сценарии, а не измеренный факт для книжной подписки.

## Конфликты

- Конфликт оснований: внутриисточникового конфликта нет; конфликт — между заявкой метода (работает «значительно лучше» в банке, ev-005) и отсутствием независимой проверки на предметной области «ДомКниг» [гипотеза]. Зафиксированы оба утверждения; усреднения нет.

## Пробелы (именованно)

- Полный текст (PDF/HTML) не читался: в перечне материалов указано «методология из аннотации (полный текст — по желанию)» (ev-005). Если шагу 2 понадобятся детали (какие именно признаки, метрики качества), источник придётся дочитать — пробел именован, не замазан.

## Сырой материал

- `eval/tasks/heldout-growth-segment/artifacts/materials/page-arxiv-2012.11876.txt` (снимок abstract, 2026-11-16, ev-005)
