"""Юнит-тесты драйвера TASK-hermes-17 (§31.1, H-A1).

`eval/blindspot_axis.py` — замер «пункты слепых зон отдельной осью vs
без»: парсер двух осей выхода критика версии 2 (база /40 — итоговый
балл; ось /30 — диагностика; общего /70 в контракте нет), правило
направления, правило вердикта по предрегистрации §31.1 (форма §30.2),
неизменность базового условия против TASK-16 (анти-круг).

Регресс на закоммиченный `eval/runs/t17-axis/summary.json` фиксирует
вердикт предрегистрации как факт (как test_task16 для §30.2).

Запуск: python3 -m unittest tests.test_task17 -v
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AXIS = load_module("blindspot_axis_test", REPO_ROOT / "eval" / "blindspot_axis.py")
ADD = load_module("blindspot_addendum_test_t17", REPO_ROOT / "eval" / "blindspot_addendum.py")

RUNS = REPO_ROOT / "eval" / "runs" / "t17-axis"


class TestAxesParser(unittest.TestCase):
    """Парсер контракта версии 2: база /40 (балл) + ось /30 (отчёт)."""

    def test_format_explicit_subtotals(self):
        text = ("| 1. Проработанность | 5/5 | 4/5 | 8/10 |\n"
                "Итого (база, критерии 1–4): 22 /40\n"
                "Итого (ось слепых зон 5.1–5.3): 24 /30\n")
        parsed = AXIS.parse_axes(text)
        self.assertEqual((parsed["base40"], parsed["axis30"]), (22.0, 24.0))
        self.assertFalse(parsed["partial"])

    def test_format_axis_from_items_when_line_missing(self):
        # Метрика оси — сумма пунктов, если строка оси не распознана.
        text = ("| 5.1 Управляемость | 4/5 | 3/5 | 7/10 |\n"
                "| 5.2 Управляемая сложность | 5/5 | 4/5 | 9/10 |\n"
                "| 5.3 Обоснованность диапазонов | 4/5 | 4/5 | 8/10 |\n"
                "Итого (база, критерии 1–4): 20 /40\n")
        parsed = AXIS.parse_axes(text)
        self.assertEqual(parsed["base40"], 20.0)
        self.assertEqual(parsed["axis30"], 24.0)
        self.assertEqual(parsed["items"], {"5.1": 7.0, "5.2": 9.0, "5.3": 8.0})

    def test_format_base_as_table_row(self):
        # Живой формат (класс §12.1): итог базы — строка таблицы.
        text = ("| 1. Проработанность | 5/5 | 4/5 | 8/10 |\n"
                "| **Итого** | | | **16/40** |\n"
                "Итого (ось слепых зон 5.1–5.3): 18 /30\n")
        parsed = AXIS.parse_axes(text)
        self.assertEqual(parsed["base40"], 16.0)
        self.assertEqual(parsed["axis30"], 18.0)

    def test_stray_flat_total_ignored(self):
        # Модель может выпустить /70 по привычке плоского дизайна —
        # контракт версии 2 его не просит; парсинг осей не ломается.
        text = ("Итого (база, критерии 1–4): 20 /40\n"
                "Итого (ось слепых зон 5.1–5.3): 24 /30\n"
                "Итого: 44 /70\n")
        parsed = AXIS.parse_axes(text)
        self.assertEqual((parsed["base40"], parsed["axis30"]), (20.0, 24.0))

    def test_missing_base_is_unrecognized(self):
        # Нет строки базы → клетка не сравнима (итоговый балл — база).
        text = "Итого (ось слепых зон 5.1–5.3): 24 /30\n"
        parsed = AXIS.parse_axes(text)
        self.assertIsNone(parsed["base40"])

    def test_partial_assessment_excluded(self):
        # Частичная оценка («по оценимым») — клетка не сравнима (§26.4):
        # обе оси обнуляются, клетка требует добора.
        text = ("Итого (база, критерии 1–4): **23/30** по оценимым — из 40.\n"
                "Итого (ось слепых зон 5.1–5.3): **22/30**.\n")
        parsed = AXIS.parse_axes(text)
        self.assertTrue(parsed["partial"])
        self.assertIsNone(parsed["base40"])
        self.assertIsNone(parsed["axis30"])

    def test_model_normalized_partial_not_counted(self):
        # Живой формат lean#0 (проход 1): «58/70 по применимым
        # подпунктам → 33/40 (нормировано)». Нормализация — решение
        # модели, не протокол: «по применимым» = частичная оценка,
        # число 33/40 в сравнение не идёт (§26.4).
        text = ("Итого (база, критерии 1–4): **58/70 по применимым "
                "подпунктам → 33/40** (нормировано).\n"
                "Итого (ось слепых зон 5.1–5.3): **24/30**.\n")
        parsed = AXIS.parse_axes(text)
        self.assertTrue(parsed["partial"])
        self.assertIsNone(parsed["base40"])
        self.assertIsNone(parsed["axis30"])

    def test_partial_marker_in_findings_is_not_partial_total(self):
        # Живой FP (curation#0, добор): в находках критик пишет
        # «критерий 3 не оценим из артефакта» — комментарий про
        # критерий, НЕ частичный тотал. Частичность — свойство строки
        # итога; клетка с полным «16/40» остаётся сравнимой.
        text = ("Итого (база, критерии 1–4): **16/40** (проход 2); "
                "24/40 (проход 1). Расхождений >1 балла между "
                "проходами нет.\n"
                "Итого (ось слепых зон 5.1–5.3): **22/30** — "
                "диагностика, не балл.\n\n"
                "[важно] Критерий 3 не оценим из артефакта: строки "
                "3.1/3.3 вне области — оценка 3 означает «не "
                "подтверждено и не опровергнуто».\n")
        parsed = AXIS.parse_axes(text)
        self.assertFalse(parsed["partial"])
        self.assertEqual((parsed["base40"], parsed["axis30"]), (16.0, 22.0))


class TestDirectionAndVerdict(unittest.TestCase):
    def test_direction_rule(self):
        self.assertEqual(AXIS.direction(22, 16, "skill", "cl2"), "skill")
        self.assertEqual(AXIS.direction(16, 22, "skill", "cl2"), "cl2")
        self.assertEqual(AXIS.direction(20, 20, "skill", "cl2"), "нет направления")
        self.assertEqual(AXIS.direction(None, 22, "skill", "cl2"), "нет оценки")

    def test_verdict_validated(self):
        # Δ ≥ +2 и ни одна согласованная пара не перевернулась.
        self.assertEqual(AXIS.verdict_for(2, []), "ВАЛИДИРОВАН")
        self.assertEqual(AXIS.verdict_for(3, []), "ВАЛИДИРОВАН")

    def test_verdict_flip_blocks_even_with_gain(self):
        # Переворот согласованной пары (контроль) блокирует вердикт —
        # правило §30.2/§31.1: рост согласия не отменяет потери.
        self.assertEqual(AXIS.verdict_for(3, [3]), "НЕ ВАЛИДИРОВАН")

    def test_verdict_partial_and_negative(self):
        self.assertEqual(AXIS.verdict_for(1, []), "ЧАСТИЧНО")
        self.assertEqual(AXIS.verdict_for(0, []), "НЕ ВАЛИДИРОВАН")
        self.assertEqual(AXIS.verdict_for(-1, []), "НЕ ВАЛИДИРОВАН")


class TestDesignInvariants(unittest.TestCase):
    def test_base_condition_unchanged_vs_task16(self):
        # Анти-круг (BRIEF п.20): базовое условие «без» — те же константы
        # §29.1, тот же состав пар и артефактов, что в TASK-16. Меняется
        # только новое условие (рубрика версии 2).
        self.assertEqual(AXIS.BASE40, ADD.BASE40)
        self.assertEqual([p["n"] for p in AXIS.PAIRS], [p["n"] for p in ADD.PAIRS])
        self.assertEqual(AXIS.ARTIFACTS, ADD.ARTIFACTS)

    def test_rubric_has_no_flat_total_in_contract(self):
        # Контракт выхода рубрики версии 2 не содержит плоской строки
        # /70: механизм перекоса (назван PO в §31.1) убран из контракта.
        # (Упоминания /70 в пояснительной прозе рубрики — объяснение
        # убранной строки, не контракт.)
        rubric = (REPO_ROOT / "eval" / "rubrics" / "hackathon-criteria-bs.md")
        text = rubric.read_text(encoding="utf-8")
        self.assertIn("Итого (база, критерии 1–4): __ /40", text)
        self.assertIn("Итого (ось слепых зон 5.1–5.3): __ /30", text)
        block = text.split("```")[1] if "```" in text else ""
        self.assertIn("Итого (база, критерии 1–4): __ /40", block)
        self.assertIn("Итого (ось слепых зон 5.1–5.3): __ /30", block)
        self.assertNotIn("/70", block)

    def test_committed_summary_locks_preregistered_verdict(self):
        # Регресс на вердикт §31.1: как только артефакт замера на диске,
        # его вердикт фиксируется тестом (предсказания §31.2 для гейта
        # проверяются прогоном и пишутся в артефакт
        # eval/runs/t17-actionability/gates-vs-human-v2.md).
        summary = RUNS / "summary.json"
        if not summary.is_file():
            self.skipTest(f"артефакт замера ещё не на диске: {summary}")
        payload = json.loads(summary.read_text(encoding="utf-8"))
        self.assertEqual(payload["prereg"], "measurements.md §31.1")
        self.assertEqual(payload["agreement"]["pairs"], 7)
        self.assertEqual(payload["failures"], 0)
        self.assertEqual(payload["blinding_defects"], [])
        # Согласие оси — диагностика, не вердикт: в payload есть, но
        # вердикт считается по базе.
        self.assertIn("axis_diag", payload["agreement"])
        self.assertIn(payload["verdict"],
                      ("ВАЛИДИРОВАН", "ЧАСТИЧНО", "НЕ ВАЛИДИРОВАН"))


if __name__ == "__main__":
    unittest.main()
