#!/usr/bin/env python3
"""critic_loop_round2.py — плато-итерация H-R2: второй раунд точечной
ревизии critic-loop2 (TASK-hermes-10 §23.2, предрегистрация ДО прогонов).

Обоснование (анти-круг, §23.2): серия §22.4 показала, что разброс
эффекта критика порождён ГЛУБИНОЙ ревизии (applied 3…15), а один
раунд даёт случайную глубину. H-R2: систематический второй раунд
(критик по финалу round-1 → точечные правки) даёт измеримый прирост.

Протокол: переиспользуем артефакты линейности cl2 (`eval/runs/cl2-*`),
round-1 не перепрогоняется; круг 2 = свежий критик (единая рубрика,
как §17) + точечная ревизия (`PATCH_REVISION_PROMPT` +
`scripts/apply_revision.py`, integrity-гейт). Оценивание round-2 под
ОБЕИМИ рубриками; round-1 — из `eval/runs/t7-rescore/summary.json`
(рубрики не менялись с task 6, протокол идентичен).

Вердикт по предрегистрации: Δ(round2 − round1) ≥ MDD(n=1) → «глубина
даёт прирост, механизму нужны ≥2 раунда»; ниже → «плато подтверждено
эмпирически: удвоение глубины измеримого не даёт». Без расширения
серии в любом случае.

Контракт CLI:
    python3 eval/critic_loop_round2.py [--timeout SEC] [--dry-run]

Коды возврата: 0 — всё зелено; 1 — использование; 3 — нет ключа;
4 — прогон упал.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from arg_chunk import chunk_prompt  # noqa: E402
import run_label  # noqa: E402
from run_ab import PATCH_REVISION_PROMPT, parse_patch_json  # noqa: E402
from score_ablation import RUBRICS, parse_scores, run_critic  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

MODEL = "stepfun/step-5-preview"
MAX_PATCH_EDITS = 15

# Линейность round-1 (артефакты не перепрогоняются).
CL2_ROUND1 = {
    "demo": REPO_ROOT / "eval" / "runs" / "cl2-demo" / "critic-loop2",
    "heldout": REPO_ROOT / "eval" / "runs" / "cl2-heldout" / "critic-loop2",
}
# Баллы round-1 под обеими рубриками (t7-rescore, critic-режим).
T7_RESCORE = {
    "demo": {"unified": 26.0, "typical": 36.0},
    "heldout": {"unified": 22.0, "typical": 40.0},
}
# Измеренный шум судьи (§21.2/§12.1) — тот же, что в ablation_stats.
NOISE_SD = {"typical": 1.03, "unified": 1.41}
Z_975 = 1.959963984540054
POWER = 0.80
Z_080 = 0.8416212335729143


def mdd1(sd: float) -> float:
    import math

    return (Z_975 + Z_080) * sd * math.sqrt(2.0)


def verdict(delta: float, sd: float) -> str:
    mdd = mdd1(sd)
    a = abs(delta)
    if a >= mdd:
        return "выше шума"
    if a >= 0.75 * mdd:
        return "НА ГРАНИЦЕ"
    return "нет отличимого различия"


def run_session(prompt: str, out_dir: Path, name: str, timeout: int) -> tuple[int, str]:
    """In-repo сессия (хук cost-append атрибутирует по метке прогона)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    run_label.set_run_label(f"О4: t10-cl2r2-{out_dir.parent.name}-{name}"[:40])
    try:
        proc = subprocess.run(
            ["opencode", "run", "--model", MODEL, *chunk_prompt(prompt)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return -1, ""
    finally:
        run_label.clear_run_label()
    (out_dir / f"{name}.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / f"{name}.end").write_text(
        f"exit={proc.returncode}\n", encoding="utf-8"
    )
    return proc.returncode, proc.stdout


def run_critic_labeled(artifact: Path, rubric: str, out_dir: Path, tag: str, timeout: int) -> dict:
    run_label.set_run_label(f"О4: {tag}"[:40])
    try:
        result = run_critic(artifact, rubric, out_dir, tag, timeout)
    finally:
        run_label.clear_run_label()
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="critic_loop_round2.py",
        description="H-R2: второй раунд точечной ревизии critic-loop2 (плато-итерация).",
    )
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--out", default=str(REPO_ROOT / "eval" / "runs" / "t10-cl2-r2"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    out_root = Path(args.out)
    if args.dry_run:
        for task, src in CL2_ROUND1.items():
            print(f"[dry-run] {task}: round-1 {src / 'final.md'} ({'есть' if (src / 'final.md').is_file() else 'НЕТ'})")
        return EXIT_OK

    lines = [
        "# H-R2: второй раунд точечной ревизии critic-loop2 (TASK-hermes-10 §23.2)",
        "",
        "Round-1 переиспользован из `eval/runs/cl2-*` (линейность); круг 2 —",
        "свежий критик + точечные правки. Оценивание round-2 под обеими",
        "рубриками; round-1 — из t7-rescore (протокол идентичен).",
        "",
        "| задача | round-1 (ед./тип.) | round-2 (ед./тип.) | Δ ед. | Δ тип. | вердикт (ед./тип.) | applied | integrity |",
        "|---|---|---|---|---|---|---|---|",
    ]
    failures = 0
    for task, src in CL2_ROUND1.items():
        round1 = (src / "final.md").read_text(encoding="utf-8", errors="replace")
        out_dir = out_root / task
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "round1.md").write_text(round1, encoding="utf-8")

        # Круг 2: критик по финалу round-1 (единая рубрика, как §17).
        critic_dir = out_dir / "critic2"
        scores_err = run_critic_labeled(
            out_dir / "round1.md", RUBRICS["unified"], critic_dir,
            f"t10-cl2r2-{task}-critic2", args.timeout,
        )
        critic_out = critic_dir / "critic.out"
        if "error" in scores_err or not critic_out.is_file():
            print(f"{task}: критик round-2 упал: {scores_err.get('error')}", file=sys.stderr)
            failures += 1
            continue
        findings = critic_out.read_text(encoding="utf-8", errors="replace")
        (out_dir / "findings2.md").write_text(findings, encoding="utf-8")

        # Точечная ревизия по находкам круга 2.
        code, reply = run_session(
            PATCH_REVISION_PROMPT.format(draft=round1, findings=findings),
            out_dir, "session-r2", args.timeout,
        )
        if code != 0 or not reply.strip():
            print(f"{task}: сессия ревизии round-2 упала exit={code}", file=sys.stderr)
            failures += 1
            continue
        patches = parse_patch_json(reply)
        if patches is None:
            (out_dir / "final.md").write_text(round1, encoding="utf-8")
            (out_dir / "revision-report.md").write_text(
                "# Отчёт round-2\n\nJSON правок не разобран — финал = round-1 (fallback).\n",
                encoding="utf-8",
            )
            print(f"{task}: правки round-2 не разобраны — fallback на round-1")
            failures += 1
            continue
        edits = [e for e in patches.get("edits", []) if isinstance(e, dict)][:MAX_PATCH_EDITS]
        patches["edits"] = edits
        (out_dir / "patches2.json").write_text(
            json.dumps(patches, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        applier = subprocess.run(
            [
                sys.executable, str(REPO_ROOT / "scripts" / "apply_revision.py"),
                "--draft", str(out_dir / "round1.md"),
                "--patches", str(out_dir / "patches2.json"),
                "--out", str(out_dir / "final.md"),
                "--report", str(out_dir / "revision-report.md"),
            ],
            cwd=REPO_ROOT,
        )
        if applier.returncode != 0:
            print(f"{task}: apply_revision round-2 exit={applier.returncode}", file=sys.stderr)
            failures += 1
            continue

        # Оценивание round-2 под обеими рубриками.
        row: dict[str, str] = {"applied": "—", "integrity": "—"}
        r2_scores: dict[str, float | None] = {}
        for rubric_name in RUBRICS:
            res = run_critic_labeled(
                out_dir / "final.md", RUBRICS[rubric_name],
                out_dir / f"score-{rubric_name}",
                f"t10-cl2r2-{task}-score-{rubric_name}", args.timeout,
            )
            r2_scores[rubric_name] = res.get("total40")
        report_text = (out_dir / "revision-report.md").read_text(encoding="utf-8", errors="replace")
        applied = re.search(r"applied=(\d+)", report_text)
        integrity = re.search(r"integrity=(\w+)", report_text)
        row["applied"] = applied.group(1) if applied else "—"
        row["integrity"] = integrity.group(1) if integrity else "—"

        r1 = T7_RESCORE[task]
        deltas = {}
        verdicts = {}
        for rubric_name in RUBRICS:
            value = r2_scores[rubric_name]
            if value is None:
                deltas[rubric_name] = None
                verdicts[rubric_name] = "не распознан"
                continue
            d = value - r1[rubric_name]
            deltas[rubric_name] = round(d, 1)
            verdicts[rubric_name] = verdict(d, NOISE_SD[rubric_name])
        lines.append(
            f"| {task} | {r1['unified']:.0f}/{r1['typical']:.0f} "
            f"| {r2_scores['unified']}/{r2_scores['typical']} "
            f"| {deltas['unified']} | {deltas['typical']} "
            f"| {verdicts['unified']} / {verdicts['typical']} "
            f"| {row['applied']} | {row['integrity']} |"
        )
        (out_dir / "round2-result.json").write_text(
            json.dumps(
                {"task": task, "round1": r1, "round2": r2_scores,
                 "delta": deltas, "verdict": verdicts,
                 "applied": row["applied"], "integrity": row["integrity"]},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"{task}: round-1 {r1} → round-2 {r2_scores}; Δ {deltas} → {verdicts}")

    lines.append("")
    lines.append(f"Провалов: {failures}")
    (out_root / "h-r2-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"итог: {out_root / 'h-r2-summary.md'}, провалов {failures}")
    return EXIT_RUN_FAILED if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
