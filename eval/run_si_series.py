#!/usr/bin/env python3
"""run_si_series.py — серия H-SI1: навык с патчами по замеру против навыка
без патчей (TASK-hermes-15 П.3).

Предрегистрация: measurements.md §28 + поправка §28.1 (заявлена ДО
прогонов: у §28 был дефект канала — патч навыка без навыка в промпте
не влияет на артефакт; обе руки несут навык инлайном и различаются
ТОЛЬКО содержимым навыка).

Руки (шаг 2 демо, промпт-канал — как hybrid §25.1: базовый промпт +
навык evidence инлайном):
- si-off: навык evidence ДО патчей (блоб before первой записи журнала
  `knowledge/skills/.evolution/`);
- si-on: навык evidence ПОСЛЕ трёх патчей, допущенных предохранителем
  «только по замеру» (P1 §25.7, P2 §25.7, P3 §26.4).

Генерация — ПРЯМОЙ вызов API (операционное правило §24.3), k=3 на руку.
Оценивание — eval/score_skills_k3.py (группа si), свежий критик на
артефакт × рубрику.

Контракт CLI:
    python3 eval/run_si_series.py [--k 3] [--out DIR] [--timeout SEC]
        [--dry-run]

Коды возврата: 0 — все прогоны зелёные; 1 — ошибка использования;
2 — дрейф текста руки в run_ab.py или журнала; 3 — ключ не в
окружении; 4 — хотя бы один прогон упал.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_ab = load_module("run_ab", REPO_ROOT / "eval" / "run_ab.py")
run_skills = load_module("run_skills_k3", REPO_ROOT / "eval" / "run_skills_k3.py")
skill_ledger = load_module("skill_ledger", REPO_ROOT / "product" / "agent" / "skill_ledger.py")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_DRIFT = 2
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

MODEL_STEP5 = run_skills.MODEL_STEP5
SKILL_REL = "knowledge/skills/evidence/SKILL.md"
ARMS = ("si-off", "si-on")
DEFAULT_K = 3

# Токены руки для проверки ослепления (§28.1): артефакт не должен знать,
# из какой руки он вышел.
ARM_TOKENS = ("si-on", "si-off", "skill-evolve", "ledger", ".evolution",
              "patched", "h-si1", "си-он", "си-офф")


def skill_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_skill_versions() -> tuple[str, str, str]:
    """(навык до патчей, навык после патчей, примечание о сверке).

    «До» — блоб before ПЕРВОЙ записи журнала для навыка evidence;
    «после» — текущий файл; его sha256 сверяется с after последней
    записи (иначе файл ушёл вперёди журнала — гонка, драйвер падает).
    """
    ledger = skill_ledger.ledger_path(REPO_ROOT)
    entries = [json.loads(line) for line in
               ledger.read_text(encoding="utf-8").splitlines() if line.strip()] if ledger.is_file() else []
    patches = [e for e in entries if e.get("skill") == "evidence" and e.get("action") == "patch"]
    if not patches:
        raise RuntimeError("в журнале нет патчей навыка evidence — сначала product/agent/skill_evolve.py apply")
    first_before = patches[0]["before"][0]["sha256"]
    last_after = patches[-1]["after"][0]["sha256"]
    blob = skill_ledger.read_blob(first_before, REPO_ROOT)
    if blob is None:
        raise RuntimeError(f"блоб before {first_before[:8]} потерян — откат/серия невозможны (fail-closed)")
    current = (REPO_ROOT / SKILL_REL).read_text(encoding="utf-8-sig", errors="replace")
    note = f"before {first_before[:8]} → after {last_after[:8]}"
    if skill_sha256(current) != last_after:
        raise RuntimeError(
            f"файл {SKILL_REL} (sha {skill_sha256(current)[:8]}) не совпадает с after "
            f"последней записи журнала ({last_after[:8]}) — гонка правок")
    return blob.decode("utf-8"), current, note


def block(header: str, body: str) -> str:
    return f"=== {header} ===\n{body}\n=== КОНЕЦ: {header} ===\n"


def build_prompts() -> tuple[str, str, str]:
    task = run_ab.TASKS["demo-retention"]
    brief = run_skills.read_repo_file(task["brief"])
    evidence = run_ab.build_evidence_bundle(task)
    base = run_skills.adapt_prompt(
        run_ab.RESEARCH_HYBRID_PROMPT.format(brief=brief, evidence=evidence),
        "RESEARCH_HYBRID_PROMPT")
    skill_off, skill_on, note = load_skill_versions()
    prompt_off = base + "\n" + block("НАВЫК EVIDENCE", skill_off)
    prompt_on = base + "\n" + block("НАВЫК EVIDENCE", skill_on)
    return prompt_off, prompt_on, note


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_si_series.py",
        description="Серия H-SI1: навык с патчами по замеру против навыка без патчей (§28/§28.1).",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--out", default=str(REPO_ROOT / "eval" / "runs" / "t15-si"))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.k < 1:
        print("--k должен быть ≥1", file=sys.stderr)
        return EXIT_USAGE

    try:
        prompt_off, prompt_on, note = build_prompts()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DRIFT

    prompts = {"si-off": prompt_off, "si-on": prompt_on}
    if args.dry_run:
        for arm, prompt in prompts.items():
            print(f"[dry-run] {arm}: промпт {len(prompt)} символов, "
                  f"sha256 {run_skills.sha256_text(prompt)}")
        print(f"[dry-run] журнал: {note}")
        return EXIT_OK

    key = os.environ.get("STEPFUN_API_KEY")
    if not key:
        print("STEPFUN_API_KEY не в окружении — прогон невозможен", file=sys.stderr)
        return EXIT_NO_KEY

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = [
        "# Серия H-SI1 — генерация (TASK-hermes-15 П.3, §28 + поправка §28.1)",
        "",
        f"Старт (UTC): {datetime.now(timezone.utc).isoformat()}",
        "Задача: demo-retention (шаг 2). Генерация — прямой вызов API (среда = промпт).",
        f"Журнал навыка: {note}.",
        "",
        "| Цепочка | Промпт (символов) | sha256 | Итог |",
        "|---|---|---|---|",
    ]
    failures = 0
    cost_total = 0.0
    for arm in ARMS:
        failures += run_skills.run_group("si", arm, prompts[arm], MODEL_STEP5,
                                         out_dir, key, args.timeout, args.k, manifest)
        meta_path = out_dir / "si" / arm / "meta.json"
        if meta_path.is_file():
            cost_total += json.loads(meta_path.read_text(encoding="utf-8"))["cost_usd_total"]

    # Проверка ослепления (§28.1): токены руки в артефактах.
    leaks: list[str] = []
    for arm in ARMS:
        for name in ("final.md", "final-1.md", "final-2.md")[:args.k]:
            path = out_dir / "si" / arm / name
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            found = [t for t in ARM_TOKENS if t in text.lower()]
            if found:
                leaks.append(f"si/{arm}/{name}: {found}")
    manifest.append("")
    manifest.append("## Проверка ослепления")
    manifest.append("")
    manifest.append(f"Артефактов с токенами руки: {len(leaks)}"
                    + (f" — {leaks}" if leaks else " — ослепление чистое."))
    manifest.append("")
    manifest.append(f"Стоимость генерации (прямой вызов, usage-формула §1.8): "
                    f"**${cost_total:.4f}** — строка COST.md dev-таблицы дописывается вручную.")
    (out_dir / "manifest.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    print(f"\nитог: падений {failures}; генерация ${cost_total:.4f}; "
          f"ослепление: {'чистое' if not leaks else leaks}; "
          f"manifest: {out_dir / 'manifest.md'}")
    return EXIT_OK if failures == 0 else EXIT_RUN_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
