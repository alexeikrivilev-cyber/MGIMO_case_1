#!/usr/bin/env python3
"""ablation_stats.py — статистика абляции слоёв (TASK-hermes-10 §23.1).

Считает по артефакту `eval/score_ablation.py` (scores/summary.json):
- баллы рук L0–L4 под обеими рубриками;
- Δ к базе (L0) и Δ соседних слоёв с доверительными интервалами;
- MDD из ИЗМЕРЕННОГО шума судьи (типовая σ=1.03 n=6 §21.2; единая
  σ=1.41 n=2 §12.1) при мощности 0.8, α=0.05 — переиспользуем
  `critic_step4_power` (та же модель, что §22.1/§22.2);
- требуемое k для наблюдаемых Δ (таблица мощности);
- вердикт по каждой соседней паре и ответ на вопрос ТЗ «какой слой
  оправдывает сложность» с маржой $/run.

Ограничение названо в предрегистрации (§23.1): n=1 на руку, интервалы
покрывают только шум судьи — MDD есть НИЖНЯЯ граница порога
(генерационная дисперсия не измерена). Все вердикты — suggestive.

Контракт CLI:
    python3 eval/ablation_stats.py [--runs-dir DIR] [--out DIR]

Коды возврата: 0 — расчёт завершён; 2 — ошибка использования.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from critic_step4_power import (  # noqa: E402
    ALPHA,
    POWER,
    mdd_at,
    power_one_sample_t,
    required_k,
)

EXIT_OK = 0
EXIT_USAGE = 2

Z_975 = 1.959963984540054
Z_080 = 0.8416212335729143  # z_{0.80}

# Измеренный шум судьи (§21.2 типовая: 6 прогонов одного артефакта;
# §12.1 единая: 2 наблюдения — оценка слабая, названа).
NOISE = {
    "typical": {"sd": 1.03, "n_obs": 6, "source": "measurements.md §21.2 (36/38/38/38/36/38)"},
    "unified": {"sd": 1.41, "n_obs": 2, "source": "measurements.md §12.1 (22/20 — оценка слабая)"},
}

ARMS = ("L0", "L1", "L2", "L3", "L4")
ADJACENT_PAIRS = (("L0", "L1"), ("L1", "L2"), ("L2", "L3"), ("L3", "L4"))


def mdd_two_arm(n: int, sigma: float) -> float:
    """MDD разности двух рук при n наблюдениях на руку (как mdd_recompute)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if n == 1:
        return (Z_975 + Z_080) * sigma * math.sqrt(2.0)  # z-аппроксимация, теста нет
    lo, hi = 0.0, 60.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if power_one_sample_t(mid, sigma * math.sqrt(2.0), n) >= POWER:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def verdict(delta: float, mdd: float) -> str:
    a = abs(delta)
    if a >= mdd:
        return "выше шума"
    if a >= 0.75 * mdd:
        return "НА ГРАНИЦЕ"
    return "нет отличимого различия"


