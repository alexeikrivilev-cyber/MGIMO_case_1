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
CHECK_OPTIONS = "check_options.py"
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


# --------------------------------------------------------------------------
# 5) check_options.py — структура вариантов (R1 варианты, R2 возражения, R3 типы)
# --------------------------------------------------------------------------

OPTIONS_OK = """# Варианты удержания (фикстура)

> Цитата запроса РП — не проверяется.

## Критерии сравнения

- Эффект на удержание
- Стоимость и перераспределение

## Варианты

### Вариант 1: программа лояльности

#### Суть

- Механизм: …
- Основание: ev-1

#### Что требует

- Ресурсы: …

#### Экономика

- Затраты: …
- Эффект: … [прогноз]

#### Сильные возражения

- Сильнейшее возражение: …

#### Риски

- … [гипотеза]

### Вариант 2: первые 90 дней жизни подписчика

#### Суть

- Механизм: …
- Основание: ev-2

#### Что требует

- …

#### Экономика

- … [допущение]

#### Сильные возражения

- Сильнейшее возражение: …

#### Риски

- …

### Вариант 3: оставить как есть

#### Суть

- Механизм: инерция текущих процессов.
- Основание: ev-3

#### Что требует

- Ничего.

#### Экономика

- Затрат нет; что теряем: … [прогноз]

#### Сильные возражения

- Сильнейшее возражение: …

#### Риски

- … [гипотеза]

## Сравнение вариантов

| Критерий | Вариант 1 | Вариант 2 | Вариант 3 (как есть) |
|---|---|---|---|
| Эффект | … | … | … |
"""

OPTIONS_TWO_VARIANTS = OPTIONS_OK[
    : OPTIONS_OK.index("### Вариант 2:")
] + OPTIONS_OK[OPTIONS_OK.index("### Вариант 3:"):]

OPTIONS_NO_STATUS_QUO = OPTIONS_OK.replace(
    "### Вариант 3: оставить как есть",
    "### Вариант 3: сэкономить и не трогать продукт",
)

OPTIONS_NO_OBJECTION = OPTIONS_OK.replace(
    "#### Сильные возражения\n\n- Сильнейшее возражение: …\n\n#### Риски\n\n- …\n\n### Вариант 3:",
    "#### Сильные возражения\n\n- Замечание: …\n\n#### Риски\n\n- …\n\n### Вариант 3:",
)

OPTIONS_NO_MARKER = OPTIONS_OK.replace(
    "#### Экономика\n\n- Затрат нет; что теряем: … [прогноз]",
    "#### Экономика\n\n- Затрат нет; что теряем: …",
).replace(
    "#### Риски\n\n- … [гипотеза]\n\n## Сравнение вариантов",
    "#### Риски\n\n- …\n\n## Сравнение вариантов",
)

OPTIONS_OBJECTION_IN_QUOTE = OPTIONS_OK.replace(
    "#### Сильные возражения\n\n- Сильнейшее возражение: …\n\n#### Риски\n\n- … [гипотеза]\n\n## Сравнение",
    "#### Сильные возражения\n\n> Сильнейшее возражение: …\n\n#### Риски\n\n- … [гипотеза]\n\n## Сравнение",
)


