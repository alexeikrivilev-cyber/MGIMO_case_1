"""Юнит-тесты драйверов TASK-hermes-16 (§30.2–30.3).

`eval/blindspot_addendum.py` — парсер итогов критика (4 живых формата
выхода + частичная оценка по §26.4) и вердикт по предрегистрации;
`eval/trigger_audit_heldout2.py` — второй набор кейсов триггера
не пересекается с §27.1, шаблон промпта — тот же объект, не копия.

Фикстуры парсера — РЕАЛЬНЫЕ выходы сессий замера (read-only):
`eval/runs/t16-addendum/` (итоговые) и `pass1|pass2/` (дефектные
проходы). Тест на закоммиченный summary.json фиксирует вердикт
предрегистрации (§30.2) как регресс.

Запуск: python3 -m unittest tests.test_task16 -v
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


ADD = load_module("blindspot_addendum_test", REPO_ROOT / "eval" / "blindspot_addendum.py")
TRIG2 = load_module("trigger_audit_heldout2_test", REPO_ROOT / "eval" / "trigger_audit_heldout2.py")
TRIG1 = load_module("trigger_audit_heldout1_test", REPO_ROOT / "eval" / "trigger_audit_heldout.py")

RUNS = REPO_ROOT / "eval" / "runs" / "t16-addendum"


def critic_out(*parts: str) -> str:
    path = RUNS.joinpath(*parts)
    if not path.is_file():
        raise unittest.SkipTest(f"артефакт прогона не на диске: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


class TestExtendedTotalsParser(unittest.TestCase):
    """Парсер «Итого» расширенной рубрики: 4 живых формата модели."""

    def test_format_explicit_subtotals(self):
        # Формат рубрики: «Итого (база…): 22 /40» + «Итого (пункты…): 24 /30»
        text = ("| 1. Проработанность | 5/5 | 4/5 | 8/10 |\n"
                "Итого (база, критерии 1–4): 22 /40\n"
                "Итого (пункты слепых зон 5.1–5.3): 24 /30\n"
                "Итого: 44 /70\n")
        parsed = ADD.parse_extended(text)
        self.assertEqual((parsed["base40"], parsed["addendum30"], parsed["total70"]),
                         (22.0, 24.0, 44.0))
        self.assertFalse(parsed["partial"])

    def test_format_short_labels(self):
        # Живой формат cl2 (проход 1): «Итого (5.1–5.3): 20/30 · Итого полное: 46/70»
        text = ("Итого: 26/40\n"
                "| 5.1 Управляемость | 4/5 | 3/5 | 6/10 |\n"
                "| 5.2 Управляемая сложность | 5/5 | 5/5 | 10/10 |\n"
                "| 5.3 Обоснованность диапазонов | 3/5 | 2/5 | 4/10 |\n"
                "Итого (5.1–5.3): 20/30 · Итого полное: 46/70\n")
        parsed = ADD.parse_extended(text)
        self.assertEqual((parsed["base40"], parsed["addendum30"], parsed["total70"]),
                         (26.0, 20.0, 46.0))
        self.assertEqual(parsed["items"], {"5.1": 6.0, "5.2": 10.0, "5.3": 4.0})

    def test_format_bare_item_cells(self):
        # Живой формат skill/lean0: последняя клетка пункта — «4», не «4/10»
        text = ("| 5.1 Управляемость (слепая зона человека) | 3 | 2 | 4 |\n"
                "| 5.2 Управляемая сложность | 5 | 5 | 10 |\n"
                "| 5.3 Обоснованность диапазонов | 5 | 5 | 10 |\n"
                "Итого (база, критерии 1–4): 20 /40\n"
                "Итого (пункты слепых зон 5.1–5.3): 24 /30\n"
                "Итого: 44 /70\n")
        parsed = ADD.parse_extended(text)
        self.assertEqual(parsed["items"], {"5.1": 4.0, "5.2": 10.0, "5.3": 10.0})
        self.assertEqual(parsed["total70"], 44.0)

    def test_format_table_total(self):
        # Живой формат cl2 (проход 3): итог base — строка таблицы
        text = ("| 1. Проработанность | 5/5 | 4/5 | 8/10 |\n"
                "| **Итого** | | | **16/40** |\n")
        parsed = ADD.parse_extended(text)
        self.assertEqual(parsed["base40"], 16.0)
        self.assertIsNone(parsed["total70"])

    def test_base_derived_from_total_minus_addendum(self):
        text = ("| 5.1 Управляемость | 4/5 | 3/5 | 7/10 |\n"
                "| 5.2 Управляемая сложность | 5/5 | 4/5 | 9/10 |\n"
                "| 5.3 Обоснованность диапазонов | 4/5 | 4/5 | 8/10 |\n"
                "Итого: 46 /70\n")
        parsed = ADD.parse_extended(text)
        self.assertEqual(parsed["addendum30"], 24.0)   # сумма пунктов
        self.assertEqual(parsed["base40"], 22.0)       # total − addendum
        self.assertEqual(parsed["total70"], 46.0)

    def test_partial_assessment_excluded(self):
        # Частичная оценка («по оценимым») — клетка не сравнима (§26.4):
        # total70 обнуляется, частичность фиксируется.
        text = ("Итого (база, критерии 1–4): **23/30** по оценимым (К1 8, К3 н/о) — из 40.\n"
                "Итого (пункты слепых зон 5.1–5.3): **22/30**.\n"
                "Итого: **45/60** по оценимым — из 70\n")
        parsed = ADD.parse_extended(text)
        self.assertTrue(parsed["partial"])
        self.assertIsNone(parsed["total70"])
        self.assertEqual(parsed["addendum30"], 22.0)

    def test_real_artifacts_parse(self):
        # Итоговые артефакты замера: 7 рук, 7 полных итогов (клетка
        # curation#0 получена добором — частичная оценка прохода 4 сохранена).
        expected = {
            "council-lite": 30.0, "critic-loop2": 40.0, "curation0": 42.0,
            "hybrid0": 36.0, "lean0": 38.0, "plain-chat": 44.0, "skill": 44.0,
        }
        for arm, total in expected.items():
            parsed = ADD.parse_extended(critic_out(arm, "critic.out"))
            self.assertEqual(parsed["total70"], total, arm)
            self.assertFalse(parsed["partial"], arm)

    def test_pass1_defect_artifacts_are_partial_or_baseless(self):
        # Проход 1 (битая рубрика): итогов /70 нет — клетки не сравнимая
        # механика, поэтому серия перепрогнана. Тест фиксирует, почему.
        for arm in ("council-lite", "skill", "plain-chat"):
            parsed = ADD.parse_extended(critic_out("pass1", arm, "critic.out"))
            self.assertIsNone(parsed["total70"], arm)


class TestDirectionAndVerdict(unittest.TestCase):
    def test_direction_rule(self):
        self.assertEqual(ADD.direction(44, 30, "skill", "cl2"), "skill")
        self.assertEqual(ADD.direction(30, 44, "skill", "cl2"), "cl2")
        self.assertEqual(ADD.direction(44, 44, "skill", "cl2"), "нет направления")
        self.assertEqual(ADD.direction(None, 44, "skill", "cl2"), "нет оценки")

    def test_committed_summary_locks_preregistered_verdict(self):
        # Регресс на вердикт §30.2: согласие выросло 1/7 → 4/7, но
        # согласованная пара 3 перевернулась → НЕ ВАЛИДИРОВАН.
        payload = json.loads((RUNS / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["agreement"]["old_base"], 1)
        self.assertEqual(payload["agreement"]["extended"], 4)
        self.assertEqual(payload["flipped_agreed"], [3])
        self.assertEqual(payload["verdict"], "НЕ ВАЛИДИРОВАН")
        self.assertEqual(payload["failures"], 0)
        self.assertEqual(payload["blinding_defects"], [])
        # Расширенная рубрика согласована с человеком РОВНО на парах,
        # чьи человеческие причины — три слепые зоны (2, 4, 5, 6).
        agreed = sorted(r["n"] for r in payload["rows"] if r["agree_ext"])
        self.assertEqual(agreed, [2, 4, 5, 6])


class TestTriggerAuditSecondSet(unittest.TestCase):
    def test_cases_disjoint_from_first_set(self):
        ids1 = {c["id"] for c in TRIG1.CASES}
        ids2 = {c["id"] for c in TRIG2.CASES}
        self.assertEqual(len(ids2), 5)
        self.assertTrue(ids2.isdisjoint(ids1))

    def test_prompt_template_is_the_same_object_not_a_copy(self):
        # Сломанная копия шаблона = вторая «правда»: текст проверяется на
        # точное равенство (импорт из базового модуля, не копия в файле).
        self.assertEqual(TRIG2.base.AUDIT_PROMPT, TRIG1.AUDIT_PROMPT)
        rendered = TRIG2.base.AUDIT_PROMPT.format(cases=TRIG2.render_cases())
        self.assertIn("ho-6", rendered)
        self.assertNotIn("ho-1 ", rendered)  # кейсы первого набора не подмешаны

    def test_expectations_follow_council_rule(self):
        # Ожидания расставлены по правилу council-design §3 (ДО прогона):
        # кросс-функциональность (>1 контура) → high; иначе low.
        expected = {"ho-6": "high", "ho-7": "high", "ho-8": "high",
                    "ho-9": "low", "ho-10": "low"}
        self.assertEqual({c["id"]: c["expected"] for c in TRIG2.CASES}, expected)


if __name__ == "__main__":
    unittest.main()
