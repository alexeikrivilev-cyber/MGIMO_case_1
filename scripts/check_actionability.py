#!/usr/bin/env python3
"""Гейт «управляемость / готовность к действию» (TASK-hermes-16 §30.1).

Human ground truth (владелец, 2026-11-17 12:34, BRIEF п.27): в парах
1 и 4 чат победил, потому что «решал задачу целиком: приоритеты
P0–P2, последовательность, контрольные группы, KPI, критерии
остановки», а артефакт шага 3 «не доведён до плана исполнения».
Оценка /40 этого не видит: полнота вырезки вариантов и план —
разные классы. Продуктовое решение того же пункта: шаги 4–5 несут
ответственность за «готовность к действию» — поэтому в репозитории
гейт применяется к артефакту шага 4 (`project/strategy-product.md`),
а на артефактах шага 3 его находка — это ИЗМЕРЕНИЕ слепой зоны (по
дизайну шаг 3 останавливается на вариантах), а не нарушение.

Правило: пять элементов управленческого плана (состав — дословно из
BRIEF п.27), каждый ищется по группе ключевых слов
(регистронезависимо), отсутствие элемента — finding:
    1. приоритеты              → «приоритет» / «P0»…«P2»
    2. последовательность      → «последовательн» / «очеред» /
                                  «порядок» / «сначала»
    3. контрольные группы      → «контрольн…групп» / «A/B»
    4. метрики успеха (KPI)    → «KPI» / «метрик»
    5. критерии остановки      → «критерии остановки» /
                                  «когда остановить» / «останов»

Гейт проверяет НАЛИЧИЕ элементов, не их качество (разделение
ответственности — как у check_acceptance): качество плана — за
критиком и человеком.

Контракт:
    python3 scripts/check_actionability.py <file.md> [<file.md> ...]

Коды возврата: 0 — нарушений нет; 1 — ошибка вызова; 2 — нарушения.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PRIORITY_RE = re.compile(r"(приоритет|\bP[0-2]\b)", re.IGNORECASE)
SEQUENCE_RE = re.compile(r"(последовательн|очеред|порядок|сначала)", re.IGNORECASE)
CONTROL_RE = re.compile(r"(контрольн\w*\s+групп|\bA/B\b)", re.IGNORECASE)
METRIC_RE = re.compile(r"(\bKPI\b|метрик)", re.IGNORECASE)
STOP_RE = re.compile(
    r"(критерии остановки|когда остановить|критерий остановки|останов)",
    re.IGNORECASE)

ELEMENTS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("1. приоритеты", PRIORITY_RE, "приоритет / P0–P2"),
    ("2. последовательность", SEQUENCE_RE,
     "последовательность / очередь / порядок / сначала"),
    ("3. контрольные группы", CONTROL_RE, "контрольная группа / A/B"),
    ("4. метрики успеха (KPI)", METRIC_RE, "KPI / метрики"),
    ("5. критерии остановки", STOP_RE, "критерии остановки / когда остановить"),
)

FENCE_RE = re.compile(r"^\s*```")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATIONS = 2


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    in_fence = False
    active: list[str] = []
    for raw in text.splitlines():
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if not in_fence and not raw.lstrip().startswith(">"):
            active.append(raw)
    prose = "\n".join(active)
    problems = [
        f"{path}: нет элемента плана «{name}» (искали: {hint}) — "
        f"«готовность к действию» по вердикту человека, BRIEF п.27 "
        f"(пары 1 и 4)"
        for name, pattern, hint in ELEMENTS
        if not pattern.search(prose)
    ]
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print("использование: check_actionability.py <file.md> [...]",
              file=sys.stderr)
        return EXIT_USAGE
    problems: list[str] = []
    for arg in argv:
        path = Path(arg)
        if not path.is_file():
            print(f"файл не найден: {path}", file=sys.stderr)
            return EXIT_USAGE
        problems.extend(check_file(path))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"итог: нарушений {len(problems)}", file=sys.stderr)
        return EXIT_VIOLATIONS
    print(f"ok: файлов проверено {len(argv)}, нарушений нет")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
