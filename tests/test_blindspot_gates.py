"""Юнит-тесты гейтов слепых зон рубрики (TASK-hermes-16 §30.1):
scripts/check_complexity.py (избыточная сложность набора вариантов),
scripts/check_actionability.py (управляемость / готовность к действию),
scripts/check_ranges.py (обоснованность диапазонов).

Шов под тестом — CLI целиком (субпроцесс, временные файлы): коды
возврата и тексты нарушений. НегативныеControls обязательны: гейт,
который не ловит нарушение на синтетике, на артефактах бесполезен.
Тест на ПОРОГ («5 вариантов проходят, 6 — нет») фиксирует границу,
установленную по вердикту человека (BRIEF п.27, пара 5).

Запуск: python3 -m unittest tests.test_blindspot_gates -v
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPLEXITY = REPO_ROOT / "scripts" / "check_complexity.py"
ACTIONABILITY = REPO_ROOT / "scripts" / "check_actionability.py"
RANGES = REPO_ROOT / "scripts" / "check_ranges.py"


def run_gate(script: Path, text: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "artifact.md"
        path.write_text(text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(script), str(path)],
            capture_output=True, text=True, timeout=120)


def variant(title: str) -> str:
    return (f"## Вариант {title}\n\nСуть варианта {title}. "
            f"Возражение: сильное [гипотеза]. Экономика: перераспределение.\n")


TABLE = ("| Критерий | A | B |\n|---|---|---|\n"
         "| Эффект | высокий | средний |\n| Срок | квартал | месяц |\n"
         "| Стоимость | ~0 | ~0 |\n")


class TestComplexity(unittest.TestCase):
    def test_four_variants_with_table_pass(self):
        text = ("# options.md\n\n" + variant("1") + variant("2")
                + variant("3") + variant("4 — «Оставить как есть»")
                + "\n## Таблица сравнения\n\n" + TABLE)
        proc = run_gate(COMPLEXITY, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_six_variants_flagged(self):
        text = ("# options.md\n\n"
                + "".join(variant(str(i)) for i in range(1, 6))
                + variant("6 — «Оставить как есть»")
                + "\n## Таблица сравнения\n\n" + TABLE)
        proc = run_gate(COMPLEXITY, text)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("вариантов 6 > 5", proc.stderr)

    def test_five_variants_pass_threshold(self):
        text = ("# options.md\n\n"
                + "".join(variant(str(i)) for i in range(1, 5))
                + variant("5 — «Оставить как есть»")
                + "\n## Таблица сравнения\n\n" + TABLE)
        proc = run_gate(COMPLEXITY, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_status_quo_flagged(self):
        text = ("# options.md\n\n" + variant("1") + variant("2") + variant("3")
                + "\n## Таблица сравнения\n\n" + TABLE)
        proc = run_gate(COMPLEXITY, text)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("оставить как есть", proc.stderr)

    def test_missing_table_flagged(self):
        text = "# options.md\n\n" + variant("1 — «Оставить как есть»") + variant("2") + variant("3")
        proc = run_gate(COMPLEXITY, text)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("единой таблицы", proc.stderr)

    def test_non_options_artifact_named_skip(self):
        text = "# research.md\n\nИсследование без вариантов: только анализ [гипотеза].\n"
        proc = run_gate(COMPLEXITY, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("пропуск", proc.stdout)

    def test_usage_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "nope.md")
            proc = subprocess.run([sys.executable, str(COMPLEXITY), missing],
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 1)
        proc = subprocess.run([sys.executable, str(COMPLEXITY)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1)


class TestActionability(unittest.TestCase):
    PLAN_OK = ("# Стратегия\n\nПриоритеты инициатив: P0, P1, P2.\n"
               "Последовательность: P0 раньше всех.\n"
               "Пилот с контрольной группой и A/B внутри тира.\n"
               "Метрики успеха замеряются недельно.\n"
               "Критерии остановки: порог «не работает».\n")

    def test_full_plan_pass(self):
        proc = run_gate(ACTIONABILITY, self.PLAN_OK)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_control_group_flagged(self):
        text = self.PLAN_OK.replace("Пилот с контрольной группой и A/B внутри тира.", "Пилот на когорте.")
        proc = run_gate(ACTIONABILITY, text)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("контрольные группы", proc.stderr)

    def test_missing_priorities_flagged(self):
        text = self.PLAN_OK.replace("Приоритеты инициативы: P0, P1, P2.", "Инициативы перечислены ниже.").replace(
            "Приоритеты инициатив: P0, P1, P2.", "Инициативы перечислены ниже.").replace(
            "Последовательность: P0 раньше всех.", "Последовательность: блокер раньше всех.")
        proc = run_gate(ACTIONABILITY, text)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("приоритеты", proc.stderr)

    def test_missing_stop_criteria_flagged(self):
        text = self.PLAN_OK.replace("Критерии остановки: порог «не работает».", "Откат описан.")
        proc = run_gate(ACTIONABILITY, text)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("критерии остановки", proc.stderr)

    def test_usage_errors(self):
        proc = subprocess.run([sys.executable, str(ACTIONABILITY)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1)


class TestRanges(unittest.TestCase):
    def test_grounded_range_pass(self):
        text = "отток когорты 0–3 мес — 56.21% (ev-002)\n"
        proc = run_gate(RANGES, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_estimate_marker_pass(self):
        text = "срок запуска 4–6 недель [оценка, не из источников]\n"
        proc = run_gate(RANGES, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_bare_range_flagged(self):
        text = "| Срок до эффекта | квартал | 4–8 недель |\n"
        proc = run_gate(RANGES, text)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("4–8", proc.stderr)

    def test_marked_but_underived_passes_named_limitation(self):
        # Класс самого человека (пара 6) гейтом НЕ ловится — named
        # limitation: «[прогноз]» без основания проходит механический
        # класс; семантика — только критиком (§30.1).
        text = "ожидаемый сдвиг оттока −5…−15 п.п. [прогноз]\n"
        proc = run_gate(RANGES, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_identifier_ranges_not_matched(self):
        text = "приоритеты P0–P2 и слои L2–L4 не являются диапазонами\n"
        proc = run_gate(RANGES, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_dates_times_years_excluded(self):
        text = ("проверено 2026-11-16 в 10:43; периоды 2008–2010 вне scope; "
                "`ev-001…ev-003` — диапазон записей\n")
        proc = run_gate(RANGES, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_ordinal_and_compound_labels_excluded(self):
        text = "возврат на 2–3-й день; окно 30–60-дневного цикла\n"
        proc = run_gate(RANGES, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_heading_and_fence_and_quote_excluded(self):
        text = ("# Заголовок с диапазоном 1–3\n\n```\nдиапазон 5–10 в коде\n```\n"
                "> цитата с диапазоном 7–9\n")
        proc = run_gate(RANGES, text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_money_range_flagged_when_bare(self):
        text = "экономия $199K–$319K за цикл без пояснений\n"
        proc = run_gate(RANGES, text)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("$199K–$319K", proc.stderr)

    def test_usage_errors(self):
        proc = subprocess.run([sys.executable, str(RANGES)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
