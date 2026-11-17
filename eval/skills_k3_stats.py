#!/usr/bin/env python3
"""skills_k3_stats.py — статистика серии k=3 по дизайну навыков + О5 + H-C2 (TASK-hermes-12).

Модель — та же, что §24.1 (k3_series): средние ± 95% CI по t (df=2 →
4.303); Δ пар с интервалами по НАБЛЮДАЕМЫМ sd (генерационная
дисперсия входит — предмет серии); MDD(n=3) из измеренного шума
(ablation_stats.NOISE); вердикт по предрегистрированному правилу
§25.1: |Δ| ≥ MDD → «выше шума»; 0.75–1× → «НА ГРАНИЦЕ»; ниже → «нет
отличимого различия». Требуемое k для наблюдаемых Δ.

Группы анализа (рука → из каких групп оценок берутся наблюдения):
  step2 — шаг 2 (research): curation / lean / hybrid (step-5);
  step3 — шаг 3 (options): те же руки (step-5);
  o5a   — research lean: step-5 vs flash (O5-A);
  o5b   — options skill: research от step-5 (P) vs от flash (F) (O5-B);
  hc2   — шаг 2: черновик lean vs ревизованный (H-C2) vs курация.

Cross-check: точки §18.1/§14.3 (n=1, сессии opencode с AGENTS.md и
инструментами — ДРУГАЯ механика, уровни несравнимы; внешняя опора).

Контракт CLI:
    python3 eval/skills_k3_stats.py [--runs-dir DIR] [--out DIR]

Коды возврата: 0 — расчёт завершён; 2 — использование/нет данных.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from ablation_stats import NOISE, mdd_two_arm, verdict  # noqa: E402
from critic_step4_power import T_CRIT_TABLE, required_k  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2

# Группы анализа: рука → (группы оценок, имя руки в записях); пары Δ.
ANALYSES: dict[str, dict] = {
    "step2": {
        "arms": {
            "curation": (["research"], "curation"),
            "lean": (["research"], "lean"),
            "hybrid": (["research"], "hybrid"),
        },
        "pairs": [("curation", "lean"), ("hybrid", "lean"), ("curation", "hybrid")],
    },
    "step3": {
        "arms": {
            "curation": (["options"], "curation"),
            "lean": (["options"], "lean"),
            "hybrid": (["options"], "hybrid"),
        },
        "pairs": [("curation", "lean"), ("hybrid", "lean"), ("curation", "hybrid")],
    },
    "o5a": {
        "arms": {"step5": (["research"], "lean"), "flash": (["o5a"], "lean")},
        "pairs": [("step5", "flash")],
    },
    "o5b": {
        "arms": {"P": (["o5b-P"], "skill"), "F": (["o5b-F"], "skill")},
        "pairs": [("P", "F")],
    },
    "hc2": {
        "arms": {
            "draft": (["research"], "lean"),
            "revised": (["hc2"], "revised"),
            "curation": (["research"], "curation"),
        },
        "pairs": [("revised", "draft"), ("revised", "curation")],
    },
}

# Внешний cross-check (n=1, другая механика — §18.1/§14.3 + реcкоринг
# §20.6, артефакт eval/runs/t7-rescore/summary.json).
CROSSCHECK = {
    "step2": {"curation": {"unified": 18.0, "typical": 39.0},
              "lean": {"unified": 26.0, "typical": 36.0},
              "hybrid": {"unified": 16.0, "typical": 36.0}},
    "step3": {"curation": {"unified": 20.0, "typical": 39.0},
              "lean": {"unified": 19.1, "typical": 36.0},
              "hybrid": {"unified": 19.0, "typical": 36.0}},
}
CROSSCHECK_SOURCE = ("§18.1/§14.3 (единая, n=1) + §20.6 реcкоринг "
                     "(типовая, n=1, eval/runs/t7-rescore/summary.json); "
                     "механика: сессии opencode с инструментами и AGENTS.md — "
                     "абсолютные уровни НЕ сопоставимы с этой серией")


def t_crit(n: int) -> float:
    return T_CRIT_TABLE.get(n - 1, 1.959963984540054)


def arm_summary(obs: list[float]) -> dict:
    n = len(obs)
    mean = sum(obs) / n
    if n < 2:
        return {"n": n, "obs": obs, "mean": mean, "sd": None, "ci95": None}
    var = sum((o - mean) ** 2 for o in obs) / (n - 1)
    sd = math.sqrt(var)
    return {"n": n, "obs": obs, "mean": mean, "sd": sd, "ci95": t_crit(n) * sd / math.sqrt(n)}


def delta_summary(lo: dict, hi: dict) -> dict:
    delta = hi["mean"] - lo["mean"]
    if lo.get("sd") is None or hi.get("sd") is None:
        return {"delta": delta, "ci95": None, "covers_zero": None}
    n_lo, n_hi = lo["n"], hi["n"]
    se = math.sqrt(lo["sd"] ** 2 / n_lo + hi["sd"] ** 2 / n_hi)
    half = t_crit(min(n_lo, n_hi)) * se
    return {"delta": delta, "se": se, "ci95": half, "covers_zero": half >= abs(delta)}


def load_records(runs_dir: Path, subdir: str = "scores") -> list[dict]:
    path = runs_dir / subdir / "summary.json"
    if not path.is_file():
        raise FileNotFoundError(f"не найден {path} — сначала eval/score_skills_k3.py")
    return json.loads(path.read_text(encoding="utf-8"))["records"]


def observations(records: list[dict], groups: list[str], arm: str, rubric: str) -> list[float]:
    out: list[float] = []
    for group in groups:
        for r in records:
            if (r["group"] == group and r["arm"] == arm and r["rubric"] == rubric
                    and r["total40"] is not None):
                out.append(float(r["total40"]))
    return sorted(out)


def generation_costs(runs_dir: Path) -> dict[str, float]:
    """$/генерация из meta.json (прямой вызов API, формула §1.8)."""
    costs: dict[str, float] = {}
    for meta_path in sorted(runs_dir.glob("*/*/meta*.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        key = f"{meta.get('group')}/{meta.get('arm')}"
        costs[key] = costs.get(key, 0.0) + float(meta.get("cost_usd_total") or 0.0)
    return costs


def scoring_costs(labels: tuple[str, ...] = ("t12-",)) -> tuple[float, int]:
    """$ оценивания и ревизий из COST.md по меткам «О4: <label>…» (хук)."""
    cost_path = REPO_ROOT / "COST.md"
    total, count = 0.0, 0
    if not cost_path.is_file():
        return total, count
    for line in cost_path.read_text(encoding="utf-8-sig").splitlines():
        if not any(label in line for label in labels):
            continue
        match = re.search(r"\$([\d.]+)\s*\|", line)
        if match:
            total += float(match.group(1))
            count += 1
    return total, count


def analyze_records(records: list[dict], wanted: list[str], crosscheck: bool = True,
                    critic_title: str | None = None) -> tuple[dict, list[str]]:
    """Таблицы и payload по одному набору оценок (одному критику).

    Извлечено из main, чтобы один и тот же расчёт применялся к обоим
    критикам протокола (§27.2-А) без дублирования логики вердиктов.
    """
    lines: list[str] = []
    if critic_title:
        lines.append(f"# Оценки: {critic_title}")
        lines.append("")
    payload: dict[str, dict] = {}
    for analysis in wanted:
        spec = ANALYSES[analysis]
        lines.append(f"## {analysis}")
        lines.append("")
        for rubric in ("unified", "typical"):
            sd = NOISE[rubric]["sd"]
            mdd = mdd_two_arm(3, sd)
            lines.append(f"### Рубрика {rubric} (MDD(n=3) = {mdd:.2f})")
            lines.append("")
            lines.append("| Рука | Наблюдения | Среднее | sd (набл.) | 95% CI (t) |")
            lines.append("|---|---|---|---|---|")
            summaries: dict[str, dict] = {}
            for arm, (groups, record_arm) in spec["arms"].items():
                obs = observations(records, groups, record_arm, rubric)
                if not obs:
                    lines.append(f"| {arm} | — | — | — | — |")
                    continue
                st = arm_summary(obs)
                summaries[arm] = st
                sd_s = f"{st['sd']:.2f}" if st.get("sd") is not None else "—"
                ci_s = f"±{st['ci95']:.2f}" if st.get("ci95") is not None else "—"
                lines.append(f"| {arm} | {obs} | {st['mean']:.2f} | {sd_s} | {ci_s} |")
            lines.append("")
            if summaries:
                lines.append("| Δ (hi − lo) | Величина | 95% CI (t, набл. sd) | Накрывает 0 | Вердикт (предрег. §25.1) | Требуемое k |")
                lines.append("|---|---|---|---|---|---|")
                pairs_out: dict[str, dict] = {}
                for lo, hi in spec["pairs"]:
                    if lo not in summaries or hi not in summaries:
                        continue
                    d = delta_summary(summaries[lo], summaries[hi])
                    need_k = required_k(d["delta"], sd * math.sqrt(2.0)) if d["delta"] > 0 else None
                    v = verdict(d["delta"], mdd)
                    pairs_out[f"{lo}->{hi}"] = {**d, "mdd": mdd, "verdict": v, "required_k": need_k}
                    ci_s = f"±{d['ci95']:.2f}" if d.get("ci95") is not None else "—"
                    cov = d.get("covers_zero")
                    cov_s = "да" if cov else ("нет" if cov is not None else "—")
                    lines.append(
                        f"| {hi} − {lo} | {d['delta']:+.2f} | {ci_s} | {cov_s} | {v} "
                        f"| {need_k if need_k else '—'} |"
                    )
                lines.append("")
                payload.setdefault(analysis, {})[rubric] = {"arms": summaries, "pairs": pairs_out, "mdd_n3": mdd}
            if crosscheck and analysis in CROSSCHECK:
                lines.append("Cross-check (n=1, ДРУГАЯ механика): "
                             + "; ".join(f"{arm} {CROSSCHECK[analysis][arm][rubric]}"
                                         for arm in CROSSCHECK[analysis])
                             + f". {CROSSCHECK_SOURCE}.")
                lines.append("")
    return payload, lines


def agreement_lines(records_a: list[dict], records_b: list[dict],
                    payload_a: dict, payload_b: dict) -> list[str]:
    """Согласие двух критиков (§27.2-А): поклеточные Δ и согласие вердиктов.

    Протокол двух критиков применяется, чтобы отделить task-эффект от
    конвенции судьи: расхождение вердиктов = вердикт серии
    конвенция-зависим, а не task-зависим.
    """
    lines = [
        "# Согласие критиков (протокол двух критиков, §27.2-А)",
        "",
        "Поклеточные Δ (критик #2 − критик #1) по общим клеткам и согласие",
        "вердиктов пар. Вердикт пары считается согласованным, если оба",
        "критика дают одну и ту же категорию предрегистрации.",
        "",
    ]
    index_a = {(r.get("group"), r.get("arm"), r.get("i"), r.get("rubric")): float(r["total40"])
               for r in records_a if r.get("total40") is not None}
    index_b = {(r.get("group"), r.get("arm"), r.get("i"), r.get("rubric")): float(r["total40"])
               for r in records_b if r.get("total40") is not None}
    common = sorted(set(index_a) & set(index_b))
    by_rubric: dict[str, list[float]] = {}
    for key in common:
        by_rubric.setdefault(key[3], []).append(index_b[key] - index_a[key])
    lines.append("| Рубрика | Общих клеток | mean |Δ| | sd(Δ) | Клеток с |Δ| ≥ MDD(n=1) |")
    lines.append("|---|---|---|---|---|")
    for rubric in ("unified", "typical"):
        diffs = by_rubric.get(rubric)
        if not diffs:
            continue
        abs_diffs = [abs(d) for d in diffs]
        mean_ad = sum(abs_diffs) / len(abs_diffs)
        sd_d = math.sqrt(sum((d - sum(diffs) / len(diffs)) ** 2 for d in diffs) / (len(diffs) - 1)) if len(diffs) > 1 else 0.0
        mdd1 = mdd_two_arm(1, NOISE[rubric]["sd"])
        beyond = sum(1 for d in abs_diffs if d >= mdd1)
        lines.append(f"| {rubric} | {len(diffs)} | {mean_ad:.2f} | {sd_d:.2f} | {beyond} (MDD {mdd1:.2f}) |")
    lines.append("")
    lines.append("| Анализ | Рубрика | Пара | Δ к1 | вердикт к1 | Δ к2 | вердикт к2 | Согласие |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for analysis in payload_a:
        for rubric, cell in payload_a[analysis].items():
            other = payload_b.get(analysis, {}).get(rubric, {})
            for pair, d in cell.get("pairs", {}).items():
                od = other.get("pairs", {}).get(pair)
                if od is None:
                    continue
                agree = "да" if d["verdict"] == od["verdict"] else "НЕТ"
                lines.append(
                    f"| {analysis} | {rubric} | {pair} | {d['delta']:+.2f} | {d['verdict']} "
                    f"| {od['delta']:+.2f} | {od['verdict']} | {agree} |"
                )
    lines.append("")
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skills_k3_stats.py",
        description="Статистика серии навыков k=3: интервалы, Δ, вердикты по предрегистрации §25.1.",
    )
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "eval" / "runs" / "t12-skills"))
    parser.add_argument("--out", default=None)
    parser.add_argument("--analyses", default=",".join(ANALYSES))
    parser.add_argument("--scores-subdir", default="scores",
                        help="подкаталог runs-dir с оценками критика #1")
    parser.add_argument("--other-scores-subdir", default=None,
                        help="подкаталог runs-dir с оценками критика #2 (протокол §27.2-А)")
    parser.add_argument("--cost-label", action="append", default=None,
                        help="метка сессий оценивания в COST.md (можно многократно)")
    parser.add_argument("--no-crosscheck", action="store_true",
                        help="без демо-cross-check (для серий на других задачах)")
    args = parser.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    out_dir = Path(args.out) if args.out else runs_dir
    wanted = [a.strip() for a in args.analyses.split(",") if a.strip()]
    unknown = [a for a in wanted if a not in ANALYSES]
    if unknown:
        print(f"неизвестные группы анализа: {unknown}; доступно: {list(ANALYSES)}", file=sys.stderr)
        return EXIT_USAGE
    try:
        records = load_records(runs_dir, args.scores_subdir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    header_lines: list[str] = [
        "# Серия k=3 по дизайну навыков + О5 — статистика (TASK-hermes-12 §25.1/§25.2/§25.3)",
        "",
        "Драйвер: `eval/skills_k3_stats.py` (API-вызовов нет). Предрегистрация —",
        "measurements.md §25.1/§25.2/§25.3 ДО прогонов. Интервалы — по t (df=2 →",
        "4.303), не по z. MDD(n=3) из измеренного шума судьи.",
        "",
        "| Рубрика | sd шума | n наблюдений шума | MDD(n=3) |",
        "|---|---|---|---|",
    ]
    for key, spec in NOISE.items():
        header_lines.append(f"| {key} | {spec['sd']} | {spec['n_obs']} | {mdd_two_arm(3, spec['sd']):.2f} |")
    header_lines.append("")

    payload, body_lines = analyze_records(records, wanted, crosscheck=not args.no_crosscheck)
    lines = header_lines + body_lines

    other_payload: dict[str, dict] | None = None
    if args.other_scores_subdir:
        try:
            other_records = load_records(runs_dir, args.other_scores_subdir)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE
        other_payload, other_lines = analyze_records(
            other_records, wanted, crosscheck=False, critic_title="критик #2")
        lines += other_lines
        lines += agreement_lines(records, other_records, payload, other_payload)

    # Стоимость очереди.
    gen_costs = generation_costs(runs_dir)
    labels = tuple(args.cost_label or ["t12-"])
    score_usd, score_n = scoring_costs(labels)
    lines.append("## Стоимость (из meta.json генерации + COST.md сессий оценивания)")
    lines.append("")
    lines.append("| Источник | $ |")
    lines.append("|---|---|")
    for key in sorted(gen_costs):
        lines.append(f"| генерация {key} | {gen_costs[key]:.4f} |")
    gen_total = sum(gen_costs.values())
    lines.append(f"| генерация итого (прямой вызов API) | {gen_total:.4f} |")
    lines.append(f"| сессии OpenCode ({score_n} строк, метки «О4: {labels[0]}…») | {score_usd:.4f} |")
    lines.append(f"| итого очередь (без сессий оркестратора) | {gen_total + score_usd:.4f} |")
    lines.append("")

    (out_dir / "scores").mkdir(parents=True, exist_ok=True)
    (out_dir / "scores" / "skills-k3-summary.json").write_text(
        json.dumps({"analyses": payload, "other_critic": other_payload,
                    "generation_costs": gen_costs,
                    "sessions_usd": score_usd, "sessions_rows": score_n},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "scores" / "skills-k3-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"артефакт: {out_dir / 'scores' / 'skills-k3-summary.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
