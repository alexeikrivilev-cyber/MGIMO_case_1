"""Юнит-тесты гейта статического анализа типов (TASK-hermes-17 §31.3).

`scripts/check_pyright.py` — предохранитель «механический класс,
который pytest не видит» (кандидат ретро TASK-15 №2, §30.3). Шов под
тестом — CLI целиком (субпроцесс): коды возврата, фильтр названных
исключений, негативный контроль (гейт, который не ловит type error
на синтетике, бесполезен).

Без npx/node тесты пропускаются (как тесты хука без node): инструмент
внешний, а не часть репозитория.

Запуск: python3 -m unittest tests.test_pyright_gate -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "check_pyright.py"

NX = shutil.which("npx") or ""

CLEAN = '''"""Чистый файл-проба."""


def add(a: int, b: int) -> int:
    return a + b
'''

BROKEN = '''"""Файл с тип-ошибкой (негативный контроль)."""


def f(x: int) -> int:
    return "not an int"
'''


def run_gate(text: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.py"
        path.write_text(text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(GATE), str(path)],
            capture_output=True, text=True, timeout=300)


@unittest.skipUnless(NX, "npx не в окружении — pyright вызывается через npx")
class TestPyrightGate(unittest.TestCase):
    def test_clean_file_passes(self):
        proc = run_gate(CLEAN)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("находок нет", proc.stdout)

    def test_type_error_flagged(self):
        proc = run_gate(BROKEN)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("находка", proc.stderr)

    def test_named_exceptions_filtered_not_failures(self):
        # Предсуществующие ошибки резолва в run_critic.py (§30.3) —
        # названные исключения: гейт зелёный, но печатает их явно.
        proc = subprocess.run(
            [sys.executable, str(GATE), "scripts/run_critic.py"],
            capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.count("названное исключение"), 2)
        self.assertIn("arg_chunk", proc.stdout)
        self.assertIn("run_label", proc.stdout)

    def test_usage_errors(self):
        proc = subprocess.run([sys.executable, str(GATE)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1)
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "nope.py")
            proc = subprocess.run([sys.executable, str(GATE), missing],
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
