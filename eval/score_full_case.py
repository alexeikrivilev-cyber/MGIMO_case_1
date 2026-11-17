#!/usr/bin/env python3
"""score_full_case.py — оценка финальной цепочки артефактов кейса
двумя изолированными критиками + ось слепых зон как диагностика
(TASK-hermes-18 §32.1).

Протокол (dev, не прод):
- критик #1 и критик #2 — независимые свежие сессии
  (`scripts/run_critic.py`, изоляция промпт-уровня), единая рубрика
  (`eval/rubrics/hackathon-criteria.md`), на всех 6 артефактах цепочки;
- критик #1 дополнительно — типовые рубрики там, где они названы
  (research → `rubric-research.md`, options → `rubric-options.md`);
  для шагов 4–5 типовой рубрики нет (TASK-8: именованный допуск —
  hackathon-criteria как рубрика артефактов шага 4);
- ось слепых зон (`eval/rubrics/hackathon-criteria-bs.md` версия 2):
  база /40 1:1 + ОТДЕЛЬНАЯ ось 5.1–5.3 (/30) — ДИАГНОСТИКА. Вердиктов
  человека на новой цепочке нет, поэтому ось не валидируется и в балл
  не входит (урок §31.4).

Частичная оценка («по оценимым…») — исход протокола §26.4: клетка
исключается из сравнения и требует добора, не считается нулём.

Идемпотентность (урок t11): готовый непустой critic.out с распознанным
итогом переиспользуется; иначе — перепрогон. Один раннер за раз
(метка прогона — отдельный файл eval/.cost-label, урок TASK-6).

Контракт CLI:
    python3 eval/score_full_case.py --task demo-retention
        [--runs-dir DIR] [--dry-run] [--force]

Коды возврата: 0 — все клетки распознаны (полные оценки); 1 — ошибка
использования; 4 — часть клеток провалилась/частичная (нужен добор).
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from blindspot_axis import parse_axes  # noqa: E402
from score_ablation import assess_scores  # noqa: E402
import run_label  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_CELLS_FAILED = 4

UNITARY = "eval/rubrics/hackathon-criteria.md"
BS_V2 = "eval/rubrics/hackathon-criteria-bs.md"
TYPICAL_BY_STEP = {
    "research.md": "eval/rubrics/rubric-research.md",
    "options.md": "eval/rubrics/rubric-options.md",
}
# MDD единой рубрики при n=1 — пересчёт из измеренного шума (§22.2):
# sd 1.414 (два наблюдения), порог ≈ 4.1 при мощности 0.8.
MDD_UNIFIED_N1 = 4.1
# Шум единой рубрики между двумя критиками (§26): sd(Δ)=1.41,
# системное расхождение 4.94 = 3.5× шума; типовая — 1.82×.
NOISE_SD_UNIFIED = 1.41

CHAIN = ("research.md", "options.md", "strategy-product.md",
         "strategy-comms.md", "verification-plan.md", "decisions.md")
ART_SHORT = {
    "research.md": "res", "options.md": "opt",
    "strategy-product.md": "sp", "strategy-comms.md": "sc",
    "verification-plan.md": "vp", "decisions.md": "dec",
}

TASKS = {
    "demo-retention": "eval/runs/t18-case",
    "heldout-growth-segment": "eval/runs/t18-case-heldout",
}


def set_label(tag: str) -> None:
    run_label.set_run_label(f"О4: {tag}")


def clear_label() -> None:
    run_label.clear_run_label()


def run_critic_cell(artifact: Path, rubric: str, out_dir: Path, tag: str,
                    timeout: int = 1800) -> dict:
    """Одна клетка оценки: свежая сессия критика + разбор выхода."""
    out_dir.mkdir(parents=True, exist_ok=True)
    set_label(tag)
    try:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "run_critic.py"),
             "--artifact", str(artifact), "--rubric", rubric,
             "--mode", "critic", "--out", str(out_dir), "--tag", tag,
             "--timeout", str(timeout)],
            cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=timeout + 60)
    finally:
        clear_label()
    critic_out = out_dir / "critic.out"
    if proc.returncode != 0 or not critic_out.is_file():
        return {"error": f"run_critic exit={proc.returncode}",
                "partial": False}
    text = critic_out.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        # Дефект «exit 0 ≠ непустой выход» (TASK-5/9): пустой выход —
        # не измерение.
        return {"error": "пустой выход при exit=0", "partial": False}
    if rubric == BS_V2:
        parsed = parse_axes(text)
        return {"base40": parsed["base40"], "axis30": parsed["axis30"],
                "items": parsed["items"], "partial": parsed["partial"],
                "error": None if parsed["base40"] is not None
                else "база /40 не распознана"}
    scores = assess_scores(text)
    scores.setdefault("partial", False)
    return scores


def collect(task: str, runs_dir: Path, force: bool) -> tuple[dict, list]:
    """Все клетки оценки: (результаты, проблемы)."""
    artifacts_dir = runs_dir / "artifacts"
    eval_dir = runs_dir / "eval"
    results: dict = {}
    problems: list[str] = []
    cells: list[tuple[str, str, str, str]] = []
    for name in CHAIN:
        for critic in ("c1", "c2"):
            cells.append((critic, name, UNITARY, "uni"))
        typical = TYPICAL_BY_STEP.get(name)
        if typical:
            cells.append(("c1", name, typical, "typ"))
        cells.append(("axis", name, BS_V2, "bs"))
    for critic, name, rubric, rub in cells:
        art = ART_SHORT[name]
        cell_dir = eval_dir / f"{critic}-{art}-{rub}"
        critic_out = cell_dir / "critic.out"
        if (not force and critic_out.is_file()
                and critic_out.stat().st_size > 0):
            text = critic_out.read_text(encoding="utf-8-sig", errors="replace")
            if rubric == BS_V2:
                parsed = parse_axes(text)
                cell = {"base40": parsed["base40"], "axis30": parsed["axis30"],
                        "items": parsed["items"], "partial": parsed["partial"]}
            else:
                cell = assess_scores(text)
                cell.setdefault("partial", False)
            if cell.get("base40") is not None or cell.get("total40") is not None:
                results[f"{critic}-{art}-{rub}"] = cell
                print(f"[{critic}-{art}-{rub}] переиспользован", flush=True)
                continue
            if cell.get("partial"):
                problems.append(f"{critic}-{art}-{rub}: частичная оценка "
                                f"(требует добора по §26.4)")
                results[f"{critic}-{art}-{rub}"] = cell
                continue
        cell = run_critic_cell(artifacts_dir / name, rubric, cell_dir,
                               f"t18-ev-{critic}-{art}-{rub}")
        results[f"{critic}-{art}-{rub}"] = cell
        if cell.get("error"):
            problems.append(f"{critic}-{art}-{rub}: {cell['error']}")
        elif cell.get("partial"):
            problems.append(f"{critic}-{art}-{rub}: частичная оценка "
                            f"(требует добора по §26.4)")
        print(f"[{critic}-{art}-{rub}] exit-ok error={cell.get('error')}",
              flush=True)
    return results, problems


def agreement(rows: list[tuple[str, float, float]]) -> dict:
    """Согласие двух критиков: mean|c1−c2|, sd, доля ≥ MDD."""
    diffs = [abs(a - b) for _, a, b in rows]
    if not diffs:
        return {"n": 0}
    return {
        "n": len(diffs),
        "mean_abs": round(statistics.fmean(diffs), 2),
        "sd": round(statistics.stdev(diffs), 2) if len(diffs) > 1 else None,
        "max_abs": round(max(diffs), 2),
        "share_ge_mdd": round(sum(1 for d in diffs if d >= MDD_UNIFIED_N1)
                              / len(diffs), 2),
        "mdd": MDD_UNIFIED_N1,
        "noise_sd": NOISE_SD_UNIFIED,
    }


def build_report(task: str, results: dict, problems: list) -> str:
    lines = [
        f"# Оценка финальной цепочки кейса — {task} (TASK-hermes-18 §32.1)",
        "",
        "Протокол dev: критик #1 и критик #2 — независимые свежие сессии,",
        "единая рубрика; критик #1 — типовые рубрики там, где названы;",
        "ось слепых зон (рубрика v2) — ДИАГНОСТИКА (вердиктов человека на",
        "цепочке нет — не валидация). Частичная оценка = исход протокола",
        "§26.4 (добор, не ноль).",
        "",
        "## Баллы по артефактам",
        "",
        "| Артефакт | c1 (единая) | c2 (единая) | |c1−c2| | c1 (типовая) | "
        "ось: база | ось 5.1–5.3 |",
        "|---|---|---|---|---|---|---|",
    ]
    pair_rows: list[tuple[str, float, float]] = []
    for name in CHAIN:
        art = ART_SHORT[name]
        c1 = results.get(f"c1-{art}-uni", {})
        c2 = results.get(f"c2-{art}-uni", {})
        typ = results.get(f"c1-{art}-typ", {})
        axis = results.get(f"axis-{art}-bs", {})
        v1 = c1.get("total40")
        v2 = c2.get("total40")
        if v1 is not None and v2 is not None:
            pair_rows.append((name, v1, v2))
        diff = f"{abs(v1 - v2):.1f}" if v1 is not None and v2 is not None else "—"
        lines.append(
            f"| {name} | {fmt(v1, c1)} | {fmt(v2, c2)} | {diff} | "
            f"{fmt(typ.get('total40'), typ)} | {fmt(axis.get('base40'), axis)} | "
            f"{axis.get('axis30', '—')} |")
    lines += ["", "## Согласие двух критиков (единая рубрика)", ""]
    if pair_rows:
        stats = agreement(pair_rows)
        lines += [
            f"- клеток с полной оценкой у обоих: {stats['n']} из {len(CHAIN)}",
            f"- mean |c1−c2| = {stats['mean_abs']} (шум сессии судьи "
            f"sd={stats['noise_sd']}, §26)",
            f"- sd(|c1−c2|) = {stats['sd']}",
            f"- максимум |c1−c2| = {stats['max_abs']}",
            f"- доля клеток с |c1−c2| ≥ MDD({stats['mdd']}) = "
            f"{stats['share_ge_mdd']}",
            "- интерпретация — по §26: единая рубрика давала системное "
            "расхождение (3.5× шума), типовая — близко к независимым "
            "(1.82×). Наблюдение, не вердикт (P4 §32.1).",
        ]
    else:
        lines.append("- пар с полной оценкой у обоих критиков нет "
                     "(добор не выполнен).")
    unstable = []
    for key, cell in sorted(results.items()):
        passes = cell.get("passes") or []
        vals = ([cell["total40"]] if cell.get("total40") is not None else []) + passes
        if len(vals) > 1 and max(vals) - min(vals) > NOISE_SD_UNIFIED:
            unstable.append((key, vals))
    if unstable:
        lines += ["", "## Нестабильность клеток (разброс проходов > шума судьи)", ""]
        for key, vals in unstable:
            lines.append(f"- {key}: значения {vals} — разброс "
                         f"{max(vals) - min(vals):.1f} > шума {NOISE_SD_UNIFIED}; "
                         f"итог берётся по финальному проходу, самоотчёт "
                         f"модели о стабильности с таким разбросом "
                         f"противоречив (названо, не спрятано)")

    lines += ["", "## Ось слепых зон (диагностика, не балл)", ""]
    for name in CHAIN:
        axis = results.get(f"axis-{ART_SHORT[name]}-bs", {})
        items = axis.get("items") or {}
        detail = ", ".join(f"5.{k[-1]}={v}" for k, v in sorted(items.items()))
        lines.append(f"- {name}: ось {axis.get('axis30', '—')}/30 "
                     f"({detail or 'пункты не распознаны'})")
    if problems:
        lines += ["", "## Проблемы клеток (добор по §26.4)", ""]
        lines += [f"- {p}" for p in problems]
    lines += ["", "## Наблюдения против предсказаний §32.1", "",
              "- P3 (форма ответа): сравнить mean базы артефактов шага 4 "
              "против options шага 3 — строка ниже.",
              ]
    step4 = [results.get(f"c1-{ART_SHORT[n]}-uni", {}).get("total40")
             for n in ("strategy-product.md", "strategy-comms.md",
                       "verification-plan.md")]
    step4 = [v for v in step4 if v is not None]
    opt = results.get(f"c1-opt-uni", {}).get("total40")
    if step4 and opt is not None:
        lines.append(f"- mean(шаг 4) = {statistics.fmean(step4):.1f} "
                     f"против options = {opt} → P3 "
                     f"{'выполнено' if statistics.fmean(step4) > opt else 'НЕ выполнено'}")
    else:
        lines.append("- P3: недостаточно полных оценок для сравнения.")
    return "\n".join(lines) + "\n"


def fmt(value, cell: dict) -> str:
    if value is None:
        if cell.get("partial"):
            return "частичная"
        return "—"
    return f"{value:g}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="score_full_case.py",
        description="Оценка финальной цепочки двумя изолированными "
                    "критиками + ось как диагностика (TASK-hermes-18 §32.1).")
    parser.add_argument("--task", required=True, choices=sorted(TASKS))
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    runs_dir = (Path(args.runs_dir) if args.runs_dir
                else REPO_ROOT / TASKS[args.task])
    if args.dry_run:
        print(f"task={args.task} runs-dir={runs_dir}")
        print("клетки: c1/c2 × единая × 6 артефактов; c1 × типовая "
              "(research, options); ось (bs v2) × 6 — диагностика")
        return EXIT_OK
    results, problems = collect(args.task, runs_dir, args.force)
    report = build_report(args.task, results, problems)
    eval_dir = runs_dir / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "summary.md").write_text(report, encoding="utf-8")
    (eval_dir / "summary.json").write_text(
        json.dumps({"results": results, "problems": problems},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"отчёт: {eval_dir / 'summary.md'}")
    print(f"проблемы: {len(problems)}")
    return EXIT_OK if not problems else EXIT_CELLS_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
