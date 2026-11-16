#!/usr/bin/env python3
"""run_critic.py — прогон внутреннего агента-критика с изолированным контекстом.

Протокол: knowledge/skills/critic/SKILL.md. Рубрика: eval/rubrics/.
Критик получает ТОЛЬКО артефакт + рубрику (инлайном в промпте), в свежей
сессии opencode run; доступ к файлам проекта запрещён инструкцией
(изоляция на уровне сессии и промпта, не sandbox — ограничение названо
в навыке). Ключ STEPFUN_API_KEY берётся из окружения и никогда не
печатается.

Контракт CLI:
    python3 scripts/run_critic.py --artifact FILE --rubric FILE
        --mode critic|self [--out DIR] [--tag TAG] [--model MODEL]
        [--timeout SEC]

Коды возврата:
    0 — прогон завершён, выход записан;
    1 — ошибка использования (нет аргументов/худший режим);
    2 — файл артефакта или рубрики не найден;
    3 — STEPFUN_API_KEY не в окружении;
    4 — прогон открылся с ненулевым кодом (детали в .err).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_FOUND = 2
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

REPO_ROOT = Path(__file__).resolve().parents[1]

CRITIC_ROLE = (
    "Ты — внутренний агент-критик «Стратега» с изолированным контекстом "
    "(роль из навыка critic). Ты оцениваешь ТОЛЬКО готовый артефакт ниже "
    "по рубрике ниже. У тебя нет доступа к истории создания: НЕ читай "
    "никакие файлы проекта (STATE.md, LOG.md, черновики, другие "
    "артефакты, каталог project/) — всё необходимое уже в этом промпте. "
    "Не правь артефакт, не пиши файлы: верни оценки и находки текстом. "
    "Это внутренняя проверка, не внешняя экспертиза — не пиши обратного."
)

SELF_ROLE = (
    "Ты — автор агента «Стратег», создавший артефакт ниже. Оцени СВОЙ "
    "артефакт по той же рубрике, двумя проходами (щедрый / строгий). "
    "Не читай файлы проекта: артефакт и рубрика уже в промпте. Не правь "
    "артефакт: верни самооценку и находки текстом."
)

OUTPUT_FORMAT = """\
Формат ответа (строго):

## Оценки
| Критерий | Проход 1 | Проход 2 | Баллы (×2, проход 2) |
| 1. Проработанность | _/5 | _/5 | _/10 |
| 2. Масштаб использования нейротехнологий | _/5 | _/5 | _/10 |
| 3. Имплементация | _/5 | _/5 | _/10 |
| 4. Качество | _/5 | _/5 | _/10 |
Итого: _ /40

## Findings
Каждая находка: [важность: критично|важно|незначительно] место
(цитата/раздел артефакта) → что не так → почему это важно → что
починит. Если находок нет — так и напиши, не выдумывай.

