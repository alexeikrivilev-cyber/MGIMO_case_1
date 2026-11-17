#!/usr/bin/env python3
"""revise_step45_gates.py — ревизия артефактов шагов 4–5 по находкам
ГЕЙТОВ через механизм ревизии продукта (TASK-hermes-20).

Дефект области действия (найден повторным проходом проверки сдачи
2026-11-17 ночью): гейты check_acceptance / check_actionability
применялись только к strategy-product.md, поэтому strategy-comms,
verification-plan и decisions дошли до сдачи без секции «Приёмный
чек-лист» и без структурных признаков плана (приоритеты P0–P2,
последовательность, контрольные группы, KPI, критерии остановки) —
ровно тот класс «не доведён до плана исполнения», которого не хватало
человеку в парах 1 и 4 (вердикт владельца, BRIEF п.27).

Этот драйвер доводит артефакты до зелёных гейтов РЕАЛЬНЫМ содержанием
(не подгонкой под гейт) через механизм продукта:
    patch-сессия (модель возвращает JSON точечных правок find→replace)
    → scripts/apply_revision.py (детерминированное применение +
      проверки целостности: заголовки, «оставить как есть», размер)
    → перепрогон гейтов этапа (состав — из run_full_case.gates_for_artifact,
      уже включающий acceptance/actionability на весь этап после фикса
      области действия).
Идемпотентность: зелёный артефакт не пересессится. Честная деградация:
правки не применились (integrity=BROKEN / 0 applied) → финал =
черновик дословно, артефакт не теряется.

Журнал — manifest.md каталога прогона (как у run_full_case): сессии,
правки, отчёты apply_revision, коды гейтов по раундам, sha256 до/после.

Контракт CLI:
    python3 eval/revise_step45_gates.py --artifacts-dir DIR
        [--names a.md,b.md] [--rounds N] [--timeout SEC] [--dry-run]

Коды возврата: 0 — все артефакты зелёные; 1 — ошибка использования;
4 — провал ревизии (детали в manifest.md).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

import run_full_case as RFC  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_RUN_FAILED = 4

MAX_ROUNDS = 3
LABEL = "t20-gate-rev"

# Промпт точечной ревизии по находкам ГЕЙТОВ (контракт правок — тот же,
# что у PATCH_REVISION_PROMPT run_full_case: name/draft/findings/max_edits).
GATE_PATCH_PROMPT = """Ты — тот же агент «Стратег», дорабатываешь свой
артефакт «{name}» по находкам АВТОМАТИЧЕСКИХ ГЕЙТОВ приёмки
(механические проверки «готовности к действию» — решение владельца,
BRIEF п.27: артефакт шага 4–5 обязан доводить решение до плана
исполнения; пары 1 и 4 человек отдал чату именно за это).

Ниже — текущий артефакт и вывод гейтов. Это ТОЧЕЧНАЯ правка
(targeted patch), а не переписывание: полный артефакт заново не
выдаётся.

Верни ТОЛЬКО JSON-блок (в фи ```json или голым JSON) такого вида:

{{"edits": [{{"find": "<дословный фрагмент черновика, 40–800 символов>",
"replace": "<новый текст>", "finding": "<какую находку закрывает>",
"action": "apply|reject", "reason": "<обязательно при reject>"}}]}}

Правила:
- Находки гейтов механические: чаще всего структурный элемент плана
  отсутствует, либо спрятан в код-фенс (гейты исключают фенсы и
  блокцитаты из анализа — артефакт внутри ```markdown для них
  невидим), либо число потеряло основание в строке.
