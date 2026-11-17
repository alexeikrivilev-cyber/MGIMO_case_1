"""Юнит-тесты драйвера TASK-hermes-18 (§32, полный путь под прод-конфигом).

`eval/run_full_case.py` — прогон шагов 0–5 под текущим прод-конфигом:
состав гейтов по артефактам цепочки, контракт сессий (входы инлайном,
артефакт — ответом в чат, внешний фенс снимается), порог годности
артефакта (заглушка не проходит — дефект живого прогона 1: гейты
проходили ВАКУУМНО на 48-байтном нарративе), переиспользование зелёного
артефакта (идемппотентность, урок t11), проводка гейтов через
subprocess с явным exit-кодом, перенос рамки шага 0 дословно.

Регресс на предрегистрацию: measurements.md §32 существует ДО
прогонов (порядок дисциплины: предрегистрация → прогон → вердикт).

Запуск: python3 -m unittest tests.test_task18 -v
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RFC = load_module("run_full_case_test", REPO_ROOT / "eval" / "run_full_case.py")
SFC = load_module("score_full_case_test",
                  REPO_ROOT / "eval" / "score_full_case.py")


class TestGateSets(unittest.TestCase):
    """Состав гейтов шага для артефакта цепочки (§32.0)."""

    def setUp(self):
        self.artifacts = Path(tempfile.mkdtemp()) / "artifacts"
        self.artifacts.mkdir(parents=True)
        self.task = RFC.TASKS["demo-retention"]

    def gate_names(self, name: str) -> list[str]:
        return [g for g, _ in RFC.gates_for_artifact(
            name, self.artifacts, self.task)]

    def test_research_only_base_gates(self):
        # Шаг 2 не несёт специфических гейтов шага: sources +
        # transferability на весь путь.
        self.assertEqual(self.gate_names("research.md"),
                         ["sources-research.md",
                          "transferability-research.md"])

    def test_options_gets_step3_gates(self):
        names = self.gate_names("options.md")
        self.assertIn("options", names)
        self.assertIn("complexity", names)
        self.assertIn("ranges", names)

    def test_strategy_product_gets_acceptance_and_actionability(self):
        names = self.gate_names("strategy-product.md")
        self.assertIn("acceptance", names)
        self.assertIn("actionability", names)
        self.assertIn("ranges", names)

    def test_all_step45_artifacts_get_acceptance_and_actionability(self):
        # Дефект области действия TASK-hermes-20: гейты чек-листа и
        # управляемости винтили только на strategy-product.md — comms /
        # verification / decisions дошли до сдачи без плана. Фикс: весь
        # этап 4–5 под обоими гейтами.
        for name in RFC.STEP45_ARTIFACTS:
            names = self.gate_names(name)
            self.assertIn("acceptance", names, name)
            self.assertIn("actionability", names, name)

    def test_comms_and_verification_get_ranges_only(self):
        # Прежний состав (ranges без acceptance/actionability) — это и
        # есть дефект области действия; регресс фиксирует новый состав.
        for name in ("strategy-comms.md", "verification-plan.md"):
            names = self.gate_names(name)
            self.assertIn("ranges", names)
            self.assertIn("acceptance", names)

    def test_decisions_gets_registry_gate(self):
        names = self.gate_names("decisions.md")
        self.assertIn("decisions", names)
        self.assertIn("ranges", names)
        self.assertIn("acceptance", names)
        self.assertIn("actionability", names)

    def test_all_chain_artifacts_have_sources(self):
        for name in RFC.CHAIN:
            self.assertTrue(any(g.startswith("sources-")
                                for g in self.gate_names(name)), name)


class TestChatContract(unittest.TestCase):
    """Артефакт возвращается ответом в чат; внешний фенс снимается."""

    def test_strip_fence_markdown(self):
        text = "```markdown\n# Артефакт\n\nтело\n```\n"
        self.assertEqual(RFC.strip_fence(text), "# Артефакт\n\nтело")

    def test_strip_fence_plain(self):
        text = "# Артефакт\n\nтело\n"
        self.assertEqual(RFC.strip_fence(text), text.strip())

    def test_strip_fence_preserves_inner(self):
        text = "# Артефакт\n\n```python\nкод\n```\n"
        self.assertEqual(RFC.strip_fence(text), text.strip())


class TestArtifactSanity(unittest.TestCase):
    """Порог годности: заглушка не проходит к гейтам (дефект прогона 1)."""

    def test_narration_stub_rejected(self):
        # Живой дефект: сессия вернула 48 байт нарратива, гейты прошли
        # вакуумно на файле-заглушке.
        ok, why = RFC.artifact_sane("I'll start by reading the files.")
        self.assertFalse(ok)
        self.assertIn("коротко", why)

    def test_no_heading_rejected(self):
        ok, why = RFC.artifact_sane("текст без заголовка " * 200)
        self.assertFalse(ok)
        self.assertIn("заголовка", why)

    def test_real_artifact_accepted(self):
        body = "# Исследование\n\n" + ("Основание ev-002, число 56.21%.\n" * 100)
        ok, why = RFC.artifact_sane(body)
        self.assertTrue(ok, why)

    def test_fenced_artifact_accepted(self):
        body = ("```markdown\n# Исследование\n\n"
                + ("строка основания ev-001 с числом 56.21%\n" * 120) + "```")
        ok, why = RFC.artifact_sane(body)
        self.assertTrue(ok, why)


class TestInlineContract(unittest.TestCase):
    """Входы инлайном: навык + шаблон + входящие артефакты; прежние
    project-артефакты ответа не входят (изоляция цепочки)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.artifacts = self.tmp / "artifacts"
        self.artifacts.mkdir(parents=True)
        for name in ("research.md", "options.md", "strategy-product.md",
                     "verification-plan.md"):
            (self.artifacts / name).write_text(
                f"# {name}\n\n" + ("строка основания ev-001\n" * 50),
                encoding="utf-8")
        self.task = RFC.TASKS["demo-retention"]

    def test_research_prompt_has_skill_template_evidence(self):
        prompt = RFC.build_prompt(self.task, self.artifacts, "research.md")
        self.assertIn("НАВЫК", prompt)
        self.assertIn("ШАБЛОН", prompt)
        self.assertIn("РАМКА", prompt)
        self.assertIn("ev-001-mixpanel-benchmarks.md", prompt)
        self.assertIn("ЧЕКПОИНТА 2", prompt)
        self.assertIn("НЕ открывай файлы", prompt)

    def test_options_prompt_has_carried_cp3(self):
        prompt = RFC.build_prompt(self.task, self.artifacts, "options.md")
        self.assertIn("ЧЕКПОИНТА 3", prompt)
        self.assertIn("ИССЛЕДОВАНИЕ (шаг 2 этого прогона)", prompt)

    def test_strategy_product_prompt_has_checklist_mandate(self):
        prompt = RFC.build_prompt(self.task, self.artifacts,
                                  "strategy-product.md")
        self.assertIn("приёмный чек-лист 6 вопросов", prompt)
        self.assertIn("ВАРИАНТЫ (шаг 3 этого прогона)", prompt)

    def test_decisions_prompt_has_verification_input(self):
        prompt = RFC.build_prompt(self.task, self.artifacts, "decisions.md")
        self.assertIn("ПЛАН ПРОВЕРКИ (шаг 4 этого прогона)", prompt)

    def test_carried_decisions_per_task(self):
        # Перенесённые решения чекпоинтов — свои у каждой задачи:
        # демой текст про «Первые 90 дни», held-out — про «Второй
        # месяц» + «Премиум» (симметрия §32.2).
        demo = RFC.TASKS["demo-retention"]
        ho = RFC.TASKS["heldout-growth-segment"]
        self.assertIn("Первые 90 дни", demo["cp3"])
        self.assertIn("Второй месяц", ho["cp3"])
        self.assertIn("Премиум", ho["cp3"])
        self.assertNotIn("Первые 90 дни", ho["cp3"])
        self.assertIn("30-дневное удержание", demo["cp2"])
        self.assertIn("направление роста", ho["cp2"])

    def test_inputs_block_excludes_previous_project_artifacts(self):
        # Изоляция цепочки: прежние project-артефакты ответа не
        # инлайнятся как ВХОДЫ (навык/шаблон могут упоминать project-
        # пути как методологию — это не вход; проверяем заголовки
        # секций входа).
        import re
        block = RFC.build_inputs_block(self.task, self.artifacts,
                                       "options.md")
        headers = re.findall(r"^=== (.+?) ===$", block, re.MULTILINE)
        joined = "\n".join(headers)
        self.assertNotIn("project/research.md", joined)
        self.assertNotIn("project/options.md", joined)
        self.assertTrue(any("research.md" in h and "этого прогона" in h
                            for h in headers), headers)


