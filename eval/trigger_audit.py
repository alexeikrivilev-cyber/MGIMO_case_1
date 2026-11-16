#!/usr/bin/env python3
"""trigger_audit.py — аудит триггера Консилиума (О5 итерация 3).

Предрегистрация: measurements.md §19.3 п.3 (продолжение
prod-council-lite.md §5 п.3). Триггер council-design §3: решение
классифицируется high-stakes, если НЕОБРАТИМО, или КРОСС-ФУНКЦИОНАЛЬНО,
или ВЫШЕ ПОРОГА $; low-stakes — совет off, много-линза одним вызовом.

Замер: 10 решений из демо и held-out прогонов классифицирует главный
агент (step-5-preview) одним прогоном, промпт зафиксирован (хеш в
отчёте). Метрики: доля high-stakes, доля low-stakes решений с
признаками high (пропуски), self-assessed уверенность. Вердикт по
предрегистрации: пропуски >0 → триггер требует второго прохода;
иначе триггер адекватен (proxy, n=10).

Классификатор — та же модель, что и агент: аудит САМООЦЕНКИ триггера
(self-assessed proxy, R3), не внешняя валидация.

Контракт CLI:
    python3 eval/trigger_audit.py [--out DIR] [--timeout SEC]

Коды возврата: 0 — аудит завершён; 4 — прогон упал.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

import run_label  # noqa: E402  (метка прогона — отдельный файл)

EXIT_OK = 0
EXIT_RUN_FAILED = 4
MODEL = "stepfun/step-5-preview"

# 10 решений прогонов: 5 демо (demo-retention) + 5 held-out
# (heldout-growth-segment). Каждое — с контекстом, который главный
# агент имел на чекпоинте; маркер EXPECTED — ожидание по протоколу
# council-design §3 (для сверки, не для подсказки модели).
CASES = [
    {
        "id": "demo-1",
        "task": "demo-retention",
        "decision": "Комбинация вариантов: «Первые 90 дней» (продуктовая интервенция) + «Риск-таргетинг» (коммуникационная) — база стратегии шага 4",
        "context": "Удержание 30-го дня упало с 34% до 21% [допущение сценария]; бюджет около нуля, только перераспределение; решения затрагивают продукт и коммуникации; эффект — в горизонте квартала.",
        "expected": "high",
    },
    {
        "id": "demo-2",
        "task": "demo-retention",
        "decision": "Вариант «Контракт на входе» (month-to-month → годовой с ценовым дифференцированием)",
        "context": "Меняет тарифную сетку — вне рамки brief.md «Что НЕ входит»; необратимо для восприятия цены; затрагивает продукт, цены, юридический и коммуникации.",
        "expected": "high",
    },
    {
        "id": "demo-3",
        "task": "demo-retention",
        "decision": "«Оставить как есть» — цена бездействия зафиксирована [прогноз]",
        "context": "Решение без действий: удержание фиксируется около 21% [прогноз]; необратимо по умолчанию; кросс-функциональность минимальна.",
        "expected": "high",
    },
    {
        "id": "demo-4",
        "task": "demo-retention",
        "decision": "Инициатива И1 «Измеряемость» — выгрузка когорт и единое определение метрики как блокер пилотов",
        "context": "Техническая инициатива: доступ к данным и метрология; обратима; внутри одного контура (данные + аналитика).",
        "expected": "low",
    },
    {
        "id": "demo-5",
        "task": "demo-retention",
        "decision": "Целевые метрики плана проверки: остановить падение и стабилизировать удержание (конкретные цифры — [прогноз])",
        "context": "Определение целей замера для уже выбранной комбинации; обратимо; аналитический контур.",
        "expected": "low",
    },
    {
        "id": "heldout-1",
        "task": "heldout-growth-segment",
        "decision": "Выбор ОДНОГО направления роста из трёх (ставка портфеля: B2B / 65+ / премиум) на квартал",
        "context": "Совет директелей дал квартал и один приоритет; выбор одного направления означает отказ от двух других на этот горизонт; кросс-функционально (продукт, цены, коммуникации, операция).",
        "expected": "high",
    },
    {
        "id": "heldout-2",
        "task": "heldout-growth-segment",
        "decision": "Направление «Библиотеки для компаний» (B2B)",
        "context": "Новый сегмент: новый продукт, продажи, онбординг; инвестиции в контур, которого нет; отказ от альтернатив на горизонт квартала.",
        "expected": "high",
    },
    {
        "id": "heldout-3",
        "task": "heldout-growth-segment",
        "decision": "Направление «Линейка 65+» (крупный шрифт, аудио, простая оплата)",
        "context": "Новая аудитория с иными требованиями доступности и оплаты; затрагивает продукт, поддержку, коммуникации; частично обратимо.",
        "expected": "high",
    },
    {
        "id": "heldout-4",
        "task": "heldout-growth-segment",
        "decision": "Направление «Премиальный тариф с эксклюзивом»",
        "context": "Тарифное решение внутри существующего продукта; ценообразование и восприятие; обратимее, чем новый сегмент, но меняет продуктовую линейку.",
        "expected": "high",
    },
    {
        "id": "heldout-5",
        "task": "heldout-growth-segment",
        "decision": "Правило перераспределения бюджета около нуля между каналами коммуникаций",
        "context": "Операционное распределение spend'а без изменения стратегии; обратимо ежеквартально; в рамках одного контура.",
        "expected": "low",
    },
]

AUDIT_PROMPT = """Ты — главный агент «Стратег» на чекпоинте классификации решений
(протокол council-design §3, триггер Консилиума).

