#!/usr/bin/env python3
"""Гейт «управляемая сложность» набора вариантов (TASK-hermes-16 §30.1).

Human ground truth (владелец, 2026-11-17 12:34, BRIEF п.27, пара 5):
«4 различающихся варианта + единая таблица против 6 вариантов с
избыточной сложностью» — человек наказывает комплексность набора,
рубрика /40 её не видит: пункт 1.3 поощряет «≥3 варианта» без
потолка. Оговорка владельца из того же абзаца: «длина ≠ преимущество».

Правила:
    R1 «потолок вариантов»: заголовков вариантов (уровень «##» или
       «###», необязательный префикс «N.», затем слово «Вариант») —
       не больше MAX_VARIANTS = 5. Порог 5/6 установлен по ОДНОМУ
       человеческому вердикту (пара 5) — названо как слабое
       основание; продуктная норма — 4 (три механизма + «оставить
       как есть»), held-out несёт 5 и человеком не судился.
    R2 «единая таблица сравнения»: в файле есть markdown-таблица
       (≥3 строки таблицы, среди них строка-разделитель) — человек
       назвал «единую таблицу» достоинством победителя пары 5.
    R3 «статус-кво»: если варианты есть — среди заголовков есть
       «оставить как есть». Пересекается с check_options.py R1, но
       тот рассчитан на продуктовый формат «### Вариант N», а руки
       стенда пишут «## Вариант …» — разный формат, один инвариант.

Файл без заголовков вариантов — не артефакт типа options: явный
пропуск с печатью (не «тихий» — урок check_options: тихий пропуск
даёт «ok: нарушений нет» на опечатке пути; здесь пропуск
содержательный и назван в выводе).

Контракт:
    python3 scripts/check_complexity.py <file.md> [<file.md> ...]

Коды возврата: 0 — нарушений нет (включая названные пропуски);
1 — ошибка вызова; 2 — нарушения.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(#{2,3})\s+(.*?)\s*#*\s*$")
# Заголовок варианта: необязательный префикс «N.» / «N)», затем слово
# «Вариант» (руки стенда: «## 2. Вариант A — …», «## Вариант 0 — …»).
VARIANT_HEADING_RE = re.compile(r"^(?:\d+[.)]\s+)?вариант\b", re.IGNORECASE)
STATUS_QUO_RE = re.compile(r"оставить как есть", re.IGNORECASE)
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
MIN_TABLE_ROWS = 3

MAX_VARIANTS = 5

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATIONS = 2


def variant_headings(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        heading = HEADING_RE.match(raw.strip())
        if not heading:
            continue
        title = heading.group(2)
        if VARIANT_HEADING_RE.match(title):
            out.append((lineno, title))
    return out


def has_comparison_table(text: str) -> bool:
    rows = [line for line in text.splitlines() if TABLE_ROW_RE.match(line)]
    if len(rows) < MIN_TABLE_ROWS:
        return False
    return any(TABLE_SEP_RE.match(line) for line in rows)


def check_file(path: Path) -> tuple[list[str], bool]:
    """(нарушения, является_артефактом_вариантов)."""
    problems: list[str] = []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    variants = variant_headings(text)
    if not variants:
        # Не артефакт типа options (напр. plain-chat или research):
        # гейт неприменим — названный пропуск, не нарушение.
        return problems, False
    if len(variants) > MAX_VARIANTS:
        problems.append(
            f"{path}: вариантов {len(variants)} > {MAX_VARIANTS} — "
            f"избыточная сложность набора (человек, пара 5: «6 вариантов "
            f"с избыточной сложностью»); заголовки: "
            + "; ".join(f"L{ln}:{t[:60]}" for ln, t in variants))
    if not has_comparison_table(text):
        problems.append(
            f"{path}: нет единой таблицы сравнения вариантов — человек "
            f"назвал её достоинством победителя пары 5 («4 различающихся "
            f"варианта + единая таблица»)")
    if not any(STATUS_QUO_RE.search(title) for _, title in variants):
        problems.append(
            f"{path}: среди вариантов нет «оставить как есть» — цена "
            f"бездействия должна быть полноценным вариантом (BRIEF п.27)")
    return problems, True


def main(argv: list[str]) -> int:
    if not argv:
        print("использование: check_complexity.py <file.md> [...]", file=sys.stderr)
        return EXIT_USAGE
    problems: list[str] = []
    skipped = 0
    for arg in argv:
        path = Path(arg)
        if not path.is_file():
            print(f"файл не найден: {path}", file=sys.stderr)
            return EXIT_USAGE
        file_problems, is_options = check_file(path)
        problems.extend(file_problems)
        if not is_options:
            skipped += 1
            print(f"пропуск: {path} — не артефакт вариантов (заголовков "
                  f"«Вариант» нет), гейт неприменим")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"итог: нарушений {len(problems)}", file=sys.stderr)
        return EXIT_VIOLATIONS
    print(f"ok: файлов проверено {len(argv)} (пропусков {skipped}), нарушений нет")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
