#!/usr/bin/env python3
"""run_label.py — метка прогона для хука cost-append В ОТДЕЛЬНОМ ФАЙЛЕ.

Дефект (найден в ночном прогоне О4-хвоста, TASK-hermes-5): раннеры
(`scripts/run_critic.py`, `eval/run_ab.py`) писали метку «Шаг» прямо в
STATE.md, которым владеет агент. Правки STATE.md, сделанные агентом во
во время сессии критика, затирались restore'ом метки — раннер делил
файл состояния с агентом (гонка read/write на STATE.md).

Решение (TASK-hermes-6 п.4): метка живёт в отдельном файле
`eval/.cost-label`; STATE.md раннеры не трогают вообще. Хук
cost-append (`.opencode/plugins/strategy-hooks.ts`, currentStep())
читает сначала этот файл и только при его отсутствии падает назад на
STATE.md — совместимость с прогонами до фикса сохранена.

Файл метки односессионный: set → clear вокруг subprocess-прогона.
Если процесс убит между set и clear, метка остаётся в файле — хук
подхватит её для следующей сессии, поэтому stale-метка не опасна
(перезаписывается следующим set). Для человека: `--clear` сбрасывает.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LABEL_PATH = REPO_ROOT / "eval" / ".cost-label"

EXIT_OK = 0
EXIT_USAGE = 1


def label_path() -> Path:
    return LABEL_PATH


def set_run_label(label: str) -> Path:
    """Записать метку прогона в отдельный файл. STATE.md не трогается."""
    LABEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    LABEL_PATH.write_text(label + "\n", encoding="utf-8")
    return LABEL_PATH


def clear_run_label() -> None:
    """Удалить файл метки (нет файла — не ошибка)."""
    try:
        LABEL_PATH.unlink()
    except FileNotFoundError:
        pass


def current_run_label() -> str | None:
    """Текущая метка прогона или None (хук-совместимый доступ)."""
    try:
        text = LABEL_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_label.py",
        description="Метка прогона для хука cost-append в отдельном файле (STATE.md не трогается).",
    )
    parser.add_argument("--set", dest="label", default=None, help="записать метку")
    parser.add_argument("--clear", action="store_true", help="удалить файл метки")
    parser.add_argument("--show", action="store_true", help="показать текущую метку")
    args = parser.parse_args(argv)
    if sum(bool(x) for x in (args.label, args.clear, args.show)) != 1:
        parser.error("ровно одно из --set/--clear/--show")
    if args.label is not None:
        path = set_run_label(args.label)
        print(f"метка записана: {path} → {args.label}")
    elif args.clear:
        clear_run_label()
        print("метка удалена")
    else:
        print(current_run_label() or "(метки нет)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
