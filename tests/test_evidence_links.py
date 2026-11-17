"""Юнит-тесты гейта резолвимости доказательной цепи (TASK-hermes-8 §1).

Шов — контракт CLI, как в `tests/test_scripts.py`: скрипты запускаются
отдельными процессами, фикстуры — во временной директории. Плюс тесты
на реальные артефакты репозитория (критерий приёмки: гейт зелёный на
демо и held-out И ловит исходный дефект класса «ссылка есть,
содержания нет»).

Запуск: python3 -m unittest tests.test_evidence_links -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
EVAL_DIR = REPO_ROOT / "eval"

CHECK_LINKS = "check_evidence_links.py"
RECOMPUTE_TELCO = EVAL_DIR / "recompute_telco_slices.py"
RECOMPUTE_HELDOUT = EVAL_DIR / "recompute_heldout_slices.py"

TELCO_CSV = REPO_ROOT / "project" / "materials" / "telco-customer-churn.csv"
HELDOUT_CSV = (
    REPO_ROOT / "eval" / "tasks" / "heldout-growth-segment" / "artifacts"
    / "materials" / "bank-additional" / "bank-additional-full.csv"
)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_UNRESOLVED = 2
EXIT_MISMATCH = 1


def run_script(path: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(path), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
    )


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def write(self, rel_path: str, text: str) -> Path:
        path = self.tmp / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class CheckEvidenceLinksTests(TempDirTestCase):
    """Гейт «число → содержание записи evidence» на фикстурах."""

    def evidence_with(self, body: str) -> Path:
        return self.write("evidence/ev-002-x.md", (
            "# ev-002 — фикстура\n\n"
            "## Источник\n\n"
            "- URL: https://example.org/dataset.csv\n"
            "- Дата доступа: 2026-11-17\n\n"
            "## Тип\n\n"
            "- [x] факт\n\n"
            "## Факт\n\n" + body + "\n"
        ))

    def test_resolved_number_exit_0(self) -> None:
        self.evidence_with("- Отток month-to-month — 42.71% (n=3 875).\n")
        art = self.write("art.md", (
            "## Раздел\n\n"
            "- Драйвер оттока — контракт: 42.71% у month-to-month (ev-002).\n"
        ))
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS, "--files", str(art),
                          "--evidence", str(self.tmp / "evidence"))
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)

    def test_missing_number_exit_2(self) -> None:
        """Класс дефекта: ссылка есть, содержания за ней нет."""
        self.evidence_with("- Отток month-to-month — 42.71% (n=3 875).\n")
        art = self.write("art.md", (
            "## Раздел\n\n"
            "- Тонкий срез: внутри новичков 96.52% — month-to-month (ev-002).\n"
        ))
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS, "--files", str(art),
                          "--evidence", str(self.tmp / "evidence"))
        self.assertEqual(proc.returncode, EXIT_UNRESOLVED)
        self.assertIn("96.52", proc.stdout)
        self.assertIn("ev-002", proc.stdout)

    def test_marker_shields_scenario_number_exit_0(self) -> None:
        """[допущение]/[прогноз] grounding'ят число (как в check_sources B)."""
        self.evidence_with("- Отток month-to-month — 42.71% (n=3 875).\n")
        art = self.write("art.md", (
            "## Раздел\n\n"
            "- Симптом сервиса (34% → 21%) — цифры сценария демо "
            "[допущение]; драйвер — контракт 42.71% (ev-002).\n"
        ))
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS, "--files", str(art),
                          "--evidence", str(self.tmp / "evidence"))
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)

    def test_logical_line_join_resolves_across_wrap(self) -> None:
        """Перенос списка: число на второй физической строке, ссылка на первой."""
        self.evidence_with("- Когорта 0–3 мес: 31.94% всего оттока.\n")
        art = self.write("art.md", (
            "## Раздел\n\n"
            "- Когорта первых 3 месяцев даёт\n"
            "  31.94% всего оттока датасета (ev-002).\n"
        ))
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS, "--files", str(art),
                          "--evidence", str(self.tmp / "evidence"))
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)

    def test_table_cells_checked_independently(self) -> None:
        """В строке таблицы каждая ячейка резолвится своей записью."""
        self.evidence_with("- Отток month-to-month — 42.71%.\n")
        self.write("evidence/ev-003-y.md", (
            "# ev-003 — фикстура\n\n"
            "## Источник\n\n"
            "- URL: https://example.org/paper\n"
            "- Дата доступа: 2026-11-17\n\n"
            "## Тип\n\n"
            "- [x] факт\n\n"
            "## Факт\n\n"
            "- AUC-ROC 0.8411.\n"
        ))
        art = self.write("art.md", (
            "## Раздел\n\n"
            "| Вопрос | А | Б |\n"
            "|---|---|---|\n"
            "| Драйвер | 42.71% (ev-002) | SHAP-ранжинг (ev-003) |\n"
        ))
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS, "--files", str(art),
                          "--evidence", str(self.tmp / "evidence"))
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)

    def test_evidence_range_expands(self) -> None:
        """«ev-001…ev-003» резолвится записью из середины диапазона."""
        self.write("evidence/ev-001-a.md", (
            "# ev-001\n\n- URL: https://example.org/a\n"
            "- Дата доступа: 2026-11-17\n- [x] факт\n"
        ))
        self.evidence_with("- Отток month-to-month — 42.71%.\n")
        self.write("evidence/ev-003-b.md", (
            "# ev-003\n\n- URL: https://example.org/b\n"
            "- Дата доступа: 2026-11-17\n- [x] факт\n"
        ))
        art = self.write("art.md", (
            "## Раздел\n\n"
            "- Данные из записей ev-001…ev-003: отток 42.71% у month-to-month.\n"
        ))
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS, "--files", str(art),
                          "--evidence", str(self.tmp / "evidence"))
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)

    def test_section_crossref_not_a_claim(self) -> None:
        """«§2.1» — пересечение, не измерение."""
        self.evidence_with("- Отток month-to-month — 42.71%.\n")
        art = self.write("art.md", (
            "## Раздел\n\n"
            "- Возражение зафиксировано в Phase 3 §2.1 (ev-002); отток 42.71%.\n"
        ))
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS, "--files", str(art),
                          "--evidence", str(self.tmp / "evidence"))
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)

    def test_cli_requires_task_or_files(self) -> None:
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS)
        self.assertEqual(proc.returncode, EXIT_USAGE)

    def test_cli_missing_evidence_dir_exit_1(self) -> None:
        art = self.write("art.md", "- 42.71% (ev-002).\n")
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS, "--files", str(art),
                          "--evidence", str(self.tmp / "nope"))
        self.assertEqual(proc.returncode, EXIT_USAGE)


