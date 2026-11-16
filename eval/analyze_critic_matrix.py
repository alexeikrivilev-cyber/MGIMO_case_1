#!/usr/bin/env python3
"""analyze_critic_matrix.py — замер пользы механизма «внутренний критик».

Сравнивает выходы режимов critic и self на каждом артефакте матрицы
(`eval/runs/critic-matrix/m-*`): расхождение оценок по рубрике и
findings, которые самооценка пропустила. Правило вывода
предрегистрировано в docs/research/measurements.md §12:
механизм оправдан, если есть находка критика важности ≥ «важно»,
которой нет в self-выходе; MDD по оценкам — ≥ 0.5 балла на критерии.

Контракт CLI:
    python3 eval/analyze_critic_matrix.py [--dir eval/runs/critic-matrix]

Коды возврата: 0 — анализ построен; 2 — каталог не найден.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 2

CRITERION_RE = re.compile(
    r"\|\s*(\d)\.\s*([^|]+?)\s*\|\s*([\d.]+)\s*/\s*5\s*\|\s*([\d.]+)\s*/\s*5\s*\|\s*([\d.]+)\s*/\s*10\s*\|"
)
TOTAL_RE = re.compile(r"Итого:\s*([\d.]+)\s*/\s*40")
FINDING_RE = re.compile(r"\[(?:важность:\s*)?(критично|важно|незначительно)\]\s*(.+)")


def parse_output(text: str) -> dict:
    criteria = {}
    for num, name, p1, p2, pts in CRITERION_RE.findall(text):
        criteria[f"{num}. {name.strip()}"] = {
            "pass1": float(p1),
            "pass2": float(p2),
            "points": float(pts),
        }
    total = TOTAL_RE.search(text)
    findings = [
        {"severity": sev, "text": txt.strip()}
        for sev, txt in FINDING_RE.findall(text)
    ]
    return {
        "criteria": criteria,
        "total40": float(total.group(1)) if total else None,
        "findings": findings,
    }


def normalize(text: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", text.lower()).strip()


def finding_overlap(critic_f: dict, self_findings: list[dict]) -> bool:
    """Грубое совпадение находок: общие значимые слова или подстрока."""
    cn = normalize(critic_f["text"])
    cw = set(cn.split())
    for sf in self_findings:
        sn = normalize(sf["text"])
        if cn and (cn in sn or sn in cn):
            return True
        sw = set(sn.split())
        if cw and sw and len(cw & sw) / max(1, len(cw | sw)) >= 0.5:
            return True
    return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="analyze_critic_matrix.py")
    parser.add_argument("--dir", default=str(REPO_ROOT / "eval" / "runs" / "critic-matrix"))
    args = parser.parse_args(argv)

    base = Path(args.dir)
    if not base.is_dir():
        print(f"каталог не найден: {base}", file=sys.stderr)
        return EXIT_USAGE

    pairs: dict[str, dict[str, Path]] = {}
    for run_dir in sorted(base.iterdir()):
        if not run_dir.is_dir() or "-" not in run_dir.name:
            continue
        stem = run_dir.name.rsplit("-", 1)[0]
        mode = run_dir.name.rsplit("-", 1)[1]
        if mode in ("critic", "self"):
            out_file = run_dir / "critic.out"
            if out_file.is_file():  # прогон может быть ещё в работе
                pairs.setdefault(stem, {})[mode] = out_file

    rows = []
    mechanism_trigger = []
    for stem in sorted(pairs):
        modes = pairs[stem]
        if "critic" not in modes or "self" not in modes:
            continue
        critic = parse_output(modes["critic"].read_text(encoding="utf-8", errors="replace"))
        self_a = parse_output(modes["self"].read_text(encoding="utf-8", errors="replace"))
        div_total = None
        if critic["total40"] is not None and self_a["total40"] is not None:
            div_total = round(critic["total40"] - self_a["total40"], 1)
        crit_div = {}
        for key in set(critic["criteria"]) | set(self_a["criteria"]):
            c = critic["criteria"].get(key, {}).get("points")
            s = self_a["criteria"].get(key, {}).get("points")
            if c is not None and s is not None:
                crit_div[key] = round(c - s, 1)
        critic_only = [
            f for f in critic["findings"]
            if f["severity"] in ("критично", "важно") and not finding_overlap(f, self_a["findings"])
        ]
        self_only = [
            f for f in self_a["findings"]
            if f["severity"] in ("критично", "важно") and not finding_overlap(f, critic["findings"])
        ]
        row = {
            "artifact": stem,
            "critic_total40": critic["total40"],
            "self_total40": self_a["total40"],
            "divergence_total": div_total,
            "divergence_by_criterion": crit_div,
            "critic_findings": len(critic["findings"]),
            "self_findings": len(self_a["findings"]),
            "critic_only_important": critic_only,
            "self_only_important": self_only,
        }
        rows.append(row)
        if critic_only:
            mechanism_trigger.append(stem)

    justified = bool(mechanism_trigger)
    payload = {
        "rule": "measurements.md §12: критик оправдан, если ≥1 важная находка критика отсутствует в self-выходе",
        "artifacts": len(rows),
        "mechanism_justified": justified,
        "trigger_artifacts": mechanism_trigger,
        "rows": rows,
    }
    out_json = base / "analysis.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Замер пользы внутреннего критика (матрица О4)",
        "",
        f"Артефактов в анализе: {len(rows)} (рук: critic vs self на одной рубрике)",
        "Источник данных: каталоги прогона `eval/runs/critic-matrix/m-*`",
        "(выходы `critic.out`, трассы `critic.start`/`critic.end`), метки",
        "сессий — в `COST.md` (колонка «Шаг» = «О4: m-…»).",
        "Предрегистрированное правило: `docs/research/measurements.md` §12.",
        f"**Вердикт по правилу: механизм {'ОПРАВДАН' if justified else 'НЕ оправдан (negative result)'}**"
        + (f" — важные находки критика, пропущенные самооценкой, на: {', '.join(mechanism_trigger)}"
           if justified else " — важных находок критика, отсутствующих в self, не найдено."),
        "",
        "## Сравнение рук",
        "",
        "Числа таблицы — из выходов прогона `eval/runs/critic-matrix/`",
        "(файлы `critic.out` в каталогах `m-*`).",
        "",
        "| Артефакт | critic /40 | self /40 | Δ | findings c/s | critic-only (важные) | self-only (важные) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        co = "; ".join(f["text"][:60] for f in r["critic_only_important"]) or "—"
        so = "; ".join(f["text"][:60] for f in r["self_only_important"]) or "—"
        lines.append(
            f"| {r['artifact']} | {r['critic_total40']} | {r['self_total40']} "
            f"| {r['divergence_total']} | {r['critic_findings']}/{r['self_findings']} "
            f"| {co} | {so} |"
        )
    lines += [
        "",
        "Δ = critic − self (баллы /40). «critic-only» — находки важности",
        "≥ «важно» из выхода критика, не найденные в self-выходе",
        "(грубое совпадение: общие значимые слова / подстрока;",
        "окончательную эквивалентность проверяет человек при чтении).",
    ]
    (base / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"вердикт: {'оправдан' if justified else 'negative result'}; артефактов: {len(rows)}")
    print(f"анализ: {base / 'analysis.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
