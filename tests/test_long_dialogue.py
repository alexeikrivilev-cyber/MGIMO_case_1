"""Юнит-тесты эксперимента TASK-hermes-23 (длинный диалог, руки A/B/C).

Что держится тестами:
1. **Повороты не дрейфуют.** Драйвер обязан отвечать ровно теми 12
   вопросами, что заморожены в предрегистрации (`PREREGISTRATION.md` §4) —
   иначе «подбор поворотов под результат» стал бы возможен незаметно.
2. **Anchor-таблица M1 живёт и различает округление и контрадикцию.**
3. **M2 переиспользует правила гейта**, а журнальная шапка ответа не
   создаёт ложных находок sources.
4. **Правило вердикта §6** применяется буквально (включая границу «>20 п.п.»,
   а не «≥20»).
5. **Промпт идёт через stdin, не argv** — регресс класса E2BIG (сид руки A
   ≈250 КБ против лимита 128 КБ на один argv-аргумент).

Запуск: python3 -m unittest tests.test_long_dialogue -v
"""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import re
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


DRIVER = load_module("run_long_dialogue_test", REPO_ROOT / "eval" / "run_long_dialogue.py")
SCORER = load_module("score_long_dialogue_test", REPO_ROOT / "eval" / "score_long_dialogue.py")

RUNS = REPO_ROOT / "eval" / "runs" / "t23-longdialogue"

# Сид руки B воспроизводим в любом окружении (TASK-hermes-25): живой
# `STATE.md` — файл разработки вне git, в свежем клоне его нет, поэтому
# `build_seed("B", …)` падает на закоммиченную копию
# `eval/runs/t23-longdialogue/B/state-as-used.md` — те самые байты, что
# лежали в сиде прогона (сверка с журналом — в
# `test_arm_b_seed_is_byte_identical_to_recorded_run`). Урок
# TASK-hermes-21 (тест, зелёный локально и красный у организатора)
# закрыт здесь по существу: тесты сида руки B не skip'ятся и не
# зависят от окружения.


class TestTurnsFrozen(unittest.TestCase):
    """12 поворотов драйвера = 12 поворотов предрегистрации (дословно)."""

    def test_preregistration_exists(self):
        self.assertTrue((RUNS / "PREREGISTRATION.md").is_file(),
                        "предрегистрация должна лежать в журнале и быть в git")
        self.assertTrue((RUNS / "prompt-template.md").is_file())

    def test_driver_turns_match_preregistration(self):
        text = (RUNS / "PREREGISTRATION.md").read_text(encoding="utf-8")
        quoted = re.findall(r"^\d+\.\s+.*?«(.+?)»", text, re.MULTILINE)
        # §4 предрегистрации: 12 пронумерованных поворотов в кавычках.
        self.assertEqual(len(quoted), 12, f"в предрегистрации не 12 поворотов: {quoted}")
        self.assertEqual(
            [DRIVER.TURNS[i] for i in range(1, 13)], quoted,
            "повороты драйвера разошлись с предрегистрацией — эксперимент несопоставим",
        )

    def test_turn_artifact_map_covers_all_turns(self):
        self.assertEqual(sorted(DRIVER.TURN_ARTIFACTS), list(range(1, 13)))
        for turn, blocks in DRIVER.TURN_ARTIFACTS.items():
            for _, rel in blocks:
                self.assertTrue((REPO_ROOT / rel).is_file(), f"поворот {turn}: нет файла {rel}")

    def test_a_seed_components_exist(self):
        for _, rel in DRIVER.A_COMPONENTS:
            self.assertTrue((REPO_ROOT / rel).is_file(), f"сид A: нет файла {rel}")
        # decisions.md в сид не входит — решение предрегистрации §3.
        self.assertNotIn("project/decisions.md", [rel for _, rel in DRIVER.A_COMPONENTS])


