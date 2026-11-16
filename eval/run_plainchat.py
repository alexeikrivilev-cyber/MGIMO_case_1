#!/usr/bin/env python3
"""run_plainchat.py — рука B11(b): «обычный чат той же модели».

Предрегистрация: measurements.md §19.4. Один диалог step-5-preview с
ДОСЛОВНЫМ запросом РП (из `eval/tasks/demo-retention/task.md`), без
нашей папки-агента, навыков, проверок и инструментов — так, как
менеджер спросил бы тот же вопрос у обычного чата. Промпт
зафиксируется в `prompt.md` с sha256 (воспроизводимость).

Выход (артефакт) оценивается ТЕМИ ЖЕ метриками, что и руки стенда:
рубрика (внутренний критик, единая рубрика хакатона), citation
accuracy (check_citations.py), diversity (council_diversity.py), $/run
(COST.md по метке «О4: b11-plainchat»), время прогона.

Важная честность сравнения: обычный чат даёт ОДИН артефакт (ответ в
чате), наш агент — путь из 6 артефактов. Рубрика /40 применяется к
ответу чата как к «артефакту шага 3+4» (наиболее близкий тип);
разница в охвате пути — не преимущество рубрики, а свойство способа,
и фиксируется отдельно в B11.

Контракт CLI:
    python3 eval/run_plainchat.py [--task demo-retention] [--out DIR]
        [--timeout SEC] [--dry-run]

Коды возврата: 0 — прогон завершён; 4 — прогон упал; 2 — использование.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

import run_label  # noqa: E402  (метка прогона — отдельный файл)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_RUN_FAILED = 4
MODEL = "stepfun/step-5-preview"
TASKS = {"demo-retention": "eval/tasks/demo-retention/task.md"}

# Инструкция «обычного чата»: тот же запрос, один ответ, без папки,
# без навыков, без проверок. Ничего не обещаем про доказательства —
# чат отвечает так, как умеет.
CHAT_INSTRUCTION = """

---

Ответь на запрос выше ОДНИМ сообщением, как обычный чат-ассистент:
разберись, что происходит, и предложи стратегию — продуктовую и
коммуникационную — с метриками проверки. Без уточняющих вопросов,
без промежуточных шагов, без обещаний данных, которых у тебя нет."""


def extract_request(task_path: Path) -> str:
    """Дословный запрос РП: блок-цитата после «## Постановка»."""
    text = task_path.read_text(encoding="utf-8-sig", errors="replace")
    match = re.search(r"##\s*Постановка[^\n]*\n+((?:>.*\n?)+)", text)
    if not match:
        raise ValueError(f"в {task_path} не найден блок «Постановка»")
    quote = "\n".join(line.lstrip(">").strip() for line in match.group(1).splitlines())
    return quote.strip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_plainchat.py")
    parser.add_argument("--task", default="demo-retention", choices=sorted(TASKS))
    parser.add_argument("--out", default=None)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    task_path = REPO_ROOT / TASKS[args.task]
    if not task_path.is_file():
        print(f"задача не найдена: {task_path}", file=sys.stderr)
        return EXIT_USAGE
    request = extract_request(task_path)
    prompt = request + CHAT_INSTRUCTION
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / f"b11-plainchat-{stamp}"
    if args.dry_run:
        print(f"[dry-run] задача {args.task}, промпт {len(prompt)} символов, sha256 {prompt_hash}")
        return EXIT_OK
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    import os

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении — прогон невозможен", file=sys.stderr)
        return EXIT_RUN_FAILED

    run_label.set_run_label("О4: b11-plainchat")
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            ["opencode", "run", "--model", MODEL, prompt],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        (out_dir / "plainchat.end").write_text(
            datetime.now(timezone.utc).isoformat() + " TIMEOUT\n", encoding="utf-8"
        )
        print(f"прогон превысил таймаут {args.timeout}s", file=sys.stderr)
        return EXIT_RUN_FAILED
    finally:
        run_label.clear_run_label()
    finished = datetime.now(timezone.utc)
    elapsed = (finished - started).total_seconds()

    (out_dir / "plainchat.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "plainchat.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / "final.md").write_text(proc.stdout, encoding="utf-8")
    meta = {
        "task": args.task,
        "model": MODEL,
        "prompt_sha256_16": prompt_hash,
        "prompt_chars": len(prompt),
        "elapsed_sec": round(elapsed, 1),
        "exit": proc.returncode,
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"exit={proc.returncode} elapsed={elapsed:.1f}s out={out_dir}")
    return EXIT_OK if proc.returncode == 0 else EXIT_RUN_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
