#!/usr/bin/env python3
"""Гейт «переносимость оснований» (TASK-hermes-14 §3, BRIEF п.27).

Правило владельца (дословно, BRIEF п.27, 2026-11-17 12:34): «перенос
чужого датасета (IBM Telco) как причина для стриминга — запрещён без
пометки [аналог]; денежные показатели аналога не переносятся». Человек-
судья назвал это «главной содержательной слабостью» ответов: «почти все
ответы слишком уверенно связывают причины оттока стриминга с типом
контракта/оплаты/TechSupport из чужого (IBM Telco) датасета».

Устройство гейта (эвристика, и это названо честно):
- проверяется АБЗАЦ (блок строк до пустой), не отдельная строка: маркер
  переноса может стоять на строке продолжения — строковая проверка даёт
  ложные срабатывания на переносах (урок первого прогона: 8 находок,
  из них 6 — на переносах, заголовках и констатациях пробелов);
- абзац с датасетом-аналогом + причинная связка ИЛИ денежный показатель
  требует маркера переноса в том же абзаце: [аналог] /
  [гипотеза переносимости] / [гипотеза] / [прогноз] / [допущение];
- не проверяются: абзацы-заголовки (метка раздела, не утверждение),
  вопросы и секции решающих вопросов (спрашивают, не утверждают),
  констатации пробела («не знаем», «пробел», «неизвестно», «ненайдено»,
  «нет ни в одном», «не содержит») — названный пробел и есть честный
  результат, и гейт не должен наказывать за него;
- блокцитаты и код-фенсы исключаются (цитаты запроса/источников).

Эвристика не различает все формулировки «причина»; она снижает порог
уверенного переноса, а не заменяет критика (разделение названо).
Названное ограничение: абзац, где уверенный перенос и оговорка живут
ВМЕСТЕ («причина — контракт (IBM Telco), хотя данных сервиса мы не
знаем»), проходит по исключению пробела — такой класс ловится только
критиком, не гейтом.

Контракт:
    python3 scripts/check_transferability.py <file.md> [<file.md> ...]

Коды возврата: 0 — нарушений нет; 1 — ошибка вызова; 2 — нарушения.
Применение: к артефактам проекта (`project/*.md`) и артефактам held-out
(`eval/tasks/heldout-*/artifacts/*.md`). Замороженные входы задач
(`eval/tasks/*/task.md`, `materials.md`) НЕ проверяются: это вход, а не
артефакт агента.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Датасеты-аналоги и указания на «чужой» источник данных.
ANALOG_RE = re.compile(
    r"\b(telco|ibm|bank\s+marketing|online\s+shoppers|uci(?:\s+id)?\s*\d+|"
    r"датасет|dataset|аналог\w*|41\s*188|7\s*043|12\s*330)\b", re.IGNORECASE)

# Причинные связки: «вызвано», «причина», «из-за», «драйвер оттока»…
CAUSAL_RE = re.compile(
    r"(вызван|причин|из-за|вследствие|приводит к|приводят к|драйвер|"
    r"объясня|следствие|эффект\s+\S+\s+на\s+отток|влияет на отток)", re.IGNORECASE)

# Денежные показатели: рублёжные/долларовые суммы, ARPU/LTV/CPL.
MONEY_RE = re.compile(r"(₽|\bруб|\$\s?\d|\barpu\b|\bltv\b|\bcpl\b)", re.IGNORECASE)

# Маркеры переноса — в том же абзаце.
MARKER_RE = re.compile(
    r"\[(аналог|гипотеза переносимости|гипотеза|прогноз|допущение)", re.IGNORECASE)

# Констатация пробела: абзац называет, чего мы НЕ знаем — это результат,
# а не перенос причины (иначе гейт наказывает за честность).
GAP_RE = re.compile(
    r"(не знаем|пробел|неизвестн|ненайден|ненайдена|недоступно|"
    r"нет ни в одном|не содержит|не различают)", re.IGNORECASE)

FENCE_RE = re.compile(r"^\s*```")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
BACKTICK_RE = re.compile(r"`[^`]*`")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATIONS = 2


def _paragraphs(text: str) -> list[tuple[int, str, bool, str]]:
    """Абзацы активного текста: (стартовая строка, склеенный текст,
    heading_only, заголовок текущей секции).

    Исключаются код-фенсы и блокцитаты. Абзац, начавшийся с заголовка —
    heading_only: метка раздела, не утверждение.
    """
    paragraphs: list[tuple[int, str, bool, str]] = []
    in_fence = False
    current: list[str] = []
    current_line = 0
    heading_only = False
    current_section = ""
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence or raw.lstrip().startswith(">"):
            continue
        stripped = raw.strip()
        heading = HEADING_RE.match(stripped)
        if heading:
            current_section = heading.group(2).lower()
        if not stripped:
            if current:
                paragraphs.append((current_line, "\n".join(current),
                                   heading_only, current_section))
                current = []
                heading_only = False
            continue
        if not current:
            current_line = lineno
            heading_only = bool(heading)
        current.append(stripped)
    if current:
        paragraphs.append((current_line, "\n".join(current),
                           heading_only, current_section))
    return paragraphs


def _in_question_context(paragraph: str) -> bool:
    """Абзац спрашивает (вопрос в любом переносе) или живёт в секции
    решающих вопросов — он не утверждает перенос."""
    if paragraph.rstrip().endswith("?"):
        return True
    return any("вопрос" in line.lower()
               for line in paragraph.splitlines() if HEADING_RE.match(line))


def check_file(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for lineno, paragraph, heading_only, section in _paragraphs(text):
        if heading_only:
            continue
        if "вопрос" in section:
            continue  # секция уточняющих/решающих вопросов: спрашивают
        # Бэктичные токены — пути/идентификаторы (напр. ev-001-...-dataset.md):
        # это указатели, не упоминание датасета; убираем до матчинга.
        prose = BACKTICK_RE.sub(" ", paragraph)
        if not ANALOG_RE.search(prose):
            continue
        if MARKER_RE.search(paragraph):
            continue
        if GAP_RE.search(prose):
            continue
        if _in_question_context(prose):
            continue
        causal = bool(CAUSAL_RE.search(prose))
        money = bool(MONEY_RE.search(prose))
        if causal:
            problems.append(
                f"{path}:{lineno}: причинная связка на датасете-аналоге без "
                f"маркера переноса — нужно [аналог] / [гипотеза переносимости] "
                f"(аналоги ≠ причины, BRIEF п.27): {paragraph[:120]}")
        if money:
            problems.append(
                f"{path}:{lineno}: денежный показатель рядом с датасетом-аналогом "
                f"без маркера — денежные показатели аналога не переносятся "
                f"(BRIEF п.27): {paragraph[:120]}")
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print("использование: check_transferability.py <file.md> [...]", file=sys.stderr)
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
