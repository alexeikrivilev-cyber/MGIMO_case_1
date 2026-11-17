#!/usr/bin/env python3
"""blindpair_c2.py — добор покрытия критика #2 на артефактах слепых пар
(TASK-hermes-15 П.1, предрегистрация — measurements.md §29 ДО прогонов).

Замер §26.5 (г2) закрыт частично: у протокола двух критиков покрытие
было 2 полные + 2 частичные клетки из 10 пар. Этот драйвер доводит
покрытие критика #2 до всех 11 уникальных текстов: 6 артефактов без
полной оценки (plain-chat, skill, council-lite, critic-loop2 — руки вне
серии t12; lean#0 и hybrid#0 — частичные оценки §26.4).

Контракт — тот же, что у критика #1 и у §26: scripts/run_critic.py,
свежая сессия, режим critic, изоляция, единая рубрика
(eval/rubrics/hackathon-criteria.md, версия с 956da24 — сверено
git log в §26.5). Оценки критика #1 не перемеряются (анти-круг).

Проверка ослепления (§26.2): скан артефактов на токены рук; находка
токена — дефект ослебления, клетка помечается.

Контракт CLI:
    python3 eval/blindpair_c2.py [--dry-run]

Коды возврата: 0 — все клетки got full/partial оценку; 1 — есть
провалы прогона (без оценки); 2 — ошибка использования.
"""

from __future__ import annotations

import argparse
import importlib.util
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


score_ablation = load_module("score_ablation", REPO_ROOT / "eval" / "score_ablation.py")
second_critic = load_module("second_critic", REPO_ROOT / "eval" / "second_critic.py")

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_USAGE = 2

RUBRIC = "eval/rubrics/hackathon-criteria.md"
OUT_ROOT = REPO_ROOT / "eval" / "runs" / "t15-blindpairs-c2"

# Артефакты добора: рука → путь (провенанс — eval/runs/t13-blindpairs/key.md).
# sha256 сверяется в отчёте (артефакт не должен был измениться).
CELLS: list[tuple[str, str]] = [
    ("plain-chat", "eval/runs/b11-plainchat/final.md"),
    ("skill", "eval/runs/ab-options-demo-retention/skill/final.md"),
    ("council-lite", "eval/runs/ab-options-demo-retention/council-lite/final.md"),
    ("critic-loop2", "eval/runs/cl2-demo/critic-loop2/final.md"),
    ("lean#0", "eval/runs/t12-skills/options/lean/final.md"),
    ("hybrid#0", "eval/runs/t12-skills/options/hybrid/final.md"),
]

# Ожидаемые sha256 (16 символов) из key.md — при расхождении артефакт
# изменился, и клетка помечается дефектом провенанса.
EXPECTED_SHA16 = {
    "plain-chat": "08a36621201c013e",
    "skill": "17f974dfd4c002a8",
    "council-lite": "9566ffc1527ec8af",
    "critic-loop2": "7833864102d45b62",
    "lean#0": "e99feb48e0045131",
    "hybrid#0": "ede676dc608230a3",
}


def sha16(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="blindpair_c2.py",
        description="Добор критика #2 на артефактах слепых пар (г2, §29).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    failures = 0
    partials: list[str] = []
    leaks: list[str] = []
    provenance: list[str] = []
    rows: list[str] = []

    for arm, rel in CELLS:
        artifact = REPO_ROOT / rel
        if not artifact.is_file():
            print(f"артефакт не найден: {artifact}", file=sys.stderr)
            return EXIT_USAGE
        digest = sha16(artifact)
        expected = EXPECTED_SHA16.get(arm)
        prov_ok = expected is None or digest == expected
        if not prov_ok:
            provenance.append(f"{arm}: sha256 {digest} != {expected} (key.md)")
        text = artifact.read_text(encoding="utf-8-sig", errors="replace")
        leak = [t for t in second_critic.ARM_TOKENS
                if re.search(rf"\b{re.escape(t)}\b", text, re.IGNORECASE)]
        if leak:
            leaks.append(f"{arm}: {leak}")

        if args.dry_run:
            print(f"[dry-run] {arm}: {rel} sha256={digest} prov={'ok' if prov_ok else 'НЕСОВПАДЕНИЕ'} "
                  f"leak={leak or '—'}")
            continue

        out_dir = OUT_ROOT / arm.replace("#", "")
        critic_out = out_dir / "critic.out"
        res: dict = {}
        if critic_out.is_file() and critic_out.read_text(encoding="utf-8", errors="replace").strip():
            res = second_critic.assess_critic_out(
                critic_out.read_text(encoding="utf-8", errors="replace"))
            if res.get("total40") is None and not res.get("partial"):
                res["error"] = "Итого не распознан в существующем critic.out"
        else:
            tag = f"t15-c2-{arm.replace('#', '')}"[:36]
            # Один добор на пустой/неразобранный выход (урок TASK-5/9:
            # exit 0 ≠ непустой выход; run_critic.py сам гейтит пустоту).
            for attempt in (1, 2):
                res = score_ablation.run_critic(artifact, RUBRIC, out_dir, tag)
                if res.get("total40") is not None or res.get("partial"):
                    break
                print(f"{arm}: попытка {attempt} — {res.get('error')}", file=sys.stderr)
        if res.get("partial"):
            partials.append(arm)
        elif res.get("error") or res.get("total40") is None:
            failures += 1
        score = res.get("total40")
        rows.append(f"| {arm} | {digest} | {'ok' if prov_ok else 'НЕСОВПАДЕНИЕ'} "
                    f"| {score if score is not None else 'частич.'} "
                    f"| {res.get('error') or '—'} |")
        print(f"{arm}: c2={score}" + (f" ЧАСТИЧНО: {res['error']}" if res.get("partial")
                                      else f" ПРОВАЛ: {res['error']}" if res.get("error") else ""))

    if args.dry_run:
        return EXIT_OK

    lines = [
        "# Добор критика #2 на артефактах слепых пар (TASK-hermes-15 П.1, §29)",
        "",
        "Драйвер: `eval/blindpair_c2.py`. Предрегистрация — measurements.md §29 ДО прогонов.",
        "Контракт: `scripts/run_critic.py`, свежая сессия, режим critic, единая рубрика",
        "(`eval/rubrics/hackathon-criteria.md`, версия с 956da24). Оценки критика #1 не",
        "перемерялись (анти-круг BRIEF п.20).",
        "",
        "| Рука | sha256 (16) | провенанс | оценка #2 | примечание |",
        "|---|---|---|---|---|",
        *rows,
        "",
        f"Провалов прогона: {failures}. Частичных оценок: {len(partials)}"
        + (f" — {partials}" if partials else "."),
        "",
        "## Проверка ослепления",
        "",
        (f"Дефекты ослепления: {leaks}" if leaks else "Токенов рук в артефактах не найдено — ослепление чистое."),
        "",
        "## Провенанс",
        "",
        (f"Несовпадения sha256 с key.md: {provenance}" if provenance
         else "sha256 всех артефактов совпадают с `eval/runs/t13-blindpairs/key.md`."),
        "",
    ]
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "blindpair-c2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nsummary: {OUT_ROOT / 'blindpair-c2.md'}")
    return EXIT_OK if failures == 0 else EXIT_FAILURES


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
