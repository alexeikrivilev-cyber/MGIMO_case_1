#!/usr/bin/env python3
"""run_skills_k3.py — генерация серии k=3 по дизайну навыков + О5 (TASK-hermes-12).

Предрегистрация: measurements.md §25.1 (П.1 — курация/lean/гибрид на шагах
2–3 демо, k=3 на руку, обе рубрики) и §25.2 (П.2 — O5-A: research на
step-3.7-flash; O5-B: шаг 3 с research.md от step-5 (P) и от flash (F)).
Предрегистрация написана ДО прогонов; серия не расширяется молча после
просмотра данных (урок §22.1).

Генерация — ПРЯМОЙ вызов API (операционное правило §24.3): in-repo сессии
opencode несут внедрённый AGENTS.md, который велит «открой навык» — это
конфундило бы определяющий признак руки lean. Среда генерации = промпт
(один user-месседж, без инструментов, temperature 0). Промпты рук —
дословно из `eval/run_ab.py`; единственная адаптация названа в §25.1:
ссылки на файлы («открой и примени …») заменены на инлайн того же
содержимого. Guard: если текст рук в run_ab.py изменится, драйвер падает
с ошибкой (молчаливой подмены промпта не происходит).

Оценивание — отдельный драйвер `eval/score_skills_k3.py`; статистика —
`eval/skills_k3_stats.py`.

Контракт CLI:
    python3 eval/run_skills_k3.py --task demo-retention
        [--groups research,options,o5a,o5b] [--k 3] [--out DIR]
        [--timeout SEC] [--dry-run]

Коды возврата: 0 — все прогоны зелёные; 1 — ошибка использования;
2 — тексты рук в run_ab.py изменились (prompt drift); 3 — ключ не в
окружении; 4 — хотя бы один прогон упал.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_ab = load_module("run_ab", REPO_ROOT / "eval" / "run_ab.py")
run_ablation = load_module("run_ablation", REPO_ROOT / "eval" / "run_ablation.py")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_PROMPT_DRIFT = 2
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

MODEL_STEP5 = run_ablation.API_MODEL          # step-5-preview
MODEL_FLASH = "step-3.7-flash"
TEMPERATURE = 0.0
REASONING_EFFORT = "high"

# Цены §1.8 (llm-pricing-agent-costs.md, пересчёт 2026-11-16 без изменений):
# input-miss / input-hit / output за 1M токенов.
PRICES = {
    MODEL_STEP5: {"input": 1.00, "cache_read": 0.10, "output": 2.70},
    MODEL_FLASH: {"input": 0.20, "cache_read": 0.04, "output": 1.15},
}

# Файлы, инлайнящиеся в промпты рук «курация»/«гибрид» (те же, что
# открывали бы руки в сессиях §18/§14.3).
SKILL_EVIDENCE = "knowledge/skills/evidence/SKILL.md"
SKILL_OPTIONS = "knowledge/skills/options/SKILL.md"
TEMPLATE_RESEARCH = "templates/research.md"

# Адаптации «открой файл» → «применяй инлайн» (дословно из run_ab.py →
# замена). Ключ — имя промпта-источника в run_ab; рука lean адаптации
# не требует (её промпт самодостаточен). Guard: источник обязан
# encontrиться РОВНО один раз — иначе тексты рук в run_ab.py изменились,
# и драйвер падает (EXIT_PROMPT_DRIFT), а не генерирует «почти тот»
# промпт.
ADAPTATIONS: dict[str, tuple[str, str]] = {
    "RESEARCH_CURATION_PROMPT": (
        "Работай строго по навыку: открой\nи примени `knowledge/skills/evidence/SKILL.md` (раздел «Шаг 2 —\nисследование»); структура выхода — по шаблону `templates/research.md`.",
        "Работай строго по навыку: навык и шаблон исследования даны ниже ИНЛАЙНОМ — применяй их дословно, как открытые файлы.",
    ),
    "RESEARCH_HYBRID_PROMPT": (
        "для механики исследования открой ОДИН навык —\n`knowledge/skills/evidence/SKILL.md`, раздел «Шаг 2 — исследование» — и\nприменяй его",
        "для механики исследования примени ОДИН навык — данный ниже инлайном (раздел «Шаг 2 — исследование») — и применяй его",
    ),
    "STEP_PROMPT": (
        "Работай строго по навыку: открой и\nпримени `knowledge/skills/options/SKILL.md`.",
        "Работай строго по навыку: навык шага 3 дан ниже ИНЛАЙНОМ — применяй его дословно, как открытый файл.",
    ),
    "HYBRID_PROMPT": (
        "для механики карточки варианта открой ОДИН навык —\n`knowledge/skills/options/SKILL.md` — и применяй его §2–3",
        "для механики карточки варианта примени ОДИН навык — данный ниже инлайном — его §2–3",
    ),
}

# Группы серии: step → рука → (базовый промпт из run_ab, что инлайнить).
# o5a — research lean на flash (O5-A); o5b-P/o5b-F — шаг 3 skill с
# research.md от step-5 (P) и от flash (F) (O5-B); рука шага 3 у обоих
# вариантов O5-B — skill (прод-дефолт council-off, §25.2).
GROUPS = ("research", "options", "o5a", "o5b-P", "o5b-F")
ARMS = ("curation", "lean", "hybrid")
DEFAULT_K = 3


def sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def read_repo_file(rel_path: str) -> str:
    path = REPO_ROOT / rel_path
    if not path.is_file():
        raise FileNotFoundError(f"файл стека не найден: {rel_path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def block(header: str, body: str) -> str:
    return f"=== {header} ===\n{body}\n=== КОНЕЦ: {header.split(' (')[0]} ===\n"


def inline_block(rel_path: str, header: str) -> str:
    return block(f"{header} ({rel_path})", read_repo_file(rel_path))


def adapt_prompt(prompt: str, source: str | None) -> str:
    """Заменяет «открой файл» на «применяй инлайн» для промпта-источника.

    source — имя константы в run_ab (None для self-contained промптов
    рук lean). Источник обязан encontrиться РОВНО один раз: 0 вхождений
    означают, что тексты рук изменились и промпт серии не соответствует
    предрегистрации — падение вместо тихой подмены.
    """
    if source is None:
        return prompt
    old, new = ADAPTATIONS[source]
    count = prompt.count(old)
    if count != 1:
        raise RuntimeError(
            f"prompt drift ({source}): адаптация нашла {count} вхождений "
            f"(ожидалось 1): {old[:60]!r} — тексты рук в run_ab.py изменились?"
        )
    return prompt.replace(old, new, 1)


def cost_usd(tokens: dict, model: str) -> float:
    """Формула COST.md §1.8 под модель (step-5 / flash цены разные)."""
    price = PRICES[model]
    return (
        tokens["input"] * price["input"]
        + tokens["cache_read"] * price["cache_read"]
        + tokens["output"] * price["output"]
    ) / 1_000_000


def generate(prompt: str, key: str, timeout: int, model: str) -> dict:
    """Один прямой вызов API: ответ + токены + $ (по цене модели).

    Пустой ответ — провал прогона (урок TASK-hermes-5/9: «успех» без
    содержания не является успехом). reasoning_effort пробрасывается
    только если модель его принимает: на отказе (HTTP 400) вызов
    повторяется без него, факт фиксируется в meta (смоук-проверено).
    """
    import urllib.error
    import urllib.request

    tokens = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0}
    result = {"text": "", "tokens": tokens, "model": model, "error": None,
              "reasoning_effort_dropped": False}

    def call(with_effort: bool) -> tuple[dict | None, str | None]:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": TEMPERATURE,
        }
        if with_effort:
            body["reasoning_effort"] = REASONING_EFFORT
        request = urllib.request.Request(
            f"{run_ablation.API_BASE}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8")), None
        except urllib.error.HTTPError as exc:
            return None, f"API: HTTP {exc.code} {exc.reason}"
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            return None, f"API: {exc}"

    payload, error = call(with_effort=True)
    if error and "400" in error:
        payload, error = call(with_effort=False)
        if not error:
            result["reasoning_effort_dropped"] = True
    if error or payload is None:
        result["error"] = error or "API: нет ответа"
        result["cost_usd"] = 0.0
        return result

    choices = payload.get("choices") or []
    message = choices[0].get("message") if choices else None
    if not message:
        result["error"] = "API: пустой choices"
        result["cost_usd"] = 0.0
        return result
    result["text"] = (message.get("content") or "").strip()
    usage = payload.get("usage") or {}
    tokens["input"] = int(usage.get("prompt_tokens") or 0)
    tokens["output"] = int(usage.get("completion_tokens") or 0)
    details = usage.get("completion_tokens_details") or {}
    tokens["reasoning"] = int(details.get("reasoning_tokens") or 0)
    if not result["text"]:
        result["error"] = "API: пустой content при успешном ответе"
    result["cost_usd"] = round(cost_usd(tokens, model), 6)
    return result


def build_step2_prompts(brief: str, evidence: str) -> dict[str, str]:
    """Промпты шага 2 (research) под руки; §25.1 — определения из run_ab."""
    base = {
        "curation": (run_ab.RESEARCH_CURATION_PROMPT.format(brief=brief, evidence=evidence), "RESEARCH_CURATION_PROMPT"),
        "lean": (run_ab.RESEARCH_LEAN_PROMPT.format(brief=brief, evidence=evidence), None),
        "hybrid": (run_ab.RESEARCH_HYBRID_PROMPT.format(brief=brief, evidence=evidence), "RESEARCH_HYBRID_PROMPT"),
    }
    prompts = {arm: adapt_prompt(p, src) for arm, (p, src) in base.items()}
    prompts["curation"] += "\n" + inline_block(SKILL_EVIDENCE, "НАВЫК EVIDENCE") + inline_block(TEMPLATE_RESEARCH, "ШАБЛОН RESEARCH.MD")
    prompts["hybrid"] += "\n" + inline_block(SKILL_EVIDENCE, "НАВЫК EVIDENCE")
    return prompts


def build_step3_prompts(brief: str) -> dict[str, str]:
    """Промпты шага 3 (options) под руки; вход — только бриф (как §14.3)."""
    base = {
        "curation": (run_ab.STEP_PROMPT.format(brief=brief), "STEP_PROMPT"),
        "lean": (run_ab.LEAN_PROMPT.format(brief=brief), None),
        "hybrid": (run_ab.HYBRID_PROMPT.format(brief=brief), "HYBRID_PROMPT"),
    }
    prompts = {arm: adapt_prompt(p, src) for arm, (p, src) in base.items()}
    prompts["curation"] += "\n" + inline_block(SKILL_OPTIONS, "НАВЫК OPTIONS")
    prompts["hybrid"] += "\n" + inline_block(SKILL_OPTIONS, "НАВЫК OPTIONS")
    return prompts


def build_o5b_prompt(brief: str, evidence: str, research: str) -> str:
    """O5-B: шаг 3 (рука skill) с входом бриф + дайджест + research.md.

    Как в продукте: шаг 3 видит research.md предыдущего шага (в §14.3
    подача была изолирована — названо). Мандат оснований не меняется:
    числа — из брифа/дайджеста, research — контекст исследования.
    """
    prompt = adapt_prompt(run_ab.STEP_PROMPT.format(brief=brief, evidence=evidence), "STEP_PROMPT")
    prompt += "\n" + inline_block(SKILL_OPTIONS, "НАВЫК OPTIONS")
    prompt += (
        "\nНиже также дан результат шага 2 (research.md) предыдущего шага — "
        "опирайся на него как на контекст исследования; числа и основания "
        "бери из брифа и дайджеста выше, не из research.md.\n"
        + block("РЕЗУЛЬТАТ ШАГА 2 (research.md)", research)
    )
    return prompt


def run_group(
    group: str,
    arm: str,
    prompt: str,
    model: str,
    out_dir: Path,
    key: str,
    timeout: int,
    k: int,
    manifest: list[str],
) -> int:
    """k независимых генераций одной руки; итог цепочки = черновик
    (руки серии — однослойные, гейта проверок нет по предрегистрации)."""
    arm_dir = out_dir / group / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    (arm_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    sessions: list[dict] = []
    failures = 0
    for idx in range(k):
        res = generate(prompt, key, timeout, model)
        suffix = "" if idx == 0 else f"-{idx}"
        (arm_dir / f"final{suffix}.md").write_text(res["text"], encoding="utf-8")
        sessions.append({"name": f"final{suffix}", **res})
        if res["error"] or not res["text"]:
            failures += 1
            manifest.append(
                f"| {group}/{arm}#{idx} | {len(prompt)} | {sha256_text(prompt)} | FAIL "
                f"{res['error'] or 'пустой ответ'} |"
            )
            print(f"{group}/{arm}#{idx}: FAIL {res['error'] or 'пустой ответ'}", file=sys.stderr)
            continue
        manifest.append(
            f"| {group}/{arm}#{idx} | {len(prompt)} | {sha256_text(prompt)} | OK "
            f"(${res['cost_usd']:.4f}, {len(res['text'])} символов) |"
        )
        print(f"{group}/{arm}#{idx}: {len(res['text'])} символов, ${res['cost_usd']:.4f}")
    meta = {
        "group": group,
        "arm": arm,
        "model": model,
        "k": k,
        "prompt_sha256_16": sha256_text(prompt),
        "prompt_chars": len(prompt),
        "temperature": TEMPERATURE,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "sessions": sessions,
        "cost_usd_total": round(sum(s["cost_usd"] for s in sessions), 6),
        "tokens_total": {
            field: sum(s["tokens"][field] for s in sessions)
            for field in ("input", "output", "reasoning", "cache_read")
        },
    }
    (arm_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_skills_k3.py",
        description="Серия k=3 по дизайну навыков + О5: генерация (TASK-hermes-12 §25.1/§25.2).",
    )
    parser.add_argument("--task", default="demo-retention", choices=sorted(run_ab.TASKS))
    parser.add_argument("--groups", default=",".join(GROUPS), help="группы через запятую")
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--out", default=None)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    unknown = [g for g in groups if g not in GROUPS]
    if unknown:
        print(f"неизвестные группы: {unknown}; доступно: {list(GROUPS)}", file=sys.stderr)
        return EXIT_USAGE
    if args.k < 1:
        print("--k должен быть ≥1", file=sys.stderr)
        return EXIT_USAGE

    task = run_ab.TASKS[args.task]
    brief = read_repo_file(task["brief"])
    evidence = run_ab.build_evidence_bundle(task)

    try:
        step2 = build_step2_prompts(brief, evidence)
        step3 = build_step3_prompts(brief)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_PROMPT_DRIFT

    # План группы → [(рука, промпт, модель)].
    plan: dict[str, list[tuple[str, str, str]]] = {}
    if "research" in groups:
        plan["research"] = [(arm, step2[arm], MODEL_STEP5) for arm in ARMS]
    if "options" in groups:
        plan["options"] = [(arm, step3[arm], MODEL_STEP5) for arm in ARMS]
    if "o5a" in groups:
        plan["o5a"] = [("lean", step2["lean"], MODEL_FLASH)]
    for group in ("o5b-P", "o5b-F"):
        if group in groups:
            # Промпты O5-B зависят от research-цепочек (своих у группы):
            # собираются в generate-фазе ниже.
            plan[group] = []

    out_dir = Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / "t12-skills"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for group, rows in plan.items():
            for arm, prompt, model in rows:
                print(f"[dry-run] {group}/{arm}: модель {model}, промпт {len(prompt)} символов, sha256 {sha256_text(prompt)}")
        for group in ("o5b-P", "o5b-F"):
            if group in groups:
                src = out_dir / ("research" if group == "o5b-P" else "o5a") / "lean"
                files = [src / ("final.md" if i == 0 else f"final-{i}.md") for i in range(args.k)]
                missing = [f.name for f in files if not f.is_file()]
                print(f"[dry-run] {group}/skill: research-источник {src} (k={args.k}); нет: {missing or '—'}")
        return EXIT_OK

    key = os.environ.get("STEPFUN_API_KEY")
    if not key:
        print("STEPFUN_API_KEY не в окружении — прогон невозможен", file=sys.stderr)
        return EXIT_NO_KEY

    manifest = [
        "# Серия k=3 по дизайну навыков + О5 — генерация (TASK-hermes-12 §25.1/§25.2)",
        "",
        f"Старт (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Задача: {args.task}; бриф `{task['brief']}` (sha256 `{sha256_text(brief)}…`)",
        f"k={args.k}; генерация — прямой вызов API (среда = промпт); цена — §1.8 под модель",
        "",
        "| Цепочка | Промпт (символов) | sha256 | Итог |",
        "|---|---|---|---|",
    ]
    failures = 0

    for group, rows in plan.items():
        for arm, prompt, model in rows:
            failures += run_group(group, arm, prompt, model, out_dir, key, args.timeout, args.k, manifest)

    # O5-B: промпт каждой цепочки зависит от research-файла этой цепочки.
    for group in ("o5b-P", "o5b-F"):
        if group not in groups:
            continue
        src = out_dir / ("research" if group == "o5b-P" else "o5a") / "lean"
        for idx in range(args.k):
            research_file = src / ("final.md" if idx == 0 else f"final-{idx}.md")
            if not research_file.is_file():
                failures += 1
                manifest.append(f"| {group}/skill#{idx} | — | — | FAIL нет research-источника {research_file.name} |")
                print(f"{group}/skill#{idx}: нет research-источника {research_file}", file=sys.stderr)
                continue
            research = research_file.read_text(encoding="utf-8", errors="replace")
            prompt = build_o5b_prompt(brief, evidence, research)
            arm_dir = out_dir / group / "skill"
            arm_dir.mkdir(parents=True, exist_ok=True)
            (arm_dir / f"prompt-{idx}.md").write_text(prompt, encoding="utf-8")
            res = generate(prompt, key, args.timeout, MODEL_STEP5)
            (arm_dir / f"final{'' if idx == 0 else f'-{idx}'}.md").write_text(res["text"], encoding="utf-8")
            if res["error"] or not res["text"]:
                failures += 1
                manifest.append(f"| {group}/skill#{idx} | {len(prompt)} | {sha256_text(prompt)} | FAIL {res['error'] or 'пустой ответ'} |")
                print(f"{group}/skill#{idx}: FAIL {res['error'] or 'пустой ответ'}", file=sys.stderr)
                continue
            meta_path = arm_dir / f"meta-{idx}.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "group": group,
                        "arm": "skill",
                        "model": MODEL_STEP5,
                        "research_source": str(research_file),
                        "research_sha256_16": sha256_text(research),
                        "prompt_sha256_16": sha256_text(prompt),
                        "prompt_chars": len(prompt),
                        "finished_utc": datetime.now(timezone.utc).isoformat(),
                        "sessions": [{"name": f"final{'' if idx == 0 else f'-{idx}'}", **res}],
                        "cost_usd_total": res["cost_usd"],
                        "tokens_total": res["tokens"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            manifest.append(
                f"| {group}/skill#{idx} | {len(prompt)} | {sha256_text(prompt)} | OK "
                f"(${res['cost_usd']:.4f}, {len(res['text'])} символов) |"
            )
            print(f"{group}/skill#{idx}: {len(res['text'])} символов, ${res['cost_usd']:.4f}")

    manifest.append("")
    manifest.append(f"Финиш (UTC): {datetime.now(timezone.utc).isoformat()}")
    manifest.append(f"Провалов: {failures}")
    (out_dir / "manifest.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"готово, провалов: {failures}, манифест: {out_dir / 'manifest.md'}")
    return EXIT_RUN_FAILED if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
