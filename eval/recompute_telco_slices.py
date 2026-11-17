#!/usr/bin/env python3
"""recompute_telco_slices.py — пересчёт ВСЕХ чисел ev-002/research.md из
Первоисточника (TASK-hermes-8 §1, дефект доказательной цепи демо).

Контекст: `project/research.md` ссылался (ev-002) на ~15 тонких срезов,
которых в записи ev-002 не было («ссылка есть, содержания нет» — найдено
дайджест-критиком TASK-hermes-7 §20.9-Б). Этот скрипт пересчитывает
каждое цитируемое число ИЗ ПЕРВОИСТОЧНИКА (`telco-customer-churn.csv`)
и сверяет с цитируемым значением: расхождение > 0.005 п.п. — дефект
(число в артефакте не воспроизводится), exit 1.

Ожидаемые значения — те, что цитируют артефакты демо (research.md,
options.md, strategy-*.md, synthesis.md); они НЕ подгоняются под CSV:
скрипт — арбитр между артефактом и источником.

Отчёт: `eval/runs/t8-evidence/recompute-telco.md` + `.json`
(скрипт + команда + дата + значения — для записи в ev-002).

Контракт CLI:
    python3 eval/recompute_telco_slices.py [--csv FILE] [--out DIR]

Коды возврата:
    0 — все ожидаемые значения воспроизведены (≤0.005 п.п. / точный счёт);
    1 — есть расхождения (список в отчёте);
    2 — ошибка использования (нет CSV).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2

DEFAULT_CSV = REPO_ROOT / "project" / "materials" / "telco-customer-churn.csv"
DEFAULT_OUT = REPO_ROOT / "eval" / "runs" / "t8-evidence"

TOL = 0.005  # п.п. — допуск на округление цитируемого значения

# Срезы: (id, группировка, описание, ожидаемое значение % или count, kind)
# kind: "rate" — доля оттока в группе (%); "count" — счёт; "mean" — среднее.
SLICES: list[dict] = [
    # --- Агрегаты ev-002 (перепроверка записи шага 1) ---
    {"id": "total_n", "kind": "count", "expect": 7043, "desc": "всего записей в датасете"},
    {"id": "total_churn_n", "kind": "count", "expect": 1869, "desc": "ушедших (Churn=Yes) всего"},
    {"id": "total_rate", "kind": "rate", "expect": 26.54, "desc": "доля оттока в датасете"},
    {"id": "mean_tenure", "kind": "mean", "expect": 32.37, "desc": "средний tenure, мес"},
    {"id": "mean_monthly", "kind": "mean", "expect": 64.76, "desc": "средний MonthlyCharges"},
    # --- Контракт ---
    {"id": "contract_m2m_rate", "kind": "rate", "expect": 42.71, "desc": "отток month-to-month"},
    {"id": "contract_m2m_n", "kind": "count", "expect": 3875, "desc": "n month-to-month"},
    {"id": "contract_m2m_churn", "kind": "count", "expect": 1655, "desc": "ушедших month-to-month"},
    {"id": "contract_1y_rate", "kind": "rate", "expect": 11.27, "desc": "отток one year"},
    {"id": "contract_1y_n", "kind": "count", "expect": 1473, "desc": "n one year"},
    {"id": "contract_1y_churn", "kind": "count", "expect": 166, "desc": "ушедших one year"},
    {"id": "contract_2y_rate", "kind": "rate", "expect": 2.83, "desc": "отток two year"},
    {"id": "contract_2y_n", "kind": "count", "expect": 1695, "desc": "n two year"},
    {"id": "contract_2y_churn", "kind": "count", "expect": 48, "desc": "ушедших two year"},
    {"id": "m2m_share_of_churn", "kind": "rate", "expect": 88.55,
     "desc": "доля month-to-month среди всех ушедших"},
    {"id": "derived_m2m_minus_2y", "kind": "derived_pp", "expect": 39.88,
     "desc": "разница оттока month-to-month против two-year, п.п.",
     "inputs": ["contract_m2m_rate", "contract_2y_rate"]},
    # --- Тенур-бакеты ---
    {"id": "tenure_0_3_rate", "kind": "rate", "expect": 56.21, "desc": "отток 0–3 мес"},
    {"id": "tenure_0_3_n", "kind": "count", "expect": 1062, "desc": "n 0–3 мес"},
    {"id": "tenure_4_12_rate", "kind": "rate", "expect": 39.15, "desc": "отток 4–12 мес"},
    {"id": "tenure_4_12_n", "kind": "count", "expect": 1124, "desc": "n 4–12 мес"},
    {"id": "tenure_13_24_rate", "kind": "rate", "expect": 28.71, "desc": "отток 13–24 мес"},
    {"id": "tenure_13_24_n", "kind": "count", "expect": 1024, "desc": "n 13–24 мес"},
    {"id": "tenure_25_48_rate", "kind": "rate", "expect": 20.39, "desc": "отток 25–48 мес"},
    {"id": "tenure_25_48_n", "kind": "count", "expect": 1594, "desc": "n 25–48 мес"},
    {"id": "tenure_49_rate", "kind": "rate", "expect": 9.51, "desc": "отток 49+ мес"},
    {"id": "tenure_49_n", "kind": "count", "expect": 2239, "desc": "n 49+ мес"},
    # --- Когорта 0–3 мес ---
    {"id": "cohort_churners", "kind": "count", "expect": 597,
     "desc": "ушедших из когорты 0–3 мес"},
    {"id": "cohort_share_of_churn", "kind": "rate", "expect": 31.94,
     "desc": "доля когорты 0–3 мес во всём оттоке датасета"},
    {"id": "tenure0_rate", "kind": "rate", "expect": 0.00, "desc": "отток при tenure=0"},
    {"id": "tenure0_n", "kind": "count", "expect": 11, "desc": "n tenure=0"},
    {"id": "tenure1_rate", "kind": "rate", "expect": 61.99, "desc": "отток при tenure=1"},
    {"id": "tenure1_n", "kind": "count", "expect": 613, "desc": "n tenure=1"},
    {"id": "tenure2_rate", "kind": "rate", "expect": 51.68, "desc": "отток при tenure=2"},
    {"id": "tenure2_n", "kind": "count", "expect": 238, "desc": "n tenure=2"},
    {"id": "tenure3_rate", "kind": "rate", "expect": 47.00, "desc": "отток при tenure=3"},
    {"id": "tenure3_n", "kind": "count", "expect": 200, "desc": "n tenure=3"},
    {"id": "tenure4_rate", "kind": "rate", "expect": 47.16, "desc": "отток при tenure=4"},
    {"id": "tenure5_rate", "kind": "rate", "expect": 48.12, "desc": "отток при tenure=5"},
    {"id": "tenure6_rate", "kind": "rate", "expect": 36.36, "desc": "отток при tenure=6"},
    # --- Внутри новичков (0–3 мес) по контракту ---
    {"id": "new_m2m_share", "kind": "rate", "expect": 96.52,
     "desc": "доля month-to-month среди новичков"},
    {"id": "new_m2m_n", "kind": "count", "expect": 1025, "desc": "n новичков month-to-month"},
    {"id": "new_m2m_rate", "kind": "rate", "expect": 58.05, "desc": "отток новичков month-to-month"},
    {"id": "new_1y_rate", "kind": "rate", "expect": 9.52, "desc": "отток новичков one year"},
    {"id": "new_1y_n", "kind": "count", "expect": 21, "desc": "n новичков one year"},
    {"id": "new_2y_rate", "kind": "rate", "expect": 0.00, "desc": "отток новичков two year"},
    {"id": "new_2y_n", "kind": "count", "expect": 16, "desc": "n новичков two year"},
    # --- Внутри month-to-month по тенур-бакетам ---
    {"id": "m2m_t0_3_rate", "kind": "rate", "expect": 58.05, "desc": "отток m2m 0–3 мес"},
    {"id": "m2m_t0_3_n", "kind": "count", "expect": 1025, "desc": "n m2m 0–3 мес"},
    {"id": "m2m_t4_12_rate", "kind": "rate", "expect": 44.27, "desc": "отток m2m 4–12 мес"},
    {"id": "m2m_t4_12_n", "kind": "count", "expect": 969, "desc": "n m2m 4–12 мес"},
    {"id": "m2m_t13_24_rate", "kind": "rate", "expect": 37.72, "desc": "отток m2m 13–24 мес"},
    {"id": "m2m_t13_24_n", "kind": "count", "expect": 737, "desc": "n m2m 13–24 мес"},
    {"id": "m2m_t25_48_rate", "kind": "rate", "expect": 32.92, "desc": "отток m2m 25–48 мес"},
    {"id": "m2m_t25_48_n", "kind": "count", "expect": 802, "desc": "n m2m 25–48 мес"},
    {"id": "m2m_t49_rate", "kind": "rate", "expect": 26.02, "desc": "отток m2m 49+ мес"},
    {"id": "m2m_t49_n", "kind": "count", "expect": 342, "desc": "n m2m 49+ мес"},
    # --- Канал доставки ---
    {"id": "fiber_rate", "kind": "rate", "expect": 41.89, "desc": "отток Fiber optic"},
    {"id": "fiber_n", "kind": "count", "expect": 3096, "desc": "n Fiber optic"},
    {"id": "dsl_rate", "kind": "rate", "expect": 18.96, "desc": "отток DSL"},
    {"id": "dsl_n", "kind": "count", "expect": 2421, "desc": "n DSL"},
    {"id": "noinet_rate", "kind": "rate", "expect": 7.40, "desc": "отток без интернет-услуги"},
    {"id": "noinet_n", "kind": "count", "expect": 1526, "desc": "n без интернета"},
    {"id": "noinet_mean_tenure", "kind": "mean", "expect": 30.55,
     "desc": "средний tenure без интернета"},
    # --- Платёжный метод ---
    {"id": "echeck_rate", "kind": "rate", "expect": 45.29, "desc": "отток electronic check"},
    {"id": "echeck_n", "kind": "count", "expect": 2365, "desc": "n electronic check"},
    {"id": "cc_rate", "kind": "rate", "expect": 15.24, "desc": "отток credit card (automatic)"},
    {"id": "cc_n", "kind": "count", "expect": 1522, "desc": "n credit card (automatic)"},
    {"id": "echeck_share_new", "kind": "rate", "expect": 46.89,
     "desc": "доля e-check среди новичков"},
    {"id": "echeck_share_49", "kind": "rate", "expect": 21.75,
     "desc": "доля e-check в бакете 49+"},
    # --- Поддержка ---
    {"id": "nots_rate", "kind": "rate", "expect": 41.64, "desc": "отток без TechSupport"},
    {"id": "nots_n", "kind": "count", "expect": 3473, "desc": "n без TechSupport"},
    {"id": "ts_rate", "kind": "rate", "expect": 15.17, "desc": "отток с TechSupport"},
    {"id": "ts_n", "kind": "count", "expect": 2044, "desc": "n с TechSupport"},
    # --- Градиент аддонов (интернет-пользователи) ---
    {"id": "addons0_rate", "kind": "rate", "expect": 52.24, "desc": "отток при 0 аддонов"},
    {"id": "addons0_n", "kind": "count", "expect": 693, "desc": "n при 0 аддонов"},
    {"id": "addons6_rate", "kind": "rate", "expect": 5.28, "desc": "отток при 6 аддонов"},
    {"id": "addons6_n", "kind": "count", "expect": 284, "desc": "n при 6 аддонов"},
    # --- Цена ---
    {"id": "monthly_churned", "kind": "mean", "expect": 74.44,
     "desc": "средний MonthlyCharges ушедших"},
    {"id": "monthly_stayed", "kind": "mean", "expect": 61.27,
     "desc": "средний MonthlyCharges оставшихся"},
    # --- Стриминг-аддоны ---
    {"id": "stv_yes_rate", "kind": "rate", "expect": 30.07, "desc": "отток StreamingTV=yes"},
    {"id": "stv_yes_n", "kind": "count", "expect": 2707, "desc": "n StreamingTV=yes"},
    {"id": "stv_no_rate", "kind": "rate", "expect": 33.52, "desc": "отток StreamingTV=no"},
    {"id": "stv_no_n", "kind": "count", "expect": 2810, "desc": "n StreamingTV=no"},
    {"id": "stm_yes_rate", "kind": "rate", "expect": 29.94, "desc": "отток StreamingMovies=yes"},
    {"id": "stm_yes_n", "kind": "count", "expect": 2732, "desc": "n StreamingMovies=yes"},
    {"id": "stm_no_rate", "kind": "rate", "expect": 33.68, "desc": "отток StreamingMovies=no"},
    {"id": "stm_no_n", "kind": "count", "expect": 2785, "desc": "n StreamingMovies=no"},
    {"id": "stm_m2m_new_yes_rate", "kind": "rate", "expect": 73.56,
     "desc": "отток StreamingMovies=yes внутри m2m 0–3 мес"},
    {"id": "stm_m2m_new_yes_n", "kind": "count", "expect": 174, "desc": "n StreamingMovies=yes в m2m 0–3"},
    {"id": "stm_m2m_new_no_rate", "kind": "rate", "expect": 64.35,
     "desc": "отток StreamingMovies=no внутри m2m 0–3 мес"},
    {"id": "stm_m2m_new_no_n", "kind": "count", "expect": 620, "desc": "n StreamingMovies=no в m2m 0–3"},
    # --- Пожилые ---
    {"id": "senior_rate", "kind": "rate", "expect": 41.68, "desc": "отток SeniorCitizen=1"},
    {"id": "senior_n", "kind": "count", "expect": 1142, "desc": "n SeniorCitizen=1"},
    {"id": "nonsenior_rate", "kind": "rate", "expect": 23.61, "desc": "отток SeniorCitizen=0"},
    {"id": "nonsenior_n", "kind": "count", "expect": 5901, "desc": "n SeniorCitizen=0"},
    {"id": "senior_new_rate", "kind": "rate", "expect": 80.52,
     "desc": "отток пожилых среди новичков"},
    {"id": "senior_new_n", "kind": "count", "expect": 154, "desc": "n пожилых новичков"},
]

ADDONS = ["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport",
          "StreamingTV", "StreamingMovies"]


def tenure_bucket(value: str) -> str:
    t = int(value)
    if t <= 3:
        return "0-3"
    if t <= 12:
        return "4-12"
    if t <= 24:
        return "13-24"
    if t <= 48:
        return "25-48"
    return "49+"


def compute(rows: list[dict]) -> dict[str, float]:
    """Считает все срезы плана из CSV. Возвращает id → значение."""
    yes = [r for r in rows if r["Churn"] == "Yes"]
    cohort = [r for r in rows if int(r["tenure"]) <= 3]
    m2m = [r for r in rows if r["Contract"] == "Month-to-month"]
    m2m_cohort = [r for r in cohort if r["Contract"] == "Month-to-month"]
    b49 = [r for r in rows if tenure_bucket(r["tenure"]) == "49+"]
    noinet = [r for r in rows if r["InternetService"] == "No"]
    inet = [r for r in rows if r["InternetService"] != "No"]
    churned = [r for r in yes]
    stayed = [r for r in rows if r["Churn"] == "No"]

    def rate(sub: list[dict]) -> float:
        return 100.0 * sum(1 for r in sub if r["Churn"] == "Yes") / len(sub)

    def share(sub: list[dict], pred) -> float:
        return 100.0 * sum(1 for r in sub if pred(r)) / len(sub)

    def addon_count(r: dict) -> int:
        return sum(1 for a in ADDONS if r[a] == "Yes")

    out: dict[str, float] = {}
    out["total_n"] = len(rows)
    out["total_churn_n"] = len(yes)
    out["total_rate"] = rate(rows)
    out["mean_tenure"] = statistics.mean(int(r["tenure"]) for r in rows)
    out["mean_monthly"] = statistics.mean(float(r["MonthlyCharges"]) for r in rows)

    for prefix, contract in (("m2m", "Month-to-month"), ("1y", "One year"), ("2y", "Two year")):
        sub = [r for r in rows if r["Contract"] == contract]
        out[f"contract_{prefix}_rate"] = rate(sub)
        out[f"contract_{prefix}_n"] = len(sub)
        out[f"contract_{prefix}_churn"] = sum(1 for r in yes if r["Contract"] == contract)
    out["m2m_share_of_churn"] = 100.0 * out["contract_m2m_churn"] / len(yes)
    out["derived_m2m_minus_2y"] = out["contract_m2m_rate"] - out["contract_2y_rate"]

    for key, bucket in (("0_3", "0-3"), ("4_12", "4-12"), ("13_24", "13-24"),
                        ("25_48", "25-48"), ("49", "49+")):
        sub = [r for r in rows if tenure_bucket(r["tenure"]) == bucket]
        out[f"tenure_{key}_rate"] = rate(sub)
        out[f"tenure_{key}_n"] = len(sub)

    out["cohort_churners"] = sum(1 for r in cohort if r["Churn"] == "Yes")
    out["cohort_share_of_churn"] = 100.0 * out["cohort_churners"] / len(yes)
    for m in range(0, 7):
        sub = [r for r in rows if int(r["tenure"]) == m]
        out[f"tenure{m}_rate"] = rate(sub) if sub else 0.0
        out[f"tenure{m}_n"] = len(sub)

    out["new_m2m_share"] = share(cohort, lambda r: r["Contract"] == "Month-to-month")
    out["new_m2m_n"] = len(m2m_cohort)
    out["new_m2m_rate"] = rate(m2m_cohort)
    for prefix, contract in (("1y", "One year"), ("2y", "Two year")):
        sub = [r for r in cohort if r["Contract"] == contract]
        out[f"new_{prefix}_rate"] = rate(sub) if sub else 0.0
        out[f"new_{prefix}_n"] = len(sub)

    for key, bucket in (("0_3", "0-3"), ("4_12", "4-12"), ("13_24", "13-24"),
                        ("25_48", "25-48"), ("49", "49+")):
        sub = [r for r in m2m if tenure_bucket(r["tenure"]) == bucket]
        out[f"m2m_t{key}_rate"] = rate(sub)
        out[f"m2m_t{key}_n"] = len(sub)

    for prefix, service in (("fiber", "Fiber optic"), ("dsl", "DSL")):
        sub = [r for r in rows if r["InternetService"] == service]
        out[f"{prefix}_rate"] = rate(sub)
        out[f"{prefix}_n"] = len(sub)
    out["noinet_rate"] = rate(noinet)
    out["noinet_n"] = len(noinet)
    out["noinet_mean_tenure"] = statistics.mean(int(r["tenure"]) for r in noinet)

    for prefix, method in (("echeck", "Electronic check"),
                           ("cc", "Credit card (automatic)")):
        sub = [r for r in rows if r["PaymentMethod"] == method]
        out[f"{prefix}_rate"] = rate(sub)
        out[f"{prefix}_n"] = len(sub)
    out["echeck_share_new"] = share(cohort, lambda r: r["PaymentMethod"] == "Electronic check")
    out["echeck_share_49"] = share(b49, lambda r: r["PaymentMethod"] == "Electronic check")

    for prefix, value in (("nots", "No"), ("ts", "Yes")):
        sub = [r for r in rows if r["TechSupport"] == value]
        out[f"{prefix}_rate"] = rate(sub)
        out[f"{prefix}_n"] = len(sub)

    for k in (0, 6):
        sub = [r for r in inet if addon_count(r) == k]
        out[f"addons{k}_rate"] = rate(sub) if sub else 0.0
        out[f"addons{k}_n"] = len(sub)

    out["monthly_churned"] = statistics.mean(float(r["MonthlyCharges"]) for r in churned)
    out["monthly_stayed"] = statistics.mean(float(r["MonthlyCharges"]) for r in stayed)

    for col, tag in (("StreamingTV", "stv"), ("StreamingMovies", "stm")):
        for value, suffix in (("Yes", "yes"), ("No", "no")):
            sub = [r for r in rows if r[col] == value]
            out[f"{tag}_{suffix}_rate"] = rate(sub)
            out[f"{tag}_{suffix}_n"] = len(sub)
    for value, suffix in (("Yes", "yes"), ("No", "no")):
        sub = [r for r in m2m_cohort if r["StreamingMovies"] == value]
        out[f"stm_m2m_new_{suffix}_rate"] = rate(sub) if sub else 0.0
        out[f"stm_m2m_new_{suffix}_n"] = len(sub)

    for value, tag in (("1", "senior"), ("0", "nonsenior")):
        sub = [r for r in rows if r["SeniorCitizen"] == value]
        out[f"{tag}_rate"] = rate(sub)
        out[f"{tag}_n"] = len(sub)
    senior_new = [r for r in cohort if r["SeniorCitizen"] == "1"]
    out["senior_new_rate"] = rate(senior_new) if senior_new else 0.0
    out["senior_new_n"] = len(senior_new)
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="recompute_telco_slices.py",
        description="Пересчёт чисел ev-002 / research.md из первоисточника (CSV).",
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
        rows = list(csv.DictReader(handle))
    values = compute(rows)

    results = []
    mismatches = 0
    for spec in SLICES:
        got = values.get(spec["id"])
        expect = spec["expect"]
        if spec["kind"] in ("rate", "mean", "derived_pp"):
            ok = got is not None and abs(got - expect) <= TOL
            got_text = f"{got:.2f}" if got is not None else "—"
        else:
            ok = got == expect
            got_text = str(int(got)) if got is not None else "—"
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
        "script": "eval/recompute_telco_slices.py",
        "command": f"python3 eval/recompute_telco_slices.py --csv {args.csv}",
        "source": str(csv_path),
        "rows": len(rows),
        "utc": stamp,
        "tolerance_pp": TOL,
        "slices": results,
        "mismatches": mismatches,
    }
    (out_dir / "recompute-telco.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Пересчёт чисел демо (ev-002 ↔ research.md) из первоисточника",
        "",
        f"- Скрипт: `eval/recompute_telco_slices.py`; команда:",
        f"  `python3 eval/recompute_telco_slices.py --csv {args.csv}`",
        f"- Источник: `{csv_path}` ({len(rows)} записей); Дата (UTC): {stamp}",
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
    (out_dir / "recompute-telco.md").write_text("\n".join(lines), encoding="utf-8")

    for r in results:
        if not r["ok"]:
            print(f"РАСХОЖДЕНИЕ {r['id']}: ожидалось {r['expect']}, "
                  f"получено {r['got']} ({r['desc']})")
    print(f"срезов {len(results)}, расхождений {mismatches}; отчёт: {out_dir / 'recompute-telco.md'}")
    return EXIT_OK if mismatches == 0 else EXIT_MISMATCH


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
