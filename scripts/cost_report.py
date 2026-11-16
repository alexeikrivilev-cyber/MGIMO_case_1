#!/usr/bin/env python3
"""Сводка стоимости прогонов из COST.md — оба контура (PRD §7/§13, PO R1).

Контракт:

    python3 scripts/cost_report.py [путь к COST.md]

Без аргумента берётся ``COST.md`` в корне репозитория; корень определяется
как ``parents[1]`` от расположения этого скрипта.

Распознаются две секции-таблицы (по заголовку ``##``, по подстроке,
регистронезависимо):
    * «Контур разработки» (dev) — колонки: Дата | Что | Модель |
      Токены in | Токены out | Оценка $ | Источник данных;
    * «Контур прода» (prod) — колонки: Дата | Прогон (sessionID) | Шаг |
      Модель | in | out | reasoning | cache read | cache write | поиск |
      Оценка $.

Строка оценима, если её колонка «Оценка $» разбирается как число.
Допустимые форматы чисел: ``8.87``, ``~8.87``, ``$1.23``, ``4 189 926``,
``4,189,926``. Прочерк (``—``) и нечисловой текст — строка неоценима;
неоценимые строки перечисляются с объяснением (первая нечисловая колонка
среди стоимости/reasoning/токенов), а их вклад в суммы равен нулю.

Коды возврата:
    0 — сводка построена (в том числе когда prod-таблица пуста);
    1 — файл не найден, пуст или не в кодировке UTF-8;
    2 — в файле не распознана структура COST.md (нет ни одной секции).

Вывод — русский, суммы токенов группируются пробелами, деньги — с двумя
знаками. Оценка $ — оценка по прайсам из
``docs/research/llm-pricing-agent-costs.md``, не факт списания.

"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATION = 2

DEV_KEYWORD = "контур разработки"
PROD_KEYWORD = "контур прода"

HEADING_RE = re.compile(r"^##\s+(.*?)\s*#*\s*$")
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
NUMBER_CLEAN_RE = re.compile(r"^[~$≈\s]+|[~$≈\s]+$")
THOUSANDS_GROUP_RE = re.compile(r"^\d{1,3}(\s\d{3})*$")
NOT_A_NUMBER_HINTS = ("—", "-", "–", "")

# Индексы колонок в строках таблиц (после split по «|» и обрезки).
DEV_COL_IN = 3
DEV_COL_OUT = 4
DEV_COL_COST = 5
PROD_COL_IN = 4
PROD_COL_OUT = 5
PROD_COL_REASONING = 6
PROD_COL_SEARCH = 9
PROD_COL_COST = 10


def repo_root() -> Path:
    """Корень репозитория: parents[1] от расположения скрипта."""
    return Path(__file__).resolve().parents[1]


def default_cost_path() -> Path:
    """Путь к COST.md по умолчанию."""
    return repo_root() / "COST.md"


def parse_number(cell: str) -> float | None:
    """Разбирает колонку как число. ``None`` — прочерк или не число.

    Терпит пробелы-разряды (``4 189 926``), запятые-разряды (``4,189,926``)
    и денежные префиксы (``~8.87``, ``$1.23``).
    """
    text = NUMBER_CLEAN_RE.sub("", cell.strip())
    if not text or text in NOT_A_NUMBER_HINTS:
        return None
    text = text.replace(" ", "").replace("\u00a0", "")
    if "," in text and "." not in text:
        parts = text.split(",")
        if parts[0].isdigit() and all(len(part) == 3 for part in parts[1:]):
            text = "".join(parts)  # запятая — разделитель разрядов
        else:
            text = text.replace(",", ".")  # запятая — десятичная
    try:
        return float(text)
    except ValueError:
        return None


def split_row(line: str) -> list[str]:
    """Строка таблицы ``| a | b |`` → список обрезанных колонок."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_row(line: str) -> bool:
    """Строка даннных таблицы (не заголовок и не разделитель)."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    cells = split_row(stripped)
    if not cells or cells[0] == "Дата":
        return False
    return not all(SEPARATOR_CELL_RE.match(cell) for cell in cells if cell)


def parse_contours(text: str) -> tuple[dict[str, list[tuple[int, list[str]]]], set[str]]:
    """COST.md → (строки таблиц по контурам, множество найденных секций).

    Секция считается найденной по заголовку ``##`` (даже если строк нет) —
    пустая таблица это «нет данных», а не ошибка структуры.
    """
    contours: dict[str, list[tuple[int, list[str]]]] = {"dev": [], "prod": []}
    seen: set[str] = set()
    current: str | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        heading = HEADING_RE.match(raw)
        if heading:
            title = heading.group(1).lower()
            if DEV_KEYWORD in title:
                current = "dev"
            elif PROD_KEYWORD in title:
                current = "prod"
            else:
                current = None
                continue
            seen.add(current)
            continue
        if current and is_table_row(raw):
            contours[current].append((lineno, split_row(raw)))
    return contours, seen


def _explanation(cells: list[str], indexes: tuple[int, ...]) -> str:
    """Первая нечисловая колонка из списка — объяснение неоценимости."""
    for index in indexes:
        if index >= len(cells):
            continue
        value = cells[index].strip()
        if not value or value in NOT_A_NUMBER_HINTS:
            continue
        if parse_number(value) is None:
            return value
    return "причина не указана"


def _cell(cells: list[str], index: int) -> str:
    """Колонка по индексу или пустая строка, если строка короче."""
    return cells[index] if index < len(cells) else ""


def _sum(values: Iterable[float]) -> float:
    return sum(values)


def _grouped(value: float) -> str:
    """4189926 → ``4 189 926`` (разряды пробелами)."""
    return f"{int(round(value)):,}".replace(",", " ")


def _money(value: float) -> str:
    return f"{value:.2f}"


def _report_contour(
    title: str,
    rows: list[tuple[int, list[str]]],
    unit: str,
    columns: dict[str, int],
    explanation_order: tuple[int, ...],
    session_column: int | None,
) -> tuple[list[str], float]:
    """Сводка по одному контуру. Возвращает (строки вывода, сумма $).

    ``unit`` — «строк»/«прогонов» (счётчик в шапке контура).
    """
    if not rows:
        return [f"{title}: {unit}: 0 — нет данных"], 0.0

    estimable: list[tuple[str, list[str]]] = []
    unestimable: list[tuple[str, str]] = []
    for _, cells in rows:
        label = _cell(cells, session_column) if session_column is not None else ""
        if parse_number(_cell(cells, columns["cost"])) is None:
            unestimable.append((label, _explanation(cells, explanation_order)))
        else:
            estimable.append((label, cells))

    lines = [f"{title}: {unit}: {len(rows)}"]
    in_total = _sum(
        parse_number(_cell(cells, columns["in"])) or 0.0 for _, cells in estimable
    )
    out_total = _sum(
        parse_number(_cell(cells, columns["out"])) or 0.0 for _, cells in estimable
    )
    cost_total = _sum(
        parse_number(_cell(cells, columns["cost"])) or 0.0 for _, cells in estimable
    )
    lines.append(f"  токены in: {_grouped(in_total)}")
    lines.append(f"  токены out: {_grouped(out_total)}")
    if "reasoning" in columns:
        reasoning_total = _sum(
            parse_number(_cell(cells, columns["reasoning"])) or 0.0
            for _, cells in estimable
        )
        lines.append(f"  токены reasoning: {_grouped(reasoning_total)}")
    if "search" in columns:
        search_total = _sum(
            parse_number(_cell(cells, columns["search"])) or 0.0
            for _, cells in estimable
        )
        lines.append(f"  поисковых вызовов: {_grouped(search_total)}")
    lines.append(f"  оценка $: {_money(cost_total)}")
    lines.append(f"  неоценимо: {unit}: {len(unestimable)}")
    for label, reason in unestimable:
        prefix = f"{label} " if label else ""
        lines.append(f"    {prefix}({reason})")
    return lines, cost_total


def build_report(text: str) -> tuple[list[str], float]:
    """Текст COST.md → (строки сводки, итог $ по обоим контурам)."""
    contours, _ = parse_contours(text)
    dev_lines, dev_cost = _report_contour(
        "Контур разработки (dev)",
        contours["dev"],
        "строк",
        {"in": DEV_COL_IN, "out": DEV_COL_OUT, "cost": DEV_COL_COST},
        (DEV_COL_COST, DEV_COL_IN, DEV_COL_OUT),
        None,
    )
    prod_lines, prod_cost = _report_contour(
        "Контур прода (prod)",
        contours["prod"],
        "прогонов",
        {
            "in": PROD_COL_IN,
            "out": PROD_COL_OUT,
            "reasoning": PROD_COL_REASONING,
            "search": PROD_COL_SEARCH,
            "cost": PROD_COL_COST,
        },
        (PROD_COL_COST, PROD_COL_REASONING, PROD_COL_IN, PROD_COL_OUT),
        1,  # sessionID — метка неоценимого прогона
    )
    lines = dev_lines + [""] + prod_lines + [""]
    lines.append(f"Итого (dev + prod): {_money(dev_cost + prod_cost)}")
    return lines, dev_cost + prod_cost


def main(argv: list[str] | None = None) -> int:
    """Разбор аргументов и печать сводки. Возвращает код возврата."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0

    path = Path(args[0]) if args else default_cost_path()
    if not path.is_file():
        print(f"ошибка: файл не найден: {path}", file=sys.stderr)
        return 1
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        print(f"ошибка: файл не в кодировке UTF-8 ({exc.reason}): {path}", file=sys.stderr)
        return 1
    if not text.strip():
        print(f"ошибка: файл пуст: {path}", file=sys.stderr)
        return 1

    _, seen = parse_contours(text)
    if not seen:
        print(
            f"ошибка: в файле не найдены секции контуров "
            f"(«{DEV_KEYWORD}» / «{PROD_KEYWORD}»): {path}",
            file=sys.stderr,
        )
        return 2

    lines, _ = build_report(text)
    print(f"ok: {path} — сводка стоимости")
    print()
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
