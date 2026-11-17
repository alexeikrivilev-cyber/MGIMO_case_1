#!/usr/bin/env python3
"""aggregate_step4.py — агрегация серии репликаций «критик только на шаге 4».

TASK-hermes-9 §22.1 (анализ предзарегистрирован до данных). Скрипт чистый
(только чтение артефактов прогонов), API-вызовов нет.

Для каждой задачи (демо / held-out) собирает прогоны серии:
- score-draft/critic.out — наблюдение черновика (мандат «замер»);
- critic-draft/critic.out — наблюдение черновика (мандат «находки»),
  используется ТОЛЬКО в робастном анализе (предрегистрация §22.1);
- score-final/critic.out — наблюдение финала после точечной ревизии;
- revision-report.md — applied/not_found/ambiguous/integrity/size_ratio.

Анализ (предзарегистрирован §22.1):
- первичный: pooled Δ̂ = mean(score-final) − mean(score-draft);
- робастность (а): только score-draft наблюдения (если серия includes
  прогон с иным мандатом);
- робастность (б): по-прогонный Δ_i = final_i − draft_i: mean, sd (n−1),
  one-sample t (t, df, p двусторонний, 95% CI), разброс против σ·√2;
- вердикт по предрегистрации: Δ̂ ≥ MDD(k) → «подтверждено»;
  Δ̂ ∈ [3, MDD(k)) → «suggestive» (требуемое k — владельцу); иначе negative.

Контракт CLI:
    python3 eval/aggregate_step4.py --task NAME --runs DIR [DIR ...] [--out FILE]

Коды возврата: 0 — агрегация завершена; 2 — ошибка использования;
3 — среди прогонов нет разборимых замеров.
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

from critic_step4_power import power_one_sample_t  # noqa: E402  (переиспользование мощности)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_DATA = 3

TOTAL_RE = re.compile(
    r"Итого\s*:\s*(?:\*\*)?\s*([\d.]+)\s*(?:\*\*)?\s*/\s*40"
    r"|\|\s*Итого\s*\|[^|\n]*\|[^|\n]*\|\s*(?:\*\*)?\s*([\d.]+)\s*/\s*40"
)
FINDING_RE = re.compile(r"\[(?:важность:\s*)?(критично|важно|незначительно)\]")
REVISION_RE = re.compile(
    r"applied=(\d+)\s+not_found=(\d+)\s+ambiguous=(\d+)\s+rejected=(\d+)\s+"
    r"fallback=(\w+)\s+integrity=(\w+)\s+size_ratio=([\d.]+)"
)

# Шум судьи на демо step-4 (§21.3, n=2) — для сравнения наблюдаемого разброса.
SIGMA_DELTA = 3.70
MDD_TABLE = {2: 42.73, 3: 12.08, 4: 7.87, 5: 6.22, 6: 5.31, 8: 4.28}


def parse_total(text: str) -> float | None:
    m = TOTAL_RE.search(text)
    if not m:
        return None
    value = m.group(1) or m.group(2)
    return float(value) if value else None


def parse_findings(text: str) -> tuple[int, int]:
    """(всего находок, важно+критично)."""
    kinds = FINDING_RE.findall(text)
    return len(kinds), sum(1 for k in kinds if k in ("важно", "критично"))


def parse_revision(text: str) -> dict | None:
    m = REVISION_RE.search(text)
    if not m:
        return None
    return {
        "applied": int(m.group(1)),
        "not_found": int(m.group(2)),
        "ambiguous": int(m.group(3)),
        "rejected": int(m.group(4)),
        "fallback": m.group(5),
        "integrity": m.group(6),
        "size_ratio": float(m.group(7)),
    }


def read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def collect_run(run_dir: Path) -> dict:
    out: dict = {"run": run_dir.name}
    for name, sub, key in (
        ("score-draft", "score-draft", "draft_score"),
        ("score-final", "score-final", "final_score"),
        ("critic-draft", "critic-draft", "draft_critic"),
    ):
        text = read_optional(run_dir / sub / "critic.out")
        total = parse_total(text)
        findings, important = parse_findings(text)
        out[key] = total
        out[f"{key}_findings"] = findings
        out[f"{key}_important"] = important
    rev = parse_revision(read_optional(run_dir / "revision-report.md"))
    if rev:
        out.update(rev)
    return out


def t_sf(t: float, df: int) -> float:
    """P(T_df > t) — смесь по χ² (тот же приём, что в power-анализе)."""
    if df < 1:
        return 0.5 * math.erfc(t / math.sqrt(2.0))
    log_norm = (df / 2) * math.log(2.0) + math.lgamma(df / 2)

    def f_u(u: float) -> float:
        return 2.0 * df ** (df / 2) * u ** (df - 1) * math.exp(-df * u * u / 2) / math.exp(log_norm)

    n = 4000
    h = 12.0 / n
    acc = 0.0
    for i in range(n + 1):
        u = i * h
        acc += f_u(u) * (0.5 * math.erfc(t * u / math.sqrt(2.0))) * (
            1 if i in (0, n) else (4 if i % 2 else 2)
        )
    return acc * h / 3.0


def one_sample_t(xs: list[float]) -> dict:
    n = len(xs)
    mean = sum(xs) / n
    if n < 2:
        return {"n": n, "mean": mean, "sd": None, "t": None, "df": None, "p": None}
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1))
    if sd == 0:
        return {"n": n, "mean": mean, "sd": sd, "t": math.inf if mean else 0.0, "df": n - 1, "p": 0.0}
    t = mean / (sd / math.sqrt(n))
    df = n - 1
    p = 2 * t_sf(abs(t), df)
    return {"n": n, "mean": mean, "sd": sd, "t": t, "df": df, "p": min(1.0, p)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="aggregate_step4.py",
        description="Агрегация серии репликаций «критик на шаге 4»: pooled Δ, разброс, вердикт по предрегистрации.",
    )
    parser.add_argument("--task", required=True, help="имя задачи (демо / heldout)")
    parser.add_argument("--runs", nargs="+", required=True, help="каталоги прогонов серии")
    parser.add_argument("--out", default=None, help="файл summary.md (default: <первый прогон>/../aggregate-<task>.md)")
    args = parser.parse_args(argv)

    run_dirs = [Path(r) for r in args.runs]
    missing = [str(r) for r in run_dirs if not r.is_dir()]
    if missing:
        print(f"каталоги прогонов не найдены: {missing}", file=sys.stderr)
        return EXIT_NO_DATA

    runs = [collect_run(r) for r in run_dirs]
    usable = [r for r in runs if r.get("final_score") is not None and r.get("draft_score") is not None]
    if not usable:
        print("ни один прогон не содержит разборимых замеров (score-draft/score-final)", file=sys.stderr)
        return EXIT_NO_DATA

    finals = [r["final_score"] for r in usable]
    drafts = [r["draft_score"] for r in usable]
    k = len(usable)
    pooled = sum(finals) / k - sum(drafts) / k
    per_run = [r["final_score"] - r["draft_score"] for r in usable]
    stats = one_sample_t(per_run)
    mdd = MDD_TABLE.get(k)
    if mdd is not None and pooled >= mdd:
        verdict = "ПОДТВЕРЖДЕНО (pooled Δ ≥ MDD при мощности 0.8)"
    elif pooled >= 3.0:
        verdict = "SUGGESTIVE (полоса [3, MDD) — требуемое k выносится владельцу)"
    else:
        verdict = "NEGATIVE (Δ < 3 = предрегистрированный MDD)"

    # Робастность: только score-draft наблюдения + наблюдения critic-draft отдельно.
    critic_drafts = [r["draft_critic"] for r in usable if r.get("draft_critic") is not None]
    pooled_score_only = sum(finals) / k - sum(drafts) / k  # уже только score-draft
    pooled_with_critic = (
        sum(finals) / k - (sum(drafts) + sum(critic_drafts)) / (k + len(critic_drafts))
        if critic_drafts else None
    )

    spread_note = (
        f"наблюдаемый разброс Δ_i: sd {stats['sd']:.2f} против σ·√2 = {SIGMA_DELTA} "
        f"({'в пределах' if stats['sd'] is not None and stats['sd'] <= SIGMA_DELTA else 'ВЫШЕ — дисперсия ревизии'})"
        if stats["sd"] is not None else "разброс: n<2"
    )

    lines: list[str] = []
    lines.append(f"# Агрегация серии «критик на шаге 4» — задача {args.task} (TASK-hermes-9 §22.1)")
    lines.append("")
    lines.append(f"Прогоны серии: {', '.join(r['run'] for r in runs)}")
    lines.append(f"Разборимых замеров: {k} (score-draft + score-final в каждом).")
    lines.append("")
    lines.append("| Прогон | draft (score) | final | Δ | draft (critic) | findings | «важно» | applied | integrity | size_ratio |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in usable:
        lines.append(
            f"| {r['run']} | {r['draft_score']} | {r['final_score']} | "
            f"{r['final_score'] - r['draft_score']:+.1f} | "
            f"{r.get('draft_critic') if r.get('draft_critic') is not None else '—'} | "
            f"{r.get('final_score_findings', '—')} | {r.get('final_score_important', '—')} | "
            f"{r.get('applied', '—')} | {r.get('integrity', '—')} | {r.get('size_ratio', '—')} |"
        )
    lines.append("")
    lines.append("## Первичный анализ (предзарегистрирован)")
    lines.append("")
    lines.append(f"- pooled Δ̂ = mean(finals) − mean(drafts) = **{pooled:+.2f}**")
    lines.append(f"- по-прогонные Δ_i: {['%+.1f' % d for d in per_run]}")
    lines.append(
        f"- one-sample t по Δ_i: mean {stats['mean']:+.2f}, sd "
        f"{stats['sd'] if stats['sd'] is not None else '—'}, t = "
        f"{stats['t'] if stats['t'] is not None else '—'}, df = {stats['df']}, "
        f"p = {stats['p'] if stats['p'] is not None else '—'}"
    )
    lines.append(f"- MDD(k={k}) при мощности 0.8 (power-анализ §22.1): **{mdd}**")
    lines.append(f"- Вердикт по предрегистрации: **{verdict}**")
    lines.append(f"- {spread_note}")
    lines.append("")
    lines.append("## Робастность")
    lines.append("")
    lines.append(f"- (а) только score-draft наблюдения: pooled Δ = **{pooled_score_only:+.2f}**")
    if pooled_with_critic is not None:
        lines.append(
            f"- (б) с наблюдениями critic-draft (мандат «находки»): pooled Δ = **{pooled_with_critic:+.2f}**"
        )
    lines.append("")
    lines.append("## Целостность ревизий")
    lines.append("")
    ok = [r for r in usable if r.get("integrity") == "ok"]
    lines.append(f"- integrity ok: {len(ok)}/{k}; fallback: "
                 f"{sum(1 for r in usable if r.get('fallback') == 'yes')}")
    lines.append("")

    payload = {
        "task": args.task,
        "runs": runs,
        "k": k,
        "pooled_delta": pooled,
        "per_run_delta": per_run,
        "one_sample_t": stats,
        "mdd": mdd,
        "verdict": verdict,
        "pooled_score_only": pooled_score_only,
        "pooled_with_critic": pooled_with_critic,
    }
    out = Path(args.out) if args.out else run_dirs[0].parent / f"aggregate-{args.task}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"задача {args.task}: k={k}, pooled Δ={pooled:+.2f}, MDD={mdd}, вердикт: {verdict}")
    print(f"артефакт: {out}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
