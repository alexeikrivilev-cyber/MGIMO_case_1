#!/usr/bin/env python3
"""trigger_audit_heldout2.py — расширение аудита триггера council на held-out (TASK-hermes-16 §30.3).

Предрегистрация: measurements.md §30.3 (гипотеза H-T2) ДО прогона.
§27.1: 5 кейсов, 5/5, 0 пропусков (n=5). Здесь — ВТОРОЙ набор из 5
РЕАЛЬНЫХ решений held-out-growth-segment, не пересекающихся с
первыми пятью (те — выбор ЧЕКПОИНТА 3, И1, определение метрики,
перераспределение бюджета, капы напоминаний). Правило, модель,
формат ответа и шаблон промпта — дословно из
`eval/trigger_audit_heldout.py` (импортируем, не копируем: сломанная
копия = второй «правде»). Меняется только блок кейсов; ожидания —
по правилу council-design §3, расставлены ДО прогона.

Контракт CLI:
    python3 eval/trigger_audit_heldout2.py [--out DIR] [--timeout SEC]

Коды возврата: 0 — аудит завершён; 4 — прогон упал.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

import run_label  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = _load("trigger_audit_heldout", REPO_ROOT / "eval" / "trigger_audit_heldout.py")

EXIT_OK = 0
EXIT_RUN_FAILED = 4
MODEL = base.MODEL

# Второй набор: решения шага 4 held-out (инициативы, дизайн пилотов,
# коммуникационный формат). Ожидание — по правилу council-design §3
# (необратимо / кросс-функционально / выше порога $), ДО прогона.
CASES = [
    {
        "id": "ho-6",
        "decision": "И2 «Второй месяц»: пилот активации на когорте подключения с контрольной группой (онбординг, вехи активации, первые подборки)",
        "context": "Пилот затрагивает продукт, контент и CRM (три контура); контрольная группа по когорте; обратимо отключением программы.",
        "expected": "high",
    },
    {
        "id": "ho-7",
        "decision": "И3 «Второй месяц»: A/B перевода на автоплатём и отмены в 2 шага внутри ставки",
        "context": "A/B на когорте подключения; затрагивает платёжный контур и продукт; обратимо.",
        "expected": "high",
    },
    {
        "id": "ho-8",
        "decision": "И5 «Премиум на том, что есть»: подчинённый тест с жёстким holdout и капом ресурса, чтобы не стать вторым направлением",
        "context": "Затрагивает продукт, тарифы и коммуникации; обратимо; кап ресурса предрегистрирован.",
        "expected": "high",
    },
    {
        "id": "ho-9",
        "decision": "Коммуникационная стратегия: получатель — совет директоров, формат «на утверждение», структура «решение вперёд, доказательства за ним»",
        "context": "Формат и структура документа для совета; один контур (коммуникации); обратимо переоформлением.",
        "expected": "low",
    },
    {
        "id": "ho-10",
        "decision": "Правило «рано судить»: эффект пилотов не судится раньше накопления двух полных когорт после старта измерений",
        "context": "Правило интерпретации замера; контур аналитики; обратимо пересмотром правила при новых данных.",
        "expected": "low",
    },
]


def render_cases() -> str:
    parts = []
    for case in CASES:
        parts.append(
            f"- id: {case['id']}\n"
            f"  решение: {case['decision']}\n"
            f"  контекст: {case['context']}")
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="trigger_audit_heldout2.py",
        description="Аудит триггера council на held-out: второй набор кейсов (§30.3, H-T2).")
    parser.add_argument("--out", default=None)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)

    import os

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении — аудит невозможен", file=sys.stderr)
        return EXIT_RUN_FAILED

    prompt = base.AUDIT_PROMPT.format(cases=render_cases())
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = (Path(args.out) if args.out
               else REPO_ROOT / "eval" / "runs" / f"t16-trigger-heldout2-{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    run_label.set_run_label("О4: t16-trigger-heldout2")
    try:
        proc = subprocess.run(
            ["opencode", "run", "--model", MODEL, prompt],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print(f"аудит превысил таймаут {args.timeout}s", file=sys.stderr)
        return EXIT_RUN_FAILED
    finally:
        run_label.clear_run_label()

    (out_dir / "audit.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "audit.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / "audit.end").write_text(
        datetime.now(timezone.utc).isoformat() + f" exit={proc.returncode}\n",
        encoding="utf-8")
    if proc.returncode != 0:
        print("прогон упал, детали в audit.err", file=sys.stderr)
        return EXIT_RUN_FAILED

    parsed = base.parse_audit(proc.stdout)
    if parsed is None:
        print("ответ не разобран (нет JSON-массива)", file=sys.stderr)
        return EXIT_RUN_FAILED

    expected = {c["id"]: c["expected"] for c in CASES}
    got = {item["id"]: item for item in parsed}
    misses = [cid for cid, exp in expected.items()
              if got.get(cid, {}).get("class") != exp]
    false_alarms = [cid for cid, exp in expected.items()
                    if exp == "low" and got.get(cid, {}).get("class") == "high"]
    skipped = [cid for cid, exp in expected.items()
               if exp == "high" and got.get(cid, {}).get("class") == "low"]
    conf = [float(item.get("confidence", 0)) for item in parsed
            if isinstance(item.get("confidence"), (int, float))]
    high = sum(1 for item in parsed if item.get("class") == "high")

    lines = [
        "# Аудит триггера council на held-out — второй набор (TASK-hermes-16 §30.3, H-T2)",
        "",
        "Предрегистрация — measurements.md §30.3 ДО прогона. Кейсы — реальные",
        "решения шага 4 held-out-growth-segment, не пересекающиеся с §27.1",
        "(ho-1…ho-5). Правило, модель, формат и шаблон промпта — дословно из",
        "`eval/trigger_audit_heldout.py` (импорт); ожидания — по правилу",
        "council-design §3, расставлены ДО прогона (self-assessed proxy, R3).",
        "",
        f"Промпт sha256 (16): {prompt_hash} (§27.1: 33cd2b429c19f4a6 — шаблон",
        "тот же, блок кейсов другой)",
        f"Кейсов: {len(CASES)}, ответов: {len(parsed)}, high: {high}, low: {len(parsed) - high}",
        f"Пропуски (low вместо high): {len(skipped)}; ложные (high вместо low): {len(false_alarms)}",
        f"Средняя уверенность: {sum(conf) / len(conf):.2f}" if conf else "уверенность не распознана",
        "",
        "| id | класс агента | ожидание | уверенность | причина |",
        "|---|---|---|---|---|",
    ]
    for case in CASES:
        item = got.get(case["id"], {})
        lines.append(
            f"| {case['id']} | {item.get('class', '—')} | {case['expected']} "
            f"| {item.get('confidence', '—')} | {str(item.get('reason', ''))[:70]} |")
    verdict = ("H-T2 подтверждена: правило на втором наборе согласовано"
               if not misses else
               f"H-T2 НЕ подтверждена: расхождения {misses}")
    lines += ["", f"Вердикт: {verdict} (proxy, n={len(CASES)})", ""]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps({"prompt_hash": prompt_hash, "cases": CASES,
                    "parsed": parsed, "misses": misses,
                    "false_alarms": false_alarms, "skipped": skipped,
                    "verdict": verdict}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"артефакт: {out_dir / 'report.md'}; вердикт: {verdict}")
    return EXIT_OK if not misses else EXIT_RUN_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
