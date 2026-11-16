#!/usr/bin/env python3
"""Дисциплина доказательств: у каждого существенного утверждения есть основание.

Контракт (PRD §2/§7 — «основания: каждое существенное утверждение в артефакте
имеет ссылку»):

    python3 scripts/check_sources.py <file.md> [<file.md> ...]

Коды возврата:
    0 — все переданные файлы прошли проверку;
    1 — ошибка вызова: нет аргументов, файл не найден или передан каталог;
    2 — найдены нарушения доказательственной дисциплины.

Правила:
    A. Файлы ``project/evidence/*.md`` (журнал доказательств, шаблон
       ``templates/evidence-record.md``) проверяются строго:
         * есть строка ``- URL: https://...`` (регекс ``https?://\\S``);
         * есть строка ``- Дата доступа: YYYY-MM-DD`` с валидной датой;
         * ровно одна отметка типа: ``[x] факт`` / ``[x] гипотеза`` /
           ``[x] прогноз`` (регистр ``[xX]``); ноль или несколько — нарушение.
    B. Остальные ``.md`` (project/brief.md, research.md, options.md,
       strategy-product.md, strategy-comms.md, verification-plan.md):
         * каждая секция (заголовок ``##`` или ``###``) содержит хотя бы одну
           ссылку — URL (``https?://``) или ``ev-N``, либо её заголовок
           матчится allowlist (регистронезависимо, по подстроке);
         * hard-claim — строка с числовым утверждением (проценты, ``2026 г``,
           ``млн``/``тыс``/``руб``/``₽``/``$`` либо глагол роста/падения рядом
           с цифрами) — должна содержать URL, ``ev-N`` или маркер
           ``[гипотеза]`` / ``[прогноз]`` / ``[допущение]`` в той же строке.
    C. Журналы измерений и протоколов прогонов (путь содержит
       ``project/council/`` или файл ``measurements.md``): их числовые
       утверждения — результаты собственных прогонов, а не факты о мире;
       основанием считается ссылка на артефакт прогона: sessionID
       (``ses_…``), хеш (≥12 hex) или имя файла/пути в бэктиках
       (``COST.md``, ``scripts/…``) — в строке утверждения либо в секции,
       документирующей процедуру измерения. Правило не ослабляет B для
       обычных артефактов.

Блокцитаты (``> ...``) и код-фенсы (`` ``` ``) из всех проверок исключаются:
это цитаты запроса и выдержки. Файл читается как UTF-8 (допускается BOM),
толерантен к CRLF. Вывод нарушений: ``путь:строка: причина``, затем итог.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

# --- Регексы правил -------------------------------------------------------

URL_RE = re.compile(r"https?://\S")
EVIDENCE_RE = re.compile(r"\bev-\d+\b")
MARKER_RE = re.compile(r"\[(?:гипотеза|прогноз|допущение)\]", re.IGNORECASE)
TYPE_MARK_RE = re.compile(r"\[[xX]\]\s*(факт|гипотеза|прогноз)", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*```")
DIGIT_RE = re.compile(r"\d")
URL_LINE_RE = re.compile(r"^[-*+]\s*URL\s*:\s*(\S.*)$")
ACCESS_DATE_LINE_RE = re.compile(r"^[-*+]\s*Дата доступа\s*:\s*(.*)$")
NUMERIC_CLAIM_RE = re.compile(
    r"(\d+(?:[.,]\d+)?\s*%|\b\d{4}\s*г|млн|тыс|руб(?:\.|лей|лях|ль)?(?![а-я])|₽|\$)"
)
GROWTH_VERB_RE = re.compile(r"вырос|упал|снизил|сократил", re.IGNORECASE)
DATE_VALUE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\b")
# Правило C: основание-артефакт для журналов измерений и прогонов —
# sessionID, хеш (≥12 hex) или имя файла/пути в бэктиках.
ARTIFACT_REF_RE = re.compile(
    r"ses_[A-Za-z0-9]{6,}|\b[0-9a-f]{12,64}\b|`[^`]+[./][^`]*`"
)

# Заголовки секций, которым ссылка не нужна (регистронезависимо, по подстроке).
ALLOWLIST = (
    "сводка",
    "чекпоинт",
    "вопрос",
    "гипотез",
    "допущен",
    "прогноз",
    "не входит",
    "план",
    "шаблон",
    "итог",
    "статус",
    "вводные",
    "запрос",
    "цель",
    "ограничения",
    "получатель",
    "доступные данные",
    "решающие",
    "что делаем",
    "следующий шаг",
    "примечание",
    "легенда",
)

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


def _is_evidence_path(path: Path) -> bool:
    """True, если файл — запись журнала доказательств (project/evidence/*.md)."""
    parts = path.parts
    for i in range(len(parts) - 1):
        if parts[i] == "project" and parts[i + 1] == "evidence":
            return True
    return False


def _heading_line(active: list[tuple[int, str]], keyword: str) -> int | None:
    """Номер строки заголовка, содержащего keyword (для адресной диагностики)."""
    keyword = keyword.lower()
    for lineno, line in active:
        match = HEADING_RE.match(line)
        if match and keyword in match.group(2).lower():
            return lineno
    return None


# --- Правило A: журнал доказательств --------------------------------------


def check_evidence_record(active: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Проверка одной записи project/evidence/*.md. Возвращает нарушения."""
    problems: list[tuple[int, str]] = []
    source_line = _heading_line(active, "источник") or FALLBACK_LINE
    type_line = _heading_line(active, "тип") or FALLBACK_LINE

    # URL
    if not any(
        URL_LINE_RE.match(line.strip()) and URL_RE.search(line)
        for _, line in active
    ):
        problems.append(
            (source_line, "нет строки «- URL: https://...» — запись без источника")
        )

    # Дата доступа
    date_lines = [
        (lineno, ACCESS_DATE_LINE_RE.match(line.strip()))
        for lineno, line in active
        if ACCESS_DATE_LINE_RE.match(line.strip())
    ]
    if not date_lines:
        problems.append(
            (source_line, "нет строки «- Дата доступа: YYYY-MM-DD»")
        )
    else:
        for lineno, match in date_lines:
            value = (match.group(1) or "").strip()
            date_match = DATE_VALUE_RE.search(value)
            if not date_match:
                problems.append(
                    (lineno, f"дата доступа не в формате YYYY-MM-DD: «{value}»")
                )
                continue
            year, month, day = (int(part) for part in date_match.groups())
            try:
                date(year, month, day)
            except ValueError:
                problems.append(
                    (lineno, f"некорректная дата доступа: «{value}»")
                )

    # Отметка типа — ровно одна
    type_marks = [
        (lineno, match)
        for lineno, line in active
        if (match := TYPE_MARK_RE.search(line))
    ]
    if not type_marks:
        problems.append(
            (
                type_line,
                "не отмечен тип записи: нужна ровно одна отметка "
                "«[x] факт», «[x] гипотеза» или «[x] прогноз»",
            )
        )
    elif len(type_marks) > 1:
        lineno = type_marks[1][0]
        problems.append(
            (
                lineno,
                f"отметок типа {len(type_marks)}, а должна быть ровно одна",
            )
        )
    return problems


# --- Правило B: обычные артефакты -----------------------------------------


def _split_sections(
    active: list[tuple[int, str]],
) -> list[tuple[int, str, list[tuple[int, str]]]]:
    """Секции документа: (строка заголовка, заголовок, строки тела).

    Секцию открывает заголовок ``##`` или ``###``; более глубокие заголовки
    (``####``+) остаются внутри секции-родителя, ``#`` закрывает её.
    """
    sections: list[tuple[int, str, list[tuple[int, str]]]] = []
    current: list | None = None
    for lineno, line in active:
        match = HEADING_RE.match(line)
        if match:
            if current is not None:
                sections.append((current[0], current[1], current[2]))
            level = len(match.group(1))
            if level in (2, 3):
                current = [lineno, match.group(2).strip(), []]
            else:
                current = None
            continue
        if current is not None:
            current[2].append((lineno, line))
    if current is not None:
        sections.append((current[0], current[1], current[2]))
    return sections


def _is_allowlisted(title: str) -> bool:
    """Заголовок в allowlist (регистронезависимо, по подстроке)."""
    lowered = title.lower()
    return any(keyword in lowered for keyword in ALLOWLIST)


def _is_measurement_log(path: Path) -> bool:
    """Правило C: журнал измерений/прогона. Для таких файлов основанием
    числового утверждения может быть ссылка на артефакт прогона.

    Охват (намеренно узкий): журналы Консилиума (`project/council/`),
    файл `measurements.md`, журналы стенда О4 (`eval/runs/…`) и
    результаты бенчмарков (`eval/benchmarks/…/results.md`,
    `analysis.md`, `manifest.md`). Правило C не ослабляет проверку
    обычных артефактов — для них основание только в строке.
    """
    parts = path.parts
    if "council" in parts:
        return True
    if path.name == "measurements.md":
        return True
    if "runs" in parts and "eval" in parts:
        return True
    if "benchmarks" in parts and path.name in ("results.md", "analysis.md", "manifest.md"):
        return True
    return False


def _has_reference(line: str, measurement_log: bool = False) -> bool:
    """В строке есть URL, ссылка на evidence или (для журналов) артефакт."""
    if URL_RE.search(line) or EVIDENCE_RE.search(line):
        return True
    return measurement_log and bool(ARTIFACT_REF_RE.search(line))


def _is_hard_claim(line: str) -> bool:
    """Строка с числовым утверждением (проценты, суммы, годы, глаголы роста)."""
    if NUMERIC_CLAIM_RE.search(line):
        return True
    return bool(GROWTH_VERB_RE.search(line) and DIGIT_RE.search(line))


def _is_grounded(line: str, measurement_log: bool = False) -> bool:
    """Утверждение имеет основание в той же строке."""
    return _has_reference(line, measurement_log) or bool(MARKER_RE.search(line))


def check_artifact(active: list[tuple[int, str]], measurement_log: bool = False) -> list[tuple[int, str]]:
    """Проверка обычного артефакта. Возвращает нарушения."""
    problems: list[tuple[int, str]] = []
    sections = _split_sections(active)

    for lineno, title, body in sections:
        if _is_allowlisted(title):
            continue
        if not any(_has_reference(line, measurement_log) for _, line in body):
            problems.append(
                (
                    lineno,
                    f"секция «{title}» без ссылки: нужен URL или ev-N "
                    "(либо заголовок из allowlist)",
                )
            )

    if not measurement_log:
        for lineno, line in active:
            if _is_hard_claim(line) and not _is_grounded(line):
                problems.append(
                    (
                        lineno,
                        "числовое утверждение без основания: нужен URL, ev-N или "
                        "маркер [гипотеза] / [прогноз] / [допущение] в этой строке",
                    )
                )
        return problems

    # Правило C (журналы измерений): числовое утверждение обосновано, если
    # ссылка на артефакт прогона есть в его строке ИЛИ в секции, которая
    # документирует процедуру измерения (секция = «чем мерили»).
    section_ref: dict[int, bool] = {}
    for lineno, title, body in sections:
        section_ref[lineno] = _is_allowlisted(title) or any(
            _has_reference(line, True) for _, line in body
        )
    current_ref = False
    for lineno, line in active:
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            if level in (2, 3):
                current_ref = section_ref.get(lineno, False)
            else:
                current_ref = False  # заголовок `#` закрывает секцию
            continue
        if _is_hard_claim(line) and not _is_grounded(line, True) and not current_ref:
            problems.append(
                (
                    lineno,
                    "числовое утверждение без основания: нужен URL, ev-N, маркер "
                    "[гипотеза] / [прогноз] / [допущение] в строке либо ссылка на "
                    "артефакт прогона в секции (правило C)",
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
    active = _active_lines(text)
    if _is_evidence_path(path):
        return check_evidence_record(active)
    return check_artifact(active, _is_measurement_log(path))


def main(argv: list[str] | None = None) -> int:
    """Разбор аргументов и запуск проверок. Возвращает код возврата."""
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        print(
            "использование: python3 scripts/check_sources.py <file.md> [<file.md> ...]",
            file=sys.stderr,
        )
        return 1
    if args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0

    unusable = [arg for arg in args if not Path(arg).is_file()]
    for arg in unusable:
        print(f"ошибка: файл не найден: {arg}", file=sys.stderr)
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