class TestGateScopeRegression(unittest.TestCase):
    """Регресс дефекта области действия (TASK-hermes-20): нарочно
    сломанный артефакт ЛЮБОГО из шагов 4–5 обязан валить гейты —
    прогон с ним падает. До фикса гейты acceptance/actionability
    смотрели только на strategy-product.md, и сломанный comms /
    verification / decisions прошли бы «зелёно»."""

    BROKEN_COMMS = """# Коммуникационная стратегия (фикстура регресса)

## Ключевые сообщения

1. Сообщение без плана: запускаем комбинацию механизмов.
"""

    BROKEN_DECISIONS_FENCED = """Гейт падал на указатели пунктов навыка.

```markdown
# Решения (фикстура регресса)

## Реестр решений

| ID | Решение | Владелец | Дата | Метрика | Условие | Статус |
|---|---|---|---|---|---|---|
| D1 | Целевая метрика — удержание | РП | 2026-11-17 | holdout | пересмотр | принято |
```
"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.task = RFC.TASKS["demo-retention"]

    def _gates(self, name: str) -> dict[str, int]:
        path = self.tmp / name
        codes: dict[str, int] = {}
        for gate_name, argv in RFC.gates_for_artifact(name, self.tmp,
                                                      self.task):
            argv = [a.replace(str(self.tmp), str(self.tmp)) for a in argv]
            code, _ = RFC.run_gate(argv, self.tmp / "logs", gate_name)
            codes[gate_name] = code
        return codes

    def test_broken_comms_fails_acceptance_and_actionability(self):
        (self.tmp / "strategy-comms.md").write_text(self.BROKEN_COMMS,
                                                   encoding="utf-8")
        codes = self._gates("strategy-comms.md")
        self.assertEqual(codes["acceptance"], 2)
        self.assertEqual(codes["actionability"], 2)

    def test_fenced_decisions_fails_both_gates(self):
        # Артефакт внутри код-фенса невидим для гейтов (они исключают
        # фенсы) — содержание с приёмным чек-листом внутри ограды не
        # проходит: класс прецедента TASK-hermes-18 (strategy-product).
        path = self.tmp / "decisions.md"
        path.write_text(self.BROKEN_DECISIONS_FENCED, encoding="utf-8")
        codes = self._gates("decisions.md")
        self.assertEqual(codes["acceptance"], 2)
        self.assertEqual(codes["actionability"], 2)

    def test_real_step45_artifacts_all_green(self):
        # Живые артефакты этапа после ревизии TASK-hermes-20: состав
        # гейтов драйвера на них зелёный (не только на strategy-product).
        artifacts = (REPO_ROOT / "eval" / "runs" / "t18-case"
                     / "artifacts")
        for name in RFC.STEP45_ARTIFACTS:
            path = artifacts / name
            self.assertTrue(path.is_file(), name)
            for gate_name, argv in RFC.gates_for_artifact(name, artifacts,
                                                          self.task):
                code, output = RFC.run_gate(argv, self.tmp / "logs",
                                            f"live-{gate_name}")
                self.assertEqual(code, 0,
                                 f"{gate_name}: {output[:500]}")


class TestGenerationMandates(unittest.TestCase):
    """Промпты генерации шагов 4–5 несут мандат приёмного чек-листа и
    структур плана — иначе следующий прогон воспроизведёт дефект
    области действия на стороне генерации (TASK-hermes-20)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.artifacts = self.tmp / "artifacts"
        self.artifacts.mkdir(parents=True)
        for name in ("research.md", "options.md", "strategy-product.md",
                     "verification-plan.md"):
            (self.artifacts / name).write_text(
                f"# {name}\n\n" + ("строка основания ev-001\n" * 50),
                encoding="utf-8")
        self.task = RFC.TASKS["demo-retention"]

    def test_comms_prompt_mandates_checklist_and_plan(self):
        prompt = RFC.build_prompt(self.task, self.artifacts,
                                  "strategy-comms.md")
        self.assertIn("Приёмный чек-лист (6 вопросов владельца)", prompt)
        self.assertIn("P0–P2", prompt)
        self.assertIn("контрольная группа", prompt)

    def test_verification_prompt_mandates_checklist_and_plan(self):
        prompt = RFC.build_prompt(self.task, self.artifacts,
                                  "verification-plan.md")
        self.assertIn("Приёмный чек-лист (6 вопросов владельца)", prompt)
        self.assertIn("P0–P2", prompt)
        self.assertIn("критерии остановки", prompt.lower())

    def test_decisions_prompt_mandates_checklist_and_clean_md(self):
        prompt = RFC.build_prompt(self.task, self.artifacts, "decisions.md")
        self.assertIn("Приёмный чек-лист (6 вопросов владельца)", prompt)
        self.assertIn("P0–P2", prompt)
        self.assertIn("кодовых фенсов", prompt.lower())