Правило триггера: решение классифицируется HIGH-STAKES, если
НЕОБРАТИМО (или дорого обратить), или КРОСС-ФУНКЦИОНАЛЬНО (затрагивает
более одного контура: продукт, цены, коммуникации, данные, юридика),
или ВЫШЕ ПОРОГА $ (ставка выше квартального бюджета инициативы).
Иначе — LOW-STAKES: совет выключен, решение принимается много-линзой
одним вызовом и логируется.

Ниже 10 решений из двух прогонов агента. Для КАЖДОГО дай класс
(high|low), уверенность (0..1) и причину (до 15 слов). Сверься с
правилом, а не с интуицией о важности.

Формат ответа (строго, только JSON-массив):
[{{"id": "demo-1", "class": "high", "confidence": 0.9, "reason": "..."}}, ...]

=== РЕШЕНИЯ ===
{cases}
=== КОНЕЦ ==="""


def render_cases() -> str:
    parts = []
    for case in CASES:
        parts.append(
            f"- id: {case['id']} (задача {case['task']})\n"
            f"  решение: {case['decision']}\n"
            f"  контекст: {case['context']}"
        )
    return "\n".join(parts)


def parse_audit(text: str) -> list[dict] | None:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    out = []
    for item in data:
        if isinstance(item, dict) and "id" in item and "class" in item:
            out.append(item)
    return out or None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="trigger_audit.py")
    parser.add_argument("--out", default=None)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)

    import os

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении — аудит невозможен", file=sys.stderr)
        return EXIT_RUN_FAILED

    prompt = AUDIT_PROMPT.format(cases=render_cases())
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / f"o5-trigger-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_label.set_run_label("О4: o5-trigger-audit")
    try:
        proc = subprocess.run(
            ["opencode", "run", "--model", MODEL, prompt],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"аудит превысил таймаут {args.timeout}s", file=sys.stderr)
        return EXIT_RUN_FAILED
    finally:
        run_label.clear_run_label()

    (out_dir / "audit.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "audit.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / "audit.end").write_text(
        datetime.now(timezone.utc).isoformat() + f" exit={proc.returncode}\n", encoding="utf-8"
    )
    if proc.returncode != 0:
        print("прогон упал, детали в audit.err", file=sys.stderr)
        return EXIT_RUN_FAILED

    parsed = parse_audit(proc.stdout)
    if parsed is None:
        print("ответ не разобран (нет JSON-массива)", file=sys.stderr)
        return EXIT_RUN_FAILED

    by_id = {item["id"]: item for item in parsed}
    rows = []
    high = low = 0
    misses = 0  # low при ожидании high
    false_alarm = 0  # high при ожидании low
    confidences = []
    for case in CASES:
        item = by_id.get(case["id"])
        if not item:
            rows.append((case["id"], "?", case["expected"], "—", "нет ответа по кейсу"))
            continue
        klass = str(item.get("class", "?")).strip().lower()
        try:
            conf = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        confidences.append(conf)
        if klass == "high":
            high += 1
        elif klass == "low":
            low += 1
        if case["expected"] == "high" and klass == "low":
            misses += 1
        if case["expected"] == "low" and klass == "high":
            false_alarm += 1
        rows.append(
            (case["id"], klass, case["expected"], f"{conf:.2f}", str(item.get("reason", ""))[:60])
        )

    answered = high + low
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    summary = {
        "prompt_sha256_16": prompt_hash,
        "cases": len(CASES),
        "answered": answered,
        "high": high,
        "low": low,
        "misses_low_instead_of_high": misses,
        "false_alarm_high_instead_of_low": false_alarm,
        "avg_confidence": round(avg_conf, 2),
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = [
        "# Аудит триггера council (О5 итерация 3)",
        "",
        f"Промпт sha256 (16): {prompt_hash}",
        f"Кейсов: {len(CASES)}, ответов: {answered}, high: {high}, low: {low}",
        f"Пропуски (low вместо high): {misses}; ложные (high вместо low): {false_alarm}",
        f"Средняя уверенность: {avg_conf:.2f}",
        "",
        "| id | класс агента | ожидание | уверенность | причина |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        report.append("| " + " | ".join(str(c) for c in row) + " |")
    (out_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
