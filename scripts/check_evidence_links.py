#!/usr/bin/env python3
"""check_evidence_links.py — резолвимость ссылок «артефакт → evidence»
(гейт класса «ссылка есть, содержания нет», TASK-hermes-8 §1).

Дефект, который закрывает гейт: `project/research.md` ссылался (ev-002)
на ~15 тонких срезов, которых в записи ev-002 не было (найдено
дайджест-критиком TASK-hermes-7 §20.9-Б). `check_sources.py` проверяет
НАЛИЧИЕ основания в строке, но не то, что цитируемая запись несёт
содержание числа; `check_citations.py` — только резолвимость URL. Этот
гейт проверяет содержательную резоляцию: каждое число, привязанное к
ссылке ev-N, находится в тексте записи ev-N (либо в другой записи,
цитируемой в той же строке — Attribution leniency, см. ниже).

Правила извлечения (все — эвристики с dokumentированными границами):
1. Логические строки: перенос маркдаун-списка продолжает предыдущий
   пункт (число и его основание часто на разных физических строках).
2. Строки таблицы обрабатываются по ЯЧЕЙКАМ: в одной строке могут
   цитироваться разные записи.
3. Проверяются числа-измерения: десятичные доли (42.71), счётчики
   (1 062 / 39 673) и целые с % (26%). Малые целые — проза, не проверяются.
4. Основание числа — ближайший токен в пределах окна 60 символов:
   ссылка ev-N ИЛИ маркер [гипотеза]/[прогноз]/[допущение]. Маркер
   экранирует число (согласовано с правилом B check_sources: маркер в
   строке — основание). Число перед «§2.1»-подобными пересечениями
   исключается.
5. Attribution leniency: число резолвится, если найдено в ближайшей
   записи ИЛИ в ЛЮБОЙ записи, цитируемой в той же ячейке/строке. Гейт
   проверяет класс «содержание за ссылкой есть», не «ссылка правильная»:
   путаница ev-002 ↔ ev-003 остаётся зоной человека/критика.
6. Диапазоны «ev-001…ev-003» разворачиваются в множество записей.

Границы (честно): гейт не проверяет цитаты без чисел, не различает
«совпало число, но смысл другой» (это делает дайджест-критик), не
касается файлов STATE/LOG и сырых снимков (`.txt`, `.out`) — это не
аналитические артефакты.

Контракт CLI:
    python3 scripts/check_evidence_links.py --task demo-retention
    python3 scripts/check_evidence_links.py --task heldout-growth-segment
    python3 scripts/check_evidence_links.py --task all
    python3 scripts/check_evidence_links.py --files a.md b.md --evidence DIR

Коды возврата:
    0 — все привязанные числа резолвются;
    1 — ошибка использования;
    2 — найдены нерезолвленные ссылки.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_UNRESOLVED = 2

WINDOW = 60  # символов: максимальная дистанция «число → основание»

NUM_RE = re.compile(r"\d[\d \u00a0\u202f]*[.,]\d+|\d[\d \u00a0\u202f]{3,}|\d+(?=%)")
EV_RE = re.compile(r"\b(ev-\d+)\b")
EV_RANGE_RE = re.compile(r"\b(ev-\d+)\s*(?:…|\.{3}|-)\s*(ev-\d+)\b")
MARK_RE = re.compile(r"\[(?:гипотеза|прогноз|допущение)\]")
# Новый пункт логической строки: маркер списка, заголовок, цитата,
# нумерованный пункт, строка таблицы.
ITEM_START_RE = re.compile(r"^\s*(?:[-*+>#]|\d+[.)]\s|\|)")

TASKS = {
    "demo-retention": {
        "artifacts": [
            "project/research.md",
            "project/options.md",
            "project/strategy-product.md",
            "project/strategy-comms.md",
            "project/verification-plan.md",
            "project/decisions.md",
            "project/council/run-2026-11-16-01/synthesis.md",
            "project/council/run-2026-11-16-01/frozen-brief.md",
        ],
        "evidence": "project/evidence",
    },
    "heldout-growth-segment": {
        "artifacts": [
            "eval/tasks/heldout-growth-segment/artifacts/research.md",
            "eval/tasks/heldout-growth-segment/artifacts/options.md",
            "eval/tasks/heldout-growth-segment/artifacts/strategy-product.md",
            "eval/tasks/heldout-growth-segment/artifacts/strategy-comms.md",
            "eval/tasks/heldout-growth-segment/artifacts/verification-plan.md",
        ],
        "evidence": "eval/tasks/heldout-growth-segment/artifacts/evidence",
    },
}


def normalize_number(text: str) -> str:
    """«1 062» → «1062», «42,71» → «42.71» — сравнение в одном формате."""
    return (
        text.replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace(",", ".")
    )


def normalize_text(text: str) -> str:
    return (
        text.replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace(",", ".")
    )


def load_evidence(evidence_dir: Path) -> dict[str, str]:
    """ev-NNN → нормализованный текст записи."""
    records: dict[str, str] = {}
    for path in sorted(evidence_dir.glob("ev-*.md")):
        match = re.match(r"(ev-\d+)", path.stem)
        if match:
            records[match.group(1)] = normalize_text(
                path.read_text(encoding="utf-8-sig", errors="replace")
            )
    return records


def logical_lines(text: str) -> list[tuple[int, str]]:
    """Физические строки → логические пункты (склейка переносов)."""
    out: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        if not out or ITEM_START_RE.match(raw):
            out.append((lineno, raw))
        else:
            first, prev = out[-1]
            out[-1] = (first, prev + " " + raw.strip())
    return out


def expand_citations(cell: str) -> set[str]:
    """Все записи, цитируемые в ячейке, включая диапазоны ev-001…ev-003."""
    cited = {m.group(1) for m in EV_RE.finditer(cell)}
    for match in EV_RANGE_RE.finditer(cell):
        low_m = re.search(r"\d+", match.group(1))
        high_m = re.search(r"\d+", match.group(2))
        if not low_m or not high_m:
            continue
        low, high = int(low_m.group(0)), int(high_m.group(0))
        for n in range(low, high + 1):
            cited.add(f"ev-{n:03d}")
    return cited


def check_file(path: Path, evidence: dict[str, str]) -> list[tuple[int, str, str]]:
    """Нерезолвленные ссылки файла: (строка, ev-N, число)."""
    misses: list[tuple[int, str, str]] = []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for lineno, line in logical_lines(text):
        cells = line.split("|") if line.strip().startswith("|") else [line]
        for cell in cells:
            cited = expand_citations(cell)
            if not cited:
                continue
            # Позиции ev-токенов считаем в тексте с затёртыми токенами
            # (« @ »), чтобы позиции чисел и оснований совпадали.
            ev_matches = list(EV_RE.finditer(cell))
            stripped = EV_RE.sub(" @ ", cell)
            ev_positions: list[tuple[int, int, str]] = []
            shift = 0
            for match in ev_matches:
                start = match.start() - shift
                ev_positions.append((start, start + len(" @ "), match.group(1)))
                shift += len(match.group(1)) - len(" @ ")
            marks = [
                (m.start(), m.end()) for m in MARK_RE.finditer(stripped)
            ]
            for match in NUM_RE.finditer(stripped):
                start, end = match.start(), match.end()
                # «§2.1»-подобное пересечение — не измерение.
                if start > 0 and stripped[start - 1] == "§":
                    continue
                number = normalize_number(match.group(0))
                # Ближайшее основание: ev-токен или маркер. В прозе
                # grounding обычно идёт ЗА claim («X% (ev-002)»,
                # «X% [прогноз]»), поэтому сначала ищем ближайший токен
                # ПОСЛЕ числа; если в окне его нет — ближайший ДО.
                # Дистанция — зазор между токенами (не перекрытие).
                following: list[tuple[int, str]] = []
                preceding: list[tuple[int, str]] = []
                for pos_start, pos_end, ev in ev_positions:
                    if pos_start >= end:
                        following.append((pos_start - end, ev))
                    else:
                        preceding.append((start - pos_end, ev))
                for pos_start, pos_end in marks:
                    if pos_start >= end:
                        following.append((pos_start - end, "MARK"))
                    else:
                        preceding.append((start - pos_end, "MARK"))
                best_ev, best_dist = None, None
                for pool in (following, preceding):
                    in_window = [item for item in pool if item[0] <= WINDOW]
                    if in_window:
                        best_dist, best_ev = min(in_window, key=lambda item: item[0])
                        break
                if best_dist is None or not best_ev or best_ev == "MARK":
                    continue
                resolved = number in evidence.get(best_ev, "") or any(
                    number in evidence.get(ev, "") for ev in cited
                )
                if not resolved:
                    misses.append((lineno, best_ev or "?", number))
    return misses


class _Parser(argparse.ArgumentParser):
    """Документированный контракт: ошибка использования = exit 1
    (argparse по умолчанию выходит с 2, что в этом репозитории занято
    кодом «нашлись нарушения»)."""

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"{self.prog}: ошибка: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = _Parser(
        prog="check_evidence_links.py",
        description="Резолвимость ссылок «артефакт → evidence» (число → содержание).",
    )
    parser.add_argument(
        "--task",
        choices=sorted(TASKS) + ["all"],
        help="набор артефактов задачи (demo-retention / heldout-growth-segment / all)",
    )
    parser.add_argument("--files", nargs="*", help="свои файлы артефактов (с --evidence)")
    parser.add_argument("--evidence", help="каталог записей evidence для --files")
    args = parser.parse_args(argv)
    if not args.task and not (args.files and args.evidence):
        parser.error(
            "нужно либо --task <имя|all>, либо --files ... --evidence DIR"
        )
    if args.files and not args.evidence:
        parser.error("--files требует --evidence")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    jobs: list[tuple[str, Path, Path]] = []
    if args.files:
        evidence_dir = Path(args.evidence)
        if not evidence_dir.is_dir():
            print(f"каталог evidence не найден: {evidence_dir}", file=sys.stderr)
            return EXIT_USAGE
        for name in args.files:
            path = Path(name)
            if not path.is_file():
                print(f"файл не найден: {path}", file=sys.stderr)
                return EXIT_USAGE
            jobs.append(("custom", path, evidence_dir))
    else:
        task_names = sorted(TASKS) if args.task == "all" else [args.task]
        for task_name in task_names:
            task = TASKS[task_name]
            evidence_dir = REPO_ROOT / task["evidence"]
            for rel in task["artifacts"]:
                path = REPO_ROOT / rel
                if not path.is_file():
                    print(f"файл задачи не найден: {path}", file=sys.stderr)
                    return EXIT_USAGE
                jobs.append((task_name, path, evidence_dir))

    total_misses = 0
    checked = 0
    for task_name, path, evidence_dir in jobs:
        evidence = load_evidence(evidence_dir)
        if not evidence:
            print(f"предупреждение: записей evidence нет в {evidence_dir}", file=sys.stderr)
        misses = check_file(path, evidence)
        checked += 1
        for lineno, ev, number in misses:
            print(f"{path}:{lineno}: число {number} не резолвируется в {ev} "
                  f"(иных записей строки недостаточно)")
        total_misses += len(misses)

    if total_misses:
        print(f"итог: нерезолвленных ссылок {total_misses} в файлах {checked}")
        return EXIT_UNRESOLVED
    print(f"ok: файлов проверено {checked}, все привязанные числа резолвятся")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
