"""Юнит-тесты стенда О4: критик, A/B, метрики, бенчмарк DABstep.

Шов (seam) под тестом — контракт CLI и чистые функции парсинга:
скрипты запускаются отдельными процессами (как хук/человек в терминале),
сетевые вызовы и прогоны моделей не выполняются.

Запуск: python3 -m unittest tests.test_o4_scripts -v
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
EVAL_DIR = REPO_ROOT / "eval"
BENCH_DIR = REPO_ROOT / "eval" / "benchmarks" / "dabstep" / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(path: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
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


# --------------------------------------------------------------------------
# 1) scripts/run_critic.py — контракт CLI
# --------------------------------------------------------------------------


class RunCriticCliTests(unittest.TestCase):
    def test_missing_artifact_exit_2(self) -> None:
        proc = run_script(
            SCRIPTS_DIR / "run_critic.py",
            "--artifact", "/nonexistent.md",
            "--rubric", "eval/rubrics/hackathon-criteria.md",
            "--mode", "critic",
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("файл не найден", proc.stderr)

    def test_missing_key_exit_3(self) -> None:
        # STEPFUN_API_KEY вычищен в run_script; суррогатный ключ в env_extra
        # НЕ проходит — проверяем именно отсутствие.
        proc = run_script(
            SCRIPTS_DIR / "run_critic.py",
            "--artifact", "project/brief.md",
            "--rubric", "eval/rubrics/hackathon-criteria.md",
            "--mode", "critic",
        )
        self.assertEqual(proc.returncode, 3)
        self.assertIn("STEPFUN_API_KEY", proc.stderr)

    def test_bad_mode_argparse_exit_2(self) -> None:
        proc = run_script(
            SCRIPTS_DIR / "run_critic.py",
            "--artifact", "project/brief.md",
            "--rubric", "eval/rubrics/hackathon-criteria.md",
            "--mode", "bogus",
        )
        self.assertEqual(proc.returncode, 2)


class StateStepLabelTests(unittest.TestCase):
    """Метка «Шаг» для хука cost-append: выставление и точное восстановление."""

    def test_set_and_restore_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil_copy = (REPO_ROOT / "STATE.md").read_text(encoding="utf-8")
            (root / "STATE.md").write_text(shutil_copy, encoding="utf-8")
            module = load_module("run_critic_under_test", SCRIPTS_DIR / "run_critic.py")
            module.REPO_ROOT = root
            previous = module.set_state_step("О4: test-label")
            self.assertIsNotNone(previous)
            patched = (root / "STATE.md").read_text(encoding="utf-8")
            self.assertIn("## шаг\n\nО4: test-label", patched)
            module.restore_state_step(previous)
            self.assertEqual(
                (root / "STATE.md").read_text(encoding="utf-8"), shutil_copy
            )


# --------------------------------------------------------------------------
# 2) eval/run_ab.py — контракт CLI и префиксы промптов
# --------------------------------------------------------------------------


class RunAbCliTests(unittest.TestCase):
    def test_unknown_arm_exit_1(self) -> None:
        proc = run_script(
            EVAL_DIR / "run_ab.py",
            "--task", "demo-retention",
            "--feature", "options",
            "--arms", "bogus",
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("неизвестные руки", proc.stderr)

    def test_dry_run_lists_arms(self) -> None:
        proc = run_script(
            EVAL_DIR / "run_ab.py",
            "--task", "demo-retention",
            "--feature", "options",
            "--arms", "skill,critic-loop,council-lite",
            "--dry-run",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("[dry-run] skill", proc.stdout)
        self.assertIn("council-lite", proc.stdout)

    def test_reverse_order(self) -> None:
        module = load_module("run_ab_under_test", EVAL_DIR / "run_ab.py")
        arms = ["skill", "critic-loop", "council-lite"]
        self.assertEqual(list(reversed(arms)), arms[::-1])
        self.assertIn("council-lite", module.ARMS)
        # data-линза совета — на дешёвом семействе (routing-решение О3),
        # имена моделей — квалифицированные для opencode run --model.
        self.assertIn("stepfun/step-3.7-flash", module.ROLE_MODEL.values())
        self.assertIn("stepfun/step-5-preview", module.ROLE_MODEL.values())


# --------------------------------------------------------------------------
# 3) eval/run_critic_matrix.py — dry-run = 26 прогонов (13 × 2)
# --------------------------------------------------------------------------


class CriticMatrixTests(unittest.TestCase):
    def test_dry_run_covers_all_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # --out во временный каталог: dry-run не должен трогать
            # манифест реального прогона (это артефакт замера).
            proc = run_script(
                EVAL_DIR / "run_critic_matrix.py", "--dry-run", "--out", tmp
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[dry-run]", proc.stdout)
            manifest = Path(tmp) / "manifest.md"
            self.assertTrue(manifest.is_file())
            self.assertIn("Провалов: 0", manifest.read_text(encoding="utf-8"))
            module = load_module("matrix_under_test", EVAL_DIR / "run_critic_matrix.py")
            self.assertEqual(len(module.ARTIFACTS), 13)
            self.assertEqual(len(module.ARTIFACTS) * 2, 26)


# --------------------------------------------------------------------------
# 4) eval/score_arms.py — парсинг выходов и строк стоимости
# --------------------------------------------------------------------------


class ScoreArmsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module("score_arms_under_test", EVAL_DIR / "score_arms.py")

    def test_parse_critic_scores(self) -> None:
        text = (
            "## Оценки\n"
            "| Критерий | Проход 1 | Проход 2 | Баллы (×2, проход 2) |\n"
            "| 1. Проработанность | 4/5 | 3/5 | 6/10 |\n"
            "| 2. Масштаб использования нейротехнологий | 4/5 | 3/5 | 6/10 |\n"
            "Итого: 24 /40\n"
            "## Findings\n"
            "[важно] место → что не так → почему → что починит\n"
            "[незначительно] ещё одна\n"
        )
        parsed = self.module.parse_critic_scores(text)
        self.assertEqual(parsed["total40"], 24.0)
        self.assertEqual(parsed["findings"], 2)
        self.assertEqual(parsed["criteria"]["1. Проработанность"]["points"], 6.0)

    def test_cost_rows_for(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "COST.md").write_text(
                "<!-- cost-rows:begin -->\n"
                "| 2026-11-16 | ses_x | О4: ab-run-skill | step-5-preview | 1 | 2 | 0 | 0 | 0 | 0 | $0.10 |\n"
                "| 2026-11-16 | ses_y | О4: ab-run-critic-loop | step-5-preview | 1 | 2 | 0 | 0 | 0 | 0 | $0.25 |\n"
                "| 2026-11-16 | ses_z | О3: council | step-5-preview | 1 | 2 | 0 | 0 | 0 | 0 | $0.99 |\n"
                "<!-- cost-rows:end -->\n",
                encoding="utf-8",
            )
            self.module.REPO_ROOT = root
            usd, rows = self.module.cost_rows_for("О4: ab-run-skill")
            self.assertAlmostEqual(usd, 0.10)
            self.assertEqual(rows, 1)
            usd2, rows2 = self.module.cost_rows_for("О4: ab-run-")
            self.assertAlmostEqual(usd2, 0.35)
            self.assertEqual(rows2, 2)


# --------------------------------------------------------------------------
# 5) Бенчмарк DABstep — вендор-scorer и протокол агента
# --------------------------------------------------------------------------


class DabstepScorerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = load_module("dabstep_scorer_under_test", BENCH_DIR / "scorer.py")

    def test_reference_pairs(self) -> None:
        qs = self.scorer.question_scorer
        self.assertTrue(qs("SwiftCharge", "swiftcharge"))
        self.assertTrue(qs("E:346.49", "E:346.49"))
        self.assertTrue(qs("1, 2, 5", "5, 2, 1"))
        self.assertTrue(qs("0.120132", "0.1201"))
        self.assertTrue(qs("Not Applicable", "not applicable"))
        self.assertFalse(qs("NL", "BE"))


class DabstepAgentProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = load_module("dabstep_agent_under_test", BENCH_DIR / "agent.py")

    def test_extract_code_and_final(self) -> None:
        reply = "Вот код:\n```python\nprint(1 + 1)\n```"
        self.assertEqual(self.agent.extract_code(reply), "print(1 + 1)\n")
        self.assertIsNone(self.agent.extract_final(reply))
        final_reply = "FINAL: NL"
        self.assertEqual(self.agent.extract_final(final_reply), "NL")
        self.assertIsNone(self.agent.extract_code(final_reply))

    def test_extract_reply_falls_back_to_reasoning(self) -> None:
        message = {"content": "", "reasoning_content": "думаю…"}
        self.assertEqual(self.agent.extract_reply(message), "думаю…")

    def test_run_code_timeout_guard(self) -> None:
        with self.assertRaises(subprocess.TimeoutExpired):
            self.agent.run_code("import time; time.sleep(5)", Path("."), timeout=1)


if __name__ == "__main__":
    unittest.main()
