"""Юнит-тесты скриптов-проверок «Стратега» (каталог scripts/).

Шов (seam) под тестом — контракт CLI: аргументы, коды возврата и текст
вывода. Скрипты запускаются отдельными процессами, поэтому тесты видят
ровно то же поведение, что и хук/человек в терминале.

Фикстуры создаются во временной директории (tempfile) — репозиторий
не мусорится. Исключение — тесты «реальный STATE.md / COST.md»: они
проверяют артефакты самого репозитория (критерий приёмки задания).

Запуск: python3 -m unittest tests.test_scripts -v
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

CHECK_SOURCES = "check_sources.py"
CHECK_STATE = "check_state.py"
COST_REPORT = "cost_report.py"

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATION = 2

PLACEHOLDER = "(пока нет)"


def run_script(name: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Запускает скрипт из scripts/ отдельным процессом и возвращает результат."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / name), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
    )


class TempDirTestCase(unittest.TestCase):
    """Базовый кейс с временным каталогом для фикстур."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def write(self, rel_path: str, text: str) -> Path:
        """Пишет файл фикстуры во временном каталоге и возвращает путь."""
        path = self.tmp / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


# --------------------------------------------------------------------------
# 1) check_sources.py — журнал доказательств (project/evidence/*.md)
# --------------------------------------------------------------------------

EVIDENCE_OK = """# ev-001 — удержание падает

## Факт (формулировка)

- Удержание в цифровом сервисе снижается второй квартал подряд.

## Источник

- URL: https://example.com/report-2026
- Дата доступа: 2026-11-16
- Что подтверждает: «retention down 12%»

## Тип

- [x] факт (есть источник)

## Связь с задачей

- Решающий вопрос из brief.md: что драйвит отток
- Как используется в артефакте: основание варианта «программа лояльности»
"""

EVIDENCE_NO_URL = EVIDENCE_OK.replace("- URL: https://example.com/report-2026\n", "")
EVIDENCE_NO_DATE = EVIDENCE_OK.replace("- Дата доступа: 2026-11-16\n", "")
EVIDENCE_NO_TYPE = EVIDENCE_OK.replace("- [x] факт (есть источник)\n", "")
EVIDENCE_BAD_DATE = EVIDENCE_OK.replace("2026-11-16", "2026-13-45")
EVIDENCE_TWO_TYPES = EVIDENCE_OK.replace(
    "- [x] факт (есть источник)\n",
    "- [x] факт (есть источник)\n- [x] прогноз (помечено)\n",
)
EVIDENCE_NO_ACCESS_DATE_LINE = EVIDENCE_OK.replace(
    "- Дата доступа: 2026-11-16\n", "- Дата доступа: YYYY-MM-DD\n"
)


class CheckSourcesEvidenceTests(TempDirTestCase):
    """Правило A: строгий формат записи журнала доказательств."""

    def test_valid_evidence_record_exit_0(self) -> None:
        path = self.write("project/evidence/ev-001-uderzhanie.md", EVIDENCE_OK)
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
        self.assertIn("ok", result.stdout.lower())

    def test_evidence_without_url_exit_2(self) -> None:
        path = self.write("project/evidence/ev-001.md", EVIDENCE_NO_URL)
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn("URL", result.stdout)

    def test_evidence_without_access_date_exit_2(self) -> None:
        path = self.write("project/evidence/ev-001.md", EVIDENCE_NO_DATE)
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn("Дата доступа", result.stdout)

    def test_evidence_with_unfilled_date_exit_2(self) -> None:
        path = self.write("project/evidence/ev-001.md", EVIDENCE_NO_ACCESS_DATE_LINE)
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_evidence_with_impossible_date_exit_2(self) -> None:
        path = self.write("project/evidence/ev-001.md", EVIDENCE_BAD_DATE)
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_evidence_without_type_mark_exit_2(self) -> None:
        path = self.write("project/evidence/ev-001.md", EVIDENCE_NO_TYPE)
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn("тип", result.stdout.lower())

    def test_evidence_with_two_type_marks_exit_2(self) -> None:
        path = self.write("project/evidence/ev-001.md", EVIDENCE_TWO_TYPES)
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)