class TestSeedAssembly(unittest.TestCase):
    """Сид собирается из заявленных компонентов и кончается вопросом РП."""

    def test_arm_a_seed_has_all_artifacts_and_question(self):
        prompt, components = DRIVER.build_seed("A", 1)
        self.assertEqual(len(components), 1 + len(DRIVER.A_COMPONENTS))
        self.assertIn("----- НАЧАЛО ВХОДНЫХ ДАННЫХ -----", prompt)
        self.assertIn("----- КОНЕЦ ВХОДНЫХ ДАННЫХ -----", prompt)
        self.assertTrue(prompt.rstrip().endswith(DRIVER.TURNS[1]))
        self.assertIn("project/verification-plan.md", prompt)
        self.assertNotIn("project/decisions.md", prompt)

    def test_arm_b_seed_has_state_and_relevant_artifact(self):
        prompt, components = DRIVER.build_seed("B", 2)
        roles = [c["role"] for c in components]
        self.assertIn("состояние задачи", roles)
        self.assertTrue(prompt.rstrip().endswith(DRIVER.TURNS[2]))
        self.assertIn("project/options.md", prompt)

    def test_arm_c_seed_has_no_state(self):
        prompt, components = DRIVER.build_seed("C", 2)
        roles = [c["role"] for c in components]
        self.assertNotIn("состояние задачи", roles)
        self.assertNotIn("resume-карта", prompt)
        self.assertTrue(prompt.rstrip().endswith(DRIVER.TURNS[2]))

    def test_arm_b_seed_is_byte_identical_to_recorded_run(self):
        """Фолбэк даёт сид руки B побайтово тот, что был в прогоне.

        STATE.md — файл разработки вне git, поэтому в свежем клоне сид
        берётся из закоммиченной копии `B/state-as-used.md`. Ориентир —
        журнал прогона (`B/turn-01.json`): sha256 состояния и sha256
        полного промпта поворота 1. STATE_PATH подменяется отсутствующим
        путём — это ровно условие свежего клона; подмена (а не чтение
        dev-файла) делает тест детерминированным и в dev, где живой
        STATE.md уже уехал вперёд относительно прогона.
        """
        recorded = json.loads((RUNS / "B" / "turn-01.json").read_text(encoding="utf-8"))
        recorded_state_sha = next(
            c["sha256"] for c in recorded["components"] if c["role"] == "состояние задачи"
        )
        absent = RUNS / "B" / "__state_absent_in_fresh_clone__.md"
        self.assertFalse(absent.is_file())
        with mock.patch.object(DRIVER, "STATE_PATH", absent):
            prompt, components = DRIVER.build_seed("B", 1)
        state_comp = next(c for c in components if c["role"] == "состояние задачи")
        self.assertEqual(
            state_comp["sha256"], recorded_state_sha,
            "состояние в сиде B разошлось с тем, что лежало в сиде прогона",
        )
        self.assertEqual(
            DRIVER.sha256_text(prompt), recorded["prompt_sha256"],
            "полный промпт руки B в клоне разошёлся с промптом прогона",
        )
        self.assertEqual(len(prompt), recorded["prompt_chars"])

    def test_arm_b_seed_prefers_live_state_file_over_copy(self):
        """Обратная ветка фолбэка: живой STATE.md имеет приоритет.

        Условие клона разобрано в
        `test_arm_b_seed_is_byte_identical_to_recorded_run`; здесь
        проверяется приоритет dev-файла — иначе «удобная» копия молча
        подменила бы живое состояние и в dev. STATE_PATH подменяется
        временным файлом с известными байтами, поэтому тест одинаков в
        dev и в клоне.
        """
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "STATE.md"
            live_text = "# живое состояние задачи\n\nшаг 0 — рамка\n"
            live.write_text(live_text, encoding="utf-8")
            with mock.patch.object(DRIVER, "STATE_PATH", live):
                prompt, components = DRIVER.build_seed("B", 3)
        state_comp = next(c for c in components if c["role"] == "состояние задачи")
        self.assertEqual(state_comp["sha256"], DRIVER.sha256_text(live_text),
                         "при живом STATE.md сид обязан брать его, а не копию")
        self.assertIn("живое состояние задачи", prompt)

    def test_arms_differ_only_by_state_bridge_on_same_turn(self):
        """B и C на одном повороте различаются ТОЛЬКО блоком состояния.

        Проверка по-настоящему, не по skip: выкинув из сида B блок
        состояния и вернув артефакту его номер, получаем сид C
        байт-в-байт. Если в сид B протечёт что-то ещё (история, мета,
        лишний артефакт) или сид C потеряет артефакт — строки разойдутся.
        """
        prompt_b, _ = DRIVER.build_seed("B", 9)
        prompt_c, _ = DRIVER.build_seed("C", 9)
        self.assertIn("СОСТОЯНИЕ ЗАДАЧИ", prompt_b)
        self.assertNotIn("СОСТОЯНИЕ ЗАДАЧИ", prompt_c)
        # кроме моста состояния, сид B и C на поворот 9 — один и тот же артефакт
        self.assertIn("project/strategy-comms.md", prompt_b)
        self.assertIn("project/strategy-comms.md", prompt_c)
        start = prompt_b.index("[1] СОСТОЯНИЕ ЗАДАЧИ")
        end = prompt_b.index("[2] АРТЕФАКТ — КОММУНИКАЦИОННАЯ СТРАТЕГИЯ")
        b_without_state = prompt_b[:start] + "[1] " + prompt_b[end + len("[2] "):]
        self.assertEqual(b_without_state, prompt_c,
                         "сид B и C на одном повороте различаются не только мостом состояния")

    def test_prompt_passed_via_stdin_not_argv(self):
        """Регресс E2BIG: промпт ~250 КБ одним argv упал бы на MAX_ARG_STRLEN."""
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            seen["input"] = kwargs.get("input")
            proc = mock.Mock()
            proc.stdout = json.dumps(
                {"type": "text", "sessionID": "ses_test", "part": {"type": "text", "text": "ок"}}
            ) + "\n"
            proc.stderr = ""
            proc.returncode = 0
            return proc

        with mock.patch.object(DRIVER.subprocess, "run", side_effect=fake_run):
            DRIVER.run_opencode("промпт " * 10, None, 60)
        self.assertEqual(seen["input"], "промпт " * 10, "промпт должен идти через stdin")
        self.assertNotIn("промпт", seen["cmd"], "промпт не должен быть argv-аргументом")

    def test_answer_record_metadata_is_blockquote(self):
        """Журнальная шапка не должна давать находок гейта sources.

        Гейт исключает блокцитаты из проверки — поэтому шапка поворота
        (вопрос, sessionID, статус) идёт блокцитатой, и проверяется ровно
        то, что ответил агент. Прогон — субпроцессом: правило гейта не
        копируется в тест (один дом факта).
        """
        record = DRIVER.answer_record_text(
            "A", 5, "ses_test", "OK", 1,
            "Экономика: при оттоке 30% когорта теряет больше подписчиков [прогноз].",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "turn-05.answer.md"
            path.write_text(record, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "check_sources.py"), str(path)],
                capture_output=True, text=True, timeout=120,
            )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("нарушений нет", proc.stdout)


