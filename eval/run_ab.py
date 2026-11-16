#!/usr/bin/env python3
"""run_ab.py — попарный A/B стенд «Стратега» (О4, мультинаправленные замеры).

Протокол: TASK-hermes-4 §3 (BRIEF п.17). Фича × рука × метрика × $/run.
Все руки получают ОДИН замороженный бриф (инлайном) и работают в свежих
сессиях `opencode run`; роли read-only (проверка `git status` после
каждого прогона — в манифест). Учёт $ — через хуки cost-append с меткой
«О4: ab-<прогон>-<рука>-<сессия>» в колонке «Шаг» (STATE.md `## шаг` на время
прогона). Хук обрезает метку до 40 символов, поэтому новые прогоны
запускают с короткими `--out` (cf-heldout, cl2-demo, cl2-heldout), а
атрибуция $ в `score_arms.py` идёт префиксными фрагментами
(`ARM_LABELS_BY_RUN`).

Руки (арms) фичи «Варианты» (шаг 3):
  skill        — текущий навык options (базовая рука продукта);
  lean         — минимальная универсальная инструкция (дизайн навыков b);
  hybrid       — lean + один точечный навык (дизайн навыков c);
  critic-loop  — skill + внутренний критик (изолированный) + одна
                 ревизия по находкам (полное переписывание);
  critic-loop2 — skill + критик + ТОЧЕЧНАЯ ревизия (targeted patch):
                 модель возвращает JSON правок «find → replace», их
                 применяет `scripts/apply_revision.py` с проверками
                 целостности и честным откатом к черновику;
  council-lite — 3 роли (product/devil на step-5-preview, data на
                 step-3.7-flash) по council-design §5 (рычаг O1: 3 роли,
                 один раунд) + синтезатор-сессия (единственный писатель);
  council-full — полный протокол council-design §4, 12 сессий: Phase 1
                 независимая дивергенция 5 линз, Phase 2 кросс-критика
                 (линза видит четыре чужих выхода, свой — нет), Phase 3
                 состязательный проход дьявола (последним, защищён,
                 в синтез дословно), Phase 4 синтез одним писателем.

Руки фичи «Исследование» (шаг 2, дизайн навыков):
  curation     — открыть и применить навык `knowledge/skills/evidence/SKILL.md`
                 (раздел «Шаг 2») + шаблон `templates/research.md`;
  lean         — минимальная универсальная инструкция исследования
                 инлайном, библиотека навыков не открывается;
  hybrid       — lean + единственный навык evidence.
Все три руки получают один дайджест оснований (бриф + все `ev-*.md`
задачи) и выдают research.md с одинаковыми требованиями к выходу.

Балансировка порядка: порядок рук ротируется между задачами (демо —
как задано, held-out — реверс), чтобы порядок не был спутан с эффектом.

Контракт CLI:
    python3 eval/run_ab.py --task demo-retention|heldout-growth-segment
        --feature options|research --arms skill,critic-loop,council-full
        [--out DIR] [--timeout SEC] [--dry-run]

Коды возврата: 0 — все прогоны зелёные; 1 — ошибка использования;
4 — хотя бы один прогон упал (детали в <out>/manifest.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_RUN_FAILED = 4

# Фичи стенда: у фичи свой набор рук (одинаковые имена рук в разных фичах
# — разные промпты, поэтому реестр рук ключуется парой «фича × рука»).
FEATURES = ("options", "research")
DEFAULT_FEATURE = "options"

# Лимит точечных правок critic-loop2: сколько правок из ответа модели
# реально попадает в файл патчей (контракт промпта — не более 15).
MAX_PATCH_EDITS = 15

# Linux ограничивает ОДИН аргумент exec до 128 КБ (MAX_ARG_STRLEN).
# Промпт сессии council-full на held-out (бриф + 5 выходов Phase 1 +
# 5 выходов Phase 2) — 133 КБ: одним argv он не влезает и процесс
# падал с OSError E2BIG (внешне выглядело как «тихое убийство»).
# Поэтому промпт режется по границам UTF-8 на части и передаётся
# несколькими позиционными аргументами `opencode run` (склейка
#message через пробел — проверено).
ARG_LIMIT_BYTES = 120_000


def chunk_prompt(prompt: str, limit_bytes: int = ARG_LIMIT_BYTES) -> list[str]:
    """Промпт → части, каждая ≤ limit_bytes байт и валидный UTF-8.

    Граница реза никогда не рассекает многобайтовый символ (откат до
    lead-byte). Промпт в пределах лимита возвращается как есть.
    """
    data = prompt.encode("utf-8")
    if len(data) <= limit_bytes:
        return [prompt]
    chunks: list[bytes] = []
    start = 0
    while start < len(data):
        end = min(start + limit_bytes, len(data))
        if end < len(data):
            while end > start and (data[end] & 0xC0) == 0x80:
                end -= 1  # откат из середины многобайтового символа
        chunks.append(data[start:end])
        start = end
    return [chunk.decode("utf-8") for chunk in chunks]

TASKS = {
    "demo-retention": {
        "brief": "project/council/run-2026-11-16-01/frozen-brief.md",
        "evidence": "project/evidence",
    },
    "heldout-growth-segment": {
        "brief": "eval/tasks/heldout-growth-segment/artifacts/brief.md",
        "evidence": "eval/tasks/heldout-growth-segment/artifacts/evidence",
    },
}

STEP_PROMPT = """Ты — агент «Стратег» (папка-агент для руководителя продукта), выполняешь
шаг 3 (ВАРИАНТЫ) рабочего процесса. Работай строго по навыку: открой и
примени `knowledge/skills/options/SKILL.md`.