# --------------------------------------------------------------------------
# 2) check_sources.py — обычные артефакты (project/*.md)
# --------------------------------------------------------------------------


def artifact(*sections: str, title: str = "# Исследование") -> str:
    """Собирает markdown-артефакт из заголовка и секций."""
    return title + "\n\n" + "\n\n".join(sections) + "\n"


class CheckSourcesArtifactTests(TempDirTestCase):
    """Правило B: ссылка в секции и grounding у hard-claim."""

    def test_section_with_evidence_reference_exit_0(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Данные\n- Удержание упало на 12% (ev-3)\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_section_with_url_reference_exit_0(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Анализ рынка\n- Рост 12% зафиксирован: https://example.com/x\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_section_without_reference_and_not_allowlisted_exit_2(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Анализ\n- Текст без ссылок и без цифр.\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn("Анализ", result.stdout)

    def test_allowlisted_section_without_reference_exit_0(self) -> None:
        path = self.write(
            "project/brief.md",
            artifact("## Сводка\n- Коротко и без ссылок.\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_hard_claim_percent_without_grounding_exit_2(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Сводка\n- Выручка выросла на 12%.\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_hard_claim_with_hypothesis_marker_exit_0(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Сводка\n- Выручка выросла на 12% [гипотеза]\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_hard_claim_with_forecast_marker_exit_0(self) -> None:
        path = self.write(
            "project/options.md",
            artifact("## Сводка\n- Выручка упадёт на 12% [прогноз]\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_hard_claim_with_assumption_marker_exit_0(self) -> None:
        path = self.write(
            "project/options.md",
            artifact("## Сводка\n- Рынок 5 млн руб [допущение]\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_hard_claim_with_url_exit_0(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Сводка\n- Отток 30%: https://example.com/churn\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_hard_claim_growth_verb_with_digits_exit_2(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Сводка\n- Выручка выросла на 3 пункта в 2026 квартале.\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_growth_verb_without_digits_is_not_a_claim(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Сводка\n- Выручка выросла после запуска программы.\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_blockquote_with_numbers_excluded_exit_0(self) -> None:
        path = self.write(
            "project/brief.md",
            artifact('## Сводка\n> Запрос РП: «выручка выросла на 12%, рынок 5 млн ₽»\n'),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_code_fence_with_numbers_excluded_exit_0(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Легенда\n```\nвыручка выросла на 12%, рынок 5 млн ₽\n```\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_blockquote_does_not_ground_a_section_exit_2(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Анализ\n> Ссылка в блокцитате: https://example.com/x\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_only_title_file_exit_0(self) -> None:
        path = self.write("project/research.md", "# Исследование\n")
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_violation_reports_file_and_line(self) -> None:
        path = self.write(
            "project/research.md",
            artifact("## Сводка\n- Тут всё спокойно.\n\n## Анализ\n- Выручка 12%.\n"),
        )
        result = run_script(CHECK_SOURCES, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertRegex(result.stdout, r"project/research\.md:\d+: .+")


class CheckSourcesCliTests(TempDirTestCase):
    """Контракт CLI check_sources.py."""

    def test_no_arguments_exit_1(self) -> None:
        result = run_script(CHECK_SOURCES)
        self.assertEqual(result.returncode, EXIT_USAGE)
        self.assertTrue(result.stderr.strip())

    def test_missing_file_exit_1(self) -> None:
        missing = self.tmp / "project" / "no-such-file.md"
        result = run_script(CHECK_SOURCES, str(missing))
        self.assertEqual(result.returncode, EXIT_USAGE)
        self.assertIn(str(missing), result.stderr)

    def test_directory_argument_exit_1(self) -> None:
        (self.tmp / "project").mkdir(parents=True, exist_ok=True)
        result = run_script(CHECK_SOURCES, str(self.tmp / "project"))
        self.assertEqual(result.returncode, EXIT_USAGE)

    def test_several_files_one_dirty_exit_2(self) -> None:
        clean = self.write("project/brief.md", artifact("## Сводка\n- Без ссылок.\n"))
        dirty = self.write(
            "project/research.md",
            artifact("## Сводка\n- Выручка выросла на 12%.\n"),
        )
        result = run_script(CHECK_SOURCES, str(clean), str(dirty))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn(str(dirty) + ":", result.stdout)
        self.assertNotIn(str(clean) + ":", result.stdout)

    def test_relative_path_from_tmp_cwd(self) -> None:
        self.write("project/research.md", artifact("## Анализ\n- Без ссылок.\n"))
        result = run_script(CHECK_SOURCES, "project/research.md", cwd=self.tmp)
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)


# --------------------------------------------------------------------------
# 3) check_state.py — валидность STATE.md
# --------------------------------------------------------------------------

STATE_OK = """# STATE.md — состояние задачи

## objective

Демо-задача `eval/tasks/demo-retention`.

## шаг

Шаг 1 — материалы.

## завершённые шаги

(пока нет)

## решения и причины

(пока нет)

## открытые вопросы

(пока нет)

## обязательства

(пока нет)

## ключевые файлы

- `README.md` — описание репозитория
- `scripts/check_state.py` — этот проверяющий скрипт

## провалившиеся подходы

(пока нет)

## стоимость на сейчас

См. `COST.md`.
"""


class CheckStateTests(TempDirTestCase):
    """Схема STATE.md (PRD §6)."""

    def test_valid_state_exit_0(self) -> None:
        path = self.write("STATE.md", STATE_OK)
        result = run_script(CHECK_STATE, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
        self.assertIn("ok", result.stdout.lower())

    def test_missing_section_exit_2(self) -> None:
        text = STATE_OK.replace("## провалившиеся подходы\n\n" + PLACEHOLDER + "\n\n", "")
        path = self.write("STATE.md", text)
        result = run_script(CHECK_STATE, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn("провалившиеся подходы", result.stdout)

    def test_broken_path_in_key_files_exit_2(self) -> None:
        text = STATE_OK.replace(
            "- `README.md` — описание репозитория\n",
            "- `README.md` — описание репозитория\n- `project/нет-такого.md` — битый путь\n",
        )
        path = self.write("STATE.md", text)
        result = run_script(CHECK_STATE, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn("project/нет-такого.md", result.stdout)

    def test_empty_step_exit_2(self) -> None:
        path = self.write("STATE.md", STATE_OK.replace("Шаг 1 — материалы.", ""))
        result = run_script(CHECK_STATE, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_placeholder_step_exit_2(self) -> None:
        text = STATE_OK.replace("Шаг 1 — материалы.", PLACEHOLDER)
        path = self.write("STATE.md", text)
        result = run_script(CHECK_STATE, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_empty_objective_exit_2(self) -> None:
        text = STATE_OK.replace("Демо-задача `eval/tasks/demo-retention`.", "")
        path = self.write("STATE.md", text)
        result = run_script(CHECK_STATE, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_placeholder_in_open_questions_allowed_exit_0(self) -> None:
        path = self.write("STATE.md", STATE_OK)
        result = run_script(CHECK_STATE, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)

    def test_missing_file_exit_1(self) -> None:
        result = run_script(CHECK_STATE, str(self.tmp / "STATE.md"))
        self.assertEqual(result.returncode, EXIT_USAGE)
        self.assertTrue(result.stderr.strip())

    def test_empty_file_exit_1(self) -> None:
        path = self.write("STATE.md", "   \n\n")
        result = run_script(CHECK_STATE, str(path))
        self.assertEqual(result.returncode, EXIT_USAGE)

    def test_repo_state_file_is_valid(self) -> None:
        """Критерий приёмки: реальный STATE.md репозитория проходит проверку."""
        result = run_script(CHECK_STATE)
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)


# --------------------------------------------------------------------------
# 4) cost_report.py — сводка стоимости из COST.md
# --------------------------------------------------------------------------

COST_FIXTURE = """# COST.md — учёт стоимости

## Контур разработки (dev) — метрика «сколько стоило исследование»

| Дата | Что | Модель | Токены in | Токены out | Оценка $ | Источник данных |
|---|---|---|---|---|---|---|
| 2026-11-16 | День 1: research | Sonnet 5.5 | 4 189 926 | 48 802 | ~8.87 | appendix |

## Контур прода (prod) — метрика $/прогон

| Дата | Прогон (sessionID) | Шаг | Модель | in | out | reasoning | cache read | cache write | поиск | Оценка $ |
|---|---|---|---|---|---|---|---|---|---|---|
<!-- cost-rows:begin -->
| 2026-11-17 | sess-001 | 2 | step-5-preview | 1 000 | 200 | 50 | 10 | 20 | 1 | $1.23 |
| 2026-11-17 | sess-002 | 3 | step-5-preview | — | — | не метрится рантаймном | — | — | 0 | — |
<!-- cost-rows:end -->
"""


class CostReportTests(TempDirTestCase):
    """Сводка по обоим контурам (PRD §7/§13)."""

    def test_totals_for_both_contours(self) -> None:
        path = self.write("COST.md", COST_FIXTURE)
        result = run_script(COST_REPORT, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
        out = result.stdout
        self.assertIn("4 189 926", out)  # dev in
        self.assertIn("48 802", out)  # dev out
        self.assertIn("8.87", out)  # dev $
        self.assertIn("1 000", out)  # prod in
        self.assertIn("1.23", out)  # prod $
        self.assertIn("10.10", out)  # итог 8.87 + 1.23

    def test_counts_of_rows(self) -> None:
        path = self.write("COST.md", COST_FIXTURE)
        result = run_script(COST_REPORT, str(path))
        self.assertIn("строк: 1", result.stdout)  # dev
        self.assertIn("прогонов: 2", result.stdout)  # prod

    def test_unestimable_rows_listed_as_zero(self) -> None:
        path = self.write("COST.md", COST_FIXTURE)
        result = run_script(COST_REPORT, str(path))
        out = result.stdout
        self.assertIn("sess-002", out)
        self.assertIn("неоценим", out.lower())
        self.assertIn("не метрится рантаймном", out)

    def test_empty_prod_table_reports_no_data(self) -> None:
        text = COST_FIXTURE.replace(
            "| 2026-11-17 | sess-001 | 2 | step-5-preview | 1 000 | 200 | 50 | 10 | 20 | 1 | $1.23 |\n",
            "",
        ).replace(
            "| 2026-11-17 | sess-002 | 3 | step-5-preview | — | — | не метрится рантаймном | — | — | 0 | — |\n",
            "",
        )
        path = self.write("COST.md", text)
        result = run_script(COST_REPORT, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
        self.assertIn("нет данных", result.stdout.lower())

    def test_missing_file_exit_1(self) -> None:
        result = run_script(COST_REPORT, str(self.tmp / "COST.md"))
        self.assertEqual(result.returncode, EXIT_USAGE)
        self.assertTrue(result.stderr.strip())

    def test_repo_cost_file_is_reported(self) -> None:
        """Критерий приёмки: сводка по реальному COST.md репозитория.

        Ожидание не завязываем на конкретный итог $: COST.md растёт
        (каждый прогон дописывает строку) — проверяем, что отчёт строится
        и dev-контур со строковой оценкой $ в нём есть.
        """
        result = run_script(COST_REPORT)
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
        self.assertIn("Контур разработки (dev): строк:", result.stdout)
        self.assertRegex(result.stdout, r"оценка \$: \d+\.\d{2}")
        self.assertIn("Итого (dev + prod):", result.stdout)


if __name__ == "__main__":
    unittest.main()
