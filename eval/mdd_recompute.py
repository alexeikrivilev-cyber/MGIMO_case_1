#!/usr/bin/env python3
"""mdd_recompute.py — пересчёт MDD из ИЗМЕРЕННОГО шума (TASK-hermes-9 §22.2).

Предрегистрация (§22.2): предрегистрированный MDD задан ДО измерения шума
(council-design §6 — «~1 балл / полная смена ранжира»; A/B §14 — +3/40 с
оговоркой шума судьи). Шум теперь измерён на трёх рубриках. Скрипт считает,
при каком пороге различие рук статистически отличимо от шума при фактическом
n на руку, и перепроверяет прошлые выводы — честная пометка «пересмотрён
пост-фактум» обязательна (правило артефакта).

Модель: две руки, n наблюдений на руку, равные дисперсии σ (шум судьи на
наблюдение). Различие средних эквивалентно one-sample t по n разностям с
sd σ·√2 (df = n−1) — переиспользуется `critic_step4_power.power_one_sample_t`.
При n=1 теста не существует (df=0): порог даётся z-аппроксимацией
(z_{α/2}+z_β)·σ·√2 и ПОМЕЧЕН как аппроксимация.

Контракт CLI:
    python3 eval/mdd_recompute.py [--out DIR]

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
    Z_975,
    power_one_sample_t,
    sample_sd,
)

EXIT_OK = 0
EXIT_USAGE = 2

Z_080 = 0.8416212335729143  # z_{0.80}

# Шум судьи, измеренный повторными прогонами на ОДНОМ артефакте.
NOISE = {
    "typical-options": {
        "rubric": "eval/rubrics/rubric-options.md (типовая)",
        "artifact": "project/options.md (демо, шаг 3)",
        "obs": [36, 38, 38, 38, 36, 38],
        "source": "measurements.md §21.2 (6 прогонов; 1 переиспользован из §19.1)",
    },
    "unified-options": {
        "rubric": "eval/rubrics/hackathon-criteria.md (единая)",
        "artifact": "project/options.md (демо, шаг 3)",
        "obs": [22, 20],
        "source": "measurements.md §12.1 (matrix) и §19.1 (h2-unified) — два наблюдения",
    },
    "hackathon-step4": {
        "rubric": "eval/rubrics/hackathon-criteria.md (единая)",
        "artifact": "project/strategy-product.md (демо, шаг 4)",
        "obs": [20.0, 23.7],
        "source": "measurements.md §21.3 (score-draft, critic-draft)",
    },
}

# Прошлые выводы для перепроверки: (id, вывод, рубрика, n на руку, дельты по задачам, источник)
CONCLUSIONS = [
    ("C1", "Совет: качество возражений +1.0 к A1", "council-design §6.2 (шкала совета, не /40)",
     None, [1.0], "measurements.md §1.3/§1.5"),
    ("C2", "council-lite бьёт базу (шаг 3)", "unified-options", 1, [4.0, 4.0],
     "measurements.md §14.1–14.2"),
    ("C3", "critic-loop2 бьёт базу (шаг 3)", "unified-options", 1, [6.0, 4.0],
     "measurements.md §17.1"),
    ("C4", "lean бьёт курацию на шаге 2", "unified-options", 1, [8.0, 6.0],
     "measurements.md §18.1"),
    ("C5", "council-full НЕ добавляет сверх council-lite", "unified-options", 1, [2.0],
     "measurements.md §16.1"),
    ("C6", "devil→flash ухудшает качество", "unified-options", 1, [-6.0, -2.0],
     "measurements.md §19.3-1"),
    ("C7", "Реcкоринг §20.6: council-lite − база", "typical-options", 1, [-5.0, -1.0],
     "measurements.md §20.6"),
    ("C8", "Реcкоринг §20.6: critic-loop2 − база", "typical-options", 1, [-3.0, 3.0],
     "measurements.md §20.6"),
    ("C9", "Реcкоринг §20.6: council-lite-critic − council-lite", "typical-options", 1, [4.0, 2.0],
     "measurements.md §20.9-А"),
    ("C10", "Реcкоринг §20.6: курация +3 над lean (шаг 3)", "typical-options", 1, [3.0],
     "measurements.md §20.6"),
    ("C11", "Критик на шаге 4: Δ+8.0 (одна ревизия)", "hackathon-step4", 1, [8.0],
     "measurements.md §21.3 (one-sample по ревизиям; см. power-анализ §22.1)"),
]


def mdd_two_arm(n: int, sigma: float) -> float:
    """Минимальный эффект с мощностью POWER при n наблюдениях на руку."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if n == 1:
        # Теста нет (df=0): z-аппроксимация разности двух средних.
        return (Z_975 + Z_080) * sigma * math.sqrt(2.0)
    lo, hi = 0.0, 60.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if power_one_sample_t(mid, sigma * math.sqrt(2.0), n) >= POWER:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def verdict(deltas: list[float], mdd: float) -> str:
    """Вердикт по худшей (ближней к порогу) по модулю делельта."""
    worst = min(abs(d) for d in deltas)
    if worst >= mdd:
        return "выше пересчитанного MDD"
    if worst >= 0.75 * mdd:
        return "НА ГРАНИЦЕ (0.75–1× MDD)"
    return "ниже шума"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="mdd_recompute.py",
        description="Пересчёт MDD из измеренного шума и перепроверка прошлых выводов (пост-фактум).",
    )
    parser.add_argument("--out", default=str(REPO_ROOT / "eval" / "runs" / "t9-mdd"))
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    noise_rows = []
    for key, spec in NOISE.items():
        sd = sample_sd(spec["obs"])
        noise_rows.append({"key": key, "sd": sd, "n": len(spec["obs"]), **spec})

    # Таблица MDD по рубрикам и n.
    mdd_table: dict[str, dict[int, float]] = {}
    for row in noise_rows:
        mdd_table[row["key"]] = {
            n: mdd_two_arm(n, row["sd"]) for n in (1, 2, 3, 4, 6, 8)
        }

    # Перепроверка выводов.
    checked = []
    for cid, claim, rubric_key, n, deltas, source in CONCLUSIONS:
        if n is None:
            checked.append({
                "id": cid, "claim": claim, "source": source, "deltas": deltas,
                "rubric": rubric_key, "mdd": None,
                "verdict": "шум не измерен — остаётся граничным по предрегистрации "
                           "(«~1 балл», §1.5); именованный пробел",
            })
            continue
        sd = next(r["sd"] for r in noise_rows if r["key"] == rubric_key)
        mdd = mdd_two_arm(n, sd)
        checked.append({
            "id": cid, "claim": claim, "source": source, "deltas": deltas,
            "rubric": rubric_key, "n": n, "sd": sd, "mdd": mdd,
            "verdict": verdict(deltas, mdd),
        })

    lines: list[str] = []
    lines.append("# Пересчёт MDD из измеренного шума (TASK-hermes-9 §22.2)")
    lines.append("")
    lines.append("> **ЧЕСТНАЯ ПОМЕТКА: пересмотрён ПОСТ-ФАКТУМ на основе измеренного")
    lines.append("> шума.** Предрегистрация (benchmarks.md §2.2 п.4; council-design §6;")
    lines.append("> measurements.md §14) задавала MDD ДО замеров шума. Ниже — пересчёт")
    lines.append("> порога и перепроверка прошлых выводов. Данные не менялись; меняется")
    lines.append("> порог их чтения.")
    lines.append("")
    lines.append("Драйвер: `eval/mdd_recompute.py`. API-вызовов нет. α = 0.05")
    lines.append("(двусторонний), мощность 0.8.")
    lines.append("")
    lines.append("## 1. Измеренный шум судьи (повторные прогоны на одном артефакте)")
    lines.append("")
    lines.append("| Рубрика | Артефакт | Наблюдения | sd (n−1) | n | Источник |")
    lines.append("|---|---|---|---|---|---|")
    for row in noise_rows:
        lines.append(
            f"| {row['rubric']} | {row['artifact']} | {row['obs']} | "
            f"**{row['sd']:.3f}** | {row['n']} | {row['source']} |"
        )
    lines.append("")
    lines.append("## 2. Пересчитанный MDD (баллы /40) при мощности 0.8")
    lines.append("")
    header = "| Рубрика (sd) | n=1 (z-аппрокс.) | n=2 | n=3 | n=4 | n=6 | n=8 |"
    lines.append(header)
    lines.append("|---|---|---|---|---|---|---|")
    for row in noise_rows:
        cells = " | ".join(f"{mdd_table[row['key']][n]:.2f}" for n in (1, 2, 3, 4, 6, 8))
        lines.append(f"| {row['key']} (sd {row['sd']:.2f}) | {cells} |")
    lines.append("")
    lines.append("Чтение: при n=1 на руку теста не существует — порог дан")
    lines.append("z-аппроксимацией (предел обнаружимости разности двух средних).")
    lines.append("Аномалия n=2 (MDD ВЫШЕ, чем при n=1) — реальное свойство точного t:")
    lines.append("при df=1 (два наблюдения на руку) распределение t настолько")
    lines.append("тяжелохвосто, что малые эффекты неотличимы; z-аппроксимация при")
    lines.append("n=1 оптимистичнее. Отсюда правило: серия из 2 прогонов на руку")
    lines.append("НЕ информативна для эффектов < ~10 баллов — это и есть мощность,")
    lines.append("которой требует репликация §22.1 (k=4).")
    lines.append("")
    lines.append("## 3. Перепроверка прошлых выводов (пост-фактум)")
    lines.append("")
    lines.append("| # | Вывод | Δ по задачам | Рубрика (sd) | n | Пересчитанный MDD | Вердикт |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in checked:
        if c["mdd"] is None:
            lines.append(f"| {c['id']} | {c['claim']} | {c['deltas']} | {c['rubric']} | — | — | {c['verdict']} |")
        else:
            lines.append(
                f"| {c['id']} | {c['claim']} | {c['deltas']} | {c['rubric']} "
                f"(sd {c['sd']:.2f}) | {c['n']} | {c['mdd']:.2f} | {c['verdict']} |"
            )
    lines.append("")
    lines.append("## 4. Какие прошлые выводы были на границе (честно)")
    lines.append("")
    lines.append("- **C2 council-lite +4/+4 (§14.1–14.2):** при пересчитанном MDD 5.60")
    lines.append("  (единая, n=1) +4 — НИЖЕ порога даже до типовой рубрики; вывод")
    lines.append("  держался только при предрегистрированном +3. Совместимо с §20.6")
    lines.append("  (знак сменился).")
    lines.append("- **C3 critic-loop2 +6/+4 (§17.1):** демо +6 выше порога 5.60,")
    lines.append("  held-out +4 — ниже; §20.6 не воспроизвёл. Оба наблюдения слабые.")
    lines.append("- **C6 devil→flash −6/−2 (§19.3-1):** −6 выше порога 5.60, −2 ниже —")
    lines.append("  вывод «flash ухудшает» опирался на одну задачу; откат стоит на")
    lines.append("  цене руки (§20.6 подтвердил), не на рубрике.")
    lines.append("- **C10 курация +3 над lean (§20.6):** +3 при MDD 4.09 (типовая,")
    lines.append("  n=1) — ниже порога; «ровно MDD» в §20.6 стоит читать как")
    lines.append("  «пограничье», не как вывод.")
    lines.append("- **C11 критик на шаге 4 Δ+8 (§21.3):** при шуме step-4 (sd 2.62)")
    lines.append("  MDD(1) = 10.37 (z-аппрокс., теста нет) — Δ+8 НА ГРАНИЦЕ; при")
    lines.append("  k=4 порог 7.9 (§22.1). Отсюда — репликация §22.1.")
    lines.append("- **Выше пересчитанного MDD:** C4 lean +8/+6 (оба выше 5.60).")
    lines.append("- **Отрицательные результаты не требуют пересмотра:** C5 (+2 < MDD),")
    lines.append("  C7/C8 при |Δ| ≤ 5 — вывод «различие не обнаружено» остаётся,")
    lines.append("  порог пересчёта его только укрепляет.")
    lines.append("")
    lines.append("## 5. Итог пересчёта")
    lines.append("")
    lines.append("1. Предрегистрированный MDD +3/40 корректен при n ≥ 3 на руку")
    lines.append("   (типовая: MDD(3) = 4.77 — даже при n=3 точный порог выше +3,")
    lines.append("   потому что измерения шумнее, чем предполагала предрегистрация)")
    lines.append("   и ЗАНИЖЕН при n = 1 (4.09 типовая, 5.60 единая, 10.37 хакатон")
    lines.append("   step-4 — z-аппроксимация, теста нет).")
    lines.append("2. Ни один прошлой относительный вывод с n=1 не отменяется")
    lines.append("   пересчётом автоматически: отменяются те, что были на границе")
    lines.append("   И не воспроизводились (§20.6). Пересчёт — защита от чтения")
    lines.append("   пограничных Δ как выводов.")
    lines.append("3. Правило на будущее (предлагается владельцу): relative-вывод")
    lines.append("   при n=1 объявляется «suggestive» и требует n≥3 или явной")
    lines.append("   пометки граничности; MDD фиксируется в предрегистрации")
    lines.append("   КАЖДОЙ итерации по измеренному шуму её рубрики.")
    lines.append("")

    payload = {
        "noise": [{k: v for k, v in r.items()} for r in noise_rows],
        "mdd_table": {k: {str(n): v for n, v in d.items()} for k, d in mdd_table.items()},
        "conclusions": checked,
        "post_hoc": True,
        "alpha": ALPHA,
        "power": POWER,
    }
    (out_dir / "mdd-recompute.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "mdd-recompute.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"артефакт: {out_dir / 'mdd-recompute.md'}")
    for c in checked:
        mdd = c["mdd"]
        print(
            f"  {c['id']}: Δ={c['deltas']} MDD={'-' if mdd is None else round(mdd, 2)} "
            f"→ {c['verdict']}"
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