- Доведи артефакт до плана РЕАЛЬНЫМ содержанием, НЕ подгонкой под гейт:
  * приоритеты P0–P2 с последовательностью и обоснованием порядка —
    по сути ЭТОГО артефакта (что идёт первым, что блокирует что);
  * контрольные группы / A-B: пилот против контрольной группы
    (holdout) — как в этом артефакте уже описано, назови структурно;
  * KPI с порогами — бери из verification-plan.md по ссылке, НЕ
    выдумывай новые числа;
  * критерии остановки — по сути артефакта (зоны «не работает»,
    правило опровержения);
  * секция «Приёмный чек-лист (6 вопросов владельца)» с ответами по
    СУТИ ЭТОГО артефакта: что знаем / чего не знаем; какие решения;
    что проверять первым и почему; деньги / команды / сроки; метрики
    успеха; когда остановить.
- Не удаляй и не ослабляй возражения, пробелы, числа и маркеры
  [факт]/[гипотеза]/[прогноз]/[допущение]; каждое новое число — с
  основанием в той же строке (ev-N / ссылка на артефакт пакета).
- НЕ переименовывай и НЕ удаляй существующие заголовки: гейт
  целостности требует сохранения ВСЕХ заголовков черновика, и правка,
  которая переименовывает раздел, откатывается целиком (integrity=
  BROKEN → финал = черновик, живой прогон TASK-hermes-20: три раунда
  verification-plan ушли именно на это). Новую секцию добавляй
  ОТДЕЛЬНЫМ заголовком рядом — прежний заголовок остаётся на месте,
  текст внутри него может быть дополнен.
- Если артефакт обёрнут в код-фенс или несёт повествовательную
  преамбулу вне содержания — сними ограду: гейты анализируют только
  чистый markdown.
- Не цитируй вывод гейтов дословно в теле артефакта (номера строк и
  диапазоны сами попадают под ranges-гейт).
- Не более {max_edits} правок.

=== АРТЕФАКТ ===
{draft}
=== ВЫВОД ГЕЙТОВ ===
{findings}
=== КОНЕЦ ===

