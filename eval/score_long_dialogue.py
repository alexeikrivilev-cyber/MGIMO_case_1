#!/usr/bin/env python3
"""score_long_dialogue.py — метрики M1–M5 (+M6) и вердикт экспериментов
«длинный диалог»: TASK-hermes-23 (§33, 12 поворотов, руки A/B/C) и
TASK-hermes-26 (§34, 36 поворотов, руки A2/C2).

Читает журнал `eval/runs/<runs>/{A,B,C}/turn-NN.{json,answer.md}` и считает
метрики по операциональзации предрегистраций:

    M1 — консистентность с артефактом: числа ответа против anchor-таблицы
         замороженных значений (совпадение / контрадикция / не сверено);
    M2 — grounding: `scripts/check_sources.py` по сохранённому ответу
         (правило C для пути eval/runs/…), доля grounded числовых
         утверждений;
    M3 — дрейф памяти: пробы 3/6/11 (§33) + 15/20/26/32/35 (§34); правило
         §34.3(б) — расхождение ЛЮБОЙ пробы с поворотом 3;
    M4 — стоимость/токены: поповоротно из БД OpenCode (meta.json), включая
         размер контекста (input + cache-read), итог по метке из COST.md;
    M5 — длина ответа в символах + поправка на сложность вопроса (A−C);
    M6 — поворот первой деградации (§34): минимальный поворот, на котором
         выполняется правило §34.3; «нет», если ни на одном.

Вердикт §33 — по предрегистрированному правилу §6 (дословно, без поправок
по результату). Вердикт §34 — по правилу §34.3 дословно:

    деградация = ЛЮБОЕ из:
      (а) хотя бы одна контрадикция с артефактом, ПОДТВЕРЖДЁННАЯ
          адъюдикацией (разбор каждой сырой находки — решение с
          основанием; файл `M1-adjudication.json` + `M1-adjudication.md`);
      (б) memory-проба на любом повороте расходится с поворотом 3;
      (в) доля grounded < 0.90 на двух поворотах подряд.

Контроль трактовки §34.4: те же правила применяются к руке C2.

Контракт CLI:
    python3 eval/score_long_dialogue.py [--runs DIR] [--out DIR]
        [--cost-label LABEL] [--adjudication FILE]

Коды возврата: 0 — скоринг выполнен; 2 — журнал не читается / адъюдикация
не покрывает сырые находки / решение адъюдикации вне словаря.
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
MEMORY_PROBES = (3, 6, 11, 15, 20, 26, 32, 35)  # §33 + §34.1
MEMORY_BASELINE_TURN = 3  # §34.3(б): пробы сверяются с поворотом 3
FIRST_TURN, LAST_TURN = 1, 12  # границы правила вердикта §33 (§6)
M2_DROP_THRESHOLD_PP = 20.0  # предрегистрация §6: падение >20 п.п.
M1_CONTRADICTION_TURNS = 2  # предрегистрация §6: ≥2 поворотов с контрадикцией
GROUNDED_FLOOR = 0.90  # §34.3(в): доля grounded ниже этого порога
ADJUDICATION_DECISIONS = ("контрадикция", "не контрадикция")
ADJUDICATION_CONFIRMED = "контрадикция"

# --- Anchor-таблица: замороженные значения артефактов демо -------------------
# Значения взяты из `project/*.md` и `project/evidence/ev-00*.md` ДО прогонов
# (предрегистрация §5). Число ответа, равное anchor (с точностью до округления
# до его же разрядов) — ok; близкое (±15% относительного), но не равное —
# контрадикция; вне таблицы — «не сверено».
#
# Таблица НЕ расширялась после прогонов §33 и НЕ расширяется после §34:
# расширить её под находки значило бы подгонять измеритель под результат
# (решение TASK-hermes-23). Новые величины evidence, названные агентами,
# разбираются адъюдикацией вручную.

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
    {"value": 2713, "meaning": "медиа- и развлекательных компания в отчёте Mixpanel", "source": "ev-001"},
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
    """Пробы памяти: метрика успеха и baseline.

    §33: пробы 3/6/11, дрейф = поворот 11 против поворота 3.
    §34: те же пробы + 15/20/26/32/35; правило §34.3(б) — расхождение
    ЛЮБОЙ пробы с поворотом 3 (метрика «удержание на 30-й день»,
    baseline 21%, докризисный 34%). Отсутствующие повороты (например,
    журнал §33 длиной 12) в правило не входят: сравнивать не с чем.
    """
    probes: dict[int, dict] = {}
    for turn in MEMORY_PROBES:
        if turn not in answers:
            continue  # журнал короче набора проб (§33: 12 поворотов) — сравнивать не с чем
        answer = answers[turn]
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
    baseline = probes.get(MEMORY_BASELINE_TURN)
    drift_turns: list[int] = []
    for turn, probe in sorted(probes.items()):
        if turn == MEMORY_BASELINE_TURN or baseline is None:
            continue
        diverged = (
            probe["metric_named"] != baseline["metric_named"]
            or probe["baseline_21"] != baseline["baseline_21"]
            or bool(probe["wrong_baseline_candidates"])
        )
        if diverged:
            drift_turns.append(turn)
    # Легаси-поле §33: дрейф последней пробы (11) против первой (3).
    first, last = probes.get(MEMORY_PROBES[0]), probes.get(MEMORY_PROBES[2])
    drift_last_vs_first = bool(
        first and last
        and (
            first["metric_named"] != last["metric_named"]
            or first["baseline_21"] != last["baseline_21"]
            or bool(last["wrong_baseline_candidates"])
        )
    )
    return {
        "probes": probes,
        "baseline_turn": MEMORY_BASELINE_TURN,
        "drift_turns_vs_baseline": drift_turns,
        "drift_last_vs_first": drift_last_vs_first,
    }


# --- M1: сырые находки и адъюдикация (§34.3(а)) -------------------------------


def m1_finding_key(arm: str, turn: int, index: int, as_written: str) -> str:
    """Ключ сырой находки M1 для соединения с решением адъюдикации.

    Индекс нужен, чтобы два одинаковых числа в одном повороте не
    склеились в одну находку: «полная адъюдикация» означает решение по
    КАЖДОЙ находке, а не по уникальным значениям.
    """
    return f"{arm}:{turn:02d}:{index:02d}:{as_written}"


def raw_m1_findings(journal: dict[str, dict[int, dict]]) -> list[dict]:
    """Все сырые «контрадикции» M1 по журналу — вход адъюдикации."""
    findings: list[dict] = []
    for arm in ARMS:
        for turn, meta in sorted(journal.get(arm, {}).items()):
            for index, claim in enumerate(meta["m1"]["contradiction_details"]):
                findings.append(
                    {
                        "key": m1_finding_key(arm, turn, index, claim["as_written"]),
                        "arm": arm,
                        "turn": turn,
                        "question": meta["question"],
                        "claim": claim,
                    }
                )
    return findings


def load_adjudication(path: Path, required_keys: list[str]) -> tuple[dict[str, dict[int, int]], dict]:
    """Решения адъюдикации: (рука → поворот → подтверждённых контрадикций, отчёт).

    Полнота проверяется механически: каждая сырая находка обязана иметь
    решение с основанием. Находка без решения — не «чисто», а
    неадъюдирована: вердикт §34.3(а) по ней принимать нельзя (exit 2).
    Решение вне словаря (`контрадикция` / `не контрадикция`) — тоже
    отказ: опечатка не должна молча означать «не контрадикция».
    """
    if not path.is_file():
        return {}, {
            "attached": False,
            "file": str(path),
            "raw_findings": len(required_keys),
            "reason": "файл адъюдикации не найден — пункт §34.3(а) в вердикт не вносится",
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    decisions = data.get("decisions")
    if not isinstance(decisions, list):
        raise SystemExit(f"адъюдикация {path}: нет списка decisions")
    by_key: dict[str, dict] = {}
    for decision in decisions:
        key = decision.get("key")
        if not key:
            raise SystemExit(f"адъюдикация {path}: решение без ключа: {decision}")
        if key in by_key:
            raise SystemExit(f"адъюдикация {path}: дубликат ключа {key}")
        verdict = decision.get("decision")
        if verdict not in ADJUDICATION_DECISIONS:
            raise SystemExit(
                f"адъюдикация {path}: решение {key} = {verdict!r} вне словаря "
                f"{ADJUDICATION_DECISIONS}"
            )
        if not decision.get("basis"):
            raise SystemExit(f"адъюдикация {path}: решение {key} без основания")
        by_key[key] = decision
    missing = [key for key in required_keys if key not in by_key]
    if missing:
        raise SystemExit(
            f"адъюдикация {path} не покрывает {len(missing)} сырых находок M1 "
            f"(первые: {missing[:5]}) — правило §34.3(а) требует разбора КАЖДОЙ"
        )
    extra = [key for key in by_key if key not in set(required_keys)]
    confirmed: dict[str, dict[int, int]] = {}
    for key, decision in by_key.items():
        if key in extra or decision["decision"] != ADJUDICATION_CONFIRMED:
            continue
        arm, turn = key.split(":")[0], int(key.split(":")[1])
        confirmed.setdefault(arm, {})
        confirmed[arm][turn] = confirmed[arm].get(turn, 0) + 1
    report = {
        "attached": True,
        "file": str(path),
        "raw_findings": len(required_keys),
        "decisions": len(by_key),
        "confirmed_contradictions": sum(
            count for turns in confirmed.values() for count in turns.values()
        ),
        "extra_keys_ignored": extra,
    }
    return confirmed, report


# --- Правило вердикта §33 (§6, легаси) ---------------------------------------


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


# --- Правило вердикта §34.3 (дословно) + M6 -----------------------------------


def degradation_events_34(metrics: dict[int, dict], m3: dict,
                          confirmed_contradictions: dict[int, int]) -> list[dict]:
    """События деградации §34.3 по поворотам: (поворот, пункт, пояснение).

    (а) подтверждённая адъюдикацией контрадикция с артефактом;
    (б) memory-проба расходится с поворотом 3 (поворот деградации — сам
        поворот пробы, а не поворот 3: правило выполнилось на нём);
    (в) доля grounded < 0.90 на двух поворотах подряд (поворот деградации —
        второй из пары: на нём правило сработало).
    """
    events: list[dict] = []
    for turn in sorted(confirmed_contradictions):
        if confirmed_contradictions[turn] > 0:
            events.append(
                {
                    "turn": turn,
                    "rule": "а",
                    "detail": (
                        f"контрадикция с артефактом подтверждена адъюдикацией "
                        f"({confirmed_contradictions[turn]})"
                    ),
                }
            )
    for turn in m3.get("drift_turns_vs_baseline", []):
        events.append(
            {
                "turn": turn,
                "rule": "б",
                "detail": "memory-проба расходится с поворотом 3",
            }
        )
    shares = {
        t: m["m2"]["share"]
        for t, m in metrics.items()
        if m["m2"]["share"] is not None
    }
    for turn in sorted(shares):
        prev = turn - 1
        if prev in shares and shares[prev] < GROUNDED_FLOOR and shares[turn] < GROUNDED_FLOOR:
            events.append(
                {
                    "turn": turn,
                    "rule": "в",
                    "detail": (
                        f"доля grounded {shares[prev]:.2f} и {shares[turn]:.2f} < "
                        f"{GROUNDED_FLOOR} на поворотах {prev} и {turn}"
                    ),
                }
            )
    events.sort(key=lambda e: (e["turn"], e["rule"]))
    return events


def verdict_for_arm_34(metrics: dict[int, dict], m3: dict,
                       confirmed_contradictions: dict[int, int]) -> dict:
    """Вердикт §34.3 (дословно) + M6 — поворот первой деградации."""
    events = degradation_events_34(metrics, m3, confirmed_contradictions)
    return {
        "events": events,
        "triggered": [f"§34.3({e['rule']}) поворот {e['turn']}: {e['detail']}" for e in events],
        "m6_first_degradation_turn": events[0]["turn"] if events else None,
        "verdict": "Деградация подтверждена" if events else "Деградации не обнаружено",
    }


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


def context_summary(metrics: dict[int, dict]) -> dict:
    """Размер контекста по поворотам (None, если БД не отдала токены)."""
    values = {
        t: m["m4"].get("context_tokens")
        for t, m in sorted(metrics.items())
        if m["m4"].get("context_tokens") is not None
    }
    if not values:
        return {"first_turn": None, "last_turn": None, "max": None, "per_turn": {}}
    last_turn = max(values)
    return {
        "first_turn": values[min(values)],
        "last_turn": values[last_turn],
        "max": max(values.values()),
        "per_turn": {str(t): v for t, v in values.items()},
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="score_long_dialogue.py")
    parser.add_argument("--runs", default=str(RUNS_ROOT))
    parser.add_argument("--out", default=None)
    parser.add_argument("--cost-label", default="t23-longdialogue",
                        help="метка строк COST.md этого прогона (по умолчанию §33)")
    parser.add_argument("--adjudication", default=None,
                        help="файл решений адъюдикации M1 (по умолчанию "
                             "<runs>/M1-adjudication.json)")
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

    # Первый проход: метрики по поворотам (M1 считается и для журнала, и
    # для списка сырых находок — один compute, два потребителя).
    scored: dict[str, dict[int, dict]] = {}
    for arm in ARMS:
        turns = journal[arm]
        if not turns:
            scored[arm] = {}
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
        scored[arm] = metrics

    # Адъюдикация M1: решения по КАЖДОЙ сырой находке (правило §34.3(а)).
    journal_with_m1 = {
        arm: {t: {"question": meta["question"], "m1": scored[arm][t]["m1"]}
              for t, meta in turns.items()}
        for arm, turns in journal.items()
    }
    findings = raw_m1_findings(journal_with_m1)
    (runs_root / "m1-raw.json").write_text(
        json.dumps(
            {
                "runs_root": str(runs_root),
                "raw_contradictions": findings,
                "note": "сырые находки M1 до адъюдикации; ключи обязаны быть "
                        "покрыты решениями M1-adjudication.json",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    adjudication_path = (
        Path(args.adjudication) if args.adjudication else runs_root / "M1-adjudication.json"
    )
    confirmed, adjudication_report = load_adjudication(
        adjudication_path, [f["key"] for f in findings]
    )

    report: dict = {
        "runs_root": str(runs_root),
        "cost_label": args.cost_label,
        "cost_rows": cost_rows(args.cost_label),
        "adjudication": adjudication_report,
        "arms": {},
    }
    for arm in ARMS:
        metrics = scored[arm]
        if not metrics:
            continue
        m3 = score_m3({t: journal[arm][t]["answer_text"] for t in metrics})
        verdict33 = verdict_for_arm(metrics, m3)
        verdict34 = verdict_for_arm_34(metrics, m3, confirmed.get(arm, {}))
        raw_contra_turns = sorted(verdict33["contradiction_turns"])
        confirmed_turns = sorted(
            t for t, count in confirmed.get(arm, {}).items() if count > 0
        )
        report["arms"][arm] = {
            "metrics": metrics,
            "m3": m3,
            "verdict": verdict33,
            "verdict_34": verdict34,
            "m6_first_degradation_turn": verdict34["m6_first_degradation_turn"],
            "m1": {
                "raw_contradiction_turns": raw_contra_turns,
                "confirmed_contradiction_turns": confirmed_turns,
            },
            "context": context_summary(metrics),
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
    print(
        f"адъюдикация M1: {'подключена' if adjudication_report['attached'] else 'НЕ ПОДКЛЮЧЕНА'}"
        f" ({adjudication_report.get('raw_findings', 0)} сырых находок, "
        f"подтверждено {adjudication_report.get('confirmed_contradictions', 0)})"
    )
    for arm, data in report["arms"].items():
        verdict = data["verdict"]
        verdict34 = data["verdict_34"]
        print(
            f"рука {arm}: §33-правило {verdict['verdict']} | §34.3 {verdict34['verdict']} | "
            f"M6 {data['m6_first_degradation_turn']} | контрадикций сырых "
            f"{verdict['contradiction_turns']} / подтверждённых "
            f"{data['m1']['confirmed_contradiction_turns']} | M2 Δ {verdict['m2_drop_pp']} п.п. | "
            f"M3 дрейф {verdict['m3_drift']} | $ {data['totals']['usd_formula']}"
        )
    if not adjudication_report["attached"]:
        print(
            "ВНИМАНИЕ: адъюдикация M1 не подключена — пункт §34.3(а) вердикта "
            "не подтверждён ни одной находкой (сырые находки — в m1-raw.json). "
            "Вердикт §34 без адъюдикации не финальный.",
            file=sys.stderr,
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
