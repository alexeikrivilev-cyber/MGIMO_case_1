"""Юнит-тесты серии k=3 (TASK-hermes-11 §24.1, драйвер eval/k3_series.py).

Шов под тестом — чистые функции статистики и контракт CLI: t-интервалы
(не z!), интервал Δ по наблюдаемым sd, сбор артефактов цепочек,
предрегистрированное правило вердикта. Прогонов моделей и сети нет.

Запуск: python3 -m unittest tests.test_k3_series -v
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from unittest import mock
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


k3 = load_module("k3_series", REPO_ROOT / "eval" / "k3_series.py")
ablation_stats = load_module("ablation_stats", REPO_ROOT / "eval" / "ablation_stats.py")


class IntervalMathTests(unittest.TestCase):
    """При k=3 интервал по t (4.303), не по z (1.96) — иначе занижение ~2.2×."""

    def test_t_crit_k3_is_table_value(self):
        self.assertEqual(k3.t_crit(3), 4.303)
        self.assertEqual(k3.t_crit(2), 12.706)
        # при большом n — z-аппроксимация
        self.assertAlmostEqual(k3.t_crit(20), 1.959963984540054, places=6)

    def test_arm_summary_uses_t_not_z(self):
        st = k3.arm_summary([36.0, 38.0, 38.0], 1.03)
        self.assertEqual(st["n"], 3)
        self.assertAlmostEqual(st["mean"], 37.333333, places=4)
        self.assertAlmostEqual(st["sd"], 1.154701, places=4)
        # 4.303 * 1.1547 / sqrt(3) = 2.868; z-вариант дал бы 1.305
        self.assertAlmostEqual(st["ci95"], 2.868, places=2)
        self.assertGreater(st["ci95"], 1.96 * st["sd"] / 3 ** 0.5)

    def test_arm_summary_single_observation_has_no_ci(self):
        st = k3.arm_summary([39.0], 1.03)
        self.assertIsNone(st["sd"])
        self.assertIsNone(st["ci95"])

    def test_delta_ci_uses_observed_sds(self):
        # Δ(L3−L2) с наблюдаемыми sd: sqrt(sd1²/n1 + sd2²/n2)
        lo = k3.arm_summary([37.0, 37.0, 37.0], 1.03)  # sd=0
        hi = k3.arm_summary([36.0, 38.0, 40.0], 1.03)  # sd=2
        d = k3.delta_summary(lo, hi)
        self.assertAlmostEqual(d["delta"], 1.0, places=6)
        self.assertAlmostEqual(d["se"], (2.0 ** 2 / 3) ** 0.5, places=6)
        self.assertAlmostEqual(d["ci95"], 4.303 * (2.0 ** 2 / 3) ** 0.5, places=6)
        self.assertTrue(d["covers_zero"])

    def test_delta_covers_zero_flag(self):
        a = k3.arm_summary([30.0, 30.0, 30.0], 1.03)
        b = k3.arm_summary([40.0, 40.0, 40.0], 1.03)
        d = k3.delta_summary(a, b)
        self.assertFalse(d["covers_zero"])


class VerdictRuleTests(unittest.TestCase):
    """Предрегистрированное правило §24.1 (как §20.1/§22.2): |Δ| ≥ MDD —
    выше шума; 0.75–1× — граница; ниже — нет отличимого различия."""

    def test_thresholds(self):
        mdd = ablation_stats.mdd_two_arm(3, 1.03)  # 4.77 (типовая)
        self.assertEqual(ablation_stats.verdict(5.0, mdd), "выше шума")
        self.assertEqual(ablation_stats.verdict(4.0, mdd), "НА ГРАНИЦЕ")
        self.assertEqual(ablation_stats.verdict(2.0, mdd), "нет отличимого различия")
        self.assertEqual(ablation_stats.verdict(-5.0, mdd), "выше шума")


class ArtifactCollectionTests(unittest.TestCase):
    """Цепочки серии: final.md / final-1.md / final-2.md (конвенция --repeat)."""

    def test_collect_chain_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "demo-retention"
            (base / "L2").mkdir(parents=True)
            (base / "L3").mkdir(parents=True)
            (base / "L2" / "final.md").write_text("a", encoding="utf-8")
            (base / "L2" / "final-1.md").write_text("b", encoding="utf-8")
            # L3: только две цепочки из трёх — третья должна отсутствовать
            (base / "L3" / "final.md").write_text("c", encoding="utf-8")
            (base / "L3" / "final-2.md").write_text("d", encoding="utf-8")
            arts = k3.collect_artifacts(Path(tmp), "demo")
            self.assertEqual([p.name for p in arts["L2"]], ["final.md", "final-1.md"])
            self.assertEqual([p.name for p in arts["L3"]], ["final.md", "final-2.md"])
            self.assertEqual(len(arts["L4"]), 1)
            self.assertTrue(arts["L4"][0].is_file())


class ScoringCoverageTests(unittest.TestCase):
    """РЕГРЕСС: каждая цепочка генерации scored один раз на рубрику.

    Баг (найден при прогоне 2026-11-17): драйвер взял n=1 для L2/L3 и
    оценил только первую цепочку — серия k=3 выродилась в n=1 без всяких
    признаков. Тест фиксирует: вызовов критика = цепочки × рубрики.
    """

    def test_every_chain_is_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "demo-retention"
            (base / "L2").mkdir(parents=True)
            (base / "L3").mkdir(parents=True)
            for name in ("final.md", "final-1.md", "final-2.md"):
                (base / "L2" / name).write_text("a", encoding="utf-8")
                (base / "L3" / name).write_text("b", encoding="utf-8")
            (REPO_ROOT / "project").mkdir(exist_ok=True)
            calls: list[tuple[str, str]] = []

            def fake_run_critic(artifact, rubric, out_dir, tag):
                calls.append((Path(artifact).name, Path(rubric).name))
                return {"total40": 37.0}

            with mock.patch.object(k3, "run_critic", fake_run_critic):
                rc = k3.main(["--task", "demo", "--runs-dir", tmp])
            self.assertEqual(rc, 0)
            # L2 и L3: 3 цепочки × 2 рубрики; L4: 3 прогона × 2 рубрики
            # (артефакт продукта читается из репозитория — существует).
            l2 = [c for c in calls if c[0].startswith("final") and c[1] == "rubric-options.md"]
            self.assertEqual(len(l2), 3 * 2)
            names = {c[0] for c in calls}
            self.assertIn("final-2.md", names)  # третья цепочка обязательно


class CliTests(unittest.TestCase):
    def test_dry_run_lists_artifacts(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "eval" / "k3_series.py"), "--dry-run"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[dry-run] L2:", proc.stdout)


if __name__ == "__main__":
    unittest.main()
