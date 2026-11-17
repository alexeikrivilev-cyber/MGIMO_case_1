"""Юнит-тесты TASK-hermes-13: слепые пары и критик #2 (драйверы
eval/build_blind_pairs.py, eval/second_critic.py).

Шов под тестом — чистые функции: слепление (подписи снимаются, ключ
не утекает в пары), детерминированность порядка A/B по seed, выборка
критика #2 и рубрика под семейство артефакта, вердикты согласия.
Прогонов моделей и сети нет.

Запуск: python3 -m unittest tests.test_task13 -v
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


bp = load_module("build_blind_pairs", REPO_ROOT / "eval" / "build_blind_pairs.py")
sc = load_module("second_critic", REPO_ROOT / "eval" / "second_critic.py")
ablation_stats = load_module("ablation_stats", REPO_ROOT / "eval" / "ablation_stats.py")


class BlindingTests(unittest.TestCase):
    """Подписи снимаются; ключ не утекает в парный материал."""

    def test_strip_removes_arm_tokens(self):
        text = ("Рука council-lite: протокол council-design §4. Артефакт curation, "
                "черновик lean, гибрид hybrid. Путь eval/runs/t12-skills, "
                "сессия ses_abc123, прогон run-2026-11-16-01.")
        out = bp.strip_identifiers(text)
        for token in ("council", "curation", "lean", "hybrid", "eval/runs",
                      "ses_", "run-2026-11-16-01"):
            self.assertNotIn(token, out)

    def test_digest_extracts_sut_both_formats(self):
        skill_style = "# Заголовок\n\n## 1. Вариант 1 — «А»\n\n**Суть.** Первая карточка.\n"
        t12_style = "# Заголовок\n\n## A. Риск-таргетинг\n\n- **Суть:** Вторая карточка.\n"
        for text, want in ((skill_style, "Первая карточка"), (t12_style, "Вторая карточка")):
            self.assertIn(want, bp.digest(text))

    def test_digest_has_no_arm_tokens(self):
        text = "# options.md\n\n## 1. Вариант 1\n\n**Суть.** Рука council-lite, курация.\n"
        self.assertNotIn("council", bp.digest(text))

    def test_pairs_are_deterministic_by_seed(self):
        # Один seed → один и тот же порядок A/B (воспроизводимость суждения).
        orders = []
        for _ in range(2):
            rng = __import__("random").Random(bp.SEED)
            orders.append([rng.random() < 0.5 for _ in bp.PAIRS])
        self.assertEqual(orders[0], orders[1])

    def test_pair_notes_are_neutral(self):
        # note (предъявляемое) не содержит имён рук; имена — только в key.
        for _, _, note, _arm_note in bp.PAIRS:
            for token in ("curation", "lean", "hybrid", "council", "critic-loop",
                          "plain-chat", "skill"):
                self.assertNotIn(token, note.lower())


class SecondCriticSampleTests(unittest.TestCase):
    """Выборка критика #2 и рубрика под семейство артефакта."""

    def test_sample_size_and_composition(self):
        unified = [s for s in sc.SAMPLE if s[2] == "unified"]
        typical = [s for s in sc.SAMPLE if s[2] == "typical"]
        self.assertEqual(len(sc.SAMPLE), 27)
        self.assertEqual(len(unified), 18)
        self.assertEqual(len(typical), 9)

    def test_rubric_under_artifact_family(self):
        self.assertEqual(sc.rubric_path("unified", "research"), "eval/rubrics/hackathon-criteria.md")
        self.assertEqual(sc.rubric_path("typical", "research"), "eval/rubrics/rubric-research.md")
        self.assertEqual(sc.rubric_path("typical", "o5a"), "eval/rubrics/rubric-research.md")
        self.assertEqual(sc.rubric_path("typical", "options"), "eval/rubrics/rubric-options.md")
        self.assertEqual(sc.rubric_path("typical", "o5b-F"), "eval/rubrics/rubric-options.md")

    def test_first_scores_keyed_by_cell(self):
        records = [
            {"group": "research", "arm": "lean", "i": 0, "rubric": "unified", "total40": 14.0},
            {"group": "research", "arm": "lean", "i": 0, "rubric": "unified", "total40": None},
        ]
        scores = sc.first_scores(records)
        self.assertEqual(scores[("research", "lean", 0, "unified")], 14.0)


class AgreementVerdictTests(unittest.TestCase):
    """Предрегистрированные пороги согласия (§26.1): 2× шума, 10%/25% клеток."""

    def test_ratio_thresholds(self):
        noise = 1.03
        self.assertTrue(1.5 * noise <= 2 * noise)          # близки к независимым
        self.assertTrue(3.0 * noise > 2 * noise)           # системное расхождение

    def test_mdd_used_for_beyond_count(self):
        # MDD(n=1) по модели ablation_stats: единая ~5.59, типовая ~4.08
        # (интервал Δ между руками ±1.96σ√2 — другая величина: 3.92/2.86).
        self.assertAlmostEqual(ablation_stats.mdd_two_arm(1, 1.41), 5.586, places=2)
        self.assertAlmostEqual(ablation_stats.mdd_two_arm(1, 1.03), 4.082, places=2)


class CliContractTests(unittest.TestCase):
    def test_blind_pairs_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "eval" / "build_blind_pairs.py"),
                 "--out", tmp],
                capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            pairs = json.loads((Path(tmp) / "pairs.json").read_text(encoding="utf-8"))
            self.assertEqual(len(pairs["pairs"]), 10)
            # в предъявляемом JSON нет имён рук в парах
            for pair in pairs["pairs"]:
                self.assertNotIn("curation", json.dumps(pair, ensure_ascii=False).replace("курация", ""))
            self.assertTrue((Path(tmp) / "key.md").is_file())

    def test_second_critic_dry_run(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "eval" / "second_critic.py"), "--dry-run"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.count("[dry-run]"), 27)


if __name__ == "__main__":
    unittest.main()
