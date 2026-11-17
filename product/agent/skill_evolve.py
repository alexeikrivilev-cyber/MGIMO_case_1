#!/usr/bin/env python3
"""skill_evolve.py — CLI самоулучшения навыков (TASK-hermes-14 §2).

Механика learned-скиллов Hermes, адаптированная под strategy-agent:
версии (журнал мутаций), патчи (точечная замена), откат (fail-closed) —
и предохранитель «самоулучшение только по замеру» (skill_guard).

Команды:
    propose  --skill N --file SKILL.md --old ... --new ... --evidence "..."
        Валидация + дифф; НИЧЕГО не пишет. Exit 0 = патч будет допущен.
    apply    (те же аргументы)
        Снимок before → патч → снимок after → запись в журнал.
        Exit 3 = предохранитель отказал (с причиной).
    rollback --entry ID [--actor ...] [--reason "..."]
        Восстановление before-состояния записи. Exit 4 = отказ fail-closed.
    verify   — целостность журнала (все блобы на месте, записи читаемы).
    log [--skill N] — записи журнала.
    status --skill N — счётчики патчей/откатов и список оснований.

Коды возврата: 0 — ок; 2 — использование; 3 — отказ предохранителя;
4 — откат/верификация fail-closed.
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import sys
from pathlib import Path

# Корень репо переопределяем переменной окружения (для тестов на временном
# корне; в проде путь выводится из расположения файла).
REPO_ROOT = Path(os.environ.get("STRATEGY_AGENT_ROOT") or Path(__file__).resolve().parents[2])


def _load(name: str, rel: str):
    path = Path(__file__).resolve().parent / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


skill_ledger = _load("skill_ledger", "skill_ledger.py")
skill_guard = _load("skill_guard", "skill_guard.py")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_GUARD = 3
EXIT_FAIL_CLOSED = 4


def _add_patch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skill", required=True, help="имя навыка (каталог в knowledge/skills)")
    parser.add_argument("--file", default="SKILL.md", help="файл внутри навыка")
    parser.add_argument("--old", required=True, help="заменяемый текст (единственный в файле)")
    parser.add_argument("--new", required=True, help="новый текст")
    parser.add_argument("--evidence", required=True,
                        help="основание: путь к артефакту замера или «measurements.md §N»")
    parser.add_argument("--actor", default="agent", choices=skill_ledger.VALID_ACTORS)


def _cmd_propose(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    ok, reason = skill_guard.guard_patch(args.skill, args.file, args.old, args.new,
                                         args.evidence, root)
    if not ok:
        print(f"ОТКАЗ предохранителя: {reason}", file=sys.stderr)
        return EXIT_GUARD
    target = root / "knowledge" / "skills" / args.skill / args.file
    before = target.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    # Патч может быть многострочным: ищем позицию old в тексте.
    text = "\n".join(before)
    pos = text.index(args.old)
    new_text = text[:pos] + args.new + text[pos + len(args.old):]
    after = new_text.splitlines()
    diff = difflib.unified_diff(before, after, lineterm="",
                                fromfile=f"a/{args.file}", tofile=f"b/{args.file}")
    print("\n".join(diff))
    print(f"\n[propose] допущен: {reason}")
    return EXIT_OK


def _cmd_apply(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    ok, reason = skill_guard.guard_patch(args.skill, args.file, args.old, args.new,
                                         args.evidence, root)
    if not ok:
        print(f"ОТКАЗ предохранителя: {reason}", file=sys.stderr)
        return EXIT_GUARD
    skill_dir = root / "knowledge" / "skills" / args.skill
    target = skill_dir / args.file
    before = skill_ledger.snapshot_skill(skill_dir, root)
    text = target.read_text(encoding="utf-8-sig", errors="replace")
    if text.count(args.old) != 1:
        print("ОТКАЗ: old_string не единственный (гонка между propose и apply)",
              file=sys.stderr)
        return EXIT_GUARD
    pos = text.index(args.old)
    target.write_text(text[:pos] + args.new + text[pos + len(args.old):],
                      encoding="utf-8")
    after = skill_ledger.snapshot_skill(skill_dir, root)
    entry = skill_ledger.append_entry({
        "action": "patch", "skill": args.skill, "actor": args.actor,
        "evidence": args.evidence, "file": args.file,
        "patch": {"old": args.old, "new": args.new},
        "evidence_resolved": reason, "before": before, "after": after,
    }, root)
    print(f"[apply] запись {entry['id']}: {args.skill}/{args.file}; основание: {reason}")
    return EXIT_OK


def _cmd_rollback(args: argparse.Namespace) -> int:
    try:
        entry = skill_ledger.rollback_entry(args.entry, actor=args.actor,
                                            reason=args.reason, root=REPO_ROOT)
    except skill_ledger.RollbackError as exc:
        print(f"ОТКАЗ fail-closed: {exc}", file=sys.stderr)
        return EXIT_FAIL_CLOSED
    print(f"[rollback] запись {args.entry} откачена; новая запись {entry['id']}")
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace) -> int:
    problems = skill_ledger.verify(REPO_ROOT)
    if problems:
        for problem in problems:
            print(f"ПРОБЛЕМА: {problem}", file=sys.stderr)
        return EXIT_FAIL_CLOSED
    print("[verify] журнал целостен: все блобы на месте, записи читаемы")
    return EXIT_OK


def _cmd_log(args: argparse.Namespace) -> int:
    for entry in skill_ledger.iter_entries(REPO_ROOT):
        if args.skill and entry.get("skill") != args.skill:
            continue
        print(json.dumps({k: v for k, v in entry.items()
                          if k not in ("before", "after")}, ensure_ascii=False))
    return EXIT_OK


def _cmd_status(args: argparse.Namespace) -> int:
    record = skill_ledger.usage_record(args.skill, REPO_ROOT)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return EXIT_OK


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skill_evolve.py",
        description="Самоулучшение навыков: версии, патчи, откат; "
                    "предохранитель «только по замеру».")
    sub = parser.add_subparsers(dest="command", required=True)

    p_propose = sub.add_parser("propose", help="валидация + дифф, без записи")
    _add_patch_args(p_propose)
    p_propose.set_defaults(func=_cmd_propose)

    p_apply = sub.add_parser("apply", help="применить патч и записать в журнал")
    _add_patch_args(p_apply)
    p_apply.set_defaults(func=_cmd_apply)

    p_rollback = sub.add_parser("rollback", help="откат мутации по id записи")
    p_rollback.add_argument("--entry", required=True)
    p_rollback.add_argument("--actor", default="po", choices=skill_ledger.VALID_ACTORS)
    p_rollback.add_argument("--reason", default="откат по требованию")
    p_rollback.set_defaults(func=_cmd_rollback)

    p_verify = sub.add_parser("verify", help="целостность журнала и блобов")
    p_verify.set_defaults(func=_cmd_verify)

    p_log = sub.add_parser("log", help="записи журнала")
    p_log.add_argument("--skill", default=None)
    p_log.set_defaults(func=_cmd_log)

    p_status = sub.add_parser("status", help="счётчики по навыку")
    p_status.add_argument("--skill", required=True)
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
