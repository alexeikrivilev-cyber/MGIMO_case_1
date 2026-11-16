#!/usr/bin/env python3
"""score_arms.py — метрики рук A/B-прогона (О4, TASK-hermes-4 §3).

По каждому `<out>/<arm>/final.md`:
  1. рубрика — внутренний критик (`scripts/run_critic.py`, изолированный
     контекст, два прохода) — self-assessed proxy (R3);
  2. citation accuracy — `scripts/check_citations.py` (резолвимость URL);
  3. diversity — `scripts/council_diversity.py` (TF-IDF proxy);
  4. $/run — строки COST.md с меткой «О4: ab-<...>» (хук cost-append).

Итог — `<out>/metrics.md` (таблица «рука × метрика × $») + metrics.json.

Контракт CLI:
    python3 eval/score_arms.py --run-dir eval/runs/ab-options-demo-retention

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
    total = re.search(r"Итого:\s*([\d.]+)\s*/\s*40", text)
    findings = len(re.findall(r"\[(?:критично|важно|незначительно)\]", text))
    return {
        "criteria": scores,
        "total40": float(total.group(1)) if total else None,
        "findings": findings,
    }


def cost_rows_for(label_prefix: str) -> tuple[float, int]:
    """Сумма $ и число строк COST.md, чья колонка «Шаг» начинается с префикса."""
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
        if len(cells) < 11 or not cells[2].startswith(label_prefix):
            continue
        money = cells[10].lstrip("$~")
        try:
            total += float(money)
            count += 1
        except ValueError:
            continue
    return total, count


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="score_arms.py")
    parser.add_argument("--run-dir", required=True, help="каталог A/B-прогона")
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
        # 1) рубрика — критик на финальном артефакте
        critic_dir = arm_dir / "critic-final"
        code, out = run([
            sys.executable, str(REPO_ROOT / "scripts" / "run_critic.py"),
            "--artifact", str(final),
            "--rubric", "eval/rubrics/hackathon-criteria.md",
            "--mode", "critic",
            "--out", str(critic_dir),
            "--tag", f"ab-score-{run_dir.name}-{arm}",
        ])
        rubric = parse_critic_scores((critic_dir / "critic.out").read_text(encoding="utf-8")) if code == 0 else {}
        # 2) citation accuracy
        code_c, out_c = run([sys.executable, str(REPO_ROOT / "scripts" / "check_citations.py"), str(final)])
        cite_total = re.search(r"итог:\s*(\d+)/(\d+)", out_c)
        cite = {"resolved": int(cite_total.group(1)), "total": int(cite_total.group(2))} if cite_total else {}
        # 3) diversity (proxy)
        code_d, out_d = run([sys.executable, str(REPO_ROOT / "scripts" / "council_diversity.py"), str(final)])
        div = re.search(r"средняя попарная дистанция[^\d]*([\d.]+)", out_d, re.I)
        n_var = re.findall(r"^###\s+(Вариант\s+[^\n]+)$", final.read_text(encoding="utf-8"), re.M)
        diversity = {"avg_distance": float(div.group(1)) if div else None, "options": len(n_var)}
        # 4) $/run
        usd, rows = cost_rows_for(f"О4: ab-{run_dir.name}-{arm}")
        metrics.append({
            "arm": arm,
            "rubric": rubric,
            "citations": cite,
            "diversity": diversity,
            "usd": round(usd, 3),
            "cost_rows": rows,
        })
        print(f"{arm}: рубрика {rubric.get('total40')}/40, findings {rubric.get('findings')}, "
              f"cite {cite.get('resolved')}/{cite.get('total')}, div {diversity['avg_distance']}, ${usd:.2f}")

    payload = {"run": run_dir.name, "arms": metrics}
    (run_dir / "metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Метрики рук — {run_dir.name} (О4)",
        "",
        "| Рука | Рубрика /40 (critic, proxy) | Findings | Citation accuracy | Diversity (proxy) | Вариантов | $/run |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in metrics:
        lines.append(
            f"| {m['arm']} | {m['rubric'].get('total40', '—')} | {m['rubric'].get('findings', '—')} "
            f"| {m['citations'].get('resolved', '—')}/{m['citations'].get('total', '—')} "
            f"| {m['diversity']['avg_distance'] if m['diversity']['avg_distance'] is not None else '—'} "
            f"| {m['diversity']['options']} | {m['usd']:.2f} |"
        )
    (run_dir / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"метрики: {run_dir / 'metrics.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
