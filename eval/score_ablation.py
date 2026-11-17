#!/usr/bin/env python3
"""score_ablation.py — оценивание абляции слоёв (TASK-hermes-10 §23.1).

Скоринг артефактов рук L0–L4 под ОБЕИМИ рубриками (единая +
типовая), режим critic, свежая сессия на руку — та же процедура, что
`eval/rescore_arms.py` (чтобы числа были сопоставимы с §20.6/§22).

Дополнительно — метрики слоя без LLM: citation (URL + резолвимость +
ev-N), diversity (proxy TF-IDF), целостность (check_options /
check_sources exit-коды).

Источники артефактов:
  L0–L3 — `eval/runs/t10-ablation/<task>/<arm>/final.md` (генерация
         `eval/run_ablation.py`, прямой вызов API — среда равна промпту);
  L4    — артефакты продукта (полный агент «как в продукте»):
         демо `project/options.md`, held-out
         `eval/tasks/heldout-growth-segment/artifacts/options.md`.

Контракт CLI:
    python3 eval/score_ablation.py [--task demo|heldout|all]
        [--runs-dir DIR] [--dry-run]

Коды возврата: 0 — все прогоны завершились; 1 — часть упала; 2 — использование.
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
EXIT_USAGE = 2

ARMS = ("L0", "L1", "L2", "L3", "L4")
TASK_DIRS = {"demo": "demo-retention", "heldout": "heldout-growth-segment"}

RUBRICS = {
    "unified": "eval/rubrics/hackathon-criteria.md",
    "typical": "eval/rubrics/rubric-options.md",
}

# Артефакты L4 — продукт «как в продукте» (без новой генерации, §23.1).
PRODUCT_ARTIFACTS = {
    "demo": "project/options.md",
    "heldout": "eval/tasks/heldout-growth-segment/artifacts/options.md",
}

# $/run продукта (шаг 3 и полный путь) — строки COST.md / §19.4.
L4_COSTS = {
    "demo": {"step3_usd": 0.51, "step3_session": "ses_e1b1269a4ffe5gJIhbGoK6LnQl",
             "full_path_usd": 1.69, "source": "COST.md (хук); measurements.md §19.4"},
    "heldout": {"step3_usd": 0.61, "step3_session": "ses_e1ab684c3ffecrHULwEBV64Nio",
                "full_path_usd": 2.96, "source": "COST.md (хук); measurements.md §19.4"},
}


def parse_scores(text: str) -> dict:
    """Тот же контракт парсинга, что в rescore_arms.py/score_arms.py.

    Два формата «Итого»: строка «Итого: 36 /40» и табличная строка
    «| Итого | | | **22/40** |» (дефект парсинга найден на прогоне
    clc-heldout: оценка терялась, хотя критик её вернул). Вариант с
    выделением «| **Итого** |» добавлен по прогону TASK-hermes-12
    (research-curation-1-unified): тот же класс дефекта — формат выхода
    оценщика валидируется не регуляркой «на глаз».
    """
    total = re.search(
        r"Итого\s*:\s*(?:\*\*)?\s*([\d.]+)\s*(?:\*\*)?\s*/\s*40"
        r"|\|\s*\**\s*Итого\s*\**\s*\|[^|\n]*\|[^|\n]*\|\s*(?:\*\*)?\s*([\d.]+)\s*/\s*40",
        text,
    )
    value = total.group(1) or total.group(2) if total else None
    findings = re.findall(r"\[(?:важность:\s*)?(критично|важно|незначительно)\]", text)
    return {
        "total40": float(value) if value else None,
        "findings_total": len(findings),
        "findings_important": sum(1 for f in findings if f in ("критично", "важно")),
    }


# Частичная оценка: критик отказался оценивать критерии, неоценимые из
# артефакта шага («Итого: N/20|N/30 по оценимым, остальные — н/д»).
# Класс протокола (TASK-hermes-13 §26.4), НЕ провал прогона: клетка
# исключается из Δ-статистики и reporting отдельной строкой.
PARTIAL_RE = re.compile(
    r"Итого\s*:\s*([\d.]+)\s*/\s*(?:20|30)\b[^.\n]*"
    r"(?:н/д|оценив|не проверить|недостаточно|вне области)",
    re.IGNORECASE,
)


def assess_scores(text: str) -> dict:
    """Разбор выхода критика: полная оценка / частичная / провал."""
    res = parse_scores(text)
    if res.get("total40") is not None:
        return res
    partial = PARTIAL_RE.search(text)
    if partial:
        res["partial"] = True
        res["error"] = (f"частичная оценка: {partial.group(1)} по оценимым "
                        "критериям, остальные — н/д (машинно-сравнимого /40 нет)")
    return res


def run_critic(artifact: Path, rubric: str, out_dir: Path, tag: str, timeout: int = 1800) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_critic.py"),
        "--artifact", str(artifact),
        "--rubric", str(REPO_ROOT / rubric),
        "--mode", "critic",
        "--out", str(out_dir),
        "--tag", tag,
        "--timeout", str(timeout),
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout + 60)
    critic_out = out_dir / "critic.out"
    if proc.returncode != 0 or not critic_out.is_file():
        return {"error": f"run_critic exit={proc.returncode}"}
    scores = parse_scores(critic_out.read_text(encoding="utf-8", errors="replace"))
    scores["source"] = str(critic_out)
    if scores["total40"] is None:
        scores["error"] = "Итого не распознан в выходе критика"
    return scores


def citation_metrics(artifact: Path) -> dict:
    """URL-ы, их резолвимость (check_citations.py) и ev-N упоминания."""
    text = artifact.read_text(encoding="utf-8-sig", errors="replace")
    urls = sorted(set(re.findall(r"https?://[^\s)>\]`,;]+", text)))
    ev_refs = sorted(set(re.findall(r"\bev-\d+\b", text)))
    resolved = None
    if urls:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "check_citations.py"), str(artifact)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
        )
        resolved = {
            "exit": proc.returncode,
            "line": next((ln for ln in proc.stdout.splitlines() if ln.startswith("итог:")), ""),
        }
    return {"urls": len(urls), "url_list": urls[:20], "ev_refs": ev_refs, "resolution": resolved}


def diversity_metrics(artifact: Path) -> dict:
    """Proxy-разнообразие (TF-IDF); <2 вариантов → «н/д» (соглашение B11)."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "council_diversity.py"), str(artifact)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    out = proc.stdout
    variants = re.search(r"вариантов:\s*(\d+)", out)
    mean = re.search(r"средняя попарная дистанция:\s*([\d.]+)", out)
    return {
        "exit": proc.returncode,
        "variants": int(variants.group(1)) if variants else 0,
        "mean_distance": float(mean.group(1)) if mean else None,
    }