def heading_lineno(text: str, needle: str) -> int:
    """Номер строки, содержащей needle (для адресной проверки вывода)."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return lineno
    raise AssertionError(f"в фикстуре нет строки с «{needle}»")


class CheckOptionsRuleTests(TempDirTestCase):
    """Правила R1–R3: варианты, возражения, маркеры типов."""

    def test_three_variants_with_status_quo_exit_0(self) -> None:
        path = self.write("project/options.md", OPTIONS_OK)
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
        self.assertIn("ok", result.stdout.lower())

    def test_two_variants_exit_2(self) -> None:
        path = self.write("project/options.md", OPTIONS_TWO_VARIANTS)
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn("3", result.stdout)

    def test_missing_status_quo_variant_exit_2(self) -> None:
        path = self.write("project/options.md", OPTIONS_NO_STATUS_QUO)
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn("оставить как есть", result.stdout)

    def test_variant_without_objection_exit_2_addressed(self) -> None:
        path = self.write("project/options.md", OPTIONS_NO_OBJECTION)
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        lineno = heading_lineno(OPTIONS_NO_OBJECTION, "### Вариант 2:")
        self.assertIn(f"{path}:{lineno}: ", result.stdout)
        self.assertIn("возражени", result.stdout)

    def test_variant_without_type_marker_exit_2(self) -> None:
        path = self.write("project/options.md", OPTIONS_NO_MARKER)
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        lineno = heading_lineno(OPTIONS_NO_MARKER, "### Вариант 3:")
        self.assertIn(f"{path}:{lineno}: ", result.stdout)
        self.assertIn("[гипотеза]", result.stdout)

    def test_objection_in_blockquote_does_not_count_exit_2(self) -> None:
        path = self.write("project/options.md", OPTIONS_OBJECTION_IN_QUOTE)
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_no_variant_sections_exit_2(self) -> None:
        path = self.write("project/options.md", "# Варианты\n\n- Ничего не решено.\n")
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)

    def test_template_options_md_is_self_consistent_exit_0(self) -> None:
        """Шаблон templates/options.md сам проходит check_options.py.

        Согласованность шаблона и проверки: если агент скопирует шаблон
        и начнёт заполнять, структура «### Вариант …» уже корректна.
        """
        result = run_script(CHECK_OPTIONS, "templates/options.md")
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)

    def test_clean_and_dirty_files_reported_separately(self) -> None:
        clean = self.write("project/options.md", OPTIONS_OK)
        dirty = self.write("project/options-draft.md", OPTIONS_TWO_VARIANTS)
        result = run_script(CHECK_OPTIONS, str(clean), str(dirty))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn(str(dirty) + ":", result.stdout)
        self.assertNotIn(str(clean) + ":", result.stdout)


class CheckOptionsCliTests(TempDirTestCase):
    """Контракт CLI check_options.py."""

    def test_no_arguments_exit_1(self) -> None:
        result = run_script(CHECK_OPTIONS)
        self.assertEqual(result.returncode, EXIT_USAGE)
        self.assertTrue(result.stderr.strip())

    def test_help_prints_contract_exit_0(self) -> None:
        result = run_script(CHECK_OPTIONS, "--help")
        self.assertEqual(result.returncode, EXIT_OK, result.stdout)
        self.assertIn("check_options.py", result.stdout)
        self.assertIn("R1", result.stdout)

    def test_missing_file_exit_1(self) -> None:
        missing = self.tmp / "project" / "no-such-options.md"
        result = run_script(CHECK_OPTIONS, str(missing))
        self.assertEqual(result.returncode, EXIT_USAGE)
        self.assertIn(str(missing), result.stderr)

    def test_directory_argument_exit_1(self) -> None:
        (self.tmp / "project").mkdir(parents=True, exist_ok=True)
        result = run_script(CHECK_OPTIONS, str(self.tmp / "project"))
        self.assertEqual(result.returncode, EXIT_USAGE)

    def test_relative_path_from_tmp_cwd(self) -> None:
        self.write("project/options.md", OPTIONS_TWO_VARIANTS)
        result = run_script(CHECK_OPTIONS, "project/options.md", cwd=self.tmp)
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertRegex(result.stdout, r"project/options\.md:\d+: .+")

    def test_any_passed_file_is_checked_not_only_options_md(self) -> None:
        """Контракт: проверяется каждый переданный файл, а не только options.md.

        Тихий пропуск файлов по имени превращал бы опечатку в пути в
        «ok: нарушений нет» — поэтому поведение закреплено тестом.
        """
        path = self.write("draft/varianty-chernovik.md", OPTIONS_TWO_VARIANTS)
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn(str(path) + ":", result.stdout)

    def test_non_utf8_file_exit_2(self) -> None:
        path = self.tmp / "project" / "options.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# \xff\xfe options\n")
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn("UTF-8", result.stdout)

    def test_non_options_file_is_checked_exit_2(self) -> None:
        """Контракт: каждый переданный файл проверяется, тихого пропуска нет.

        Скрипт про шаг 3, поэтому пакетный выхват ``project/*.md`` — не его
        сценарий: варианты проверяются вызовом на ``project/options.md``.
        Молчаливый пропуск файлов по имени превращал бы опечатку в пути в
        «ok: нарушений нет» — поэтому он не делается.
        """
        path = self.write(
            "project/brief.md", "# brief.md — рамка\n\n## Сводка\n\n- Без вариантов.\n"
        )
        result = run_script(CHECK_OPTIONS, str(path))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn(str(path) + ":", result.stdout)

    def test_batch_checks_every_passed_file(self) -> None:
        """Пакетный вызов: нарушение находится в каждом переданном файле."""
        dirty = self.write("project/options.md", OPTIONS_TWO_VARIANTS)
        brief = self.write(
            "project/brief.md", "# brief.md — рамка\n\n## Сводка\n\n- Без вариантов.\n"
        )
        result = run_script(CHECK_OPTIONS, str(dirty), str(brief))
        self.assertEqual(result.returncode, EXIT_VIOLATION, result.stdout)
        self.assertIn(str(dirty) + ":", result.stdout)
        self.assertIn(str(brief) + ":", result.stdout)


# --------------------------------------------------------------------------
# 6) Структура артефактов очереди О2: навыки и шаблоны
# --------------------------------------------------------------------------


def read_text(path: Path) -> str:
    """Читает файл как UTF-8 с BOM."""
    return path.read_text(encoding="utf-8-sig")


def frontmatter(path: Path) -> dict[str, str]:
    """Разбирает frontmatter «key: value» из начала файла."""
    lines = read_text(path).splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def headings(path: Path) -> list[str]:
    """Строки-заголовки markdown (обрезанные)."""
    return [line.strip() for line in read_text(path).splitlines() if line.startswith("#")]


class SkillsStructureTests(unittest.TestCase):
    """Навыки knowledge/skills/*/SKILL.md: frontmatter и раздел «Проверка»."""

    NEW_SKILLS = ("options", "strategy-product", "strategy-comms", "verification")

    def skills(self) -> list[Path]:
        """Все навыки репозитория (существующие + новые очереди О2)."""
        return sorted((REPO_ROOT / "knowledge" / "skills").glob("*/SKILL.md"))

    def test_every_skill_has_name_description_and_check_section(self) -> None:
        skills = self.skills()
        self.assertTrue(skills, "не найдено навыков knowledge/skills/*/SKILL.md")
        for path in skills:
            fields = frontmatter(path)
            self.assertIn("name", fields, f"{path}: нет frontmatter name")
            self.assertIn("description", fields, f"{path}: нет frontmatter description")
            self.assertTrue(fields["description"], f"{path}: пустое описание")
            self.assertEqual(
                fields["name"], path.parent.name, f"{path}: name ≠ каталогу"
            )
            self.assertIn("## Проверка", headings(path), f"{path}: нет раздела «Проверка»")
            self.assertTrue(
                any(item.startswith("## Анти-паттерны") for item in headings(path)),
                f"{path}: нет раздела «Анти-паттерны»",
            )

    def test_new_o2_skills_exist(self) -> None:
        for name in self.NEW_SKILLS:
            path = REPO_ROOT / "knowledge" / "skills" / name / "SKILL.md"
            self.assertTrue(path.is_file(), f"нет навыка {name}: {path}")

    def test_evidence_skill_has_step2_section(self) -> None:
        """О2: навык evidence дополнен разделом шага 2 (append-only)."""
        path = REPO_ROOT / "knowledge" / "skills" / "evidence" / "SKILL.md"
        self.assertIn("Шаг 2", read_text(path))
        self.assertIn("2026-11-16", read_text(path))


class TemplatesStructureTests(unittest.TestCase):
    """Шаблоны templates/*.md: непустой файл с шапкой-блокцитатой."""

    NEW_TEMPLATES = (
        "research.md",
        "options.md",
        "strategy-product.md",
        "strategy-comms.md",
        "verification-plan.md",
    )

    def test_every_template_has_header_quote(self) -> None:
        templates = sorted((REPO_ROOT / "templates").glob("*.md"))
        self.assertTrue(templates, "не найдено шаблонов templates/*.md")
        for path in templates:
            text = read_text(path)
            self.assertTrue(text.strip(), f"{path}: пустой файл")
            self.assertTrue(
                any(line.startswith(">") for line in text.splitlines()),
                f"{path}: нет шапки «> …»",
            )

    def test_new_o2_templates_exist(self) -> None:
        for name in self.NEW_TEMPLATES:
            path = REPO_ROOT / "templates" / name
            self.assertTrue(path.is_file(), f"нет шаблона {name}: {path}")


if __name__ == "__main__":
    unittest.main()