#!/usr/bin/env python3
"""Валидность STATE.md — схемы состояния задачи (PRD §6) перед концом сеанса.

Контракт:

    python3 scripts/check_state.py [путь]

Без аргумента берётся ``STATE.md`` в корне репозитория; корень определяется
как ``parents[1]`` от расположения этого скрипта.

Обязательные секции ``##`` (точные имена):
    objective · шаг · завершённые шаги · решения и причины ·
    открытые вопросы · обязательства · ключевые файлы ·
    провалившиеся подходы · стоимость на сейчас.

Коды возврата:
    0 — STATE.md валиден;
    1 — файл не найден или пуст;
    2 — нарушена схема.

Нарушения:
    * отсутствует обязательная секция;
    * секции «objective» или «шаг» пустые (в том числе плейсхолдер
      «(пока нет)»);
    * в «ключевые файлы» путь в бэктиках не существует относительно корня
      репозитория.

В остальных секциях плейсхолдер «(пока нет)» допустим. Вывод нарушений:
``путь:строка: причина``, затем итог по-русски.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = (
    "objective",
    "шаг",
    "завершённые шаги",
    "решения и причины",
    "открытые вопросы",
    "обязательства",
    "ключевые файлы",
    "провалившиеся подходы",
    "стоимость на сейчас",
)

# Секции, которым плейсхолдер «(пока нет)» не разрешён.
SECTIONS_REQUIRING_CONTENT = ("objective", "шаг")

PLACEHOLDER = "(пока нет)"
HEADING_RE = re.compile(r"^##\s+(.*?)\s*#*\s*$")
BACKTICK_PATH_RE = re.compile(r"`([^`]*)`")


def repo_root() -> Path:
    """Корень репозитория: parents[1] от расположения скрипта."""
    return Path(__file__).resolve().parents[1]


def default_state_path() -> Path:
    """Путь к STATE.md по умолчанию."""
    return repo_root() / "STATE.md"


def parse_sections(text: str) -> dict[str, tuple[int, list[tuple[int, str]]]]:
    """Разбирает STATE.md на секции: имя → (строка заголовка, тело с номерами)."""
    sections: dict[str, tuple[int, list[tuple[int, str]]]] = {}
    current_name: str | None = None
    current_lines: list[tuple[int, str]] = []
    current_lineno = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        match = HEADING_RE.match(raw)
        if match:
            if current_name is not None:
                sections[current_name] = (current_lineno, current_lines)
            current_name = match.group(1).strip()
            current_lines = []
            current_lineno = lineno
            continue
        if current_name is not None:
            current_lines.append((lineno, raw))
    if current_name is not None:
        sections[current_name] = (current_lineno, current_lines)
    return sections


def body_text(lines: list[tuple[int, str]]) -> str:
    """Текст секции без markdown-оформления списков."""
    stripped = [line.strip().lstrip("-*+").strip() for _, line in lines]
    return "\n".join(part for part in stripped if part).strip()


def check_state_file(path: Path, root: Path) -> list[tuple[int, str]]:
    """Проверяет STATE.md по схеме. Возвращает нарушения «строка: причина»."""
    sections = parse_sections(path.read_text(encoding="utf-8-sig"))
    problems: list[tuple[int, str]] = []

    for name in REQUIRED_SECTIONS:
        if name not in sections:
            problems.append((1, f"отсутствует обязательная секция «{name}»"))

    for name in SECTIONS_REQUIRING_CONTENT:
        if name not in sections:
            continue
        lineno, lines = sections[name]
        content = body_text(lines)
        if not content:
            problems.append((lineno, f"секция «{name}» пуста"))
        elif content == PLACEHOLDER:
            problems.append(
                (lineno, f"секция «{name}» не заполнена (плейсхолдер «{PLACEHOLDER}»)")
            )

    if "ключевые файлы" in sections:
        _, lines = sections["ключевые файлы"]
        for lineno, line in lines:
            for token in BACKTICK_PATH_RE.findall(line):
                problems.extend(_check_referenced_path(token, lineno, root))

    return sorted(problems, key=lambda item: item[0])


def _check_referenced_path(
    token: str, lineno: int, root: Path
) -> list[tuple[int, str]]:
    """Проверяет существование одного пути из бэктиков."""
    cleaned = token.strip()
    if not cleaned or any(char.isspace() for char in cleaned):
        # Не путь (пустая строка или команда) — проверке не подлежит.
        return []
    target = Path(cleaned)
    if not target.is_absolute():
        target = root / target
    if target.exists():
        return []
    return [(lineno, f"файл из «ключевые файлы» не найден: «{cleaned}»")]


def main(argv: list[str] | None = None) -> int:
    """Разбор аргументов и проверка STATE.md. Возвращает код возврата."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0

    path = Path(args[0]) if args else default_state_path()
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

    problems = check_state_file(path, repo_root())
    if problems:
        for lineno, reason in problems:
            print(f"{path}:{lineno}: {reason}")
        print(f"итог: нарушений {len(problems)}")
        return 2

    print(
        f"ok: {path} — схема валидна "
        f"(все {len(REQUIRED_SECTIONS)} обязательных секций на месте)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
