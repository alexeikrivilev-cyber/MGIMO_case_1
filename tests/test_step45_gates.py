"""Юнит-тесты гейтов шагов 4–5 (TASK-hermes-14 §3):
scripts/check_acceptance.py (приёмный чек-лист 6 вопросов, BRIEF п.27) и
scripts/check_transferability.py (переносимость оснований: аналоги ≠
причины; деньги аналога не переносятся).

Шов под тестом — CLI целиком (субпроцесс, временные файлы): проверяются
коды возврата и тексты нарушений. Негативные Controls обязательны: гейт,
который не ловит нарушение на синтетике, на артефактах бесполезен.

Запуск: python3 -m unittest tests.test_step45_gates -v
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ACCEPT = REPO_ROOT / "scripts" / "check_acceptance.py"
TRANSFER = REPO_ROOT / "scripts" / "check_transferability.py"

CHECKLIST_OK = """# Артефакт шага 4

## Приёмный чек-лист (6 вопросов владельца)

| # | Вопрос | Ответ |
|---|---|---|
| 1 | Что знаем / чего не знаем | Знаем структуру на аналоге (ev-002); не знаем данные сервиса [допущение] |
| 2 | Какие решения | Решение: сочетание вариантов 1 и 3 (ЧЕКПОИНТ 3) |
| 3 | Что проверять первым и почему | Проверять первым — И1 «Измеряемость»: без метрики пилоты слепые [допущение] |
| 4 | Деньги / команды / сроки | Бюджет около нуля [допущение]; команды и сроки — в разделе «Зависимости» |
| 5 | Метрики успеха | Метрика: 30-дневное удержание, вилки [прогноз], baseline ev-002 |
| 6 | Когда остановить | Остановить по порогу «не работает»; правило — в verification-plan.md |
"""

CHECKLIST_MISSING_STOP = CHECKLIST_OK.replace(
    "| 6 | Когда остановить | Остановить по порогу «не работает»; правило — в verification-plan.md |",
    "| 6 | Что ещё учесть | Разное |")

VIOLATION_CAUSAL = """# Артефакт

## Раздел

Отток стриминга вызван типом контракта и способом оплаты (IBM Telco Churn).
"""

VIOLATION_MONEY = """# Артефакт

## Раздел

ARPU аналога 500 руб в месяц задаёт ориентир экономики сервиса.
"""

CLEAN_WITH_MARKERS = """# Артефакт

## Раздел

На аналоге IBM Telco Churn month-to-month даёт 42.71% оттока [аналог].
Причина для стриминга — [гипотеза переносимости], не факт.
ARPU аналога 500 руб [аналог] — на сервис не переносится.
"""

QUESTION_LINES = """# Бриф

## Решающие вопросы

3. Переносимы ли драйверы оттока с аналога (IBM Telco Churn) на наш
сервис, и что для этого нужно?
4. Метрика доказательства для совета директоров?
"""

QUOTED = """# Артефакт

## Раздел

> Отток вызван контрактом (IBM Telco) — цитата запроса РП.
"""

FENCED_CHECKLIST = """# Артефакт

```
## Приёмный чек-лист (6 вопросов владельца)

1. что знаем: ...
2. какие решения: ...
3. проверять первым: ...
4. деньги: ...
5. метрики: ...
6. остановить: ...
```
"""


class AcceptanceGateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_gate(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(script), *args],
                              capture_output=True, text=True, timeout=60)

    def write(self, name: str, body: str) -> Path:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return path

    # --- check_acceptance -------------------------------------------------

    def test_full_checklist_passes(self) -> None:
        path = self.write("ok.md", CHECKLIST_OK)
        res = self.run_gate(ACCEPT, str(path))
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_missing_question_caught(self) -> None:
        path = self.write("bad.md", CHECKLIST_MISSING_STOP)
        res = self.run_gate(ACCEPT, str(path))
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("когда остановить", res.stderr)

    def test_no_section_caught(self) -> None:
        path = self.write("nosec.md", "# Артефакт\n\nТекст без чек-листа.\n")
        res = self.run_gate(ACCEPT, str(path))
        self.assertEqual(res.returncode, 2)
        self.assertIn("нет секции", res.stderr)

    def test_checklist_in_fence_not_counted(self) -> None:
        path = self.write("fenced.md", FENCED_CHECKLIST)
        res = self.run_gate(ACCEPT, str(path))
        self.assertEqual(res.returncode, 2)

    def test_usage_error(self) -> None:
        res = self.run_gate(ACCEPT)
        self.assertEqual(res.returncode, 1)

    def test_missing_file_usage_error(self) -> None:
        res = self.run_gate(ACCEPT, str(self.root / "нет.md"))
        self.assertEqual(res.returncode, 1)

    # --- check_transferability --------------------------------------------

    def test_marked_analog_lines_pass(self) -> None:
        path = self.write("clean.md", CLEAN_WITH_MARKERS)
        res = self.run_gate(TRANSFER, str(path))
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_causal_transfer_without_marker_caught(self) -> None:
        path = self.write("causal.md", VIOLATION_CAUSAL)
        res = self.run_gate(TRANSFER, str(path))
        self.assertEqual(res.returncode, 2)
        self.assertIn("аналоги ≠ причины", res.stderr)

    def test_money_transfer_without_marker_caught(self) -> None:
        path = self.write("money.md", VIOLATION_MONEY)
        res = self.run_gate(TRANSFER, str(path))
        self.assertEqual(res.returncode, 2)
        self.assertIn("денежные показатели аналога не переносятся", res.stderr)

    def test_question_lines_exempt(self) -> None:
        path = self.write("questions.md", QUESTION_LINES)
        res = self.run_gate(TRANSFER, str(path))
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_blockquote_exempt(self) -> None:
        path = self.write("quoted.md", QUOTED)
        res = self.run_gate(TRANSFER, str(path))
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_transfer_usage_error(self) -> None:
        res = self.run_gate(TRANSFER)
        self.assertEqual(res.returncode, 1)


if __name__ == "__main__":
    unittest.main()