Верни только JSON-блок ответом в чат. Файлы не пиши."""


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def run_gates(name: str, artifacts: Path, task: dict, work_dir: Path,
              tag: str) -> list[tuple[str, str]]:
    """Прогон гейтов этапа для артефакта; список провалов (имя, вывод)."""
    failures: list[tuple[str, str]] = []
    for gate_name, argv in RFC.gates_for_artifact(name, artifacts, task):
        code, output = RFC.run_gate(argv, work_dir / "gates",
                                    f"{tag}-{gate_name}")
        if code != 0:
            failures.append((gate_name, output))
    return failures


def revise_artifact(name: str, artifacts: Path, task: dict, work_dir: Path,
                    timeout: int, manifest: list, rounds: int) -> bool:
    """Ревизия одного артефакта до зелёных гейтов (идемпотентно)."""
    artifact = artifacts / name
    if not artifact.is_file():
        manifest.append(f"- {name}: ОТСУТСТВУЕТ — ревизии не подлежит")
        return False
    before = sha256_of(artifact)
    manifest.append(f"- {name}: старт sha256={before}, "
                    f"{len(artifact.read_text(encoding='utf-8'))} символов")

    failures = run_gates(name, artifacts, task, work_dir, "pre")
    if not failures:
        manifest.append(f"- {name}: уже зелёный — сессия не запускалась")
        print(f"[{name}] уже зелёный", flush=True)
        return True
    manifest.append(f"- {name}: провал гейтов ДО ревизии: "
                    f"{[n for n, _ in failures]}")

    for round_no in range(1, rounds + 1):
        joined = "\n\n".join(f"--- {n} (exit≠0) ---\n{o.strip()[:1500]}"
                             for n, o in failures)
        ok = RFC.patch_revision(artifact, joined, work_dir, name, timeout,
                                LABEL, manifest,
                                prompt_template=GATE_PATCH_PROMPT)
        if not ok:
            manifest.append(f"- {name}: раунд {round_no} — правки не "
                            f"применились, финал = черновик (честная "
                            f"деградация)")
            print(f"[{name}] раунд {round_no}: правки не применились",
                  flush=True)
            return False
        failures = run_gates(name, artifacts, task, work_dir,
                             f"r{round_no}")
        if not failures:
            after = sha256_of(artifact)
            manifest.append(f"- {name}: гейты зелёные (раунд {round_no}), "
                            f"sha256={after}")
            print(f"[{name}] гейты зелёные (раунд {round_no})", flush=True)
            return True
        manifest.append(f"- {name}: раунд {round_no} — всё ещё провал: "
                        f"{[n for n, _ in failures]} → следующий раунд")
        print(f"[{name}] раунд {round_no}: провал "
              f"{[n for n, _ in failures]}", flush=True)

    manifest.append(f"- {name}: ИТОГ — гейты не зелёные за {rounds} "
                    f"раундов: {[n for n, _ in failures]}")
    return False


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="revise_step45_gates.py",
        description="Ревизия артефактов шагов 4–5 по находкам гейтов "
                    "через механизм продукта (TASK-hermes-20).")
    parser.add_argument("--artifacts-dir", required=True,
                        help="каталог артефактов прогона")
    parser.add_argument("--names", default=None,
                        help="имена через запятую (default: три артефакта "
                             "с дефектом — comms, verification, decisions)")
    parser.add_argument("--task", default="demo-retention",
                        choices=sorted(RFC.TASKS))
    parser.add_argument("--rounds", type=int, default=MAX_ROUNDS)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--out-dir", default=None,
                        help="каталог журнала (default: <runs-dir>)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    artifacts = Path(args.artifacts_dir)
    names = (args.names.split(",") if args.names
             else ["strategy-comms.md", "verification-plan.md",
                   "decisions.md"])
    for name in names:
        if name not in RFC.STEP45_ARTIFACTS:
            print(f"имя вне этапа 4–5: {name}", file=sys.stderr)
            return EXIT_USAGE
    out_dir = (Path(args.out_dir) if args.out_dir else artifacts.parent)
    task = RFC.TASKS[args.task]

    if args.dry_run:
        print(f"artifacts-dir={artifacts} names={names} "
              f"rounds={args.rounds} out-dir={out_dir}")
        for name in names:
            gates = [g for g, _ in RFC.gates_for_artifact(name, artifacts,
                                                          task)]
            print(f"  {name}: гейты {gates}")
        print("механизм: patch-сессия → apply_revision.py (integrity) → "
              "перепрогон гейтов; журнал — manifest.md")
        return EXIT_OK

    manifest: list[str] = [
        "# Ревизия артефактов шагов 4–5 по находкам гейтов "
        "(TASK-hermes-20)",
        "",
        f"- старт: {datetime.now(timezone.utc).isoformat()}",
        f"- артефакты: {artifacts}",
        f"- имена: {names}",
        f"- механизм: patch-сессия + apply_revision.py (integrity-гейт) "
        f"+ перепрогон гейтов этапа; раундов до {args.rounds}",
        f"- причина: дефект области действия — гейты acceptance/"
        f"actionability винтили только на strategy-product.md; "
        f"comms/verification/decisions дошли до сдачи без секции "
        f"приёмного чек-листа и структурных признаков плана "
        f"(вердикт владельца, BRIEF п.27)",
        "",
    ]
    print(f"== ревизия {names} → {artifacts}", flush=True)

    ok = True
    for name in names:
        if not revise_artifact(name, artifacts, task, out_dir,
                               args.timeout, manifest, args.rounds):
            ok = False

    manifest.append("")
    manifest.append(f"- ИТОГ: {'все артефакты зелёные' if ok else 'ЕСТЬ ПРОВАЛЫ'}")
    (out_dir / "manifest.md").write_text("\n".join(manifest) + "\n",
                                        encoding="utf-8")
    print(f"== итог: {'зелено' if ok else 'ПРОВАЛЫ'}", flush=True)
    return EXIT_OK if ok else EXIT_RUN_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
