#!/usr/bin/env python3
"""council_quota.py — проверка квот протокола Консилиума ( council-design.md §4 ).

Что проверяет (детерминированно, по файлам прогона project/council/run-*/):
  R1 (покрытие): каждая роль Phase 2 адресует КАЖДЫЙ вариант инвентаря
     (O1…O<n>) — иначе ро ль могла «забыть» вариант, и квота невыполнима.
  R2 (квота возражений): у каждого варианта либо ≥2 линз с возражением,
     либо он помечен «возражений нет» с причиной («unchallenged»).
  R3 (позиции): у каждой роли Phase 2 есть блок «ИЗМЕНЕНИЯ ПОЗИЦИЙ»
     (метрика здоровья совета — council-design.md §4 logging).
  R4 (dissent): в synthesis.md есть секция «Разногласия» — синтез обязан
     сохранить несогласие (протокол Phase 4).

Коды возврата: 0 — ок; 1 — ошибка использования (нет файла/каталога);
2 — нарушение протокола.

Использование:
  python3 scripts/council_quota.py project/council/run-2026-11-16-01
  python3 scripts/council_quota.py <run-dir> --options 14 --roles product,comms,data,devil,user
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATION = 2

DEFAULT_ROLES = ("product", "comms", "data", "devil", "user")

# адресная строка возражения: «O7 — …», «**O7** — …», «- O7: …»
OBJECTION_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?O(\d+)(?:\*\*)?\s*[—–:-]", re.M)
NO_OBJECTION_RE = re.compile(r"возражений нет", re.IGNORECASE)
POSITIONS_RE = re.compile(r"ИЗМЕНЕНИЯ ПОЗИЦИЙ", re.IGNORECASE)
DISSENT_RE = re.compile(r"^##\s*5?\.?\s*Разногласия", re.M)
# Возражение считается возражением, только если в строке есть основание
# (ev-N / URL / маркер типа) или строка содержательна (≥60 символов).
# Голое «O7 — учтено.» — не возражение и не «unchallenged»: это пробел
# квоты (performed silence), его ловит R2.
GROUNDING_RE = re.compile(r"ev-00\d|https?://|\[гипотеза\]|\[прогноз\]|\[допущение\]|\[пробел\]|\[конфликт\]|\[риск")
MIN_OBJECTION_LEN = 60


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="council_quota.py",
        description="Проверка квот протокола Консилиума по файлам прогона.",
    )
    parser.add_argument("run_dir", nargs="?", help="каталог прогона project/council/run-*/")
    parser.add_argument(
        "--options",
        type=int,
        default=14,
        help="число вариантов инвентаря (по умолчанию 14)",
    )
    parser.add_argument(
        "--roles",
        default=",".join(DEFAULT_ROLES),
        help="роли через запятую (по умолчанию product,comms,data,devil,user)",
    )
    parser.add_argument(
        "--synthesis",
        default="synthesis.md",
        help="имя файла синтеза в каталоге прогона (проверка R4)",
    )
    args = parser.parse_args(argv)
    if not args.run_dir:
        print(
            "использование: council_quota.py <каталог прогона project/council/run-*>",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    if args.options < 1:
        parser.error("--options должен быть ≥ 1")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"каталог прогона не найден: {run_dir}", file=sys.stderr)
        return EXIT_USAGE

    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    violations: list[str] = []

    addressed: dict[str, set[int]] = {}
    no_objection: dict[str, set[int]] = {}
    for role in roles:
        path = run_dir / f"phase2-{role}.out"
        if not path.is_file():
            violations.append(f"{path}: нет выхода Phase 2 роли «{role}»")
            addressed[role] = set()
            no_objection[role] = set()
            continue
        text = path.read_text(encoding="utf-8")
        hits: set[int] = set()
        silent: set[int] = set()
        bare: set[int] = set()
        for match in OBJECTION_RE.finditer(text):
            number = int(match.group(1))
            if not 1 <= number <= args.options:
                continue
            hits.add(number)
            line_end = text.find("\n", match.end())
            line = text[match.end() : line_end if line_end > 0 else len(text)]
            if NO_OBJECTION_RE.search(line):
                silent.add(number)
            elif not (GROUNDING_RE.search(line) or len(line.strip()) >= MIN_OBJECTION_LEN):
                # адресовано, но без основания и без причины «возражений нет»
                bare.add(number)
        addressed[role] = hits
        no_objection[role] = silent
        if bare:
            variants = ", ".join(f"O{n}" for n in sorted(bare))
            violations.append(
                f"{path}: варианты {variants} адресованы без возражения и "
                f"без причины «возражений нет» (performed silence, R2)"
            )
        # R3: блок изменений позиций
        if not POSITIONS_RE.search(text):
            violations.append(f"{path}: нет блока «ИЗМЕНЕНИЯ ПОЗИЦИЙ» (R3)")

    # R1: покрытие инвентаря каждой ролью
    for role in roles:
        missing = sorted(set(range(1, args.options + 1)) - addressed[role])
        if missing:
            violations.append(
                f"phase2-{role}.out: роль не адресует варианты {missing} (R1)"
            )

    # R2: квота ≥2 линз с возражением либо «unchallenged» с причиной
    for number in range(1, args.options + 1):
        objecting = [
            role
            for role in roles
            if number in addressed[role] and number not in no_objection[role]
        ]
        silent_roles = [role for role in roles if number in no_objection[role]]
        if len(objecting) < 2 and not silent_roles:
            violations.append(
                f"O{number}: возражений от {len(objecting)} линз {objecting} "
                f"и нет пометки «возражений нет» (R2)"
            )

    # R4: dissent-секция в синтезе
    synthesis_path = run_dir / args.synthesis
    if not synthesis_path.is_file():
        violations.append(f"{synthesis_path}: нет файла синтеза (R4)")
    elif not DISSENT_RE.search(synthesis_path.read_text(encoding="utf-8")):
        violations.append(f"{synthesis_path}: нет секции «Разногласия» (R4)")

    if violations:
        print("нарушения протокола Консилиума:")
        for line in violations:
            print(f"  {line}")
        print(f"итог: нарушений {len(violations)}")
        return EXIT_VIOLATION

    print(
        f"ok: {args.options} вариантов × {len(roles)} ролей — покрытие и квоты "
        f"выполнены, позиции зафиксированы, dissent-секция есть"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
