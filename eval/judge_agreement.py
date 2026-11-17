#!/usr/bin/env python3
"""judge_agreement.py — согласие оценок критиков с человеком-судьёй (г2, §26).

Предрегистрация: measurements.md §26.1 (г2 отложена до возврата
суждений владельца по слепым парам) + §29 (TASK-hermes-15 П.1: добор
покрытия критика #2 до всех 11 уникальных текстов и метрики ПРОТОКОЛА
двух критиков — среднее и единогласие). Суждения получены 2026-11-17
12:34 (BRIEF п.27, 10 пар, ключ `eval/runs/t13-blindpairs/key.md`).

Замер: для каждой пары — победитель по оценкам критика (более высокий
/40 под единой рубрикой) против вердикта человека. Два критика:
критик #1 — оценки протокола одного критика (серии t6/t12, единая
рубрика `eval/rubrics/hackathon-criteria.md`, версия не менялась с
956da24 — сверено `git log`); критик #2 — протокол двух критиков
(§26, клетки `eval/runs/t13-twocritic/` + добор TASK-15
`eval/runs/t15-blindpairs-c2/`). Протокол: победитель по среднему двух
критиков и победитель единогласно (где критики разошлись — протокол
направления не даёт).

Оговорка named (BRIEF п.27): пары 1–4 — НЕЭКВИВАЛЕНТНЫЙ вход (чат
отвечал на дословный запрос РП целиком, артефакт шага 3
останавливается на вариантах); критик оценивает АРТЕФАКТ, человек
судит ОТВЕТ НА ПОТРЕБНОСТЬ. Согласие считается отдельно по классам
пар: «форки» (эквивалентный вход) и «против чата».

Контракт CLI:
    python3 eval/judge_agreement.py [--out DIR]

Коды возврата: 0 — расчёт завершён; 2 — нет данных.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 2


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sc = load_module("second_critic", REPO_ROOT / "eval" / "second_critic.py")

# Суждения владельца (BRIEF п.27, 2026-11-17 12:34). Состав пар — из
# key.md (после раскрытия ключа); human_winner — вердикт владельца.
PAIRS: list[dict] = [
    {"n": 1, "a": "plain-chat", "b": "skill", "human": "plain-chat", "cls": "chat"},
    {"n": 2, "a": "critic-loop2", "b": "plain-chat", "human": "plain-chat", "cls": "chat"},
    {"n": 3, "a": "council-lite", "b": "plain-chat", "human": "council-lite", "cls": "chat"},
    {"n": 4, "a": "curation#0", "b": "plain-chat", "human": "plain-chat", "cls": "chat"},
    {"n": 5, "a": "skill", "b": "council-lite", "human": "skill", "cls": "fork"},
    {"n": 6, "a": "skill", "b": "critic-loop2", "human": "skill", "cls": "fork"},
    {"n": 7, "a": "curation#0", "b": "lean#0", "human": "curation#0", "cls": "fork"},
    {"n": 8, "a": "curation#1", "b": "lean#1", "human": "curation#1", "cls": "fork"},
    {"n": 9, "a": "curation#2", "b": "lean#2", "human": "curation#2", "cls": "fork"},
    {"n": 10, "a": "hybrid#0", "b": "lean#0", "human": "hybrid#0", "cls": "fork"},
]

# Оценки критика #1 для рук вне серии t12 (протокол одного критика,
# единая рубрика; источник — метрики прогонов t6, версия рубрики та же).
C1_LEGACY = {
    "plain-chat": 14.0,
    "skill": 20.0,
    "council-lite": 24.0,
    "critic-loop2": 26.0,
}

# Добор критика #2 (TASK-hermes-15 П.1): рука → каталог прогона в
# eval/runs/t15-blindpairs-c2/. Полные оценки перекрывают частичные
# оценки §26.4 (расхождение классов названо в отчёте).
C2_BLINDPAIR_DIRS = {
    "plain-chat": "plain-chat",
    "skill": "skill",
    "council-lite": "council-lite",
    "critic-loop2": "critic-loop2",
    "lean#0": "lean0",
    "hybrid#0": "hybrid0",
}


def c1_t12_scores() -> dict[str, float]:
    """Оценки критика #1 серии t12 под единой рубрикой (options)."""
    path = REPO_ROOT / "eval" / "runs" / "t12-skills" / "scores" / "summary.json"
    records = json.loads(path.read_text(encoding="utf-8"))["records"]
    out: dict[str, float] = {}
    for r in records:
        if r.get("rubric") != "unified" or r.get("group") != "options":
            continue
        if r.get("total40") is None:
            continue
        out[f"{r['arm']}#{r['i']}"] = float(r["total40"])
    return out


