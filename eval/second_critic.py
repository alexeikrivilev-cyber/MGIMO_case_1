#!/usr/bin/env python3
"""second_critic.py — критик #2 для DEV-протокола двух критиков (TASK-hermes-13 §1, BRIEF п.23).

Предрегистрация: measurements.md §26 ДО замера. На клетках
(артефакт × рубрика) серии t12, где уже есть оценка критика #1,
прогоняется критик #2: свежая сессия, тот же контракт
(`scripts/run_critic.py`, роль critic), та же рубрика. Считается
согласие: mean |c1 − c2|, sd(c1 − c2), доля клеток с |c1 − c2| ≥ MDD;
вердикты г1/г3 — по предрегистрированным правилам §26.1. г2
(согласие с человеком-судьёй) отложено до возврата суждений владельца
по слепым парам — названо, не подменяется.

Проверка ослепления: промпт критика = артефакт + рубрика; драйвер
проверяет, что в артефактах выборки нет токенов рук (curation/lean/
hybrid/o5a/o5b/hc2/flash/step-5) — иначе клетка помечается дефектом
ослепления (критик #2 знал бы руку).

Частичная оценка: если критик #2 вернул «Итого: N/20 по оценимым
критериям, остальные — н/д» (отказ оценивать критерии 2–3 из
артефакта шага 3), клетка — исход протокола (класс расхождения
интерпретации рубрики), а НЕ провал прогона: исключается из
Δ-статистики и reporting отдельной строкой.

Контракт CLI:
    python3 eval/second_critic.py [--runs-dir DIR] [--dry-run]

Коды возврата: 0 — всё оценено; 1 — часть прогонов упала; 2 — использование.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


score_skills = load_module("score_skills_k3", REPO_ROOT / "eval" / "score_skills_k3.py")
ablation_stats = load_module("ablation_stats", REPO_ROOT / "eval" / "ablation_stats.py")

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2

# Токены рук — при находке в артефакте клетка помечается дефектом
# ослепления (критик #2 узнал бы руку из преамбулы).
ARM_TOKENS = ("curation", "lean", "hybrid", "o5a", "o5b", "hc2", "flash", "step-5",
              "step-3.7", "council", "critic-loop", "t12-skills", "eval/runs")

# Выборка (§26.2, фиксирована ДО прогона):
# (а) 18 клеток серии t12 под единой рубрикой;
# (б) 9 клеток под типовой с вырожденным паттерном критика #1.
SAMPLE: list[tuple[str, str, str]] = []
for _arm in ("curation", "lean", "hybrid"):
    for _i in range(3):
        SAMPLE.append((f"research-{_arm}-{_i}-unified", f"research/{_arm}/final{'' if _i == 0 else f'-{_i}'}.md", "unified"))
        SAMPLE.append((f"options-{_arm}-{_i}-unified", f"options/{_arm}/final{'' if _i == 0 else f'-{_i}'}.md", "unified"))
for _arm in ("lean",):
    for _i in range(3):
        SAMPLE.append((f"reslean-typ-{_i}", f"research/{_arm}/final{'' if _i == 0 else f'-{_i}'}.md", "typical"))
        SAMPLE.append((f"o5alean-typ-{_i}", f"o5a/{_arm}/final{'' if _i == 0 else f'-{_i}'}.md", "typical"))
        SAMPLE.append((f"o5bF-typ-{_i}", f"o5b-F/skill/final{'' if _i == 0 else f'-{_i}'}.md", "typical"))

# Частичная оценка: критик дал «Итого: N/20 по оценимым критериям» и
# явно отказался оценивать остальные (н/д) — содержимое есть, но
# машинно-сравнимого /40 нет. Это НЕ провал прогона и НЕ мусорный
# выход: это исход протокола — расхождение интерпретации рубрики
# (критик #1 такой клетке поставил /40, критик #2 часть критериев
# счёл неоценимой из артефакта). Клетка исключается из Δ-статистики
# и Reporting как класс расхождения. Общая логика — score_ablation.


def assess_critic_out(text: str) -> dict:
    """Разбор выхода критика #2: полная оценка / частичная / провал."""
    return score_skills.assess_scores(text)


def rubric_path(rubric: str, group: str) -> str:
    """Единая — hackathon-criteria; типовая — под семейство артефакта
    (research/o5a/hc2 → rubric-research, options/o5b → rubric-options)."""
    if rubric == "unified":
        return "eval/rubrics/hackathon-criteria.md"
    if group in ("research", "o5a", "hc2"):
        return "eval/rubrics/rubric-research.md"
    return "eval/rubrics/rubric-options.md"


