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

from score_ablation import RUBRICS, parse_scores, run_critic  # noqa: E402

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
}

# Короткие код группы для тега (хук режет «Шаг» до 40 символов, плюс
# префикс «О4: » от run_critic — тег обязан быть ≤36).
TAG_CODES = {"research": "res", "options": "opt", "o5a": "o5a", "o5b-P": "o5bP",
             "o5b-F": "o5bF", "hc2": "hc2"}

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
    # подмножества групп перезаписывал накопленные записи). Ключ записи —
    # (group, arm, i, rubric); новые записи заменяют старые с тем же ключом.
    summary_path = runs_dir / "scores" / "summary.json"
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
                    tag = f"t12-{code}-{arm}-{i}-{rubric_name}"[:36]
                    out_dir = runs_dir / "scores" / f"{group}-{arm}-{i}-{rubric_name}"
                    critic_out = out_dir / "critic.out"
                    res: dict = {}
                    if critic_out.is_file() and critic_out.read_text(encoding="utf-8", errors="replace").strip():
                        # Идемпотентность: уже оцененный прогон не повторяем.
                        res = parse_scores(critic_out.read_text(encoding="utf-8", errors="replace"))
                        res["source"] = str(critic_out)
                        if res.get("total40") is None:
                            res["error"] = "Итого не распознан в существующем critic.out"
                    else:
                        res = run_critic(artifact, rubric_path, out_dir, tag)
                    if "error" in res:
                        failures += 1
                    record = {
                        "group": group, "arm": arm, "i": i, "rubric": rubric_name,
                        "total40": res.get("total40"),
                        "findings_total": res.get("findings_total"),
                        "findings_important": res.get("findings_important"),
                        "artifact": str(artifact),
                        "error": res.get("error"),
                    }
                    key = (group, arm, i, rubric_name)
                    records = [r for r in records
                               if (r.get("group"), r.get("arm"), r.get("i"), r.get("rubric")) != key]
                    records.append(record)
                    print(f"{group}/{arm}#{i} {rubric_name}: {res.get('total40')}"
                          + (f" ПРОВАЛ: {res['error']}" if res.get("error") else ""))

    (runs_dir / "scores").mkdir(parents=True, exist_ok=True)
    (runs_dir / "scores" / "summary.json").write_text(
        json.dumps({"records": records, "failures": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Оценивание серии навыков k=3 (TASK-hermes-12 §25.1/§25.2)",
        "",
        "Числа — из `summary.json`; критические прогоны — `scores/<group>-<arm>-<i>-<rubric>/critic.out`",
        "(теги COST.md «О4: t12-…»). Свежая сессия критика на артефакт × рубрику.",
        "",
        "| Группа | Рука | # | Рубрика | /40 | findings (важно) |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        if r.get("error") and r.get("total40") is None:
            lines.append(f"| {r.get('group')} | {r.get('arm')} | {r.get('i')} | {r.get('rubric')} | ПРОВАЛ: {r.get('error')} | |")
            continue
        lines.append(
            f"| {r.get('group')} | {r.get('arm')} | {r.get('i')} | {r.get('rubric')} | {r.get('total40')} "
            f"| {r.get('findings_total')} ({r.get('findings_important')}) |"
        )
    (runs_dir / "scores" / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nитог: прогонов {len(records)}, падений {failures}; summary: {runs_dir / 'scores' / 'summary.md'}")
    return EXIT_OK if failures == 0 else EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
