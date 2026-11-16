#!/usr/bin/env python3
"""build_digest.py — полный дайджест доказательств задачи для критика
(TASK-hermes-7 §20.3-Б, follow-up H3 §12.3).

Зачем: проба H3 (§12.3) давала критику дайджест, собранный ВРУЧНУЮ
(выдержки «Источник» + секции «Ре-проверка»); одна её находка оказалась
артефактом неполноты именно этой ручной выборки (claim, который ЕСТЬ в
ev-002, но не попал в ручную выборку). Гипотеза итерации Б: дайджест,
собранный МЕХАНИЧЕСКИ из всех `ev-*.md` каталога задачи целиком
(дословно, без отбора), либо (а) находит больше реальных расхождений,
либо (б) показывает, что полезность механизма ограничена не выборкой,
а самим множеством зафиксированных доказательств.

Контракт CLI:
    python3 eval/build_digest.py --evidence DIR [--out FILE] [--task-name NAME]

Выход: markdown-дайджест (заголовок «=== ev-NNN — файл ===» на запись)
+ статистика (файлов, байт) в stdout. Код возврата: 0 — готово;
2 — каталог не найден или в нём нет ev-*.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_USAGE = 2

DEFAULT_OUT = REPO_ROOT / "eval" / "runs" / "t7-digest" / "digest.md"


def build_digest(evidence_dir: Path, task_name: str) -> tuple[str, list[Path]]:
    """Собирает дайджест: все ev-*.md каталога целиком, дословно."""
    records = sorted(evidence_dir.glob("ev-*.md"))
    if not records:
        return "", []
    parts = [
        f"# Полный дайджест доказательств — {task_name}",
        "",
        "> Собран скриптом `eval/build_digest.py` из ВСЕХ записей "
        f"`{evidence_dir}` целиком, дословно, без ручного отбора "
        "(follow-up H3, measurements.md §20.3-Б).",
        "",
    ]
    for path in records:
        match = re.match(r"(ev-\d+)", path.stem)
        label = match.group(1) if match else path.stem
        parts.append(f"=== {label} ({path.name}) ===")
        parts.append(path.read_text(encoding="utf-8-sig", errors="replace").strip())
        parts.append("")
    return "\n".join(parts) + "\n", records


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="build_digest.py")
    parser.add_argument("--evidence", required=True, help="каталог с ev-*.md задачи")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--task-name", default="задача")
    args = parser.parse_args(argv)

    evidence_dir = Path(args.evidence)
    if not evidence_dir.is_dir():
        print(f"каталог не найден: {evidence_dir}", file=sys.stderr)
        return EXIT_USAGE
    digest, records = build_digest(evidence_dir, args.task_name)
    if not records:
        print(f"в {evidence_dir} нет записей ev-*.md", file=sys.stderr)
        return EXIT_USAGE

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(digest, encoding="utf-8")
    total_bytes = sum(p.stat().st_size for p in records)
    print(
        f"дайджест: {out_path} — записей {len(records)}, "
        f"байт {total_bytes}, байт дайджеста {out_path.stat().st_size}"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
