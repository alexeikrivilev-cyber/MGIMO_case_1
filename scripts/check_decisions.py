#!/usr/bin/env python3
"""check_decisions.py — реестр решений полон (B6, PRD §11).

Проверяет `project/decisions.md` (шаблон `templates/decisions.md`):
  R1. Есть секция «Реестр решений» с таблицей и ≥1 решения (D1…).
  R2. У каждого решения заполнены: владелец, метрика, условие
      пересмотра, дата (YYYY-MM-DD). Пустые ячейки/«…»/«пока нет» —
      нарушение.
  R3. Есть секция «Основания каждого решения» со ссылками на
      артефакты (options/strategy/ev-N/URL).
  R4. Есть секция «История пересмотров» (даже если пуста — явно).

Коды возврата: 0 — ок; 1 — ошибка использования; 2 — нарушение.

Использование:
  python3 scripts/check_decisions.py project/decisions.md
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATION = 2

DECISION_ROW_RE = re.compile(r"^\|\s*(D\d+)\s*\|(.+)\|\s*$", re.M)
DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
PLACEHOLDERS = {"…", "...", "пока нет", "-", "—", "tbd", ""}

REQUIRED_SECTIONS = (
    "Реестр решений",
    "Основания каждого решения",
    "История пересмотров",
)


def is_placeholder(cell: str) -> bool:
    return cell.strip().lower() in PLACEHOLDERS


def parse_rows(text: str) -> list[tuple[str, list[str]]]:
    """[(ID, [ячейки])] строк решений из таблицы реестра."""
    rows: list[tuple[str, list[str]]] = []
    for match in DECISION_ROW_RE.finditer(text):
        cells = [c.strip() for c in match.group(2).split("|")]
        if len(cells) < 6:
            continue
        rows.append((match.group(1), cells))
    return rows


def valid_date(cell: str) -> bool:
    match = DATE_RE.search(cell)
    if not match:
        return False
    year, month, day = (int(part) for part in match.groups())
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "использование: python3 scripts/check_decisions.py project/decisions.md",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return EXIT_OK
    if len(args) > 1:
        print("ожидается один файл", file=sys.stderr)
        return EXIT_USAGE

    path = Path(args[0])
    if not path.is_file():
        print(f"файл не найден: {path}", file=sys.stderr)
        return EXIT_USAGE
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        print(f"файл не в кодировке UTF-8: {path}", file=sys.stderr)
        return EXIT_VIOLATION

    problems: list[str] = []

    for section in REQUIRED_SECTIONS:
        if section.lower() not in text.lower():
            problems.append(f"нет секции «{section}»")

    rows = parse_rows(text)
    if not rows:
        problems.append("в реестре нет строк решений (ожидается ≥1, вид «| D1 | … |»)")

    # колонки таблицы шаблона после ID:
    # 0 решение, 1 владелец, 2 дата, 3 метрика, 4 условие пересмотра, 5 статус
    fields = {
        0: "решение",
        1: "владелец",
        2: "дата",
        3: "метрика",
        4: "условие пересмотра",
        5: "статус",
    }
    for decision_id, cells in rows:
        for index, name in fields.items():
            if index >= len(cells) or is_placeholder(cells[index]):
                problems.append(f"{decision_id}: не заполнено «{name}»")
        if len(cells) > 2 and not valid_date(cells[2]):
            problems.append(f"{decision_id}: дата не в формате YYYY-MM-DD")

    grounds = re.search(
        r"##\s*Основания каждого решения(.*?)(?=\n##|\Z)", text, re.S | re.I
    )
    if grounds and not re.search(r"ev-\d+|https?://|options\.md|strategy", grounds.group(1)):
        problems.append("«Основания каждого решения» без ссылок на артефакты/evidence")

    if problems:
        print("нарушения реестра решений:")
        for line in problems:
            print(f"  {path}: {line}")
        print(f"итог: нарушений {len(problems)}")
        return EXIT_VIOLATION

    print(f"ok: решений {len(rows)} — владелец, метрика, условие пересмотра, дата на месте")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
