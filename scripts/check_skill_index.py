#!/usr/bin/env python3
"""check_skill_index.py — гейт синхронности индекса навыков (TASK-hermes-15 П.2.1).

Механика M2/M11 декомпозиции mattpocock (docs/research/
mattpocock-decomposition.md §3, §13): ask-matt описан как «the router
that maps every user-reachable skill», с инвариантом «a new skill it
never mentions, or a stale one it still routes to, is a router that
lies». knowledge/index.md — наш роутер; гейт снимает класс «роутер
врёт» дешёвой детерминированной проверкой.

Обе стороны синхронности:
  1. навык → индекс: каждый выпущенный навык (knowledge/skills/<name>/
     SKILL.md) упомянут в индексе путьём skills/<name>/SKILL.md;
  2. индекс → навык: каждый путь skills/... из индекса существует;
  3. имя → директория: frontmatter name: навыка совпадает с именем его
     каталога (переименование каталога со старым name — тот же класс
     «роутер врёт»).

Стадирование (M3): каталог knowledge/skills/_draft/ — черновики, они
намеренно НЕ в индексе (выпуск — только решением PO с замером,
правило — в _draft/README.md). Гейт исключает _draft Named-исключением:
проверять «черновик обязан быть в индексе» — ломать правило стадирования.

Контракт:
    python3 scripts/check_skill_index.py [--index FILE] [--skills DIR]

Коды возврата: 0 — индекс синхронен; 1 — ошибка вызова; 2 — нарушения.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATIONS = 2

DRAFT_DIR = "_draft"
INDEX_PATH_REL = "knowledge/index.md"
SKILLS_DIR_REL = "knowledge/skills"
# Пути к навыкам в индексе — в бэктиках («skills/framing/SKILL.md»).
INDEX_SKILL_PATH_RE = re.compile(r"`((?:skills/)?([\w.-]+)/SKILL\.md)`")
FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)


def check(index_path: Path, skills_dir: Path) -> tuple[list[str], list[str]]:
    """Возвращает (нарушения, проверенные пути)."""
    violations: list[str] = []
    checked: list[str] = []

    if not index_path.is_file():
        return ([f"индекс не найден: {index_path}"], checked)
    index_text = index_path.read_text(encoding="utf-8-sig", errors="replace")

    # Направление 2 + сбор упомянутых в индексе навыков.
    index_skills: dict[str, str] = {}  # имя навыка → путь из индекса
    for match in INDEX_SKILL_PATH_RE.finditer(index_text):
        rel, name = match.group(1), match.group(2)
        target = index_path.parent / rel
        checked.append(rel)
        if not target.is_file():
            violations.append(
                f"индекс → навык: {index_path.name} ссылается на «{rel}», "
                f"файла нет ({target})")
        else:
            index_skills[name] = rel

    if not skills_dir.is_dir():
        violations.append(f"каталог навыков не найден: {skills_dir}")
        return (violations, checked)

    # Направление 1 + направление 3 по факту на диске.
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        if name == DRAFT_DIR:
            continue  # стадирование M3: черновики вне роутера (исключение названо)
        rel = f"skills/{name}/SKILL.md"
        if name not in index_skills:
            violations.append(
                f"навык → индекс: {rel} есть на диске, но индекс "
                f"{index_path.name} его не упоминает (роутер врёт)")
            continue
        if index_skills[name] != rel:
            violations.append(
                f"навык → индекс: {rel} на диске, а индекс ведёт на "
                f"«{index_skills[name]}» — путь устарел")
        front = skill_md.read_text(encoding="utf-8-sig", errors="replace")
        m = FRONTMATTER_NAME_RE.search(front)
        if not m:
            violations.append(f"{rel}: нет frontmatter name: — синхронизировать не с чем")
        elif m.group(1) != name:
            violations.append(
                f"{rel}: frontmatter name: «{m.group(1)}» не совпадает с "
                f"каталогом «{name}» — роутер врёт об имени")

    return (violations, checked)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check_skill_index.py",
        description="Гейт синхронности индекса навыков и SKILL.md (M2/M11).",
    )
    parser.add_argument("--index", default=str(REPO_ROOT / INDEX_PATH_REL))
    parser.add_argument("--skills", default=str(REPO_ROOT / SKILLS_DIR_REL))
    args = parser.parse_args(argv)

    violations, checked = check(Path(args.index), Path(args.skills))
    if violations:
        for v in violations:
            print(f"НАРУШЕНИЕ: {v}", file=sys.stderr)
        print(f"итог: нарушений {len(violations)} (проверено путей в индексе: {len(checked)})",
              file=sys.stderr)
        return EXIT_VIOLATIONS
    print(f"ok: индекс и навыки синхронны (обе стороны; путей в индексе: {len(checked)})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
