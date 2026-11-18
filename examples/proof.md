# Доказательство: пример диалога — запись реального прогона

Файл подтверждает, что [`dialogue.md`](dialogue.md) — не реконструкция и
не «красивый рассказ», а выжимка из записей реального прогона, которые
лежат в этом же репозитории. Каждый пункт ниже содержит: что утверждается,
где запись, и **чем это можно проверить самостоятельно** (команда или
файл). Все команды выполняются из корня репозитория, без ключей и без
оплаты.

## 1. Что это был за прогон

| Параметр | Значение | Где запись |
|---|---|---|
| Задача | `demo-retention` («МегаТВ Онлайн», удержание) | `eval/tasks/demo-retention/task.md` |
| Драйвер | `eval/run_full_case.py`, шаги 0–5, гейты с явными кодами возврата, ревизионные раунды, критик-детектор на шагах 4–5 | `eval/run_full_case.py` |
| Старт | 2026-11-17T16:32:19+00:00 | `eval/runs/t18-case/manifest.md` (первая строка) |
| Модель сессий | `stepfun/step-5-preview` | там же |
| Контракт сессий | входы инлайном, артефакт — ответом в чат; порог годности 2000 символов + markdown-заголовок | там же |
| Итог | все гейты зелёные, `RUNNER_EXIT=0` | `eval/runs/t18-case-launch.log` (последние строки) |

## 2. Журнал прогона (дословно)

Полный журнал — `eval/runs/t18-case/manifest.md`. Ключевые строки,
проверяемые `grep`:

```bash
grep -n "раунд 1 — провал" eval/runs/t18-case/manifest.md
grep -n "ИТОГ: все гейты зелёные" eval/runs/t18-case/manifest.md
```

Строки, на которые опирается диалог:

```
- options.md: раунд 1 — провал гейтов: ['sources-options.md'] → ревизия
- options.md: гейты зелёные (раунд 2)
- strategy-product.md: раунд 2 — провал гейтов: ['transferability-strategy-product.md', 'acceptance', 'actionability'] → ревизия
- strategy-product.md: гейты зелёные (раунд 3)
- decisions.md: раунд 1 — провал гейтов: ['ranges'] → ревизия
- критик t18-case-critic4: exit=0
- критик t18-case-critic5: exit=0
- ИТОГ: все гейты зелёные
```

## 3. Провал первого полного пути и перезапуск (дословно из лога)

`eval/runs/t18-case-launch.log` содержит ДВА запуска. Первый:

```
[options.md] итог гейтов: {'sources-options.md': 0, 'transferability-options.md': 0, 'options': 0, 'complexity': 0, 'ranges': 2}
RUNNER_EXIT=4
```

Второй (победный):

```
[options.md] гейты зелёные (раунд 2)
...
[шаг 5 после критика] гейты: {'sources-decisions.md': 0, 'transferability-decisions.md': 0, 'decisions': 0, 'ranges': 0}
== итог: зелено
RUNNER_EXIT=0
```

Проверка: `grep -n "RUNNER_EXIT" eval/runs/t18-case-launch.log` — должны
быть оба кода (4 и 0).

## 4. Применение находок критика — с сохранением целостности

Строки из `eval/runs/t18-case-launch.log`:

```
applied=7 not_found=1 ambiguous=0 rejected=3 fallback=no integrity=ok size_ratio=1.07
applied=8 not_found=0 ambiguous=0 rejected=5 fallback=no integrity=ok size_ratio=1.04
applied=6 not_found=0 ambiguous=0 rejected=3 fallback=no integrity=ok size_ratio=1.02
...
applied=9 not_found=0 ambiguous=0 rejected=0 fallback=no integrity=ok size_ratio=1.13
```

Формат: сколько патчей применено / не найдено / неоднозначно /
**отклонено** integrity-гейтом. Отклонённые патчи — не сбой: гейт не даёт
правке сломать структуру артефакта (механика — `scripts/apply_revision.py`).

Сами находки (дословно, с оценками по рубрике 1:1 из критериев хакатона):
`eval/runs/t18-case/critic4/findings.md` и `critic5/findings.md`.
Проверка: `head -30 eval/runs/t18-case/critic4/findings.md`.

## 5. Артефакты: хеши и «один дом факта»

Соглашение хеша — `eval/run_full_case.py`, `sha256_of` (первые 16
символов sha256). Актуальные значения (сверены 2026-11-18;
`project/` и `eval/runs/t18-case/artifacts/` побайтово identical):

```bash
for f in research options strategy-product strategy-comms verification-plan decisions; do
  printf "%-20s %s\n" "$f" "$(sha256sum project/$f.md | cut -c1-16)"
done
```

Ожидаемый вывод:

```
research             4b223a6e037339c4
options              7bd2f86c77d10d93
strategy-product     a9044f0adb864066
strategy-comms       cc69de997a2c37e1
verification-plan    7373bfb1f6fc71c4
decisions            906e68a1ff023151
```

