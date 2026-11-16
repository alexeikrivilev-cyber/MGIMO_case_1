#!/usr/bin/env python3
"""run_critic_matrix.py — матрица прогонов критика/self по артефактам демо и held-out.

Замер пользы механизма (TASK-hermes-4 §1, BRIEF п.16): на каждом артефакте
два прогона — critic (изолированный рецензент) и self (роль автора), на
одной рубрике, с балансировкой порядка (нечётные артефакты — critic
сначала, чётные — self сначала). Результаты — eval/runs/critic-matrix/.

Контракт CLI:
    python3 eval/run_critic_matrix.py [--dry-run]

Коды возврата: 0 — все прогоны exit 0; 4 — хотя бы один прогон упал.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# (задача, артефакт) — аргументативные артефакты шагов 0–5; evidence-записи
# и сырье не оцениваются (это записи-цитаты, не аргументация).
ARTIFACTS = [
    ("demo", "project/brief.md"),
    ("demo", "project/research.md"),
    ("demo", "project/options.md"),
    ("demo", "project/strategy-product.md"),
    ("demo", "project/strategy-comms.md"),
    ("demo", "project/verification-plan.md"),
    ("demo", "project/decisions.md"),
    ("heldout", "eval/tasks/heldout-growth-segment/artifacts/brief.md"),
    ("heldout", "eval/tasks/heldout-growth-segment/artifacts/research.md"),
    ("heldout", "eval/tasks/heldout-growth-segment/artifacts/options.md"),
    ("heldout", "eval/tasks/heldout-growth-segment/artifacts/strategy-product.md"),
    ("heldout", "eval/tasks/heldout-growth-segment/artifacts/strategy-comms.md"),
    ("heldout", "eval/tasks/heldout-growth-segment/artifacts/verification-plan.md"),
]

RUBRIC = "eval/rubrics/hackathon-criteria.md"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_critic_matrix.py")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--out",
        default=None,
        help="каталог манифеста (default: eval/runs/critic-matrix)",
    )
    args = parser.parse_args(argv)

    manifest = (
        Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / "critic-matrix"
    ) / "manifest.md"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Матрица критика (О4, замер пользы механизма)",
        "",
        f"Старт (UTC): {started}",
        "",
        "| # | Задача | Артефакт | Порядок | critic exit | self exit |",
        "|---|---|---|---|---|---|",
    ]

    failures = 0
    for idx, (task, artifact) in enumerate(ARTIFACTS, start=1):
        # Балансировка: нечётные — critic первым, чётные — self первым.
        order = ["critic", "self"] if idx % 2 == 1 else ["self", "critic"]
        exits: dict[str, int] = {}
        for mode in order:
            tag = f"m-{task}-{Path(artifact).stem}-{mode}"
            out = REPO_ROOT / "eval" / "runs" / "critic-matrix" / tag
            if args.dry_run:
                print(f"[dry-run] {artifact} {mode} -> {out}")
                exits[mode] = 0
                continue
            proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "run_critic.py"),
                    "--artifact", artifact,
                    "--rubric", RUBRIC,
                    "--mode", mode,
                    "--out", str(out),
                    "--tag", tag,
                ],
                cwd=REPO_ROOT,
            )
            exits[mode] = proc.returncode
            if proc.returncode != 0:
                failures += 1
                print(f"FAIL {artifact} {mode} exit={proc.returncode}", file=sys.stderr)
        lines.append(
            f"| {idx} | {task} | `{artifact}` | {' → '.join(order)} "
            f"| {exits.get('critic', '-')} | {exits.get('self', '-')} |"
        )
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    finished = datetime.now(timezone.utc).isoformat()
    manifest.write_text(
        "\n".join(lines) + f"\n\nФиниш (UTC): {finished}\nПровалов: {failures}\n",
        encoding="utf-8",
    )
    print(f"матрица завершена, провалов: {failures}, манифест: {manifest}")
    return EXIT_RUN_FAILED if failures else 0


EXIT_RUN_FAILED = 4

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
