#!/usr/bin/env python3
"""recover_state.py — восстановление STATE.md из git (PRD §12).

Поведение по PRD §12 («битый STATE.md»): восстановление из последней
валидной копии в git или из артефактов `project/`. Скрипт делает first
шаг детерминированным:

  1. проверяет текущий STATE.md (`check_state.py`);
  2. если валиден — exit 0, ничего не меняет;
  3. если битый — идёт по истории git (`git log`) от новых версий к
     старым и восстанавливает ПЕРВУЮ версию, которая проходит
     `check_state.py` (peers-validate, не «последний коммит»);
  4. если ни одна версия не проходит — откат к артефактам невозможен
     автоматически: печатает, какие секции сломаны, exit 2.

Контракт CLI:
    python3 scripts/recover_state.py [--state PATH] [--dry-run]

Коды возврата:
    0 — STATE.md валиден (или успешно восстановлен);
    1 — ошибка использования / не git-репозиторий;
    2 — восстановление не удалось (печатает диагностику).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_FAILED = 2

# Шов для тестов: корень репозитория можно переопределить env-переменной
# (тесты создают временный git-репозиторий с фикстурами STATE.md).
REPO_ROOT = Path(os.environ.get("STRATEGY_AGENT_ROOT", Path(__file__).resolve().parents[1]))
CHECK_STATE = REPO_ROOT / "scripts" / "check_state.py"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="recover_state.py",
        description="Восстановление STATE.md из последней валидной git-версии.",
    )
    parser.add_argument("--state", default="STATE.md", help="путь к STATE.md")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="только показать, какая версия восстановила бы, не писав файл",
    )
    args = parser.parse_args(argv)
    if not args.state:
        print("--state не может быть пустым", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    return args


def run_check(path: Path) -> tuple[bool, str]:
    """Прогон check_state.py на файле. Возвращает (ok, вывод)."""
    result = subprocess.run(
        [sys.executable, str(CHECK_STATE), str(path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def git_versions(state_rel: str) -> list[tuple[str, str]]:
    """[(commit, sha-аббревиатура)] версий файла в git, от новых к старым."""
    result = subprocess.run(
        ["git", "log", "--format=%H", "--", state_rel],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        return []
    return [(commit, commit[:12]) for commit in result.stdout.split()]


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    state_path = Path(args.state)
    if not state_path.is_absolute():
        state_path = (REPO_ROOT / state_path).resolve()
    state_rel = str(state_path.relative_to(REPO_ROOT)) if state_path.is_relative_to(REPO_ROOT) else str(state_path)

    ok, out = run_check(state_path)
    if ok:
        print(f"ok: {state_rel} валиден, восстановление не требуется")
        return EXIT_OK

    print(f"STATE.md битый ({out.splitlines()[0] if out else 'проверка не прошла'})")
    versions = git_versions(state_rel)
    if not versions:
        print(
            "не git-репозиторий или нет истории файла — восстановление невозможно",
            file=sys.stderr,
        )
        return EXIT_FAILED

    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "STATE.md"
        for commit, short in versions:
            show = subprocess.run(
                ["git", "show", f"{commit}:{state_rel}"],
                capture_output=True,
                cwd=str(REPO_ROOT),
            )
            if show.returncode != 0:
                continue
            candidate.write_bytes(show.stdout)
            ok, _ = run_check(candidate)
            if not ok:
                continue
            if args.dry_run:
                print(f"dry-run: восстановила бы версия {short}")
                return EXIT_OK
            state_path.write_bytes(show.stdout)
            print(f"ok: восстановлен {state_rel} из версии {short}")
            ok_after, out_after = run_check(state_path)
            print(f"проверка после восстановления: {'ok' if ok_after else out_after}")
            return EXIT_OK if ok_after else EXIT_FAILED

    print(
        "ни одна версия STATE.md в git не проходит проверку — нужен ручной "
        "разбор (артефакты project/ как источник)",
        file=sys.stderr,
    )
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
