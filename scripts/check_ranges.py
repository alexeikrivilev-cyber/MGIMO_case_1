#!/usr/bin/env python3
"""Гейт «обоснованность диапазонов» (TASK-hermes-16 §30.1).

Human ground truth (владелец, 2026-11-17 12:34, BRIEF п.27, пара 6):
«у ревизии — необоснованные диапазоны» — у critic-loop2 эффект-
диапазоны вида «−5…−15 п.п. [прогноз]» стоят без видимого
основания, тогда как у победителя (skill) те же диапазоны несли
ev-N, «линейную экстраполяцию» или честную пометку [оценка].
Рубрика /40 этого класса не видит.

Что ловит гейт (механический подкласс): числовой диапазон без
НИ ОДНОГО токена основания в той же строке — ни ev-N/URL, ни слова
вывода (арифметика, экстраполяция, расчёт/пересчёт/подсчёт,
сценарий, тренд, база, модель, формула), ни любого маркера типа
claim ([прогноз]/[гипотеза]/[допущение]/[оценка]). Этот подкласс
гейт ловит детерминированно (прецедент — cl2, «4–8 недель» без
всего).

Названные ограничения (честно, как у check_transferability):
  1. Класс самого человека — ПОМЕЧЕННЫЙ, но без вывода диапазон
     («−5…−15 п.п. [прогноз]» без арифметики) — гейтом НЕ ловится:
     маркер типазирует claim, но не обосновывает его, а ev-N в той
     же строке может groundить ДРУГОЕ число (семантика). Этот
     класс — только критиком (пункт 5.3 расширенной рубрики,
     §30.2); тот же класс, что «ссылка есть, содержания нет» (§25.7).
  2. Гейт не судит адекватность основания, только его наличие.
  3. Исключаются: бэктичные токены (пути/идентификаторы), даты
     (2026-11-16), время (10:43), код-фенсы, блокцитаты.
  4. Область: аналитические артефакты (project/*.md, held-out
     artifacts, артефакты рук стенда). Evidence-записи, STATE/LOG
     и docs — вне области: несут учётные числа и цитаты со своей
     дисциплиной.
  5. Ссылки на секции («§3.1–3.6») исключены как указатели (класс
     «руб≈рубли» из check_sources, TASK-14): указатель матчился
     как числовой диапазон.
  6. Проверка идёт по ЛОГИЧЕСКИМ строкам (абзац/пункт списка со
     продолжением — прецедент check_transferability, TASK-14):
     перенос не разрывает основание, но основание одного пункта
     списка на соседний не переносится. Ограничение наличия, не
     семантики — то же, что п.1.

Контракт:
    python3 scripts/check_ranges.py <file.md> [<file.md> ...]

Коды возврата: 0 — нарушений нет; 1 — ошибка вызова; 2 — нарушения.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MINUS = "\u2212"  # − (U+2212), модели пишут им минус в диапазонах
# Разделитель диапазона: en/em dash, ellipsis, три точки.
SEP = r"(?:–|—|…|\.\.\.)"
NUM = rf"[%$₽{MINUS}\-+]?\d+(?:[.,]\d+)?"
# Зазор перед разделителем — единицы («%», «K», «п.п.»), до 6 символов;
# зазор после — валюта/знак/пробелы, до 4. Буквенный зазор после
# разделителя запрещён: иначе «P0–P2» и «L2–L4» (идентификаторы)
# матчились бы как числовой диапазон.
RANGE_RE = re.compile(
    NUM + r"[^\d" + MINUS + r"\-\+–—…\n]{0,6}?" + SEP
    + rf"[%$₽{MINUS}\-\+\s]{{0,4}}?" + r"\d+(?:[.,]\d+)?")

EV_RE = re.compile(r"(ev-\d+|https?://)", re.IGNORECASE)
DERIVATION_RE = re.compile(
    r"(арифметик|экстраполя|расч[её]т|пересч[её]т|подсч[её]т|сценари|"
    r"тренд|база|baseline|модел|формул|оценк|ориентир)", re.IGNORECASE)
MARKER_RE = re.compile(r"\[(?:прогноз|гипотеза|допущение|оценка)", re.IGNORECASE)

BACKTICK_RE = re.compile(r"`[^`]*`")
DATE_RE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")
TIME_RE = re.compile(r"\d{1,2}:\d{2}")
# Годы-период («2008–2010») — временной интервал, не claim.
YEAR_RANGE_RE = re.compile(r"\b(?:19|20)\d{2}\s*[–—]\s*(?:19|20)\d{2}\b")
# Ссылка на секции («§3.1–3.6», «§§ 3.1–3.6») — указатель, не
# количественный claim. Тот же класс ложных срабатываний, что
# «руб≈рубли» в check_sources (TASK-14): строка-указатель матчилась
# как числовой диапазон.
SECTION_RE = re.compile(
    r"§{1,2}\s*\d+(?:\.\d+)?\s*[–—…]\s*§?\s*\d+(?:\.\d+)?")
FENCE_RE = re.compile(r"^\s*```")
HEADING_RE = re.compile(r"^#{1,6}\s")
# Порядковый/составной ярлык («2–3-й день», «30–60-дневного окна») —
# идентификатор точки отсчёта, не количественный claim.
ORDINAL_RE = re.compile(r"^\s*-[а-яё]+")
# Начало пункта списка («- D2: …», «1. …»): граница логической
# строки — основание одного пункта не переносится на соседний.
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
# Строка таблицы: своя единица. Строки таблицы идут без пустых
# строк между ними, и склейка «в абзац» дала бы основанию из
# соседней строки прикрывать диапазон в этой (дефект найден
# регрессией TASK-18: находка «4–8 недель» у cl2 — прецедент,
# под который гейт написан, — пропала бы).
TABLE_ROW_RE = re.compile(r"^\s*\|")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATIONS = 2


def logical_lines(text: str) -> list[tuple[int, str]]:
    """Физические строки, свёрнутые в логические единицы.

    Перенос строки внутри абзаца или пункта списка не разрывает
    основание: число на одной строке и маркер на строке продолжения —
    одна единица (урок TASK-3: правило hard-claim в ТОЙ ЖЕ физической
    строке ломалось о переносы; прецедент абзац-проверки —
    check_transferability, TASK-14). Пункт списка, заголовок,
    блокцитата и код-фенс — границы единицы. Нулевой элемент пары —
    номер первой физической строки (для сообщения о находке).
    """
    units: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 0
    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            if buf:
                units.append((start, " ".join(buf)))
                buf = []
            continue
        if in_fence or not raw.strip():
            if buf:
                units.append((start, " ".join(buf)))
                buf = []
            continue
        if raw.lstrip().startswith(">") or HEADING_RE.match(raw):
            if buf:
                units.append((start, " ".join(buf)))
                buf = []
            continue
        if TABLE_ROW_RE.match(raw):
            # Строка таблицы — всегда своя единица (см. TABLE_ROW_RE).
            if buf:
                units.append((start, " ".join(buf)))
                buf = []
            units.append((lineno, raw.strip()))
            continue
        if LIST_ITEM_RE.match(raw) and buf:
            units.append((start, " ".join(buf)))
            buf = []
        if not buf:
            start = lineno
        buf.append(raw.strip())
    if buf:
        units.append((start, " ".join(buf)))
    return units


def check_file(path: Path) -> list[str]:
    problems: list[str] = []
    for lineno, logical in logical_lines(
            path.read_text(encoding="utf-8-sig", errors="replace")):
        # Бэктичные токены, даты, время, годы-периоды и ссылки на
        # секции убираем ДО матчинга: это указатели и служебные
        # числа, не диапазоны-claims.
        line = BACKTICK_RE.sub(" ", logical)
        line = DATE_RE.sub(" ", line)
        line = TIME_RE.sub(" ", line)
        line = YEAR_RANGE_RE.sub(" ", line)
        line = SECTION_RE.sub(" ", line)
        for match in RANGE_RE.finditer(line):
            if ORDINAL_RE.match(line[match.end():]):
                continue
            grounded = bool(EV_RE.search(line) or DERIVATION_RE.search(line)
                            or MARKER_RE.search(line))
            if not grounded:
                problems.append(
                    f"{path}:{lineno}: диапазон «{match.group(0).strip()}» "
                    f"без всякого основания в строке — нужно ev-N/URL, "
                    f"слово вывода (арифметика/сценарий/экстраполяция) или "
                    f"маркер [прогноз]/[оценка]: {logical[:110]}")
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print("использование: check_ranges.py <file.md> [...]", file=sys.stderr)
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
