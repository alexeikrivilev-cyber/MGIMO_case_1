"""Юнит-тесты механики самоулучшения навыков (TASK-hermes-14 §2):
product/agent/skill_evolve.py + skill_guard.py + skill_ledger.py.

Шов под тестом — CLI целиком (субпроцесс с STRATEGY_AGENT_ROOT на
временном корне): так проверяются и коды возврата, и предохранитель, и
откат fail-closed. Прогонов модели и сети нет.

Запуск: python3 -m unittest tests.test_skill_evolution -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "product" / "agent" / "skill_evolve.py"

SKILL_BODY = """---
name: testskill
description: Навык для тестов самоулучшения.
---

# Навык testskill

## Метод

ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА — единственная в файле.
"""

MEASUREMENTS_BODY = """# measurements.md — журнал измерений (тестовая копия)

## 28. Самоулучшение навыков (предрегистрация)

Гипотеза H-SI1: агент, который фиксирует и правит свои инструкции по
замеру, даёт лучший артефакт на N-й итерации. Вердикт: не запускалось.
Итог: Δ и MDD — в §28.2 после прогонов.
"""

ARTIFACT_BODY = """# Артефакт замера (тест)

Вердикт по предрегистрации: прироста нет. Δ = -0.67, MDD(n=1) = 4.08.
Итог: клетка ниже порога.
"""

NOTES_BODY = """# Просто заметки

