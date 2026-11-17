#!/usr/bin/env python3
"""blindspot_addendum.py — замер «критик с новыми пунктами vs без» (TASK-hermes-16 §30.2).

Предрегистрация: measurements.md §30.2 ДО прогонов.

Вопрос: ловят ли три пункта по слепым зонам human ground truth
(BRIEF п.27) то, что видел человек, — сдвигается ли направление
критика к вердикту человека на парах, где базовая рубрика с ним
расходилась?

Устройство:
- База («без»): оценки критика #1 по единой рубрике из §29.1
  (сессии t6/t12 — ПЕРЕИСПОЛЬЗУЕМ, анти-круг BRIEF п.20; константы
  BASE40 ниже, сверены с judge_agreement.py).
- Новое условие («с»): та же сессионная механика (scripts/run_critic.py,
  свежая сессия, изоляция, step-5-preview), рубрика —
  eval/rubrics/hackathon-criteria-bs.md (база 1:1 + критерий 5).
  Из одной сессии парсятся база (/40), аддендум (/30) и итог (/70).
- Область: 7 пар с известным вердиктом человека (5, 6, 10 + чат 1–4),
  14 артефактов. Провенанс — eval/runs/t13-blindpairs/key.md.
- Направление пары: больший итог (/70); равенство → «нет направления».
  Контроль шума сессии: направление по НОВОЙ базе (/40) против
  СТАРОЙ базы.
- Идемпотентность (урок t11): готовый непустой critic.out с
  распознанными итогами переиспользуется; иначе — перепрогон.
- Ослепление: артефакты сканируются на токены рук (имена рук в
  предъявляемом файле); находка — дефект ослепления в отчёте.

Контракт CLI:
    python3 eval/blindspot_addendum.py [--runs-dir DIR] [--dry-run]

Коды возврата: 0 — все 14 артефактов оценены и распознаны;
1 — часть прогонов упала/не распозналась; 2 — ошибка использования.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from score_ablation import run_critic  # noqa: E402

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2

RUBRIC_BS = "eval/rubrics/hackathon-criteria-bs.md"
TAG_PREFIX = "t16-bs"

# Суждения владельца (BRIEF п.27, 2026-11-17 12:34). Состав пар и
# human_winner — как в eval/judge_agreement.py (ключ раскрыт).
PAIRS: list[dict] = [
    {"n": 1, "a": "plain-chat", "b": "skill", "human": "plain-chat", "cls": "chat"},
    {"n": 2, "a": "critic-loop2", "b": "plain-chat", "human": "plain-chat", "cls": "chat"},
    {"n": 3, "a": "council-lite", "b": "plain-chat", "human": "council-lite", "cls": "chat"},
    {"n": 4, "a": "curation#0", "b": "plain-chat", "human": "plain-chat", "cls": "chat"},
    {"n": 5, "a": "skill", "b": "council-lite", "human": "skill", "cls": "fork"},
    {"n": 6, "a": "skill", "b": "critic-loop2", "human": "skill", "cls": "fork"},
    {"n": 10, "a": "hybrid#0", "b": "lean#0", "human": "hybrid#0", "cls": "fork"},
]

# Провенанс артефактов — eval/runs/t13-blindpairs/key.md (sha256 там же).
ARTIFACTS: dict[str, str] = {
    "plain-chat": "eval/runs/b11-plainchat/final.md",
    "skill": "eval/runs/ab-options-demo-retention/skill/final.md",
    "council-lite": "eval/runs/ab-options-demo-retention/council-lite/final.md",
    "critic-loop2": "eval/runs/cl2-demo/critic-loop2/final.md",
    "curation#0": "eval/runs/t12-skills/options/curation/final.md",
    "lean#0": "eval/runs/t12-skills/options/lean/final.md",
    "hybrid#0": "eval/runs/t12-skills/options/hybrid/final.md",
}

# База «без»: оценки критика #1 по единой рубрике (§29.1, сессии
# t6/t12; сверка — eval/judge_agreement.py C1_LEGACY + c1_t12_scores).
BASE40: dict[str, float] = {
    "plain-chat": 14.0,
    "skill": 20.0,
    "council-lite": 24.0,
    "critic-loop2": 26.0,
    "curation#0": 22.0,
    "lean#0": 18.0,
    "hybrid#0": 16.0,
}

# Токены рук для проверки ослепления предъявляемых артефактов.
ARM_TOKENS = ("si-on", "si-off", "skill-evolve", "ledger")

BASE_RE = re.compile(
    r"Итого\s*\(база[^)]*\)\s*:?\s*\**\s*(\d+(?:[.,]\d+)?)\s*/\s*40", re.IGNORECASE)
# Толерантность к формату модели: «Итого (5.1–5.3): 20/30» и
# «Итого полное: 46/70» — живые варианты выхода критика (проход 1).
ADD_RE = re.compile(
    r"Итого\s*\((?:пункты слепых зон|5\.1[^)]*)[^)]*\)\s*:?\s*\**\s*"
    r"(\d+(?:[.,]\d+)?)\s*/\s*30", re.IGNORECASE)
TOTAL_RE = re.compile(
    r"Итого(?:\s+полное)?\s*:?\s*\**\s*(\d+(?:[.,]\d+)?)\s*/\s*70", re.IGNORECASE)
BASE40_LINE_RE = re.compile(
    r"Итого\**\s*[|:\s]*\**\s*(\d+(?:[.,]\d+)?)\s*/\s*40", re.IGNORECASE)
ITEM_RE = re.compile(
    r"\|\s*5\.([123])[^|]*\|[^|]*\|[^|]*\|\s*\**\s*(\d+(?:[.,]\d+)?)"
    r"(?:\s*/\s*10)?\s*\**\s*\|?", re.IGNORECASE)
# Частичная оценка: «по оценимым», «н/д», «не оценим» — клетка не
# машинно-сравнима (§26.4), исключается и требует добора.
PARTIAL_RE = re.compile(r"(по оценимым|н/д|не оценим)", re.IGNORECASE)


def parse_extended(text: str) -> dict:
    """База /40, аддендум /30, итог /70 и пункты 5.1–5.3 из выхода критика.

    Приоритет: явные строки итогов → сумма пунктов → total70−addendum30.
    Частичный разбор (нет total70) — провал распознавания: клетка не
    сравнима и требует перепрогона (класс «exit 0 ≠ годный выход»)."""
    total = TOTAL_RE.search(text)
    add = ADD_RE.search(text)
    base = BASE_RE.search(text) or BASE40_LINE_RE.search(text)
    items = {f"5.{m.group(1)}": float(m.group(2).replace(",", "."))
             for m in ITEM_RE.finditer(text)}
    total70 = float(total.group(1).replace(",", ".")) if total else None
    addendum30 = float(add.group(1).replace(",", ".")) if add else None
    if addendum30 is None and items:
        addendum30 = sum(items.values())
    base40 = float(base.group(1).replace(",", ".")) if base else None
    if base40 is None and total70 is not None and addendum30 is not None:
        base40 = total70 - addendum30
    partial = bool(PARTIAL_RE.search(text))
    if partial:
        # Протокол §26.4: частичная оценка исключается из сравнения
        # (не ноль!) и требует добора.
        total70 = None
    return {
        "base40": base40,
        "addendum30": addendum30,
        "total70": total70,
        "items": items,
        "partial": partial,
    }


def direction(a: float | None, b: float | None, name_a: str, name_b: str) -> str:
    if a is None or b is None:
        return "нет оценки"
    if a > b:
        return name_a
    if b > a:
        return name_b
    return "нет направления"


def check_blinding(paths: list[Path]) -> list[str]:
    defects: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for token in ARM_TOKENS:
            if token.lower() in text.lower():
                defects.append(f"{path}: токен руки «{token}» в артефакте")
    return defects


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="blindspot_addendum.py",
        description="Замер §30.2: критик с пунктами слепых зон vs без, на парах с вердиктом человека.")
    parser.add_argument("--runs-dir",
                        default=str(REPO_ROOT / "eval" / "runs" / "t16-addendum"))
    parser.add_argument("--force", action="store_true",
                        help="перепрогон ВСЕХ артефактов (восстановление дизайна "
                             "после дефекта рубрики; проход 1 сохраняется отдельно)")
    parser.add_argument("--retry-failed", action="store_true",
                        help="перепрогон только артефактов, чей critic.out не "
                             "распознан (частичная/негодная оценка → добор)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    arms = sorted({arm for pair in PAIRS for arm in (pair["a"], pair["b"])})
    paths = {arm: REPO_ROOT / ARTIFACTS[arm] for arm in arms}
    missing = [str(p) for p in paths.values() if not p.is_file()]
    if missing:
        print(f"артефакты не найдены: {missing}", file=sys.stderr)
        return EXIT_USAGE

    if args.dry_run:
        for arm in arms:
            print(f"[dry-run] {arm}: {paths[arm]}")
        print(f"[dry-run] рубрика: {RUBRIC_BS}")
        return EXIT_OK

    runs_dir = Path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    records: dict[str, dict] = {}
    for arm in arms:
        out_dir = runs_dir / arm.replace("#", "")
        critic_out = out_dir / "critic.out"
        parsed: dict = {}
        if ((args.force or args.retry_failed) and critic_out.is_file()
                and critic_out.read_text(encoding="utf-8", errors="replace").strip()):
            # --retry-failed: перепрогон только нераспознанного выхода
            # (протокол добора); --force: всех.
            existing = parse_extended(
                critic_out.read_text(encoding="utf-8", errors="replace"))
            if args.retry_failed and existing.get("total70") is not None:
                existing["source"] = str(critic_out)
                parsed = existing
                print(f"{arm}: переиспользован (итоги распознаны)")
                if parsed.get("error"):
                    failures += 1
                records[arm] = parsed
                continue
            (runs_dir / "pass2").mkdir(parents=True, exist_ok=True)
            saved = runs_dir / "pass2" / out_dir.name
            if not saved.exists():
                shutil.copytree(out_dir, saved)
        if ((not args.force and not args.retry_failed) and critic_out.is_file()
                and critic_out.read_text(encoding="utf-8", errors="replace").strip()):
            parsed = parse_extended(
                critic_out.read_text(encoding="utf-8", errors="replace"))
            parsed["source"] = str(critic_out)
            if parsed["total70"] is None:
                parsed["error"] = "итоги не распознаны в существующем critic.out"
        else:
            tag = f"{TAG_PREFIX}-{arm.replace('#', '')}"[:36]
            res = run_critic(paths[arm], RUBRIC_BS, out_dir, tag)
            if res.get("error") and not critic_out.is_file():
                parsed = {"error": res["error"]}
            else:
                parsed = parse_extended(critic_out.read_text(
                    encoding="utf-8", errors="replace"))
                parsed["source"] = str(critic_out)
                if parsed["total70"] is None:
                    parsed["error"] = "итоги не распознаны в свежем critic.out"
        if parsed.get("error"):
            failures += 1
        records[arm] = parsed
        state = (f"base={parsed.get('base40')} add={parsed.get('addendum30')} "
                 f"total={parsed.get('total70')}")
        print(f"{arm}: {state}"
              + (f" ПРОВАЛ: {parsed['error']}" if parsed.get("error") else ""))

    blinding = check_blinding([paths[arm] for arm in arms])

    # Направления и согласие с человеком.
    rows: list[dict] = []
    for pair in PAIRS:
        a, b = pair["a"], pair["b"]
        old_a, old_b = BASE40[a], BASE40[b]
        new_a = records[a].get("base40")
        new_b = records[b].get("base40")
        tot_a = records[a].get("total70")
        tot_b = records[b].get("total70")
        rows.append({
            "n": pair["n"], "cls": pair["cls"],
            "a": a, "b": b, "human": pair["human"],
            "old_base": (old_a, old_b, direction(old_a, old_b, a, b)),
            "new_base": (new_a, new_b, direction(new_a, new_b, a, b)),
            "extended": (tot_a, tot_b, direction(tot_a, tot_b, a, b)),
            "items_a": records[a].get("items", {}),
            "items_b": records[b].get("items", {}),
            "agree_old": direction(old_a, old_b, a, b) == pair["human"],
            "agree_new": direction(new_a, new_b, a, b) == pair["human"],
            "agree_ext": direction(tot_a, tot_b, a, b) == pair["human"],
        })

    def agreement(key: str) -> tuple[int, int]:
        ok = sum(1 for r in rows if r[key])
        return ok, len(rows)

    old_ok, n_pairs = agreement("agree_old")
    new_ok, _ = agreement("agree_new")
    ext_ok, _ = agreement("agree_ext")
    # Контроль: согласованные пары по старой базе не должны перевернуться.
    flipped = [r["n"] for r in rows if r["agree_old"] and not r["agree_ext"]]
    delta = ext_ok - old_ok
    if delta >= 2 and not flipped:
        verdict = "ВАЛИДИРОВАН"
    elif delta == 1 and not flipped:
        verdict = "ЧАСТИЧНО"
    else:
        verdict = "НЕ ВАЛИДИРОВАН"

    payload = {
        "prereg": "measurements.md §30.2",
        "rubric": RUBRIC_BS,
        "records": records,
        "rows": rows,
        "agreement": {"old_base": old_ok, "new_base": new_ok,
                      "extended": ext_ok, "pairs": n_pairs},
        "flipped_agreed": flipped,
        "verdict": verdict,
        "blinding_defects": blinding,
        "failures": failures,
    }
    (runs_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Замер «критик с новыми пунктами vs без» (TASK-hermes-16 §30.2)",
        "",
        "Предрегистрация — measurements.md §30.2 ДО прогонов. Рубрика —",
        f"`{RUBRIC_BS}` (база 1:1 + критерий 5). База «без» — оценки",
        "критика #1 из §29.1 (переиспользованы, анти-круг BRIEF п.20).",
        "Суждения человека — BRIEF п.27 (ключ `eval/runs/t13-blindpairs/key.md`).",
        "",
        "| Пара | Класс | Человек | старая база (A,B → побед.) | новая база | расширенная (A,B → побед.) | согласие стар. | согласие новой | согласие расш. |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        ob = f"{r['old_base'][0]:.0f},{r['old_base'][1]:.0f} → {r['old_base'][2]}"
        nb = (f"{r['new_base'][0]:.0f},{r['new_base'][1]:.0f} → {r['new_base'][2]}"
              if None not in r["new_base"][:2] else "нет оценки")
        ex = (f"{r['extended'][0]:.0f},{r['extended'][1]:.0f} → {r['extended'][2]}"
              if None not in r["extended"][:2] else "нет оценки")
        lines.append(
            f"| {r['n']} | {r['cls']} | {r['human']} | {ob} | {nb} | {ex} "
            f"| {'да' if r['agree_old'] else 'нет'} "
            f"| {'да' if r['agree_new'] else 'нет'} "
            f"| {'да' if r['agree_ext'] else 'нет'} |")
    lines += [
        "",
        f"- согласие с человеком: старая база {old_ok}/{n_pairs}, "
        f"новая база {new_ok}/{n_pairs}, расширенная {ext_ok}/{n_pairs}",
        f"- перевернутые согласованные пары: {flipped or 'нет'}",
        f"- **Вердикт по предрегистрации §30.2: {verdict}** "
        f"(Δ согласия = {delta:+d})",
        "",
        "## Диагностика по пунктам (5.1–5.3, /10 каждый)",
        "",
        "| Пара | Рука | 5.1 управляемость | 5.2 сложность | 5.3 диапазоны |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        for side, arm in (("a", r["a"]), ("b", r["b"])):
            items = r[f"items_{side}"]
            lines.append(
                f"| {r['n']} | {arm} | {items.get('5.1', '—')} "
                f"| {items.get('5.2', '—')} | {items.get('5.3', '—')} |")
    lines += [
        "",
        "## Ослепление",
        "",
        (f"дефектов ослепления: {len(blinding)}" if blinding
         else "дефектов ослепления нет (0 токенов рук в артефактах)"),
        "",
        f"Провалов распознавания: {failures}. Артефакты сессий — "
        f"`{runs_dir}/<рука>/critic.out` (теги COST.md «О4: {TAG_PREFIX}-…»).",
    ]
    for defect in blinding:
        lines.append(f"- ДЕФЕКТ: {defect}")
    (runs_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nитог: артефактов {len(arms)}, падений {failures}; "
          f"согласие старая {old_ok}/{n_pairs}, расширенная {ext_ok}/{n_pairs}; "
          f"вердикт: {verdict}; summary: {runs_dir / 'summary.md'}")
    return EXIT_OK if failures == 0 else EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
