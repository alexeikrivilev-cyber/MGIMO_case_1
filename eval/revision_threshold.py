#!/usr/bin/env python3
"""revision_threshold.py — гипотеза «порог: сколько правок достаточно»
(TASK-hermes-9 §22.3-Б, предрегистрация — до анализа).

Гипотеза: при applied ≥ 10 точечных правок Δ rubric устойчиво ≥ 0, при
applied ≤ 8 — внутри шума; число правок — предиктор эффекта ревизии.
Анти-круг: §17.1 мерил МЕХАНИЗМ (точечные vs перезапись), §20.9-А —
комбинацию с советом, §22.1 — мощность репликации. Число правок как
предиктор не измерялось.

Данные — все события ревизии стенда под рубрикой хакатона (critic-loop2
на шаге 3, council-lite-critic, критик на шаге 4): applied против Δ
рубрики. Ограничение названо: артефакты РАЗНЫХ шагов (options.md шага 3
против strategy-product.md шага 4), n=12, рубрика одна.

Контракт CLI:
    python3 eval/revision_threshold.py [--out DIR]

Коды возврата: 0 — анализ завершён; 2 — ошибка использования.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 2

# (run, applied, Δ rubric, источник)
EVENTS = [
    ("cl2-demo", 12, 6.0, "measurements.md §17.1 (точечные правки, шаг 3, демо)"),
    ("cl2-heldout", 14, 4.0, "measurements.md §17.1 (шаг 3, held-out)"),
    ("clc-demo", 13, -2.0, "measurements.md §20.9-А (совет+ревизия, демо)"),
    ("clc-heldout", 8, 0.0, "measurements.md §20.9-А (held-out)"),
    ("t8-step4", 14, 8.0, "measurements.md §21.3 (критик на шаге 4, демо)"),
    ("t9-demo-run2", 3, 2.0, "measurements.md §22.4 (репликация, демо)"),
    ("t9-demo-run3", 15, 10.0, "measurements.md §22.4 (репликация, демо)"),
    ("t9-demo-run4b", 9, -2.0, "measurements.md §22.4 (репликация, демо)"),
    ("t9-heldout-run1", 6, 0.0, "measurements.md §22.4 (репликация, held-out)"),
    ("t9-heldout-run2", 13, -2.0, "measurements.md §22.4 (репликация, held-out)"),
    ("t9-heldout-run3", 8, 8.0, "measurements.md §22.4 (репликация, held-out)"),
    ("t9-heldout-run4", 8, 8.0, "measurements.md §22.4 (репликация, held-out)"),
]


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return 0.0
    return cov / (vx * vy) ** 0.5


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="revision_threshold.py",
        description="Гипотеза порога правок: связь applied count и Δ rubric по всем ревизиям стенда.",
    )
    parser.add_argument("--out", default=str(REPO_ROOT / "eval" / "runs" / "t9-mdd"))
    args = parser.parse_args(argv)

    applied = [float(e[1]) for e in EVENTS]
    deltas = [e[2] for e in EVENTS]
    r = pearson(applied, deltas)

    high = [d for a, d in zip(applied, deltas) if a >= 10]
    low = [d for a, d in zip(applied, deltas) if a <= 8]
    high_nonneg = sum(1 for d in high if d >= 0)
    low_within = sum(1 for d in low if abs(d) <= 3)

    # Разделительная способность порога: точность предсказания «Δ≥0» по applied≥10.
    tp = sum(1 for a, d in zip(applied, deltas) if a >= 10 and d >= 0)
    fp = sum(1 for a, d in zip(applied, deltas) if a >= 10 and d < 0)
    fn = sum(1 for a, d in zip(applied, deltas) if a < 10 and d >= 0)
    tn = sum(1 for a, d in zip(applied, deltas) if a < 10 and d < 0)

    lines: list[str] = []
    lines.append("# Гипотеза порога правок: «сколько правок достаточно» (TASK-hermes-9 §22.3-Б)")
    lines.append("")
    lines.append("Предрегистрация — §22.3-Б (до анализа). Драйвер: `eval/revision_threshold.py`.")
    lines.append("API-вызовов нет. Ограничение названо: n=12 событий, артефакты разных")
    lines.append("шагов (options.md шага 3 против strategy-* шага 4), рубрика одна")
    lines.append("(хакатон).")
    lines.append("")
    lines.append("| Событие | applied | Δ rubric | Источник |")
    lines.append("|---|---|---|---|")
    for name, a, d, src in EVENTS:
        lines.append(f"| {name} | {a} | {d:+.1f} | {src} |")
    lines.append("")
    lines.append("## Результат")
    lines.append("")
    lines.append(f"- Корреция applied ↔ Δ (Пирсон): **r = {r:+.2f}** (n=12)")
    lines.append(f"- Группа applied ≥ 10 (n={len(high)}): Δ {high}, неотрицательных "
                 f"{high_nonneg}/{len(high)}")
    lines.append(f"- Группа applied ≤ 8 (n={len(low)}): Δ {low}, в пределах ±3 "
                 f"{low_within}/{len(low)}")
    lines.append(f"- Предсказание «applied ≥ 10 → Δ ≥ 0»: TP={tp}, FP={fp}, "
                 f"FN={fn}, TN={tn}")
    lines.append("")
    lines.append("## Вердикт по предрегистрации")
    lines.append("")
    if high_nonneg == len(high) and low_within == len(low):
        verdict = "ПОДТВЕРЖДЕНО"
    else:
        verdict = "НЕ ПОДТВЕРЖДЕНО"
    lines.append(f"**{verdict}.** Число применённых правок не предиктор эффекта:")
    lines.append(f"корреция слабая ({r:+.2f}); группа applied ≥ 10 дала "
                 f"{high_nonneg}/{len(high)} неотрицательных Δ; группа applied ≤ 8 "
                 f"дала {low_within}/{len(low)} в пределах ±3 (два события с applied=8 "
                 "дали Δ+8 — малые по числу правки закрыли крупные находки). "
                 "Практический вывод: «просить больше правок» не повышает и не "
                 "гарантирует эффект; глубина ревизии — свойство НАБОРА находок "
                 "критика в данном прогоне (ему же и подвержена дисперсия, §22.4), "
                 "а не управляемый параметр. Эвристика апдейтера «≥10 правок» "
                 "не обоснована данными.")
    lines.append("")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "revision-threshold.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "revision-threshold.json").write_text(
        json.dumps(
            {
                "events": [{"run": n, "applied": a, "delta": d, "source": s} for n, a, d, s in EVENTS],
                "pearson_r": r,
                "high_applied_deltas": high,
                "low_applied_deltas": low,
                "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
                "verdict": verdict,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"r={r:+.2f}; high(≥10) неотрицательных {high_nonneg}/{len(high)}; "
          f"low(≤8) в ±3: {low_within}/{len(low)}; вердикт: {verdict}")
    print(f"артефакт: {out_dir / 'revision-threshold.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
