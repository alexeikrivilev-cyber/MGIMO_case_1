#!/usr/bin/env python3
"""apply_revision.py — точечные правки (targeted patch) черновика артефакта.

Рука `critic-loop2` стенда О4: вместо полного переписывания модель
возвращает JSON с правками «find → replace», а этот скрипт применяет их
детерминированно и защищает артефакт от потери содержимого (честная
деградация вместо пустого/обрезанного финала).

Контракт CLI:
    python3 scripts/apply_revision.py --draft FILE --patches FILE
        [--out FILE] [--report FILE]

Формат --patches (JSON):
    {"edits": [{"find": "<дословный фрагмент черновика>",
                "replace": "<новый текст>",
                "finding": "<какую находку закрывает>",
                "action": "apply|reject",
                "reason": "<обязательно при reject>"}]}

Правила:
    - action=reject → статус `rejected` (правка не применяется);
    - find должен встречаться в черновике РОВНО ОДИН РАЗ: 0 вхождений →
      `not-found`, больше одного → `ambiguous` (ни одна из них не
      применяется и попадает в отчёт);
    - вхождения считаются в текущем тексте (после ранее применённых
      правок), правки применяются в порядке перечисления;
    - проверки целостности (все обязательны, иначе integrity=BROKEN):
        * каждый заголовок черновика (`^#{1,3} `) присутствует в финале;
        * секция «оставить как есть» сохранена (если была в черновике);
        * размер финала ≥ 60% размера черновика;
    - если integrity=BROKEN или не применилась ни одна правка → финал =
      черновик дословно, fallback=yes: артефакт не теряется, деградация
      честно записана в отчёт.

Коды возврата: 0 — готово (включая честный откат к черновику);
2 — ошибка использования или файла (нет черновика/правок, битый JSON).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2

# Порог сохранения объёма: финал меньше 60% черновика — признак того, что
# правки срезали артефакт, а не усилили его.
MIN_SIZE_RATIO = 0.60

HEADER_RE = re.compile(r"^#{1,3}\s+\S")
KEEP_AS_IS_RE = re.compile(r"как\s+есть", re.IGNORECASE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="apply_revision.py",
        description="Точечные правки черновика артефакта с проверкой целостности.",
    )
    parser.add_argument("--draft", required=True, help="markdown-черновик артефакта")
    parser.add_argument("--patches", required=True, help="JSON-файл с правками")
    parser.add_argument("--out", default=None, help="файл финального артефакта (default: stdout)")
    parser.add_argument("--report", default=None, help="файл отчёта (default: stdout)")
    return parser.parse_args(argv)


def header_lines(text: str) -> list[str]:
    """Строки-заголовки markdown уровней 1–3."""
    return [line.rstrip() for line in text.splitlines() if HEADER_RE.match(line)]


def keep_as_is_headers(text: str) -> list[str]:
    """Заголовки секции «оставить как есть» (цена бездействия)."""
    return [
        line.rstrip()
        for line in text.splitlines()
        if HEADER_RE.match(line) and KEEP_AS_IS_RE.search(line)
    ]


def short_fragment(text: str, limit: int = 60) -> str:
    """Короткий вид фрагмента для таблицы отчёта."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def load_patches(path: Path) -> list:
    """Читает JSON правок. Битый формат — ошибка использования (exit 2)."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        edits = data.get("edits", [])
    elif isinstance(data, list):
        edits = data
    else:
        raise ValueError("ожидался объект {\"edits\": [...]} или список правок")
    if not isinstance(edits, list):
        raise ValueError("поле «edits» должно быть списком")
    return edits


def apply_edits(draft: str, edits: list) -> tuple[str, list[dict]]:
    """Применяет правки по порядку. Возвращает текст и строки отчёта."""
    text = draft
    rows: list[dict] = []
    for index, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            rows.append(
                {"n": index, "action": "—", "status": "invalid", "note": "правка не объект JSON"}
            )
            continue
        action = str(edit.get("action") or "apply").strip().lower()
        find = edit.get("find") or ""
        replace = edit.get("replace") or ""
        finding = str(edit.get("finding") or "").strip()
        reason = str(edit.get("reason") or "").strip()
        row = {
            "n": index,
            "action": action,
            "status": "",
            "finding": finding,
            "note": "",
        }
        if action not in ("apply", "reject"):
            row["status"] = "invalid"
            row["note"] = f"неизвестное действие «{action}» (ожидалось apply|reject)"
            rows.append(row)
            continue
        if action == "reject":
            row["status"] = "rejected"
            row["note"] = reason or "отклонено моделью (причина не названа)"
            rows.append(row)
            continue
        if not find:
            row["status"] = "invalid"
            row["note"] = "пустой find — нечего искать в черновике"
            rows.append(row)
            continue
        occurrences = text.count(find)
        if occurrences == 0:
            row["status"] = "not-found"
            row["note"] = f"0 вхождений в черновике: «{short_fragment(find)}»"
        elif occurrences > 1:
            row["status"] = "ambiguous"
            row["note"] = f"{occurrences} вхождений в черновике: «{short_fragment(find)}»"
        else:
            text = text.replace(find, replace, 1)
            row["status"] = "applied"
            row["note"] = f"«{short_fragment(find)}» → «{short_fragment(replace)}»"
        rows.append(row)
    return text, rows


def integrity_problems(draft: str, final: str) -> tuple[bool, list[str], float, dict[str, str]]:
    """Проверки целостности артефакта. Возвращает (ok, проблемы, размер, детали)."""
    problems: list[str] = []
    draft_headers = header_lines(draft)
    final_headers = set(header_lines(final))
    lost_headers = sorted({h for h in draft_headers if h not in final_headers})
    if lost_headers:
        problems.append(
            "потеряны заголовки черновика: " + "; ".join(f"«{h}»" for h in lost_headers[:5])
        )
    draft_keep = keep_as_is_headers(draft)
    final_keep = set(keep_as_is_headers(final))
    lost_keep = sorted({h for h in draft_keep if h not in final_keep})
    if lost_keep:
        problems.append(
            "потеряна секция «оставить как есть»: " + "; ".join(f"«{h}»" for h in lost_keep)
        )
    draft_bytes = len(draft.encode("utf-8"))
    final_bytes = len(final.encode("utf-8"))
    ratio = (final_bytes / draft_bytes) if draft_bytes else 1.0
    if ratio < MIN_SIZE_RATIO:
        problems.append(
            f"размер финала {final_bytes} Б меньше {MIN_SIZE_RATIO:.2f} "
            f"от черновика {draft_bytes} Б (ratio {ratio:.2f})"
        )
    details = {
        "headers": f"сохранены все ({len(set(draft_headers))})"
        if not lost_headers
        else f"потеряны: {'; '.join(lost_headers)}",
        "keep_as_is": "в черновике отсутствовала"
        if not draft_keep
        else ("сохранена" if not lost_keep else "ПОТЕРЯНА"),
        "size": f"{final_bytes} Б из {draft_bytes} Б",
    }
    return (not problems), problems, ratio, details


def summary_line(rows: list[dict], fallback: bool, integrity_ok: bool, ratio: float) -> str:
    """Одна строка итога для логов и манифеста прогона."""
    counts = Counter(row["status"] for row in rows)
    return (
        f"applied={counts.get('applied', 0)} "
        f"not_found={counts.get('not-found', 0)} "
        f"ambiguous={counts.get('ambiguous', 0)} "
        f"rejected={counts.get('rejected', 0)} "
        f"fallback={'yes' if fallback else 'no'} "
        f"integrity={'ok' if integrity_ok else 'BROKEN'} "
        f"size_ratio={ratio:.2f}"
    )


def build_report(
    draft_path: Path,
    patches_path: Path,
    rows: list[dict],
    draft: str,
    integrity_ok: bool,
    problems: list[str],
    fallback: bool,
    fallback_reason: str,
    ratio: float,
    integrity_details: dict[str, str],
) -> str:
    """Текст отчёта: таблица правок + целостность + размер + флаг отката."""
    lines = [
        "# Отчёт по точечным правкам (critic-loop2)",
        "",
        f"- Черновик: `{draft_path}` ({len(draft.encode('utf-8'))} Б)",
        f"- Правки: `{patches_path}` ({len(rows)} шт.)",
        "",
        "## Итог",
        "",
        "```",
        summary_line(rows, fallback, integrity_ok, ratio),
        "```",
        "",
        "## Правки",
        "",
        "| # | Действие | Статус | Находка | Фрагмент / причина |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        finding = row["finding"] or "—"
        lines.append(
            f"| {row['n']} | {row['action']} | {row['status']} "
            f"| {finding} | {row['note'] or '—'} |"
        )
    lines += [
        "",
        "## Целостность",
        "",
        f"- Заголовки черновика (^#{{1,3}} ): {integrity_details['headers']}",
        f"- Секция «оставить как есть»: {integrity_details['keep_as_is']}",
        f"- Размер: {integrity_details['size']} (порог {MIN_SIZE_RATIO:.2f})",
        f"- integrity: {'ok' if integrity_ok else 'BROKEN'}",
    ]
    if problems:
        lines.append("- Причины: " + "; ".join(problems))
    lines += [
        f"- fallback: {'yes' if fallback else 'no'}"
        + (f" — {fallback_reason}" if fallback_reason else ""),
        "",
    ]
    if fallback:
        lines += [
            "Финальный артефакт = черновик дословно: правки не применены, "
            "чтобы не отдать замеру потерянный или оборванный артефакт.",
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    draft_path = Path(args.draft)
    patches_path = Path(args.patches)
    for path in (draft_path, patches_path):
        if not path.is_file():
            print(f"файл не найден: {path}", file=sys.stderr)
            return EXIT_USAGE
    try:
        draft = draft_path.read_text(encoding="utf-8-sig", errors="replace")
        edits = load_patches(patches_path)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"не удалось разобрать правки {patches_path}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    final, rows = apply_edits(draft, edits)
    applied = sum(1 for row in rows if row["status"] == "applied")
    integrity_ok, problems, ratio, integrity_details = integrity_problems(draft, final)
    fallback = (not integrity_ok) or applied == 0
    fallback_reason = ""
    if fallback:
        if not integrity_ok:
            fallback_reason = "integrity=BROKEN: " + "; ".join(problems)
        else:
            fallback_reason = "не применилась ни одна правка"
        # size_ratio намеренно остаётся посчитанным по тексту С правками:
        # именно он показывает, что правки сделали с артефактом (откат к
        # черновику помечается флагом fallback=yes).
        final = draft

    report = build_report(
        draft_path,
        patches_path,
        rows,
        draft,
        integrity_ok,
        problems,
        fallback,
        fallback_reason,
        ratio,
        integrity_details,
    )
    if args.out:
        Path(args.out).write_text(final, encoding="utf-8")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report, encoding="utf-8")
    if args.out and args.report:
        print(summary_line(rows, fallback, integrity_ok, ratio))
        return EXIT_OK
    # Один из выходов идёт в stdout: сначала отчёт (если он не в файле),
    # затем артефакт (если он не в файле), последней строкой — итог.
    if not args.report:
        print(report, end="" if report.endswith("\n") else "\n")
    if not args.out:
        print(final, end="" if final.endswith("\n") else "\n")
    print(summary_line(rows, fallback, integrity_ok, ratio))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
