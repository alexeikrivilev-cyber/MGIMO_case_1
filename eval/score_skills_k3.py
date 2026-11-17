#!/usr/bin/env python3
"""score_skills_k3.py — оценивание серии k=3 по дизайну навыков + О5 (TASK-hermes-12).

Предрегистрация: measurements.md §25.1/§25.2 ДО прогонов. Каждый
артефакт каждой руки оценивается свежей сессией критика
(`scripts/run_critic.py`, режим critic) под КАЖДОЙ рубрикой:
research-артефакты — единая (hackathon-criteria) + типовая
(rubric-research); options-артефакты — единая + типовая
(rubric-options). Рубрика под тип артефакта — принцип H2 (§19.1).

Идемпотентность (урок t11): готовый непустой critic.out с распознанным
«Итого» переиспользуется — защита от двойной оплаты при перезапуске.
Пустой/непарсящийся выход — прогон НЕ засчитан и перезапускается
(дефект «exit 0 ≠ непустой выход», TASK-hermes-5/9).

Статистика — отдельный драйвер `eval/skills_k3_stats.py`.

Контракт CLI:
    python3 eval/score_skills_k3.py [--runs-dir DIR] [--groups ...]
        [--dry-run]

Коды возврата: 0 — всё оценено; 1 — часть прогонов упала; 2 — использование.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from score_ablation import RUBRICS, assess_scores, parse_scores, run_critic  # noqa: E402

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2

# Семейства артефактов: группа → (подкаталог, руки, типовая рубрика).
# Единая рубрика — hackathon-criteria для всех (как в rescore/score_ablation).
FAMILIES = {
    "research": {"arms": ("curation", "lean", "hybrid"), "typical": "rubric-research.md"},
    "options": {"arms": ("curation", "lean", "hybrid"), "typical": "rubric-options.md"},
    "o5a": {"arms": ("lean",), "typical": "rubric-research.md"},
    "o5b-P": {"arms": ("skill",), "typical": "rubric-options.md"},
    "o5b-F": {"arms": ("skill",), "typical": "rubric-options.md"},
    "hc2": {"arms": ("revised",), "typical": "rubric-research.md"},
    # H-SI1 (TASK-hermes-15 §28.1): навык с патчами по замеру против
    # навыка без патчей; артефакт — research, поэтому типовая рубрика
    # исследовательская.
    "si": {"arms": ("si-off", "si-on"), "typical": "rubric-research.md"},
}

# Короткие код группы для тега (хук режет «Шаг» до 40 символов, плюс
# префикс «О4: » от run_critic — тег обязан быть ≤36).
TAG_CODES = {"research": "res", "options": "opt", "o5a": "o5a", "o5b-P": "o5bP",
             "o5b-F": "o5bF", "hc2": "hc2", "si": "si"}

CHAIN_FILES = ("final.md", "final-1.md", "final-2.md")


def collect_artifacts(runs_dir: Path, group: str, k: int) -> dict[str, list[Path]]:
    """Файлы цепочек руки: final.md / final-1.md / final-2.md (конвенция
    генератора; k<3 — сколько есть)."""
    fam = FAMILIES[group]
    out: dict[str, list[Path]] = {}
    for arm in fam["arms"]:
        arm_dir = runs_dir / group / arm
        files = [arm_dir / name for name in CHAIN_FILES[:k]]
        out[arm] = [p for p in files if p.is_file()]
    return out


def rubrics_for(group: str) -> dict[str, str]:
    fam = FAMILIES[group]
    return {"unified": RUBRICS["unified"], "typical": f"eval/rubrics/{fam['typical']}"}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="score_skills_k3.py",
        description="Оценивание серии навыков k=3: свежий критик на артефакт × рубрику.",
    )
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "eval" / "runs" / "t12-skills"))
    parser.add_argument("--groups", default=",".join(FAMILIES))
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--out-subdir", default="scores",
                        help="подкаталог runs-dir для оценок этого прохода (разделение критиков)")
    parser.add_argument("--tag-prefix", default="t12",
                        help="префикс тега прогона для атрибуции стоимости (COST.md)")
    parser.add_argument("--critic-id", default="c1",
                        help="идентификатор критика в записях (протокол двух критиков, §27.2-А)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    unknown = [g for g in groups if g not in FAMILIES]
    if unknown:
        print(f"неизвестные группы: {unknown}; доступно: {list(FAMILIES)}", file=sys.stderr)
        return EXIT_USAGE

    if args.dry_run:
        for group in groups:
            for arm, files in collect_artifacts(runs_dir, group, args.k).items():
                print(f"[dry-run] {group}/{arm}: {len(files)} артефактов: {[f.name for f in files]}")
        return EXIT_OK

    failures = 0
    records: list[dict] = []
    # Слияние с существующей summary.json (урок TASK-hermes-12: прогон
    # подмножеством групп перезаписывал накопленные записи). Ключ записи —
    # (critic, group, arm, i, rubric); новые записи заменяют старые с тем
    # же ключом. Summary читается/пишется в подкаталоге прохода
    # (--out-subdir): критические проходы разных критиков не смешиваются.
    scores_root = runs_dir / args.out_subdir
    summary_path = scores_root / "summary.json"
    if summary_path.is_file():
        try:
            old = json.loads(summary_path.read_text(encoding="utf-8")).get("records", [])
            records.extend(r for r in old if isinstance(r, dict))
        except (json.JSONDecodeError, OSError):
            pass
    for group in groups:
        rubrics = rubrics_for(group)
        for arm, files in collect_artifacts(runs_dir, group, args.k).items():
            if not files:
                failures += 1
                print(f"{group}/{arm}: артефакты не найдены", file=sys.stderr)
                continue
            for i, artifact in enumerate(files):
                for rubric_name, rubric_path in rubrics.items():
                    code = TAG_CODES[group]
                    tag = f"{args.tag_prefix}-{code}-{arm}-{i}-{rubric_name}"[:36]
                    out_dir = scores_root / f"{group}-{arm}-{i}-{rubric_name}"
                    critic_out = out_dir / "critic.out"
                    res: dict = {}
                    if critic_out.is_file() and critic_out.read_text(encoding="utf-8", errors="replace").strip():
                        # Идемпотентность: уже оцененный прогон не повторяем.
                        res = assess_scores(critic_out.read_text(encoding="utf-8", errors="replace"))
                        res["source"] = str(critic_out)
                        if res.get("total40") is None and not res.get("partial"):
                            res["error"] = "Итого не распознан в существующем critic.out"
                    else:
                        res = run_critic(artifact, rubric_path, out_dir, tag)
                        # Переразбор свежего выхода через assess_scores:
                        # run_critic зовёт parse_scores напрямую и НЕ ловит
                        # частичную оценку нового формата («24/40 по
                        # оценимому» counted как полная — дефект
                        # TASK-hermes-15, менявший знак Δ).
                        if critic_out.is_file():
                            reparsed = assess_scores(
                                critic_out.read_text(encoding="utf-8", errors="replace"))
                            reparsed["source"] = str(critic_out)
                            if (reparsed.get("total40") is None
                                    and not reparsed.get("partial")
                                    and not res.get("error")):
                                reparsed["error"] = "Итого не распознан в critic.out"
                            res = reparsed
                    if res.get("error") and not res.get("partial"):
                        # Частичная оценка — класс протокола (§26.4), не
                        # провал прогона: она не должна удовать exit-код.
                        failures += 1
                    record = {
                        "critic": args.critic_id,
                        "group": group, "arm": arm, "i": i, "rubric": rubric_name,
                        # Частичная оценка — не сравнимая клетка (§26.4):
                        # total40 = None, класс назван в error.
                        "total40": None if res.get("partial") else res.get("total40"),
                        "partial": bool(res.get("partial")),
                        "findings_total": res.get("findings_total"),
                        "findings_important": res.get("findings_important"),
                        "artifact": str(artifact),
                        "error": res.get("error"),
                    }
                    key = (args.critic_id, group, arm, i, rubric_name)
                    records = [r for r in records
                               if (r.get("critic"), r.get("group"), r.get("arm"), r.get("i"), r.get("rubric")) != key]
                    records.append(record)
                    print(f"{group}/{arm}#{i} {rubric_name} [{args.critic_id}]: {res.get('total40')}"
                          + (f" ЧАСТИЧНО: {res['error']}" if res.get("partial")
                             else f" ПРОВАЛ: {res['error']}" if res.get("error") else ""))

    scores_root.mkdir(parents=True, exist_ok=True)
    (scores_root / "summary.json").write_text(
        json.dumps({"records": records, "failures": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Оценивание серии навыков k=3 (TASK-hermes-12 §25.1/§25.2)",
        "",
        f"Числа — из `summary.json`; критические прогоны — "
        f"`{args.out_subdir}/<group>-<arm>-<i>-<rubric>/critic.out`",
        f"(теги COST.md «О4: {args.tag_prefix}-…»). Свежая сессия критика на артефакт × рубрику.",
        "",
        "| Группа | Рука | # | Рубрика | /40 | findings (важно) |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        if r.get("error") and r.get("total40") is None:
            kind = "ЧАСТИЧНАЯ ОЦЕНКА" if str(r.get("error", "")).startswith("частичная") else "ПРОВАЛ"
            lines.append(f"| {r.get('group')} | {r.get('arm')} | {r.get('i')} | {r.get('rubric')} | {kind}: {r.get('error')} | |")
            continue
        lines.append(
            f"| {r.get('group')} | {r.get('arm')} | {r.get('i')} | {r.get('rubric')} | {r.get('total40')} "
            f"| {r.get('findings_total')} ({r.get('findings_important')}) |"
        )
    (scores_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nитог: прогонов {len(records)}, падений {failures}; summary: {scores_root / 'summary.md'}")
    return EXIT_OK if failures == 0 else EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
