#!/usr/bin/env python3
"""check_commit_scope.py — гейт состава коммита (TASK-hermes-15 П.4, ретро M9).

Дефект класса «преждевременный коммит»: сообщение коммита заявляет
«task N выполнен», а дифф содержит ТОЛЬKO TASK-hermes-N.md. В этом
репозитории это произошло ВОСЕМЬ раз подряд (task 6→6c0f8c3,
7→2bd8cf4, 8→d2ebe90, 9→5201124, 10→bef56dc, 11→659e34e,
13→fb24556-WIP, 15→96158b1) — каждый раз работу приходилось делать
заново, а «готовность» из сообщения коммита не засчитывалась.

Механика M9 ретро: механическая находка → детерминированный гейт, а не
prose-правило («default to building the check over writing the rule»).
Правило простое и без исключений: индекс, содержащий ТОЛЬКО файлы
TASK-*.md, — отказ. Легитимного коммита «один TASK-файл» в дисциплине
репозитория не существует: TASK либо коммитится вместе с работой, либо
не коммитится вовсе.

Контракт:
    python3 scripts/check_commit_scope.py [--names a.md,b.md]
        [--staged-file PATH]

Без аргументов читает `git diff --cached --name-only`. --names и
--staged-file — для тестов и для проверки произвольного набора.

Коды возврата: 0 — состав допустим; 1 — ошибка вызова/git; 2 — отказ
(в индексе только TASK-файлы).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATION = 2

TASK_GLOB_PREFIX = "task-"


def staged_names(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, cwd=str(repo_root), timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff --cached упал")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def is_task_file(name: str) -> bool:
    return Path(name).name.lower().startswith(TASK_GLOB_PREFIX) and name.lower().endswith(".md")


def check(names: list[str]) -> tuple[bool, str]:
    if not names:
        return True, "индекс пуст — нечего проверять"
    if all(is_task_file(n) for n in names):
        return False, (f"в индексе только TASK-файлы: {names}. Коммит «задача "
                       "выполнена» без работы в диффе — преждевременный коммит "
                       "(8 повторов в истории); застейджи работу вместе с TASK "
                       "или убери TASK из коммита")
    return True, f"состав допустим: {len(names)} файлов"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check_commit_scope.py",
        description="Гейт состава коммита: индекс только из TASK-файлов — отказ.",
    )
    parser.add_argument("--names", default=None,
                        help="имена файлов через запятую (вместо git diff --cached)")
    parser.add_argument("--staged-file", default=None,
                        help="файл со списком имён (для тестов)")
    args = parser.parse_args(argv)

    try:
        if args.names is not None:
            names = [n.strip() for n in args.names.split(",") if n.strip()]
        elif args.staged_file is not None:
            names = [line.strip() for line in
                     Path(args.staged_file).read_text(encoding="utf-8").splitlines()
                     if line.strip()]
        else:
            names = staged_names(Path(__file__).resolve().parents[1])
    except (RuntimeError, OSError) as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return EXIT_USAGE

    ok, reason = check(names)
    if not ok:
        print(f"ОТКАЗ: {reason}", file=sys.stderr)
        return EXIT_VIOLATION
    print(f"ok: {reason}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