## Что сделано хорошо
1–3 пункта с доказательством из артефакта."""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_critic.py",
        description="Прогон внутреннего критика (изолированный контекст, свежая сессия).",
    )
    parser.add_argument("--artifact", required=True, help="markdown-артефакт для оценки")
    parser.add_argument("--rubric", required=True, help="файл рубрики")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["critic", "self"],
        help="critic — изолированный рецензент; self — роль автора (замер пользы)",
    )
    parser.add_argument(
        "--evidence-digest",
        default=None,
        help="файл с выдержками доказательств: критик получает мандат "
        "сверить каждую цитату артефакта с выдержкой (режим critic)",
    )
    parser.add_argument("--out", default=None, help="каталог прогона (default: eval/runs/<tag>)")
    parser.add_argument("--tag", default=None, help="метка прогона (default: critic-<mode>-<artifact>-<utc>)")
    parser.add_argument("--model", default="stepfun/step-5-preview")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    return args


def build_prompt(
    artifact_text: str,
    rubric_text: str,
    mode: str,
    evidence_digest: str | None = None,
) -> str:
    role = CRITIC_ROLE if mode == "critic" else SELF_ROLE
    mandate = ""
    if mode == "critic" and evidence_digest:
        mandate = (
            "\n\nДОПОЛНИТЕЛЬНЫЙ МАНДАТ (проверка цитат): ниже дан дайджест "
            "доказательств (выдержки из источников с URL). Сверь КАЖДУЮ "
            "существенную цитату/число артефакта с выдержкой: совпадает "
            "ли дословно, не добавилось ли к выдержке того, чего в ней "
            "нет (единицы измерения, знак валюты, уточнения), не "
            "приписывается ли источнику то, чего он не содержит. "
            "Каждое расхождение — отдельная находка с важностью «важно»."
            "\n\n=== ДАЙДЖЕСТ ДОКАЗАТЕЛЬСТВ ===\n" + evidence_digest + "\n=== КОНЕЦ ДАЙДЖЕСТА ===\n"
        )
    return (
        f"{role}{mandate}\n\n"
        f"=== РУБРИКА (eval/rubrics/hackathon-criteria.md) ===\n{rubric_text}\n\n"
        f"=== АРТЕФАКТ ПОД ОЦЕНКУ ===\n{artifact_text}\n\n"
        f"{OUTPUT_FORMAT}\n"
    )


def set_state_step(label: str) -> str | None:
    """Подпись прогона для хука cost-append (колонка «Шаг» в COST.md).

    Хук читает STATE.md `## шаг`; выставляем метку на время прогона и
    возвращаем прежнее значение после. Возвращает прежний текст секции
    (или None, если файла/секции нет).
    """
    state = REPO_ROOT / "STATE.md"
    try:
        text = state.read_text(encoding="utf-8")
    except OSError:
        return None
    import re

    match = re.search(r"(##\s*шаг\s*\n\n)([^\n#]*(?:\n(?![#\n])[^\n#]*)*)", text)
    if not match:
        return None
    previous = match.group(2).strip()
    patched = text[: match.start(2)] + label + text[match.end(2) :]
    try:
        state.write_text(patched, encoding="utf-8")
    except OSError:
        return None
    return previous


def restore_state_step(previous: str | None) -> None:
    if previous is None:
        return
    state = REPO_ROOT / "STATE.md"
    try:
        text = state.read_text(encoding="utf-8")
    except OSError:
        return
    import re

    match = re.search(r"(##\s*шаг\s*\n\n)([^\n#]*(?:\n(?![#\n])[^\n#]*)*)", text)
    if not match:
        return
    patched = text[: match.start(2)] + previous + text[match.end(2) :]
    try:
        state.write_text(patched, encoding="utf-8")
    except OSError:
        pass


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    artifact_path = Path(args.artifact)
    rubric_path = Path(args.rubric)
    for path in (artifact_path, rubric_path):
        if not path.is_file():
            print(f"файл не найден: {path}", file=sys.stderr)
            return EXIT_NOT_FOUND

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении — прогон невозможен (ключ только из env)", file=sys.stderr)
        return EXIT_NO_KEY

    artifact_text = artifact_path.read_text(encoding="utf-8-sig", errors="replace")
    rubric_text = rubric_path.read_text(encoding="utf-8-sig", errors="replace")
    evidence_digest = None
    if args.evidence_digest:
        digest_path = Path(args.evidence_digest)
        if not digest_path.is_file():
            print(f"дайджест не найден: {digest_path}", file=sys.stderr)
            return EXIT_NOT_FOUND
        evidence_digest = digest_path.read_text(encoding="utf-8-sig", errors="replace")
    prompt = build_prompt(artifact_text, rubric_text, args.mode, evidence_digest)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tag = args.tag or f"critic-{args.mode}-{artifact_path.stem}-{stamp}"
    out_dir = Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "critic.start").write_text(
        datetime.now(timezone.utc).isoformat() + "\n"
        f"artifact: {artifact_path}\nrubric: {rubric_path}\nmode: {args.mode}\nmodel: {args.model}\n",
        encoding="utf-8",
    )

    cmd = ["opencode", "run", "--model", args.model, prompt]
    step_label = f"О4: {tag}"
    previous_step = set_state_step(step_label)
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        (out_dir / "critic.end").write_text(
            datetime.now(timezone.utc).isoformat() + " TIMEOUT\n", encoding="utf-8"
        )
        print(f"прогон превысил таймаут {args.timeout}s: {out_dir}", file=sys.stderr)
        return EXIT_RUN_FAILED
    finally:
        restore_state_step(previous_step)

    (out_dir / "critic.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "critic.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / "critic.end").write_text(
        datetime.now(timezone.utc).isoformat() + f" exit={proc.returncode}\n",
        encoding="utf-8",
    )

    print(f"mode={args.mode} artifact={artifact_path} out={out_dir} exit={proc.returncode}")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        print("\n".join(tail), file=sys.stderr)
        return EXIT_RUN_FAILED
    print(f"оценки и находки: {out_dir / 'critic.out'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
