#!/usr/bin/env python3
"""k3_series.py — серия k=3 по слоям L2/L3/L4 (TASK-hermes-11 §24.1).

Предрегистрация: measurements.md §24.1 ДО прогонов. Генерацию делает
`eval/run_ablation.py --repeat 3` (независимые цепочки L2/L3, прямой
вызов API — среда = промпт); этот драйвер оценивает артефакты и
считает статистику:

  L2/L3 — 3 независимые генерации, каждая — 1 прогон критика под
          каждой рубрикой (генерационная дисперсия входит в интервалы);
  L4    — артефакт продукта ФИКСИРОВАН: 3 свежих скоринга на рубрику
          (интервал шума судьи; генерационной дисперсии нет по
          построению — асимметрия названа в предрегистрации).

Статистика — та же модель, что §22.1/§22.2/§23.5 (`ablation_stats`,
`critic_step4_power`): средние ± 95% CI, Δ с интервалами, вердикт по
MDD(n), требуемое k. Серия не расширяется молча после просмотра данных.

ВАЖНО (исправление против наивной z-модели): при k=3 доверительный
интервал строится по t_{0.975, k-1} = 4.303, а не по z = 1.96 — иначе
интервал занижен в ~2.2 раза. Интервал Δ считается по НАБЛЮДАЕМЫМ sd
рук (у L2/L3 в них входит генерационная дисперсия — это и предмет
серии), а не по модели «шум судьи только».

Контракт CLI:
    python3 eval/k3_series.py [--task demo] [--runs-dir DIR] [--dry-run]

Коды возврата: 0 — всё оценено; 1 — часть прогонов упала; 2 — использование.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from ablation_stats import NOISE, mdd_two_arm, verdict  # noqa: E402
from critic_step4_power import T_CRIT_TABLE, required_k  # noqa: E402
from score_ablation import RUBRICS, parse_scores, run_critic  # noqa: E402

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2

TASK_DIRS = {"demo": "demo-retention"}
PRODUCT_ARTIFACT = "project/options.md"
L4_RESCORINGS = 3
# Базовая серия §23.5 — внешний cross-check балла L4 (n=1, другая сессия).
T10_SUMMARY = REPO_ROOT / "eval" / "runs" / "t10-ablation" / "scores" / "summary.json"

# Файлы цепочек серии: idx 0 — без суффикса (как в серии n=1), далее -1/-2
# (конвенция `run_ablation.py --repeat`).
CHAIN_FILES = ("final.md", "final-1.md", "final-2.md")


def t_crit(n: int) -> float:
    """t_{0.975, n-1}; при n>11 — z-аппроксимация (таблица модуля — до df=10)."""
    return T_CRIT_TABLE.get(n - 1, 1.959963984540054)


def collect_artifacts(runs_dir: Path, task: str) -> dict[str, list[Path]]:
    """Артефакты серии: L2/L3 — финалы трёх генераций; L4 — продукт."""
    base = runs_dir / TASK_DIRS[task]
    out: dict[str, list[Path]] = {}
    for arm in ("L2", "L3"):
        files = [base / arm / name for name in CHAIN_FILES]
        out[arm] = [p for p in files if p.is_file()]
    out["L4"] = [REPO_ROOT / PRODUCT_ARTIFACT]
    return out


def arm_summary(obs: list[float], sd_noise: float) -> dict:
    """Среднее, наблюдаемое sd, 95% CI по t (df = n-1).

    Наблюдаемое sd у L2/L3 включает генерационную дисперсию + шум судьи;
    у L4 — только шум судьи (артефакт фиксирован).
    """
    n = len(obs)
    mean = sum(obs) / n
    if n < 2:
        return {"n": n, "obs": obs, "mean": mean, "sd": None, "ci95": None}
    var = sum((o - mean) ** 2 for o in obs) / (n - 1)
    sd = math.sqrt(var)
    return {
        "n": n,
        "obs": obs,
        "mean": mean,
        "sd": sd,
        "ci95": t_crit(n) * sd / math.sqrt(n),
    }


def delta_summary(arm_lo: dict, arm_hi: dict) -> dict:
    """Δ = mean(hi) − mean(lo) с 95% интервалом по наблюдаемым sd рук."""
    delta = arm_hi["mean"] - arm_lo["mean"]
    if arm_lo.get("sd") is None or arm_hi.get("sd") is None:
        return {"delta": delta, "ci95": None, "covers_zero": None}
    n_lo, n_hi = arm_lo["n"], arm_hi["n"]
    se = math.sqrt(arm_lo["sd"] ** 2 / n_lo + arm_hi["sd"] ** 2 / n_hi)
    half = t_crit(min(n_lo, n_hi)) * se
    return {
        "delta": delta,
        "se": se,
        "ci95": half,
        "covers_zero": half >= abs(delta),
    }


def load_t10_l4() -> dict:
    """Балл L4 из базовой серии §23.5 (n=1) — внешний cross-check."""
    if not T10_SUMMARY.is_file():
        return {}
    out: dict[str, float] = {}
    for r in json.loads(T10_SUMMARY.read_text(encoding="utf-8"))["runs"]:
        if r.get("task") == "demo" and r.get("arm") == "L4":
            for rubric in RUBRICS:
                value = r.get(rubric, {}).get("total40")
                if value is not None:
                    out[rubric] = value
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="k3_series.py",
        description="Серия k=3 по слоям L2/L3/L4: оценивание + статистика (TASK-hermes-11 §24.1).",
    )
    parser.add_argument("--task", default="demo", choices=sorted(TASK_DIRS))
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "eval" / "runs" / "t11-k3"))
    parser.add_argument(
        "--arms",
        default="L2,L3,L4",
        help="какие руки оценивать (L4 — фиксированный артефакт продукта)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    wanted = [a.strip() for a in args.arms.split(",") if a.strip()]
    artifacts = {a: f for a, f in collect_artifacts(runs_dir, args.task).items() if a in wanted}

    if args.dry_run:
        for arm, files in artifacts.items():
            print(f"[dry-run] {arm}: {len(files)} артефактов: {[f.name for f in files]}")
        return EXIT_OK

    failures = 0
    # Оценивание: (arm, idx, rubric) -> score.
    # КАЖДАЯ цепочка генерации scored один раз на рубрику (k наблюдений
    # на руку); L4 — фиксированный артефакт, L4_RESCORINGS прогонов
    # (интервал шума судьи). Регресс-тест: tests/test_k3_series.py.
    scores: dict[tuple[str, int, str], float | None] = {}
    records: list[dict] = []
    for arm, files in artifacts.items():
        reps = L4_RESCORINGS if arm == "L4" else len(files)
        for i in range(reps):
            artifact = files[i % len(files)] if files else None
            if artifact is None or not artifact.is_file():
                failures += 1
                print(f"{arm}#{i}: артефакт не найден", file=sys.stderr)
                continue
            for rubric_name, rubric_path in RUBRICS.items():
                tag = f"t11-k3-{args.task}-{arm}-{i}-{rubric_name}"[:40]
                out_dir = runs_dir / "scores" / args.task / f"{arm}-{i}-{rubric_name}"
                critic_out = out_dir / "critic.out"
                if critic_out.is_file() and critic_out.read_text(encoding="utf-8", errors="replace").strip():
                    # Идемпотентность: уже оцененный прогон не повторяем
                    # (защита от двойной оплаты при перезапуске драйвера).
                    res = parse_scores(
                        critic_out.read_text(encoding="utf-8", errors="replace")
                    )
                    res["source"] = str(critic_out)
                    if res.get("total40") is None:
                        res["error"] = "Итого не распознан в существующем critic.out"
                else:
                    res = run_critic(artifact, rubric_path, out_dir, tag)
                if "error" in res:
                    failures += 1
                scores[(arm, i, rubric_name)] = res.get("total40")
                records.append({"arm": arm, "i": i, "rubric": rubric_name,
                                "total40": res.get("total40"),
                                "artifact": artifact.name,
                                "error": res.get("error")})
                print(f"{arm}#{i} {rubric_name}: {res.get('total40')}")

    # Статистика по рубрикам.
    lines = [
        f"# Серия k=3 по слоям L2/L3/L4 — задача {args.task} (TASK-hermes-11 §24.1)",
        "",
        "Драйвер: `eval/k3_series.py`. Предрегистрация — measurements.md §24.1.",
        "L2/L3 — независимые генерации (генерационная дисперсия включена в",
        "наблюдаемое sd); L4 — фиксированный артефакт продукта, 3 свежих",
        "скоринга (шум судьи). Интервалы — по t_{{0.975, n-1}} (при n=3 —",
        "4.303), не по z.",
        "",
    ]
    payload: dict[str, dict] = {}
    t10_l4 = load_t10_l4()
    for rubric_name, spec in NOISE.items():
        sd = spec["sd"]
        lines.append(f"## Рубрика {rubric_name} (шум судьи sd {sd}, наблюдений шума {spec['n_obs']})")
        lines.append("")
        lines.append("| Рука | Наблюдения | Среднее | sd (набл.) | 95% CI (t) | MDD(n=3) |")
        lines.append("|---|---|---|---|---|---|")
        means: dict[str, float] = {}
        summaries: dict[str, dict] = {}
        for arm in ("L2", "L3", "L4"):
            reps = L4_RESCORINGS if arm == "L4" else len(artifacts.get(arm, []))
            obs = [scores.get((arm, i, rubric_name)) for i in range(reps)]
            obs = [float(o) for o in obs if o is not None]
            if not obs:
                lines.append(f"| {arm} | — | — | — | — | — |")
                continue
            st = arm_summary(obs, sd)
            means[arm] = st["mean"]
            summaries[arm] = st
            sd_s = f"{st['sd']:.2f}" if st.get("sd") is not None else "—"
            ci_s = f"±{st['ci95']:.2f}" if st.get("ci95") is not None else "—"
            lines.append(
                f"| {arm} | {obs} | {st['mean']:.2f} | {sd_s} | {ci_s} | {mdd_two_arm(3, sd):.2f} |"
            )
        lines.append("")
        lines.append("| Δ | Величина | 95% CI (t, наблюдаемые sd) | Интервал накрывает 0 | Вердикт (предрег. §24.1) | Требуемое k (нижняя граница) |")
        lines.append("|---|---|---|---|---|---|")
        pairs: dict[str, dict] = {}
        for lo, hi in (("L2", "L3"), ("L3", "L4")):
            if lo in summaries and hi in summaries:
                d = delta_summary(summaries[lo], summaries[hi])
                mdd = mdd_two_arm(3, sd)
                need_k = required_k(d["delta"], sd * math.sqrt(2.0)) if d["delta"] > 0 else None
                pairs[f"{lo}->{hi}"] = {**d, "mdd": mdd, "verdict": verdict(d["delta"], mdd),
                                        "required_k": need_k}
                ci_s = f"±{d['ci95']:.2f}" if d.get("ci95") is not None else "—"
                cov = d.get("covers_zero")
                cov_s = "да" if cov else ("нет" if cov is not None else "—")
                lines.append(
                    f"| {lo}→{hi} | {d['delta']:+.2f} | {ci_s} | {cov_s} "
                    f"| {pairs[f'{lo}->{hi}']['verdict']} | {need_k if need_k else '—'} |"
                )
        lines.append("")
        if rubric_name in t10_l4:
            lines.append(
                f"L4 cross-check: базовая серия §23.5 (n=1, другая сессия) — "
                f"{t10_l4[rubric_name]}; разница со средним этой серии — "
                f"шум судьи на фиксированном артефакте."
            )
            lines.append("")
        payload[rubric_name] = {
            "arms": summaries,
            "mdd_n3": mdd_two_arm(3, sd),
            "pairs": pairs,
            "l4_t10_crosscheck": t10_l4.get(rubric_name),
        }

    lines.append(
        "Ограничения (названы в §24.1): (1) сравнительная асимметрия — у L2/L3"
    )
    lines.append(
        "в интервалы входит генерационная дисперсия, у L4 только шум судьи;"
    )
    lines.append(
        "(2) требуемое k считалось по модели «шум судьи только» — нижняя"
    )
    lines.append(
        "граница; (3) вердикт — по предрегистрированному правилу точки; если"
    )
    lines.append(
        "интервал Δ накрывает 0, точечный вердикт читать как suggestive."
    )

    (runs_dir / "scores").mkdir(parents=True, exist_ok=True)
    (runs_dir / "scores" / "k3-summary.json").write_text(
        json.dumps({"task": args.task, "records": records, "stats": payload,
                    "failures": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runs_dir / "scores" / "k3-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nитог: падений {failures}; summary: {runs_dir / 'scores' / 'k3-summary.md'}")
    return EXIT_OK if failures == 0 else EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
