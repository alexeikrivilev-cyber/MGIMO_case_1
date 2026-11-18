#!/usr/bin/env python3
"""run_long_dialogue.py — предрегистрированный эксперимент TASK-hermes-23.

Три руки на замороженных артефактах демо `demo-retention`:

    A — одна длинная сессия: сид (рамка + все артефакты инлайном), затем
        12 поворотов РП в той же сессии (`opencode run -s <id>`);
    B — продуктовый паттерн: каждый поворот — свежая сессия, сид =
        `STATE.md` + релевантный артефакт инлайном;
    C — контроль: каждый поворот — свежая сессия с артефактом инлайном,
        без состояния и без истории.

Повороты, метрики M1–M5, правило вердикта и состав сида заморожены в
`eval/runs/t23-longdialogue/PREREGISTRATION.md` ДО прогонов; этот драйвер
исполняет их механически и не содержит продуктовых решений.

Промпт передаётся через STDIN, а не argv: сид руки A ≈250 КБ, а Linux
ограничивает один argv-аргумент 128 КБ (MAX_ARG_STRLEN → OSError E2BIG,
прецедент «тихого убийства» раннера council-full, `eval/arg_chunk.py`).
Склейка message через пробел при нескольких argv-аргументах меняла бы
байты промпта — stdin передаёт их дословно.

Контракт CLI:
    python3 eval/run_long_dialogue.py --hand A [--turns 1-12] [--timeout SEC]
        [--dry-run] [--out DIR]

Коды возврата: 0 — все запрошенные повороты выполнены (включая помеченные
FAILED по порогу годности — провал поворота это данные, не сбой драйвера);
3 — нет ключа; 4 — прогон упал (исключение без ответа).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

import run_label  # noqa: E402  (метка прогона — отдельный файл, STATE.md не трогаем)

EXIT_OK = 0
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

MODEL = "stepfun/step-5-preview"
RUNS_ROOT = REPO_ROOT / "eval" / "runs" / "t23-longdialogue"
DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

# Цена step-5-preview (§1.8 прайс-документа), $ за 1M токенов.
PRICE = {"input": 1.0, "cache_read": 0.1, "output": 2.7}

# Порог годности поворота (предрегистрация §5): непустой ответ ≥300 символов.
MIN_ANSWER_CHARS = 300
MAX_ATTEMPTS = 2  # первый провал — один повтор тем же промптом (§26.4)

# --- Повороты: дословно из TASK-hermes-23.md, не меняются -------------------

TURNS: dict[int, str] = {
    1: "Почему удержание падает? Коротко, три причины.",
    2: "Какой вариант вы выбрали и почему не третий?",
    3: "Какая у нас метрика успеха и её baseline?",
    4: "А если бюджет на удержание равен нулю — что меняется?",
    5: "Пересчитай экономику выбранного варианта при оттоке 30% вместо 21%.",
    6: "Напомни, какую метрику мы измеряем и от какого baseline?",
    7: "Что мы НЕ знаем и какие пробелы названы?",
    8: "Сократи план до одной инициативы — что оставишь?",
    9: "Почему в коммуникационной стратегии именно этот канал?",
    10: "Дай три возражения против собственного решения.",
    11: "Метрика успеха и baseline?",
    12: "Итог: что делаем в первую очередь и как поймём, что сработало?",
}

# --- Состав сида (предрегистрация §3) ---------------------------------------

# Рука A: рамка + все артефакты стратегии + записи доказательств.
# decisions.md (шаг 5) в сид не входит — решение зафиксировано в
# предрегистрации §3 до прогонов.
A_COMPONENTS: list[tuple[str, str]] = [
    ("РАМКА ЗАДАЧИ", "project/brief.md"),
    ("АРТЕФАКТ — ИССЛЕДОВАНИЕ (шаг 2)", "project/research.md"),
    ("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md"),
    ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
    ("АРТЕФАКТ — КОММУНИКАЦИОННАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-comms.md"),
    ("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
    ("ДОКАЗАТЕЛЬСТВО — бенчмарки Mixpanel", "project/evidence/ev-001-mixpanel-benchmarks.md"),
    ("ДОКАЗАТЕЛЬСТВО — датасет IBM Telco Churn", "project/evidence/ev-002-telco-dataset-stats.md"),
    ("ДОКАЗАТЕЛЬСТВО — драйверы оттока (arXiv)", "project/evidence/ev-003-arxiv-churn-drivers.md"),
]

# Руки B и C: релевантный артефакт поворота (одинаков, чтобы руки различались
# только мостом состояния).
TURN_ARTIFACTS: dict[int, list[tuple[str, str]]] = {
    1: [("АРТЕФАКТ — ИССЛЕДОВАНИЕ (шаг 2)", "project/research.md"),
        ("ДОКАЗАТЕЛЬСТВО — датасет IBM Telco Churn", "project/evidence/ev-002-telco-dataset-stats.md")],
    2: [("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md")],
    3: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
        ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    4: [("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md"),
        ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    5: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
        ("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md")],
    6: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
        ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    7: [("АРТЕФАКТ — ИССЛЕДОВАНИЕ (шаг 2)", "project/research.md")],
    8: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    9: [("АРТЕФАКТ — КОММУНИКАЦИОННАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-comms.md")],
    10: [("АРТЕФАКТ — ВАРИАНТЫ (шаг 3)", "project/options.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    11: [("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md"),
         ("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md")],
    12: [("АРТЕФАКТ — ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4)", "project/strategy-product.md"),
         ("АРТЕФАКТ — ПЛАН ПРОВЕРКИ (шаг 4)", "project/verification-plan.md")],
}

STATE_PATH = REPO_ROOT / "STATE.md"
TEMPLATE_PATH = "eval/runs/t23-longdialogue/prompt-template.md"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_turns(spec: str) -> list[int]:
    """«1-12» / «1,3,5» / «7» → список номеров поворотов."""
    turns: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, _, hi = chunk.partition("-")
            turns.extend(range(int(lo), int(hi) + 1))
        else:
            turns.append(int(chunk))
    unknown = [t for t in turns if t not in TURNS]
    if unknown:
        raise SystemExit(f"неизвестные номера поворотов: {unknown}")
    return sorted(set(turns))


# --- Сид ---------------------------------------------------------------------


def read_component(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def build_seed(arm: str, turn: int) -> tuple[str, list[dict[str, str]]]:
    """Собрать полный промпт поворота. Возвращает (текст, компоненты с sha256)."""
    template = read_component(TEMPLATE_PATH)
    parts: list[str] = [template.strip(), ""]
    components: list[dict[str, str]] = [
        {"role": "шаблон промпта", "path": TEMPLATE_PATH, "sha256": sha256_text(template)}
    ]

    if arm == "A":
        blocks = A_COMPONENTS
    else:
        blocks = list(TURN_ARTIFACTS[turn])

    parts.append("----- НАЧАЛО ВХОДНЫХ ДАННЫХ -----")
    parts.append("")
    index = 1
    if arm == "B":
        state_text = STATE_PATH.read_text(encoding="utf-8")
        parts.append(f"[{index}] СОСТОЯНИЕ ЗАДАЧИ — файл STATE.md (resume-карта, дословно)")
        parts.append("")
        parts.append(state_text.strip())
        parts.append("")
        components.append(
            {"role": "состояние задачи", "path": "STATE.md", "sha256": sha256_text(state_text)}
        )
        index += 1
    for title, rel in blocks:
        text = read_component(rel)
        parts.append(f"[{index}] {title} — файл {rel}")
        parts.append("")
        parts.append(text.strip())
        parts.append("")
        components.append({"role": title, "path": rel, "sha256": sha256_text(text)})
        index += 1
    parts.append("----- КОНЕЦ ВХОДНЫХ ДАННЫХ -----")
    parts.append("")
    parts.append(TURNS[turn])
    return "\n".join(parts), components


def write_prompt_record(arm_dir: Path, arm: str, turn: int, prompt: str,
                        components: list[dict[str, str]]) -> None:
    """Журнальная запись промпта.

    Рука A: полный сид хранится один раз в `A/seed.md`, повороты 2–12 —
    голый текст вопроса в той же сессии, поэтому в записи поворота лежит
    ссылка на сид (иначе 200+ КБ дублировались бы 12 раз).
    Руки B и C: сид собирается из шаблона + (STATE.md для B) + артефактов;
    компоненты перечислены с sha256, полный промпт восстановим по ним
    байт-в-байт (sha256 полного промпта — в записи).
    """
    lines = [
        f"# Рука {arm}, поворот {turn} — промпт сессии",
        "",
        f"## Вопрос РП (дословно)",
        "",
        TURNS[turn],
        "",
        f"## Компоненты сида (путь — sha256)",
        "",
    ]
    lines += [f"- `{c['path']}` ({c['role']}) — `{c['sha256']}`" for c in components]
    if arm == "A":
        lines += [
            "",
            "## Сборка",
            "",
            "Полный промпт = `seed.md` (sha256 — в `seed-manifest.json`) + вопрос РП.",
            "Повороты 2–12 отправлялись в ту же сессию голым текстом вопроса.",
        ]
    else:
        lines += [
            "",
            "## Сборка",
            "",
            "Полный промпт = компоненты в порядке списка (шаблон, затем "
            + ("`STATE.md` (копия — `B/state-as-used.md`), затем " if arm == "B" else "")
            + "артефакты) + вопрос РП.",
        ]
    lines += ["", f"sha256 полного промпта: `{sha256_text(prompt)}`", ""]
    (arm_dir / f"turn-{turn:02d}.prompt.md").write_text("\n".join(lines), encoding="utf-8")


# --- OpenCode ----------------------------------------------------------------


def run_opencode(prompt: str, session_id: str | None, timeout: int) -> dict:
    """Один запуск `opencode run` (промпт — через stdin)."""
    cmd = ["opencode", "run", "--model", MODEL, "--format", "json"]
    if session_id:
        cmd += ["-s", session_id]
    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    finished = datetime.now(timezone.utc)
    events = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    sid = next((e.get("sessionID") for e in events if e.get("sessionID")), None)
    text_parts = [
        e["part"]["text"]
        for e in events
        if e.get("type") == "text" and isinstance(e.get("part"), dict) and "text" in e["part"]
    ]
    return {
        "session_id": sid,
        "text": "\n".join(text_parts),
        "exit_code": proc.returncode,
        "stderr_tail": proc.stderr[-2000:],
        "events": len(events),
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "elapsed_sec": round((finished - started).total_seconds(), 1),
    }


def session_metrics(session_id: str | None) -> dict:
    """Токены последнего ассистентского сообщения + тул-вызовы (БД OpenCode)."""
    empty = {
        "input": None, "output": None, "reasoning": None, "cache_read": None,
        "cost_usd_provider": None, "cost_usd_formula": None, "tool_calls": None,
        "patch_parts": None, "assistant_messages": None,
    }
    if not session_id or not DB_PATH.is_file():
        return empty
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        messages = [
            json.loads(data)
            for (data,) in cur.execute(
                "select data from message where session_id=? order by time_created", (session_id,)
            )
        ]
        tool_calls = 0
        patch_parts = 0
        for (data,) in cur.execute("select data from part where session_id=?", (session_id,)):
            part = json.loads(data)
            if part.get("type") == "tool":
                tool_calls += 1
            elif part.get("type") == "patch":
                patch_parts += 1
    finally:
        con.close()
    assistants = [d for d in messages if d.get("role") == "assistant" and d.get("tokens")]
    if not assistants:
        return {**empty, "tool_calls": tool_calls, "patch_parts": patch_parts,
                "assistant_messages": len(assistants)}
    last = assistants[-1]
    tokens = last.get("tokens") or {}
    cache = tokens.get("cache") or {}
    cost = last.get("cost")
    estimate = (
        (tokens.get("input") or 0) * PRICE["input"] / 1e6
        + (cache.get("read") or 0) * PRICE["cache_read"] / 1e6
        + (tokens.get("output") or 0) * PRICE["output"] / 1e6
    )
    return {
        "input": tokens.get("input"),
        "output": tokens.get("output"),
        "reasoning": tokens.get("reasoning"),
        "cache_read": cache.get("read"),
        "cost_usd_provider": round(cost, 6) if isinstance(cost, (int, float)) else None,
        "cost_usd_formula": round(estimate, 6),
        "tool_calls": tool_calls,
        "patch_parts": patch_parts,
        "assistant_messages": len(assistants),
    }


# --- Прогон руки -------------------------------------------------------------


def answer_record_text(arm: str, turn: int, session_id: str | None, status: str,
                       attempts: int, answer: str) -> str:
    """Текст журнальной записи ответа.

    Метаданные поворота идут блокцитатой: `check_sources.py` исключает
    блокцитаты из проверки (правило гейта), поэтому журнальная шапка не
    создаёт ложных находок sources в самом ответе агента. Разделитель
    `---` и заголовок `#` (уровень 1) секцию не открывают — проверяется
    ровно то, что ответил агент.
    """
    return (
        f"# Рука {arm}, поворот {turn} — ответ агента (дословно)\n\n"
        f"> Вопрос РП: {TURNS[turn]}\n>\n"
        f"> sessionID: {session_id}\n>\n"
        f"> Рука {arm}, поворот {turn} из 12; статус {status}, попыток {attempts}\n\n"
        f"---\n\n{answer}\n"
    )


def run_hand(arm: str, turns: list[int], timeout: int, out_root: Path) -> int:
    arm_dir = out_root / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    session_id: str | None = None
    failures = 0

    if arm == "A":
        # Сид одной сессии — в журнал целиком (это якорь воспроизводимости).
        _, components = build_seed("A", turns[0])
        prompt0, _ = build_seed("A", turns[0])
        seed_text = prompt0[: prompt0.rfind(TURNS[turns[0]])].rstrip()
        (arm_dir / "seed.md").write_text(seed_text + "\n", encoding="utf-8")
        (arm_dir / "seed-manifest.json").write_text(
            json.dumps(
                {
                    "arm": "A",
                    "seed_sha256": sha256_text(seed_text),
                    "seed_chars": len(seed_text),
                    "components": components,
                    "note": "сид один на все 12 поворотов; повороты 2–12 — голый текст вопроса в той же сессии",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if arm == "B":
        state_text = STATE_PATH.read_text(encoding="utf-8")
        (arm_dir / "state-as-used.md").write_text(
            f"# STATE.md как использован в сиде руки B\n\n"
            f"sha256: `{sha256_text(state_text)}`\n"
            f"скопирован: {datetime.now(timezone.utc).isoformat()}\n\n---\n\n{state_text}",
            encoding="utf-8",
        )

    for turn in turns:
        prompt, components = build_seed(arm, turn)
        write_prompt_record(arm_dir, arm, turn, prompt, components)

        # Метка прогона: рука A — одна сессия на 12 поворотов (хук мержит
        # строки по sessionID, поэтому поповоротные метки в COST.md для A
        # невозможны — поповоротная цена берётся из БД); руки B и C — своя
        # сессия на поворот, метка ставится на каждый поворот.
        label = f"t23-longdialogue-{arm}" if arm == "A" else f"t23-longdialogue-{arm}-t{turn:02d}"

        answer = ""
        attempts = 0
        status = "FAILED"
        run_meta: dict = {}
        run_label.set_run_label(label)
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                attempts = attempt
                try:
                    run_meta = run_opencode(prompt, session_id, timeout)
                except subprocess.TimeoutExpired:
                    run_meta = {
                        "session_id": session_id, "text": "", "exit_code": None,
                        "stderr_tail": f"TIMEOUT {timeout}s", "events": 0,
                        "started_utc": "", "finished_utc": "", "elapsed_sec": timeout,
                    }
                if arm == "A" and run_meta.get("session_id"):
                    session_id = run_meta["session_id"]
                answer = (run_meta.get("text") or "").strip()
                if run_meta.get("exit_code") == 0 and len(answer) >= MIN_ANSWER_CHARS:
                    status = "OK"
                    break
                print(
                    f"[{arm} поворот {turn}] попытка {attempt}: exit={run_meta.get('exit_code')}, "
                    f"символов {len(answer)} — повтор по протоколу §26.4",
                    flush=True,
                )
        finally:
            run_label.clear_run_label()

        metrics = (
            session_metrics(run_meta.get("session_id"))
            if run_meta.get("session_id")
            else session_metrics(None)
        )
        answer_file = arm_dir / f"turn-{turn:02d}.answer.md"
        answer_file.write_text(
            answer_record_text(arm, turn, run_meta.get("session_id"), status, attempts, answer),
            encoding="utf-8",
        )
        meta = {
            "arm": arm,
            "turn": turn,
            "question": TURNS[turn],
            "session_id": run_meta.get("session_id"),
            "status": status,
            "attempts": attempts,
            "answer_chars": len(answer),
            "prompt_chars": len(prompt),
            "prompt_sha256": sha256_text(prompt),
            "components": components,
            "exit_code": run_meta.get("exit_code"),
            "elapsed_sec": run_meta.get("elapsed_sec"),
            "started_utc": run_meta.get("started_utc"),
            "finished_utc": run_meta.get("finished_utc"),
            "answer_file": f"{arm}/turn-{turn:02d}.answer.md",
            "prompt_file": f"{arm}/turn-{turn:02d}.prompt.md",
            "metrics_db": metrics,
        }
        (arm_dir / f"turn-{turn:02d}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if status != "OK":
            failures += 1
        print(
            f"[{arm} поворот {turn}] {status}: {len(answer)} символов, "
            f"тулов {metrics.get('tool_calls')}, in={metrics.get('input')}, "
            f"out={metrics.get('output')}",
            flush=True,
        )

    (arm_dir / "session.json").write_text(
        json.dumps(
            {"arm": arm, "session_id": session_id, "model": MODEL, "turns": turns},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"рука {arm}: поворотов {len(turns)}, из них провалено по порогу {failures}")
    return EXIT_OK


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_long_dialogue.py")
    parser.add_argument("--hand", required=True, choices=["A", "B", "C"])
    parser.add_argument("--turns", default="1-12")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    turns = parse_turns(args.turns)
    out_root = Path(args.out) if args.out else RUNS_ROOT

    if args.dry_run:
        prompt, components = build_seed(args.hand, turns[0])
        print(f"[dry-run] рука {args.hand}, поворотов {len(turns)}, "
              f"промпт поворота {turns[0]}: {len(prompt)} символов, "
              f"компонент {len(components)}")
        return EXIT_OK

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении — прогон невозможен", file=sys.stderr)
        return EXIT_NO_KEY

    started = time.time()
    code = run_hand(args.hand, turns, args.timeout, out_root)
    print(f"рука {args.hand}: итог {time.time() - started:.0f}s, артефакты {out_root / args.hand}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
