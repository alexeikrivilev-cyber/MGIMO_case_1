#!/usr/bin/env python3
"""run_ab.py — попарный A/B стенд «Стратега» (О4, мультинаправленные замеры).

Протокол: TASK-hermes-4 §3 (BRIEF п.17). Фича × рука × метрика × $/run.
Все руки получают ОДИН замороженный бриф (инлайном) и работают в свежих
сессиях `opencode run`; роли read-only (проверка `git status` после
каждого прогона — в манифест). Учёт $ — через хуки cost-append с меткой
«О4: ab-<task>-<arm>-<n>» в колонке «Шаг» (STATE.md `## шаг` на время
прогона).

Руки (арms) фичи «Варианты» (шаг 3):
  skill        — текущий навык options (базовая рука продукта);
  critic-loop  — skill + внутренний критик (изолированный) + одна
                 ревизия по находкам;
  council-lite — 3 роли (product/devil на step-5-preview, data на
                 step-3.7-flash) по council-design §5 (рычаг O1: 3 роли,
                 один раунд) + синтезатор-сессия (единственный писатель).

Балансировка порядка: порядок рук ротируется между задачами (демо —
как задано, held-out — реверс), чтобы порядок не был спутан с эффектом.

Контракт CLI:
    python3 eval/run_ab.py --task demo-retention|heldout-growth-segment
        --feature options --arms skill,critic-loop,council-lite
        [--out DIR] [--timeout SEC] [--dry-run]

Коды возврата: 0 — все прогоны зелёные; 1 — ошибка использования;
4 — хотя бы один прогон упал (детали в <out>/manifest.md).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_RUN_FAILED = 4

TASKS = {
    "demo-retention": {
        "brief": "project/council/run-2026-11-16-01/frozen-brief.md",
    },
    "heldout-growth-segment": {
        "brief": "eval/tasks/heldout-growth-segment/artifacts/brief.md",
    },
}

STEP_PROMPT = """Ты — агент «Стратег» (папка-агент для руководителя продукта), выполняешь
шаг 3 (ВАРИАНТЫ) рабочего процесса. Работай строго по навыку: открой и
примени `knowledge/skills/options/SKILL.md`.

Вход — замороженный бриф задачи (ДАН НИЖЕ ИНЛАЙНОМ, это единственный
источник основания; файлы проекта не открывай, кроме навыка):

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

Требования к выходу:
- Не менее трёх вариантов с РАЗНЫМИ механизмами + «оставить как есть»
  с ценой бездействия (навык options §2–3).
- У каждого варианта: суть / что требует / экономика / сильные
  возражения (сильнейшее первым) / риски.
- Не-факты помечены [гипотеза]/[прогноз]/[допущение]; каждое
  существенное число несёт основание (ev-N / URL) в той же строке.
- Артефакт — на русском.
- Верни готовый markdown артефакта options.md ОТВЕТОМ В ЧАТ. Файлы не
  пиши, ничего не коммить.
"""

REVISION_PROMPT = """Ты — тот же агент «Стратег», дорабатываешь свой черновик шага 3
(ВАРИАНТЫ) по находкам внутреннего критика. Ниже — твой черновик и
находки критика (рубрика — критерии хакатона).

Правила доработки:
- Прими находку, если она по существу (исправь текст); отклони —
  только с явной причиной в блоке «Ответ на находки критика».
- Не «подгоняй» оценки: цель — усилить артефакт, а не понравиться
  критику. Сохрани маркеры [факт]/[гипотеза]/[прогноз]/[допущение].
- Не ослабляй возражения и не увеличивай число вариантов ради
  разнообразия.

=== ЧЕРНОВИК ===
{draft}
=== НАХОДКИ КРИТИКА ===
{findings}
=== КОНЕЦ ===

Верни доработанный markdown артефакта options.md ОТВЕТОМ В ЧАТ. Файлы
не пиши.
"""

ROLE_PROMPT = """Ты — экспертная линза «{role}» в Консилиуме агента «Стратег» (протокол
 council-design §4 Phase 1, одна фаза — независимая дивергенция).
Других линз ты не видишь и не должен предполагать их позиции.

Твоя линза: {lens}

Вход — замороженный бриф задачи (инлайном):

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

Задача: предложи 2–4 варианта решения с позиции своей линзы. Для
каждого — суть, механизм воздействия, сильнейшее возражение к нему
(по существу, с основаниями из брифа), риски. Не-факты помечай
[гипотеза]/[прогноз]. Каждое существенное число — с основанием
(ev-N / URL) в той же строке. Язык — русский.

