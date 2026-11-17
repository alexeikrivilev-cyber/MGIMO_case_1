#!/usr/bin/env python3
"""rescore_arms.py — реcкоринг рук A/B под ТИПОВЫЕ рубрики (H2) —
проверка целостности измерений (TASK-hermes-7 §1).

Контекст: H2 (TASK-hermes-6 §19.1) показала, что единая рубрика
хакатона имеет потолок «вырезки» на артефактах одного шага
(research 16/40, options 20/40 — основная «важно»-находка про
неприменимые системные критерии). Типовые рубрики (rubric-research,
rubric-options) подняли те же артефакты до 38/36. Все A/B О4/О4-хвоста
мерялись ЕДИНОЙ рубрикой — значит, относительные выводы (порядок рук,
знак дельты) надо перепроверить под типовой.

Что делает скрипт: для каждого артефакта руки запускает критика
(`scripts/run_critic.py`, изолированный контекст, свежая сессия) с
ТИПОВОЙ рубрикой, парсит «Итого /40» и находки тем же контрактом,
что `eval/score_arms.py`, и СРАВНИВАЕТ с единорубриковым замером той
же руки (парсинг существующего `<arm>/critic-final/critic.out`).
Итог — `eval/runs/t7-rescore/summary.json` + `summary.md`.

Анти-круг: демо research/options в режиме critic под типовой рубрикой
УЖЕ измерены в `eval/runs/h2-research/typed`, `eval/runs/h2-options/
typed` — эти прогоны не повторяются, числа берутся оттуда (поле
`reused_from`).

Контракт CLI:
    python3 eval/rescore_arms.py [--dry-run] [--only BUCKET]

Коды возврата: 0 — все прогоны завершились (или --dry-run); 1 —
часть прогонов упала (детали в summary.json).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_PARTIAL = 1

RESCORE_DIR = REPO_ROOT / "eval" / "runs" / "t7-rescore"

# План: bucket → список прогонов.
#   artifact  — файл артефакта руки (относительно корня репозитория);
#   rubric    — типовая рубрика под тип артефакта;
#   mode      — critic | self (как в матрице §12.1);
#   unified   — путь к существующему выходу критика ЕДИНОЙ рубрикой
#               для сравнения (None — нет старого замера);
#   reused_from — путь к УЖЕ измеренному типовому прогону (анти-круг:
#               перепрогон не делается, число берётся оттуда).
PLAN: dict[str, list[dict]] = {
    # Руки шага 3 (артефакт options.md) — рубрика options.
    "opt": [
        {"name": "demo-skill", "artifact": "eval/runs/ab-options-demo-retention/skill/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/ab-options-demo-retention/skill/critic-final/critic.out"},
        {"name": "demo-criticloop", "artifact": "eval/runs/ab-options-demo-retention/critic-loop/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/ab-options-demo-retention/critic-loop/critic-final/critic.out"},
        {"name": "demo-councillite", "artifact": "eval/runs/ab-options-demo-retention/council-lite/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/ab-options-demo-retention/council-lite/critic-final/critic.out"},
        {"name": "heldout-skill", "artifact": "eval/runs/ab-options-heldout-growth-segment/skill/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/ab-options-heldout-growth-segment/skill/critic-final/critic.out"},
        {"name": "heldout-criticloop", "artifact": "eval/runs/ab-options-heldout-growth-segment/critic-loop/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/ab-options-heldout-growth-segment/critic-loop/critic-final/critic.out"},
        {"name": "heldout-councillite", "artifact": "eval/runs/ab-options-heldout-growth-segment/council-lite/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/ab-options-heldout-growth-segment/council-lite/critic-final/critic.out"},
        {"name": "heldout-councilfull", "artifact": "eval/runs/cf-heldout/council-full/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/cf-heldout/council-full/critic-final/critic.out"},
        {"name": "demo-criticloop2", "artifact": "eval/runs/cl2-demo/critic-loop2/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/cl2-demo/critic-loop2/critic-final/critic.out"},
        {"name": "heldout-criticloop2", "artifact": "eval/runs/cl2-heldout/critic-loop2/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/cl2-heldout/critic-loop2/critic-final/critic.out"},
        {"name": "demo-clf", "artifact": "eval/runs/clf-demo/council-lite-flash/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/clf-demo/council-lite-flash/critic-final/critic.out"},
        {"name": "heldout-clf", "artifact": "eval/runs/clf-heldout/council-lite-flash/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/clf-heldout/council-lite-flash/critic-final/critic.out"},
        # Дизайн навыков на шаге 3 (§14.3): lean/hybrid Arms; рука skill —
        # та же, что demo-skill выше (анти-круг, не перепрогоняется).
        {"name": "demo-skills-lean", "artifact": "eval/runs/ab-skills-demo-retention/lean/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/ab-skills-demo-retention/lean/critic-final/critic.out"},
        {"name": "demo-skills-hybrid", "artifact": "eval/runs/ab-skills-demo-retention/hybrid/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/ab-skills-demo-retention/hybrid/critic-final/critic.out"},
    ],
    # Руки шага 2 (артефакт research.md) — рубрика research.
    "res": [
        {"name": "demo-curation", "artifact": "eval/runs/rd-demo/curation/final.md",
         "rubric": "eval/rubrics/rubric-research.md", "mode": "critic",
         "unified": "eval/runs/rd-demo/curation/critic-final/critic.out"},
        {"name": "demo-lean", "artifact": "eval/runs/rd-demo/lean/final.md",
         "rubric": "eval/rubrics/rubric-research.md", "mode": "critic",
         "unified": "eval/runs/rd-demo/lean/critic-final/critic.out"},
        {"name": "demo-hybrid", "artifact": "eval/runs/rd-demo/hybrid/final.md",
         "rubric": "eval/rubrics/rubric-research.md", "mode": "critic",
         "unified": "eval/runs/rd-demo/hybrid/critic-final/critic.out"},
        {"name": "heldout-curation", "artifact": "eval/runs/rh-heldout/curation/final.md",
         "rubric": "eval/rubrics/rubric-research.md", "mode": "critic",
         "unified": "eval/runs/rh-heldout/curation/critic-final/critic.out"},
        {"name": "heldout-lean", "artifact": "eval/runs/rh-heldout/lean/final.md",
         "rubric": "eval/rubrics/rubric-research.md", "mode": "critic",
         "unified": "eval/runs/rh-heldout/lean/critic-final/critic.out"},
        {"name": "heldout-hybrid", "artifact": "eval/runs/rh-heldout/hybrid/final.md",
         "rubric": "eval/rubrics/rubric-research.md", "mode": "critic",
         "unified": "eval/runs/rh-heldout/hybrid/critic-final/critic.out"},
    ],
    # B11: plain-chat ответ — ближайший тип артефакта options
    # (ответ на бриф вариантами/стратегией; допущение названо явно).
    "b11": [
        {"name": "plainchat", "artifact": "eval/runs/b11-plainchat/final.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/b11-plainchat/critic-final/critic.out"},
    ],
    # Критик vs self (§12.1) под типовыми рубриками. Демо-critic УЖЕ
    # измерен в h2-research/h2-options typed (reused_from, анти-круг).
    "cvs": [
        {"name": "demo-research-self", "artifact": "project/research.md",
         "rubric": "eval/rubrics/rubric-research.md", "mode": "self",
         "unified": "eval/runs/critic-matrix/m-demo-research-self/critic.out"},
        {"name": "demo-options-self", "artifact": "project/options.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "self",
         "unified": "eval/runs/critic-matrix/m-demo-options-self/critic.out"},
        {"name": "heldout-research-critic", "artifact": "eval/tasks/heldout-growth-segment/artifacts/research.md",
         "rubric": "eval/rubrics/rubric-research.md", "mode": "critic",
         "unified": "eval/runs/critic-matrix/m-heldout-research-critic/critic.out",
         "reused_from": None},
        {"name": "heldout-research-self", "artifact": "eval/tasks/heldout-growth-segment/artifacts/research.md",
         "rubric": "eval/rubrics/rubric-research.md", "mode": "self",
         "unified": "eval/runs/critic-matrix/m-heldout-research-self/critic.out",
         "reused_from": None},
        {"name": "heldout-options-critic", "artifact": "eval/tasks/heldout-growth-segment/artifacts/options.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "critic",
         "unified": "eval/runs/critic-matrix/m-heldout-options-critic/critic.out",
         "reused_from": None},
        {"name": "heldout-options-self", "artifact": "eval/tasks/heldout-growth-segment/artifacts/options.md",
         "rubric": "eval/rubrics/rubric-options.md", "mode": "self",
         "unified": "eval/runs/critic-matrix/m-heldout-options-self/critic.out",
         "reused_from": None},
    ],
}

# Уже измеренные типовые прогоны (анти-круг): демо-critic под типовой
# рубрикой — из h2-research/h2-options (TASK-hermes-6 §19.1). Это строки
# СРАВНЕНИЯ без нового прогона: единая — из матрицы §12.1, типовая — h2.
REFERENCES = [
    {"name": "demo-research-critic", "mode": "critic", "bucket": "cvs",
     "unified": "eval/runs/critic-matrix/m-demo-research-critic/critic.out",
     "typical": "eval/runs/h2-research/typed/critic.out",
     "note": "типовая — h2-research/typed (TASK-hermes-6 §19.1)"},
    {"name": "demo-options-critic", "mode": "critic", "bucket": "cvs",
     "unified": "eval/runs/critic-matrix/m-demo-options-critic/critic.out",
     "typical": "eval/runs/h2-options/typed/critic.out",
     "note": "типовая — h2-options/typed (TASK-hermes-6 §19.1)"},
]


def parse_scores(text: str) -> dict:
    """Тот же контракт парсинга, что в eval/score_arms.py.

    Два формата «Итого»: строка «Итого: 36 /40» и табличная строка
    «| Итого | | | **22/40** |» (дефект парсинга найден на прогоне
    clc-heldout: оценка терялась, хотя критик её вернул). Вариант с
    выделением «| **Итого** |» добавлен по прогону TASK-hermes-12 —
    тот же класс дефекта (см. score_ablation.parse_scores).
    """
    total = re.search(
        r"Итого\s*:\s*(?:\*\*)?\s*([\d.]+)\s*(?:\*\*)?\s*/\s*40"
        r"|\|\s*\**\s*Итого\s*\**\s*\|[^|\n]*\|[^|\n]*\|\s*(?:\*\*)?\s*([\d.]+)\s*/\s*40",
        text,
    )
    # Два формата «Итого»: строка «Итого: 36 /40» и табличная строка
    # «| Итого | | | **22/40** |» (дефект парсинга найден на прогоне
    # clc-heldout: оценка терялась, хотя критик её вернул).
    value = total.group(1) or total.group(2) if total else None
    findings = re.findall(r"\[(?:важность:\s*)?(критично|важно|незначительно)\]", text)
    return {
        "total40": float(value) if value else None,
        "findings_total": len(findings),
        "findings_important": sum(1 for f in findings if f in ("критично", "важно")),
    }


def run_critic(artifact: str, rubric: str, mode: str, out_dir: Path, tag: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_critic.py"),
        "--artifact", str(REPO_ROOT / artifact),
        "--rubric", str(REPO_ROOT / rubric),
        "--mode", mode,
        "--out", str(out_dir),
        "--tag", tag,
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=1800)
    return proc.returncode


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rescore_arms.py")
    parser.add_argument("--dry-run", action="store_true", help="только показать план")
    parser.add_argument("--only", default=None, help="один bucket (opt/res/b11/cvs)")
    args = parser.parse_args(argv)

    results: list[dict] = []
    failures = 0
    for bucket, items in PLAN.items():
        if args.only and bucket != args.only:
            continue
        for item in items:
            name = item["name"]
            tag = f"t7-{bucket}-{name}"
            out_dir = RESCORE_DIR / bucket / name / ("critic-final" if item["mode"] == "critic" else "self-final")
            record: dict = {
                "bucket": bucket,
                "name": name,
                "artifact": item["artifact"],
                "rubric": item["rubric"],
                "mode": item["mode"],
                "tag": tag,
                "unified": None,
                "typical": None,
                "reused_from": None,
            }
            # Старый замер единой рубрикой (если есть) — парсим существующий выход.
            if item.get("unified"):
                unified_path = REPO_ROOT / item["unified"]
                if unified_path.is_file():
                    record["unified"] = parse_scores(unified_path.read_text(encoding="utf-8", errors="replace"))
                    record["unified"]["source"] = item["unified"]
            # Типовая рубрика: новый прогон критика.
            if args.dry_run:
                print(f"[dry-run] {tag}: {item['artifact']} рубрика {item['rubric']} режим {item['mode']}")
                results.append(record)
                continue
            code = run_critic(item["artifact"], item["rubric"], item["mode"], out_dir, tag)
            critic_out = out_dir / "critic.out"
            if code != 0 or not critic_out.is_file():
                record["error"] = f"run_critic exit={code}"
                failures += 1
            else:
                record["typical"] = parse_scores(critic_out.read_text(encoding="utf-8", errors="replace"))
                record["typical"]["source"] = str(out_dir / "critic.out")
            results.append(record)
            u = record["unified"]["total40"] if record["unified"] else None
            t = record["typical"]["total40"] if record["typical"] else None
            print(f"{tag}: единая={u} типовая={t} findings={record['typical']['findings_important'] if record['typical'] else '—'}")

    # Строки сравнения без нового прогона (анти-круг): демо-critic из h2.
    for ref in REFERENCES:
        if args.only and ref["bucket"] != args.only:
            continue
        record = {
            "bucket": ref["bucket"], "name": ref["name"], "mode": ref["mode"],
            "artifact": None, "rubric": None, "tag": None,
            "unified": None, "typical": None, "reused_from": ref["note"],
        }
        for field, path in (("unified", ref["unified"]), ("typical", ref["typical"])):
            p = REPO_ROOT / path
            if p.is_file():
                record[field] = parse_scores(p.read_text(encoding="utf-8", errors="replace"))
                record[field]["source"] = path
        results.append(record)
        print(f"[reused] {ref['name']}: единая="
              f"{record['unified']['total40'] if record['unified'] else None} "
              f"типовая={record['typical']['total40'] if record['typical'] else None}")

    if args.dry_run:
        return EXIT_OK

    RESCORE_DIR.mkdir(parents=True, exist_ok=True)
    (RESCORE_DIR / "summary.json").write_text(
        json.dumps({"runs": results, "failures": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Реcкоринг рук под типовые рубрики (TASK-hermes-7 §1)",
        "",
        "Числа — из `summary.json` этого каталога; единая рубрика — парсинг",
        "существующих `<arm>/critic-final/critic.out`; типовая — новые",
        "прогоны критика (теги COST.md «О4: t7-…»). reused_from — переиспользованный",
        "прогон h2 (анти-круг).",
        "",
        "| bucket | рука | режим | единая /40 | типовая /40 | Δ | важно+критично (типовая) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        u = r["unified"]["total40"] if r["unified"] else "—"
        t = r["typical"]["total40"] if r["typical"] else "—"
        d = ""
        if r["unified"] and r["typical"] and r["unified"]["total40"] is not None and r["typical"]["total40"] is not None:
            d = f"{r['typical']['total40'] - r['unified']['total40']:+.0f}"
        fi = r["typical"]["findings_important"] if r["typical"] else "—"
        lines.append(f"| {r['bucket']} | {r['name']} | {r['mode']} | {u} | {t} | {d} | {fi} |")
    (RESCORE_DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nитог: прогонов {len(results)}, падений {failures}; summary: {RESCORE_DIR / 'summary.md'}")
    return EXIT_OK if failures == 0 else EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
