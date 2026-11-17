"""Тесты проводки гейтов в TS-хук (TASK-hermes-15 П.4).

Контекст: в TASK-hermes-14 новые гейты (check_acceptance,
check_transferability) и кандидат check_skill_index намеренно НЕ были
проведены в `.opencode/plugins/strategy-hooks.ts` — хук не покрыт
тестами, а сломать его = сломать живую проверку всех будущих сессий.
Здесь появляется недостающий тест: python-проба через node грузит
настоящий хук, имитирует запись файла и проверяет, что нужный гейт
запустился и показал свой exit-код (TASK-hermes-14: «сессия, пишущая
нарушающий артефакт → хук должен показать отказ»).

Прогонов модели и сети нет: гейты — детерминированные скрипты.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or ""
PROBE = REPO_ROOT / "tests" / "hook_probe.mjs"

# Фикстура-нарушитель приёмного чек-листа: артефакт шага 4 без секции
# «приёмный чек-лист / 6 вопросов» (должен быть отказ check_acceptance).
ARTIFACT_NO_CHECKLIST = """# Продуктовая стратегия (фикстура пробы хука)

## Инициативы

- И1 «Измеряемость» — блокер пилотов: без выгрузки когорт пилоты слепы.
"""

# Фикстура с отвеченным чек-листом (допускается гейтом).
ARTIFACT_WITH_CHECKLIST = """# Продуктовая стратегия (фикстура пробы хука)

## Приёмный чек-лист (6 вопросов)

1. Что знаем / чего не знаем: знаем распределение оттока по тенур-бакетам;
   не знаем событие-триггер.
2. Какие решения: решение — комбинация вариантов «первые девяносто дней»
   и «риск-таргетинг».
3. Что проверять первым и почему: первым — выгрузка когорт, потому что
   пилот без данных слепой.
4. Деньги / команды / сроки: бюджет около нуля, команда данных, срок —
   квартал.
5. Метрики успеха: метрика удержания на тридцатый день, целевая вилка
   названа в вариантах.
6. Когда остановить: при опровержении — возврат варианта «контракт на
   входе» отдельным решением человека.
"""

# Фикстура-нарушитель переносимости: чужой датасет + причинная связка
# без маркера переноса (должен быть отказ check_transferability).
ARTIFACT_UNMARKED_TRANSFER = """# Драйверы (фикстура пробы хука)

Отток вызван типом контракта на датасете IBM Telco, поэтому на стриминге
работает тот же механизм.
"""

# Фикстура этапа 4–5, проходящая оба гейта «готовности к действию»:
# приоритеты P0–P2, контрольная группа, KPI, критерии остановки и
# приёмный чек-лист с ответами на 6 вопросов (дефект области действия
# TASK-hermes-20: этот состав теперь обязателен на КАЖДОМ артефакте
# этапа, не только на strategy-product.md).
ARTIFACT_STEP45_CLEAN = """# Коммуникационная стратегия (фикстура пробы хука)

## Приоритеты и последовательность

- P0 — согласование решения с руководством до конца квартала.
- P1 — пилот коммуникации с контрольной группой (holdout).
- P2 — масштабирование на всю когорту после замера.

## Приёмный чек-лист (6 вопросов владельца)

1. Что знаем / чего не знаем: знаем структуру оттока по тенур-бакетам
   на аналоге (ev-002); не знаем событие-триггер на сервисе.
2. Какие решения: комбинация механизмов «первые девяносто дней» и
   «риск-таргетинг» на утверждение.
3. Что проверять первым и почему: первым — доставляемость сообщений,
   потому что канал может не выдержать адресной нагрузки.
4. Деньги / команды / сроки: бюджет около нуля (перераспределение),
   команда коммуникаций, срок — квартал.
5. Метрики успеха: KPI доставляемости и открываемости не ниже
   broadcast-уровня.
6. Когда остановить: критерии остановки — эффект таргетинга ниже
   порога за цикл; spend возвращается на адресную коммуникацию.
