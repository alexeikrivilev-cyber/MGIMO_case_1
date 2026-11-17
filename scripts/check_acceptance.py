#!/usr/bin/env python3
"""Гейт «приёмный чек-лист 6 вопросов» (TASK-hermes-14 §3, BRIEF п.27).

Human ground truth (владелец, 2026-11-17 12:34, BRIEF п.27): определение
«лучшего ответа» = 6 вопросов — что знаем/не знаем; какие решения; что
проверять первым и почему; деньги/команды/сроки; метрики успеха; когда
остановить. Сильный чат-ответ даёт план; артефакты шага 3 останавливаются
на вариантах — поэтому шаги 4–5 несут ответственность за «готовность к
действию», и гейт требует явного блока ответов на 6 вопросов в артефакте
шага 4.

Контракт:
    python3 scripts/check_acceptance.py <file.md> [<file.md> ...]

Правила:
    A. В файле есть секция с «приёмный чек-лист» или «6 вопросов» в
       заголовке (## или ###).
    B. В теле этой секции отвечены все 6 вопросов (по группам ключевых
       слов, регистронезависимо):
         1. что знаем / чего не знаем        → «знаем»
         2. какие решения                    → «реши» (решение/решения/решили)
         3. что проверять первым и почему    → «проверять первым» / «первым»
         4. деньги / команды / сроки         → «деньг» / «бюджет» / «команд» / «срок»
         5. метрики успеха                   → «метрик»
         6. когда остановить                 → «останов»
    C. Блокцитаты и код-фенсы исключаются (как в check_sources.py).

Коды возврата: 0 — все файлы прошли; 1 — ошибка вызова; 2 — нарушения.
Гейт проверяет НАЛИЧИЕ и ПОКРЫТИЕ ответов, не их качество: качество —
задача критика и человека (разделение ответственности названо).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*```")
SECTION_TITLE_RE = re.compile(r"приёмный чек-лист|6 вопросов", re.IGNORECASE)

QUESTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("1. что знаем / чего не знаем", ("знаем",)),
    ("2. какие решения", ("решен", "решил")),
    ("3. что проверять первым и почему", ("проверять первым", "первым")),
    ("4. деньги / команды / сроки", ("деньг", "бюджет", "команд", "срок")),
    ("5. метрики успеха", ("метрик",)),
    ("6. когда остановить", ("останов",)),
)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATIONS = 2


def _active_lines(text: str) -> list[tuple[int, str]]:
    active: list[tuple[int, str]] = []
    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence or raw.lstrip().startswith(">"):
            continue
        active.append((lineno, raw))
    return active


def _checklist_section(lines: list[tuple[int, str]]) -> tuple[int, list[str]] | None:
    """(номер строки заголовка, тело секции) или None, если секции нет."""
    for idx, (lineno, raw) in enumerate(lines):
        match = HEADING_RE.match(raw)
        if match and SECTION_TITLE_RE.search(match.group(2)):
            body: list[str] = []
            for _, follow in lines[idx + 1:]:
                if HEADING_RE.match(follow):
                    break
                body.append(follow)
            return lineno, body
    return None


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = _active_lines(text)
    section = _checklist_section(lines)
    if section is None:
        return [f"{path}: нет секции «Приёмный чек-лист» / «6 вопросов» "
                f"(шаги 4–5 отвечают за готовность к действию, BRIEF п.27)"]
    lineno, body = section
    body_text = "\n".join(body).lower()
    missing = [name for name, keys in QUESTIONS
               if not any(key in body_text for key in keys)]
    if missing:
        return [f"{path}:{lineno}: в приёмочном чек-листе не отвечены: "
                + "; ".join(missing)]
    return []


def main(argv: list[str]) -> int:
    if not argv:
        print("использование: check_acceptance.py <file.md> [...]", file=sys.stderr)
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