Вход — замороженный бриф задачи (ДАН НИЖЕ ИНЛАЙНОМ, это единственный
источник основания; файлы проекта не открывай, кроме навыка):

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

Требования к выходу:
- Не менее трёх вариантов с РАЗНЫМИ механизмами + «оставить как есть»
  с ценой бездействия (навык options §2–3).
- У каждого варианта: суть / что требует / экономика / сильные
  возражения (сильнейшее первым) / риски.
- Не-факты помечены [гипотеза]/[прогноз]/[допущение]; каждое
  существенное число несёт основание (ev-N / URL) в той же строке.
- Артефакт — на русском.
- Верни готовый markdown артефакта options.md ОТВЕТОМ В ЧАТ. Файлы не
  пиши, ничего не коммить.
"""

REVISION_PROMPT = """Ты — тот же агент «Стратег», дорабатываешь свой черновик шага 3
(ВАРИАНТЫ) по находкам внутреннего критика. Ниже — твой черновик и
находки критика (рубрика — критерии хакатона).

Правила доработки:
- Прими находку, если она по существу (исправь текст); отклони —
  только с явной причиной в блоке «Ответ на находки критика».
- Не «подгоняй» оценки: цель — усилить артефакт, а не понравиться
  критику. Сохрани маркеры [факт]/[гипотеза]/[прогноз]/[допущение].
- Не ослабляй возражения и не увеличивай число вариантов ради
  разнообразия.

=== ЧЕРНОВИК ===
{draft}
=== НАХОДКИ КРИТИКА ===
{findings}
=== КОНЕЦ ===

Верни доработанный markdown артефакта options.md ОТВЕТОМ В ЧАТ. Файлы
не пиши.
"""

PATCH_REVISION_PROMPT = """Ты — тот же агент «Стратег», дорабатываешь свой черновик шага 3
(ВАРИАНТЫ) по находкам внутреннего критика. Это ТОЧЕЧНАЯ правка
(targeted patch), а не переписывание: полный артефакт заново не выдаётся.

