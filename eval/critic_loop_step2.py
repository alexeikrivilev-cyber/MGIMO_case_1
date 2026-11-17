#!/usr/bin/env python3
"""critic_loop_step2.py — H-C2: критик + точечная ревизия на шаге 2 (TASK-hermes-12 §25.3).

Предрегистрация: measurements.md §25.3 ДО прогонов. Новая гипотеза
(не круг): критик-ревизия как УЛУЧШИТЕЛЬ измерена на шагах 3/4/пакете
(suggestive/отрицательно) и деградировала во втором раунде (H-R2), но
на шаге 2 ПЕРВЫЙ раунд не измерян. H-C2 прогоняет над черновиками
шага 2 (рука lean из §25.1) цепочку critic-loop2: свежий критик
(мандат — типовая рубрика rubric-research, принцип H2) → модель
возвращает JSON точечных правок → `scripts/apply_revision.py`
применяет их с integrity-гейтом и честной деградацией (0 применённых
или BROKEN → финал = черновик дословно, как §17).

Сравнения (считает `eval/skills_k3_stats.py`, анализ hc2): revised −
draft (вклад механизма) и revised − curation (компенсирует ли ревизия
отказ от курации).

Сессии правок идут через `opencode run` в репозитории — как ревизионные
сессии §17/§22.1 (уровень L1+ одинаков для сравнений внутри серии;
относительные выводы сохраняют силу, §24.3). Метка прогона —
«О4: t12-hc2-…» через eval/.cost-label (STATE.md не трогается).

Контракт CLI:
    python3 eval/critic_loop_step2.py [--runs-dir DIR] [--k 3] [--dry-run]

Коды возврата: 0 — все цепочки отработали; 1 — ошибка использования;
3 — ключ не в окружении; 4 — хотя бы одна цепочка упала.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
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
run_label = load_module("run_label", REPO_ROOT / "eval" / "run_label.py")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NO_KEY = 3
EXIT_RUN_FAILED = 4

MODEL = run_ab.MODEL  # stepfun/step-5-preview (как ревизионные сессии §17)
RUBRIC_RESEARCH = "eval/rubrics/rubric-research.md"
MAX_PATCH_EDITS = 15

# Промпт точечных правок — адаптация PATCH_REVISION_PROMPT (run_ab.py)
# под research: убраны options-специфичные правила про секции вариантов,
# добавлены правила сохранения структурных секций исследования.
# Предрегистрация §25.3 фиксирует эту адаптацию ДО прогонов.
PATCH_PROMPT = """Ты — тот же агент «Стратег», дорабатываешь свой черновик шага 2
(ИССЛЕДОВАНИЕ) по находкам внутреннего критика. Это ТОЧЕЧНАЯ правка
(targeted patch), а не переписывание: полный артефакт заново не выдаётся.

