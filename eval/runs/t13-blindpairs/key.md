# Ключ слепых пар (НЕ предъявлять до суждения владельца)

Seed: 20261117; перемешивание A/B — random.Random(seed), детерминировано.
note в парах — нейтральный вопрос; пояснения с именами рук — только здесь.

| Пара | A | B | Вопрос пары (нейтральный) | Состав пары (после суждения) |
|---|---|---|---|---|
| 1 | plain-chat | skill | Полный путь против одного диалога | агент против обычного чата (база шага 3) |
| 2 | critic-loop2 | plain-chat | Полный путь против одного диалога | агент против обычного чата (сильная рука) |
| 3 | council-lite | plain-chat | Полный путь против одного диалога | агент против обычного чата (совет) |
| 4 | curation#0 | plain-chat | Полный путь против одного диалога | агент против обычного чата (свежая курация) |
| 5 | council-lite | skill | Два способа получить набор вариантов (шаг 3) | развилка прод-конфига: база против совета |
| 6 | critic-loop2 | skill | Два способа получить набор вариантов (шаг 3) | развилка прод-конфига: база против ревизии |
| 7 | lean#0 | curation#0 | Два дизайна инструкций для одного шага | развилка навыков: курация против lean (цепочка 0) |
| 8 | curation#1 | lean#1 | Два дизайна инструкций для одного шага | развилка навыков: курация против lean (цепочка 1) |
| 9 | lean#2 | curation#2 | Два дизайна инструкций для одного шага | развилка навыков: курация против lean (цепочка 2) |
| 10 | hybrid#0 | lean#0 | Два дизайна инструкций для одного шага | развилка навыков: lean против гибрида (цепочка 0) |

## Provenance (путь, sha256, байты)

| Рука | Путь | sha256 | Байт |
|---|---|---|---|
| plain-chat | `eval/runs/b11-plainchat/final.md` | 08a36621201c013e | 8607 |
| skill | `eval/runs/ab-options-demo-retention/skill/final.md` | 17f974dfd4c002a8 | 22712 |
| critic-loop2 | `eval/runs/cl2-demo/critic-loop2/final.md` | 7833864102d45b62 | 24369 |
| council-lite | `eval/runs/ab-options-demo-retention/council-lite/final.md` | 9566ffc1527ec8af | 29213 |
| curation#0 | `eval/runs/t12-skills/options/curation/final.md` | fd7fe83dc8e90928 | 14004 |
| curation#1 | `eval/runs/t12-skills/options/curation/final-1.md` | d55914c54f5ded8b | 26245 |
| curation#2 | `eval/runs/t12-skills/options/curation/final-2.md` | 7feca19ecb53277b | 19949 |
| lean#0 | `eval/runs/t12-skills/options/lean/final.md` | e99feb48e0045131 | 11424 |
| lean#1 | `eval/runs/t12-skills/options/lean/final-1.md` | 0ae15f3222ca0c1c | 15118 |
| lean#2 | `eval/runs/t12-skills/options/lean/final-2.md` | bbbb6c9ee0ce3954 | 11056 |
| hybrid#0 | `eval/runs/t12-skills/options/hybrid/final.md` | ede676dc608230a3 | 10569 |
