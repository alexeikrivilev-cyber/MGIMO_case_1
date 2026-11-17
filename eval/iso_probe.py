#!/usr/bin/env python3
"""iso_probe.py — проба изоляции стенда (TASK-hermes-11 §24.2).

Подтверждает механизм дефекта §23.0: `.opencode/opencode.json` корня
несёт `"instructions": ["docs/agents-md-staged.md"]`, поэтому `opencode
run` с cwd = корень репозитория внедряет AGENTS.md в КАЖДУЮ сессию.

Парная проба: один и тот же вопрос (знание ТОЛЬКО из AGENTS.md §4 —
схема STATE.md) задаётся (а) в корне репозитория и (б) вне репозитория
(чистый каталог ВНЕ дерева репозитория — конфиг opencode ищется вверх
от cwd, поэтому каталог внутри репозитория подхватил бы проектный
конфиг; это проверено отдельной пробой `out-inrepo-subdir`).

Результат прогона 2026-11-17: и (а), и (б) видят инструкции — вне
репозитория их внедряет persistent server :4096 (запущен с корнем
репозитория, держит конфиг репозитория; `opencode run` в этом
окружении уходит на него). Вывод: изоляция через cwd в этом окружении
невозможна; чистый L0/L1 — только прямой вызов API (прецедент §23.5).

Артефакты: eval/runs/t11-iso/{in,out,out-inrepo-subdir}/probe.{start,out,err,end}.
Метки COST.md: «О4: t11-iso-in» / «О4: t11-iso-out» (хук cost-append).

Контракт CLI:
    python3 eval/iso_probe.py [--timeout SEC]

Коды возврата: 0 — обе пробы выполнены (вердикт делает человек по
артефактам); 3 — нет ключа; 4 — прогон упал.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

import run_label  # noqa: E402

EXIT_OK = 0
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

PROBE_QUESTION = (
    "Ответь на два вопроса, не открывая никаких файлов и не выполняя "
    "команд: (1) загружены ли в твою сессию какие-либо постоянные "
    "инструкции агента из файла? Если да — назови файл-источник. "
    "(2) Если таких инструкций нет — так и напиши. В любом случае "
    "перечисли секции схемы STATE.md, если знаешь их из инструкций."
)


def run_probe(cwd: Path, out_dir: Path, label: str, timeout: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "probe.start").write_text(
        datetime.now(timezone.utc).isoformat() + f"\ncwd: {cwd}\nвопрос: {PROBE_QUESTION}\n",
        encoding="utf-8",
    )
    cmd = ["opencode", "run", "--model", "stepfun/step-5-preview", PROBE_QUESTION]
    run_label.set_run_label(label)
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        (out_dir / "probe.end").write_text(
            datetime.now(timezone.utc).isoformat() + " TIMEOUT\n", encoding="utf-8"
        )
        print(f"проба {label}: таймаут {timeout}s", file=sys.stderr)
        return EXIT_RUN_FAILED
    finally:
        run_label.clear_run_label()
    (out_dir / "probe.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "probe.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / "probe.end").write_text(
        datetime.now(timezone.utc).isoformat() + f" exit={proc.returncode}\n", encoding="utf-8"
    )
    print(f"проба {label}: exit={proc.returncode}, ответ {len(proc.stdout)} символов")
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return EXIT_RUN_FAILED
    return EXIT_OK


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="iso_probe.py",
        description="Парная проба изоляции стенда §23.0 (in-repo vs вне репозитория).",
    )
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении — прогон невозможен", file=sys.stderr)
        return EXIT_NO_KEY

    iso_root = REPO_ROOT / "eval" / "runs" / "t11-iso"
    failures = 0

    # (а) в репозитории: конфиг стенда внедряет AGENTS.md (§23.0)
    failures += run_probe(REPO_ROOT, iso_root / "in", "О4: t11-iso-in", args.timeout)

    # (б) вне репозитория: чистый каталог ВНЕ дерева репозитория (конфиг
    # opencode ищется вверх по дереву от cwd — каталог внутри репозитория
    # подхватил бы проектный конфиг; проверено пробой 2026-11-17).
    scratch = Path(os.environ.get("TMPDIR") or "/tmp")
    with tempfile.TemporaryDirectory(dir=str(scratch), prefix="iso-probe-") as tmp:
        failures += run_probe(Path(tmp), iso_root / "out", "О4: t11-iso-out", args.timeout)

    print(f"артефакты проб: {iso_root}/{{in,out}}/probe.out; провалов {failures}")
    return EXIT_RUN_FAILED if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