def c2_t13_scores() -> dict[str, float | None]:
    """Оценки критика #2 (протокол §26) под единой рубрикой (options).

    Частичная оценка (отказ оценивать критерии 2–3) → None: клетка
    исключается из сравнения, а не проматывается в ноль.
    """
    out: dict[str, float | None] = {}
    for cell_id, rel, rubric in sc.SAMPLE:
        if rubric != "unified" or not rel.startswith("options/"):
            continue
        critic_out = REPO_ROOT / "eval" / "runs" / "t13-twocritic" / cell_id / "critic.out"
        if not critic_out.is_file():
            continue
        res = sc.assess_critic_out(critic_out.read_text(encoding="utf-8", errors="replace"))
        m = re.search(r"options/(\w+)/final(?:-(\d))?\.md$", rel)
        if not m:
            continue
        arm = m.group(1)
        i = int(m.group(2)) if m.group(2) else 0
        out[f"{arm}#{i}"] = res.get("total40")
    return out


def c2_blindpair_scores() -> tuple[dict[str, float | None], list[str]]:
    """Добор TASK-15: полные оценки критика #2 на артефактах вне t12.

    Возвращает (оценки, расхождения классов): где t13 дал частичную
    оценку, а t15 — полную, фиксируем расхождение (отказ оценивать
    критерии 2–3 — свойство сессии, не артефакта).
    """
    out: dict[str, float | None] = {}
    class_shifts: list[str] = []
    t13 = c2_t13_scores()
    for arm, dirname in C2_BLINDPAIR_DIRS.items():
        critic_out = REPO_ROOT / "eval" / "runs" / "t15-blindpairs-c2" / dirname / "critic.out"
        if not critic_out.is_file():
            continue
        res = sc.assess_critic_out(critic_out.read_text(encoding="utf-8", errors="replace"))
        total = res.get("total40")
        out[arm] = total
        if arm in t13 and t13[arm] is None and total is not None:
            class_shifts.append(f"{arm}: t13 частичная → t15 полная {total}")
    return out, class_shifts