def first_scores(records: list[dict]) -> dict[tuple[str, str, int, str], float]:
    """Оценки критика #1 из summary.json серии t12 (ключ — клетка)."""
    out: dict[tuple[str, str, int, str], float] = {}
    for r in records:
        if r.get("total40") is None:
            continue
        out[(r["group"], r["arm"], r["i"], r["rubric"])] = float(r["total40"])
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="second_critic.py",
        description="Критик #2: межкритическое согласие на клетках серии t12 (TASK-hermes-13 §26).",
    )
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "eval" / "runs" / "t12-skills"))
    parser.add_argument("--out", default=str(REPO_ROOT / "eval" / "runs" / "t13-twocritic"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    out_dir = Path(args.out)
    summary_path = runs_dir / "scores" / "summary.json"
    if not summary_path.is_file():
        print(f"не найден {summary_path} — сначала eval/score_skills_k3.py", file=sys.stderr)
        return EXIT_USAGE
    records = json.loads(summary_path.read_text(encoding="utf-8"))["records"]
    c1 = first_scores(records)

    # Клетки выборки → оценка критика #1 (группа/рука/i из имени артефакта).
    cells: list[dict] = []
    for cell_id, rel, rubric in SAMPLE:
        artifact = runs_dir / rel
        if not artifact.is_file():
            print(f"артефакт не найден: {artifact}", file=sys.stderr)
            return EXIT_USAGE
        # группу/руку/i восстанавливаем из пути: <group>/<arm>/final[-i].md
        parts = rel.split("/")
        group, arm = parts[0], parts[1]
        m = re.search(r"final(?:-(\d))?\.md$", parts[2])
        i = int(m.group(1)) if m and m.group(1) else 0
        score1 = c1.get((group, arm, i, rubric))
        text = artifact.read_text(encoding="utf-8-sig", errors="replace")
        leak = [t for t in ARM_TOKENS if re.search(rf"\b{re.escape(t)}\b", text, re.IGNORECASE)]
        cells.append({"id": cell_id, "artifact": str(artifact), "rubric": rubric,
                      "group": group, "arm": arm, "i": i, "score1": score1,
                      "blinding_leak": leak})

    if args.dry_run:
        for cell in cells:
            print(f"[dry-run] {cell['id']}: рубрика {cell['rubric']}, c1={cell['score1']}, "
                  f"leak={cell['blinding_leak'] or '—'}")
        return EXIT_OK

    failures = 0
    partials: list[str] = []
    for cell in cells:
        out_cell = out_dir / cell["id"]
        critic_out = out_cell / "critic.out"
        res: dict = {}
        if critic_out.is_file() and critic_out.read_text(encoding="utf-8", errors="replace").strip():
            res = assess_critic_out(critic_out.read_text(encoding="utf-8", errors="replace"))
            if res.get("total40") is None and not res.get("partial"):
                res["error"] = "Итого не распознан в существующем critic.out"
        else:
            tag = f"t13-c2-{cell['id']}"[:36]
            res = score_skills.run_critic(
                Path(cell["artifact"]), rubric_path(cell["rubric"], cell["group"]), out_cell, tag
            )
            if res.get("total40") is None:
                res = assess_critic_out((out_cell / "critic.out").read_text(
                    encoding="utf-8", errors="replace")) if (out_cell / "critic.out").is_file() else res
        cell["score2"] = res.get("total40")
        cell["error"] = res.get("error")
        if res.get("partial"):
            partials.append(cell["id"])
        elif res.get("error") or res.get("total40") is None:
            failures += 1
        print(f"{cell['id']}: c1={cell['score1']} c2={cell['score2']}"
              + (f" ЧАСТИЧНО: {res['error']}" if res.get("partial")
                 else f" ПРОВАЛ: {res['error']}" if res.get("error") else ""))

    # Статистика согласия по рубрикам.
    lines = [
        "# Критик #2 — межкритическое согласие (TASK-hermes-13 §26)",
        "",
        "Драйвер: `eval/second_critic.py`. Предрегистрация — measurements.md §26 ДО замера.",
        "Выборка: 27 клеток серии t12 (18 единая + 9 типовая с вырожденным паттерном).",
        "",
    ]
    payload: dict[str, dict] = {}
    for rubric in ("unified", "typical"):
        rows = [c for c in cells if c["rubric"] == rubric
                and c["score1"] is not None and c["score2"] is not None]
        if not rows:
            continue
        diffs = [c["score2"] - c["score1"] for c in rows]
        abs_diffs = [abs(d) for d in diffs]
        mean_ad = sum(abs_diffs) / len(abs_diffs)
        var = sum((d - sum(diffs) / len(diffs)) ** 2 for d in diffs) / (len(diffs) - 1) if len(diffs) > 1 else 0.0
        sd_d = math.sqrt(var)
        sd_noise = ablation_stats.NOISE[rubric]["sd"]
        mdd1 = ablation_stats.mdd_two_arm(1, sd_noise)
        beyond = sum(1 for d in abs_diffs if d >= mdd1)
        share = beyond / len(rows)
        lines.append(f"## Рубрика {rubric} (n={len(rows)})")
        lines.append("")
        lines.append("| Клетка | c1 | c2 | Δ |")
        lines.append("|---|---|---|---|")
        for c, d in zip(rows, diffs):
            lines.append(f"| {c['id']} | {c['score1']} | {c['score2']} | {d:+.1f} |")
        lines.append("")
        lines.append(f"- mean |Δ| = {mean_ad:.2f}; sd(Δ) = {sd_d:.2f}")
        lines.append(f"- шум повтора одного критика (измеренный): sd {sd_noise}")
        lines.append(f"- отношение sd(Δ)/шум = {sd_d / sd_noise:.2f}")
        lines.append(f"- клеток с |Δ| ≥ MDD(n=1)={mdd1:.2f}: {beyond}/{len(rows)} ({share:.0%})")
        verdict_g1 = ("критики близки к независимым (≤2×)" if sd_d <= 2 * sd_noise
                      else "системное расхождение (>2×) — адъюдикация обязательна")
        verdict_g3 = ("согласие адекватно (≤10%)" if share <= 0.10
                      else "согласие слабое (>25%) — находка достоверна только при согласии двух"
                      if share > 0.25 else "согласие среднее (10–25%)")
        lines.append(f"- вердикт г1: {verdict_g1}")
        lines.append(f"- вердикт г3: {verdict_g3}")
        lines.append("")
        payload[rubric] = {"n": len(rows), "mean_abs_delta": mean_ad, "sd_delta": sd_d,
                           "noise_sd": sd_noise, "ratio": sd_d / sd_noise,
                           "beyond_mdd": beyond, "share_beyond_mdd": share,
                           "verdict_g1": verdict_g1, "verdict_g3": verdict_g3,
                           "cells": [{"id": c["id"], "c1": c["score1"], "c2": c["score2"]} for c in rows]}

    leaks = [c["id"] for c in cells if c["blinding_leak"]]
    lines.append("## Частичные оценки (критик #2 отказался оценивать часть критериев)")
    lines.append("")
    if partials:
        lines.append(f"Клеток: {len(partials)} — {partials}")
        lines.append("")
        lines.append("Класс расхождения интерпретации рубрики: критик #1 таким клеткам")
        lines.append("поставил /40 (оценил все критерии), критик #2 счёл критерии 2–3")
        lines.append("неоценимыми из артефакта шага 3 и дал оценку только по оценимым.")
        lines.append("Для г1/г3 клетки исключены из Δ-статистики (нет машинно-сравнимой")
        lines.append("оценки); как класс — свидетельство, что единая рубрика на артефакте")
        lines.append("шага 3 воспринимается критиками по-разному.")
    else:
        lines.append("Нет.")
    lines.append("")
    lines.append("## Проверка ослепления")
    lines.append("")
    lines.append(f"Клеток с токенами рук в артефакте: {len(leaks)}"
                 + (f" — {leaks}" if leaks else " — ослепление чистое"))
    lines.append("")
    lines.append("г2 (согласие с человеком-судьёй) отложено до возврата суждений")
    lines.append("владельца по слепым парам (§26.1) — названо, не подменяется.")
    lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "twocritic-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "twocritic-summary.json").write_text(
        json.dumps({"rubrics": payload, "blinding_leaks": leaks, "failures": failures,
                    "partial_assessments": partials},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nитог: падений {failures}, частичных оценок {len(partials)}; "
          f"summary: {out_dir / 'twocritic-summary.md'}")
    return EXIT_OK if failures == 0 else EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