class TestM1Anchors(unittest.TestCase):
    """Контрадикция vs округление vs число из вопроса РП."""

    def score(self, answer: str, question: str = "") -> dict:
        return SCORER.score_m1(answer, question)

    def test_frozen_values_are_ok(self):
        result = self.score(
            "Удержание на 30-й день упало с 34% до 21% (project/brief.md); "
            "на аналоге отток 26.54%, в когорте 0–3 мес — 56.21% (ev-002); "
            "AUC 0.84 (ev-003); 2.1 млн подписчиков."
        )
        self.assertEqual(result["contradictions"], 0, result["contradiction_details"])
        self.assertGreaterEqual(result["ok"], 5)

    def test_near_miss_is_contradiction(self):
        result = self.score("Удержание упало до 24%, на аналоге отток 25%.")
        values = sorted(c["value"] for c in result["contradiction_details"])
        self.assertEqual(values, [24.0, 25.0])
        self.assertEqual(result["contradictions"], 2)

    def test_numbers_from_question_excluded(self):
        question = DRIVER.TURNS[5]
        result = self.score("Пересчитываю: было 21%, станет 30%.", question)
        self.assertEqual(result["claims"], 0)

    def test_structural_and_date_numbers_skipped(self):
        result = self.score("В окне 0–3 мес, 2026 год, бакет 49+, циклов 1–2.")
        self.assertEqual(result["claims"], 0)
        # «90 дней» — не шум, а anchor-окно пилота: считается и сходится.
        pilot = self.score("Пилот идёт в окне 90 дней.")
        self.assertEqual(pilot["contradictions"], 0)
        self.assertEqual(pilot["ok"], 1)

    def test_rounding_is_not_contradiction(self):
        result = self.score("Отток 26.5% против 42.7%; AUC 0.84.")
        self.assertEqual(result["contradictions"], 0, result["contradiction_details"])

    def test_anchor_table_is_complete(self):
        for anchor in SCORER.ANCHORS:
            self.assertTrue(anchor["meaning"], f"anchor {anchor['value']} без смысла")
            self.assertTrue(anchor["source"], f"anchor {anchor['value']} без источника")
        values = [a["value"] for a in SCORER.ANCHORS]
        self.assertEqual(len(values), len(set(values)), "дубликаты значений в anchor-таблице")
        for required in (21, 34, 26.54, 56.21, 0.8411, 0.75, 273):
            self.assertIn(required, values)


