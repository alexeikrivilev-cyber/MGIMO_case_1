#!/usr/bin/env python3
"""score_arms.py — метрики рук A/B-прогона (О4, TASK-hermes-4 §3).

По каждому `<out>/<arm>/final.md`:
  1. рубрика — внутренний критик (`scripts/run_critic.py`, изолированный
     контекст, два прохода) — self-assessed proxy (R3). Повторный прогон
     критика пропускается, если `<arm>/critic-final/critic.out` уже есть
     (кэш; `--force` — перезапустить).
  2. citation accuracy — `scripts/check_citations.py` (резолвимость URL)
     + подсчёт ev-N ссылок в артефакте (основанность на evidence).
  3. diversity — `scripts/council_diversity.py` (TF-IDF proxy).
  4. $/run — строки COST.md с меткой «О4: ab-…» (хук cost-append).
  5. `--sources-gate` — дисциплина доказательств: `scripts/check_sources.py`
     на финальном артефакте каждой руки (код возврата + число нарушений);
     колонка `check_sources` в metrics.md (без флага — «—»).

Итог — `<out>/metrics.md` (таблица «рука × метрика × $») + metrics.json.

Контракт CLI:
    python3 eval/score_arms.py --run-dir eval/runs/ab-options-demo-retention
        [--force] [--sources-gate]

Коды возврата: 0 — все метрики собраны; 2 — ошибка использования.
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
EXIT_USAGE = 2

# Метки сессий в COST.md по рукам (хук cost-append пишет колонку «Шаг»,
# обрезая её до 40 символов — matching префиксный). Три поколения
# форматов метки в истории О4 (фикса атрибуции 2026-11-16):
#   LEGACY  — «О4: ab-<сессия>» (прогон demo-retention);
#   ARM     — «О4: ab-<рука>-<сессия>» (прогон heldout-growth-segment);
#   FULL    — «О4: ab-<прогон>-<рука>-<сессия>» (все последующие).
ARM_LABELS_BY_RUN = {
    "ab-options-demo-retention": {
        "skill": ["ab-session"],
        "critic-loop": ["ab-session1", "ab-session2", "ab-critic-ab-options-demo-retention-"],
        "council-lite": ["ab-role-product", "ab-role-devil", "ab-role-data", "ab-synthesizer"],
    },
    "ab-options-heldout-growth-segment": {
        "skill": ["ab-skill-session"],
        "critic-loop": ["ab-critic-loop-session1", "ab-critic-loop-session2", "ab-critic-ab-options-heldout-growth-"],
        "council-lite": ["ab-council-lite-role-product", "ab-council-lite-role-devil", "ab-council-lite-role-data", "ab-council-lite-synthesizer"],
    },
    # council-full на held-out (короткий --out: хук режет метку до 40 символов,
    # поэтому фрагмент — префиксный и покрывает все 12 сессий руки).
    "cf-heldout": {
        "council-full": ["ab-cf-heldout-council-full"],
    },
    # critic-loop2: сессии руки + метка критика («О4: <прогон>-critic»).
    "cl2-demo": {
        "critic-loop2": ["ab-cl2-demo-critic-loop2", "cl2-demo-critic"],
    },
    "cl2-heldout": {
        "critic-loop2": ["ab-cl2-heldout-critic-loop2", "cl2-heldout-critic"],
    },
}


def arm_label_fragments(run_name: str, arm: str) -> list[str]:
    """Фрагменты метки для руки: известные прогоны — по таблице, новые —
    по FULL-формату (префикс «ab-<прогон>-<рука>-»)."""
    known = ARM_LABELS_BY_RUN.get(run_name, {})
    if arm in known:
        return known[arm]
    return [f"ab-{run_name}-{arm}"]


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=1800)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def parse_critic_scores(text: str) -> dict:
    """Достаёт оценки из выхода критика: «| 1. Проработанность | 4/5 | 3/5 | 6/10 |»."""
    scores: dict[str, dict[str, float | None]] = {}
    pattern = re.compile(
        r"\|\s*(\d)\.\s*([^|]+?)\s*\|\s*([\d.]+)\s*/\s*5\s*\|\s*([\d.]+)\s*/\s*5\s*\|\s*([\d.]+)\s*/\s*10\s*\|"
    )
    for num, name, p1, p2, pts in pattern.findall(text):
        scores[f"{num}. {name.strip()}"] = {
            "pass1": float(p1),
            "pass2": float(p2),
            "points": float(pts),
        }
    total = re.search(r"Итого:\s*(?:\*\*)?\s*([\d.]+)\s*(?:\*\*)?\s*/\s*40", text)
    findings = len(re.findall(r"\[(?:важность:\s*)?(?:критично|важно|незначительно)\]", text))
    return {
        "criteria": scores,
        "total40": float(total.group(1)) if total else None,
        "findings": findings,
    }


def cost_rows_for(label_fragments: list[str]) -> tuple[float, int]:
    """Сумма $ и число строк COST.md, чья колонка «Шаг» — метка сессии
    этой руки. Точное совпадение или префикс с дефисом (фрагменты вида
    «ab-critic-ab-options-» матчат префиксом; «ab-session» не должен
    заматчить «ab-session1»)."""
    cost_md = (REPO_ROOT / "COST.md").read_text(encoding="utf-8")
    total, count = 0.0, 0
    in_rows = False
    for line in cost_md.splitlines():
        if "cost-rows:begin" in line:
            in_rows = True
            continue
        if "cost-rows:end" in line:
            in_rows = False
            continue
        if not in_rows or not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 11:
            continue
        step = cells[2]
        matched = False
        for frag in label_fragments:
            prefix = f"О4: {frag}"
            if frag.endswith("-"):
                # фрагмент-префикс (метка могла быть обрезана хуком до 40 символов)
                matched = step.startswith(prefix)
            else:
                matched = step == prefix or step.startswith(prefix + "-")
            if matched:
                break
        if not matched:
            continue
        money = cells[10].lstrip("$~")
        try:
            total += float(money)
            count += 1
        except ValueError:
            continue
    return total, count


def count_evidence_refs(text: str) -> int:
    return len(set(re.findall(r"\bev-\d+\b", text)))


def parse_violations(out: str) -> int:
    """Число нарушений из вывода `check_sources.py`: итоговая строка
    «итог: нарушений N в файлах M». Нет итога (скрипт упал) — 0."""
    match = re.search(r"итог:\s*нарушений\s+(\d+)", out)
    return int(match.group(1)) if match else 0


def sources_gate(final: Path) -> dict:
    """Гейт доказательственной дисциплины: `check_sources.py` на финальном
    артефакте руки. Возвращает код возврата и число нарушений (метрика О4:
    артефакт без оснований не засчитан, даже если рубрика высокая)."""
    code, out = run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_sources.py"), str(final)]
    )
    return {"exit": code, "violations": parse_violations(out)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="score_arms.py")
    parser.add_argument("--run-dir", required=True, help="каталог A/B-прогона")
    parser.add_argument("--force", action="store_true", help="перезапустить критика, игнорируя кэш")
    parser.add_argument(
        "--sources-gate",
        action="store_true",
        help="прогон check_sources.py на финальном артефакте каждой руки "
        "(колонка check_sources в metrics.md)",
    )
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"каталог не найден: {run_dir}", file=sys.stderr)
        return EXIT_USAGE

    metrics = []
    for arm_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        final = arm_dir / "final.md"
        if not final.is_file():
            continue
        arm = arm_dir.name
        # 1) рубрика — критик на финальном артефакте (кэш по critic-final)
        critic_dir = arm_dir / "critic-final"
        critic_out = critic_dir / "critic.out"
        if args.force and critic_out.is_file():
            critic_out.unlink()
        if not critic_out.is_file():
            code, _ = run([
                sys.executable, str(REPO_ROOT / "scripts" / "run_critic.py"),
                "--artifact", str(final),
                "--rubric", "eval/rubrics/hackathon-criteria.md",
                "--mode", "critic",
                "--out", str(critic_dir),
                "--tag", f"ab-score-{run_dir.name}-{arm}",
            ])
            if code != 0:
                print(f"critic на {arm} упал exit={code}", file=sys.stderr)
        rubric = (
            parse_critic_scores(critic_out.read_text(encoding="utf-8", errors="replace"))
            if critic_out.is_file()
            else {}
        )
        # 2) citation accuracy: URL-резолвимость + ev-N ссылки
        code_c, out_c = run([sys.executable, str(REPO_ROOT / "scripts" / "check_citations.py"), str(final)])
        cite_total = re.search(r"итог:\s*(\d+)/(\d+)", out_c)
        final_text = final.read_text(encoding="utf-8", errors="replace")
        cite = {
            "urls_resolved": int(cite_total.group(1)) if cite_total else 0,
            "urls_total": int(cite_total.group(2)) if cite_total else 0,
            "ev_refs": count_evidence_refs(final_text),
        }
        # 3) diversity (proxy)
        code_d, out_d = run([sys.executable, str(REPO_ROOT / "scripts" / "council_diversity.py"), str(final)])
        div = re.search(r"средняя попарная дистанция[^\d]*([\d.]+)", out_d, re.I)
        n_var = re.findall(r"^#{2,3}\s+(?:\d+\.\s*)?Вариант\s+[^\n]+$", final_text, re.M)
        diversity = {
            "avg_distance": float(div.group(1)) if div else None,
            "options": len(n_var),
            "status_quo_present": bool(re.search(r"как есть|оставить как", final_text, re.I)),
        }
        # 4) $/run
        usd, rows = cost_rows_for(arm_label_fragments(run_dir.name, arm))
        # 5) гейт доказательств (по флагу: проверка детерминированная и
        # дешёвая, но не входит в прежний состав метрик прогонов О4)
        gate = sources_gate(final) if args.sources_gate else None
        metrics.append({
            "arm": arm,
            "rubric": rubric,
            "citations": cite,
            "diversity": diversity,
            "sources_gate": gate,
            "usd": round(usd, 3),
            "cost_rows": rows,
        })
        gate_text = (
            f"check_sources {gate['exit']}, нарушений {gate['violations']}"
            if gate
            else "check_sources пропущен"
        )
        print(f"{arm}: рубрика {rubric.get('total40')}/40, findings {rubric.get('findings')}, "
              f"URL {cite['urls_resolved']}/{cite['urls_total']}, ev-N {cite['ev_refs']}, "
              f"div {diversity['avg_distance']}, options {diversity['options']} "
              f"(как есть: {diversity['status_quo_present']}), ${usd:.2f}, {gate_text}")

    payload = {"run": run_dir.name, "arms": metrics}
    (run_dir / "metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Метрики рук — {run_dir.name} (О4)",
        "",
        "## Метрики",
        "",
        "Числа — из `<arm>/critic-final/critic.out`, `check_citations.py`,",
        "`council_diversity.py` и строк COST.md (артефакт: `metrics.json`).",
        "Колонка `check_sources` — код возврата и число нарушений",
        "`scripts/check_sources.py` на финальном артефакте (только с флагом",
        "`--sources-gate`; без него — «—»).",
        "",
        "| Рука | Рубрика /40 (critic, proxy) | Findings | URL (живые) | ev-N | Diversity (proxy) | Вариантов | «Как есть» | USD/run | check_sources |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in metrics:
        gate = m.get("sources_gate")
        gate_cell = (
            f"exit={gate['exit']}; нарушений {gate['violations']}"
            if gate
            else "—"
        )
        lines.append(
            f"| {m['arm']} | {m['rubric'].get('total40', '—')} | {m['rubric'].get('findings', '—')} "
            f"| {m['citations']['urls_resolved']}/{m['citations']['urls_total']} "
            f"| {m['citations']['ev_refs']} "
            f"| {m['diversity']['avg_distance'] if m['diversity']['avg_distance'] is not None else '—'} "
            f"| {m['diversity']['options']} | {'да' if m['diversity']['status_quo_present'] else 'НЕТ'} "
            f"| {m['usd']:.2f} | {gate_cell} |"
        )
    (run_dir / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"метрики: {run_dir / 'metrics.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
