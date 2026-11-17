#!/usr/bin/env python3
"""trigger_audit_heldout.py — аудит триггера Консилиума на held-out артефактах.

Предрегистрация: measurements.md §27.1 ДО замера (TASK-hermes-13,
развилка BRIEF п.25 «(б) триггер council на held-out артефактах»).

Отличие от `eval/trigger_audit.py` (§19.3, кейсы ПУТИ демо/held-out,
кейсы и ожидания писал оркестратор): здесь кейсы — РЕАЛЬНЫЕ решения
прогона held-out-growth-segment, взятые из артефактов
(`artifacts/STATE.md` — решения шага 4, `artifacts/options.md` —
выбор ЧЕКПОИНТА 3). Правило триггера council-design §3, модель и
формат ответа — дословно как в §19.3; меняется только блок кейсов,
хеш промпта фиксируется в отчёте.

Классификатор — та же модель, что и агент: аудит САМООЦЕНКИ триггера
(self-assessed proxy, R3), не внешняя валидация. Ожидания расставлены
оркестратором ПО ПРАВИЛУ council-design §3 (необратимо /
кросс-функционально / выше порога $) — сверка, не подсказка модели.

Контракт CLI:
    python3 eval/trigger_audit_heldout.py [--out DIR] [--timeout SEC]

Коды возврата: 0 — аудит завершён; 4 — прогон упал.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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

# 5 реальных решений прогона held-out (источник — артефакты задачи).
# Ожидание — по правилу council-design §3, расставлено ДО прогона
# (§27.1): high = необратимо на горизонте / кросс-функционально /
# выше порога $; иначе low.
CASES = [
    {
        "id": "ho-1",
        "decision": "Выбор на ЧЕКПОИНТЕ 3: квартальная ставка — вариант 4 «Второй месяц», вариант 3 «Премиум на том, что есть» — подчинённым тестом с holdout внутри той же ставки; варианты 1 (B2B), 2 (линейка 65+) и 5 («оставить как есть») отклонены на горизонт квартала",
        "context": "Один приоритет на квартал (рамка ЧЕКПОИНТА 1); отказ от двух направлений на весь горизонт; затрагивает продукт, монетизацию и коммуникации; обратимо только в следующем квартале.",
        "expected": "high",
    },
    {
        "id": "ho-2",
        "decision": "Инициатива И1 «Измеряемость» — P0-блокер: когортная выгрузка и единое определение метрики продления как условие пилотов",
        "context": "Техническая инициатива контура данные+аналитика; обратима; внутри одного контура.",
        "expected": "low",
    },
    {
        "id": "ho-3",
        "decision": "Метрика продления не подменена: определение метрики вынесено в «что просим утвердить» как решение совета, baseline назван пробелом",
        "context": "Аналоги дали три несовместимых объекта метрики (ev-002, ev-004, ev-006); решение — о том, КТО определяет метрику, а не какая она; обратимо; контур аналитики.",
        "expected": "low",
    },
    {
        "id": "ho-4",
        "decision": "Экономика как смена адресата spend'а: часть performance-привлечения → механики продления, часть широких коммуникаций → точечные по окну продления и премиум-тест; порог бюджетной нейтральности предрегистрирован метрикой М7, величина доли — за советом",
        "context": "Перераспределение бюджета около нуля между привлечением и продлением; затрагивает маркетинг (привлечение), продукт (механики продления) и коммуникации; обратимо ежеквартально.",
        "expected": "high",
    },
    {
        "id": "ho-5",
        "decision": "Механика напоминаний (И4) ограничена капами по основанию ev-006",
        "context": "Операционное ограничение частоты внутри одной инициативы; обратимо; один контур.",
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

Ниже 5 решений из прогона агента по held-out задаче. Для КАЖДОГО дай
класс (high|low), уверенность (0..1) и причину (до 15 слов). Сверься
с правилом, а не с интуицией о важности.

Формат ответа (строго, только JSON-массив):
[{{"id": "ho-1", "class": "high", "confidence": 0.9, "reason": "..."}}, ...]

=== РЕШЕНИЯ ===
{cases}
=== КОНЕЦ ==="""


def render_cases() -> str:
    parts = []
    for case in CASES:
        parts.append(
            f"- id: {case['id']}\n"
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
    parser = argparse.ArgumentParser(
        prog="trigger_audit_heldout.py",
        description="Аудит триггера council на held-out артефактах (§27.1).",
    )
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
    out_dir = Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / f"t13-trigger-heldout-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_label.set_run_label("О4: t13-trigger-heldout")
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
    verdict = ("триггер требует второго прохода (пропуски > 0)" if misses > 0
               else "триггер адекватен (proxy, n=5)")
    summary = {
        "prompt_sha256_16": prompt_hash,
        "cases": len(CASES),
        "answered": answered,
        "high": high,
        "low": low,
        "misses_low_instead_of_high": misses,
        "false_alarm_high_instead_of_low": false_alarm,
        "avg_confidence": round(avg_conf, 2),
        "verdict": verdict,
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = [
        "# Аудит триггера council на held-out артефактах (TASK-hermes-13 §27.1)",
        "",
        "Кейсы — реальные решения прогона held-out-growth-segment из артефактов",
        "(STATE.md — решения шага 4; options.md — выбор ЧЕКПОИНТА 3).",
        "Правило, модель и формат — дословно §19.3; ожидания — по правилу",
        "council-design §3, расставлены ДО прогона (self-assessed proxy, R3).",
        "",
        f"Промпт sha256 (16): {prompt_hash}",
        f"Кейсов: {len(CASES)}, ответов: {answered}, high: {high}, low: {low}",
        f"Пропуски (low вместо high): {misses}; ложные (high вместо low): {false_alarm}",
        f"Средняя уверенность: {avg_conf:.2f}",
        f"Вердикт: {verdict}",
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