class TestM2Grounding(unittest.TestCase):
    """Доля grounded числовых утверждений + гейт на файле ответа."""

    def write(self, text: str) -> Path:
        tmp = tempfile.mkdtemp()
        path = Path(tmp) / "answer.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_share_counts_grounded_claims(self):
        path = self.write(
            "# Ответ\n\n"
            "Удержание 21% — baseline [допущение].\n"
            "Отток вырос до 26.54% (ev-002).\n"
            "Когорта теряет около 14% подписчиков.\n"
        )
        result = SCORER.score_m2(path)
        self.assertEqual(result["claims"], 3)
        self.assertEqual(result["grounded"], 2)
        self.assertAlmostEqual(result["share"], 2 / 3, places=3)
        self.assertEqual(result["ungrounded_lines"], [5])

    def test_no_claims_share_is_none(self):
        path = self.write("# Ответ\n\nТри причины: состав, цена, коммуникация.\n")
        self.assertIsNone(SCORER.score_m2(path)["share"])


class TestMemoryProbes(unittest.TestCase):
    """M3: пробы 3/6/11 — метрика успеха и baseline."""

    def test_stable_probes_no_drift(self):
        answers = {
            3: "Метрика успеха — удержание на 30-й день, baseline 21% [допущение].",
            6: "Измеряем удержание на 30-й день от baseline 21%.",
            11: "Метрика — удержание на 30-й день, baseline 21%.",
        }
        result = SCORER.score_m3(answers)
        self.assertTrue(all(p["metric_named"] for p in result["probes"].values()))
        self.assertTrue(all(p["baseline_21"] for p in result["probes"].values()))
        self.assertFalse(result["drift_last_vs_first"])

    def test_drift_when_last_probe_loses_metric(self):
        answers = {
            3: "Метрика успеха — удержание на 30-й день, baseline 21%.",
            6: "Удержание на 30-й день, baseline 21%.",
            11: "Главное — снизить отток и растить выручку.",
        }
        self.assertTrue(SCORER.score_m3(answers)["drift_last_vs_first"])

    def test_drift_when_baseline_contradicted(self):
        answers = {
            3: "Метрика успеха — удержание на 30-й день, baseline 21%.",
            6: "Удержание на 30-й день, baseline 21%.",
            11: "Метрика — удержание на 30-й день, baseline 24%.",
        }
        result = SCORER.score_m3(answers)
        self.assertTrue(result["drift_last_vs_first"])
        self.assertEqual(result["probes"][11]["wrong_baseline_candidates"], ["24 %"])