Верни ответ markdown-ом В ЧАТ. Файлы не пиши.
"""

SYNTH_PROMPT = """Ты — синтезатор Консилиума агента «Стратег» (единственный писатель
итогового набора вариантов, протокол council-design §4 Phase 4).

Вход — замороженный бриф и выходы трёх линз (product, devil, data),
каждая независима:

=== ЗАМОРОЖЕННЫЙ БРИФ ===
{brief}
=== КОНЕЦ БРИФА ===

{roles}

Требования к синтезу:
- Итоговый набор: содержательно разные варианты (разные механизмы) +
  «оставить как есть» с ценой бездействия. Объединяй только с явной
  пометкой provenance (какая линза — источник).
- Сохрани разногласия отдельным разделом (какая линза против чего и
  почему) — несогласие ценнее согласия.
- У каждого варианта: суть / что требует / экономика / сильные
  возражения (сильнейшее первым) / риски. Маркеры [факт]/[гипотеза]/
  [прогноз]/[допущение]. Каждое существенное число — с основанием
  (ev-N / URL) в той же строке. Язык — русский.
- Верни готовый markdown артефакта options.md ОТВЕТОМ В ЧАТ. Файлы не
  пиши.
"""

ROLES = {
    "product": (
        "продуктовая экономика: jobs аудитории ↔ стоимость ↔ доход; "
        "что мешает и что усиливает удержание/рост с продуктовой стороны"
    ),
    "devil": (
        "адвокат дьявола: ищи сильнейшие возражения против каждого "
        "очевидного варианта, вторые порядки, regrettable-сценарии"
    ),
    "data": (
        "данные и доказательства: что измерено в брифе, какие связи "
        "причинны, а какие — ассоциации/артефакты; где пробелы данных"
    ),
}

ROLE_MODEL = {
    "product": "stepfun/step-5-preview",
    "devil": "stepfun/step-5-preview",
    "data": "stepfun/step-3.7-flash",
}

MODEL = "stepfun/step-5-preview"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_state_step(label: str) -> str | None:
    state = REPO_ROOT / "STATE.md"
    try:
        text = state.read_text(encoding="utf-8")
    except OSError:
        return None
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
    match = re.search(r"(##\s*шаг\s*\n\n)([^\n#]*(?:\n(?![#\n])[^\n#]*)*)", text)
    if not match:
        return
    patched = text[: match.start(2)] + previous + text[match.end(2) :]
    try:
        state.write_text(patched, encoding="utf-8")
    except OSError:
        pass


def run_session(prompt: str, out_dir: Path, name: str, model: str, timeout: int) -> tuple[int, str]:
    """Свежая сессия opencode run; выход — в <out_dir>/<name>.out."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.start").write_text(
        datetime.now(timezone.utc).isoformat() + f" model={model}\n", encoding="utf-8"
    )
    previous = set_state_step(f"О4: ab-{name}")
    try:
        proc = subprocess.run(
            ["opencode", "run", "--model", model, prompt],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        (out_dir / f"{name}.end").write_text(
            datetime.now(timezone.utc).isoformat() + " TIMEOUT\n", encoding="utf-8"
        )
        return EXIT_RUN_FAILED, ""
    finally:
        restore_state_step(previous)
    (out_dir / f"{name}.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / f"{name}.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / f"{name}.end").write_text(
        datetime.now(timezone.utc).isoformat() + f" exit={proc.returncode}\n",
        encoding="utf-8",
    )
    return proc.returncode, proc.stdout


def git_status_clean() -> str:
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    lines = [
        line
        for line in proc.stdout.splitlines()
        if "eval/runs/" not in line and "COST.md" not in line and "STATE.md" not in line
    ]
    return "чисто" if not lines else "; ".join(lines[:5])


def run_arm_skill(brief: str, arm_dir: Path, timeout: int) -> int:
    code, out = run_session(
        STEP_PROMPT.format(brief=brief), arm_dir, "session", MODEL, timeout
    )
    (arm_dir / "final.md").write_text(out, encoding="utf-8")
    return code


def run_arm_critic_loop(brief: str, arm_dir: Path, timeout: int) -> int:
    code, draft = run_session(
        STEP_PROMPT.format(brief=brief), arm_dir, "session1", MODEL, timeout
    )
    if code != 0:
        return code
    (arm_dir / "draft.md").write_text(draft, encoding="utf-8")
    critic_dir = arm_dir / "critic"
    code = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_critic.py"),
            "--artifact", str(arm_dir / "draft.md"),
            "--rubric", "eval/rubrics/hackathon-criteria.md",
            "--mode", "critic",
            "--out", str(critic_dir),
            "--tag", f"ab-critic-{arm_dir.parent.name}-{arm_dir.name}",
            "--timeout", str(timeout),
        ],
        cwd=REPO_ROOT,
    ).returncode
    if code != 0:
        return code
    findings = (critic_dir / "critic.out").read_text(encoding="utf-8", errors="replace")
    (arm_dir / "findings.md").write_text(findings, encoding="utf-8")
    code, final = run_session(
        REVISION_PROMPT.format(draft=draft, findings=findings),
        arm_dir,
        "session2",
        MODEL,
        timeout,
    )
    if code != 0:
        return code
    (arm_dir / "final.md").write_text(final, encoding="utf-8")
    return 0


