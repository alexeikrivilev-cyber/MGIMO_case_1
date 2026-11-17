#!/usr/bin/env python3
"""run_ablation.py — абляция слоёв «Стратега» L0–L3 (TASK-hermes-10 §23.1).

Вопрос (прямое требование ТЗ): разрыв «агент vs обычный чат»
измерен, но не ясно, какой слой его даёт. Прогон строит ВЛОЖЕННЫЕ
стеки контекста на одном замороженном брифе и генерирует артефакт
шага 3 (options.md) для каждого слоя:

  L0 — только бриф + инструкция «ответь как обычный чат»;
  L1 — + AGENTS.md (постоянные инструкции);
  L2 — + библиотека навыков (каталог + навык шага 3);
  L3 — + скрипты-проверки как гейт (check_options/check_sources →
       ревизионная сессия по нарушениям, до 2 раундов).

L4 (полный агент «как в продукте») НЕ генерируется этим раннером: это
существующие артефакты продукта (`project/options.md` и held-out
`artifacts/options.md`), их оценивает `eval/score_ablation.py`.

Почему генерация — ПРЯМОЙ вызов API, а не `opencode run` (критично
для валидности, §23.0/§23.1):
1. `.opencode/opencode.json` корня репозитория несёт
   `instructions: [docs/agents-md-staged.md]` — in-repo сессия
   физически не может быть L0/L1 (инструкции внедряются в каждую
   сессию; проверено пробой).
2. Вне репозитория модель выходит за пределы стека по абсолютному
   пути: на первых прогонах абляции L0 читал STATE.md/LOG.md/
   council-design.md, а черновик L3 — проектный `project/options.md`
   (выход L4!). Изоляция через конфиг opencode НЕНАДЁЖНА в этом
   окружении: три пробы дали три разных набора инструментов
   (локальный opencode.json перебивается пользовательским глобальным
   `"*": "allow"`; часть сессий уходила на persistent server :4096 с
   конфигом репозитория). Подробности — в DEFECT.md отвергнутых
   прогонов `eval/runs/t10-ablation/*-contaminated*`.
3. Прямой вызов `/chat/completions` даёт детерминированную среду:
   ровно один user-месседж со стеком, БЕЗ инструментов, БЕЗ системного
   промпта opencode, БЕЗ внедрения инструкций. Ответ зависит ТОЛЬКО
   от промпта — это и делает абляцию измерением стека контекста.
   Прецедент прямых вызовов в стенде — DABstep
   (`eval/benchmarks/dabstep/scripts/agent.py`).

Стоимость: токены из `usage` ответа API; кэша префикса нет, поэтому
$/run здесь — ВЕРХНЯЯ оценка относительно opencode-сессий с кэшем
(отмечено в отчёте). Строки в COST.md дописываются вручную (прямой
вызов, как у DABstep).

Контракт CLI:
    python3 eval/run_ablation.py --task demo-retention|heldout-growth-segment
        [--arms L0,L1,L2,L3] [--out DIR] [--timeout SEC] [--dry-run]

Коды возврата: 0 — все прогоны зелёные; 1 — ошибка использования;
3 — STEPFUN_API_KEY не в окружении; 4 — хотя бы один прогон упал.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

# Прямой вызов API: база и имя модели — как у стенда DABstep (проверено:
# /chat/completions принимает «step-5-preview» без префикса провайдера).
API_BASE = "https://api.stepfun.ai/step_plan/v1"
API_MODEL = "step-5-preview"
TEMPERATURE = 0.0
REASONING_EFFORT = "high"  # как в provider-конфиге продукта

TASKS = {
    "demo-retention": "project/council/run-2026-11-16-01/frozen-brief.md",
    "heldout-growth-segment": "eval/tasks/heldout-growth-segment/artifacts/brief.md",
}

# Состав стека навыков (progressive disclosure, приближение —
# предрегистрация §23.1): каталог + навык шага 3. Фиксирован ДО прогонов.
SKILL_INDEX = "knowledge/index.md"
SKILL_STEP3 = "knowledge/skills/options/SKILL.md"

# Проверки слоя L3 (операционализация «+скрипты и хуки», §23.1).
CHECK_SCRIPTS = ("scripts/check_options.py", "scripts/check_sources.py")

MAX_REVISION_ROUNDS = 2

CHAT_INSTRUCTION = """
Ответь на задачу из брифа ОДНИМ сообщением, как обычный чат-ассистент:
разберись, что происходит, и предложи стратегию — продуктовую и
коммуникационную — с метриками проверки. Без уточняющих вопросов,
без промежуточных шагов, без обещаний данных, которых у тебя нет.
Файлы не создавай и не изменяй."""

STEP3_MANDATE = """ЗАДАНИЕ: выполни шаг 3 (ВАРИАНТЫ) рабочего процесса из инструкций.

