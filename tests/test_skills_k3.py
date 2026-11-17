"""Юнит-тесты серии навыков k=3 + О5 + H-C2 (TASK-hermes-12, драйверы
eval/run_skills_k3.py, eval/score_skills_k3.py, eval/skills_k3_stats.py,
eval/critic_loop_step2.py).

Шов под тестом — чистые функции: построение промптов рук и guard
prompt-drift, цена под модель, t-интервалы и правило вердикта, покрытие
скоринга (каждая цепочка × рубрика), идемпотентность, сбор наблюдений
кросс-группового анализа. Прогонов моделей и сети нет.

Запуск: python3 -m unittest tests.test_skills_k3 -v
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = load_module("run_skills_k3", REPO_ROOT / "eval" / "run_skills_k3.py")
scorer = load_module("score_skills_k3", REPO_ROOT / "eval" / "score_skills_k3.py")
stats = load_module("skills_k3_stats", REPO_ROOT / "eval" / "skills_k3_stats.py")
ablation_stats = load_module("ablation_stats", REPO_ROOT / "eval" / "ablation_stats.py")
hc2 = load_module("critic_loop_step2", REPO_ROOT / "eval" / "critic_loop_step2.py")


class PromptBuildTests(unittest.TestCase):
    """Промпты рук: адаптация «открой файл» → «инлайн» строго один раз;
    lean не трогаем; инлайн-блоки на месте."""

    @classmethod
    def setUpClass(cls):
        cls.brief = "БРИФ-ТЕСТ"
        cls.evidence = "=== ev-001 ===\nсодержимое"

    def test_adaptation_replaces_file_reference(self):
        source = gen.run_ab.RESEARCH_CURATION_PROMPT.format(brief="b", evidence="e")
        adapted = gen.adapt_prompt(source, "RESEARCH_CURATION_PROMPT")
        self.assertNotIn("открой", adapted)
        self.assertIn("ИНЛАЙНОМ", adapted)
        # мандат и требования сохранены дословно
        self.assertIn("Каждое существенное число несёт основание", adapted)

    def test_lean_prompt_untouched(self):
        source = gen.run_ab.RESEARCH_LEAN_PROMPT.format(brief="b", evidence="e")
        self.assertEqual(gen.adapt_prompt(source, None), source)
        self.assertNotIn("SKILL.md", source)

    def test_prompt_drift_raises(self):
        # Если тексты рук в run_ab.py изменятся — драйвер падает, а не
        # генерирует «почти тот» промпт (предрегистрация §25.1).
        with self.assertRaises(RuntimeError):
            gen.adapt_prompt("совершенно другой текст", "STEP_PROMPT")

    def test_step2_prompts_have_inline_content(self):
        prompts = gen.build_step2_prompts(self.brief, self.evidence)
        self.assertIn("НАВЫК EVIDENCE", prompts["curation"])
        self.assertIn("ШАБЛОН RESEARCH.MD", prompts["curation"])
        self.assertIn("НАВЫК EVIDENCE", prompts["hybrid"])
        self.assertNotIn("ШАБЛОН RESEARCH.MD", prompts["hybrid"])
        self.assertNotIn("НАВЫК EVIDENCE", prompts["lean"])
        # шаги 2: все три промпта содержат бриф и дайджест
        for prompt in prompts.values():
            self.assertIn(self.brief, prompt)
            self.assertIn(self.evidence, prompt)

    def test_step3_prompts_brief_only(self):
        prompts = gen.build_step3_prompts(self.brief)
        for prompt in prompts.values():
            self.assertIn(self.brief, prompt)
        self.assertIn("НАВЫК OPTIONS", prompts["curation"])
        self.assertIn("НАВЫК OPTIONS", prompts["hybrid"])
        self.assertNotIn("НАВЫК OPTIONS", prompts["lean"])

    def test_o5b_prompt_contains_research(self):
        prompt = gen.build_o5b_prompt(self.brief, self.evidence, "РЕЗУЛЬТАТ-ИССЛЕДОВАНИЯ")
        self.assertIn("РЕЗУЛЬТАТ-ИССЛЕДОВАНИЯ", prompt)
        self.assertIn("НАВЫК OPTIONS", prompt)
        self.assertIn(self.brief, prompt)


class CostModelTests(unittest.TestCase):
    """ЦенаGeneration по модели (§1.8): step-5 1.00/0.10/2.70,
    flash 0.20/0.04/1.15 за 1M."""

    def test_step5_prices(self):
        tokens = {"input": 1_000_000, "cache_read": 0, "output": 1_000_000, "reasoning": 0}
        self.assertAlmostEqual(gen.cost_usd(tokens, "step-5-preview"), 3.70, places=6)

    def test_flash_prices(self):
        tokens = {"input": 1_000_000, "cache_read": 0, "output": 1_000_000, "reasoning": 0}
        self.assertAlmostEqual(gen.cost_usd(tokens, "step-3.7-flash"), 1.35, places=6)

    def test_flash_cheaper_than_step5_same_tokens(self):
        tokens = {"input": 20_000, "cache_read": 5_000, "output": 8_000, "reasoning": 0}
        self.assertLess(gen.cost_usd(tokens, "step-3.7-flash"),
                        gen.cost_usd(tokens, "step-5-preview"))


class IntervalMathTests(unittest.TestCase):
    """При k=3 интервал по t (4.303), не по z; правило вердикта §25.1."""

    def test_t_crit_k3(self):
        self.assertEqual(stats.t_crit(3), 4.303)
        self.assertAlmostEqual(stats.t_crit(20), 1.959963984540054, places=6)

    def test_arm_summary_uses_t(self):
        st = stats.arm_summary([36.0, 38.0, 38.0])
        self.assertAlmostEqual(st["mean"], 37.333333, places=4)
        self.assertAlmostEqual(st["ci95"], 2.868, places=2)

    def test_verdict_rule(self):
        mdd = ablation_stats.mdd_two_arm(3, 1.03)
        self.assertEqual(ablation_stats.verdict(5.0, mdd), "выше шума")
        self.assertEqual(ablation_stats.verdict(4.0, mdd), "НА ГРАНИЦЕ")
        self.assertEqual(ablation_stats.verdict(2.0, mdd), "нет отличимого различия")


class ScoringCoverageTests(unittest.TestCase):
    """РЕГРЕСС (урок t11): каждая цепочка каждой руки scored один раз
    на рубрику — «серия k=3» в плане не равна k=3 в данных."""

    def _make_runs(self, tmp: str) -> Path:
        runs = Path(tmp)
        for group, arms in (("research", scorer.FAMILIES["research"]["arms"]),
                            ("options", scorer.FAMILIES["options"]["arms"])):
            for arm in arms:
                arm_dir = runs / group / arm
                arm_dir.mkdir(parents=True)
                for name in ("final.md", "final-1.md", "final-2.md"):
                    (arm_dir / name).write_text("x", encoding="utf-8")
        return runs

    def test_every_chain_scored_under_each_rubric(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = self._make_runs(tmp)
            calls: list[tuple[str, str]] = []

            def fake_run_critic(artifact, rubric, out_dir, tag):
                calls.append((Path(artifact).name, Path(rubric).name))
                return {"total40": 37.0}

            with mock.patch.object(scorer, "run_critic", fake_run_critic):
                rc = scorer.main(["--runs-dir", tmp, "--groups", "research,options"])
            self.assertEqual(rc, 0)
            # 3 руки × 3 цепочки × 2 рубрики × 2 шага = 36 прогонов
            self.assertEqual(len(calls), 36)
            # у research-артефактов типовая рубрика — research, у options — options
            # (9 артефактов шага × одна типовая рубрика на артефакт)
            research_typical = [c for c in calls if c[1] == "rubric-research.md"]
            options_typical = [c for c in calls if c[1] == "rubric-options.md"]
            unified = [c for c in calls if c[1] == "hackathon-criteria.md"]
            self.assertEqual(len(research_typical), 9)
            self.assertEqual(len(options_typical), 9)
            self.assertEqual(len(unified), 18)
            names = {c[0] for c in calls}
            self.assertIn("final-2.md", names)

    def test_existing_critic_out_not_rescored(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = self._make_runs(tmp)
            pre = runs / "scores" / "research-lean-0-unified"
            pre.mkdir(parents=True)
            (pre / "critic.out").write_text("...\nИтого: 41/40\n", encoding="utf-8")
            seen: list[str] = []

            def spy(artifact, rubric, out_dir, tag):
                seen.append(Path(out_dir).name)
                return {"total40": 0.0}

            with mock.patch.object(scorer, "run_critic", spy):
                scorer.main(["--runs-dir", tmp, "--groups", "research"])
            self.assertNotIn("research-lean-0-unified", seen)
            self.assertEqual(len(seen), 17)  # 18 − 1 уже сделанный


class StatsObservationTests(unittest.TestCase):
    """Сбор наблюдений кросс-группового анализа (o5a, o5b, hc2)."""

    def _records(self):
        recs = []
        for i in range(3):
            recs.append({"group": "research", "arm": "lean", "i": i, "rubric": "unified", "total40": 26.0 + i})
            recs.append({"group": "o5a", "arm": "lean", "i": i, "rubric": "unified", "total40": 25.0 + i})
            recs.append({"group": "hc2", "arm": "revised", "i": i, "rubric": "unified", "total40": 28.0 + i})
        return recs

    def test_o5a_arms_from_two_groups(self):
        recs = self._records()
        step5 = stats.observations(recs, ["research"], "lean", "unified")
        flash = stats.observations(recs, ["o5a"], "lean", "unified")
        self.assertEqual(step5, [26.0, 27.0, 28.0])
        self.assertEqual(flash, [25.0, 26.0, 27.0])

    def test_hc2_analysis_pairs(self):
        recs = self._records()
        revised = stats.observations(recs, ["hc2"], "revised", "unified")
        draft = stats.observations(recs, ["research"], "lean", "unified")
        d = stats.delta_summary(stats.arm_summary(draft), stats.arm_summary(revised))
        self.assertAlmostEqual(d["delta"], 2.0, places=6)
        self.assertIsNotNone(d["ci95"])

    def test_analyses_registry_has_all_five(self):
        self.assertEqual(set(stats.ANALYSES), {"step2", "step3", "o5a", "o5b", "hc2"})


class ParserFormatTests(unittest.TestCase):
    """Контракт «Итого»: три формата выхода оценщика.

    Дефект класса «оценка терялась при непустом выходе» (§12.1,
    clc-heldout §20.9-B) — формат выхода оценщика валидируется не
    регуляркой «на глаз». Вариант «| **Итого** |» найден в прогоне
    TASK-hermes-12 (research-curation-1-unified, options-lean-0-unified).
    """

    def test_three_total_formats(self):
        cases = [
            "Итого: 36 /40",
            "| Итого | | | **22/40** |",
            "| **Итого** | | | **26/40** |",
        ]
        expected = [36.0, 22.0, 26.0]
        for text, want in zip(cases, expected):
            self.assertEqual(scorer.parse_scores(text)["total40"], want)

    def test_unparseable_is_none(self):
        self.assertIsNone(scorer.parse_scores("оценки нет, только находки")["total40"])


class SummaryMergeTests(unittest.TestCase):
    """РЕГРЕСС: прогон подмножества групп Не перезаписывает накопленные
    записи (дефект найден в TASK-hermes-12: скоринг hc2 перезаписал
    summary.json с 54 записями на 6)."""

    def test_subset_run_merges_not_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            arm_dir = runs / "research" / "lean"
            arm_dir.mkdir(parents=True)
            (arm_dir / "final.md").write_text("x", encoding="utf-8")
            scores_dir = runs / "scores"
            scores_dir.mkdir()
            (scores_dir / "summary.json").write_text(json.dumps({
                "records": [{"group": "options", "arm": "lean", "i": 0,
                             "rubric": "unified", "total40": 30.0}],
                "failures": 0,
            }), encoding="utf-8")

            def fake_run_critic(artifact, rubric, out_dir, tag):
                return {"total40": 25.0}

            with mock.patch.object(scorer, "run_critic", fake_run_critic):
                scorer.main(["--runs-dir", tmp, "--groups", "research", "--k", "1"])
            merged = json.loads((scores_dir / "summary.json").read_text(encoding="utf-8"))
            keys = {(r["group"], r["rubric"]) for r in merged["records"]}
            self.assertIn(("options", "unified"), keys)   # старое сохранено
            self.assertIn(("research", "unified"), keys)  # новое добавлено
            self.assertEqual(len(merged["records"]), 3)   # options×1 + research×2


class CliContractTests(unittest.TestCase):
    """Контракт CLI драйверов: --dry-run и guard использования."""

    def test_generator_dry_run(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "eval" / "run_skills_k3.py"), "--dry-run"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[dry-run] research/curation:", proc.stdout)
        self.assertIn("step-3.7-flash", proc.stdout)

    def test_generator_rejects_unknown_group(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "eval" / "run_skills_k3.py"),
             "--groups", "nope", "--dry-run"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
        )
        self.assertEqual(proc.returncode, gen.EXIT_USAGE)

    def test_hc2_dry_run_without_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "eval" / "critic_loop_step2.py"),
                 "--runs-dir", tmp, "--dry-run"],
                capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
