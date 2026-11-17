"""Юнит-тесты драйвера ревизии TASK-hermes-20 (гейты шагов 4–5).

`eval/revise_step45_gates.py` — ревизия артефактов этапа по находкам
ГЕЙТОВ через механизм продукта: patch-сессия → apply_revision.py
(integrity) → перепрогон гейтов. Модель в тестах не вызывается:
run_session подменяется моком, отдающим JSON правок; apply_revision и
гейты — настоящие (детерминированные скрипты).

Покрытие:
- контракт CLI (dry-run, имя вне этапа → отказ);
- идемпотентность (зелёный артефакт не пересессится);
- доводка сломанного артефакта до зелёного одной правкой (реальный
  apply_revision + реальные гейты);
- честная деградация (правки отклоны → финал = черновик, провал);
- состав гейтов на всех артефактах этапа (дефект области действия).

Запуск: python3 -m unittest tests.test_task20 -v
"""

from __future__ import annotations

import importlib.util
import json
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
RSG = load_module("revise_step45_gates_test",
                  REPO_ROOT / "eval" / "revise_step45_gates.py")

BROKEN_COMMS = """# Коммуникационная стратегия (фикстура ревиссии)

## Ключевые сообщения

1. Сообщение без плана: запускаем комбинацию механизмов (ev-002).
"""

# Правка, которая доводит фикстуру до структур плана по существу:
# приоритеты P0–P2, контрольная группа, KPI, критерии остановки и
# приёмный чек-лист с ответами на 6 вопросов.
GOOD_PATCH = {
    "edits": [
        {
            "find": "1. Сообщение без плана: запускаем комбинацию "
                    "механизмов (ev-002).",
            "replace": (
                "1. Сообщение без плана: запускаем комбинацию "
                "механизмов (ev-002).\n\n"
                "## Приоритеты и последовательность\n\n"
                "Основание секции: ev-002 [аналог].\n\n"
                "- P0 — согласование решения с руководством.\n"
                "- P1 — пилот коммуникации с контрольной группой "
                "(holdout).\n"
                "- P2 — масштабирование на всю когорту.\n\n"
                "## Приёмный чек-лист (6 вопросов владельца)\n\n"
                "1. Что знаем / чего не знаем: знаем структуру оттока "
                "на аналоге (ev-002); не знаем триггер на сервисе.\n"
                "2. Какие решения: комбинация механизмов на "
                "утверждение.\n"
                "3. Что проверять первым и почему: первым — "
                "доставляемость, потому что канал может не выдержать "
                "адресной нагрузки.\n"
                "4. Деньги / команды / сроки: бюджет около нуля "
                "(перераспределение), команда коммуникаций, срок — "
                "квартал.\n"
                "5. Метрики успеха: KPI доставляемости не ниже "
                "broadcast-уровня.\n"
                "6. Когда остановить: критерии остановки — эффект "
                "таргетинга ниже порога за цикл.\n"
            ),
            "finding": "acceptance: нет секции приёмного чек-листа",
            "action": "apply",
        }
    ]
}


class TestCliContract(unittest.TestCase):
    """Контракт CLI драйвера ревизии."""

    def test_dry_run_exit_zero(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "eval"
                                 / "revise_step45_gates.py"),
             "--artifacts-dir", "eval/runs/t18-case/artifacts",
             "--dry-run"],
            capture_output=True, text=True, timeout=120, cwd=REPO_ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("strategy-comms.md", proc.stdout)
        self.assertIn("decisions.md", proc.stdout)
        self.assertIn("acceptance", proc.stdout)
        self.assertIn("apply_revision", proc.stdout)

    def test_name_outside_stage45_refused(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "eval"
                                 / "revise_step45_gates.py"),
             "--artifacts-dir", "eval/runs/t18-case/artifacts",
             "--names", "options.md", "--dry-run"],
            capture_output=True, text=True, timeout=120, cwd=REPO_ROOT)
        self.assertEqual(proc.returncode, 1, proc.stdout)

    def test_gate_scope_covers_stage(self):
        # Состав гейтов драйвера полного пути после фикса области:
        # acceptance + actionability на каждом артефакте этапа 4–5.
        task = RFC.TASKS["demo-retention"]
        with tempfile.TemporaryDirectory() as tmp:
            for name in RFC.STEP45_ARTIFACTS:
                names = [g for g, _ in RFC.gates_for_artifact(
                    name, Path(tmp), task)]
                self.assertIn("acceptance", names, name)
                self.assertIn("actionability", names, name)