Верни ТОЛЬКО JSON-блок (в фи ```json или голым JSON) такого вида:

{{"edits": [{{"find": "<дословный фрагмент черновика, 40–800 символов>",
"replace": "<новый текст>", "finding": "<какую находку закрывает>",
"action": "apply|reject", "reason": "<обязательно при reject>"}}]}}

Правила:
- Не переписывай артефакт целиком: каждая правка — замена одного
  фрагмента (find → replace). Допустимы добавления нового текста.
- find копируется из черновика ДОСЛОВНО (символ в символ): иначе правка
  не применится (0 вхождений — not-found, больше одного — ambiguous).
- Не удаляй целиком секции: решающие вопросы, картину ситуации,
  конфликты источников, гипотезы, именованные пробелы.
- Сохрани маркеры [факт]/[гипотеза]/[прогноз]/[допущение].
- Отклонённая находка — action "reject" с явной причиной в reason.
- Не более 15 правок.

=== ЧЕРНОВИК ===
{draft}
=== НАХОДКИ КРИТИКА ===
{findings}
=== КОНЕЦ ===

Верни только JSON-блок ответом в чат. Файлы не пиши.

"""


def run_session(prompt: str, out_dir: Path, name: str, label: str, timeout: int) -> tuple[int, str]:
    """Свежая сессия opencode run с меткой прогона в eval/.cost-label."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.start").write_text(
        datetime.now(timezone.utc).isoformat() + f" model={MODEL}\n", encoding="utf-8"
    )
    run_label.set_run_label(label)
    try:
        proc = subprocess.run(
            ["opencode", "run", "--model", MODEL, *run_ab.chunk_prompt(prompt)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        (out_dir / f"{name}.end").write_text(
            datetime.now(timezone.utc).isoformat() + " TIMEOUT\n", encoding="utf-8"
        )
        return 4, ""
    finally:
        run_label.clear_run_label()
    (out_dir / f"{name}.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / f"{name}.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / f"{name}.end").write_text(
        datetime.now(timezone.utc).isoformat() + f" exit={proc.returncode}\n", encoding="utf-8"
    )
    return proc.returncode, proc.stdout


def parse_patch_json(text: str) -> dict | None:
    return run_ab.parse_patch_json(text)


def run_chain(draft_path: Path, idx: int, runs_dir: Path, timeout: int) -> tuple[bool, str]:
    """Одна цепочка H-C2: критик → правки → apply_revision → финал."""
    suffix = "" if idx == 0 else f"-{idx}"
    draft = draft_path.read_text(encoding="utf-8-sig", errors="replace")
    arm_dir = runs_dir / "hc2" / "revised"
    chain_dir = arm_dir / f"chain{suffix}"
    chain_dir.mkdir(parents=True, exist_ok=True)
    (chain_dir / "draft.md").write_text(draft, encoding="utf-8")

    # 1. Критик (свежая сессия, мандат — типовая рубрика research).
    tag = f"t12-hc2-draft-{idx}-critic"[:36]
    critic_dir = chain_dir / "critic"
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "run_critic.py"),
         "--artifact", str(chain_dir / "draft.md"),
         "--rubric", RUBRIC_RESEARCH, "--mode", "critic",
         "--out", str(critic_dir), "--tag", tag, "--timeout", str(timeout)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout + 60,
    )
    if proc.returncode != 0:
        print(f"hc2#{idx}: критик упал exit={proc.returncode}", file=sys.stderr)
        return False, f"critic exit={proc.returncode}"
    findings = (critic_dir / "critic.out").read_text(encoding="utf-8", errors="replace")
    if not findings.strip():
        print(f"hc2#{idx}: критик вернул пустой выход при exit=0", file=sys.stderr)
        return False, "пустой выход критика"

    # 2. Сессия точечных правок.
    code, patch_reply = run_session(
        PATCH_PROMPT.format(draft=draft, findings=findings),
        chain_dir, "patch", f"О4: t12-hc2-rev-{idx}-patch"[:40], timeout,
    )
    if code != 0 or not patch_reply.strip():
        print(f"hc2#{idx}: сессия правок упала exit={code}", file=sys.stderr)
        return False, f"patch session exit={code}"
    patches = parse_patch_json(patch_reply)
    if patches is None:
        # Честная деградация (как §17): финал = черновик, причина в отчёте.
        (arm_dir / f"final{suffix}.md").write_text(draft, encoding="utf-8")
        (chain_dir / "revision-report.md").write_text(
            "# Отчёт по точечным правкам (H-C2, шаг 2)\n\n"
            "JSON правок из ответа модели разобрать не удалось — применять нечего. "
            "Финальный артефакт = черновик дословно (fallback).\n",
            encoding="utf-8",
        )
        print(f"hc2#{idx}: JSON правок не разобран — fallback к черновику")
        return True, "fallback: json not parsed"

    edits = [e for e in patches.get("edits", []) if isinstance(e, dict)][:MAX_PATCH_EDITS]
    patches["edits"] = edits
    (chain_dir / "patches.json").write_text(
        json.dumps(patches, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    applier = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "apply_revision.py"),
         "--draft", str(chain_dir / "draft.md"),
         "--patches", str(chain_dir / "patches.json"),
         "--out", str(arm_dir / f"final{suffix}.md"),
         "--report", str(chain_dir / "revision-report.md")],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    final_path = arm_dir / f"final{suffix}.md"
    if not final_path.is_file():
        print(f"hc2#{idx}: аппликатор не создал финал (exit={applier.returncode})", file=sys.stderr)
        return False, f"apply_revision exit={applier.returncode}"
    report = (chain_dir / "revision-report.md").read_text(encoding="utf-8", errors="replace")
    summary = next((ln for ln in report.splitlines() if ln.startswith("applied=")), "")
    print(f"hc2#{idx}: {summary or 'готово'}")
    return True, summary


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="critic_loop_step2.py",
        description="H-C2: критик + точечная ревизия на шаге 2 (TASK-hermes-12 §25.3).",
    )
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "eval" / "runs" / "t12-skills"))
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    drafts_dir = runs_dir / "research" / "lean"
    drafts = [drafts_dir / name for name in ("final.md", "final-1.md", "final-2.md")[: args.k]]
    drafts = [d for d in drafts if d.is_file()]

    if args.dry_run:
        for i, d in enumerate(drafts):
            print(f"[dry-run] hc2#{i}: черновик {d}")
        return EXIT_OK
    if not drafts:
        print(f"черновики шага 2 (lean) не найдены в {drafts_dir} — сначала run_skills_k3.py", file=sys.stderr)
        return EXIT_USAGE

    import os

    if not os.environ.get("STEPFUN_API_KEY"):
        print("STEPFUN_API_KEY не в окружении — прогон невозможен", file=sys.stderr)
        return EXIT_NO_KEY

    failures = 0
    manifest = [
        "# H-C2: критик + точечная ревизия на шаге 2 (TASK-hermes-12 §25.3)",
        "",
        f"Старт (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Черновики: {drafts_dir} (рука lean, k={len(drafts)})",
        "Мандат критика — типовая рубрика research (принцип H2).",
        "",
        "| Цепочка | Итог |",
        "|---|---|",
    ]
    for idx, draft_path in enumerate(drafts):
        ok, note = run_chain(draft_path, idx, runs_dir, args.timeout)
        if not ok:
            failures += 1
        manifest.append(f"| hc2#{idx} | {'OK' if ok else 'FAIL'} {note} |")
    manifest.append("")
    manifest.append(f"Финиш (UTC): {datetime.now(timezone.utc).isoformat()}")
    manifest.append(f"Провалов: {failures}")
    (runs_dir / "hc2" / "manifest.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"готово, провалов: {failures}")
    return EXIT_RUN_FAILED if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