История расхождения (не спрятана): в сводке манифеста три хеша
(strategy-comms, verification-plan, decisions) остались от состояния
«конец прогона» — после прогона прошли корректировочные раунды
TASK-hermes-19 и TASK-hermes-20 (описаны в том же манифесте). Расхождение
найдено сверкой `sha256sum` при подготовке этого примера и исправлено в
манифесте с пометкой; гейты на `project/` после обоих раундов — exit 0.

## 6. Стоимость прогона — по строкам, не на слово

`COST.md`, строки с меткой `t18-case` (хук `cost-append` пишет строку на
каждое сообщение ассистента). Дословно, первые строки прогона:

```
| 2026-11-17 | ses_e15bb3c62ffeyBnXuLfk2SQF6q | О4: t18-case-research | step-5-preview | 61271 | 37170 | 0 | 254272 | 0 | 0 | $0.19 |
| 2026-11-17 | ses_e15b7c51cffebQn0gS9aAN43QT | О4: t18-case-options | step-5-preview | 16150 | 8308 | 0 | 226368 | 0 | 0 | $0.06 |
```

В метке `t18-case` лежат ДВА прогона, и складывать их в «один путь»
нельзя (пример такого сложения — ошибка, которую нашла эта сверка):
`t18-case` без префикса `ho-` — демо-путь (22 сессии, $2.67),
`t18-case-ho-` — held-out-путь (23 сессии, $3.00). Плюс раунд доводки
шагов 4–5 после прогона (метка `t20-gate-rev`, 7 сессий, $0.44).

Поставленный демо-результат: **$3.11 за 29 сессий** ($2.67 + $0.44).
Ориентир ТЗ «полный прогон mid-tier ≤$2–5» — выполнен на полном прогоне
($2.67), а не на усечённом. Проверка:

```bash
python3 scripts/cost_report.py                       # итог по контурам
grep -c "О4: t18-case" COST.md                       # 45 строк двух прогонов
grep "О4: t18-case" COST.md | grep -vc "ho-"         # 22 — демо
grep -c "О4: t18-case-ho-" COST.md                   # 23 — held-out
grep -c "t20-gate-rev" COST.md                       # 7 — доводка
```

## 7. Гейты на артефактах — прогнать самому

```bash
python3 scripts/check_sources.py project/brief.md project/research.md \
  project/options.md project/strategy-product.md project/strategy-comms.md \
  project/verification-plan.md project/decisions.md        # exit 0
python3 scripts/check_acceptance.py project/strategy-product.md \
  project/strategy-comms.md project/verification-plan.md \
  project/decisions.md                                      # exit 0
python3 scripts/check_actionability.py project/strategy-product.md \
  project/strategy-comms.md project/verification-plan.md \
  project/decisions.md                                      # exit 0
```

Финальные выводы гейтов сохранены по файлам:
`eval/runs/t18-case/gates/final-*.gate.txt` (18 файлов — sources,
transferability, options, decisions, acceptance, actionability,
complexity, ranges). Проверка: `ls eval/runs/t18-case/gates/`.

## 8. Это не одноразовый результат: held-out задание

Тот же драйвер, тот же прод-конфиг, ДРУГАЯ задача («ДомКниг», рост
сегмента) — свой журнал со своими раундами ревизии:
`eval/runs/t18-case-heldout/manifest.md` (по журналу — 18 сессий
генерации и ревизии + критик-детектор; стоимость прогона — 23 сессии,
$3.00 по меткам `t18-case-ho-` в `COST.md`; первый запуск потерян
дефектом «пустой выход при exit=0» — возобновление зелёное). Проверка:
`grep -c "exit=0" eval/runs/t18-case-heldout/manifest.md`.

## 9. Что нашла эта сверка (и почему это в доказательстве)

Подготовка примера — не украшение, а ещё один проход проверки. Сверка
`sha256sum` и меток `COST.md` нашла две вещи, которые были бы незаметны
при чтении:

1. **Устаревшие хеши в манифесте.** Три хеша в финальной сводке
   (`eval/runs/t18-case/manifest.md`) остались от состояния «конец
   прогона»: после прогона прошли корректировочные раунды TASK-hermes-19
   и TASK-hermes-20. Исправлено в манифесте с пометкой (см. §5).
2. **Ошибку сложения меток.** Заявлять «полный демо-путь $6.11 за 52
   сессии» нельзя: 45 строк метки `t18-case` — это демо (22 сессии,
   $2.67) и held-out (23 сессии, $3.00) вместе. Разделение по префиксу
   `ho-` восстановлено в README и в этом файле; в `COST.md` метки
   различимы, но при беглом чтении складываются — это дефект
   удобства учёта, назван здесь, а не замазанный.

Обе находки — того же класса, что и всё остальное в проекте: заявление
без сверки с записью. Поэтому пример и доказательство сделаны из
записей, а не из пересказа.

## 10. Чего в этом доказательстве нет

- Скриншотов «из головы»: все цитаты — из файлов, перечисленных выше.
- Себестоимости «в среднем по индустрии»: только строки `COST.md` этого
  репозитория.
- Оценок «агент отличный»: оценка критика — внутренний механизм (proxy),
  её находки и баллы даны как есть, включая снижение баллов за
  непроверяемость пакета (находка 6 в `critic4/findings.md`).
