#!/usr/bin/env python3
"""Структура вариантов: варианты — разные механизмы, у каждого есть возражения.

Контракт (PRD §3/§7 — шаг 3 «ВАРИАНТЫ», ROADMAP M4):

    python3 scripts/check_options.py <file.md> [<file.md> ...]

Коды возврата:
    0 — все переданные файлы прошли проверку;
    1 — ошибка вызова: нет аргументов, файл не найден или передан каталог;
    2 — найдены нарушения структуры вариантов.

Правила:
    R1 «варианты»: секции вариантов — заголовки ``###``, текст заголовка
       начинается со слова «Вариант» (регистронезависимо). Их должно быть
       не меньше 3, и среди заголовков обязан быть вариант с подстрокой
       «оставить как есть» (регистронезависимо) — цена бездействия
       обсуждается как полноценный вариант, а не фикция.
    R2 «возражения»: в теле каждого варианта есть хотя бы одна строка
       со словом «возражени…» (регистронезависимо) — сильное возражение
       названо, а не спрятано.
    R3 «типы утверждений»: в теле каждого варианта есть хотя бы один
       маркер ``[гипотеза]`` / ``[прогноз]`` / ``[допущение]``
       (регистронезависимо) — факт, гипотеза и прогноз не смешаны.

Проверяется каждый переданный файл: тихого пропуска по имени нет, иначе
опечатка в пути дала бы «ok: нарушений нет». Скрипт про шаг 3, поэтому
пакетный вызов вида ``project/*.md`` — не его сценарий: варианты
проверяются вызовом на ``project/options.md``.

Тело варианта — строки после его заголовка ``###`` до следующего
заголовка уровня ``#``–``###``; более глубокие заголовки остаются внутри
варианта. Блокцитаты (``> ...``) и код-фенсы (`` ``` ``) из проверок
исключаются: это цитаты запроса и выдержки. Файл читается как UTF-8
(допускается BOM), толерантен к CRLF. Вывод нарушений:
``путь:строка: причина``, затем итог.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# --- Регексы правил -------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*```")
VARIANT_WORD = "вариант"
STATUS_QUO_RE = re.compile(r"оставить как есть", re.IGNORECASE)
OBJECTION_RE = re.compile(r"возражени", re.IGNORECASE)
MARKER_RE = re.compile(r"\[(?:гипотеза|прогноз|допущение)\]", re.IGNORECASE)

# Заголовок секции варианта — уровень «###» (подразделы «####» внутри).
VARIANT_LEVEL = 3

MIN_VARIANTS = 3
FALLBACK_LINE = 1


def _active_lines(text: str) -> list[tuple[int, str]]:
    """Строки, попадающие под проверки: без код-фенсов и блокцитат.

    Возвращает список пар «номер строки (с 1), текст».
    """
    active: list[tuple[int, str]] = []
    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if raw.strip().startswith(">"):
            continue
        active.append((lineno, raw))
    return active


def _is_variant_heading(match: re.Match[str]) -> bool:
    """Заголовок ``###``, текст которого начинается со слова «Вариант»."""
    if len(match.group(1)) != VARIANT_LEVEL:
        return False
    return match.group(2).strip().lower().startswith(VARIANT_WORD)


def _split_variants(
    active: list[tuple[int, str]],
) -> list[tuple[int, str, list[tuple[int, str]]]]:
    """Секции вариантов: (строка заголовка, заголовок, строки тела).

    Вариант открывает заголовок ``###`` со словом «Вариант»; закрывает его
    заголовок уровня ``#``–``###``. Подразделы варианта (``####`` и глубже)
    остаются внутри варианта, но строки заголовков любого уровня в тело не
    попадают — иначе подраздел «Сильные возражения» выдавал бы себя за
    возражение.
    """
    variants: list[tuple[int, str, list[tuple[int, str]]]] = []
    current: list | None = None
    for lineno, line in active:
        match = HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            if _is_variant_heading(match):
                if current is not None:
                    variants.append((current[0], current[1], current[2]))
                current = [lineno, match.group(2).strip(), []]
            elif level <= VARIANT_LEVEL and current is not None:
                variants.append((current[0], current[1], current[2]))
                current = None
            continue
        if current is not None:
            current[2].append((lineno, line))
    if current is not None:
        variants.append((current[0], current[1], current[2]))
    return variants


# --- Правила R1–R3 --------------------------------------------------------


def check_variants(active: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Проверка структуры вариантов (R1–R3). Возвращает нарушения."""
    problems: list[tuple[int, str]] = []
    variants = _split_variants(active)

    if not variants:
        problems.append(
            (
                FALLBACK_LINE,
                "не найдено секций вариантов: нужен заголовок вида "
                "«### Вариант …» (не меньше 3, включая «оставить как есть»)",
            )
        )
        return problems

    first_line = variants[0][0]

    # R1: не меньше трёх вариантов
    if len(variants) < MIN_VARIANTS:
        problems.append(
            (
                first_line,
                f"вариантов {len(variants)}, а нужно не меньше {MIN_VARIANTS} "
                "(разные механизмы, а не степени одного подхода)",
            )
        )

    # R1: «оставить как есть» — полноценный вариант
    if not any(STATUS_QUO_RE.search(title) for _, title, _ in variants):
        problems.append(
            (
                first_line,
                "среди вариантов нет «оставить как есть» — цена бездействия "
                "должна быть вариантом с основаниями",
            )
        )

    # R2 и R3: по каждому варианту
    for lineno, title, body in variants:
        if not any(OBJECTION_RE.search(line) for _, line in body):
            problems.append(
                (
                    lineno,
                    f"в варианте «{title}» нет возражений: нужна хотя бы одна "
                    "строка со словом «возражени…», сильнейшее — первым",
                )
            )
        if not any(MARKER_RE.search(line) for _, line in body):
            problems.append(
                (
                    lineno,
                    f"в варианте «{title}» нет маркера типа: нужен "
                    "[гипотеза] / [прогноз] / [допущение] в строках варианта",
                )
            )

    return problems


# --- Точка входа ----------------------------------------------------------


def check_file(path: Path) -> list[tuple[int, str]]:
    """Проверяет один файл и возвращает список нарушений «строка: причина»."""
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [(1, f"файл не в кодировке UTF-8 ({exc.reason})")]
    return check_variants(_active_lines(text))


def main(argv: list[str] | None = None) -> int:
    """Разбор аргументов и запуск проверок. Возвращает код возврата."""
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        print(
            "использование: python3 scripts/check_options.py <file.md> [<file.md> ...]",
            file=sys.stderr,
        )
        return 1
    if args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0

    unusable: list[str] = []
    for arg in args:
        path = Path(arg)
        if path.is_file():
            continue
        if path.is_dir():
            print(f"ошибка: передан каталог, а не файл: {arg}", file=sys.stderr)
        else:
            print(f"ошибка: файл не найден: {arg}", file=sys.stderr)
        unusable.append(arg)
    if unusable:
        return 1

    total = 0
    checked = 0
    for arg in args:
        problems = check_file(Path(arg))
        checked += 1
        for lineno, reason in problems:
            print(f"{arg}:{lineno}: {reason}")
        total += len(problems)

    if total:
        print(f"итог: нарушений {total} в файлах {checked}")
        return 2
    print(f"ok: файлов проверено {checked}, нарушений нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