def load_scores(runs_dir: Path) -> list[dict]:
    path = runs_dir / "scores" / "summary.json"
    if not path.is_file():
        raise FileNotFoundError(f"не найден {path} — сначала eval/score_ablation.py")
    return json.loads(path.read_text(encoding="utf-8"))["runs"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ablation_stats.py",
        description="Статистика абляции: Δ слоёв, MDD из измеренного шума, мощности, вердикты.",
    )
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "eval" / "runs" / "t10-ablation"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    out_dir = Path(args.out) if args.out else runs_dir
    runs = load_scores(runs_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Статистика абляции слоёв L0–L4 (TASK-hermes-10 §23.1)")
    lines.append("")
    lines.append("Драйвер: `eval/ablation_stats.py` (API-вызовов нет). α = 0.05")
    lines.append("(двусторонний), мощность 0.8. Модель шума — та же, что §22.1/§22.2.")
    lines.append("")
    lines.append("## 1. Измеренный шум судьи и пересчитанный MDD")
    lines.append("")
    lines.append("| Рубрика | sd | n наблюдений | Источник | MDD(n=1, z-апп.) | MDD(n=2) | MDD(n=4) |")
    lines.append("|---|---|---|---|---|---|---|")
    for key, spec in NOISE.items():
        lines.append(
            f"| {key} | {spec['sd']} | {spec['n_obs']} | {spec['source']} "
            f"| {mdd_two_arm(1, spec['sd']):.2f} | {mdd_two_arm(2, spec['sd']):.2f} | {mdd_two_arm(4, spec['sd']):.2f} |"
        )
    lines.append("")
    lines.append("При n=1 на руку теста не существует — порог z-аппроксимации.")
    lines.append("Интервал Δ между руками: ±1.96·σ·√2 (типовая ±2.86, единая ±3.92).")
    lines.append("Генерационная дисперсия (n=1 на руку) в интервалы НЕ входит —")
    lines.append("MDD есть нижняя граница истинного порога (ограничение §23.1).")
    lines.append("")

    payload: dict = {"noise": NOISE, "tasks": {}}
    for task in ("demo", "heldout"):
        lines.append(f"## 2. Задача {task}")
        lines.append("")
        by_arm = {r["arm"]: r for r in runs if r.get("task") == task}
        for rubric in ("unified", "typical"):
            sd = NOISE[rubric]["sd"]
            mdd1 = mdd_two_arm(1, sd)
            lines.append(f"### Рубрика {rubric} (sd {sd})")
            lines.append("")
            lines.append("| Рука | Балл /40 | Δ к L0 | Вердикт Δ к L0 | Требуемое k для Δ (мощность 0.8) |")
            lines.append("|---|---|---|---|---|")
            base = by_arm.get("L0", {}).get(rubric, {}).get("total40")
            scores: dict[str, float] = {}
            for arm in ARMS:
                value = by_arm.get(arm, {}).get(rubric, {}).get("total40")
                if value is None:
                    lines.append(f"| {arm} | — | — | — | — |")
                    continue
                scores[arm] = value
                if base is None:
                    lines.append(f"| {arm} | {value} | — | — | — |")
                    continue
                delta = value - base
                need_k = required_k(delta, sd * math.sqrt(2.0)) if delta > 0 else None
                lines.append(
                    f"| {arm} | {value} | {delta:+.1f} | {verdict(delta, mdd1)} "
                    f"| {need_k if need_k else '—'} |"
                )
            lines.append("")
            lines.append("Соседние пары (Δ слоя):")
            lines.append("")
            lines.append("| Пара | Δ | Интервал ±1.96σ√2 | Вердикт |")
            lines.append("|---|---|---|---|")
            for lo, hi in ADJACENT_PAIRS:
                if lo in scores and hi in scores:
                    delta = scores[hi] - scores[lo]
                    lines.append(
                        f"| {lo}→{hi} | {delta:+.1f} | ±{1.96 * sd * math.sqrt(2.0):.2f} "
                        f"| {verdict(delta, mdd1)} |"
                    )
            lines.append("")
            payload.setdefault("tasks", {}).setdefault(task, {})[rubric] = scores
        lines.append("")

    # 3. Итог по вопросу ТЗ: какие соседние пары дают прирост на обеих задачах.
    lines.append("## 3. Ответ на вопрос ТЗ: какая прослойка даёт прирост")
    lines.append("")
    lines.append("Вердикт пары — «выше шума», только если Δ ≥ MDD хотя бы на одной")
    lines.append("задаче (n=1 на руку; парные вердикты — suggestive).")
    lines.append("")
    lines.append("| Пара | демо (единая / типовая) | held-out (единая / типовая) | Чтение |")
    lines.append("|---|---|---|---|")
    for lo, hi in ADJACENT_PAIRS:
        cells = []
        for task in ("demo", "heldout"):
            parts = []
            for rubric in ("unified", "typical"):
                scores = payload["tasks"].get(task, {}).get(rubric, {})
                if lo in scores and hi in scores:
                    parts.append(f"{scores[hi] - scores[lo]:+.1f} {verdict(scores[hi] - scores[lo], mdd_two_arm(1, NOISE[rubric]['sd']))}")
                else:
                    parts.append("—")
            cells.append(" / ".join(parts))
        lines.append(f"| {lo}→{hi} | {cells[0]} | {cells[1]} | (интерпретация — в отчёте) |")
    lines.append("")

    # 4. $/run и маржа сложности.
    lines.append("## 4. $/run слоёв (маржа сложности)")
    lines.append("")
    lines.append("| Задача | Рука | $/run (сессии) | Источник |")
    lines.append("|---|---|---|---|")
    for r in runs:
        cost = r.get("cost", {})
        usd = cost.get("usd", cost.get("step3_usd"))
        sessions = cost.get("sessions", "—")
        source = cost.get("source", "—")
        lines.append(f"| {r['task']} | {r['arm']} | {usd} ({sessions}) | {source} |")
    lines.append("")
    lines.append("L4: step3 — сессия шага 3 продукта (хук COST.md); полный путь —")
    lines.append("§19.4 (council-on). Сравнение «один артефакт шага 3» vs «полный")
    lines.append("путь» названо: они измеряют разное (как в B11 §19.4).")
    lines.append("")

    (out_dir / "ablation-stats.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "ablation-stats.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"артефакт: {out_dir / 'ablation-stats.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