"""


@unittest.skipUnless(NODE, "node не в окружении — хук грузится только через node")
class HookGateWiringTests(unittest.TestCase):
    """Гейты проведены в хук и показывают отказ на нарушающий артефакт."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project_dir = Path(self.tmp.name) / "project"
        self.project_dir.mkdir(parents=True)
        self._stray_skills: list[Path] = []

    def tearDown(self) -> None:
        # Страховка: если проба упала между созданием и удалением
        # тестового навыка, каталог не должен остаться в репозитории.
        for path in self._stray_skills:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
        stray = REPO_ROOT / "knowledge" / "skills" / "_hooktest"
        if stray.is_dir():
            shutil.rmtree(stray, ignore_errors=True)

    def _probe(self, path: Path) -> str:
        res = subprocess.run(
            [NODE, str(PROBE), str(path)],
            capture_output=True, text=True, timeout=180, cwd=str(REPO_ROOT),
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout.strip().splitlines()[-1])
        return payload["appended"]

    def _fixture(self, name: str, text: str) -> Path:
        path = self.project_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_sources_guard_still_runs_on_project_write(self) -> None:
        appended = self._probe(self._fixture("strategy-product.md", ARTIFACT_WITH_CHECKLIST))
        self.assertIn("[hook:sources-guard] check_sources.py → exit 0", appended)

    def test_acceptance_gate_refuses_missing_checklist(self) -> None:
        """Нарушающий артефакт шага 4 → хук показывает отказ acceptance."""
        appended = self._probe(self._fixture("strategy-product.md", ARTIFACT_NO_CHECKLIST))
        self.assertIn("[hook:acceptance-guard] check_acceptance.py → exit 2", appended)

    def test_acceptance_gate_passes_with_checklist(self) -> None:
        appended = self._probe(self._fixture("strategy-product.md", ARTIFACT_WITH_CHECKLIST))
        self.assertIn("[hook:acceptance-guard] check_acceptance.py → exit 0", appended)

    def test_transferability_gate_refuses_unmarked_transfer(self) -> None:
        appended = self._probe(self._fixture("strategy-comms.md", ARTIFACT_UNMARKED_TRANSFER))
        self.assertIn("[hook:transferability-guard] check_transferability.py → exit 2", appended)
        # TASK-hermes-20: приёмный чек-лист и управляемость винтят на
        # ВСЕХ артефактах этапа 4–5 — на comms гейты тоже запускаются
        # (прежний довод «только strategy-product» опровергнут вердиктом
        # владельца). Фикстура без чек-листа и плана → отказ обоих.
        self.assertIn("[hook:acceptance-guard] check_acceptance.py → exit 2", appended)
        self.assertIn("[hook:actionability-guard] check_actionability.py → exit 2", appended)

    def test_step45_gates_run_on_every_stage_artifact(self) -> None:
        """Регресс дефекта области действия (TASK-hermes-20): гейты
        чек-листа и управляемости запускаются на КАЖДОМ артефакте этапа
        4–5 — сломанный comms / verification / decisions больше не
        проходят мимо."""
        for name in ("strategy-comms.md", "verification-plan.md",
                     "decisions.md"):
            appended = self._probe(
                self._fixture(name, ARTIFACT_NO_CHECKLIST))
            self.assertIn("[hook:acceptance-guard] check_acceptance.py → exit 2",
                          appended)
            self.assertIn(
                "[hook:actionability-guard] check_actionability.py → exit 2",
                appended)

    def test_step45_clean_fixture_passes_both_gates(self) -> None:
        """Готовый к действию артефакт этапа проходит оба гейта без
        ложных тревог — на каждом из четырёх имён этапа."""
        for name in ("strategy-product.md", "strategy-comms.md",
                     "verification-plan.md", "decisions.md"):
            appended = self._probe(self._fixture(name,
                                                 ARTIFACT_STEP45_CLEAN))
            self.assertIn("[hook:acceptance-guard] check_acceptance.py → exit 0",
                          appended)
            self.assertIn(
                "[hook:actionability-guard] check_actionability.py → exit 0",
                appended)

    def test_skill_index_gate_refuses_skill_outside_index(self) -> None:
        """Навык вне индекса → хук показывает отказ skill-index (M2/M11)."""
        stray = REPO_ROOT / "knowledge" / "skills" / "_hooktest"
        self._stray_skills.append(stray)
        stray.mkdir(parents=True)
        (stray / "SKILL.md").write_text(
            "---\nname: _hooktest\ndescription: проба хука\n---\n\n# _hooktest\n",
            encoding="utf-8")
        try:
            appended = self._probe(stray / "SKILL.md")
        finally:
            shutil.rmtree(stray, ignore_errors=True)
        self.assertIn("[hook:skill-index-guard] check_skill_index.py → exit 2", appended)

    def test_skill_index_gate_passes_on_live_index(self) -> None:
        appended = self._probe(REPO_ROOT / "knowledge" / "index.md")
        self.assertIn("[hook:skill-index-guard] check_skill_index.py → exit 0", appended)

    # --- TASK-hermes-16 §30.1: гейты слепых зон (BRIEF п.27) -----------

    def test_ranges_gate_refuses_bare_range(self) -> None:
        """Диапазон без всякого основания в строке → хук показывает отказ."""
        artifact = ("# options.md (фикстура пробы хука)\n\n"
                    "## Вариант 1 — «Первые 90 дней»\n\nСуть.\n\n"
                    "| Срок до эффекта | квартал | 4–8 недель |\n")
        appended = self._probe(self._fixture("options.md", artifact))
        self.assertIn("[hook:ranges-guard] check_ranges.py → exit 2", appended)

    def test_complexity_gate_refuses_six_variants(self) -> None:
        """Шесть вариантов → хук показывает отказ (вердикт человека, пара 5)."""
        variants = "".join(
            f"## Вариант {i} — «Механика {i}»\n\nСуть варианта {i}.\n\n"
            for i in range(1, 7))
        artifact = ("# options.md (фикстура пробы хука)\n\n" + variants
                    + "## Таблица сравнения\n\n| Критерий | A | B |\n|---|---|---|\n"
                      "| Эффект | высокий | средний |\n| Срок | квартал | месяц |\n")
        appended = self._probe(self._fixture("options.md", artifact))
        self.assertIn("[hook:complexity-guard] check_complexity.py → exit 2", appended)

    def test_actionability_gate_refuses_missing_plan(self) -> None:
        """Артефакт шага 4 без элементов плана → хук показывает отказ."""
        appended = self._probe(
            self._fixture("strategy-product.md", ARTIFACT_NO_CHECKLIST))
        self.assertIn(
            "[hook:actionability-guard] check_actionability.py → exit 2", appended)

    def test_blindspot_gates_pass_on_clean_fixture(self) -> None:
        """Чистая фикстура проекта → все три гейта зелёные (нет ложных)."""
        artifact = ("# Продуктовая стратегия (фикстура пробы хука)\n\n"
                    "## Приоритеты и последовательность\n\n"
                    "- P0 — измеряемость\n"
                    "- P1 — пилот\n\n"
                    "Пилот с контрольной группой; A/B внутри тира.\n\n"
                    "## Метрики\n\n"
                    "| Метрика | Baseline | «Работает» | «Не работает» |\n"
                    "|---|---|---|---|\n"
                    "| D30 | 21% | ≥ 21% | < 21% |\n\n"
                    "Срок запуска 4–6 недель [оценка].\n")
        appended = self._probe(self._fixture("strategy-product.md", artifact))
        self.assertIn("[hook:ranges-guard] check_ranges.py → exit 0", appended)
        self.assertIn("[hook:complexity-guard] check_complexity.py → exit 0", appended)
        self.assertIn("[hook:actionability-guard] check_actionability.py → exit 0", appended)


if __name__ == "__main__":
    unittest.main()