class CheckEvidenceLinksRepoTests(unittest.TestCase):
    """Гейт на реальных артефактах: приёмка + негативный контроль."""

    def test_real_artifacts_green(self) -> None:
        proc = run_script(SCRIPTS_DIR / CHECK_LINKS, "--task", "all")
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)
        self.assertIn("файлов проверено 13", proc.stdout)

    def test_negative_control_missing_slices(self) -> None:
        """Если у ev-002 убрать тонкие срезы — гейт обязан покраснеть."""
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence"
            evidence.mkdir()
            full = (REPO_ROOT / "project" / "evidence" / "ev-002-telco-dataset-stats.md")
            text = full.read_text(encoding="utf-8")
            cut = text.split("## Тонкие срезы")[0]
            self.assertNotIn("96.52", cut)
            (evidence / "ev-002-telco-dataset-stats.md").write_text(cut, encoding="utf-8")
            proc = run_script(
                SCRIPTS_DIR / CHECK_LINKS,
                "--files", str(REPO_ROOT / "project" / "research.md"),
                "--evidence", str(evidence),
            )
            self.assertEqual(proc.returncode, EXIT_UNRESOLVED)
            self.assertIn("96.52", proc.stdout)


class RecomputeTests(TempDirTestCase):
    """Скрипты пересчёта: арбитр между артефактом и первоисточником."""

    def test_telco_recompute_green(self) -> None:
        proc = run_script(RECOMPUTE_TELCO, "--out", str(self.tmp))
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)
        report = self.tmp / "recompute-telco.md"
        self.assertTrue(report.is_file())
        self.assertIn("расхождений 0", report.read_text(encoding="utf-8"))

    def test_heldout_recompute_green(self) -> None:
        proc = run_script(RECOMPUTE_HELDOUT, "--out", str(self.tmp))
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)
        report = self.tmp / "recompute-heldout.md"
        self.assertTrue(report.is_file())
        self.assertIn("расхождений 0", report.read_text(encoding="utf-8"))

    def test_telco_recompute_detects_source_drift(self) -> None:
        """Если CSV поехал — скрипт обязан вернуть exit 1 (не подгонять)."""
        tampered = self.tmp / "tampered.csv"
        text = TELCO_CSV.read_text(encoding="utf-8")
        lines = text.splitlines()
        # Одна запись: Month-to-month → Two year ломает ставки контракта.
        changed = False
        for i, line in enumerate(lines[1:], start=1):
            if ",Month-to-month," in line:
                lines[i] = line.replace(",Month-to-month,", ",Two year,", 1)
                changed = True
                break
        self.assertTrue(changed, "в фикстуре не нашлась запись month-to-month")
        tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")
        proc = run_script(RECOMPUTE_TELCO, "--csv", str(tampered), "--out", str(self.tmp))
        self.assertEqual(proc.returncode, EXIT_MISMATCH)
        self.assertIn("РАСХОЖДЕНИЕ", proc.stdout)

    def test_recompute_missing_csv_exit_2(self) -> None:
        proc = run_script(RECOMPUTE_TELCO, "--csv", str(self.tmp / "nope.csv"),
                          "--out", str(self.tmp))
        self.assertEqual(proc.returncode, 2)


