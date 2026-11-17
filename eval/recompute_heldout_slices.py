#!/usr/bin/env python3
"""recompute_heldout_slices.py — пересчёт чисел held-out задачи из
Первоисточника (TASK-hermes-8 §1, тот же класс дефекта, что и в демо).

Контекст: гейт `scripts/check_evidence_links.py` нашёл в held-out
артефактах 6 нерезолвленных ссылок «число → evidence» (n=39 673,
profession-ставки 12.97/11.22, счётчики unknown 330/1 731, производная
3.5 п.п.). Этот скрипт пересчитывает ВСЕ эти числа (и смежные, уже
находившиеся в записях) из Первоисточника —
`bank-additional/bank-additional-full.csv` (41 188 контактов) — и
сверяет с цитируемым. Расхождение > 0.005 п.п. — дефект, exit 1.

Отчёт: `eval/runs/t8-evidence/recompute-heldout.md` + `.json`.

Контракт CLI:
    python3 eval/recompute_heldout_slices.py [--csv FILE] [--out DIR]

Коды возврата:
    0 — все ожидаемые значения воспроизведены;
    1 — есть расхождения;
    2 — ошибка использования (нет CSV).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2

DEFAULT_CSV = (
    REPO_ROOT / "eval" / "tasks" / "heldout-growth-segment" / "artifacts"
    / "materials" / "bank-additional" / "bank-additional-full.csv"
)
DEFAULT_OUT = REPO_ROOT / "eval" / "runs" / "t8-evidence"

TOL = 0.005  # п.п.

SLICES: list[dict] = [
    # --- База (ev-002) ---
    {"id": "total_n", "kind": "count", "expect": 41188, "desc": "всего контактов"},
    {"id": "yes_n", "kind": "count", "expect": 4640, "desc": "откликов yes"},
    {"id": "no_n", "kind": "count", "expect": 36548, "desc": "отказов no"},
    {"id": "base_rate", "kind": "rate", "expect": 11.27, "desc": "базовая доля отклика"},
    # --- pdays: «существующая отношение» (ev-002, ev-006) ---
    {"id": "pdays999_n", "kind": "count", "expect": 39673, "desc": "n pdays=999 (не звонили ранее)"},
    {"id": "pdays999_rate", "kind": "rate", "expect": 9.26, "desc": "отклик при pdays=999"},
    {"id": "pdays_no999_n", "kind": "count", "expect": 1515, "desc": "n pdays≠999 (звонили ранее)"},
    {"id": "pdays_no999_rate", "kind": "rate", "expect": 63.83, "desc": "отклик при pdays≠999"},
    # --- Профессии: ставка отклика по профессии (ev-002; options.md §33) ---
    {"id": "job_admin_rate", "kind": "rate", "expect": 12.97, "desc": "отклик admin."},
    {"id": "job_admin_n", "kind": "count", "expect": 10422, "desc": "n admin."},
    {"id": "job_management_rate", "kind": "rate", "expect": 11.22, "desc": "отклик management"},
    {"id": "job_management_n", "kind": "count", "expect": 2924, "desc": "n management"},
    {"id": "job_bluecollar_rate", "kind": "rate", "expect": 6.89, "desc": "отклик blue-collar"},
    {"id": "job_bluecollar_n", "kind": "count", "expect": 9254, "desc": "n blue-collar"},
    {"id": "job_student_rate", "kind": "rate", "expect": 31.43, "desc": "отклик student"},
    {"id": "job_retired_rate", "kind": "rate", "expect": 25.23, "desc": "отклик retired"},
    {"id": "job_unemployed_rate", "kind": "rate", "expect": 14.20, "desc": "отклик unemployed"},
    {"id": "job_services_rate", "kind": "rate", "expect": 8.14, "desc": "отклик services"},
    # --- Счётчики unknown (ev-002) ---
    {"id": "unknown_job_n", "kind": "count", "expect": 330, "desc": "n job=unknown"},
    {"id": "unknown_education_n", "kind": "count", "expect": 1731, "desc": "n education=unknown"},
    # --- Повтор vs первый контакт (ev-002, ev-006) ---
    {"id": "campaign1_n", "kind": "count", "expect": 17642, "desc": "n campaign=1 (первый контакт)"},
    {"id": "campaign1_rate", "kind": "rate", "expect": 13.04, "desc": "отклик при campaign=1"},
    {"id": "campaign_gt1_n", "kind": "count", "expect": 23546, "desc": "n campaign>1 (повторный)"},
    {"id": "campaign_gt1_rate", "kind": "rate", "expect": 9.94, "desc": "отклик при campaign>1"},
    # --- «Ранее звонили» среди повторных (ev-006) ---
    {"id": "cm_pdays_called_n", "kind": "count", "expect": 718,
     "desc": "среди campaign>1 ранее звонивших (pdays≠999)"},
    {"id": "cm_pdays_called_share", "kind": "rate", "expect": 3.05,
     "desc": "доля ранее звонивших среди повторных"},
    {"id": "cm_pdays_called_rate", "kind": "rate", "expect": 60.72,
     "desc": "отклик ранее звонивших среди повторных"},
    # --- Контроль по тёплой базе (ev-006) ---
    {"id": "warm_first_n", "kind": "count", "expect": 2851,
     "desc": "n campaign=1 & previous>0 (тёплая база, первый)"},
    {"id": "warm_first_rate", "kind": "rate", "expect": 28.38, "desc": "отклик тёплая база, первый"},
    {"id": "warm_repeat_n", "kind": "count", "expect": 2774,
     "desc": "n campaign>1 & previous>0 (тёплая база, повтор)"},
    {"id": "warm_repeat_rate", "kind": "rate", "expect": 24.87, "desc": "отклик тёплая база, повтор"},
    {"id": "warm_gap_pp", "kind": "derived_pp", "expect": 3.5,
     "desc": "разница первый-повтор на тёплой базе, п.п.",
     "inputs": ["warm_first_rate", "warm_repeat_rate"]},
    # --- previous>0 (ev-006) ---
    {"id": "previous_gt0_n", "kind": "count", "expect": 5625, "desc": "n previous>0"},
    {"id": "previous_gt0_rate", "kind": "rate", "expect": 26.65, "desc": "отклик при previous>0"},
    # --- Возрастные группы (ev-002) ---
    {"id": "age65_rate", "kind": "rate", "expect": 47.21, "desc": "отклик 65+"},
    {"id": "age65_n", "kind": "count", "expect": 663, "desc": "n 65+"},
    {"id": "age_lt25_rate", "kind": "rate", "expect": 23.97, "desc": "отклик до 25"},
    {"id": "age_lt25_n", "kind": "count", "expect": 1068, "desc": "n до 25"},
    {"id": "age55_64_rate", "kind": "rate", "expect": 13.57, "desc": "отклик 55–64"},
    {"id": "age25_34_rate", "kind": "rate", "expect": 12.17, "desc": "отклик 25–34"},
]


def age_group(value: str) -> str:
    age = int(value)
    if age >= 65:
        return "65+"
    if age >= 55:
        return "55-64"
    if age >= 45:
        return "45-54"
    if age >= 35:
        return "35-44"
    if age >= 25:
        return "25-34"
    return "до 25"


def compute(rows: list[dict]) -> dict[str, float]:
    def rate(sub: list[dict]) -> float:
        return 100.0 * sum(1 for r in sub if r["y"] == "yes") / len(sub) if sub else 0.0

    yes = [r for r in rows if r["y"] == "yes"]
    out: dict[str, float] = {
        "total_n": len(rows),
        "yes_n": len(yes),
        "no_n": len(rows) - len(yes),
        "base_rate": rate(rows),
    }

    p999 = [r for r in rows if r["pdays"] == "999"]
    pno = [r for r in rows if r["pdays"] != "999"]
    out["pdays999_n"], out["pdays999_rate"] = len(p999), rate(p999)
    out["pdays_no999_n"], out["pdays_no999_rate"] = len(pno), rate(pno)

    for job, tag in (("admin.", "admin"), ("management", "management"),
                     ("blue-collar", "bluecollar"), ("student", "student"),
                     ("retired", "retired"), ("unemployed", "unemployed"),
                     ("services", "services")):
        sub = [r for r in rows if r["job"] == job]
        out[f"job_{tag}_rate"] = rate(sub)
        out[f"job_{tag}_n"] = len(sub)

    out["unknown_job_n"] = sum(1 for r in rows if r["job"] == "unknown")
    out["unknown_education_n"] = sum(1 for r in rows if r["education"] == "unknown")

    c1 = [r for r in rows if r["campaign"] == "1"]
    cm = [r for r in rows if r["campaign"] != "1"]
    out["campaign1_n"], out["campaign1_rate"] = len(c1), rate(c1)
    out["campaign_gt1_n"], out["campaign_gt1_rate"] = len(cm), rate(cm)

    cm_called = [r for r in cm if r["pdays"] != "999"]
    out["cm_pdays_called_n"] = len(cm_called)
    out["cm_pdays_called_share"] = 100.0 * len(cm_called) / len(cm)
    out["cm_pdays_called_rate"] = rate(cm_called)

    warm_first = [r for r in c1 if int(r["previous"]) > 0]
    warm_repeat = [r for r in cm if int(r["previous"]) > 0]
    out["warm_first_n"], out["warm_first_rate"] = len(warm_first), rate(warm_first)
    out["warm_repeat_n"], out["warm_repeat_rate"] = len(warm_repeat), rate(warm_repeat)
    out["warm_gap_pp"] = out["warm_first_rate"] - out["warm_repeat_rate"]

    prev = [r for r in rows if int(r["previous"]) > 0]
    out["previous_gt0_n"], out["previous_gt0_rate"] = len(prev), rate(prev)

    for group in ("65+", "до 25", "55-64", "25-34"):
        sub = [r for r in rows if age_group(r["age"]) == group]
        tag = {"65+": "age65", "до 25": "age_lt25", "55-64": "age55_64", "25-34": "age25_34"}[group]
        out[f"{tag}_rate"] = rate(sub)
        out[f"{tag}_n"] = len(sub)
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="recompute_heldout_slices.py",
        description="Пересчёт чисел held-out evidence из первоисточника (bank-additional-full.csv).",
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"CSV не найден: {csv_path}", file=sys.stderr)
        return EXIT_USAGE
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    values = compute(rows)

    results = []
    mismatches = 0
    for spec in SLICES:
        got = values.get(spec["id"])
        expect = spec["expect"]
        if spec["kind"] in ("rate", "derived_pp"):
            ok = got is not None and abs(got - expect) <= TOL
        else:
            ok = got == expect
        if not ok:
            mismatches += 1
        results.append({
            "id": spec["id"], "kind": spec["kind"], "desc": spec["desc"],
            "expect": expect, "got": got, "ok": ok,
        })

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    payload = {
        "script": "eval/recompute_heldout_slices.py",
        "command": f"python3 eval/recompute_heldout_slices.py --csv {args.csv}",
        "source": str(csv_path),
        "rows": len(rows),
        "utc": stamp,
        "tolerance_pp": TOL,
        "slices": results,
        "mismatches": mismatches,
    }
    (out_dir / "recompute-heldout.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Пересчёт чисел held-out (ev-001…ev-007 ↔ research.md) из первоисточника",
        "",
        f"- Скрипт: `eval/recompute_heldout_slices.py`; команда:",
        f"  `python3 eval/recompute_heldout_slices.py --csv {args.csv}`",
        f"- Источник: `{csv_path}` ({len(rows)} контактов); Дата (UTC): {stamp}",
        f"- Допуск: {TOL} п.п. на округление цитируемого значения.",
        "",
        "| Срез | Ожидалось (цитируется) | Пересчитано (CSV) | Итог |",
        "|---|---|---|---|",
    ]
    for r in results:
        got = r["got"]
        got_text = f"{got:.2f}" if r["kind"] != "count" and got is not None else (
            str(int(got)) if got is not None else "—"
        )
        lines.append(
            f"| {r['desc']} | {r['expect']} | {got_text} | "
            f"{'ok' if r['ok'] else 'РАСХОЖДЕНИЕ'} |"
        )
    lines += ["", f"Итого: срезов {len(results)}, расхождений {mismatches}.", ""]
    (out_dir / "recompute-heldout.md").write_text("\n".join(lines), encoding="utf-8")

    for r in results:
        if not r["ok"]:
            print(f"РАСХОЖДЕНИЕ {r['id']}: ожидалось {r['expect']}, получено {r['got']} ({r['desc']})")
    print(f"срезов {len(results)}, расхождений {mismatches}; отчёт: {out_dir / 'recompute-heldout.md'}")
    return EXIT_OK if mismatches == 0 else EXIT_MISMATCH


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