class TestVerdictRule(unittest.TestCase):
    """Вердикт по предрегистрации §6 — буквально."""

    @staticmethod
    def metrics(contradiction_turns=(), m2_first=1.0, m2_last=1.0):
        out = {}
        for turn in range(1, 13):
            contra = turn in contradiction_turns
            share = m2_first if turn == 1 else (m2_last if turn == 12 else (m2_first + m2_last) / 2)
            out[turn] = {
                "m1": {"contradictions": 1 if contra else 0},
                "m2": {"share": share},
            }
        return out

    @staticmethod
    def m3(drift: bool) -> dict:
        return {"drift_last_vs_first": drift}

    def test_clean_run_no_degradation(self):
        verdict = SCORER.verdict_for_arm(self.metrics(), self.m3(False))
        self.assertEqual(verdict["verdict"], "Деградации не обнаружено")
        self.assertEqual(verdict["triggered"], [])

    def test_two_contradiction_turns_is_degradation(self):
        verdict = SCORER.verdict_for_arm(self.metrics(contradiction_turns=(5, 9)), self.m3(False))
        self.assertEqual(verdict["verdict"], "Деградация подтверждена")
        self.assertEqual(len(verdict["triggered"]), 1)

    def test_single_contradiction_turn_is_not_enough(self):
        verdict = SCORER.verdict_for_arm(self.metrics(contradiction_turns=(5,)), self.m3(False))
        self.assertEqual(verdict["verdict"], "Деградации не обнаружено")

    def test_memory_drift_is_degradation(self):
        verdict = SCORER.verdict_for_arm(self.metrics(), self.m3(True))
        self.assertEqual(verdict["verdict"], "Деградация подтверждена")

    def test_m2_drop_above_20pp_is_degradation(self):
        verdict = SCORER.verdict_for_arm(self.metrics(m2_first=1.0, m2_last=0.75), self.m3(False))
        self.assertEqual(verdict["m2_drop_pp"], 25.0)
        self.assertEqual(verdict["verdict"], "Деградация подтверждена")

    def test_m2_drop_exactly_20pp_is_not_degradation(self):
        """Правило говорит «>20 п.п.» — граница не занижается и не завышается."""
        verdict = SCORER.verdict_for_arm(self.metrics(m2_first=1.0, m2_last=0.80), self.m3(False))
        self.assertEqual(verdict["m2_drop_pp"], 20.0)
        self.assertEqual(verdict["verdict"], "Деградации не обнаружено")


class TestArmAContinuation(unittest.TestCase):
    """Регресс дефекта первого прогона: сид не пересылается на каждом повороте.

    Предрегистрация §3: повороты 2–12 идут в ту же сессию голым текстом
    вопроса. Первый прогон пересылал полный сид (131K символов) каждый
    поворот — контекст сессии рос на сид за поворот, цена поворота выросла
    на 45%, и рука A measureла другую архитектуру, чем заявленная.
    Дефектные данные сохранены в `A-defective-contract/`.
    """

    def test_turn_one_has_full_seed(self):
        prompt, _, cont = DRIVER.prompt_for_turn("A", 1, None, [])
        self.assertFalse(cont)
        self.assertGreater(len(prompt), 100_000, "поворот 1 несёт полный сид")

    def test_turns_2_to_12_are_bare_questions(self):
        _, components, _ = DRIVER.prompt_for_turn("A", 1, None, [])
        for turn in range(2, 13):
            prompt, comps, cont = DRIVER.prompt_for_turn("A", turn, "ses_test", components)
            self.assertTrue(cont, f"поворот {turn} — продолжение сессии")
            self.assertEqual(prompt, DRIVER.TURNS[turn], f"поворот {turn} — голый вопрос")
            self.assertLess(len(prompt), 200)
            self.assertEqual(comps, components, "компоненты сида те же, что в повороте 1")

    def test_hands_b_and_c_always_fresh_session_with_seed(self):
        """Руки B и C не продолжат чужую сессию — каждый поворот со сидом.

        Раньче тест был обусловлен наличием STATE.md (dev-окружение);
        с фолбэком на закоммиченную копию состояния (TASK-hermes-25) он
        проверяет логику рук, а не окружение, поэтому выполняется и в
        свежем клоне: сид B там берётся из `B/state-as-used.md`, а рука C
        от состояния не зависит вовсе.
        """
        for arm in ("B", "C"):
            prompt, _, cont = DRIVER.prompt_for_turn(arm, 5, "ses_ignored", [])
            self.assertFalse(cont, f"рука {arm} не продолжает чужую сессию")
            self.assertIn(DRIVER.TURNS[5], prompt)
            self.assertGreater(len(prompt), 5_000, f"рука {arm} несёт полный сид")