class TestGatePlumbing(unittest.TestCase):
    """run_gate: явный exit-код, лог на диске, без конвейеров."""

    def test_gate_exit_zero_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean.md"
            clean.write_text(
                "Отток когорты 0–3 мес — 56.21% (ev-002), маркер "
                "[гипотеза] на месте.\n", encoding="utf-8")
            code, output = RFC.run_gate(
                ["scripts/check_ranges.py", str(clean)],
                Path(tmp) / "logs", "ranges")
            self.assertEqual(code, 0, output)
            log = Path(tmp) / "logs" / "ranges.gate.txt"
            self.assertTrue(log.is_file())
            self.assertIn("exit=0", log.read_text(encoding="utf-8"))

    def test_gate_exit_two_on_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.md"
            bad.write_text("| Срок | 4–8 недель |\n", encoding="utf-8")
            code, _ = RFC.run_gate(
                ["scripts/check_ranges.py", str(bad)],
                Path(tmp) / "logs", "ranges")
            self.assertEqual(code, 2)


class TestStep0Carry(unittest.TestCase):
    """Шаг 0: рамка переносится дословно, гейт sources проходит."""

    def test_carry_brief_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            manifest: list[str] = []
            ok = RFC.step0_carry_brief(RFC.TASKS["demo-retention"],
                                       artifacts, manifest)
            self.assertTrue(ok)
            carried = (artifacts / "brief.md").read_text(encoding="utf-8")
            source = (REPO_ROOT / "project" / "brief.md").read_text(
                encoding="utf-8-sig")
            self.assertEqual(carried, source)
            self.assertTrue(any("ЧЕКПОИНТ 1" in line for line in manifest))