Верни ТОЛЬКО JSON-блок (в фи ```json или голым JSON) такого вида:

{{"edits": [{{"find": "<дословный фрагмент черновика, 40–800 символов>",
"replace": "<новый текст>", "finding": "<какую находку закрывает>",
"action": "apply|reject", "reason": "<обязательно при reject>"}}]}}

Правила:
- Не переписывай артефакт целиком: каждая правка — замена одного
  фрагмента (find → replace). Допустимы добавления нового текста.
- find копируется из черновика ДОСЛОВНО (символ в символ): иначе правка
  не применится (0 вхождений — not-found, больше одного — ambiguous).
- Не удаляй целиком секцию варианта («## Вариант …») и секцию
  «оставить как есть».
- Сохрани маркеры [факт]/[гипотеза]/[прогноз]/[допущение].
- Отклонённая находка — action "reject" с явной причиной в reason.
- Не более 15 правок.

=== ЧЕРНОВИК ===
{draft}
=== НАХОДКИ КРИТИКА ===
{findings}
=== КОНЕЦ ===

Верни только JSON-блок ответом в чат. Файлы не пиши.

"""

LEAN_PROMPT = """Ты — агент «Стратег» (папка-агент для руководителя продукта), выполняешь
шаг 3 (ВАРИАНТЫ). Работай по МИНИМАЛЬНОЙ универсальной инструкции ниже
(философия «не перегружено, но работает отлично»): никаких длинных
навыков, только суть.

ИНСТРУКЦИЯ:
1. Дай не менее трёх вариантов с РАЗНЫМИ механизмами воздействия (не
   разным размером бюджета) плюс «оставить как есть» с ценой
   бездействия.
2. У каждого варианта: суть / что требует / экономика / сильнейшее
   возражение (по существу, с основаниями) / риски.
3. Не-факты помечай [гипотеза]/[прогноз]/[допущение]; каждое
   существенное число несёт основание (ev-N / URL) в той же строке.
4. Язык — русский. Верни готовый markdown артефакта options.md
   ОТВЕТОМ В ЧАТ. Файлы не пиши, ничего не коммить.

Вход — замороженный бриф задачи (единственный источник основания):

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===
"""

HYBRID_PROMPT = """Ты — агент «Стратег» (папка-агент для руководителя продукта), выполняешь
шаг 3 (ВАРИАНТЫ). Работай по МИНИМАЛЬНОЙ универсальной инструкции ниже;
для механики карточки варианта открой ОДИН навык —
`knowledge/skills/options/SKILL.md` — и применяй его §2–3 (разные
механизмы, «оставить как есть», сила возражений). Остальные навыки не
открывай.

ИНСТРУКЦИЯ:
1. Не менее трёх вариантов с разными механизмами + «оставить как есть»
   с ценой бездействия.
2. У каждого: суть / что требует / экономика / сильнейшее возражение /
   риски.
3. Не-факты помечай [гипотеза]/[прогноз]/[допущение]; каждое
   существенное число — с основанием (ev-N / URL) в той же строке.
4. Язык — русский. Верни markdown артефакта options.md ОТВЕТОМ В ЧАТ.
   Файлы не пиши, ничего не коммить.

Вход — замороженный бриф задачи (единственный источник основания):

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===
"""

ROLE_PROMPT = """Ты — экспертная линза «{role}» в Консилиуме агента «Стратег» (протокол
 council-design §4 Phase 1, одна фаза — независимая дивергенция).
Других линз ты не видишь и не должен предполагать их позиции.

Твоя линза: {lens}

Вход — замороженный бриф задачи (инлайном):

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

Задача: предложи 2–4 варианта решения с позиции своей линзы. Для
каждого — суть, механизм воздействия, сильнейшее возражение к нему
(по существу, с основаниями из брифа), риски. Не-факты помечай
[гипотеза]/[прогноз]. Каждое существенное число — с основанием
(ev-N / URL) в той же строке. Язык — русский.

Верни ответ markdown-ом В ЧАТ. Файлы не пиши.
"""

SYNTH_PROMPT = """Ты — синтезатор Консилиума агента «Стратег» (единственный писатель
итогового набора вариантов, протокол council-design §4 Phase 4).

Вход — замороженный бриф и выходы трёх линз (product, devil, data),
каждая независима:

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

{roles}

Требования к синтезу:
- Итоговый набор: содержательно разные варианты (разные механизмы) +
  «оставить как есть» с ценой бездействия. Объединяй только с явной
  пометкой provenance (какая линза — источник).
- Сохрани разногласия отдельным разделом (какая линза против чего и
  почему) — несогласие ценнее согласия.
- У каждого варианта: суть / что требует / экономика / сильные
  возражения (сильнейшее первым) / риски. Маркеры [факт]/[гипотеза]/
  [прогноз]/[допущение]. Каждое существенное число — с основанием
  (ev-N / URL) в той же строке. Язык — русский.
- Верни готовый markdown артефакта options.md ОТВЕТОМ В ЧАТ. Файлы не
  пиши.
"""

CROSS_PROMPT = """Ты — та же экспертная линза «{role}» Консилиума агента «Стратег»
(протокол council-design §4 Phase 2 — структурная кросс-критика).

ВАЖНО ПРО ИЗОЛЯЦИЮ: в Phase 1 ты работал независимо и выходов других
линз НЕ видел. Изоляция снята только на этот раунд, и ниже даны выходы
ОСТАЛЬНЫХ ЧЕТЫРЁХ линз — твоего выхода здесь нет намеренно: оценивай
чужие варианты по существу, а не защищай свою позицию Phase 1.

Твоя линза: {lens}

Вход — замороженный бриф задачи (инлайном):

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

=== ВЫХОДЫ ДРУГИХ ЛИНЗ (Phase 1, независимые) ===
{others}
=== КОНЕЦ ВЫХОДОВ ===

Задача: по каждому ЧУЖОМУ варианту из всех четырёх выходов — существенное
возражение с позиции своей линзы: режимы отказа, вторые порядки, что
пропущено, какое основание слабое, какой замер изменил бы решение. Если
возражений нет — напиши «возражений нет» и причину. Не-факты помечай
[гипотеза]/[прогноз]; каждое существенное число — с основанием
(ev-N / URL) в той же строке. Язык — русский.

Верни ответ markdown-ом В ЧАТ. Файлы не пиши.

"""

ADV_PROMPT = """Ты — адвокат дьявола Консилиума агента «Стратег» (протокол
council-design §4 Phase 3 — состязательный проход; роль всегда идёт
последней и защищена). Тебе даны бриф, ВСЕ пять выходов Phase 1
(независимая дивергенция) и ВСЕ возражения Phase 2 (кросс-критика).

Твоя задача: сильнейший случай ПРОТИВ ведущего варианта (того, что
выглядит фаворитом по поддержке линз) И сильнейший случай ЗА наименее
фаворируемый вариант, включая «оставить как есть»: режимы отказа,
вторые порядки, кому нанесён вред, что делает решение предметом
сожаления, какие факты его опровергают.

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

=== ВЫХОДЫ ЛИНЗ PHASE 1 (независимые) ===
{roles}
=== КОНЕЦ ВЫХОДОВ ===

=== ВОЗРАЖЕНИЯ PHASE 2 (кросс-критика) ===
{cross}
=== КОНЕЦ ВОЗРАЖЕНИЙ ===

Требования:
- Возражения адресные и с механизмом; performed disagreement — анти-паттерн.
- Не-факты помечай [гипотеза]/[прогноз]; каждое существенное число —
  с основанием (ev-N / URL) в той же строке.
- Этот текст попадает в итоговый артефакт ДОСЛОВНО, без сокращений и
  пересказа: пиши так, чтобы он был готов к включению как есть.
- Язык — русский. Верни ответ markdown-ом В ЧАТ. Файлы не пиши.

"""

SYNTH_FULL_PROMPT = """Ты — синтезатор Консилиума агента «Стратег» (единственный писатель
итогового набора вариантов, протокол council-design §4 Phase 4).

Вход — замороженный бриф, выходы пяти линз (product, comms, data,
devil, user), возражения кросс-критики Phase 2 и состязательный проход
дьявола Phase 3:

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

{roles}

{cross}

{adversarial}

Требования к синтезу:
- Итоговый набор: содержательно разные варианты (разные механизмы) +
  «оставить как есть» с ценой бездействия. Объединяй только с явной
  пометкой provenance (какая линза — источник).
- Сохрани разногласия отдельным разделом (какая линза против чего и
  почему) — несогласие ценнее согласия.
- Состязательный проход дьявола (Phase 3) включи ДОСЛОВНО: несогласие
  не должно быть сглажено пересказом.
- У каждого варианта: суть / что требует / экономика / сильные
  возражения (сильнейшее первым) / риски. Маркеры [факт]/[гипотеза]/
  [прогноз]/[допущение]. Каждое существенное число — с основанием
  (ev-N / URL) в той же строке. Язык — русский.
- Верни готовый markdown артефакта options.md ОТВЕТОМ В ЧАТ. Файлы не
  пиши.

"""

COUNCIL_FULL_ROLES = {
    "product": (
        "продуктовая экономика: jobs аудитории ↔ стоимость ↔ доход; "
        "что мешает и что усиливает удержание/рост с продуктовой стороны"
    ),
    "comms": (
        "барьеры понимания и выбора аудитории: что мешает аудитории "
        "понять и выбрать, какое сообщение снимает барьер, какую роль "
        "играет каждый канал, соответствие обещания продукту"
    ),
    "data": (
        "данные и доказательства: что измерено в брифе, какие связи "
        "причинны, а какие — ассоциации/артефакты; где пробелы данных"
    ),
    "devil": (
        "адвокат дьявола: ищи сильнейшие возражения против каждого "
        "очевидного варианта, вторые порядки, regrettable-сценарии"
    ),
    "user": (
        "живой опыт пользователя: реальный контекст использования, "
        "стоимость переключения, доверие; что ломается в моменте выбора"
    ),
}

# council-lite (рычаг O1 council-design §5): 3 линзы из полного набора —
# порядок и состав сохранены для обратной совместимости прогонов О4.
ROLES = {role: COUNCIL_FULL_ROLES[role] for role in ("product", "devil", "data")}

ROLE_MODEL = {
    "product": "stepfun/step-5-preview",
    "comms": "stepfun/step-5-preview",
    "devil": "stepfun/step-5-preview",
    "data": "stepfun/step-3.7-flash",
    "user": "stepfun/step-3.7-flash",
}

MODEL = "stepfun/step-5-preview"

RESEARCH_CURATION_PROMPT = """Ты — агент «Стратег» (папка-агент для руководителя продукта), выполняешь
шаг 2 (ИССЛЕДОВАНИЕ) рабочего процесса. Работай строго по навыку: открой
и примени `knowledge/skills/evidence/SKILL.md` (раздел «Шаг 2 —
исследование»); структура выхода — по шаблону `templates/research.md`.

Вход — замороженный бриф задачи (единственный источник постановки):

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

=== ДАЙДЖЕСТ ОСНОВАНИЙ (бриф + записи evidence) ===
{evidence}
=== КОНЕЦ ДАЙДЖЕСТА ===

Требования к выходу:
- Структура research.md по шаблону: решающие вопросы со статусами
  (отвечено / частично / пробел), картина ситуации только с
  основаниями, конфликты парой (источник А против источника Б), не
  усредняй, гипотезы H1..Hn с указанием, что именно их подтвердит
  или опровергнет, именованные пробелы с причинами.
- Не-факты помечай [факт]/[гипотеза]/[прогноз]/[допущение].
- Каждое существенное число несёт основание (ev-N / URL) В ТОЙ ЖЕ
  строке. Числа бери ТОЛЬКО из дайджеста оснований: недопустимо
  додумывать, округлять или «уточнять» цифры.
- Язык — русский. Верни готовый markdown артефакта research.md
  ОТВЕТОМ В ЧАТ. Файлы не пиши, ничего не коммить.

"""

RESEARCH_LEAN_PROMPT = """Ты — агент «Стратег» (папка-агент для руководителя продукта), выполняешь
шаг 2 (ИССЛЕДОВАНИЕ). Работай по МИНИМАЛЬНОЙ универсальной инструкции
ниже (философия «не перегружено, но работает отлично»): никаких длинных
навыков и библиотеки навыков, только суть.

ИНСТРУКЦИЯ:
1. Перечисли решающие вопросы из брифа — на них отвечает исследование;
   каждому дай статус: отвечено / частично / пробел.
2. «Картина ситуации» — только утверждения с основанием: URL, ev-N или
   маркер [гипотеза]/[прогноз]. Без основания — не в картину.
3. Где источники сходятся — вывод устойчив; где конфликт — фиксируй
   оба с областью применимости каждого, не усредняй.
4. Гипотезы о причинах — с пометкой и с указанием, что именно их
   подтвердит или опровергнет.
5. Пробелы — явным списком: «не знаем X, потому что …; пробовали …;
   недоступно …». Пробел — результат шага.

Вход — замороженный бриф задачи:

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

=== ДАЙДЖЕСТ ОСНОВАНИЙ (бриф + записи evidence) ===
{evidence}
=== КОНЕЦ ДАЙДЖЕСТА ===

Требования к выходу:
- Структура research.md: решающие вопросы со статусами, картина
  ситуации только с основаниями, конфликты парой без усреднения,
  гипотезы H1..Hn со способом проверки, именованные пробелы.
- Не-факты помечай [факт]/[гипотеза]/[прогноз]/[допущение].
- Каждое существенное число несёт основание (ev-N / URL) В ТОЙ ЖЕ
  строке. Числа бери ТОЛЬКО из дайджеста оснований: недопустимо
  додумывать, округлять или «уточнять» цифры.
- Язык — русский. Верни готовый markdown артефакта research.md
  ОТВЕТОМ В ЧАТ. Файлы не пиши, ничего не коммить.

"""

RESEARCH_HYBRID_PROMPT = """Ты — агент «Стратег» (папка-агент для руководителя продукта), выполняешь
шаг 2 (ИССЛЕДОВАНИЕ). Работай по МИНИМАЛЬНОЙ универсальной инструкции
ниже; для механики исследования открой ОДИН навык —
`knowledge/skills/evidence/SKILL.md`, раздел «Шаг 2 — исследование» — и
применяй его (решающие вопросы, сопоставление источников, конфликты без
усреднения, пробелы). Остальные навыки не открывай.

ИНСТРУКЦИЯ:
1. Решающие вопросы из брифа — со статусом: отвечено / частично / пробел.
2. Картина ситуации — только с основанием: URL, ev-N или маркер.
3. Конфликт источников — оба с областью применимости, не усредняй.
4. Гипотезы о причинах — с пометкой и способом проверки.
5. Пробелы — явным списком с причинами.

Вход — замороженный бриф задачи:

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

=== ДАЙДЖЕСТ ОСНОВАНИЙ (бриф + записи evidence) ===
{evidence}
=== КОНЕЦ ДАЙДЖЕСТА ===

Требования к выходу:
- Структура research.md по шаблону `templates/research.md`: решающие
  вопросы со статусами, картина ситуации только с основаниями,
  конфликты парой без усреднения, гипотезы H1..Hn со способом проверки,
  именованные пробелы.
- Не-факты помечай [факт]/[гипотеза]/[прогноз]/[допущение].
- Каждое существенное число несёт основание (ev-N / URL) В ТОЙ ЖЕ
  строке. Числа бери ТОЛЬКО из дайджеста оснований: недопустимо
  додумывать, округлять или «уточнять» цифры.
- Язык — русский. Верни готовый markdown артефакта research.md
  ОТВЕТОМ В ЧАТ. Файлы не пиши, ничего не коммить.

"""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_state_step(label: str) -> str | None:
    state = REPO_ROOT / "STATE.md"
    try:
        text = state.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"(##\s*шаг\s*\n\n)([^\n#]*(?:\n(?![#\n])[^\n#]*)*)", text)
    if not match:
        return None
    previous = match.group(2).strip()
    patched = text[: match.start(2)] + label + text[match.end(2) :]
    try:
        state.write_text(patched, encoding="utf-8")
    except OSError:
        return None
    return previous


def restore_state_step(previous: str | None) -> None:
    if previous is None:
        return
    state = REPO_ROOT / "STATE.md"
    try:
        text = state.read_text(encoding="utf-8")
    except OSError:
        return
    match = re.search(r"(##\s*шаг\s*\n\n)([^\n#]*(?:\n(?![#\n])[^\n#]*)*)", text)
    if not match:
        return
    patched = text[: match.start(2)] + previous + text[match.end(2) :]
    try:
        state.write_text(patched, encoding="utf-8")
    except OSError:
        pass


def run_session(prompt: str, out_dir: Path, name: str, model: str, timeout: int) -> tuple[int, str]:
    """Свежая сессия opencode run; выход — в <out_dir>/<name>.out."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.start").write_text(
        datetime.now(timezone.utc).isoformat() + f" model={model}\n", encoding="utf-8"
    )
    # Метка для хука cost-append: «О4: ab-<прогон>-<рука>-<сессия>» —
    # прогон и рука берутся из пути (out_dir = <прогон>/<рука>), чтобы
    # $/run атрибутировался однозначно при нескольких прогонах.
    previous = set_state_step(f"О4: ab-{out_dir.parent.name}-{out_dir.name}-{name}")
    try:
        proc = subprocess.run(
            ["opencode", "run", "--model", model, *chunk_prompt(prompt)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        (out_dir / f"{name}.end").write_text(
            datetime.now(timezone.utc).isoformat() + " TIMEOUT\n", encoding="utf-8"
        )
        return EXIT_RUN_FAILED, ""
    finally:
        restore_state_step(previous)
    (out_dir / f"{name}.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / f"{name}.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / f"{name}.end").write_text(
        datetime.now(timezone.utc).isoformat() + f" exit={proc.returncode}\n",
        encoding="utf-8",
    )
    return proc.returncode, proc.stdout


def build_evidence_bundle(task: dict) -> str:
    """Дайджест оснований шага 2: замороженный бриф + все `ev-*.md` задачи
    (отсортированные, каждая под заголовком «=== ev-NNN ===»).

    Единственный источник чисел для рук фичи «research»: всё, чего нет
    в дайджесте, в артефакт попадает только как [гипотеза]/[прогноз].
    """
    brief = (REPO_ROOT / task["brief"]).read_text(encoding="utf-8-sig", errors="replace")
    parts = ["=== ЗАМОРОЖЕННЫЙ БРИФ ===\n" + brief + "\n=== КОНЕЦ БРИФА ==="]
    evidence_dir = REPO_ROOT / task["evidence"]
    records = sorted(evidence_dir.glob("ev-*.md")) if evidence_dir.is_dir() else []
    if not records:
        print(f"предупреждение: записей evidence нет в {evidence_dir}", file=sys.stderr)
    for path in records:
        match = re.match(r"(ev-\d+)", path.stem)
        header = f"=== {match.group(1) if match else path.stem} ==="
        parts.append(header + "\n" + path.read_text(encoding="utf-8-sig", errors="replace"))
    return "\n\n".join(parts) + "\n"


def parse_patch_json(text: str) -> dict | None:
    """Достаёт JSON правок из ответа модели: фи ```json … ``` или голый
    JSON. Возвращает None, если разобрать не удалось (деградация руки
    фиксируется в отчёте, артефакт не теряется)."""
    fenced = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("edits"), list):
            return data
        if isinstance(data, list):
            return {"edits": data}
    return None


def git_status_clean() -> str:
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    lines = [
        line
        for line in proc.stdout.splitlines()
        if "eval/runs/" not in line and "COST.md" not in line and "STATE.md" not in line
    ]
    return "чисто" if not lines else "; ".join(lines[:5])


def run_arm_skill(feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = "") -> int:
    code, out = run_session(
        STEP_PROMPT.format(brief=brief), arm_dir, "session", MODEL, timeout
    )
    (arm_dir / "final.md").write_text(out, encoding="utf-8")
    return code


def run_arm_lean(feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = "") -> int:
    """Рука «дизайн навыков (b)»: минимальная универсальная инструкция,
    библиотека навыков не открывается (философия lean, BRIEF п.21)."""
    code, out = run_session(
        LEAN_PROMPT.format(brief=brief), arm_dir, "session", MODEL, timeout
    )
    (arm_dir / "final.md").write_text(out, encoding="utf-8")
    return code


def run_arm_hybrid(feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = "") -> int:
    """Рука «дизайн навыков (c)»: lean-инструкция + один точечный навык."""
    code, out = run_session(
        HYBRID_PROMPT.format(brief=brief), arm_dir, "session", MODEL, timeout
    )
    (arm_dir / "final.md").write_text(out, encoding="utf-8")
    return code


def run_arm_critic_loop(
    feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = ""
) -> int:
    code, draft = run_session(
        STEP_PROMPT.format(brief=brief), arm_dir, "session1", MODEL, timeout
    )
    if code != 0:
        return code
    (arm_dir / "draft.md").write_text(draft, encoding="utf-8")
    critic_dir = arm_dir / "critic"
    code = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_critic.py"),
            "--artifact", str(arm_dir / "draft.md"),
            "--rubric", "eval/rubrics/hackathon-criteria.md",
            "--mode", "critic",
            "--out", str(critic_dir),
            "--tag", f"ab-critic-{arm_dir.parent.name}-{arm_dir.name}",
            "--timeout", str(timeout),
        ],
        cwd=REPO_ROOT,
    ).returncode
    if code != 0:
        return code
    findings = (critic_dir / "critic.out").read_text(encoding="utf-8", errors="replace")
    (arm_dir / "findings.md").write_text(findings, encoding="utf-8")
    code, final = run_session(
        REVISION_PROMPT.format(draft=draft, findings=findings),
        arm_dir,
        "session2",
        MODEL,
        timeout,
    )
    if code != 0:
        return code
    (arm_dir / "final.md").write_text(final, encoding="utf-8")
    return 0


def run_arm_critic_loop2(
    feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = ""
) -> int:
    """Рука critic-loop2: та же схема, но ревизия — ТОЧЕЧНАЯ (targeted
    patch). Модель возвращает только JSON правок «find → replace», их
    применяет scripts/apply_revision.py; при BROKEN integrity или нуле
    применённых правок финал = черновик дословно (честная деградация,
    пишется в revision-report.md)."""
    code, draft = run_session(
        STEP_PROMPT.format(brief=brief), arm_dir, "session1", MODEL, timeout
    )
    if code != 0:
        return code
    (arm_dir / "draft.md").write_text(draft, encoding="utf-8")
    critic_dir = arm_dir / "critic"
    code = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_critic.py"),
            "--artifact", str(arm_dir / "draft.md"),
            "--rubric", "eval/rubrics/hackathon-criteria.md",
            "--mode", "critic",
            "--out", str(critic_dir),
            # Короткая метка: хук режет колонку «Шаг» до 40 символов, а
            # score_arms.py матчит строки COST.md фрагментом «<прогон>-critic».
            "--tag", f"{arm_dir.parent.name}-critic",
            "--timeout", str(timeout),
        ],
        cwd=REPO_ROOT,
    ).returncode
    if code != 0:
        return code
    findings = (critic_dir / "critic.out").read_text(encoding="utf-8", errors="replace")
    (arm_dir / "findings.md").write_text(findings, encoding="utf-8")
    code, patch_reply = run_session(
        PATCH_REVISION_PROMPT.format(draft=draft, findings=findings),
        arm_dir,
        "session2",
        MODEL,
        timeout,
    )
    if code != 0:
        return code
    patches = parse_patch_json(patch_reply)
    if patches is None:
        # Ответ модели не разобрали: артефакт не теряем — финалом становится
        # черновик, деградация честно записана в отчёт (не спрятана в код).
        (arm_dir / "final.md").write_text(draft, encoding="utf-8")
        (arm_dir / "revision-report.md").write_text(
            "# Отчёт по точечным правкам (critic-loop2)\n\n"
            f"{fallback_summary_line()}\n\n"
            "JSON правок из ответа модели разобрать не удалось — применять "
            "нечего. Финальный артефакт = черновик дословно (fallback).\n",
            encoding="utf-8",
        )
        return code
    edits = [edit for edit in patches.get("edits", []) if isinstance(edit, dict)]
    patches["edits"] = edits[:MAX_PATCH_EDITS]
    (arm_dir / "patches.json").write_text(
        json.dumps(patches, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    applier = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "apply_revision.py"),
            "--draft", str(arm_dir / "draft.md"),
            "--patches", str(arm_dir / "patches.json"),
            "--out", str(arm_dir / "final.md"),
            "--report", str(arm_dir / "revision-report.md"),
        ],
        cwd=REPO_ROOT,
    )
    # Код руки = код сессий; ошибка файлов апдейтера (exit 2) — реальный
    # сбой прогона, её не глотаем.
    return code or applier.returncode


def run_arm_council_lite(
    feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = ""
) -> int:
    role_outputs: dict[str, str] = {}
    for role, lens in ROLES.items():
        code, out = run_session(
            ROLE_PROMPT.format(role=role, lens=lens, brief=brief),
            arm_dir,
            f"role-{role}",
            ROLE_MODEL[role],
            timeout,
        )
        if code != 0:
            return code
        role_outputs[role] = out
    roles_block = "\n\n".join(
        f"=== ЛИНЗА {role.upper()} ===\n{text}" for role, text in role_outputs.items()
    )
    code, final = run_session(
        SYNTH_PROMPT.format(brief=brief, roles=roles_block),
        arm_dir,
        "synthesizer",
        MODEL,
        timeout,
    )
    if code != 0:
        return code
    (arm_dir / "final.md").write_text(final, encoding="utf-8")
    return 0


def run_arm_council_full(
    feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = ""
) -> int:
    """Рука council-full: полный протокол council-design §4 (12 сессий).

    Phase 1 — независимая дивергенция 5 линз (без кросс-чтения);
    Phase 2 — кросс-критика: линза видит бриф + ЧУЖИЕ четыре выхода
    (свой исключён — правило изоляции в промпте);
    Phase 3 — состязательный проход дьявола (последним, защищён):
    случай против ведущего варианта и за наименее фаворируемый, включая
    «оставить как есть»; уходит синтезатору дословно;
    Phase 4 — синтез одним писателем (единственный, кто пишет финал).
    """
    phase1: dict[str, str] = {}
    for role, lens in COUNCIL_FULL_ROLES.items():
        code, out = run_session(
            ROLE_PROMPT.format(role=role, lens=lens, brief=brief),
            arm_dir,
            f"role-{role}",
            ROLE_MODEL[role],
            timeout,
        )
        if code != 0:
            return code
        phase1[role] = out
    phase2: dict[str, str] = {}
    for role, lens in COUNCIL_FULL_ROLES.items():
        others = "\n\n".join(
            f"=== ЛИНЗА {other.upper()} ===\n{text}"
            for other, text in phase1.items()
            if other != role
        )
        code, out = run_session(
            CROSS_PROMPT.format(role=role, lens=lens, brief=brief, others=others),
            arm_dir,
            f"cross-{role}",
            ROLE_MODEL[role],
            timeout,
        )
        if code != 0:
            return code
        phase2[role] = out
    roles_block = "\n\n".join(
        f"=== ЛИНЗА {role.upper()} (Phase 1) ===\n{text}" for role, text in phase1.items()
    )
    cross_block = "\n\n".join(
        f"=== ВОЗРАЖЕНИЯ ЛИНЗЫ {role.upper()} (Phase 2) ===\n{text}"
        for role, text in phase2.items()
    )
    code, adversarial = run_session(
        ADV_PROMPT.format(brief=brief, roles=roles_block, cross=cross_block),
        arm_dir,
        "adversarial",
        ROLE_MODEL["devil"],
        timeout,
    )
    if code != 0:
        return code
    code, final = run_session(
        SYNTH_FULL_PROMPT.format(
            brief=brief, roles=roles_block, cross=cross_block, adversarial=adversarial
        ),
        arm_dir,
        "synthesizer",
        MODEL,
        timeout,
    )
    if code != 0:
        return code
    (arm_dir / "final.md").write_text(final, encoding="utf-8")
    return 0


def run_arm_research_curation(
    feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = ""
) -> int:
    """Рука исследования «курация»: навык evidence (шаг 2) + шаблон
    research.md открываются и применяются."""
    code, out = run_session(
        RESEARCH_CURATION_PROMPT.format(brief=brief, evidence=evidence),
        arm_dir,
        "session",
        MODEL,
        timeout,
    )
    (arm_dir / "final.md").write_text(out, encoding="utf-8")
    return code


def run_arm_research_lean(
    feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = ""
) -> int:
    """Рука исследования «lean»: минимальная инструкция инлайном,
    библиотека навыков не открывается."""
    code, out = run_session(
        RESEARCH_LEAN_PROMPT.format(brief=brief, evidence=evidence),
        arm_dir,
        "session",
        MODEL,
        timeout,
    )
    (arm_dir / "final.md").write_text(out, encoding="utf-8")
    return code


def run_arm_research_hybrid(
    feature: str, brief: str, arm_dir: Path, timeout: int, evidence: str = ""
) -> int:
    """Рука исследования «hybrid»: lean-инструкция + один навык evidence."""
    code, out = run_session(
        RESEARCH_HYBRID_PROMPT.format(brief=brief, evidence=evidence),
        arm_dir,
        "session",
        MODEL,
        timeout,
    )
    (arm_dir / "final.md").write_text(out, encoding="utf-8")
    return code


def fallback_summary_line() -> str:
    """Строка итога для отчёта деградации, когда правки не разобраны:
    финал = черновик дословно, поэтому счётчики нулевые, целостность
    не нарушена (нечего было применять), размер равен черновику."""
    return (
        "applied=0 not_found=0 ambiguous=0 rejected=0 fallback=yes "
        "integrity=ok size_ratio=1.00"
    )


class ArmRegistry(dict):
    """Реестр рук стенда: ключ — пара «(фича, рука)».

    Голое имя руки разрешается в руку фичи по умолчанию («options») —
    это эквивалентная диспетчеризация для совместимости со старыми
    вызовами (`ARMS["skill"]`). Одинаковые имена рук в разных фичах
    (lean/hybrid) — разные функции с разными промптами.
    """

    @staticmethod
    def _key(key):
        return key if isinstance(key, tuple) else (DEFAULT_FEATURE, key)

    def __contains__(self, key) -> bool:
        return dict.__contains__(self, self._key(key))

    def __getitem__(self, key):
        return dict.__getitem__(self, self._key(key))

    def get(self, key, default=None):
        return dict.get(self, self._key(key), default)

    def arms_of(self, feature: str) -> list[str]:
        """Имена рук фичи (для сообщения об ошибке использования)."""
        return sorted(arm for feat, arm in self if feat == feature)


ARMS = ArmRegistry(
    {
        ("options", "skill"): run_arm_skill,
        ("options", "lean"): run_arm_lean,
        ("options", "hybrid"): run_arm_hybrid,
        ("options", "critic-loop"): run_arm_critic_loop,
        ("options", "critic-loop2"): run_arm_critic_loop2,
        ("options", "council-lite"): run_arm_council_lite,
        ("options", "council-full"): run_arm_council_full,
        ("research", "curation"): run_arm_research_curation,
        ("research", "lean"): run_arm_research_lean,
        ("research", "hybrid"): run_arm_research_hybrid,
    }
)

# Число сессий на руку (для манифеста и плана $): council-full = 5 линз
# (Phase 1) + 5 кросс-критик (Phase 2) + дьявол (Phase 3) + синтез.
SESSIONS = {
    ("options", "skill"): 1,
    ("options", "lean"): 1,
    ("options", "hybrid"): 1,
    ("options", "critic-loop"): 3,  # черновик + критик + ревизия
    ("options", "critic-loop2"): 3,  # черновик + критик + точечная ревизия
    ("options", "council-lite"): 4,  # 3 роли + синтез
    ("options", "council-full"): 12,  # 5 + 5 + 1 + 1
    ("research", "curation"): 1,
    ("research", "lean"): 1,
    ("research", "hybrid"): 1,
}


def sessions_for(feature: str, arm: str) -> int:
    return SESSIONS.get((feature, arm), 1)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_ab.py")
    parser.add_argument("--task", required=True, choices=sorted(TASKS))
    parser.add_argument("--feature", required=True, help="например: options")
    parser.add_argument("--arms", required=True, help="список рук через запятую")
    parser.add_argument("--out", default=None)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="реверс порядка рук (балансировка между задачами)",
    )
    args = parser.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if (args.feature, a) not in ARMS]
    if unknown:
        print(
            f"неизвестные руки для фичи {args.feature}: {unknown}; "
            f"доступно: " + "; ".join(f"{f}: {','.join(ARMS.arms_of(f))}" for f in FEATURES),
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args.reverse:
        arms = list(reversed(arms))

    task = TASKS[args.task]
    brief_path = REPO_ROOT / task["brief"]
    if not brief_path.is_file():
        print(f"бриф не найден: {brief_path}", file=sys.stderr)
        return EXIT_USAGE
    brief = brief_path.read_text(encoding="utf-8-sig", errors="replace")
    brief_hash = sha256_file(brief_path)
    brief_bytes = brief_path.stat().st_size
    # Дайджест оснований нужен только рукам исследования (шаг 2); для
    # фичи options он не строится — поведение прежних прогонов не меняется.
    evidence = build_evidence_bundle(task) if args.feature == "research" else ""

    out_dir = Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / f"ab-{args.feature}-{args.task}"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = [
        f"# A/B прогон — фича {args.feature}, задача {args.task} (О4)",
        "",
        f"Старт (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Бриф: `{task['brief']}` (sha256 `{brief_hash[:16]}…`, {brief_bytes} Б)",
        f"Порядок рук: {' → '.join(arms)}"
        + (" (реверс — балансировка)" if args.reverse else ""),
        "",
        "| Рука | Сессии | git status после | Итог |",
        "|---|---|---|---|",
    ]

    failures = 0
    for arm in arms:
        arm_dir = out_dir / arm
        arm_dir.mkdir(parents=True, exist_ok=True)
        if args.dry_run:
            print(f"[dry-run] {arm} -> {arm_dir}")
            continue
        sessions = sessions_for(args.feature, arm)
        code = ARMS[(args.feature, arm)](args.feature, brief, arm_dir, args.timeout, evidence)
        failures += 1 if code != 0 else 0
        manifest.append(
            f"| {arm} | {sessions} | {git_status_clean()} "
            f"| {'OK' if code == 0 else 'FAIL exit=' + str(code)} |"
        )
        (out_dir / "manifest.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
        print(f"arm {arm}: exit={code}")

    if args.dry_run:
        return EXIT_OK
    manifest.append("")
    manifest.append(f"Финиш (UTC): {datetime.now(timezone.utc).isoformat()}")
    manifest.append(f"Провалов: {failures}")
    (out_dir / "manifest.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"готово, провалов: {failures}, манифест: {out_dir / 'manifest.md'}")
    return EXIT_RUN_FAILED if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
