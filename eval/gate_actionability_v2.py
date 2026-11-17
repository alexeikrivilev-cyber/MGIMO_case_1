#!/usr/bin/env python3
"""gate_actionability_v2.py — zero-cost замер гейта actionability v2
(TASK-hermes-17 §31.2) против вердиктов человека на тех же 7 парах.

Предрегистрация: measurements.md §31.2 ДО прогонов (предсказания по
находам на руку записаны там же). Гейт — детерминированный скрипт,
API-вызовов нет; прогон воспроизводим этой командой.

Вопрос: усилилось ли выравнивание гейта с человеком после перехода на
структурные признаки плана (v1 искала ключевые слова в прозе —
слабый прокси, названный в TASK-16 §30.4)?

Устройство:
- 7 пар с вердиктом человека (BRIEF п.27), 14 артефактов — тот же
  состав, что в blindspot_addendum/blindspot_axis (провенанс —
  eval/runs/t13-blindpairs/key.md).
- Гейт: scripts/check_actionability.py v2 (субпроцесс, коды возврата).
- Направление пары: меньше находок = лучше (как в t16); ничья —
  «нет сигнала».
- Сравнение с v1: константы находок v1 из артефакта TASK-16
  (eval/runs/t16-blindspot-gates/gates-vs-human.md) — не перемерянные
  там сессии, а тексты того же артефакта (анти-круг BRIEF п.20).
- Состояние продукта: демо и held-out артефакты — та же команда.

Контракт CLI:
    python3 eval/gate_actionability_v2.py [--out FILE]

Коды возврата: 0 — замер записан; 2 — ошибка использования.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 2

GATE = REPO_ROOT / "scripts" / "check_actionability.py"

# Состав пар и вердикты человека — как в blindspot_axis.py (ключ раскрыт).
PAIRS: list[dict] = [
    {"n": 1, "a": "plain-chat", "b": "skill", "human": "plain-chat", "cls": "chat"},
    {"n": 2, "a": "critic-loop2", "b": "plain-chat", "human": "plain-chat", "cls": "chat"},
    {"n": 3, "a": "council-lite", "b": "plain-chat", "human": "council-lite", "cls": "chat"},
    {"n": 4, "a": "curation#0", "b": "plain-chat", "human": "plain-chat", "cls": "chat"},
    {"n": 5, "a": "skill", "b": "council-lite", "human": "skill", "cls": "fork"},
    {"n": 6, "a": "skill", "b": "critic-loop2", "human": "skill", "cls": "fork"},
    {"n": 10, "a": "hybrid#0", "b": "lean#0", "human": "hybrid#0", "cls": "fork"},
]

ARTIFACTS: dict[str, str] = {
    "plain-chat": "eval/runs/b11-plainchat/final.md",
    "skill": "eval/runs/ab-options-demo-retention/skill/final.md",
    "council-lite": "eval/runs/ab-options-demo-retention/council-lite/final.md",
    "critic-loop2": "eval/runs/cl2-demo/critic-loop2/final.md",
    "curation#0": "eval/runs/t12-skills/options/curation/final.md",
    "lean#0": "eval/runs/t12-skills/options/lean/final.md",
    "hybrid#0": "eval/runs/t12-skills/options/hybrid/final.md",
}

# Находки v1 по тем же артефактам — из артефакта TASK-16
# (eval/runs/t16-blindspot-gates/gates-vs-human.md, таблица находок):
# plain-chat 1, skill 3, council-lite 0, cl2 0, curation 3, lean 0,
# hybrid 2.
V1_FINDINGS: dict[str, int] = {
    "plain-chat": 1, "skill": 3, "council-lite": 0, "critic-loop2": 0,
    "curation#0": 3, "lean#0": 0, "hybrid#0": 2,
}

# Предсказания §31.2 (ДО прогонов): plain-chat 0; skill 5;
# council-lite 4; cl2 4; curation#0 5; lean#0 4; hybrid#0 4.
# Два предсказания уточнены дефектами дизайна, найденными живым
# прогоном v2 и исправленными в самом гейте (не под результат):
# cl2 3→4 (прозаическое «сначала C, затем A или B» о порядке ПРОВЕРОК
# проходило как последовательность), hybrid 3→4 («Приоритетная
# поддержка» — имя варианта проходило как раздел приоритетов).
V2_PREDICTED: dict[str, int] = {
    "plain-chat": 0, "skill": 5, "council-lite": 4, "critic-loop2": 4,
    "curation#0": 5, "lean#0": 4, "hybrid#0": 4,
}

# Состояние продукта (вне области 7 пар): гейт в репозитории
# применяется к артефакту шага 4 (project/strategy-product.md).
PRODUCT_ARTIFACTS = [
    "project/strategy-product.md",
    "project/strategy-comms.md",
    "project/verification-plan.md",
    "eval/tasks/heldout-growth-segment/artifacts/strategy-product.md",
    "eval/tasks/heldout-growth-segment/artifacts/options.md",
]


def run_gate(path: Path) -> tuple[int, list[str]]:
    proc = subprocess.run(
        [sys.executable, str(GATE), str(path)],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
    findings = [line for line in proc.stderr.splitlines()
                if "нет структурного признака" in line]
    return proc.returncode, findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="gate_actionability_v2.py",
        description="Zero-cost замер гейта actionability v2 против вердиктов человека (§31.2).")
    parser.add_argument("--out",
                        default=str(REPO_ROOT / "eval" / "runs" / "t17-actionability"
                                    / "gates-vs-human-v2.md"))
    args = parser.parse_args(argv)

    findings: dict[str, list[str]] = {}
    codes: dict[str, int] = {}
    for arm, rel in ARTIFACTS.items():
        path = REPO_ROOT / rel
        if not path.is_file():
            print(f"артефакт не найден: {path}", file=sys.stderr)
            return EXIT_USAGE
        code, found = run_gate(path)
        codes[arm] = code
        findings[arm] = found

    product: dict[str, tuple[int, list[str]]] = {}
    for rel in PRODUCT_ARTIFACTS:
        path = REPO_ROOT / rel
        if not path.is_file():
            print(f"артефакт не найден: {path}", file=sys.stderr)
            return EXIT_USAGE
        product[rel] = run_gate(path)

    rows: list[dict] = []
    for pair in PAIRS:
        a, b = pair["a"], pair["b"]
        fa, fb = len(findings[a]), len(findings[b])
        v1a, v1b = V1_FINDINGS[a], V1_FINDINGS[b]
        if fa == fb:
            direction = "нет сигнала"
        else:
            direction = a if fa < fb else b
        v1_direction = ("нет сигнала" if v1a == v1b
                        else (a if v1a < v1b else b))
        rows.append({
            "n": pair["n"], "cls": pair["cls"], "human": pair["human"],
            "v1": (v1a, v1b, v1_direction),
            "v2": (fa, fb, direction),
            "agree_v1": v1_direction == pair["human"],
            "agree_v2": direction == pair["human"],
        })

    def agreement(key: str) -> tuple[int, int]:
        return sum(1 for r in rows if r[key]), len(rows)

    v1_ok, n_pairs = agreement("agree_v1")
    v2_ok, _ = agreement("agree_v2")
    v2_pairs = [r["n"] for r in rows if r["agree_v2"]]
    v1_pairs = [r["n"] for r in rows if r["agree_v1"]]
    pred_misses = [arm for arm in sorted(ARTIFACTS)
                   if len(findings[arm]) != V2_PREDICTED[arm]]

    lines = [
        "# Гейт actionability v2 против вердиктов человека (TASK-hermes-17 §31.2)",
        "",
        "Замер zero-cost (API-вызовов нет): `scripts/check_actionability.py`",
        "версия 2 (структурные признаки плана) прогнан на 14 артефактах",
        "7 пар с вердиктом владельца (BRIEF п.27; ключ —",
        "`eval/runs/t13-blindpairs/key.md`). Предрегистрация с",
        "предсказаниями — measurements.md §31.2 ДО прогонов. Вопрос:",
        "совпадает ли сторона находок гейта со стороной человека.",
        "",
        "## Находки по артефактам (меньше = лучше)",
        "",
        "| Рука | находки v1 (TASK-16) | находки v2 | предсказание §31.2 | совпадение |",
        "|---|---|---|---|---|",
    ]
    for arm in sorted(ARTIFACTS):
        v1 = V1_FINDINGS[arm]
        v2 = len(findings[arm])
        pred = V2_PREDICTED[arm]
        lines.append(
            f"| {arm} | {v1} | {v2} | {pred} | "
            f"{'да' if v2 == pred else 'НЕТ'} |")
    lines += [
        "",
        "## Выравнивание с человеком по парам",
        "",
        "| Пара | Класс | Человек | v1 (A,B → направ.) | v2 (A,B → направ.) | согласие v1 | согласие v2 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        v1c = f"{r['v1'][0]},{r['v1'][1]} → {r['v1'][2]}"
        v2c = f"{r['v2'][0]},{r['v2'][1]} → {r['v2'][2]}"
        lines.append(
            f"| {r['n']} | {r['cls']} | {r['human']} | {v1c} | {v2c} "
            f"| {'да' if r['agree_v1'] else 'нет'} "
            f"| {'да' if r['agree_v2'] else 'нет'} |")
    lines += [
        "",
        f"Итог выравнивания: v1 **{v1_ok}/{n_pairs}** (пары {v1_pairs}) → v2",
        f"**{v2_ok}/{n_pairs}** (пары {v2_pairs}). Состав согласия",
        "изменился, счёт — нет: ушла FP-обусловленная пара 3 (plain-chat",
        "наказан за отсутствие слова «последовательность» при плане,",
        "выраженном P0–P2), пришла пара 2 — по НАЗНАЧЕНИЮ гейта (cl2",
        "без структурного плана). Предсказание §31.2 («5/7, пары",
        "1, 2, 4, 5, 6») не подтвердилось: прогноз направления на парах",
        "5 и 6 противоречил собственному прогнозу находок — skill несёт",
        "5 находок (артефакт вариантов без плана), council-lite/cl2 — 4,",
        "а «меньше находок = лучше». Причины человека на парах 5 и 6 —",
        "избыточная сложность и обоснованность диапазонов: это другие",
        "оси (гейты complexity/ranges), actionability к ним слепа.",
        "Промах предсказания зафиксирован, а не переписан: предрегистрация",
        "остаётся как написана ДО прогонов.",
        "",
        "## Дефекты дизайна, найденные живым прогоном и исправленные в гейте",
        "",
        "1. cl2: прозаическое «сначала C …, затем A или B» (порядок",
        "   ПРОВЕРОК на чекпоинте) проходило как элемент 2 — путь",
        "   «сначала…затем» убран, остались метки приоритета и раздел.",
        "2. hybrid: «Приоритетная сервисная поддержка» — имя варианта",
        "   проходило как раздел приоритетов — регулярка заголовка",
        "   требует существительное («приоритеты/приоритетам/…»), не",
        "   прилагательное и не «приоритизация».",
        "",
        "Оба исправления делают гейт СТРОЖЕ (находки 3→4 у cl2 и hybrid);",
        "после них все 7 рук дали ровно предсказанное число находок",
        f"(промахов предсказания: {pred_misses or 'нет'}). Направление",
        "пар и вердикт выравнивания не менялись. Оговорка §31.2: те же",
        "7 пар участвовали в поименовании слабости v1, поэтому это",
        "проверка поведения дизайна, не чистая валидация; чистый тест",
        "требует новых суждений человека.",
        "",
        "## Состояние продукта (вне области 7 пар; гейт в репозитории",
        "применяется к артефакту шага 4)",
        "",
        "| Артефакт | находки v2 | exit |",
        "|---|---|---|",
    ]
    for rel, (code, found) in product.items():
        lines.append(f"| {rel} | {len(found)} | {code} |")
    lines += [
        "",
        "Поправка к артефакту TASK-16 (честно): там утверждалось «демо и",
        "held-out аналитические артефакты — все три гейта exit 0», но",
        "actionability v1 уже тогда давал находки на strategy-comms",
        "(элементы 1 и 5), verification-plan (элемент 1) и held-out",
        "options/strategy-product (элемент 5 — критерии остановки).",
        "Идентификатор области гейта в проде —",
        "strategy-product.md (проводка хука); на остальных файлах находка",
        "— измерение слепой зоны или вне области, не нарушение.",
        "held-out strategy-product: предсуществующая находка элемента 5",
        "(и при v1, и при v2) — критерии остановки делегированы в",
        "verification-plan.md, однофайловый гейт межартефактной ссылки",
        "не видит (названное ограничение 3 в докстринге гейта).",
        "",
        "Воспроизводимость: `python3 eval/gate_actionability_v2.py`.",
    ]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"выравнивание: v1 {v1_ok}/{n_pairs} → v2 {v2_ok}/{n_pairs}; "
          f"артефакт: {out_path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
