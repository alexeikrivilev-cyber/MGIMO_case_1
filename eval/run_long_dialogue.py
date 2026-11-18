#!/usr/bin/env python3
"""run_long_dialogue.py — предрегистрированный эксперимент TASK-hermes-23 / TASK-hermes-26.

Руки на замороженных артефактах демо `demo-retention`:

    A (TASK-hermes-23) / A2 (TASK-hermes-26) — одна длинная сессия: сид
        (рамка + все артефакты инлайном), затем повороты РП в той же
        сессии (`opencode run -s <id>`); 12 поворотов в §33, 36 — в §34;
    B (§33 только) — продуктовый паттерн: каждый поворот — свежая сессия,
        сид = `STATE.md` (dev) или закоммиченной копии состояния из журнала
        прогона (свежий клон) + релевантный артефакт инлайном;
    C (§33) / C2 (§34) — контроль: каждый поворот — свежая сессия с
        артефактом инлайном, без состояния и без истории.

Повороты, метрики M1–M5, M6, правило вердикта и состав сида заморожены в
`eval/runs/t23-longdialogue/PREREGISTRATION.md` (§33, коммит `28e3688`) и
`eval/runs/t26-longdialogue36/PREREGISTRATION.md` (§34, коммит `8df913a`)
ДО прогонов; этот драйвер исполняет их механически и не содержит
продуктовых решений. Повороты 1–12 — дословно из §33 (репликация);
повороты 13–36 — состав §34.1 (метки kinds — в `TURN_KINDS`).

Промпт передаётся через STDIN, а не argv: сид руки A ≈250 КБ, а Linux
ограничивает один argv-аргумент 128 КБ (MAX_ARG_STRLEN → OSError E2BIG,
прецедент «тихого убийства» раннера council-full, `eval/arg_chunk.py`).
Склейка message через пробел при нескольких argv-аргументах меняла бы
байты промпта — stdin передаёт их дословно.

Контракт CLI:
    python3 eval/run_long_dialogue.py --hand A [--turns 1-36] [--timeout SEC]
        [--dry-run] [--out DIR]

Без `--turns` выполняются ВСЕ повороты из `TURNS` (36 в §34). `--turns`
принимает диапазон («13-36»), список («1,3,5») и одиночный номер («12») —
§33 воспроизводится как `--turns 1-12`.

Коды возврата: 0 — все запрошенные повороты выполнены (включая помеченные
FAILED по порогу годности и останов по лимиту контекста — и то, и другое
результат §34.2, не сбой драйвера); 3 — нет ключа; 4 — прогон упал
(исключение без ответа).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

import run_label  # noqa: E402  (метка прогона — отдельный файл, STATE.md не трогаем)

EXIT_OK = 0
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

MODEL = "stepfun/step-5-preview"
RUNS_ROOT = REPO_ROOT / "eval" / "runs" / "t23-longdialogue"
DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

# Цена step-5-preview (§1.8 прайс-документа), $ за 1M токенов.
PRICE = {"input": 1.0, "cache_read": 0.1, "output": 2.7}

# Порог годности поворота (предрегистрация §5): непустой ответ ≥300 символов.
MIN_ANSWER_CHARS = 300
MAX_ATTEMPTS = 2  # первый провал — один повтор тем же промптом (§26.4)

# --- Повороты -----------------------------------------------------------------
# Повороты 1–12 — ДОСЛОВНО из TASK-hermes-23.md (§33, репликация; регресс-
# тест сверяет их с предрегистрацией байт-в-байт — не менять).
# Повороты 13–36 — состав §34.1 (TASK-hermes-26): memory-пробы (15, 20, 26,
# 32, 35), ловушки неверной посылки (14, 17, 23, 33), grounding в артефактах
# (13, 16, 19, 21, 24, 28, 30), опровержение (27), факт/гипотеза (25),
# собственные слабые места (34), повтор итогового вопроса §33 (36).
# Оставшиеся 4 поворота (18, 22, 29, 31) §34.1 не Named — естественное
# продолжение диалога РП (план, цена, коммуникация, критерии остановки);
# состав назван здесь явно, чтобы не выглядел «додуманным под результат».
# Требование §34.1 к вопросам: такие, какие реально задаёт РП в длинной
# сессии, и БЕЗ подсказки ответа (memory-проба «напомни метрику» — ок;
# «ты помнишь метрику 21%?» — нельзя; регресс-тест это проверяет).

TURNS: dict[int, str] = {
    1: "Почему удержание падает? Коротко, три причины.",
    2: "Какой вариант вы выбрали и почему не третий?",
    3: "Какая у нас метрика успеха и её baseline?",
    4: "А если бюджет на удержание равен нулю — что меняется?",
    5: "Пересчитай экономику выбранного варианта при оттоке 30% вместо 21%.",
    6: "Напомни, какую метрику мы измеряем и от какого baseline?",
    7: "Что мы НЕ знаем и какие пробелы названы?",
    8: "Сократи план до одной инициативы — что оставишь?",
    9: "Почему в коммуникационной стратегии именно этот канал?",
    10: "Дай три возражения против собственного решения.",
    11: "Метрика успеха и baseline?",
    12: "Итог: что делаем в первую очередь и как поймём, что сработало?",
    # --- 13–36: новый материал TASK-hermes-26 (§34.1) ---
    13: "Вернёмся к цифрам когорт: сколько подписчиков сохраняет когорта при докризисном уровне удержания и сколько при текущем baseline?",
    14: "Раз бюджет на удержание мы оценили в 5 млн, как делим его между инициативами?",
    15: "Напомни, какую метрику успеха мы взяли и от какого baseline?",
    16: "Какой отток у абонентов на month-to-month в аналоге?",
    17: "Baseline удержания у нас 25% — от него и считаем эффект пилота?",
    18: "С чего начинаем первую инициативу и что нужно от команды на первой неделе?",
    19: "Чему равен AUC модели риска на аналоге и что он нам даёт?",
    20: "Мы не передумали по метрикам? Напомни, что измеряем и от какой точки отсчёта.",
    21: "Какая доля новичков попадает на month-to-month?",
    22: "Сколько подписчиков стоит нам бездействие?",
    23: "Окно пилота — 30 дней, верно? Столько хватит для замера эффекта?",
    24: "Какой отток в первый месяц у новичков на аналоге?",
    25: "Раздели: что в нашем плане — факт с основанием, а что гипотеза или прогноз?",
    26: "Сверимся: метрика успеха и baseline те же, что в начале диалога?",
    27: "По всей базе отток со стриминг-аддонами около 30% против 33% без них — разница мелкая, значит аддоны не защищают? Опровергни или подтверди нашими цифрами.",
    28: "Какой эффект таргетинга называют на аналоге — в п.п. оттока и в подписчиках?",
    29: "Как объяснить руководству, почему эффект увидим не сразу, а в горизонте квартала?",
    30: "Какой порог приёмки для локальной модели скоринга?",
    31: "По каким признакам пилот останавливают, а не продолжают?",
    32: "Напомни ещё раз: метрика успеха и её baseline?",
    33: "Почему мы отказались от «Риск-таргетинга» — слишком дорого?",
    34: "Назови три самых слабых места нашего решения — где мы вероятнее всего ошибаемся.",
    35: "И последняя сверка: метрика успеха и baseline?",
    36: "Итог: что делаем в первую очередь и как поймём, что сработало?",
}

# Метки классов поворотов §34.1 (документация состава + предмет теста).
TURN_KINDS: dict[int, str] = {
    **{t: "репликация §33" for t in range(1, 13)},
    13: "grounding в артефактах",
    14: "ловушка неверной посылки",
    15: "memory-проба",
    16: "grounding в артефактах",
    17: "ловушка неверной посылки",
    18: "план первой недели",
    19: "grounding в артефактах",
    20: "memory-проба",
    21: "grounding в артефактах",
    22: "цена бездействия",
    23: "ловушка неверной посылки",
    24: "grounding в артефактах",
    25: "факт / гипотеза",
    26: "memory-проба",
    27: "опровержение",
    28: "grounding в артефактах",
    29: "коммуникация руководству",
    30: "grounding в артефактах",
    31: "критерии остановки",
    32: "memory-проба",
    33: "ловушка неверной посылки",
    34: "собственные слабые места",
    35: "memory-проба",
    36: "повтор итогового вопроса §33",
}

# Повороты, названные в §34.1 по классам (тест сверяет состав с ними).
MEMORY_PROBE_TURNS: tuple[int, ...] = (15, 20, 26, 32, 35)
TRAP_TURNS: tuple[int, ...] = (14, 17, 23, 33)
GROUNDING_TURNS: tuple[int, ...] = (13, 16, 19, 21, 24, 28, 30)
REPEAT_FINAL_TURN = 36

# --- Состав сида (предрегистрация §3) ---------------------------------------

# Рука A: рамка + все артефакты стратегии + записи доказательств.
# decisions.md (шаг 5) в сид не входит — решение зафиксировано в
# предрегистрации §3 до прогонов.
A_COMPONENTS: list[tuple[str, str]] = [
    ("РАМКА ЗАДАЧИ", "project/brief.md"),
    ("АРТЕФАКТ — ИССЛЕДОВАНИЕ (шаг 2)", "project/research.md"),
    ("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md"),
    ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
    ("АРТЕФАКТ — КОММУНИКАЦИОННАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-comms.md"),
    ("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
    ("ДОКАЗАТЕЛЬСТВО — бенчмарки Mixpanel", "project/evidence/ev-001-mixpanel-benchmarks.md"),
    ("ДОКАЗАТЕЛЬСТВО — датасет IBM Telco Churn", "project/evidence/ev-002-telco-dataset-stats.md"),
    ("ДОКАЗАТЕЛЬСТВО — драйверы оттока (arXiv)", "project/evidence/ev-003-arxiv-churn-drivers.md"),
]

# Руки B и C: релевантный артефакт поворота (одинаков, чтобы руки различались
# только мостом состояния).
TURN_ARTIFACTS: dict[int, list[tuple[str, str]]] = {
    1: [("АРТЕФАКТ — ИССЛЕДОВАНИЕ (шаг 2)", "project/research.md"),
        ("ДОКАЗАТЕЛЬСТВО — датасет IBM Telco Churn", "project/evidence/ev-002-telco-dataset-stats.md")],
    2: [("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md")],
    3: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
        ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    4: [("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md"),
        ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    5: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
        ("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md")],
    6: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
        ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    7: [("АРТЕФАКТ — ИССЛЕДОВАНИЕ (шаг 2)", "project/research.md")],
    8: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    9: [("АРТЕФАКТ — КОММУНИКАЦИОННАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-comms.md")],
    10: [("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    11: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    12: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
         ("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md")],
    # --- 13–36 (TASK-hermes-26): релевантный артефакт поворота для руки C2 ---
    13: [("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md")],
    14: [("РАМКА ЗАДАЧИ", "project/brief.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    15: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    16: [("ДОКАЗАТЕЛЬСТВО — датасет IBM Telco Churn", "project/evidence/ev-002-telco-dataset-stats.md")],
    17: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    18: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    19: [("ДОКАЗАТЕЛЬСТВО — драйверы оттока (arXiv)", "project/evidence/ev-003-arxiv-churn-drivers.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    20: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    21: [("ДОКАЗАТЕЛЬСТВО — датасет IBM Telco Churn", "project/evidence/ev-002-telco-dataset-stats.md")],
    22: [("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md")],
    23: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
         ("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md")],
    24: [("ДОКАЗАТЕЛЬСТВО — датасет IBM Telco Churn", "project/evidence/ev-002-telco-dataset-stats.md")],
    25: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
         ("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md")],
    26: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    27: [("ДОКАЗАТЕЛЬСТВО — датасет IBM Telco Churn", "project/evidence/ev-002-telco-dataset-stats.md"),
         ("АРТЕФАКТ — ИССЛЕДОВАНИЕ (шаг 2)", "project/research.md")],
    28: [("ДОКАЗАТЕЛЬСТВО — драйверы оттока (arXiv)", "project/evidence/ev-003-arxiv-churn-drivers.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    29: [("АРТЕФАКТ — КОММУНИКАЦИОННАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-comms.md")],
    30: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
         ("АРТЕФАКТ — КОММУНИКАЦИОННАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-comms.md")],
    31: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md")],
    32: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    33: [("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    34: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
         ("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md")],
    35: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    36: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
         ("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md")],
}

STATE_PATH = REPO_ROOT / "STATE.md"
TEMPLATE_PATH = "eval/runs/t23-longdialogue/prompt-template.md"
# Закоммиченная копия STATE.md, которая лежала в сиде руки B прогона
# TASK-hermes-23 (TASK-hermes-25): STATE.md — файл разработки вне git,
# поэтому в свежем клоне сид руки B воспроизводится по этой копии.
STATE_AS_USED_PATH = (
    REPO_ROOT / "eval" / "runs" / "t23-longdialogue" / "B" / "state-as-used.md"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_turns(spec: str) -> list[int]:
    """«1-12» / «1,3,5» / «7» → список номеров поворотов."""
    turns: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, _, hi = chunk.partition("-")
            turns.extend(range(int(lo), int(hi) + 1))
        else:
            turns.append(int(chunk))
    unknown = [t for t in turns if t not in TURNS]
    if unknown:
        raise SystemExit(f"неизвестные номера поворотов: {unknown}")
    return sorted(set(turns))


# --- Сид ---------------------------------------------------------------------


def read_component(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def state_from_committed_copy(path: Path) -> str:
    """Состояние задачи из закоммиченной копии `B/state-as-used.md`.

    Копия несёт шапку (`sha256:` + `скопирован:`) и разделитель `---`;
    состояние — всё после разделителя. Sha256 из шапки сверяется с
    извлечённым телом: сдвиг на перевод строки (или правка копии)
    обязан быть ошибкой, а не тихой порчей сида.
    """
    copy = path.read_text(encoding="utf-8")
    head, sep, body = copy.partition("\n---\n\n")
    if not sep:
        raise FileNotFoundError(f"в копии {path} не найдён разделитель состояния после шапки")
    declared = re.search(r"^sha256: `([0-9a-f]{64})`", head, re.MULTILINE)
    if not declared:
        raise ValueError(f"в шапке копии {path} нет строки sha256")
    if sha256_text(body) != declared.group(1):
        raise ValueError(
            f"состояние из {path} не сходится с sha256 шапки — сид руки B был бы испорчен"
        )
    return body


def state_text_for_seed() -> str:
    """Текст STATE.md для сида руки B.

    Dev-окружение: живой `STATE.md` — поведение не меняется. Свежий
    клон: файла разработки нет (политика «артефакты работы не в git»),
    поэтому берём закоммиченную копию `eval/runs/t23-longdialogue/B/
    state-as-used.md` — ровно те байты, что лежали в сиде прогона
    (TASK-hermes-25). Обратный фолбэк (клон → STATE.md) не делается:
    в клоне живого состояния по определению нет.
    """
    if STATE_PATH.is_file():
        return STATE_PATH.read_text(encoding="utf-8")
    return state_from_committed_copy(STATE_AS_USED_PATH)


def build_seed(arm: str, turn: int) -> tuple[str, list[dict[str, str]]]:
    """Собрать полный промпт поворота. Возвращает (текст, компоненты с sha256)."""
    template = read_component(TEMPLATE_PATH)
    parts: list[str] = [template.strip(), ""]
    components: list[dict[str, str]] = [
        {"role": "шаблон промпта", "path": TEMPLATE_PATH, "sha256": sha256_text(template)}
    ]

    if arm == "A":
        blocks = A_COMPONENTS
    else:
        blocks = list(TURN_ARTIFACTS[turn])

    parts.append("----- НАЧАЛО ВХОДНЫХ ДАННЫХ -----")
    parts.append("")
    index = 1
    if arm == "B":
        state_text = state_text_for_seed()
        parts.append(f"[{index}] СОСТОЯНИЕ ЗАДАЧИ — файл STATE.md (resume-карта, дословно)")
        parts.append("")
        parts.append(state_text.strip())
        parts.append("")
        components.append(
            {"role": "состояние задачи", "path": "STATE.md", "sha256": sha256_text(state_text)}
        )
        index += 1
    for title, rel in blocks:
        text = read_component(rel)
        parts.append(f"[{index}] {title} — файл {rel}")
        parts.append("")
        parts.append(text.strip())
        parts.append("")
        components.append({"role": title, "path": rel, "sha256": sha256_text(text)})
        index += 1
    parts.append("----- КОНЕЦ ВХОДНЫХ ДАННЫХ -----")
    parts.append("")
    parts.append(TURNS[turn])
    return "\n".join(parts), components


def write_prompt_record(arm_dir: Path, arm: str, turn: int, prompt: str,
                        components: list[dict[str, str]], continuing: bool = False,
                        total_turns: int = 36) -> None:
    """Журнальная запись промпта.

    Рука A: полный сид хранится один раз в `A/seed.md`, повороты 2..N —
    голый текст вопроса в той же сессии, поэтому в записи поворота лежит
    ссылка на сид (иначе 200+ КБ дублировались бы N раз).
    Руки B и C: сид собирается из шаблона + (STATE.md для B) + артефактов;
    компоненты перечислены с sha256, полный промпт восстановим по ним
    байт-в-байт (sha256 полного промпта — в записи).
    """
    lines = [
        f"# Рука {arm}, поворот {turn} — промпт сессии",
        "",
        f"## Вопрос РП (дословно)",
        "",
        TURNS[turn],
        "",
        f"## Компоненты сида (путь — sha256)",
        "",
    ]
    lines += [f"- `{c['path']}` ({c['role']}) — `{c['sha256']}`" for c in components]
    lines += ["", "## Сборка", ""]
    if continuing:
        lines += [
            "Поворот в ОДНОЙ сессии руки A: промпт — голый текст вопроса РП "
            f"({len(prompt)} символов), сид уже в истории сессии.",
            "Полный сид — `seed.md` (sha256 — в `seed-manifest.json`).",
        ]
    elif arm == "A":
        lines += [
            "Полный промпт = `seed.md` (sha256 — в `seed-manifest.json`) + вопрос РП.",
            f"Повороты 2–{total_turns} отправлялись в ту же сессию голым текстом вопроса.",
        ]
    else:
        lines += [
            "Полный промпт = компоненты в порядке списка (шаблон, затем "
            + ("`STATE.md` (копия — `B/state-as-used.md`), затем " if arm == "B" else "")
            + "артефакты) + вопрос РП.",
        ]
    lines += ["", f"sha256 полного промпта: `{sha256_text(prompt)}`", ""]
    (arm_dir / f"turn-{turn:02d}.prompt.md").write_text("\n".join(lines), encoding="utf-8")


# --- OpenCode ----------------------------------------------------------------


def run_opencode(prompt: str, session_id: str | None, timeout: int) -> dict:
    """Один запуск `opencode run` (промпт — через stdin)."""
    cmd = ["opencode", "run", "--model", MODEL, "--format", "json"]
    if session_id:
        cmd += ["-s", session_id]
    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    finished = datetime.now(timezone.utc)
    events = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    sid = next((e.get("sessionID") for e in events if e.get("sessionID")), None)
    text_parts = [
        e["part"]["text"]
        for e in events
        if e.get("type") == "text" and isinstance(e.get("part"), dict) and "text" in e["part"]
    ]
    return {
        "session_id": sid,
        "text": "\n".join(text_parts),
        "exit_code": proc.returncode,
        "stderr_tail": proc.stderr[-2000:],
        "events": len(events),
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "elapsed_sec": round((finished - started).total_seconds(), 1),
    }


def session_metrics(session_id: str | None) -> dict:
    """Токены последнего ассистентского сообщения + тул-вызовы (БД OpenCode).

    `context_tokens` — размер контекста на повороте: input (cache-miss) +
    cache-read последнего ассистентского сообщения. Это же данные о
    пределе длины (§34.2): по ним виден рост контекста руки A и виден
    удар в лимит, если он случится.
    """
    empty = {
        "input": None, "output": None, "reasoning": None, "cache_read": None,
        "cost_usd_provider": None, "cost_usd_formula": None, "tool_calls": None,
        "patch_parts": None, "assistant_messages": None, "context_tokens": None,
    }
    if not session_id or not DB_PATH.is_file():
        return empty
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        messages = [
            json.loads(data)
            for (data,) in cur.execute(
                "select data from message where session_id=? order by time_created", (session_id,)
            )
        ]
        tool_calls = 0
        patch_parts = 0
        for (data,) in cur.execute("select data from part where session_id=?", (session_id,)):
            part = json.loads(data)
            if part.get("type") == "tool":
                tool_calls += 1
            elif part.get("type") == "patch":
                patch_parts += 1
    finally:
        con.close()
    assistants = [d for d in messages if d.get("role") == "assistant" and d.get("tokens")]
    if not assistants:
        return {**empty, "tool_calls": tool_calls, "patch_parts": patch_parts,
                "assistant_messages": len(assistants)}
    last = assistants[-1]
    tokens = last.get("tokens") or {}
    cache = tokens.get("cache") or {}
    cost = last.get("cost")
    output_tokens = tokens.get("output") or 0
    estimate = (
        (tokens.get("input") or 0) * PRICE["input"] / 1e6
        + (cache.get("read") or 0) * PRICE["cache_read"] / 1e6
        + output_tokens * PRICE["output"] / 1e6
    )
    input_tokens = tokens.get("input")
    cache_read = cache.get("read")
    context_tokens = (
        input_tokens + cache_read
        if isinstance(input_tokens, int) and isinstance(cache_read, int)
        else None
    )
    return {
        "input": input_tokens,
        "output": output_tokens,
        "reasoning": tokens.get("reasoning"),
        "cache_read": cache_read,
        "cost_usd_provider": round(cost, 6) if isinstance(cost, (int, float)) else None,
        "cost_usd_formula": round(estimate, 6),
        "tool_calls": tool_calls,
        "patch_parts": patch_parts,
        "assistant_messages": len(assistants),
        "context_tokens": context_tokens,
    }


# --- Предел контекста (§34.2) -------------------------------------------------

# Признаки отказа API из-за переполнения контекста. Порог делается широким
# НАМЕРЕННО: лучше остановиться с записанной причиной на ложном срабатывании
# (это данные), чем продолжать мерить другую архитектуру после того, как
# запросы начали отклоняться.
CONTEXT_LIMIT_PATTERNS: tuple[str, ...] = (
    "context length",
    "context_length",
    "maximum context",
    "context window",
    "context overflow",
    "too many tokens",
    "reduce the length",
    "payload too large",
    "http 413",
    "status 413",
    "error 413",
)


def detect_context_limit(*texts: str) -> str | None:
    """Первое совпадение признака лимита контекста или None.

    Ищем по stderr и тексту ответа: провайдеры формулируют отказ по-разному
    («context length exceeded», «too many tokens», HTTP 413), а OpenCode
    может отдать ошибку и в событие, и в stderr.
    """
    haystack = "\n".join(t for t in texts if t).lower()
    for pattern in CONTEXT_LIMIT_PATTERNS:
        if pattern in haystack:
            return pattern
    return None


# --- Прогон руки -------------------------------------------------------------


def answer_record_text(arm: str, turn: int, session_id: str | None, status: str,
                       attempts: int, answer: str, total_turns: int = 36) -> str:
    """Текст журнальной записи ответа.

    Метаданные поворота идут блокцитатой: `check_sources.py` исключает
    блокцитаты из проверки (правило гейта), поэтому журнальная шапка не
    создаёт ложных находок sources в самом ответе агента. Разделитель
    `---` и заголовок `#` (уровень 1) секцию не открывают — проверяется
    ровно то, что ответил агент.
    """
    return (
        f"# Рука {arm}, поворот {turn} — ответ агента (дословно)\n\n"
        f"> Вопрос РП: {TURNS[turn]}\n>\n"
        f"> sessionID: {session_id}\n>\n"
        f"> Рука {arm}, поворот {turn} из {total_turns}; статус {status}, попыток {attempts}\n\n"
        f"---\n\n{answer}\n"
    )


def prompt_for_turn(arm: str, turn: int, session_id: str | None,
                    seed_components: list[dict[str, str]]) -> tuple[str, list[dict[str, str]], bool]:
    """Промпт поворота и флаг «продолжение той же сессии».

    Рука A: поворот 1 несёт полный сид, повороты 2..N — голый текст вопроса
    (предрегистрация §3: сид уже живёт в истории сессии). Дефект первого
    прогона TASK-hermes-23 — сид пересылался на каждом повороте, из-за чего
    контекст сессии рос на 131K символов за поворот и цена поворота росла
    на 45%; данные того прогона сохранены в `A-defective-contract/`.
    Руки B и C: каждый поворот — свежая сессия с полным сидом.
    """
    if arm == "A" and session_id is not None:
        return TURNS[turn], seed_components, True
    prompt, components = build_seed(arm, turn)
    return prompt, components, False


def run_hand(arm: str, turns: list[int], timeout: int, out_root: Path) -> int:
    arm_dir = out_root / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    session_id: str | None = None
    failures = 0
    seed_components: list[dict[str, str]] = []
    total_turns = len(turns)
    # Метка прогона строится из имени каталога: `t23-longdialogue` даёт
    # метки §33 байт-в-байт, `t26-longdialogue36` — метки §34. Рука A — одна
    # сессия на все повороты (хук мержит строки по sessionID, поэтому
    # поповоротные метки в COST.md для A невозможны — поповоротная цена
    # берётся из БД); руки B и C — своя сессия на поворот.
    label_prefix = out_root.name
    stopped_reason: str | None = None
    stopped_turn: int | None = None
    stopped_detail: str | None = None

    if arm == "A":
        # Сид одной сессии — в журнал целиком (это якорь воспроизводимости).
        _, components = build_seed("A", turns[0])
        prompt0, _ = build_seed("A", turns[0])
        seed_text = prompt0[: prompt0.rfind(TURNS[turns[0]])].rstrip()
        (arm_dir / "seed.md").write_text(seed_text + "\n", encoding="utf-8")
        (arm_dir / "seed-manifest.json").write_text(
            json.dumps(
                {
                    "arm": "A",
                    "seed_sha256": sha256_text(seed_text),
                    "seed_chars": len(seed_text),
                    "components": components,
                    "note": (
                        f"сид один на все {total_turns} поворотов; повороты "
                        f"2–{total_turns} — голый текст вопроса в той же сессии"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if arm == "B":
        state_text = state_text_for_seed()
        (arm_dir / "state-as-used.md").write_text(
            f"# STATE.md как использован в сиде руки B\n\n"
            f"sha256: `{sha256_text(state_text)}`\n"
            f"скопирован: {datetime.now(timezone.utc).isoformat()}\n\n---\n\n{state_text}",
            encoding="utf-8",
        )

    for turn in turns:
        # Рука A, повороты 2..N: голый текст вопроса — сид уже живёт в
        # сессии (предрегистрация §3). Дефект первого прогона (сид
        # пересылался каждый поворот → контекст рос на 131K символов за
        # поворот) исправлен здесь; данные дефектного прогона сохранены в
        # `A-defective-contract/` и учтены в COST.md.
        prompt, components, continuing = prompt_for_turn(arm, turn, session_id, seed_components)
        if not continuing and arm == "A":
            seed_components = components
        write_prompt_record(arm_dir, arm, turn, prompt, components, continuing, total_turns)

        label = f"{label_prefix}-{arm}" if arm == "A" else f"{label_prefix}-{arm}-t{turn:02d}"

        answer = ""
        attempts = 0
        status = "FAILED"
        run_meta: dict = {}
        context_limit: str | None = None
        run_label.set_run_label(label)
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                attempts = attempt
                try:
                    run_meta = run_opencode(prompt, session_id, timeout)
                except subprocess.TimeoutExpired:
                    run_meta = {
                        "session_id": session_id, "text": "", "exit_code": None,
                        "stderr_tail": f"TIMEOUT {timeout}s", "events": 0,
                        "started_utc": "", "finished_utc": "", "elapsed_sec": timeout,
                    }
                if arm == "A" and run_meta.get("session_id"):
                    session_id = run_meta["session_id"]
                answer = (run_meta.get("text") or "").strip()
                # Предел контекста (§34.2): отказ API из-за переполнения —
                # не провал поворота, а результат эксперимента. Повторять
                # нельзя (упадёт так же), прогон останавливается, всё
                # сделанное сохраняется.
                context_limit = detect_context_limit(
                    run_meta.get("stderr_tail") or "", answer
                )
                if context_limit is not None:
                    status = "CONTEXT_LIMIT"
                    break
                if run_meta.get("exit_code") == 0 and len(answer) >= MIN_ANSWER_CHARS:
                    status = "OK"
                    break
                print(
                    f"[{arm} поворот {turn}] попытка {attempt}: exit={run_meta.get('exit_code')}, "
                    f"символов {len(answer)} — повтор по протоколу §26.4",
                    flush=True,
                )
        finally:
            run_label.clear_run_label()

        metrics = (
            session_metrics(run_meta.get("session_id"))
            if run_meta.get("session_id")
            else session_metrics(None)
        )
        answer_file = arm_dir / f"turn-{turn:02d}.answer.md"
        answer_file.write_text(
            answer_record_text(arm, turn, run_meta.get("session_id"), status, attempts, answer, total_turns),
            encoding="utf-8",
        )
        meta = {
            "arm": arm,
            "turn": turn,
            "kind": TURN_KINDS.get(turn),
            "question": TURNS[turn],
            "session_id": run_meta.get("session_id"),
            "status": status,
            "attempts": attempts,
            "answer_chars": len(answer),
            "prompt_chars": len(prompt),
            "prompt_sha256": sha256_text(prompt),
            "components": components,
            "exit_code": run_meta.get("exit_code"),
            "elapsed_sec": run_meta.get("elapsed_sec"),
            "started_utc": run_meta.get("started_utc"),
            "finished_utc": run_meta.get("finished_utc"),
            "answer_file": f"{arm}/turn-{turn:02d}.answer.md",
            "prompt_file": f"{arm}/turn-{turn:02d}.prompt.md",
            "metrics_db": metrics,
            "context_limit_pattern": context_limit,
            "stderr_tail": (run_meta.get("stderr_tail") or "")[-500:],
        }
        (arm_dir / f"turn-{turn:02d}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if status != "OK":
            failures += 1
        print(
            f"[{arm} поворот {turn}] {status}: {len(answer)} символов, "
            f"тулов {metrics.get('tool_calls')}, in={metrics.get('input')}, "
            f"out={metrics.get('output')}, контекст {metrics.get('context_tokens')}",
            flush=True,
        )
        if context_limit is not None:
            # §34.2: удар в лимит контекста — РЕЗУЛЬТАТ. Останавливаем
            # прогон, причину и поворот пишем в журнал руки, всё сделанное
            # уже сохранено (ответ, мета, метрики).
            stopped_reason = "context_limit"
            stopped_turn = turn
            stopped_detail = (
                f"поворот {turn}: отказ API по признаку «{context_limit}»; "
                f"контекст на последнем successful-повороте и метрики — в "
                f"turn-*.json; stderr: {(run_meta.get('stderr_tail') or '')[-500:]}"
            )
            (arm_dir / "CONTEXT-LIMIT.md").write_text(
                "# Предел контекста: прогон остановлен (§34.2)\n\n"
                f"Рука {arm}, поворот {turn} из {total_turns}.\n\n"
                f"Признак отказа: `{context_limit}`\n\n"
                f"stderr (хвост):\n\n```\n{(run_meta.get('stderr_tail') or '')[-2000:]}\n```\n\n"
                "Это результат эксперимента (предел архитектуры), а не сбой "
                "драйвера: все предыдущие повороты сохранены в этом каталоге.\n",
                encoding="utf-8",
            )
            print(f"[{arm}] останов по лимиту контекста на повороте {turn}", flush=True)
            break

    session_payload = {
        "arm": arm,
        "session_id": session_id,
        "model": MODEL,
        "turns_requested": turns,
        "turns_executed": sorted(
            int(p.stem.split("-")[1]) for p in arm_dir.glob("turn-*.json")
        ),
        "label_prefix": label_prefix,
        "stopped_reason": stopped_reason,
        "stopped_turn": stopped_turn,
        "stopped_detail": stopped_detail,
    }
    (arm_dir / "session.json").write_text(
        json.dumps(session_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"рука {arm}: поворотов {len(turns)}, из них провалено по порогу {failures}"
          + (f", останов на повороте {stopped_turn} ({stopped_reason})" if stopped_reason else ""))
    return EXIT_OK


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_long_dialogue.py")
    parser.add_argument("--hand", required=True, choices=["A", "B", "C"])
    parser.add_argument("--turns", default=None,
                        help="диапазон «1-36», список «1,3,5» или номер «12»; "
                             "без флага — все повороты из TURNS")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    turns = parse_turns(args.turns) if args.turns else sorted(TURNS)
    out_root = Path(args.out) if args.out else RUNS_ROOT

    if args.dry_run:
        prompt, components = build_seed(args.hand, turns[0])
        # Дайджест поворотов 1–12 — якорь репликации §33: те же байты дают
        # тот же sha256, то есть план §33 воспроизводим без трат.
        digest = sha256_text("\n".join(TURNS[t] for t in range(1, 13)))
        print(f"[dry-run] рука {args.hand}, поворотов {len(turns)} ({turns[0]}–{turns[-1]}), "
              f"промпт поворота {turns[0]}: {len(prompt)} символов, "
              f"компонент {len(components)}")
        print(f"[dry-run] sha256 поворотов 1-12 (репликация §33): {digest}")
        print(f"[dry-run] метка прогона: {out_root.name}-{args.hand}"
              + ("" if args.hand == "A" else "-tNN"))
        return EXIT_OK

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении — прогон невозможен", file=sys.stderr)
        return EXIT_NO_KEY

    started = time.time()
    code = run_hand(args.hand, turns, args.timeout, out_root)
    print(f"рука {args.hand}: итог {time.time() - started:.0f}s, артефакты {out_root / args.hand}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
