#!/usr/bin/env python3
"""run_critic_step4.py — итерация TASK-hermes-8 §2: таргетирование
критика на шаг 4 (стратегии) вместо сквозного цикла.

Гипотеза (предрегистрация — measurements.md §21.1-Б): критик на шаге 4
даёт измеримый прирост, потому что цена ошибки в стратегии максимальна;
на шаге 3 под типовой рубрикой критик-ревизия дала −3/+3 (§20.6) — то
есть там он не рычаг. Анти-круг: шаг 3 уже измерен, шаг 4 — нет.

Дизайн: черновик — РЕАЛЬНЫЙ артефакт шага 4 (`project/strategy-product.md`,
произведён агентом без критика). Критик (изолированный контекст,
рубрика хакатона — [допущение]: типовых рубрик для шага 4 нет, а
артефакты шага 4 и есть deliverable хакатона) → находки → точечная
ревизия (JSON-правки, `scripts/apply_revision.py`, integrity-гейт,
честный откат) → финал. Рубрика считается ОТДЕЛЬНЫМИ прогонами
критика на черновике и финале (кэш score_arms не переиспуется: это
разные артефакты).

Контракт CLI:
    python3 eval/run_critic_step4.py --draft FILE [--out DIR] [--timeout SEC]

Коды возврата: 0 — прогон завершён; 4 — провал сессии/апдейтера.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from arg_chunk import chunk_prompt  # noqa: E402,F401 (реэкспорт для совместимости)
import run_label  # noqa: E402

EXIT_OK = 0
EXIT_RUN_FAILED = 4

DEFAULT_DRAFT = REPO_ROOT / "project" / "strategy-product.md"
DEFAULT_OUT = REPO_ROOT / "eval" / "runs" / "t8-step4"
RUBRIC = "eval/rubrics/hackathon-criteria.md"
MODEL = "stepfun/step-5-preview"

STEP4_REVISION_PROMPT = """Ты — тот же агент «Стратег», дорабатываешь свой артефакт шага 4
(продуктовая стратегия) по находкам внутреннего критика. Это ТОЧЕЧНАЯ
правка (targeted patch), а не переписывание: полный артефакт заново не
выдаётся.

Верни ТОЛЬКО JSON-блок (в фи ```json или голым JSON) такого вида:

{{"edits": [{{"find": "<дословный фрагмент черновика, 40–800 символов>",
"replace": "<новый текст>", "finding": "<какую находку закрывает>",
"action": "apply|reject", "reason": "<обязательно при reject>"}}]}}

Правила:
- Не переписывай артефакт целиком: каждая правка — замена одного
  фрагмента (find → replace). Допустимы добавления нового текста.
- find копируется из черновика ДОСЛОВНО (символ в символ): иначе правка
  не применится (0 вхождений — not-found, больше одного — ambiguous).
- Не удаляй секции артефакта (заголовки `##`/`###`).
- Сохрани маркеры [факт]/[гипотеза]/[прогноз]/[допущение] и основания
  (ev-N / URL) в той же строке, что и число.
- Отклонённая находка — action "reject" с явной причиной в reason.
- Не более 15 правок.

=== ЧЕРНОВИК ===
{draft}
=== НАХОДКИ КРИТИКА ===
{findings}
=== КОНЕЦ ===

Верни только JSON-блок ответом в чат. Файлы не пиши.
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_critic_step4.py",
        description="Таргетирование критика на шаг 4: черновик → критик → точечная ревизия → замер Δ.",
    )
    parser.add_argument("--draft", default=str(DEFAULT_DRAFT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--timeout", type=int, default=900)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    # Импорт после подготовки sys.path: руки стенда переиспользуются как есть.
    from run_ab import parse_patch_json, run_session  # noqa: PLC0415

    draft_path = Path(args.draft)
    if not draft_path.is_file():
        print(f"черновик не найден: {draft_path}", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    draft = draft_path.read_text(encoding="utf-8-sig", errors="replace")

    # 1) Критик на черновике (изолированный контекст, рубрика хакатона).
    critic_dir = out_dir / "critic-draft"
    code = subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "scripts" / "run_critic.py"),
            "--artifact", str(draft_path),
            "--rubric", RUBRIC,
            "--mode", "critic",
            "--out", str(critic_dir),
            "--tag", "t8-step4-critic-draft",
            "--timeout", str(args.timeout),
        ],
        cwd=REPO_ROOT,
    ).returncode
    if code != 0:
        print(f"критик на черновике упал exit={code}", file=sys.stderr)
        return EXIT_RUN_FAILED
    findings = (critic_dir / "critic.out").read_text(encoding="utf-8", errors="replace")
    (out_dir / "findings.md").write_text(findings, encoding="utf-8")

    # 2) Точечная ревизия по находкам (свежая сессия, только JSON правок).
    run_label.set_run_label("О4: t8-step4-revision")
    try:
        code, reply = run_session(
            STEP4_REVISION_PROMPT.format(draft=draft, findings=findings),
            out_dir, "revision", MODEL, args.timeout,
        )
    finally:
        run_label.clear_run_label()
    (out_dir / "revision.out").write_text(reply, encoding="utf-8")
    if code != 0:
        print(f"сессия ревизии упала exit={code}", file=sys.stderr)
        return EXIT_RUN_FAILED

    # 3) Применение правок с integrity-гейтом и честным откатом.
    patches = parse_patch_json(reply)
    if patches is None:
        (out_dir / "final.md").write_text(draft, encoding="utf-8")
        (out_dir / "revision-report.md").write_text(
            "# Отчёт по точечным правкам (critic на шаге 4)\n\n"
            "JSON правок из ответа модели разобрать не удалось — финал = "
            "черновик дословно (fallback).\n",
            encoding="utf-8",
        )
        print("правки не разобраны — финал = черновик (fallback)")
    else:
        edits = [e for e in patches.get("edits", []) if isinstance(e, dict)][:15]
        patches["edits"] = edits
        (out_dir / "patches.json").write_text(
            __import__("json").dumps(patches, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        code = subprocess.run(
            [
                sys.executable, str(REPO_ROOT / "scripts" / "apply_revision.py"),
                "--draft", str(draft_path),
                "--patches", str(out_dir / "patches.json"),
                "--out", str(out_dir / "final.md"),
                "--report", str(out_dir / "revision-report.md"),
            ],
            cwd=REPO_ROOT,
        ).returncode
        if code != 0:
            print(f"апдейтер правок упал exit={code}", file=sys.stderr)
            return EXIT_RUN_FAILED

    # 4) Замер: рубрика черновика и финала — отдельные прогоны критика.
    for name, artifact in (("draft", draft_path), ("final", out_dir / "final.md")):
        code = subprocess.run(
            [
                sys.executable, str(REPO_ROOT / "scripts" / "run_critic.py"),
                "--artifact", str(artifact),
                "--rubric", RUBRIC,
                "--mode", "critic",
                "--out", str(out_dir / f"score-{name}"),
                "--tag", f"t8-step4-score-{name}",
                "--timeout", str(args.timeout),
            ],
            cwd=REPO_ROOT,
        ).returncode
        if code != 0:
            print(f"замер {name} упал exit={code}", file=sys.stderr)
            return EXIT_RUN_FAILED

    print(f"готово: {out_dir} (critic-draft, revision, final, score-draft, score-final)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
