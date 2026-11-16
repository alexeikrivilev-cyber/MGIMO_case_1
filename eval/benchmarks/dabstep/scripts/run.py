#!/usr/bin/env python3
"""run.py — прогон стенда DABstep (dev-сплит, 10 задач с эталонными ответами).

Контракт CLI:
    python3 run.py --data DIR --tasks JSON [--out DIR]

Ожидаемый формат tasks JSON: [{"task_id", "question", "answer",
"guidelines", "level"}, ...] (dev-сплит adyen/DABstep, ответы —
официальные).

Выход в --out: results.json (полная трасса) и results.md (таблица).
Коды возврата: 0 — прогон завершён; 2 — нет ключа/данных/задач.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

EXIT_OK = 0
EXIT_USAGE = 2

# Прайс step-5-preview (§1.8 docs/research/llm-pricing-agent-costs.md):
# input $1.00/1M, cache.read $0.10/1M, output $2.70/1M (output включает
# reasoning). API отдаёт prompt_tokens без кэш-хитов (кэш — отдельно в
# prompt_tokens_details.cached_tokens) — учтены оба слагаемых.
PRICE_IN = 1.0
PRICE_CACHE = 0.1
PRICE_OUT = 2.7


def estimate_usd(usage: dict) -> float:
    return (
        usage.get("prompt_tokens", 0) * PRICE_IN
        + usage.get("cached_tokens", 0) * PRICE_CACHE
        + usage.get("completion_tokens", 0) * PRICE_OUT
    ) / 1_000_000


def build_row(task: dict, summary: dict, usd: float) -> dict:
    """Строка результата по задаче: ответ, pass-статус считает вызывающий
    (нужен scorer), шаги бюджета и флаг best-effort — из вывода агента.
    best_effort по умолчанию False, steps_budget откатывается на steps,
    если агент их не отдал (совместимость со старыми трассами)."""
    steps = summary.get("steps", 0)
    return {
        "task_id": task["task_id"],
        "level": task["level"],
        "question": task["question"],
        "gold": task["answer"],
        "answer": summary.get("answer", ""),
        "steps": steps,
        "steps_budget": summary.get("steps_budget", steps),
        "best_effort": bool(summary.get("best_effort", False)),
        "usage": summary.get("usage", {}),
        "usd": round(usd, 4),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run.py")
    parser.add_argument("--data", required=True, help="каталог с context-файлами")
    parser.add_argument("--tasks", required=True, help="JSON с задачами (dev-сплит)")
    parser.add_argument("--out", required=True, help="каталог результатов")
    args = parser.parse_args(argv)

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении", file=sys.stderr)
        return EXIT_USAGE
    data_dir = Path(args.data)
    tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
    if not tasks:
        print("список задач пуст", file=sys.stderr)
        return EXIT_USAGE

    sys.path.insert(0, str(HERE))
    from scorer import question_scorer  # noqa: E402

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manual = data_dir / "manual.md"

    rows = []
    total_usd = 0.0
    for task in tasks:
        trace_path = out_dir / f"trace-{task['task_id']}.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(HERE / "agent.py"),
                "--data", str(data_dir),
                "--question", task["question"],
                "--guidelines", task["guidelines"],
                "--manual", str(manual),
                "--out", str(trace_path),
            ],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        try:
            summary = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            summary = {"answer": "", "steps": 0, "usage": {}}
        answer = summary.get("answer", "")
        usage = summary.get("usage", {})
        usd = estimate_usd(usage)
        total_usd += usd
        passed = question_scorer(answer, task["answer"]) if answer else False
        rows.append(build_row(task, summary, usd))
        rows[-1]["pass"] = passed
        print(f"[{task['task_id']}] {task['level']:4s} pass={passed} ans={answer[:60]!r} ${usd:.3f}")

    passed_n = sum(1 for r in rows if r["pass"])
    result = {
        "benchmark": "DABstep (adyen/HuggingFace, CC-BY-4.0)",
        "split": "dev (10 задач, официальные эталонные ответы)",
        "model": os.environ.get("DABSTEP_MODEL", "step-5-preview"),
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "passed": passed_n,
        "total": len(rows),
        "accuracy": round(passed_n / len(rows), 3),
        "best_effort_answers": sum(1 for r in rows if r["best_effort"]),
        "total_usd": round(total_usd, 3),
        "rows": rows,
    }
    (out_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# DABstep (dev) — прогон на step-5 (стенд О4)",
        "",
        f"Дата (UTC): {result['date_utc']}",
        f"Артефакт прогона: `{out_dir}/results.json`",
        "(полные трассы — `trace-*.json` того же каталога).",
        f"Модель: {result['model']}",
        f"Итог: {passed_n}/{len(rows)} (accuracy {result['accuracy']:.1%}), стоимость ${total_usd:.2f}",
        f"Best-effort ответов (шаги исчерпаны): {result['best_effort_answers']}",
        "",
        "## Результаты",
        "",
        "Числа — из `results.json` и `trace-*.json` этого каталога.",
        "",
        "| task | level | ответ агента | эталон | pass | шагов (бюджет) | best-effort | $ |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        ans = (r["answer"] or "—").replace("|", "\\|")[:40]
        gold = str(r["gold"]).replace("|", "\\|")[:40]
        lines.append(
            f"| {r['task_id']} | {r['level']} | {ans} | {gold} | "
            f"{'да' if r['pass'] else 'нет'} | {r['steps_budget']} | "
            f"{'да' if r['best_effort'] else '—'} | {r['usd']:.3f} |"
        )
    (out_dir / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"итог: {passed_n}/{len(rows)}, ${total_usd:.2f}, результаты: {out_dir}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