def run_arm_council_lite(brief: str, arm_dir: Path, timeout: int) -> int:
    role_outputs: dict[str, str] = {}
    for role, lens in ROLES.items():
        code, out = run_session(
            ROLE_PROMPT.format(role=role, lens=lens, brief=brief),
            arm_dir,
            f"role-{role}",
            ROLE_MODEL[role],
            timeout,
        )
        if code != 0:
            return code
        role_outputs[role] = out
    roles_block = "\n\n".join(
        f"=== ЛИНЗА {role.upper()} ===\n{text}" for role, text in role_outputs.items()
    )
    code, final = run_session(
        SYNTH_PROMPT.format(brief=brief, roles=roles_block),
        arm_dir,
        "synthesizer",
        MODEL,
        timeout,
    )
    if code != 0:
        return code
    (arm_dir / "final.md").write_text(final, encoding="utf-8")
    return 0


ARMS = {
    "skill": run_arm_skill,
    "critic-loop": run_arm_critic_loop,
    "council-lite": run_arm_council_lite,
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_ab.py")
    parser.add_argument("--task", required=True, choices=sorted(TASKS))
    parser.add_argument("--feature", required=True, help="например: options")
    parser.add_argument("--arms", required=True, help="список рук через запятую")
    parser.add_argument("--out", default=None)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="реверс порядка рук (балансировка между задачами)",
    )
    args = parser.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        print(f"неизвестные руки: {unknown}; доступно: {sorted(ARMS)}", file=sys.stderr)
        return EXIT_USAGE
    if args.reverse:
        arms = list(reversed(arms))

    task = TASKS[args.task]
    brief_path = REPO_ROOT / task["brief"]
    if not brief_path.is_file():
        print(f"бриф не найден: {brief_path}", file=sys.stderr)
        return EXIT_USAGE
    brief = brief_path.read_text(encoding="utf-8-sig", errors="replace")
    brief_hash = sha256_file(brief_path)

    out_dir = Path(args.out) if args.out else REPO_ROOT / "eval" / "runs" / f"ab-{args.feature}-{args.task}"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = [
        f"# A/B прогон — фича {args.feature}, задача {args.task} (О4)",
        "",
        f"Старт (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Бриф: `{task['brief']}` (sha256 `{brief_hash[:16]}…`, {len(brief)} Б)",
        f"Порядок рук: {' → '.join(arms)}"
        + (" (реверс — балансировка)" if args.reverse else ""),
        "",
        "| Рука | Сессии | git status после | Итог |",
        "|---|---|---|---|",
    ]

    failures = 0
    for arm in arms:
        arm_dir = out_dir / arm
        arm_dir.mkdir(parents=True, exist_ok=True)
        if args.dry_run:
            print(f"[dry-run] {arm} -> {arm_dir}")
            continue
        sessions = {
            "skill": 1,
            "critic-loop": 3,  # черновик + критик + ревизия
            "council-lite": 4,  # 3 роли + синтез
        }[arm]
        code = ARMS[arm](brief, arm_dir, args.timeout)
        failures += 1 if code != 0 else 0
        manifest.append(
            f"| {arm} | {sessions} | {git_status_clean()} "
            f"| {'OK' if code == 0 else 'FAIL exit=' + str(code)} |"
        )
        (out_dir / "manifest.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
        print(f"arm {arm}: exit={code}")

    if args.dry_run:
        return EXIT_OK
    manifest.append("")
    manifest.append(f"Финиш (UTC): {datetime.now(timezone.utc).isoformat()}")
    manifest.append(f"Провалов: {failures}")
    (out_dir / "manifest.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"готово, провалов: {failures}, манифест: {out_dir / 'manifest.md'}")
    return EXIT_RUN_FAILED if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