class DabstepPowerTests(TempDirTestCase):
    """Дизайн эксперимента DABstep: детерминированный, без API."""

    def test_power_report_green(self) -> None:
        proc = run_script(EVAL_DIR / "dabstep_power.py", "--out", str(self.tmp))
        self.assertEqual(proc.returncode, EXIT_OK, proc.stdout + proc.stderr)
        report = (self.tmp / "dabstep-power.md").read_text(encoding="utf-8")
        self.assertIn("Δ=1 задача нужно ~39 прогонов на руку", report)
        self.assertIn("НЕ НАШ ИНСТРУМЕНТ".lower() in report.lower()
                      and "smoke-тест", report.lower())

    def test_power_json_has_required_table(self) -> None:
        run_script(EVAL_DIR / "dabstep_power.py", "--out", str(self.tmp))
        import json
        data = json.loads((self.tmp / "dabstep-power.json").read_text(encoding="utf-8"))
        self.assertEqual(data["required_runs_per_arm"]["1"], 39)
        self.assertEqual(data["required_runs_per_arm"]["2"], 10)
        self.assertEqual(data["required_runs_per_arm"]["3"], 5)
        self.assertAlmostEqual(data["p_hat"], 0.55, places=2)

    def test_power_missing_runs_exit_2(self) -> None:
        proc = run_script(EVAL_DIR / "dabstep_power.py",
                          "--runs-dir", str(self.tmp / "empty"),
                          "--out", str(self.tmp))
        self.assertEqual(proc.returncode, 2)


class CriticStep4Tests(TempDirTestCase):
    """Контракт CLI драйвера таргетирования на шаг 4 (без API-вызовов)."""

    def test_missing_draft_exit_2(self) -> None:
        proc = run_script(EVAL_DIR / "run_critic_step4.py",
                          "--draft", str(self.tmp / "nope.md"),
                          "--out", str(self.tmp))
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