def implied_winner(sa: float | None, sb: float | None) -> str | None:
    """Победитель по оценкам критика; None — сравнивать нечем."""
    if sa is None or sb is None:
        return None
    if sa > sb:
        return "A"
    if sb > sa:
        return "B"
    return "tie"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="judge_agreement.py",
        description="Согласие критиков с человеком-судьёй по слепым парам (г2, §26/§29).",
    )
    parser.add_argument("--out", default=str(REPO_ROOT / "eval" / "runs" / "t15-judge-agreement"))
    args = parser.parse_args(argv)

    c1 = c1_t12_scores()
    c2 = c2_t13_scores()
    c2_new, class_shifts = c2_blindpair_scores()
    c2.update(c2_new)

    def lookup(arm: str, scores: Mapping[str, float | None], legacy: bool) -> float | None:
        if arm in scores:
            return scores[arm]
        if legacy and arm in C1_LEGACY:
            # Легаси-оценки t6 — только для протокола одного критика:
            # у критика #2 покрытия на этих руках нет (и не должно быть
            # подставлено из другого протокола).
            return C1_LEGACY[arm]
        return None

    rows: list[dict] = []
    for pair in PAIRS:
        sa1, sb1 = lookup(pair["a"], c1, True), lookup(pair["b"], c1, True)
        sa2, sb2 = lookup(pair["a"], c2, False), lookup(pair["b"], c2, False)
        w1 = implied_winner(sa1, sb1)
        w2 = implied_winner(sa2, sb2)
        human_side = "A" if pair["human"] == pair["a"] else "B"
        # Протокол двух критиков — два чтения (предрегистрация §29).
        if sa1 is not None and sb1 is not None and sa2 is not None and sb2 is not None:
            mean_a, mean_b = (sa1 + sa2) / 2, (sb1 + sb2) / 2
            w_mean = "A" if mean_a > mean_b else "B" if mean_b > mean_a else "tie"
        else:
            w_mean = None
        if w1 is None or w2 is None:
            w_unan = None  # покрытия нет — читать нечего
        elif w1 == "tie" and w2 == "tie":
            w_unan = "tie"
        elif w1 == w2:
            w_unan = w1
        else:
            w_unan = "no-direction"  # критики разошлись — адъюдикация (§26.4)
        rows.append({
            "n": pair["n"], "cls": pair["cls"], "human": pair["human"],
            "c1": (sa1, sb1, w1), "c2": (sa2, sb2, w2),
            "protocol_mean": w_mean, "protocol_unanimous": w_unan,
            "agree_c1": w1 == human_side if w1 else None,
            "agree_c2": w2 == human_side if w2 else None,
            "agree_mean": w_mean == human_side if w_mean else None,
            "agree_unanimous": w_unan == human_side if w_unan and w_unan != "no-direction" else None,
        })

    def rate(rows: list[dict], key: str, cls: str | None = None) -> tuple[int, int, int, int]:
        agree = disagree = nocover = nodirection = 0
        for r in rows:
            if cls and r["cls"] != cls:
                continue
            v = r[key]
            if v is None:
                if key == "agree_unanimous" and r["protocol_unanimous"] == "no-direction":
                    nodirection += 1
                else:
                    nocover += 1
            elif v:
                agree += 1
            else:
                disagree += 1
        return agree, disagree, nocover, nodirection

    def fmt_score(x: float | None) -> str:
        return f"{x:g}" if x is not None else "частич."

    lines = [
        "# Согласие критиков с человеком-судьёй (г2, TASK-hermes-13 §26 → TASK-hermes-15 §29)",
        "",
        "Суждения владельца — BRIEF п.27 (2026-11-17 12:34), 10 слепых пар,",
        "ключ `eval/runs/t13-blindpairs/key.md`. Критик #1 — протокол одного",
        "критика (серии t6/t12); критик #2 — протокол двух критиков (§26 +",
        "добор TASK-15 `eval/runs/t15-blindpairs-c2/`). Единая рубрика одна и",
        "та же (версия с 956da24 — сверено git log). Победитель по оценкам =",
        "больший /40; частичная оценка → клетка не сравнивается (не ноль).",
        "",
        "Протокол двух критиков (предрегистрация §29): «среднее» — победитель",
        "по mean(c1, c2); «единогласно» — направление только там, где оба",
        "критика выбрали одну сторону; расхождение критиков между собой —",
        "«протокол не дал направления» (адъюдикация обязательна, §26.4).",
        "",
        "| Пара | Класс | Человек | к1 (A,B → побед.) | к2 (A,B → побед.) | среднее | единогл. | согласие к1 | согласие к2 | согласие протокола |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        (sa1, sb1, w1) = r["c1"]
        (sa2, sb2, w2) = r["c2"]
        c1s = f"{fmt_score(sa1)},{fmt_score(sb1)} → {w1 or '—'}"
        c2s = f"{fmt_score(sa2)},{fmt_score(sb2)} → {w2 or '—'}"
        a1 = "да" if r["agree_c1"] else ("нет" if r["agree_c1"] is False else "—")
        a2 = "да" if r["agree_c2"] else ("нет" if r["agree_c2"] is False else "—")
        am = "да" if r["agree_mean"] else ("нет" if r["agree_mean"] is False else "—")
        au = "да" if r["agree_unanimous"] else ("нет" if r["agree_unanimous"] is False else "—")
        if r["protocol_unanimous"] == "no-direction":
            au = "протокол молчит"
        lines.append(
            f"| {r['n']} | {r['cls']} | {r['human']} | {c1s} | {c2s} "
            f"| {r['protocol_mean'] or '—'} | {r['protocol_unanimous'] or '—'} "
            f"| {a1} | {a2} | {am}/{au} |")
    lines.append("")

    def report(key: str, title: str, with_nodirection: bool = False) -> None:
        allr = rate(rows, key)
        forks = rate(rows, key, "fork")
        chats = rate(rows, key, "chat")
        nod = f", протокол молчит {allr[3]}" if with_nodirection else ""
        lines.append(f"- {title}: согласие {allr[0]}, расхождение {allr[1]}, "
                     f"без покрытия {allr[2]}{nod} (всего 10 пар)")
        lines.append(f"  - форки (эквивалентный вход): {forks[0]}/{forks[0] + forks[1]} согласие, "
                     f"без покрытия {forks[2]}")
        lines.append(f"  - против чата (неэквивалентный вход): {chats[0]}/{chats[0] + chats[1]} согласие, "
                     f"без покрытия {chats[2]}")

    report("agree_c1", "критик #1 (протокол одного)")
    report("agree_c2", "критик #2 (протокол двух)")
    report("agree_mean", "протокол, чтение «среднее»")
    report("agree_unanimous", "протокол, чтение «единогласно»", with_nodirection=True)
    lines.append("")

    if class_shifts:
        lines.append("## Расхождение классов оценки у критика #2 (t13 → t15)")
        lines.append("")
        for shift in class_shifts:
            lines.append(f"- {shift}")
        lines.append("")
        lines.append("Отказ оценивать критерии 2–3 (§26.4) — свойство СЕССИИ")
        lines.append("критика, не артефакта: те же артефакты во втором проходе")
        lines.append("получили полную оценку. Для протокола это значит: частичная")
        lines.append("оценка не должна исключать клетку навсегда — нужен добор.")
        lines.append("")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "judge-agreement.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "judge-agreement.json").write_text(
        json.dumps({"pairs": [{k: v for k, v in r.items() if k not in ("c1", "c2")} | {
            "c1_scores": r["c1"][:2], "c1_winner": r["c1"][2],
            "c2_scores": r["c2"][:2], "c2_winner": r["c2"][2]} for r in rows]},
            ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n".join(lines[-14:]))
    print(f"артефакт: {out_dir / 'judge-agreement.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
