#!/usr/bin/env python3
"""dabstep_power.py — дизайн эксперимента DABstep под измеренный шум
(TASK-hermes-8 §2, итерация В; предрегистрация — measurements.md §21.1-В).

Вопрос задачи: шум ±2 задачи dominates — сколько прогонов нужно для
обнаружения дельта в 1 задачу, и стоит ли вообще использовать этот
стенд как рычаг (или честный вывод «не наш инструмент»).

Вход: 4 имеющихся прогона dev-10 (results.json), без новых API-вызовов.
Модели шума:
  1. Эмпирика повтора: один и тот же агент на тех же задачах даёт
     разброс счёта (база: 7 и 5; улучшенный: 5 и 5).
  2. Биномиальная модель: счёт = сумма 10·Bernoulli(p), σ = sqrt(n·p·(1−p)).
     Оценка p — по всем наблюдениям (40 task-прогонов).
  3. Per-task стабильность: доля флипов pass/fail между прогонами.
Требуемое число прогонов на руку (двусторонний α=0.05, мощность 0.8,
две независимые руки): n = 2·(z_{α/2}+z_β)²·σ²/Δ². Стоимость — средняя
цена прогона по 4 имеющимся (~$1/run).

Контракт CLI:
    python3 eval/dabstep_power.py [--runs-dir DIR] [--out DIR]

Коды возврата: 0 — отчёт построен; 2 — прогонов не найдено.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_USAGE = 2

DEFAULT_RUNS = REPO_ROOT / "eval" / "benchmarks" / "dstep-placeholder"  # не используется
DEFAULT_RUNS = REPO_ROOT / "eval" / "benchmarks" / "dabstep" / "runs"
DEFAULT_OUT = REPO_ROOT / "eval" / "runs" / "t8-evidence"

# Именованные прогоны (dev-10) с датами и конфигурациями агента.
RUNS = [
    ("2026-11-16-dev10", "r1 база"),
    ("2026-11-17-t7-run2", "r2 улучшенный"),
    ("2026-11-17-t7-run3-improved", "r3 улучшенный (повтор)"),
    ("2026-11-17-t7-run4-baseline", "r4 база (повтор)"),
]

# Конфигурация прогона: (порядковый номер, рука). Рука «base» или
# «improved» — по протоколу TASK-hermes-7 §20.4.
ARM_OF_RUN = {
    "2026-11-16-dev10": "base",
    "2026-11-17-t7-run2": "improved",
    "2026-11-17-t7-run3-improved": "improved",
    "2026-11-17-t7-run4-baseline": "base",
}

Z_ALPHA = 1.959964  # двусторонний α=0.05
Z_BETA = 0.841621   # мощность 0.8


def load_runs(runs_dir: Path) -> list[dict]:
    runs = []
    for name, label in RUNS:
        path = runs_dir / name / "results.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("rows", [])
        runs.append({
            "name": name,
            "label": label,
            "arm": ARM_OF_RUN.get(name, "?"),
            "passed": data.get("passed"),
            "total": data.get("total", len(rows)),
            "usd": data.get("total_usd"),
            "per_task": {str(r["task_id"]): bool(r["pass"]) for r in rows},
        })
    return runs


def analyze(runs: list[dict]) -> dict:
    scores = {(r["arm"], r["name"]): r["passed"] for r in runs}
    by_arm: dict[str, list[int]] = {}
    for (arm, _), passed in scores.items():
        by_arm.setdefault(arm, []).append(passed)

    # Все наблюдения task×run для оценки p и флипов.
    task_ids = sorted({t for r in runs for t in r["per_task"]})
    observations = [(tid, r["per_task"][tid]) for r in runs for tid in task_ids]
    total_obs = len(observations)
    total_pass = sum(1 for _, ok in observations if ok)
    p_hat = total_pass / total_obs if total_obs else 0.5

    # Флипы: число пар прогонов, где задача сменила результат.
    flips = 0
    pairs = 0
    for i, a in enumerate(runs):
        for b in runs[i + 1:]:
            for tid in task_ids:
                pairs += 1
                if a["per_task"][tid] != b["per_task"][tid]:
                    flips += 1
    flip_rate = flips / pairs if pairs else 0.0

    # Эмпирический разброс повтора внутри руки (|Δ| между прогонами).
    repeat_gaps = []
    for arm, values in by_arm.items():
        if len(values) >= 2:
            for i, a in enumerate(values):
                for b in values[i + 1:]:
                    repeat_gaps.append(abs(a - b))

    n_tasks = runs[0]["total"] if runs else 10
    sigma_binom = math.sqrt(n_tasks * p_hat * (1 - p_hat))

    # Требуемое число прогонов на руку для дельта Δ (две руки).
    required = {}
    for delta in (1, 2, 3):
        n = 2 * (Z_ALPHA + Z_BETA) ** 2 * sigma_binom ** 2 / delta ** 2
        required[delta] = math.ceil(n)

    prices = [r["usd"] for r in runs if r["usd"]]
    mean_price = statistics.mean(prices) if prices else 0.0

    return {
        "runs": [
            {"name": r["name"], "label": r["label"], "arm": r["arm"],
             "passed": r["passed"], "usd": r["usd"]}
            for r in runs
        ],
        "by_arm": by_arm,
        "observations": total_obs,
        "pass_observed": total_pass,
        "p_hat": p_hat,
        "flips": flips,
        "pairs": pairs,
        "flip_rate": flip_rate,
        "repeat_gaps": repeat_gaps,
        "n_tasks": n_tasks,
        "sigma_binomial": sigma_binom,
        "required_runs_per_arm": required,
        "mean_price_per_run": mean_price,
        "task_ids": task_ids,
    }


def render(result: dict) -> str:
    lines = [
        "# DABstep: дизайн эксперимента под измеренный шум (TASK-hermes-8 §2)",
        "",
        f"- Дата (UTC): {datetime.now(timezone.utc).isoformat()}",
        "- Вход: 4 прогона dev-10 (`eval/benchmarks/dabstep/runs/*/results.json`),",
        "  новых API-вызовов нет.",
        "",
        "## Наблюдения",
        "",
        "| Прогон | Рука | Счёт /10 | $ |",
        "|---|---|---|---|",
    ]
    for r in result["runs"]:
        lines.append(f"| {r['label']} | {r['arm']} | {r['passed']} | {r['usd']} |")
    lines += [
        "",
        "## Шум",
        "",
        f"- Повторы внутри руки: {result['by_arm']} — эмпирические "
        f"разрывы повтора: {result['repeat_gaps'] or 'нет пар'}.",
        f"- Наблюдений task×run: {result['observations']}, pass: "
        f"{result['pass_observed']} → p̂ = {result['p_hat']:.3f}.",
        f"- Флипы задачи между прогонами: {result['flips']} из "
        f"{result['pairs']} пар ({result['flip_rate']:.1%}) — при "
        "temperature 0 это nondeterminism провайдера/стенда, не агента.",
        f"- Биномиальный σ счёта (n={result['n_tasks']}, p̂="
        f"{result['p_hat']:.2f}): {result['sigma_binomial']:.2f} задачи.",
        "",
        "## Сколько прогонов нужно на руку (α=0.05, мощность 0.8, две руки)",
        "",
        "| Δ (задачи) | Прогонов на руку | Обе руки, шт | Стоимость ~$ |",
        "|---|---|---|---|",
    ]
    for delta, n in result["required_runs_per_arm"].items():
        cost = 2 * n * result["mean_price_per_run"]
        lines.append(f"| {delta} | {n} | {2 * n} | ~${cost:.0f} |")
    lines += [
        "",
        f"Средняя цена прогона по 4 имеющимся: "
        f"${result['mean_price_per_run']:.2f}.",
        "",
        "## Вердикт (по предрегистрации §21.1-В)",
        "",
    ]
    n1 = result["required_runs_per_arm"][1]
    cost1 = 2 * n1 * result["mean_price_per_run"]
    lines += [
        f"Для обнаружения Δ=1 задача нужно ~{n1} прогонов на руку "
        f"(~${cost1:.0f} за эксперимент) — при эффектах промпта, "
        "которые этот стенд измерял (best-effort, применимость — "
        "порядка 0–2 задач), стенд НЕ является рычагом: требуемый "
        "бюджет на порядок выше ночной очереди, а measured-эффекты "
        "меньше обнаружимой дельты. Δ=2 задачи (~"
        f"{result['required_runs_per_arm'][2]} прогонов на руку) — "
        "пограничный случай; Δ=3 — единственное, что стенд ловит "
        "за разумные деньги.",
        "",
        "Честный вывод по условию задачи: **DABstep dev-10 — не наш "
        "инструмент для итераций промпта.** Остаётся как smoke-тест "
        "(«агент вообще решает задачи») и как источник разбора "
        "failure modes. Путь к сигналу — больший золотой сплит, "
        "которого публично нет (10 задач с эталонами; default-сплит "
        "450 без ответов — именованный пробел, факт HF size API).",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dabstep_power.py",
        description="Дизайн эксперимента DABstep под измеренный шум (аналитически).",
    )
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    runs_dir = Path(args.runs_dir)
    runs = load_runs(runs_dir)
    if not runs:
        print(f"прогонов не найдено в {runs_dir}", file=sys.stderr)
        return EXIT_USAGE
    result = analyze(runs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dabstep-power.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    text = render(result)
    (out_dir / "dabstep-power.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"отчёт: {out_dir / 'dabstep-power.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
