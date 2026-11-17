#!/usr/bin/env python3
"""run_critic.py — прогон внутреннего агента-критика с изолированным контекстом.

Протокол: knowledge/skills/critic/SKILL.md. Рубрика: eval/rubrics/.
Критик получает ТОЛЬКО артефакт + рубрику (инлайном в промпте), в свежей
сессии opencode run; доступ к файлам проекта запрещён инструкцией
(изоляция на уровне сессии и промпта, не sandbox — ограничение названо
в навыке). Ключ STEPFUN_API_KEY берётся из окружения и никогда не
печатается.

Контракт CLI:
    python3 scripts/run_critic.py --artifact FILE1[,FILE2,...]
        --rubric FILE --mode critic|self [--out DIR] [--tag TAG]
        [--model MODEL] [--timeout SEC]

Несколько файлов в --artifact (через запятую) — пакетный режим (H4):
один прогон на весь набор артефактов с мандатом межартефактных
находок. Метка прогона для хука cost-append пишется в отдельный
файл eval/.cost-label (STATE.md агенту не трогается).

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

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from arg_chunk import chunk_prompt  # noqa: E402  (путь добавляется выше)
import run_label  # noqa: E402  (метка прогона — отдельный файл, не STATE.md)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_FOUND = 2
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

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

PACKAGE_OUTPUT_FORMAT = """\
Формат ответа (строго):

## Оценки (один набор на ВЕСЬ пакет)
| Критерий | Проход 1 | Проход 2 | Баллы (×2, проход 2) |
| 1. Проработанность | _/5 | _/5 | _/10 |
| 2. Масштаб использования нейротехнологий | _/5 | _/5 | _/10 |
| 3. Имплементация | _/5 | _/5 | _/10 |
| 4. Качество | _/5 | _/5 | _/10 |
Итого: _ /40

## Findings
Каждая находка: [важность: критично|важно|незначительно] место
(АРТЕФАКТ + раздел/цитата; для межартефактных — «А против Б») →
что не так → почему это важно → что починит. ОБЯЗАТЕЛЬНО проверь
согласованность МЕЖДУ артефактами: выбор, метрики, экономика,
пороги. Если находок нет — так и напиши, не выдумывай.

