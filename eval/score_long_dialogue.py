#!/usr/bin/env python3
"""score_long_dialogue.py — метрики M1–M5 и вердикт эксперимента TASK-hermes-23.

Читает журнал `eval/runs/t23-longdialogue/{A,B,C}/turn-NN.{json,answer.md}`
и считает метрики по операциональлизации предрегистрации §5:

    M1 — консистентность с артефактом: числа ответа против anchor-таблицы
         замороженных значений (совпадение / контрадикция / не сверено);
    M2 — grounding: `scripts/check_sources.py` по сохранённому ответу
         (правило C для пути eval/runs/…), доля grounded числовых
         утверждений;
    M3 — дрейф памяти: пробы 3/6/11 (метрика успеха + baseline) между собой
         и против anchor-таблицы;
    M4 — стоимость/токены: поповоротно из БД OpenCode (meta.json), итог по
         метке `t23-longdialogue*` из COST.md;
    M5 — длина ответа в символах + поправка на сложность вопроса (A−C).

Вердикт — по предрегистрированному правилу §6, дословно, без поправок по
результату.

Контракт CLI:
    python3 eval/score_long_dialogue.py [--runs DIR] [--out DIR]

Коды возврата: 0 — скоринг выполнен; 2 — журнал не читается.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_sources  # noqa: E402  (правила hard-claim/grounding — из гейта)

EXIT_OK = 0
EXIT_USAGE = 2

RUNS_ROOT = REPO_ROOT / "eval" / "runs" / "t23-longdialogue"
ARMS = ("A", "B", "C")
MEMORY_PROBES = (3, 6, 11)
FIRST_TURN, LAST_TURN = 1, 12
M2_DROP_THRESHOLD_PP = 20.0  # предрегистрация §6: падение >20 п.п.
M1_CONTRADICTION_TURNS = 2  # предрегистрация §6: ≥2 поворотов с контрадикцией

# --- Anchor-таблица: замороженные значения артефактов демо -------------------
# Значения взяты из `project/*.md` и `project/evidence/ev-00*.md` ДО прогонов
# (предрегистрация §5). Число ответа, равное anchor (с точностью до округления
# до его же разрядов) — ok; близкое (±15% относительного), но не равное —
# контрадикция; вне таблицы — «не сверено».

ANCHORS: list[dict] = [
    {"value": 21, "meaning": "удержание на 30-й день, baseline (сценарий запроса РП)", "source": "brief.md; strategy-product.md; verification-plan.md"},
    {"value": 34, "meaning": "докризисный уровень удержания на 30-й день", "source": "brief.md"},
    {"value": 2.1, "meaning": "млн активных подписчиков", "source": "brief.md"},
    {"value": 13, "meaning": "п.п. падения удержания за полгода", "source": "options.md"},
    {"value": 8, "meaning": "% — прогноз удержания через полгода без воздействия", "source": "options.md"},
    {"value": 273, "meaning": "тыс. подписчиков — цена бездействия", "source": "options.md; strategy-comms.md"},
    {"value": 441, "meaning": "тыс. подписчиков в когорте при удержании 21%", "source": "options.md"},
    {"value": 714, "meaning": "тыс. подписчиков в когорте при удержании 34%", "source": "options.md"},
    {"value": 56.21, "meaning": "отток при tenure 0–3 мес, n = 1 062", "source": "ev-002"},
    {"value": 1062, "meaning": "n когорты tenure 0–3 мес", "source": "ev-002"},
    {"value": 31.94, "meaning": "доля оттока датасета от когорты 0–3 мес", "source": "ev-002"},
    {"value": 26.54, "meaning": "накопленный отток датасета", "source": "ev-002"},
    {"value": 7043, "meaning": "записей в датасете", "source": "ev-002"},
    {"value": 42.71, "meaning": "отток month-to-month", "source": "ev-002"},
    {"value": 11.27, "meaning": "отток one-year", "source": "ev-002"},
    {"value": 2.83, "meaning": "отток two-year", "source": "ev-002"},
    {"value": 96.52, "meaning": "доля month-to-month среди новичков", "source": "ev-002"},
    {"value": 1025, "meaning": "n новичков на month-to-month", "source": "ev-002"},
    {"value": 61.99, "meaning": "отток первого месяца, n = 613", "source": "ev-002"},
    {"value": 613, "meaning": "n когорты первого месяца", "source": "ev-002"},
    {"value": 38.01, "meaning": "удержание первого месяца (производная)", "source": "ev-002"},
    {"value": 52.24, "meaning": "отток при нуле подключённых услуг, n = 693", "source": "ev-002"},
    {"value": 693, "meaning": "n когорты без услуг", "source": "ev-002"},
    {"value": 46.89, "meaning": "доля e-check среди новичков", "source": "ev-002"},
    {"value": 21.75, "meaning": "доля e-check в бакете 49+", "source": "ev-002"},
    {"value": 41.64, "meaning": "отток без TechSupport, n = 3 473", "source": "ev-002"},
    {"value": 3473, "meaning": "n когорты без TechSupport", "source": "ev-002"},
    {"value": 15.17, "meaning": "отток с TechSupport, n = 2 044", "source": "ev-002"},
    {"value": 2044, "meaning": "n когорты с TechSupport", "source": "ev-002"},
    {"value": 41.89, "meaning": "отток при fiber", "source": "ev-002"},
    {"value": 18.96, "meaning": "отток при DSL", "source": "ev-002"},
    {"value": 45.29, "meaning": "отток при electronic check", "source": "ev-002"},
    {"value": 15.24, "meaning": "отток при автоплатеже", "source": "ev-002"},
    {"value": 30.07, "meaning": "отток со стриминг-аддонами (по базе)", "source": "ev-002"},
    {"value": 29.94, "meaning": "отток со стриминг-аддонами (по базе)", "source": "ev-002"},
    {"value": 33.52, "meaning": "отток без стриминг-аддонов (по базе)", "source": "ev-002"},
    {"value": 33.68, "meaning": "отток без стриминг-аддонов (по базе)", "source": "ev-002"},
    {"value": 73.56, "meaning": "отток с аддонами внутри 0–3 мес", "source": "ev-002"},
    {"value": 64.35, "meaning": "отток без аддонов внутри 0–3 мес", "source": "ev-002"},
    {"value": 32.37, "meaning": "средний tenure, месяцы", "source": "ev-002"},
    {"value": 0.8411, "meaning": "AUC модели риска на аналоге", "source": "ev-003"},
    {"value": 1.9, "meaning": "ежемесячный отток зрелого рынка, %", "source": "ev-003"},
    {"value": 3.3, "meaning": "нижняя граница эффекта таргетинга, п.п. оттока за цикл", "source": "ev-003"},
    {"value": 5.3, "meaning": "верхняя граница эффекта таргетинга, п.п. оттока за цикл", "source": "ev-003"},
    {"value": 199, "meaning": "тыс. единиц — нижняя граница эффекта таргетинга", "source": "strategy-product.md"},
    {"value": 319, "meaning": "тыс. единиц — верхняя граница эффекта таргетинга", "source": "strategy-product.md"},
    {"value": 0.75, "meaning": "порог приёмки локального AUC", "source": "strategy-comms.md; strategy-product.md"},
    {"value": 2, "meaning": "п.п. — порог разницы пилот−контроль", "source": "verification-plan.md"},
    {"value": 90, "meaning": "дней — окно пилота «Первые 90 дней»", "source": "strategy-product.md"},
    {"value": 3.72, "meaning": "трлн событий в отчёте Mixpanel", "source": "ev-001"},
    {"value": 14.16, "meaning": "млрд уникальных пользователей в отчёте Mixpanel", "source": "ev-001"},
    {"value": 2713, "meaning": "медиа-и развлекательных компаний в отчёте Mixpanel", "source": "ev-001"},
]

# Числа-периоды и перечисления, не несущие факт о проекте.
STRUCTURAL_SKIP = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 30, 49, 100}

NUMBER_RE = re.compile(
    r"(?<![\d.,])(\d+(?:[ \u00a0]\d{3})*(?:[.,]\d+)?)(\s*(?:%|п\.п\.|млн|тыс|трлн|млрд|K|M)?)"
)
YEAR_RE = re.compile(r"^\d{4}$")
# Идентификаторы и даты — не числовые утверждения: без этой зачистки
# sessionID («ses_e1108c355ffe…») и «2026-11-17» давали бы «контрадикции»
# в КАЖДОМ повороте — дефект измерителя, а не свойство агента.
ID_TOKEN_RE = re.compile(r"\b(?:ses|prt|msg|ses_)[_-][A-Za-z0-9]{6,}|\b[A-Za-z]*_[A-Za-z0-9]{16,}\b")
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _decimals(text: str) -> int:
    return len(text.split(",", 1)[1]) if "," in text else (len(text.split(".", 1)[1]) if "." in text else 0)


def _rounds_to(anchor: float, candidate: float) -> bool:
    """Кандидат — anchor, округлённый до его разрядов (или наоборот)."""
    for a, b in ((anchor, candidate), (candidate, anchor)):
        if round(a, _sig_decimals(b)) == b:
            return True
    return False


def _sig_decimals(value: float) -> int:
    text = f"{value:f}".rstrip("0")
    return len(text.split(".", 1)[1]) if "." in text else 0


def strip_non_claims(text: str) -> str:
    """Убрать из текста идентификаторы и ISO-даты перед извлечением чисел.

    Журнальная шапка ответа несёт sessionID (`ses_…`), а агент называет
    даты решений («2026-11-17»): цифры внутри них — не утверждения о
    проекте. Дефект найден разбором первых находок M1 (контрадикция в
    КАЖДОМ повороте из-за «1108» внутри sessionID) и исправлен в
    измерителе, а не спрятан в отчёте.
    """
    return ISO_DATE_RE.sub(" ", ID_TOKEN_RE.sub(" ", text))


def extract_numbers(text: str) -> list[tuple[float, str, str, str]]:
    """Числа ответа: (значение, как в тексте, единица, без единицы)."""
    found: list[tuple[float, str, str, str]] = []
    for match in NUMBER_RE.finditer(strip_non_claims(text)):
        raw, unit = match.group(1), (match.group(2) or "").strip()
        plain = raw.replace(" ", "").replace("\u00a0", "").replace(",", ".")
        try:
            value = float(plain)
        except ValueError:
            continue
        if unit in ("K", "M") and value < 1000:
            value = value * (1000 if unit == "K" else 1_000_000)
        found.append((value, f"{raw}{(' ' + unit) if unit else ''}", unit, raw))
    return found


def classify(value: float, as_written: str, unit: str, raw: str,
             question: str) -> tuple[str, dict | None]:
    """ok / контрадикция / не сверено + anchor при совпадении."""
    if raw in question:
        return "из вопроса РП", None
    if YEAR_RE.match(as_written) and 1900 <= value <= 2100:
        return "дата", None
    if not unit and value == int(value) and int(value) in STRUCTURAL_SKIP:
        return "структурное число", None
    best: dict | None = None
    best_diff: float | None = None
    for anchor in ANCHORS:
        target = anchor["value"]
        if target == 0:
            continue
        diff = abs(value - target) / abs(target)
        if best_diff is None or diff < best_diff:
            best, best_diff = anchor, diff
    if best is None or best_diff is None:
        return "не сверено", None
    if best_diff == 0 or _rounds_to(best["value"], value):
        return "ok", best
    if best_diff <= 0.15:
        return "контрадикция", best
    return "не сверено", None


def score_m1(answer: str, question: str) -> dict:
    claims: list[dict] = []
    for value, as_written, unit, raw in extract_numbers(answer):
        verdict, anchor = classify(value, as_written, unit, raw, question)
        if verdict in ("из вопроса РП", "дата", "структурное число"):
            continue
        claims.append(
            {
                "value": value,
                "as_written": as_written,
                "verdict": verdict,
                "anchor": anchor["value"] if anchor else None,
                "anchor_meaning": anchor["meaning"] if anchor else None,
                "anchor_source": anchor["source"] if anchor else None,
            }
        )
    contradictions = [c for c in claims if c["verdict"] == "контрадикция"]
    return {
        "claims": len(claims),
        "ok": sum(1 for c in claims if c["verdict"] == "ok"),
        "contradictions": len(contradictions),
        "unverified": sum(1 for c in claims if c["verdict"] == "не сверено"),
        "contradiction_details": contradictions,
    }


def score_m2(answer_path: Path) -> dict:
    """Grounding: доля числовых утверждений с основанием в строке."""
    text = answer_path.read_text(encoding="utf-8-sig")
    active = check_sources._active_lines(text)
    measurement_log = check_sources._is_measurement_log(answer_path)
    claims = 0
    grounded = 0
    ungrounded_lines: list[int] = []
    for lineno, line in active:
        if not check_sources._is_hard_claim(line):
            continue
        claims += 1
        if check_sources._is_grounded(line, measurement_log):
            grounded += 1
        else:
            ungrounded_lines.append(lineno)
    return {
        "claims": claims,
        "grounded": grounded,
        "share": round(grounded / claims, 4) if claims else None,
        "ungrounded_lines": ungrounded_lines,
        "gate_problems": len(check_sources.check_file(answer_path)),
    }


def baseline_contradictions(answer: str) -> list[dict]:
    """Процентные величины, близкие к baseline 21% / 34%, но не равные им.

    Отдельно от общей anchor-сверки: «24%» ближе к 26.54% (отток датасета),
    чем к 21%, и общий классификатор отнёс бы его к чужому anchor — для
    дрейфа памяти важен именно конфликт с baseline метрики успеха.
    """
    found: list[dict] = []
    for value, as_written, unit, _raw in extract_numbers(answer):
        if unit != "%":
            continue
        for target in (21, 34):
            if value == target:
                continue
            if abs(value - target) / target <= 0.15:
                found.append({"as_written": as_written, "value": value, "anchor": target})
    return found


def score_m3(answers: dict[int, str]) -> dict:
    """Пробы памяти 3/6/11: метрика успеха и baseline."""
    probes: dict[int, dict] = {}
    for turn in MEMORY_PROBES:
        answer = answers.get(turn, "")
        lowered = answer.lower()
        metric_ok = ("30-й день" in lowered) or ("d30" in lowered) or ("30-й" in lowered)
        probes[turn] = {
            "metric_named": metric_ok,
            "baseline_21": bool(re.search(r"\b21\s*%", answer)),
            "baseline_34_context": bool(re.search(r"\b34\s*%", answer)),
            "wrong_baseline_candidates": [
                c["as_written"] for c in baseline_contradictions(answer)
            ],
        }
    first, last = probes[MEMORY_PROBES[0]], probes[MEMORY_PROBES[-1]]
    drift = (first["metric_named"] != last["metric_named"]) or (
        first["baseline_21"] != last["baseline_21"]
    ) or bool(last["wrong_baseline_candidates"])
    return {"probes": probes, "drift_last_vs_first": drift}


def load_journal(runs_root: Path) -> dict[str, dict[int, dict]]:
    journal: dict[str, dict[int, dict]] = {}
    for arm in ARMS:
        arm_dir = runs_root / arm
        turns: dict[int, dict] = {}
        if not arm_dir.is_dir():
            journal[arm] = turns
            continue
        for meta_path in sorted(arm_dir.glob("turn-*.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            answer_path = runs_root / meta["answer_file"]
            meta["answer_text"] = answer_path.read_text(encoding="utf-8") if answer_path.is_file() else ""
            turns[meta["turn"]] = meta
        journal[arm] = turns
    return journal


def cost_rows(label_prefix: str) -> list[dict]:
    """Строки прод-таблицы COST.md с меткой прогона."""
    text = (REPO_ROOT / "COST.md").read_text(encoding="utf-8-sig")
    rows: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or label_prefix not in stripped:
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 11 or cells[0] == "Дата":
            continue
        rows.append(
            {
                "date": cells[0], "session_id": cells[1], "label": cells[2], "model": cells[3],
                "in": cells[4], "out": cells[5], "reasoning": cells[6], "cache_read": cells[7],
                "cache_write": cells[8], "search": cells[9], "usd": cells[10],
            }
        )
    return rows


def verdict_for_arm(metrics: dict[int, dict], m3: dict) -> dict:
    """Вердикт по предрегистрированному правилу §6 (дословно)."""
    contra_turns = [t for t, m in metrics.items() if m["m1"]["contradictions"] > 0]
    m2_first = metrics.get(FIRST_TURN, {}).get("m2", {}).get("share")
    m2_last = metrics.get(LAST_TURN, {}).get("m2", {}).get("share")
    m2_drop = (
        round((m2_first - m2_last) * 100, 1)
        if isinstance(m2_first, float) and isinstance(m2_last, float)
        else None
    )
    triggered = []
    if len(contra_turns) >= M1_CONTRADICTION_TURNS:
        triggered.append(f"M1: контрадикции в {len(contra_turns)} поворотах {contra_turns}")
    if m3.get("drift_last_vs_first"):
        triggered.append("M3: дрейф пробы памяти (поворот 11 против поворота 3)")
    if m2_drop is not None and m2_drop > M2_DROP_THRESHOLD_PP:
        triggered.append(f"M2: доля grounded упала на {m2_drop} п.п.")
    return {
        "contradiction_turns": contra_turns,
        "m2_drop_pp": m2_drop,
        "m3_drift": m3.get("drift_last_vs_first"),
        "triggered": triggered,
        "verdict": "Деградация подтверждена" if triggered else "Деградации не обнаружено",
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="score_long_dialogue.py")
    parser.add_argument("--runs", default=str(RUNS_ROOT))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    runs_root = Path(args.runs)
    if not runs_root.is_dir():
        print(f"журнал не найден: {runs_root}", file=sys.stderr)
        return EXIT_USAGE
    journal = load_journal(runs_root)
    if not any(journal.values()):
        print(f"в журнале нет поворотов: {runs_root}", file=sys.stderr)
        return EXIT_USAGE

    gates_dir = runs_root / "gates"
    gates_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {"arms": {}, "cost_rows": cost_rows("t23-longdialogue")}
    for arm in ARMS:
        turns = journal[arm]
        if not turns:
            continue
        metrics: dict[int, dict] = {}
        for turn in sorted(turns):
            meta = turns[turn]
            answer_path = runs_root / meta["answer_file"]
            m1 = score_m1(meta["answer_text"], meta["question"])
            m2 = score_m2(answer_path)
            gate_out = gates_dir / f"sources-{arm}-{turn:02d}.txt"
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "check_sources.py"), str(answer_path)],
                capture_output=True, text=True,
            )
            gate_out.write_text(
                f"$ python3 scripts/check_sources.py {answer_path}\n\n{proc.stdout}"
                f"(exit {proc.returncode})\n", encoding="utf-8",
            )
            metrics[turn] = {
                "status": meta["status"],
                "answer_chars": meta["answer_chars"],
                "m1": m1,
                "m2": m2,
                "m4": meta.get("metrics_db", {}),
                "m5": {"chars": meta["answer_chars"]},
                "gate_exit": proc.returncode,
            }
        m3 = score_m3({t: turns[t]["answer_text"] for t in turns})
        report["arms"][arm] = {
            "metrics": metrics,
            "m3": m3,
            "verdict": verdict_for_arm(metrics, m3),
            "totals": {
                "input_tokens": sum(
                    (metrics[t]["m4"].get("input") or 0) for t in metrics
                ),
                "output_tokens": sum(
                    (metrics[t]["m4"].get("output") or 0) for t in metrics
                ),
                "cache_read_tokens": sum(
                    (metrics[t]["m4"].get("cache_read") or 0) for t in metrics
                ),
                "usd_formula": round(
                    sum((metrics[t]["m4"].get("cost_usd_formula") or 0) for t in metrics), 4
                ),
                "tool_calls": sum(
                    (metrics[t]["m4"].get("tool_calls") or 0) for t in metrics
                ),
                "patch_parts": sum(
                    (metrics[t]["m4"].get("patch_parts") or 0) for t in metrics
                ),
                "failed_turns": [
                    t for t in metrics if metrics[t]["status"] != "OK"
                ],
            },
        }

    # M5 с поправкой на сложность вопроса: A(t) − C(t)
    if "A" in report["arms"] and "C" in report["arms"]:
        a_chars = {t: m["answer_chars"] for t, m in report["arms"]["A"]["metrics"].items()}
        c_chars = {t: m["answer_chars"] for t, m in report["arms"]["C"]["metrics"].items()}
        report["m5_delta_a_minus_c"] = {
            str(t): a_chars[t] - c_chars[t] for t in sorted(set(a_chars) & set(c_chars))
        }

    out_path = Path(args.out) if args.out else runs_root / "metrics.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"метрики записаны: {out_path}")
    for arm, data in report["arms"].items():
        verdict = data["verdict"]
        print(
            f"рука {arm}: {verdict['verdict']} | контрадикций в поворотах "
            f"{verdict['contradiction_turns']} | M2 Δ {verdict['m2_drop_pp']} п.п. | "
            f"M3 дрейф {verdict['m3_drift']} | $ {data['totals']['usd_formula']}"
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
