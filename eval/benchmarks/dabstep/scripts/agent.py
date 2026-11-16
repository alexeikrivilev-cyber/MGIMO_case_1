#!/usr/bin/env python3
"""agent.py — ReAct-агент для стенда DABstep на модели step-5 (О4).

Протокол: модель в цикле либо исполняет python-код (блок ```python),
либо выдаёт финальный ответ («FINAL: …»). Код исполняется локально
(subprocess python3, cwd — каталог данных), stdout возвращается модели.
Стек — только stdlib (контейнер без pandas).

Переменные окружения:
    STEPFUN_API_KEY — обязателен (из env, никогда в репозиторий);
    DABSTEP_MODEL   — необязательно (default step-5-preview);
    DABSTEP_BASE    — необязательно (default https://api.stepfun.ai/step_plan/v1);
    DABSTEP_MAX_STEPS — необязательно (default 12).

Контракт CLI:
    python3 agent.py --data DIR --question TEXT --guidelines TEXT
        [--manual FILE] [--max-steps N] [--out JSON]

Коды возврата: 0 — агент завершился (ответ может быть пустым);
2 — нет ключа/данных; 4 — ошибка API на последнем шаге.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_API_FAIL = 4

DEFAULT_BASE = "https://api.stepfun.ai/step_plan/v1"
# У API StepFun имя модели — без префикса провайдера («stepfun/» — это
# квалифицированное имя уровня opencode; прямой вызов /chat/completions
# принимает только «step-5-preview» — проверено 2026-11-16, 404 иначе).
DEFAULT_MODEL = "step-5-preview"

SYSTEM = """Ты — аналитик данных, работающий в терминале над файлами в текущем
каталоге (там лежат CSV/JSON и документация: payments.csv,
payments-readme.md, fees.json, merchant_data.json,
merchant_category_codes.csv, acquirer_countries.csv, manual.md).

Правила работы:
0. СНАЧАЛА проверь применимость (отдельный шаг, без расчётов): применим
   ли вопрос к ЭТИМ данным — есть ли нужные сущности, поля, период,
   пороги? Если вопрос к данным неприменим (сущности нет, периода нет,
   порог не определён) — сразу «FINAL: Not Applicable». Не считай
   «понаслышке»: неприменимость должна быть видна из схемы данных или
   документации.
1. На каждом шаге отвечай ЛИБО одним блоком python-кода (```python ... ```),
   который будет исполнен (его stdout вернётся тебе), ЛИБО строкой
   «FINAL: <ответ>», если ответ известен.
2. Код исполняется с cwd = каталог данных: читай файлы относительными
   путями. Перед агрегациями смотри схему (заголовки CSV, ключи JSON).
3. Не выдумывай числа: каждое значение — из вычисления. Если вопрос не
   применим к данным — отвечай «Not Applicable».
4. Ответ FINAL должен точно соответствовать формату из guidelines
   (число, имя, список и т.п.), без пояснений.
5. Не более {max_steps} шагов. Если шаги исчерпаны, а ответ ещё не
   готов — тебе зададут дополнительный вопрос и попросят дать ЛУЧШИЙ
   ответ на основе уже полученных результатов: тогда верни
   «FINAL: <лучший ответ>» БЕЗ нового кода (непроверенную оценку
   помечай внутри ответа — формату guidelines это не мешает).
