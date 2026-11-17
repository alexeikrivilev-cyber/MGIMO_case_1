#!/usr/bin/env python3
"""critic_step4_power.py — power-анализ репликации «критик только на шаге 4».

TASK-hermes-9 §22.1 (предрегистрация — ДО прогонов репликации).

Задача: результат Δ+8 (TASK-hermes-8 §21.3) получен на ОДНОЙ ревизии.
Прежде чем повторять, считаем, сколько прогонов нужно, чтобы отличить
реальный эффект от шума рубрики.

Модель измерения:
- Оценка артефакта критиком = истинный уровень + шум судьи σ (рубрика,
  температура > 0, nondeterminism провайдера). σ оценивается по
  ПОВТОРНЫМ измерениям ОДНОГО И ТОГО ЖЕ артефакта: демо step-4 черновик
  под рубрикой хакатона — 20.0 (`score-draft`) и 23.7 (`critic-draft`),
  TASK-hermes-8 §21.3 → выборочное sd (n−1). Ограничение названо: n=2,
  оценка слабая.
- В серии из k прогонов черновик — ОДИН И ТОТ ЖЕ артефакт: k наблюдений
  черновика (среднее d̄, шум σ/√k) и k финалов (разные артефакты: шум
  судьи σ/√k + дисперсия руки). Первичный анализ: Δ̂ = mean(финалы) −
  mean(черновик). По-прогонное Δ_i = f_i − d_i имеет шум σ·√2 и
  дополнительно дисперсию ревизии (консервативная проверка пост-фактум).
- Статистика: one-sample t по набору Δ (H1: Δ > 0), α=0.05 двусторонний,
  мощность 0.8. Нормативная модель: Δ_i ~ N(δ, σ_Δ), σ_Δ = σ·√2 (два
  независимых замера). Точный расчёт мощности — нецентральное t
  (смесь по χ² через подстановку u = √w, Симпсон; scipy в окружении нет,
  зависимости stdlib).

Контракт CLI:
    python3 eval/critic_step4_power.py [--out DIR] [--sigma SD]

Коды возврата: 0 — расчёт завершён; 2 — ошибка использования.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 2

ALPHA = 0.05
POWER = 0.80
Z_975 = 1.959963984540054

# Наблюдения черновика демо step-4 под рубрикой хакатона (TASK-hermes-8 §21.3).
DRAFT_OBS = [20.0, 23.7]
DRAFT_SOURCE = "eval/runs/t8-step4/ (score-draft 20.0, critic-draft 23.7)"

# Критические уровни t_{1-α/2, df} для малых df (табличные, точные).
T_CRIT_TABLE = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
}


def sample_sd(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def norm_sf(x: float) -> float:
    """P(Z > x) для стандартного нормального."""
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def t_crit_975(df: int) -> float:
    """t_{0.975, df}: табличные значения для df ≤ 10, иначе разложение."""
    if df in T_CRIT_TABLE:
        return T_CRIT_TABLE[df]
    z = Z_975
    f = float(df)
    # Асимптотическое разложение (Корниш–Фишер для t), точности хватает при df>10.
    return z + (z ** 3 + z) / (4 * f) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * f * f)


def power_one_sample_t(delta: float, sigma_single: float, k: int, alpha: float = ALPHA) -> float:
    """Мощность one-sample t при k наблюдениях Δ_i ~ N(δ, sigma_single²).

    T = Δ̂/(s/√k) ~ t_{df=k-1, ncp=δ√k/σ}. Мощность = E_W[P(|Z| > tc·√(W/df))],
    W ~ χ²_df; интегрирование по u = √(W/df) (подстановка снимает
    особенность χ² в нуле), Симпсон на [0, 12] — хвост пренебрежим.
    """
    df = k - 1
    if df < 1:
        # t не определён при k=1: нормальная аппроксимация (σ известен) —
        # названа аппроксимацией, теста с одним наблюдением не существует.
        ncp = delta / sigma_single
        return norm_cdf(ncp - Z_975) + norm_cdf(-ncp - Z_975)
    ncp = delta * math.sqrt(k) / sigma_single
    tc = t_crit_975(df)
    log_norm = (df / 2) * math.log(2.0) + math.lgamma(df / 2)

    def f_u(u: float) -> float:
        # Плотность u = √(W/df): f_U(u) = 2·df^(df/2)·u^(df-1)·e^(-df·u²/2)/Γ(df/2)/2^(df/2)
        return (
            2.0 * df ** (df / 2) * u ** (df - 1)
            * math.exp(-df * u * u / 2) / math.exp(log_norm)
        )

    u_max, n = 12.0, 4000
    h = u_max / n
    acc = 0.0
    for i in range(n + 1):
        u = i * h
        p = norm_cdf(ncp - tc * u) + norm_cdf(-ncp - tc * u)
        acc += f_u(u) * p * (1 if i in (0, n) else (4 if i % 2 else 2))
    return acc * h / 3.0


def required_k(delta: float, sigma_single: float, alpha: float = ALPHA, power: float = POWER) -> int:
    """Минимальное k с мощностью ≥ power (итеративно, k ≤ 200)."""
    for k in range(2, 201):
        if power_one_sample_t(delta, sigma_single, k, alpha) >= power:
            return k
    return -1


def mdd_at(k: int, sigma_single: float, alpha: float = ALPHA, power: float = POWER) -> float:
    """Минимальный обнаружимый эффект при мощности 0.8 (бисекция)."""
    lo, hi = 0.0, 60.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if power_one_sample_t(mid, sigma_single, k, alpha) >= power:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="critic_step4_power.py",
        description="Power-анализ репликации критика на шаге 4: сколько прогонов нужно против шума рубрики.",
    )
    parser.add_argument("--out", default=str(REPO_ROOT / "eval" / "runs" / "t9-power"))
    parser.add_argument(
        "--sigma",
        type=float,
        default=None,
        help="шум судьи σ на одно наблюдение (default: выборочное sd по двум наблюдениям черновика)",
    )
    args = parser.parse_args(argv)

    sigma = args.sigma if args.sigma is not None else sample_sd(DRAFT_OBS)
    sigma_delta = sigma * math.sqrt(2.0)  # шум одного Δ_i = f_i − d_i
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        (8.0, "Δ+8.0 из TASK-hermes-8 §21.3 (score-final 28.0 − score-draft 20.0)"),
        (6.15, "Δ против среднего черновика (28.0 − 21.85)"),
        (4.3, "Δ против ЛУЧШЕГО наблюдения черновика (28.0 − 23.7), консервативно"),
        (3.0, "порог MDD +3"),
    ]

    lines: list[str] = []
    lines.append("# Power-анализ: репликация «критик только на шаге 4» (TASK-hermes-9 §22.1)")
    lines.append("")
    lines.append("Предрегистрация — ДО прогонов репликации. Драйвер: `eval/critic_step4_power.py`.")
    lines.append("API-вызовов нет (аналитика).")
    lines.append("")
    lines.append("## Входные данные")
    lines.append("")
    lines.append(f"- Наблюдения черновика демо step-4 под рубрикой хакатона: {DRAFT_OBS}")
    lines.append(f"  (источник: {DRAFT_SOURCE})")
    lines.append(f"- Шум судьи на наблюдение σ = **{sigma:.3f}** балла (выборочное sd, n−1)")
    lines.append(f"- Шум одного Δ_i = σ·√2 = **{sigma_delta:.3f}** балла")
    lines.append("  [ограничение названо: n=2 наблюдений — оценка слабая; шум на других")
    lines.append("  артефактах и рубриках не измерялся]")
    lines.append(f"- Пороги: α = {ALPHA} (двусторонний), мощность = {POWER}")
    lines.append("- Статистика: one-sample t по наборам Δ_i = final_i − draft_i")
    lines.append("  (первичный анализ: pooled Δ̂ = mean(финалы) − mean(черновики))")
    lines.append("")
    lines.append("## Требуемое число прогонов k на задачу (мощность 0.8, точный noncentral t)")
    lines.append("")
    lines.append("| Целевой эффект δ | Основание δ | k для мощности 0.8 |")
    lines.append("|---|---|---|")
    for delta, basis in targets:
        k = required_k(delta, sigma_delta)
        lines.append(f"| {delta:.2f} | {basis} | **{k}** |")
    lines.append("")
    lines.append("## Достигаемая мощность при k прогонах")
    lines.append("")
    lines.append("| k | δ=3.0 | δ=4.3 | δ=6.15 | δ=8.0 |")
    lines.append("|---|---|---|---|---|")
    for k in (2, 3, 4, 5, 6, 8):
        row = [f"| {k} |"]
        for delta, _ in targets:
            row.append(f" {power_one_sample_t(delta, sigma_delta, k):.2f} |")
        lines.append("".join(row))
    lines.append("")
    lines.append("## Минимальный обнаружимый эффект MDD(k) при мощности 0.8")
    lines.append("")
    lines.append("| k | MDD (баллы рубрики) |")
    lines.append("|---|---|")
    for k in (2, 3, 4, 5, 6, 8):
        lines.append(f"| {k} | {mdd_at(k, sigma_delta):.2f} |")
    lines.append("")
    lines.append("## Вывод для дизайна репликации (предрегистрация)")
    lines.append("")
    lines.append("- **k = 4 прогона на задачу**: демо — run1 из §21.3 + 3 новых;")
    lines.append("  held-out — 4 новых. Мощность для заявленного Δ+8 ≈ 0.9 (см. таблицу);")
    lines.append("  для δ=6.15 — около 0.6, для δ=4.3 и ниже — недостаточная.")
    lines.append("- Правило расширения (предзарегистрировано ДО данных): если pooled Δ")
    lines.append("  попадает в полосу [3, 8) — эффект на границе обнаружимости при k=4,")
    lines.append("  вердикт «suggestive», требуемое k для 0.8 считается по этой таблице и")
    lines.append("  выносится владельцу утром (не расширяется молча).")
    lines.append("- Пост-фактум проверка: наблюдаемый разброс по-прогонных Δ_i")
    lines.append("  сравнивается с σ·√2 — если больше (дисперсия ревизии), мощность")
    lines.append("  пересчитывается по наблюдаемому разбросу и честно понижается.")
    lines.append("- Черновик — один и тот же артефакт в серии, поэтому наблюдения")
    lines.append("  черновика пулятся: первичный анализ использует mean(drafts) против")
    lines.append("  mean(finals); робастность — анализ только по score-draft наблюдениям")
    lines.append("  (23.7 из critic-draft имеет иной мандат — находки, не замер).")
    lines.append("")

    (out_dir / "critic-step4-power.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"σ={sigma:.3f}, σ_Δ={sigma_delta:.3f}; артефакт: {out_dir / 'critic-step4-power.md'}")
    for delta, _ in targets:
        print(f"  δ={delta:.2f} → k_required={required_k(delta, sigma_delta)}")
    for k in (2, 3, 4, 5, 6, 8):
        print(
            f"  power(k={k}): "
            + " ".join(
                f"δ{d:g}={power_one_sample_t(d, sigma_delta, k):.2f}" for d, _ in targets
            )
        )
    for k in (2, 3, 4, 5, 6, 8):
        print(f"  MDD(k={k}) = {mdd_at(k, sigma_delta):.2f}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