class TestJournalReferencesResolve(unittest.TestCase):
    """Ссылки на журнал в отслеживаемых документах резолвятся в git.

    Дефект найден сверкой keep-list'а и документов: `M1-adjudication.md` и
    `A-defective-contract/DEFECT.md` цитировались из `summary.md`,
    `examples/proof.md` и `examples/long-dialogue.md` как проверяемое
    доказательство, но не входили в keep-list `.gitignore` — в свежем клоне
    ссылки висели бы (тот же класс, что утечка BRIEF.md в TASK-hermes-22).

    Правило: путь журнала в отслеживаемом документе либо резолвится в
    `git ls-files`, либо в ТОЙ ЖЕ строке честно назван вне git
    («вне git» / «пересчитыва» / «воспроизводят»).
    """

    DOCS = ("examples/long-dialogue.md", "examples/proof.md", "README.md",
            "eval/runs/t23-longdialogue/summary.md",
            "eval/runs/t23-longdialogue/PREREGISTRATION.md")
    REF_RE = re.compile(r"`(eval/runs/t23-longdialogue/[^`]+)`")
    DISCLOSURE = ("вне git", "пересчитыва", "воспроизводят")

    def tracked(self) -> set[str]:
        out = subprocess.run(
            ["git", "ls-files", "eval/runs/t23-longdialogue/"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
        )
        return set(out.stdout.split())

    def test_every_journal_reference_resolves_or_is_disclosed(self):
        tracked = self.tracked()
        self.assertIn("eval/runs/t23-longdialogue/M1-adjudication.md", tracked,
                      "M1-adjudication.md цитируется как доказательство — должен быть в git")
        self.assertIn("eval/runs/t23-longdialogue/A-defective-contract/DEFECT.md", tracked,
                      "DEFECT.md цитируется как доказательство — должен быть в git")
        dangling: list[str] = []
        for doc in self.DOCS:
            for lineno, line in enumerate(
                (REPO_ROOT / doc).read_text(encoding="utf-8").splitlines(), start=1
            ):
                for ref in self.REF_RE.findall(line):
                    if ref.endswith("/"):
                        continue  # каталог — не файл
                    if "NN" in ref:
                        # шаблон «turn-NN»: резолвится, если хоть один
                        # поворот такого имени в git
                        pattern = ref.replace("NN", "*")
                        if any(fnmatch.fnmatch(path, pattern) for path in tracked):
                            continue
                    elif ref in tracked:
                        continue
                    if any(word in line for word in self.DISCLOSURE):
                        continue
                    dangling.append(f"{doc}:{lineno}: {ref}")
        self.assertEqual(dangling, [], f"ссылки на файлы журнала вне git без оговорки: {dangling}")


class TestParseTurns(unittest.TestCase):
    def test_ranges_and_lists(self):
        self.assertEqual(DRIVER.parse_turns("1-12"), list(range(1, 13)))
        self.assertEqual(DRIVER.parse_turns("1,3,5"), [1, 3, 5])
        self.assertEqual(DRIVER.parse_turns("12"), [12])

    def test_unknown_turn_rejected(self):
        with self.assertRaises(SystemExit):
            DRIVER.parse_turns("13")


if __name__ == "__main__":
    unittest.main()