"""


# Мандат дополнительного вызова при исчерпании шагов (TASK-hermes-7 §3,
# failure mode task 2697: «12-шаговый лимит исчерпан, ответ не получен»).
# Код НЕ исполняется — ответ строится только из уже собранного контекста.
BEST_EFFORT_MANDATE = (
    "Шаги исчерпаны. Новый код исполняться НЕ будет. Дай "
    "ЛУЧШИЙ возможный ответ строго формата guidelines на "
    "основе уже полученных результатов выше — строкой "
    "«FINAL: <ответ>». Если уверенности нет — укажи лучшую "
    "оценку с пометкой внутри ответа."
)


def api_chat(messages: list[dict], key: str, base: str, model: str) -> dict:
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_reply(message: dict) -> str:
    content = (message.get("content") or "").strip()
    if content:
        return content
    # Некоторые reasoning-модели отдают текст в reasoning_content
    return (message.get("reasoning_content") or "").strip()


def extract_code(reply: str) -> str | None:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", reply, re.DOTALL)
    if match:
        return match.group(1)
    return None


def extract_final(reply: str) -> str | None:
    match = re.search(r"FINAL:\s*(.+)", reply)
    if match:
        return match.group(1).strip()
    return None


def run_code(code: str, data_dir: Path, timeout: int = 90) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=data_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return out[:4000]


def build_initial_prompt(question: str, guidelines: str, data_dir: Path, manual: str | None) -> str:
    lines = [
        f"ВОПРОС: {question}",
        f"ФОРМАТ ОТВЕТА (guidelines): {guidelines}",
        "",
        "Файлы данных в текущем каталоге:",
    ]
    for f in sorted(data_dir.iterdir()):
        if f.is_file():
            lines.append(f"- {f.name} ({f.stat().st_size} Б)")
    if manual:
        lines.append("")
        lines.append("=== ДОКУМЕНТАЦИЯ (manual.md) ===")
        lines.append(manual)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent.py")
    parser.add_argument("--data", required=True, help="каталог с данными DABstep")
    parser.add_argument("--question", required=True)
    parser.add_argument("--guidelines", required=True)
    parser.add_argument("--manual", default=None, help="файл manual.md (для hard)")
    parser.add_argument("--max-steps", type=int, default=int(os.environ.get("DABSTEP_MAX_STEPS", "12")))
    parser.add_argument("--out", default=None, help="куда записать JSON-трассу")
    args = parser.parse_args(argv)

    key = os.environ.get("STEPFUN_API_KEY")
    if not key:
        print("STEPFUN_API_KEY не в окружении", file=sys.stderr)
        return EXIT_USAGE
    data_dir = Path(args.data)
    if not data_dir.is_dir():
        print(f"каталог данных не найден: {data_dir}", file=sys.stderr)
        return EXIT_USAGE
    base = os.environ.get("DABSTEP_BASE", DEFAULT_BASE)
    model = os.environ.get("DABSTEP_MODEL", DEFAULT_MODEL)

    manual_text = None
    if args.manual and Path(args.manual).is_file():
        manual_text = Path(args.manual).read_text(encoding="utf-8", errors="replace")

    messages = [
        {"role": "system", "content": SYSTEM.format(max_steps=args.max_steps)},
        {"role": "user", "content": build_initial_prompt(args.question, args.guidelines, data_dir, manual_text)},
    ]
    trace: list[dict] = []
    usage_total = {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0}
    final_answer = ""
    started = time.time()

    for step in range(1, args.max_steps + 1):
        try:
            response = api_chat(messages, key, base, model)
        except Exception as exc:  # noqa: BLE001 — трасса важнее причины
            trace.append({"step": step, "error": str(exc)[:300]})
            print(f"API error на шаге {step}: {exc}", file=sys.stderr)
            break
        usage = response.get("usage") or {}
        usage_total["prompt_tokens"] += usage.get("prompt_tokens", 0)
        usage_total["cached_tokens"] += (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        usage_total["completion_tokens"] += usage.get("completion_tokens", 0)
        message = response["choices"][0]["message"]
        reply = extract_reply(message)
        messages.append({"role": "assistant", "content": reply})

        final = extract_final(reply)
        if final is not None:
            final_answer = final
            trace.append({"step": step, "final": final})
            break
        code = extract_code(reply)
        if code is None:
            # Нет ни кода, ни FINAL — просим соблюдать протокол
            messages.append({
                "role": "user",
                "content": "Отвечай либо блоком ```python ... ```, либо строкой FINAL: <ответ>.",
            })
            trace.append({"step": step, "protocol_nudge": True})
            continue
        try:
            output = run_code(code, data_dir)
        except subprocess.TimeoutExpired:
            output = "TIMEOUT: код исполнялся дольше 90с"
        trace.append({"step": step, "code": code, "output": output[:2000]})
        messages.append({"role": "user", "content": f"Результат исполнения:\n{output}"})

    best_effort = False
    extra_calls = 0
    if not final_answer and trace:
        # Шаги исчерпаны без FINAL — один дополнительный вызов БЕЗ
        # исполнения кода: лучший ответ по уже собранным результатам
        # (TASK-hermes-7 §3, failure mode task 2697: «12-шаговый лимит
        # исчерпан, ответ не получен»). Деградация честная: в трассе
        # помечено best_effort, в результатах — флаг.
        messages.append({
            "role": "user",
            "content": BEST_EFFORT_MANDATE,
        })
        try:
            response = api_chat(messages, key, base, model)
            usage = response.get("usage") or {}
            usage_total["prompt_tokens"] += usage.get("prompt_tokens", 0)
            usage_total["cached_tokens"] += (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            usage_total["completion_tokens"] += usage.get("completion_tokens", 0)
            reply = extract_reply(response["choices"][0]["message"])
            final = extract_final(reply)
            entry = {"step": len(trace) + 1, "best_effort": True, "reply": reply[:2000]}
            if final is not None:
                final_answer = final
                best_effort = True
                entry["final"] = final
            trace.append(entry)
            extra_calls += 1
        except Exception as exc:  # noqa: BLE001 — трасса важнее причины
            trace.append({"step": len(trace) + 1, "best_effort": True, "error": str(exc)[:300]})
            extra_calls += 1

    result = {
        "question": args.question,
        "guidelines": args.guidelines,
        "answer": final_answer,
        "best_effort": best_effort,
        "steps": len(trace),
        "steps_budget": len(trace) - extra_calls,
        "usage": usage_total,
        "seconds": round(time.time() - started, 1),
        "trace": trace,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"answer": final_answer, "best_effort": best_effort, "steps": len(trace), "usage": usage_total}, ensure_ascii=False))
    return EXIT_OK if final_answer else EXIT_API_FAIL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
