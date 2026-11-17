#!/usr/bin/env python3
"""Гейт «управляемость / готовность к действию», ВЕРСИЯ 2 (TASK-hermes-17 §31.2).

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

ЧТО ИСПРАВЛЕНО ОТНОСИТЕЛЬНО ВЕРСИИ 1 (замер TASK-16 §30.4 назвал
слабость): v1 искала ключевые слова в ПРОЗЕ — «приоритет и порядок
запуска» в чекпоинт-сводке проходил как план (council-lite/cl2/lean
получали 0 находок при отсутствии плана), а plain-chat терял элемент
«последовательность», хотя его план выражен нумерацией P0–P2.
Дизайн-основание v2 — собственное описание плана человеком (BRIEF
п.27): элемент считается присутствующим, только если выражен
СТРУКТУРНО:
    1. приоритеты         → метка P0/P1/P2 ИЛИ заголовок раздела со
                            словом «приоритет» (прозаическое
                            «[гипотеза о приоритете]» — не элемент)
    2. последовательность → ≥2 РАЗНЫХ метки приоритета (порядок по
                            определению) ИЛИ заголовок с
                            «последовательн/порядок/очередность»
                            (прозаическое «порядок проверки» и
                            «сначала C, затем A или B» о порядке
                            ПРОВЕРОК — не элемент; живой FP cl2)
    3. контрольные группы  → словосочетание «контрольн… групп» или
                            A/B (как в v1: словосочетание, не слово)
    4. метрики успеха      → KPI ИЛИ заголовок раздела со словом
                            «метрик» ИЛИ таблица метрик (шапка с
                            «Метрика»/«Baseline») (прозаическое
                            «Метрика не сведена» — не элемент)
    5. критерии остановки  → словосочетание «критерии остановки /
                            стоп-критери / когда остановить» ИЛИ
                            пороговая зона «не работает» ИЛИ
                            заголовок раздела со словом
                            «останов/пересмотр» (прозаическое «Останов
                            на ЧЕКПОИНТЕ 3» — протокольный штамп, не
                            критерий)

Гейт проверяет НАЛИЧИЕ структурных признаков, не их качество
(разделение ответственности — как у check_acceptance): качество
плана — за критиком и человеком.

НАЗВАННЫЕ ОГРАНИЧЕНИЯ v2 (честно, предрегистрация §31.2):
1. Гейт слеп к классу «управление рисками» (вердикт человека по паре
   3): структурный план и риск-менеджмент — разные оси; это named
   limite, а не дефект.
2. A/B-рамка как требование варианта («A/B-рамку» в «Что требует»)
   считается элементом 3 — гейт не отличает требует от делает.
3. Однофайловый гейт не видит межартефактного делегирования: артефакт,
   ссылающийся на критерии остановки в verification-plan.md, получит
   находку (класс межартефактной ссылки; held-out strategy-product —
   предсуществующий случай, найден и при TASK-16).

Контракт:
    python3 scripts/check_actionability.py <file.md> [<file.md> ...]

Коды возврата: 0 — нарушений нет; 1 — ошибка вызова; 2 — нарушения.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Метка приоритета — та же нотация, что у человека (BRIEF п.27).
PRIORITY_LABEL_RE = re.compile(r"\bP[0-2]\b")
HEADING_RE = re.compile(r"^#{2,6}\s")
# «Приоритет» как СУЩЕСТВИТЕЛЬНОЕ в заголовке: падежные формы, но не
# прилагательное («Приоритетная поддержка» — имя варианта, не раздел)
# и не «приоритизация» (FP, найденный живым прогоном на hybrid).
PRIORITY_HEADING_RE = re.compile(r"приоритет(?:ы|ам|ами|ах|у|ом|е)?\b", re.IGNORECASE)
SEQUENCE_HEADING_RE = re.compile(
    r"(последовательн|порядок|очередь\s|очередност)", re.IGNORECASE)
CONTROL_RE = re.compile(r"(контрольн\w*\s+групп|\bA/B\b)", re.IGNORECASE)
KPI_RE = re.compile(r"\bKPI\b")
METRIC_HEADING_RE = re.compile(r"метрик", re.IGNORECASE)
METRIC_TABLE_HEADER_RE = re.compile(r"(метрик|baseline|база\s+сравнения)", re.IGNORECASE)
STOP_PHRASE_RE = re.compile(
    r"(критерии?\s+остановки|когда\s+остановить|стоп-критери)", re.IGNORECASE)
STOP_ZONE_RE = re.compile(r"не\s+работает", re.IGNORECASE)
STOP_HEADING_RE = re.compile(r"(останов|пересмотр)", re.IGNORECASE)

TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")

FENCE_RE = re.compile(r"^\s*```")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATIONS = 2


def _headings(lines: list[str]) -> list[str]:
    return [line for line in lines if HEADING_RE.match(line)]


def _has_metric_table(lines: list[str]) -> bool:
    """Таблица метрик: идёт подряд ≥2 строки таблицы, и шапка несёт
    «Метрика»/«Baseline» (структурный признак раздела метрик, а не
    упоминание слова в прозе)."""
    for i, line in enumerate(lines):
        if not TABLE_ROW_RE.match(line):
            continue
        if METRIC_TABLE_HEADER_RE.search(line):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if TABLE_ROW_RE.match(nxt):
                return True
    return False


def _distinct_priority_labels(prose: str) -> set[str]:
    return {m.group(0) for m in PRIORITY_LABEL_RE.finditer(prose)}


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
    headings = _headings(active)
    labels = _distinct_priority_labels(prose)

    missing: list[tuple[str, str]] = []
    # 1. приоритеты — метка приоритета или раздел.
    if not labels and not any(PRIORITY_HEADING_RE.search(h) for h in headings):
        missing.append(("1. приоритеты", "метка P0–P2 или раздел «Приоритеты»"))
    # 2. последовательность — ≥2 разных метки приоритета (порядок по
    # определению) или раздел. Прозаическое «сначала C, затем A или B»
    # (порядок ПРОВЕРОК на чекпоинте, живой FP cl2) элементом не
    # считается: структурный признак — метки или раздел.
    if (len(labels) < 2
            and not any(SEQUENCE_HEADING_RE.search(h) for h in headings)):
        missing.append(("2. последовательность",
                        "≥2 метки приоритета или раздел «Последовательность»"))
    # 3. контрольные группы — словосочетание (как в v1).
    if not CONTROL_RE.search(prose):
        missing.append(("3. контрольные группы", "контрольная группа / A/B"))
    # 4. метрики успеха — KPI, раздел или таблица метрик.
    if (not KPI_RE.search(prose)
            and not any(METRIC_HEADING_RE.search(h) for h in headings)
            and not _has_metric_table(active)):
        missing.append(("4. метрики успеха (KPI)",
                        "KPI, раздел «Метрики» или таблица метрик"))
    # 5. критерии остановки — словосочетание, пороговая зона или раздел.
    if (not STOP_PHRASE_RE.search(prose)
            and not STOP_ZONE_RE.search(prose)
            and not any(STOP_HEADING_RE.search(h) for h in headings)):
        missing.append(("5. критерии остановки",
                        "«критерии остановки» / зона «не работает» / "
                        "раздел про остановку или пересмотр"))

    return [
        f"{path}: нет структурного признака плана «{name}» (искали: {hint}) — "
        f"«готовность к действию» по вердикту человека, BRIEF п.27 "
        f"(пары 1 и 4); упоминание слова в прозе элементом не считается "
        f"(дизайн v2, TASK-hermes-17 §31.2)"
        for name, hint in missing
    ]


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