def integrity_metrics(artifact: Path) -> dict:
    """Целостность: check_options.py + check_sources.py exit-коды."""
    result = {}
    for script in ("scripts/check_options.py", "scripts/check_sources.py"):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / script), str(artifact)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
        )
        tail = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1:] if proc.stdout else []
        result[script.split("/")[-1]] = {"exit": proc.returncode, "summary": tail[0] if tail else ""}
    return result


def arm_artifact(task_key: str, arm: str, runs_dir: Path) -> Path:
    if arm == "L4":
        return REPO_ROOT / PRODUCT_ARTIFACTS[task_key]
    return runs_dir / TASK_DIRS[task_key] / arm / "final.md"


def write_summary(runs_dir: Path, results: list[dict], failures: int) -> None:
    """Запись summary.{json,md} (общая для прогонов и --from-json)."""
    (runs_dir / "scores").mkdir(parents=True, exist_ok=True)
    (runs_dir / "scores" / "summary.json").write_text(
        json.dumps({"runs": results, "failures": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Оценивание абляции слоёв L0–L4 (TASK-hermes-10 §23.1)",
        "",
        "Числа — из `summary.json`; критические прогоны — `scores/<task>/<arm>-<rubric>/critic.out`",
        "(теги COST.md «О4: t10-score-…»). Единая рубрика — hackathon-criteria,",
        "типовая — rubric-options. Режим critic, свежая сессия на руку.",
        "",
        "| задача | рука | единая /40 | типовая /40 | важно+критично (тип.) | URL | ev-N | diversity (proxy) | вариантов | check_options | check_sources | $/run |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if "error" in r and "unified" not in r:
            lines.append(f"| {r['task']} | {r['arm']} | ПРОВАЛ: {r['error']} | | | | | | | | | |")
            continue
        u = r.get("unified", {}).get("total40", "—")
        t = r.get("typical", {}).get("total40", "—")
        fi = r.get("typical", {}).get("findings_important", "—")
        cit = r.get("citation", {})
        div = r.get("diversity", {})
        integ = r.get("integrity", {})
        cost = r.get("cost", {})
        usd = cost.get("usd", cost.get("step3_usd", "—"))
        lines.append(
            f"| {r['task']} | {r['arm']} | {u} | {t} | {fi} | {cit.get('urls', '—')} "
            f"| {len(cit.get('ev_refs', []))} | {div.get('mean_distance', '—')} "
            f"| {div.get('variants', '—')} | {integ.get('check_options.py', {}).get('exit', '—')} "
            f"| {integ.get('check_sources.py', {}).get('exit', '—')} | {usd} |"
        )
    (runs_dir / "scores" / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="score_ablation.py",
        description="Оценивание абляции слоёв под обе рубрики + метрики слоя.",
    )
    parser.add_argument("--task", default="all", choices=["demo", "heldout", "all"])
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "eval" / "runs" / "t10-ablation"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--from-json",
        action="store_true",
        help="пересобрать summary.md из существующего summary.json без прогонов критика",
    )
    args = parser.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    task_keys = ["demo", "heldout"] if args.task == "all" else [args.task]

    if args.dry_run:
        for tk in task_keys:
            for arm in ARMS:
                art = arm_artifact(tk, arm, runs_dir)
                print(f"[dry-run] {tk} {arm}: {art} ({'есть' if art.is_file() else 'НЕТ'})")
        return EXIT_OK

    if args.from_json:
        summary_path = runs_dir / "scores" / "summary.json"
        if not summary_path.is_file():
            print(f"не найден {summary_path}", file=sys.stderr)
            return EXIT_PARTIAL
        results = json.loads(summary_path.read_text(encoding="utf-8"))["runs"]
        failures = sum(1 for r in results if "error" in r and "unified" not in r)
        write_summary(runs_dir, results, failures)
        print(f"summary.md пересобран из summary.json; падений {failures}")
        return EXIT_OK

    results: list[dict] = []
    failures = 0
    for tk in task_keys:
        for arm in ARMS:
            artifact = arm_artifact(tk, arm, runs_dir)
            record: dict = {"task": tk, "arm": arm, "artifact": str(artifact) if artifact else None}
            if artifact is None or not artifact.is_file():
                record["error"] = "артефакт не найден"
                failures += 1
                results.append(record)
                print(f"{tk} {arm}: артефакт не найден")
                continue
            for rubric_name, rubric_path in RUBRICS.items():
                tag = f"t10-score-{tk}-{arm}-{rubric_name}"[:40]
                out_dir = runs_dir / "scores" / tk / f"{arm}-{rubric_name}"
                scores = run_critic(artifact, rubric_path, out_dir, tag)
                record[rubric_name] = scores
                if "error" in scores:
                    failures += 1
            record["citation"] = citation_metrics(artifact)
            record["diversity"] = diversity_metrics(artifact)
            record["integrity"] = integrity_metrics(artifact)
            if arm == "L4":
                record["cost"] = L4_COSTS[tk]
            else:
                meta_path = runs_dir / TASK_DIRS[tk] / arm / "meta.json"
                if meta_path.is_file():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    record["cost"] = {
                        "usd": meta.get("cost_usd_total"),
                        "sessions": len(meta.get("sessions", [])),
                        "source": "прямой вызов API, usage ответа (формула COST.md)",
                    }
            results.append(record)
            u = record.get("unified", {}).get("total40")
            t = record.get("typical", {}).get("total40")
            print(f"{tk} {arm}: единая={u} типовая={t}")

    write_summary(runs_dir, results, failures)
    print(f"\nитог: рук {len(results)}, падений {failures}; summary: {runs_dir / 'scores' / 'summary.md'}")
    return EXIT_OK if failures == 0 else EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