## Что сделано хорошо
1–3 пункта с доказательством из артефактов."""

PACKAGE_ROLE_SUFFIX = (
    " Ниже дан ПАКЕТ артефактов задачи (несколько файлов под "
    "заголовками «=== АРТЕФАКТ: имя ===»). Оцени пакет целиком по "
    "рубрике; отдельно ищи несоответствия МЕЖДУ артефактами "
    "(выбор, метрики, экономика, пороги) — этого пофайловая "
    "оценка не видит."
)


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


def rubric_defines_format(rubric_text: str) -> bool:
    """Рубрика несёт свой формат выхода — тогда промпт НЕ добавляет
    свой (дефект TASK-16: жёсткий базовый формат в промпте конфликтовал
    с расширенной рубрикой, и модель молчала по критерию 5, ссылаясь на
    «запрошенный формат»). Рубрика — контракт; блок в промпте — дефолт
    для рубрик без своего формата."""
    return "Формат выхода оценщика" in rubric_text or "Итого" in rubric_text


def build_prompt(
    artifact_text: str,
    rubric_text: str,
    mode: str,
    evidence_digest: str | None = None,
    package: list[tuple[str, str]] | None = None,
    rubric_name: str = "eval/rubrics/hackathon-criteria.md",
) -> str:
    role = CRITIC_ROLE if mode == "critic" else SELF_ROLE
    if package:
        role = role + PACKAGE_ROLE_SUFFIX
        artifact_block = "\n\n".join(
            f"=== АРТЕФАКТ: {name} ===\n{text}" for name, text in package
        )
        out_format = PACKAGE_OUTPUT_FORMAT
    else:
        artifact_block = artifact_text
        # Рубрика со своим форматом — единственный контракт выхода;
        # иначе (рубрика без формата) — дефолтный блок промпта.
        out_format = "" if rubric_defines_format(rubric_text) else OUTPUT_FORMAT
    mandate = ""
    if mode == "critic" and evidence_digest:
        mandate = (
            "\n\nДОПОЛНИТЕЛЬНЫЙ МАНДАТ (проверка цитат): ниже дан дайджест "
            "доказательств (выдержки из источников с URL). Сверь КАЖДУЮ "
            "существенную цитату/число артефакта с выдержкой: совпадает "
            "ли дословно, не добавилось ли к выдержке того, чего в ней "
            "нет (единицы измерения, знак валюты, уточнения), не "
            "приписывается ли источнику то, чего он не содержит. "
            "Каждое расхождение — отдельная находка с важностью «важно». "
            "В конце строкой: «Неподтверждённых claim'ов: N» — сколько "
            "существенных claim'ов артефакта НЕ нашли подтверждения в "
            "дайджесте (сам дайджест при этом полный — всё, что в нём "
            "не подтверждено, и есть неподтверждённый claim)."
            "\n\n=== ДАЙДЖЕСТ ДОКАЗАТЕЛЬСТВ ===\n" + evidence_digest + "\n=== КОНЕЦ ДАЙДЖЕСТА ===\n"
        )
    return (
        f"{role}{mandate}\n\n"
        f"=== РУБРИКА ({rubric_name}) ===\n{rubric_text}\n\n"
        f"=== АРТЕФАКТ ПОД ОЦЕНКУ ===\n{artifact_block}\n\n"
        f"{out_format}\n"
    )


def set_run_label(label: str) -> None:
    """Подпись прогона для хука cost-append (колонка «Шаг» в COST.md).

    Метка пишется в отдельный файл `eval/.cost-label` (модуль
    run_label): STATE.md принадлежит агенту, и раннер не трогает его —
    иначе restore метки затирал бы правки агента (гонка, найденная в
    прогоне О4-хвоста; TASK-hermes-6 п.4).
    """
    run_label.set_run_label(label)


def clear_run_label() -> None:
    run_label.clear_run_label()


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    artifact_paths = [Path(p) for p in args.artifact.split(",") if p.strip()]
    rubric_path = Path(args.rubric)
    for path in (*artifact_paths, rubric_path):
        if not path.is_file():
            print(f"файл не найден: {path}", file=sys.stderr)
            return EXIT_NOT_FOUND

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении — прогон невозможен (ключ только из env)", file=sys.stderr)
        return EXIT_NO_KEY

    package: list[tuple[str, str]] | None = None
    artifact_text = ""
    if len(artifact_paths) > 1:
        # Пакетный режим (H4): несколько артефактов одним прогоном.
        package = [
            (p.name, p.read_text(encoding="utf-8-sig", errors="replace"))
            for p in artifact_paths
        ]
    else:
        artifact_text = artifact_paths[0].read_text(encoding="utf-8-sig", errors="replace")
    rubric_text = rubric_path.read_text(encoding="utf-8-sig", errors="replace")
    evidence_digest = None
    if args.evidence_digest:
        digest_path = Path(args.evidence_digest)
        if not digest_path.is_file():
            print(f"дайджест не найден: {digest_path}", file=sys.stderr)
            return EXIT_NOT_FOUND
        evidence_digest = digest_path.read_text(encoding="utf-8-sig", errors="replace")
    # Имя рубрики в промпте — фактическое (дефект TASK-16: жёсткая
    # подпись базового файла при расширенной рубрике заставляла модель
    # выдавать базовый формат «Итого /40» и молчать по критерию 5).
    try:
        rubric_display = rubric_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rubric_display = rubric_path.name
    prompt = build_prompt(artifact_text, rubric_text, args.mode, evidence_digest,
                          package, rubric_name=rubric_display)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifacts_label = "+".join(p.stem for p in artifact_paths)
    tag = args.tag or f"critic-{args.mode}-{artifacts_label}-{stamp}"
    out_dir = Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "critic.start").write_text(
        datetime.now(timezone.utc).isoformat() + "\n"
        + "\n".join(f"artifact: {p}" for p in artifact_paths) + "\n"
        f"rubric: {rubric_path}\nmode: {args.mode}\nmodel: {args.model}\n",
        encoding="utf-8",
    )

    cmd = ["opencode", "run", "--model", args.model, *chunk_prompt(prompt)]
    set_run_label(f"О4: {tag}")
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
        clear_run_label()

    (out_dir / "critic.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "critic.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / "critic.end").write_text(
        datetime.now(timezone.utc).isoformat() + f" exit={proc.returncode}\n",
        encoding="utf-8",
    )

    print(f"mode={args.mode} artifacts={[str(p) for p in artifact_paths]} out={out_dir} exit={proc.returncode}")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        print("\n".join(tail), file=sys.stderr)
        return EXIT_RUN_FAILED
    # Дефект «exit 0 ≠ непустой выход» (TASK-hermes-5/9): провайдер может
    # вернуть успешный код с пустым ответом — такой прогон НЕ измерение.
    if not (proc.stdout or "").strip():
        print("критик вернул ПУСТОЙ выход при exit=0 — прогон не засчитан", file=sys.stderr)
        return EXIT_RUN_FAILED
    print(f"оценки и находки: {out_dir / 'critic.out'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
