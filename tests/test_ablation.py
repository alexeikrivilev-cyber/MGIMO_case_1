"""Юнит-тесты абляции слоёв и плато-итерации H-R2 (TASK-hermes-10).

Шов под тестом — контракт CLI и чистые функции: промпты слоёв,
разбор JSON-потока opencode, целостность ревизии, статистика
(MDD/вердикты), парсинг оценок. Прогоны моделей и сети не выполняются.

Запуск: python3 -m unittest tests.test_ablation -v
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
EVAL_DIR = REPO_ROOT / "eval"
T7_RESCORE = REPO_ROOT / "eval" / "runs" / "t7-rescore" / "summary.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_ablation = load_module("run_ablation", EVAL_DIR / "run_ablation.py")
score_ablation = load_module("score_ablation", EVAL_DIR / "score_ablation.py")
ablation_stats = load_module("ablation_stats", EVAL_DIR / "ablation_stats.py")
cl2r2 = load_module("critic_loop_round2", EVAL_DIR / "critic_loop_round2.py")
run_critic = load_module("run_critic", REPO_ROOT / "scripts" / "run_critic.py")


def run_script(path: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env.pop("STEPFUN_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(path), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=120,
    )


BRIEF = "ЗАМОРОЖЕННЫЙ БРИФ: удержание упало с 34% до 21% (ev-002)."
AGENTS = "# AGENTS.md\n\nРабочий процесс: шаг 0 РАМКА … шаг 4 СТРАТЕГИИ."


class LayerPromptTests(unittest.TestCase):
    """Вложенность стеков — инвариант абляции: L0 ⊂ L1 ⊂ L2 = L3-черновик."""

    def test_l0_has_brief_and_no_agents(self):
        prompt = run_ablation.build_prompt_L0(BRIEF)
        self.assertIn(BRIEF, prompt)
        self.assertIn("обычный чат-ассистент", prompt)
        self.assertNotIn("AGENTS.md", prompt)
        self.assertNotIn("knowledge/index.md", prompt)

    def test_l1_adds_agents_md_and_keeps_brief(self):
        prompt = run_ablation.build_prompt_L1(BRIEF, AGENTS)
        self.assertIn(BRIEF, prompt)
        self.assertIn(AGENTS, prompt)
        self.assertIn("НЕдоступны", prompt)
        self.assertNotIn("knowledge/index.md", prompt)

    def test_l2_adds_skills_and_keeps_agents_and_brief(self):
        prompt = run_ablation.build_prompt_L2(BRIEF, AGENTS)
        self.assertIn(BRIEF, prompt)
        self.assertIn(AGENTS, prompt)
        self.assertIn("КАТАЛОГ НАВЫКОВ", prompt)
        # реальный навык шага 3 подтягивается из репозитория
        skill = (REPO_ROOT / "knowledge" / "skills" / "options" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(skill.splitlines()[0], prompt)

    def test_l3_draft_equals_l2(self):
        # в main() prompts["L3"] = prompts["L2]: отличие слоя — гейт проверок,
        # а не текст черновика. Проверяем через build-функции.
        l2 = run_ablation.build_prompt_L2(BRIEF, AGENTS)
        self.assertIn("markdown-артефакт options.md", l2)

    def test_revision_prompt_has_draft_and_violations(self):
        prompt = run_ablation.build_revision_prompt("ЧЕРН", "options.md:12: нарушение")
        self.assertIn("ЧЕРН", prompt)
        self.assertIn("options.md:12: нарушение", prompt)


class ApiGenerationTests(unittest.TestCase):
    """Прямой вызов API: среда генерации = промпт (§23.0/23.1).

    Инструменты и системный промпт не передаются вовсе — иначе абляция
    измеряла бы не стек контекста, а случайную среду сессии.
    """

    def test_api_body_has_no_tools_and_single_user_message(self):
        body = run_ablation.build_api_body("промпт")
        self.assertNotIn("tools", body)
        self.assertNotIn("system", [m["role"] for m in body["messages"]])
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertEqual(body["messages"][0]["content"], "промпт")
        self.assertEqual(body["model"], "step-5-preview")

    def test_api_generate_parses_usage_and_answer(self):
        payload = {
            "choices": [{"message": {"content": "  ответ модели  "}}],
            "usage": {
                "prompt_tokens": 12000,
                "completion_tokens": 8000,
                "completion_tokens_details": {"reasoning_tokens": 3000},
            },
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with mock.patch.object(run_ablation.urllib.request, "urlopen", return_value=FakeResponse()):
            result = run_ablation.api_generate("промпт", "key", 60)
        self.assertEqual(result.answer, "ответ модели")
        self.assertEqual(result.tokens["input"], 12000)
        self.assertEqual(result.tokens["output"], 8000)
        self.assertEqual(result.tokens["reasoning"], 3000)
        self.assertIsNone(result.error)
        # формула COST.md: 12000×1.00 + 8000×2.70 за 1M
        self.assertAlmostEqual(result.cost_usd(), (12000 + 8000 * 2.7) / 1_000_000, places=9)

    def test_api_generate_empty_content_is_error(self):
        payload = {"choices": [{"message": {"content": ""}}], "usage": {}}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with mock.patch.object(run_ablation.urllib.request, "urlopen", return_value=FakeResponse()):
            result = run_ablation.api_generate("промпт", "key", 60)
        self.assertTrue(result.error)
        self.assertEqual(result.answer, "")

    def test_api_generate_network_error_is_captured(self):
        with mock.patch.object(
            run_ablation.urllib.request, "urlopen", side_effect=OSError("сеть недоступна")
        ):
            result = run_ablation.api_generate("промпт", "key", 60)
        self.assertIn("сеть недоступна", result.error or "")


class IntegrityReportTests(unittest.TestCase):
    """Целостность ревизии L3: секции вариантов и «оставить как есть»."""

    def test_nothing_lost(self):
        before = "### Вариант 1\nвозражение\n### Вариант 2\nвозражение\n### Вариант 3: оставить как есть\nвозражение\n"
        after = before + "дополнение"
        report = run_ablation.integrity_report(before, after)
        self.assertTrue(report["integrity_ok"])
        self.assertEqual(report["variants_after"], 3)
        self.assertTrue(report["status_quo_after"])

    def test_variant_dropped_is_broken(self):
        before = "### Вариант 1\nвозражение\n### Вариант 2\nвозражение\n### Вариант 3: оставить как есть\nвозражение\n"
        after = "### Вариант 1\nвозражение\n### Вариант 2\nвозражение\n"
        report = run_ablation.integrity_report(before, after)
        self.assertFalse(report["integrity_ok"])

    def test_shrink_below_60pct_is_broken(self):
        before = "### Вариант 1\n" + "x" * 1000 + "\n### Вариант 2\nвозражение\n### Вариант 3: оставить как есть\nвозражение\n"
        after = "### Вариант 1\nкратко\n### Вариант 2\nвозражение\n### Вариант 3: оставить как есть\nвозражение\n"
        report = run_ablation.integrity_report(before, after)
        self.assertFalse(report["integrity_ok"])


class AblationStatsTests(unittest.TestCase):
    """MDD из измеренного шума совпадает с mdd_recompute (§22.2)."""

    def test_mdd_n1_matches_recompute(self):
        self.assertAlmostEqual(ablation_stats.mdd_two_arm(1, 1.03), 4.09, places=1)
        self.assertAlmostEqual(ablation_stats.mdd_two_arm(1, 1.41), 5.60, places=1)

    def test_mdd_monotone_after_n2(self):
        m2 = ablation_stats.mdd_two_arm(2, 1.03)
        m4 = ablation_stats.mdd_two_arm(4, 1.03)
        self.assertLess(m4, m2)  # аномалия n=2 (§22.2) — свойство точного t

    def test_verdict_thresholds(self):
        self.assertEqual(ablation_stats.verdict(5.0, 4.09), "выше шума")
        self.assertEqual(ablation_stats.verdict(3.5, 4.09), "НА ГРАНИЦЕ")
        self.assertEqual(ablation_stats.verdict(1.0, 4.09), "нет отличимого различия")


class ScoreAblationTests(unittest.TestCase):
    """Парсинг оценок и разрешение артефактов рук."""

    def test_parse_scores_line_and_table(self):
        line = run_ablation  # noqa: F841  (импорт для консистентности модуля)
        self.assertEqual(score_ablation.parse_scores("Итого: 36 /40")["total40"], 36.0)
        self.assertEqual(score_ablation.parse_scores("| Итого | | | **22/40** |")["total40"], 22.0)
        parsed = score_ablation.parse_scores("[важность: важно] x\n[важность: критично] y")
        self.assertEqual(parsed["findings_important"], 2)

    def test_arm_artifact_paths(self):
        runs_dir = REPO_ROOT / "eval" / "runs" / "t10-ablation"
        l4 = score_ablation.arm_artifact("demo", "L4", runs_dir)
        self.assertEqual(l4, REPO_ROOT / "project" / "options.md")
        self.assertTrue(l4.is_file())
        l0 = score_ablation.arm_artifact("heldout", "L0", runs_dir)
        self.assertEqual(l0, runs_dir / "heldout-growth-segment" / "L0" / "final.md")


class Cl2Round2Tests(unittest.TestCase):
    """H-R2: пороги и round-1 баллы согласованы с предрегистрацией."""

    def test_round1_scores_match_t7_rescore(self):
        data = json.loads(T7_RESCORE.read_text(encoding="utf-8"))
        by_name = {(r["bucket"], r["name"]): r for r in data["runs"]}
        for task, bucket_name in (("demo", ("opt", "demo-criticloop2")), ("heldout", ("opt", "heldout-criticloop2"))):
            row = by_name[bucket_name]
            self.assertEqual(cl2r2.T7_RESCORE[task]["unified"], row["unified"]["total40"])
            self.assertEqual(cl2r2.T7_RESCORE[task]["typical"], row["typical"]["total40"])

    def test_mdd1_values(self):
        self.assertAlmostEqual(cl2r2.mdd1(1.03), 4.09, places=1)
        self.assertAlmostEqual(cl2r2.mdd1(1.41), 5.60, places=1)

    def test_verdicts(self):
        self.assertEqual(cl2r2.verdict(6.0, 1.03), "выше шума")
        self.assertEqual(cl2r2.verdict(1.0, 1.03), "нет отличимого различия")


class AblationCliTests(unittest.TestCase):
    """Контракты CLI: dry-run, использование, отсутствие ключа."""

    def test_dry_run(self):
        proc = run_script(EVAL_DIR / "run_ablation.py", "--task", "demo-retention", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("L0", proc.stdout)

    def test_unknown_arm_is_usage_error(self):
        proc = run_script(EVAL_DIR / "run_ablation.py", "--task", "demo-retention", "--arms", "L9")
        self.assertEqual(proc.returncode, 1)

    def test_no_key_exit_3(self):
        proc = run_script(EVAL_DIR / "run_ablation.py", "--task", "demo-retention")
        self.assertEqual(proc.returncode, 3)

    def test_ablation_stats_dry_usage(self):
        proc = run_script(EVAL_DIR / "ablation_stats.py", "--help")
        self.assertEqual(proc.returncode, 0)


class RepeatSeriesTests(unittest.TestCase):
    """Серия k=N (TASK-hermes-11 §24.1): независимые цепочки на руку."""

    def test_repeat_generates_independent_chains(self):
        # три цепочки: каждая со своим черновиком; суффиксы draft-1/final-1
        with tempfile.TemporaryDirectory() as tmp:
            arm_dir = Path(tmp) / "L2"
            arm_dir.mkdir(parents=True)
            answers = iter(["черновик-A", "черновик-B", "черновик-C"])
            with mock.patch.object(run_ablation, "api_generate") as gen:
                gen.side_effect = lambda prompt, key, timeout: self._fake(next(answers))
                for idx in range(3):
                    final, meta, ok = run_ablation.run_chain("L2", "промпт", arm_dir, "key", 60, idx)
                    self.assertTrue(ok)
                    self.assertEqual(final, f"черновик-{'ABC'[idx]}")
                    self.assertEqual(len(meta), 1)
            self.assertTrue((arm_dir / "draft.md").is_file())
            self.assertTrue((arm_dir / "draft-1.md").is_file())
            self.assertTrue((arm_dir / "draft-2.md").is_file())
            # final*.md пишет main() (цепочка возвращает текст), не run_chain
            self.assertFalse((arm_dir / "final.md").exists())
            self.assertEqual(gen.call_count, 3)

    def test_l3_chain_runs_check_gate(self):
        # L3: черновик + гейт (мок run_checks) + ревизия при нарушении
        with tempfile.TemporaryDirectory() as tmp:
            arm_dir = Path(tmp) / "L3"
            arm_dir.mkdir(parents=True)
            with mock.patch.object(run_ablation, "api_generate") as gen, \
                 mock.patch.object(run_ablation, "run_checks") as checks:
                gen.side_effect = [self._fake("черновик"), self._fake("исправлено")]
                checks.side_effect = [(False, "draft.md:1: нарушение"), (True, "ok")]
                final, meta, ok = run_ablation.run_chain("L3", "промпт", arm_dir, "key", 60, 0)
            self.assertTrue(ok)
            self.assertEqual(final, "исправлено")
            self.assertEqual([m["name"] for m in meta], ["draft", "revision0"])
            self.assertTrue((arm_dir / "round1.md").is_file())
            self.assertTrue((arm_dir / "integrity-round0.json").is_file())

    @staticmethod
    def _fake(text: str):
        res = run_ablation.SessionResult()
        res.text = text
        return res


class RunCriticEmptyOutputTests(unittest.TestCase):
    """Дефект «exit 0 ≠ непустой выход» (TASK-hermes-5/9): пустой выход
    критика при успешном коде — провал прогона, не измерение."""

    def test_empty_stdout_exit0_is_failure(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="  \n", stderr="")
            code = run_critic.main(
                [
                    "--artifact", str(REPO_ROOT / "project" / "options.md"),
                    "--rubric", "eval/rubrics/hackathon-criteria.md",
                    "--mode", "critic",
                    "--out", tempfile.mkdtemp(),
                ]
            )
        self.assertEqual(code, 4)

    def test_nonempty_stdout_exit0_is_ok(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="Итого: 30 /40\n", stderr=""
            )
            out_dir = tempfile.mkdtemp()
            code = run_critic.main(
                [
                    "--artifact", str(REPO_ROOT / "project" / "options.md"),
                    "--rubric", "eval/rubrics/hackathon-criteria.md",
                    "--mode", "critic",
                    "--out", out_dir,
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("Итого", (Path(out_dir) / "critic.out").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
