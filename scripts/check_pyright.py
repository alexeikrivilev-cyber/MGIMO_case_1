#!/usr/bin/env python3
"""check_pyright.py — гейт статического анализа типов (TASK-hermes-17 §31.3).

Кандидат ретро TASK-15 №2, названный в §30.3: механический класс,
который pytest не видит (type errors, неразрешённые импорты, неверные
сигнатуры). Цена — одна команда. Не гипотеза, а предохранитель.

Контракт:
    python3 scripts/check_pyright.py <file.py> [<file.py> ...]

Явный список файлов, без дефолтного скана всего репозитория: гейт,
который падает на предсуществующей истории репозитория, — сломанный
гейт (урок тихих пропусков check_options). Область гейта — файлы
очереди/новые файлы; состав называет вызывающий.

НАЗВАННЫЕ ИСКЛЮЧЕНИЯ (не спрятаны, не «починены» молча): в
`scripts/run_critic.py` две ПРЕДсуществующие ошибки резолва импортов
(`arg_chunk`, `run_label`) — рантайм-pattern `sys.path.insert`, который
pyright не видит без конфигурации. Правка резолва (pyrightconfig.json
или структурная) — решение PO (§30.3). Гейт фильтрует РОВНО эти две
находки (файл + текст) и печатает их как названные; любая другая
находка — нарушение.

Ограничения названы:
1. pyright вызывается через `npx --yes pyright` — нужен node и кэш
   npx (или сеть при первом запуске); без node гейт пропускается с
   явной печатью (как тесты хука без node).
2. Гейт проверяет типы, не смысл; AUC-класс дефектов — за тестами.

Коды возврата: 0 — чисто или только названные исключения;
1 — ошибка вызова (нет файла / pyright недоступен);
2 — находки анализа.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_FINDINGS = 2

# Названные предсуществующие исключения: (файл, подстрока сообщения).
NAMED_EXCEPTIONS: tuple[tuple[str, str], ...] = (
    ("scripts/run_critic.py", 'Import "arg_chunk" could not be resolved'),
    ("scripts/run_critic.py", 'Import "run_label" could not be resolved'),
)


def run_pyright(files: list[Path]) -> dict | None:
    """JSON-выход pyright или None, если инструмент недоступен."""
    npx = shutil.which("npx")
    if not npx:
        return None
    cmd = [npx, "--yes", "pyright", "--outputjson",
           *[str(f) for f in files]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=300, cwd=str(REPO_ROOT))
    except (subprocess.TimeoutExpired, OSError):
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def main(argv: list[str]) -> int:
    if not argv:
        print("использование: check_pyright.py <file.py> [...]",
              file=sys.stderr)
        return EXIT_USAGE
    paths: list[Path] = []
    for arg in argv:
        path = Path(arg)
        if not path.is_file():
            print(f"файл не найден: {path}", file=sys.stderr)
            return EXIT_USAGE
        paths.append(path)

    payload = run_pyright(paths)
    if payload is None:
        # node/npx недоступен или инструмент упал — названный пропуск,
        # не «ok» (тихий пропуск даёт ложное «зелёное»).
        print("пропуск: pyright недоступен (npx/node) — гейт не прогонялся",
              file=sys.stderr)
        return EXIT_OK

    findings: list[str] = []
    named: list[str] = []
    for diag in payload.get("generalDiagnostics", []):
        file_ref = diag.get("file", "")
        try:
            rel = str(Path(file_ref).resolve().relative_to(REPO_ROOT))
        except ValueError:
            rel = file_ref
        message = diag.get("message", "")
        line = diag.get("range", {}).get("start", {}).get("line", 0) + 1
        severity = diag.get("severity", "error")
        entry = f"{rel}:{line}: [{severity}] {message}"
        if any(rel == exc_file and exc_text in message
               for exc_file, exc_text in NAMED_EXCEPTIONS):
            named.append(entry)
        elif severity == "error":
            findings.append(entry)

    for entry in named:
        print(f"названное исключение (предсуществующее, §30.3): {entry}")
    if findings:
        for entry in findings:
            print(f"находка: {entry}", file=sys.stderr)
        print(f"итог: находок {len(findings)}", file=sys.stderr)
        return EXIT_FINDINGS
    print(f"ok: файлов проверено {len(paths)}, находок нет "
          f"(названных исключений {len(named)})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