Здесь записаны мысли о работе. Никаких выводов, таблиц и расчётов.
"""


class SkillEvolutionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "knowledge" / "skills" / "testskill").mkdir(parents=True)
        (self.root / "knowledge" / "skills" / "testskill" / "SKILL.md").write_text(
            SKILL_BODY, encoding="utf-8")
        research = self.root / "docs" / "research"
        research.mkdir(parents=True)
        (research / "measurements.md").write_text(MEASUREMENTS_BODY, encoding="utf-8")
        (research / "artifact.md").write_text(ARTIFACT_BODY, encoding="utf-8")
        (research / "notes.md").write_text(NOTES_BODY, encoding="utf-8")
        self.env = dict(os.environ, STRATEGY_AGENT_ROOT=str(self.root))
        self.skill_file = self.root / "knowledge" / "skills" / "testskill" / "SKILL.md"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            capture_output=True, text=True, env=self.env, timeout=120)

    def ledger_entries(self) -> list[dict]:
        path = self.root / "knowledge" / "skills" / ".evolution" / "ledger.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # --- предохранитель: самоулучшение только по замеру -------------------

    def test_propose_without_evidence_refused(self) -> None:
        res = self.run_cli("propose", "--skill", "testskill",
                           "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                           "--new", "новая строка", "--evidence", "")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertIn("evidence обязателен", res.stderr)

    def test_propose_with_missing_artifact_refused(self) -> None:
        res = self.run_cli("propose", "--skill", "testskill",
                           "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                           "--new", "новая строка",
                           "--evidence", "eval/runs/нет-такого/art.md")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertIn("не резолвится", res.stderr)

    def test_propose_with_non_measurement_file_refused(self) -> None:
        """Негативный контроль: файл есть, но это не артефакт замера."""
        res = self.run_cli("propose", "--skill", "testskill",
                           "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                           "--new", "новая строка",
                           "--evidence", "docs/research/notes.md")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertIn("не похож на артефакт замера", res.stderr)

    def test_propose_with_measurements_section_allowed(self) -> None:
        res = self.run_cli("propose", "--skill", "testskill",
                           "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                           "--new", "новая строка",
                           "--evidence", "measurements.md §28")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("--- a/SKILL.md", res.stdout)  # дифф напечатан
        self.assertEqual(self.skill_file.read_text(encoding="utf-8"), SKILL_BODY,
                         "propose не имеет права менять файл")

    def test_broken_section_ref_refused_without_file_fallback(self) -> None:
        """Регрессия (живая проба 2026-11-17): «measurements.md §99» проходил
        через резолв всего файла — битая точная ссылка не имеет права
        молча деградировать до «файл-то есть»."""
        res = self.run_cli("propose", "--skill", "testskill",
                           "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                           "--new", "новая строка",
                           "--evidence", "measurements.md §99")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertIn("§99", res.stderr)
        self.assertIn("не найдена", res.stderr)

    def test_apply_with_artifact_allowed(self) -> None:
        res = self.run_cli("apply", "--skill", "testskill",
                           "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                           "--new", "НОВАЯ СТРОКА ПО ЗАМЕРУ",
                           "--evidence", "docs/research/artifact.md")
        self.assertEqual(res.returncode, 0, res.stderr)
        text = self.skill_file.read_text(encoding="utf-8")
        self.assertIn("НОВАЯ СТРОКА ПО ЗАМЕРУ", text)
        self.assertNotIn("ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА", text)
        entries = self.ledger_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["action"], "patch")
        self.assertEqual(entries[0]["skill"], "testskill")
        self.assertTrue(entries[0]["before"])
        self.assertTrue(entries[0]["after"])

    def test_apply_refused_without_evidence_leaves_file(self) -> None:
        before = self.skill_file.read_text(encoding="utf-8")
        res = self.run_cli("apply", "--skill", "testskill",
                           "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                           "--new", "НОВАЯ СТРОКА",
                           "--evidence", "docs/research/notes.md")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertEqual(self.skill_file.read_text(encoding="utf-8"), before)
        self.assertEqual(self.ledger_entries(), [])

    def test_apply_nonunique_old_refused(self) -> None:
        """«testskill» в файле дважды (frontmatter + заголовок) — отказ."""
        res = self.run_cli("apply", "--skill", "testskill", "--old", "testskill",
                           "--new", "otherskill",
                           "--evidence", "docs/research/artifact.md")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertIn("единичность", res.stderr)

    # --- откат и целостность ----------------------------------------------

    def test_rollback_restores_bytes(self) -> None:
        self.run_cli("apply", "--skill", "testskill",
                     "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                     "--new", "НОВАЯ СТРОКА ПО ЗАМЕРУ",
                     "--evidence", "docs/research/artifact.md")
        entry_id = self.ledger_entries()[0]["id"]
        res = self.run_cli("rollback", "--entry", entry_id, "--actor", "po",
                           "--reason", "тест отката")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.skill_file.read_text(encoding="utf-8"), SKILL_BODY)
        rollbacks = [e for e in self.ledger_entries() if e["action"] == "rollback"]
        self.assertEqual(len(rollbacks), 1)
        self.assertEqual(rollbacks[0]["parent"], entry_id)
        self.assertEqual(rollbacks[0]["actor"], "po")

    def test_rollback_unknown_entry_fails_closed(self) -> None:
        res = self.run_cli("rollback", "--entry", "deadbeef1234")
        self.assertEqual(res.returncode, 4, res.stderr)
        self.assertIn("fail-closed", res.stderr)

    def test_rollback_missing_blob_fails_closed(self) -> None:
        """Урок Hermes, воспроизведён: потеря блоба = отказ, а не
        «частичный откат»."""
        self.run_cli("apply", "--skill", "testskill",
                     "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                     "--new", "НОВАЯ СТРОКА ПО ЗАМЕРУ",
                     "--evidence", "docs/research/artifact.md")
        entry = self.ledger_entries()[0]
        blob = self.root / "knowledge" / "skills" / ".evolution" / "blobs" / entry["before"][0]["sha256"]
        blob.unlink()
        res = self.run_cli("rollback", "--entry", entry["id"])
        self.assertEqual(res.returncode, 4, res.stderr)
        self.assertIn("потерян", res.stderr)
        self.assertIn("НОВАЯ СТРОКА ПО ЗАМЕРУ",
                      self.skill_file.read_text(encoding="utf-8"))

    def test_verify_detects_missing_blob(self) -> None:
        self.run_cli("apply", "--skill", "testskill",
                     "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                     "--new", "НОВАЯ СТРОКА ПО ЗАМЕРУ",
                     "--evidence", "docs/research/artifact.md")
        res = self.run_cli("verify")
        self.assertEqual(res.returncode, 0, res.stderr)
        entry = self.ledger_entries()[0]
        blob = self.root / "knowledge" / "skills" / ".evolution" / "blobs" / entry["after"][0]["sha256"]
        blob.unlink()
        res = self.run_cli("verify")
        self.assertEqual(res.returncode, 4, res.stderr)
        self.assertIn("потерян", res.stderr)

    def test_status_counts(self) -> None:
        self.run_cli("apply", "--skill", "testskill",
                     "--old", "ШАБЛОННАЯ СТРОКА ДЛЯ ПАТЧА",
                     "--new", "СТРОКА-А",
                     "--evidence", "docs/research/artifact.md")
        self.run_cli("apply", "--skill", "testskill",
                     "--old", "СТРОКА-А",
                     "--new", "СТРОКА-Б",
                     "--evidence", "docs/research/artifact.md")
        res = self.run_cli("status", "--skill", "testskill")
        self.assertEqual(res.returncode, 0, res.stderr)
        record = json.loads(res.stdout)
        self.assertEqual(record["patch_count"], 2)
        self.assertEqual(record["rollback_count"], 0)
        self.assertEqual(record["patch_generation"], 2)


if __name__ == "__main__":
    unittest.main()