class TestEvalAggregator(unittest.TestCase):
    """score_full_case.py: состав клеток, согласие, отчёт (без сессий)."""

    def test_chain_and_shorts_complete(self):
        self.assertEqual(len(SFC.CHAIN), 6)
        for name in SFC.CHAIN:
            self.assertIn(name, SFC.ART_SHORT)

    def test_typical_rubrics_only_where_named(self):
        # Типовая рубрика названа только для шагов 2 и 3; для шагов 4–5
        # её нет (TASK-8: hackathon-criteria как именованный допуск).
        self.assertEqual(set(SFC.TYPICAL_BY_STEP),
                         {"research.md", "options.md"})

    def test_agreement_stats(self):
        rows = [("research.md", 30.0, 28.0), ("options.md", 24.0, 26.0),
                ("strategy-product.md", 36.0, 33.0)]
        stats = SFC.agreement(rows)
        self.assertEqual(stats["n"], 3)
        self.assertEqual(stats["mean_abs"], 2.33)
        self.assertEqual(stats["max_abs"], 3.0)
        self.assertEqual(stats["share_ge_mdd"], 0.0)

    def test_agreement_flags_mdd_breach(self):
        rows = [("options.md", 24.0, 29.0)]
        stats = SFC.agreement(rows)
        self.assertEqual(stats["share_ge_mdd"], 1.0)

    def test_report_marks_partial_and_diagnosis(self):
        results = {
            "c1-res-uni": {"total40": 30.0},
            "c2-res-uni": {"total40": 28.0},
            "c1-opt-uni": {"total40": 24.0},
            "c2-opt-uni": {"total40": None, "partial": True},
            "axis-opt-bs": {"base40": 24.0, "axis30": 18.0,
                            "items": {"5.1": 6.0, "5.2": 6.0, "5.3": 6.0}},
        }
        report = SFC.build_report("demo-retention", results,
                                  ["c2-opt-uni: частичная оценка"])
        self.assertIn("частичная", report)
        self.assertIn("диагностика", report.lower())
        self.assertIn("5.1=6.0", report)
        self.assertIn("добор", report.lower())


class TestPreRegistration(unittest.TestCase):
    """Дисциплина порядка: §32 предрегистрация существует до прогонов."""

    def test_measurements_has_section32(self):
        text = (REPO_ROOT / "docs" / "research" / "measurements.md").read_text(
            encoding="utf-8")
        self.assertIn("## 32. TASK-hermes-18", text)
        self.assertIn("H-FP1", text)
        self.assertIn("H-FP2", text)
        self.assertIn("предрегистрация", text.lower())


class TestCliContract(unittest.TestCase):
    """Контракт CLI: dry-run печатает план; нет --task — отказ."""

    def test_dry_run_exit_zero(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "eval" / "run_full_case.py"),
             "--task", "demo-retention", "--dry-run"],
            capture_output=True, text=True, timeout=120, cwd=REPO_ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("options", proc.stdout)
        self.assertIn("критик", proc.stdout)
        self.assertIn("инлайном", proc.stdout)

    def test_missing_task_nonzero(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "eval" / "run_full_case.py")],
            capture_output=True, text=True, timeout=120, cwd=REPO_ROOT)
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