Верни готовый markdown-артефакт options.md ОТВЕТОМ В ЧАТ. Файлы не
создавай и не изменяй."""


def read_repo_file(rel_path: str) -> str:
    path = REPO_ROOT / rel_path
    if not path.is_file():
        raise FileNotFoundError(f"файл стека не найден: {rel_path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def block(header: str, body: str) -> str:
    return f"=== {header} ===\n{body}\n=== КОНЕЦ: {header.split(' (')[0]} ===\n"


def build_prompt_L0(brief: str) -> str:
    """Слой L0: бриф + инструкция обычного чата. Ничего больше."""
    return (
        "Ниже — бриф задачи (замороженный, единственный источник).\n\n"
        + block("ЗАМОРОЖЕННЫЙ БРИФ", brief)
        + CHAT_INSTRUCTION
        + "\n"
    )


def build_prompt_L1(brief: str, agents_md: str) -> str:
    """Слой L1: бриф + AGENTS.md дословно + мандат шага 3.

    Навыки и скрипты объявлены НЕдоступными — это операционализация
    границы слоя (промпт-уровень изоляции, названа в §23.1).
    """
    return (
        "Ты выполняешь задачу с помощью постоянных инструкций агента "
        "«Стратег» (ниже дословно) и брифа задачи.\n\n"
        + block("ПОСТОЯННЫЕ ИНСТРУКЦИИ (AGENTS.md)", agents_md)
        + "\n"
        + STEP3_MANDATE
        + "\n\nВ этом режиме библиотека навыков (knowledge/) и скрипты "
        "проверок НЕдоступны — работай только по инструкциям выше и "
        "брифу.\n\n"
        + block("ЗАМОРОЖЕННЫЙ БРИФ", brief)
    )


def build_prompt_L2(brief: str, agents_md: str) -> str:
    """Слой L2: L1 + каталог навыков + навык шага 3 (инлайном)."""
    return (
        "Ты выполняешь задачу с помощью постоянных инструкций агента "
        "«Стратег» (ниже дословно), библиотеки навыков и брифа задачи.\n\n"
        + block("ПОСТОЯННЫЕ ИНСТРУКЦИИ (AGENTS.md)", agents_md)
        + "\n"
        + STEP3_MANDATE
        + "\n\nВ этом режиме доступна библиотека навыков: каталог и "
        "навык шага 3 даны ниже (progressive disclosure — применяй "
        "только нужное). Скрипты проверок недоступны. Файлы не создавай "
        "и не изменяй.\n\n"
        + block("КАТАЛОГ НАВЫКОВ (knowledge/index.md)", read_repo_file(SKILL_INDEX))
        + block(
            "НАВЫК ШАГА 3 «ВАРИАНТЫ» (knowledge/skills/options/SKILL.md)",
            read_repo_file(SKILL_STEP3),
        )
        + "\n"
        + block("ЗАМОРОЖЕННЫЙ БРИФ", brief)
    )


def build_revision_prompt(draft: str, violations: str) -> str:
    """Ревизионная сессия слоя L3: черновик + нарушения проверок."""
    return (
        "Ты — тот же агент «Стратег», дорабатываешь свой черновик шага 3 "
        "(ВАРИАНТЫ) по нарушениям, найденным скриптами-проверками "
        "(check_options.py, check_sources.py).\n\n"
        "Правила доработки:\n"
        "- Устрани каждое нарушение по существу; не ослабляй возражения "
        "и не увеличивай число вариантов ради разнообразия.\n"
        "- Сохрани маркеры [факт]/[гипотеза]/[прогноз]/[допущение]; "
        "каждое существенное число — с основанием (ev-N / URL) в той же "
        "строке.\n"
        "- Не удаляй секции вариантов и «оставить как есть».\n\n"
        + block("ЧЕРНОВИК", draft)
        + block("НАРУШЕНИЯ ПРОВЕРОК", violations)
        + "Верни доработанный markdown-артефакт options.md ОТВЕТОМ В ЧАТ. "
        "Файлы не пиши.\n"
    )


class SessionResult:
    """Результат одной генерации: ответ, токены, стоимость."""

    def __init__(self) -> None:
        self.text = ""
        self.tokens = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0}
        self.error: str | None = None

    @property
    def answer(self) -> str:
        return self.text.strip()

    def cost_usd(self) -> float:
        """Формула COST.md: input×1.00 + cache.read×0.10 + output×2.70 за 1M.

        У прямого вызова кэша префикса нет (cache_read = 0), поэтому
        это ВЕРХНЯЯ оценка относительно opencode-сессий с кэшем.
        """
        return (
            self.tokens["input"] * 1.0
            + self.tokens["cache_read"] * 0.1
            + self.tokens["output"] * 2.7
        ) / 1_000_000

    def to_meta(self) -> dict:
        return {
            "tokens": dict(self.tokens),
            "cost_usd": round(self.cost_usd(), 6),
            "answer_chars": len(self.answer),
            "error": self.error,
        }


def build_api_body(prompt: str) -> dict:
    """Тело запроса: один user-месседж, БЕЗ инструментов и системного
    промпта — среда генерации равна промпту (обоснование — в докстринге
    модуля)."""
    return {
        "model": API_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE,
        "reasoning_effort": REASONING_EFFORT,
    }


def api_generate(prompt: str, key: str, timeout: int) -> SessionResult:
    """Прямой вызов /chat/completions: ответ + usage.

    Пустой ответ — провал прогона (урок TASK-hermes-5/9: «успех» без
    содержания не является успехом).
    """
    result = SessionResult()
    request = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps(build_api_body(prompt)).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        result.error = f"API: {exc}"
        return result
    choices = payload.get("choices") or []
    message = choices[0].get("message") if choices else None
    if not message:
        result.error = "API: пустой choices"
        return result
    result.text = (message.get("content") or "").strip()
    usage = payload.get("usage") or {}
    result.tokens["input"] = int(usage.get("prompt_tokens") or 0)
    result.tokens["output"] = int(usage.get("completion_tokens") or 0)
    details = usage.get("completion_tokens_details") or {}
    result.tokens["reasoning"] = int(details.get("reasoning_tokens") or 0)
    if not result.text:
        result.error = "API: пустой content при успешном ответе"
    return result


def run_checks(artifact: Path) -> tuple[bool, str]:
    """Проверки слоя L3: check_options.py + check_sources.py по артефакту.

    Возвращает (все_зелёные, вывод). Скрипты читают только файл
    артефакта, ничего не пишут.
    """
    outputs: list[str] = []
    all_ok = True
    for script in CHECK_SCRIPTS:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / script), str(artifact)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        outputs.append(f"$ {script} → exit {proc.returncode}\n{proc.stdout.strip()}")
        if proc.returncode != 0:
            all_ok = False
    return all_ok, "\n\n".join(outputs)


def integrity_report(before: str, after: str) -> dict:
    """Целостность ревизии L3: секции вариантов и «оставить как есть»."""
    def variants(text: str) -> int:
        return len(re.findall(r"^#{2,3}\s+вариант", text, re.IGNORECASE | re.MULTILINE))

    def has_status_quo(text: str) -> bool:
        return bool(re.search(r"оставить как есть", text, re.IGNORECASE))

    size_ratio = len(after) / len(before) if before else 0.0
    return {
        "variants_before": variants(before),
        "variants_after": variants(after),
        "status_quo_before": has_status_quo(before),
        "status_quo_after": has_status_quo(after),
        "size_ratio": round(size_ratio, 3),
        "integrity_ok": variants(after) >= variants(before)
        and has_status_quo(after) == has_status_quo(before)
        and size_ratio >= 0.6,
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_ablation.py",
        description="Абляция слоёв L0–L3 на одном замороженном брифе (TASK-hermes-10 §23.1).",
    )
    parser.add_argument("--task", required=True, choices=sorted(TASKS))
    parser.add_argument("--arms", default="L0,L1,L2,L3", help="список слоёв через запятую")
    parser.add_argument("--out", default=None)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ("L0", "L1", "L2", "L3")]
    if unknown:
        print(f"неизвестные слои: {unknown}; доступно: L0,L1,L2,L3", file=sys.stderr)
        return EXIT_USAGE

    brief = read_repo_file(TASKS[args.task])
    agents_md = read_repo_file("AGENTS.md")
    prompts = {
        "L0": build_prompt_L0(brief),
        "L1": build_prompt_L1(brief, agents_md),
        "L2": build_prompt_L2(brief, agents_md),
    }
    prompts["L3"] = prompts["L2"]  # черновик L3 = L2; отличие — гейт проверок

    out_dir = Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / "t10-ablation" / args.task
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for arm in arms:
            print(f"[dry-run] {arm}: промпт {len(prompts[arm])} символов, sha256 {sha256_text(prompts[arm])}")
        return EXIT_OK

    key = os.environ.get("STEPFUN_API_KEY")
    if not key:
        print("STEPFUN_API_KEY не в окружении — прогон невозможен", file=sys.stderr)
        return EXIT_NO_KEY

    manifest = [
        f"# Абляция слоёв — задача {args.task} (TASK-hermes-10 §23.1)",
        "",
        f"Старт (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Бриф: `{TASKS[args.task]}` (sha256 `{sha256_text(brief)}…`)",
        f"Модель: {API_MODEL}, прямой вызов API (temperature {TEMPERATURE}, "
        f"reasoning {REASONING_EFFORT}); среда генерации = промпт (без инструментов)",
        "",
        "| Слой | Промпт (символов) | sha256 | Генерации | Итог |",
        "|---|---|---|---|---|",
    ]
    failures = 0

    for arm in arms:
        arm_dir = out_dir / arm
        arm_dir.mkdir(parents=True, exist_ok=True)
        prompt = prompts[arm]
        (arm_dir / "prompt.md").write_text(prompt, encoding="utf-8")
        sessions_meta: list[dict] = []

        # Раунд 0 (для всех слоёв) и ревизии (только L3).
        draft_res = api_generate(prompt, key, args.timeout)
        draft = draft_res.answer
        (arm_dir / "draft.out").write_text(draft, encoding="utf-8")
        sessions_meta.append({"name": "draft", **draft_res.to_meta()})
        if draft_res.error or not draft:
            failures += 1
            manifest.append(
                f"| {arm} | {len(prompt)} | {sha256_text(prompt)} | 1 "
                f"| FAIL {draft_res.error or 'пустой ответ'} |"
            )
            write_json(arm_dir / "meta.json", {"sessions": sessions_meta})
            continue

        final = draft
        checks_log = ""
        if arm == "L3":
            rounds = 0
            while rounds < MAX_REVISION_ROUNDS:
                draft_path = arm_dir / ("draft.md" if rounds == 0 else f"round{rounds}.md")
                draft_path.write_text(final, encoding="utf-8")
                ok, output = run_checks(draft_path)
                checks_log += f"\n=== раунд {rounds} ===\n{output}\n"
                (arm_dir / "checks.md").write_text(checks_log.strip() + "\n", encoding="utf-8")
                if ok:
                    break
                rev_res = api_generate(
                    build_revision_prompt(final, output), key, args.timeout
                )
                revised = rev_res.answer
                sessions_meta.append({"name": f"revision{rounds}", **rev_res.to_meta()})
                if rev_res.error or not revised:
                    failures += 1
                    break
                report = integrity_report(final, revised)
                (arm_dir / f"integrity-round{rounds}.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                (arm_dir / f"round{rounds + 1}.md").write_text(revised, encoding="utf-8")
                final = revised
                rounds += 1

        (arm_dir / "final.md").write_text(final, encoding="utf-8")
        meta = {
            "task": args.task,
            "arm": arm,
            "model": API_MODEL,
            "api": API_BASE,
            "prompt_sha256_16": sha256_text(prompt),
            "prompt_chars": len(prompt),
            "temperature": TEMPERATURE,
            "reasoning_effort": REASONING_EFFORT,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "sessions": sessions_meta,
            "cost_usd_total": round(sum(s["cost_usd"] for s in sessions_meta), 6),
            "tokens_total": {
                field: sum(s["tokens"][field] for s in sessions_meta)
                for field in ("input", "output", "reasoning", "cache_read")
            },
        }
        write_json(arm_dir / "meta.json", meta)
        manifest.append(
            f"| {arm} | {len(prompt)} | {sha256_text(prompt)} | {len(sessions_meta)} "
            f"| OK (${meta['cost_usd_total']:.4f}, ответ {len(final)} символов) |"
        )
        print(f"arm {arm}: {len(sessions_meta)} генераций, ${meta['cost_usd_total']:.4f}, ответ {len(final)} символов")

    manifest.append("")
    manifest.append(f"Финиш (UTC): {datetime.now(timezone.utc).isoformat()}")
    manifest.append(f"Провалов: {failures}")
    (out_dir / "manifest.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"готово, провалов: {failures}, манифест: {out_dir / 'manifest.md'}")
    return EXIT_RUN_FAILED if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