class TestRevisionLoop(unittest.TestCase):
    """Цикл ревизии: идемпотентность, доводка, честная деградация."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.artifacts = self.tmp / "artifacts"
        self.artifacts.mkdir(parents=True)
        self.work = self.tmp / "run"
        self.task = RFC.TASKS["demo-retention"]
        self.sessions: list[str] = []

    def _mock_session(self, reply: str):
        # Мок ставится на ТОТ ЖЕ экземпляр модуля, которым пользуется
        # драйвер ревизии (revise_step45_gates импортирует run_full_case
        # independently — патч чужого экземпляра не действует, и тест
        # ушёл бы в настоящую сессию).
        def fake(prompt, out_dir, name, model, timeout, label):
            self.sessions.append(name)
            return 0, reply
        RSG.RFC.run_session = fake  # type: ignore[assignment]
        RFC.run_session = fake  # type: ignore[assignment]

    def _revise(self, name: str, rounds: int = 2):
        manifest: list[str] = []
        ok = RSG.revise_artifact(name, self.artifacts, self.task,
                                 self.work, 60, manifest, rounds)
        return ok, manifest

    def test_green_artifact_not_revisited(self):
        # Идемпотентность: зелёный артефакт не пересессится (урок t11).
        (self.artifacts / "strategy-comms.md").write_text(
            "# Коммуникационная стратегия\n\n"
            "## Приоритеты и последовательность\n\n"
            "Основание секции: ev-002 [аналог].\n\n"
            "- P0 — согласование.\n- P1 — пилот с контрольной группой "
            "(holdout).\n- P2 — масштаб.\n\n"
            "## Приёмный чек-лист (6 вопросов владельца)\n\n"
            "1. Что знаем / чего не знаем: знаем; не знаем.\n"
            "2. Какие решения: комбинация на утверждение.\n"
            "3. Что проверять первым и почему: первым — канал.\n"
            "4. Деньги / команды / сроки: бюджет около нуля, команда, "
            "квартал.\n"
            "5. Метрики успеха: KPI доставляемости.\n"
            "6. Когда остановить: критерии остановки — эффект ниже "
            "порога.\n",
            encoding="utf-8")

        def fail(*args, **kwargs):
            self.fail("сессия запущена на зелёном артефакте")
        # Страж на ОБА экземпляра модуля (тестовый и тот, что внутри
        # драйвера ревизии) — иначе настоящая сессия ушла бы в API.
        RSG.RFC.run_session = fail  # type: ignore[assignment]
        RFC.run_session = fail  # type: ignore[assignment]
        ok, manifest = self._revise("strategy-comms.md")
        self.assertTrue(ok)
        self.assertTrue(any("уже зелёный" in line for line in manifest))
        self.assertEqual(self.sessions, [])

    def test_broken_artifact_revised_to_green(self):
        # Реальный цикл: мок сессии отёт JSON правок → apply_revision
        # (настоящий) → гейты (настоящие) зелёные.
        (self.artifacts / "strategy-comms.md").write_text(BROKEN_COMMS,
                                                          encoding="utf-8")
        self._mock_session(json.dumps(GOOD_PATCH, ensure_ascii=False))
        ok, manifest = self._revise("strategy-comms.md")
        self.assertTrue(ok, "\n".join(manifest))
        self.assertEqual(len(self.sessions), 1)
        self.assertTrue(any("гейты зелёные (раунд 1)" in line
                            for line in manifest))
        text = (self.artifacts / "strategy-comms.md").read_text(
            encoding="utf-8")
        self.assertIn("Приёмный чек-лист", text)
        self.assertIn("P0", text)
        # Отчёт точечных правок и бэкап черновика — на диске.
        self.assertTrue((self.artifacts
                         / "strategy-comms.md.critic-backup").is_file())
        report = self.work / "strategy-comms" / "revision-report.md"
        self.assertTrue(report.is_file())
        self.assertIn("applied=1", report.read_text(encoding="utf-8"))

    def test_rejected_patch_degrades_honestly(self):
        # Правки отклоны → apply_revision пасует в черновик (0 applied)
        # → драйвер честно фиксирует провал, артефакт не потерян.
        (self.artifacts / "strategy-comms.md").write_text(BROKEN_COMMS,
                                                          encoding="utf-8")
        rejected = {"edits": [{"find": "1. Сообщение без плана: "
                                        "запускаем комбинацию механизмов "
                                        "(ev-002).",
                               "replace": "…",
                               "finding": "acceptance",
                               "action": "reject",
                               "reason": "находка отклонена"}]}
        self._mock_session(json.dumps(rejected, ensure_ascii=False))
        ok, manifest = self._revise("strategy-comms.md", rounds=2)
        self.assertFalse(ok)
        # Честная деградация видна в журнале: правки отклоны →
        # apply_revision пасует в черновик (fallback=yes), раунды
        # израсходованы, артефакт не потерян.
        self.assertTrue(any("fallback=yes" in line for line in manifest),
                        "\n".join(manifest))
        self.assertTrue(any("гейты не зелёные" in line
                            for line in manifest))
        self.assertEqual(
            (self.artifacts / "strategy-comms.md").read_text(
                encoding="utf-8"), BROKEN_COMMS)

    def test_heading_rename_rejected_by_integrity(self):
        # Регресс класса «переименование заголовка» (прецеденты: H-C2
        # TASK-12 и живой прогон TASK-hermes-20 — три раунда
        # verification-plan ушли на него): integrity-гейт требует
        # сохранения всех заголовков черновика, правка-переименование
        # откатывается целиком, артефакт остаётся дословным.
        (self.artifacts / "strategy-comms.md").write_text(BROKEN_COMMS,
                                                          encoding="utf-8")
        rename = {"edits": [{
            "find": "## Ключевые сообщения",
            "replace": "## Приёмный чек-лист (6 вопросов владельца)",
            "finding": "acceptance: нет секции чек-листа",
            "action": "apply"}]}
        self._mock_session(json.dumps(rename, ensure_ascii=False))
        ok, manifest = self._revise("strategy-comms.md", rounds=1)
        self.assertFalse(ok)
        self.assertTrue(any("integrity=BROKEN" in line
                            for line in manifest), "\n".join(manifest))
        self.assertIn("## Ключевые сообщения",
                      (self.artifacts / "strategy-comms.md").read_text(
                          encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
