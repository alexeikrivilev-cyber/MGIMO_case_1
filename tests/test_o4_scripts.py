"""Юнит-тесты стенда О4: критик, A/B, метрики, бенчмарк DABstep.

Шов (seam) под тестом — контракт CLI и чистые функции парсинга:
скрипты запускаются отдельными процессами (как хук/человек в терминале),
сетевые вызовы и прогоны моделей не выполняются.

Покрытие: critic, run_ab (руки skill/lean/hybrid/critic-loop/critic-loop2/
council-lite/council-full и фичи options/research), apply_revision,
score_arms (метрики + --sources-gate), critic_matrix, DABstep.

Запуск: python3 -m unittest tests.test_o4_scripts -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
EVAL_DIR = REPO_ROOT / "eval"
BENCH_DIR = REPO_ROOT / "eval" / "benchmarks" / "dabstep" / "scripts"
APPLY_REVISION = SCRIPTS_DIR / "apply_revision.py"


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


    def test_evidence_digest_mandate_in_prompt(self) -> None:
        # --evidence-digest добавляет мандат сверки цитат в промпт критика
        module = load_module("run_critic_prompt_test", SCRIPTS_DIR / "run_critic.py")
        with tempfile.TemporaryDirectory() as tmp:
            digest = Path(tmp) / "digest.md"
            digest.write_text("Выдержка: «199K--319K без валюты».", encoding="utf-8")
            plain = module.build_prompt("АРТ", "РУБ", "critic")
            with_digest = module.build_prompt("АРТ", "РУБ", "critic", digest.read_text(encoding="utf-8"))
            self.assertNotIn("ДОПОЛНИТЕЛЬНЫЙ МАНДАТ", plain)
            self.assertIn("ДОПОЛНИТЕЛЬНЫЙ МАНДАТ", with_digest)
            self.assertIn("199K--319K без валюты", with_digest)
            # режим self мандат не получает
            self_plain = module.build_prompt("АРТ", "РУБ", "self", digest.read_text(encoding="utf-8"))
            self.assertNotIn("ДОПОЛНИТЕЛЬНЫЙ МАНДАТ", self_plain)

    def test_package_mode_prompt(self) -> None:
        # Пакетный режим (H4): несколько артефактов одним прогоном,
        # роль и формат выхода требуют межартефактных находок.
        module = load_module("run_critic_package_test", SCRIPTS_DIR / "run_critic.py")
        package = [("brief.md", "РАМКА"), ("options.md", "ВАРИАНТЫ")]
        prompt = module.build_prompt("", "РУБ", "critic", package=package)
        self.assertIn("=== АРТЕФАКТ: brief.md ===", prompt)
        self.assertIn("=== АРТЕФАКТ: options.md ===", prompt)
        self.assertIn("ПАКЕТ артефактов", prompt)
        self.assertIn("МЕЖДУ артефактами", prompt)
        self.assertIn("А против Б", prompt)
        # одиночный режим не менялся: пакетных маркеров нет
        plain = module.build_prompt("АРТ", "РУБ", "critic")
        self.assertNotIn("АРТЕФАКТ:", plain)
        self.assertIn("место\n(цитата/раздел артефакта)", plain)


class RunLabelTests(unittest.TestCase):
    """Метка прогона для хука cost-append: отдельный файл, STATE.md не трогается.

    Дефект (TASK-hermes-6 п.4): прежняя реализация писала метку в STATE.md
    и восстанавливала «предыдущее» значение — правки агента во время
    сессии критика затирались restore'ом. Метка теперь живёт в
    eval/.cost-label; STATE.md раннеры не открывают на запись вовсе.
    """

    def test_label_file_set_and_clear(self) -> None:
        module = load_module("run_label_under_test", EVAL_DIR / "run_label.py")
        with tempfile.TemporaryDirectory() as tmp:
            module.LABEL_PATH = Path(tmp) / ".cost-label"
            module.set_run_label("О4: ab-test-arm-session")
            self.assertTrue(module.LABEL_PATH.is_file())
            self.assertEqual(module.current_run_label(), "О4: ab-test-arm-session")
            module.clear_run_label()
            self.assertFalse(module.LABEL_PATH.exists())
            self.assertIsNone(module.current_run_label())
            module.clear_run_label()  # повторное удаление — не ошибка

    def test_state_md_untouched_during_run(self) -> None:
        """Прогон метки не изменяет STATE.md агента ни на байт."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "STATE.md"
            original = (REPO_ROOT / "STATE.md").read_text(encoding="utf-8")
            state.write_text(original, encoding="utf-8")
            module = load_module("run_critic_label_under_test", SCRIPTS_DIR / "run_critic.py")
            module.REPO_ROOT = root
            module.run_label.LABEL_PATH = root / "eval" / ".cost-label"
            module.set_run_label("О4: test-label")
            self.assertEqual(state.read_text(encoding="utf-8"), original)
            module.clear_run_label()
            self.assertEqual(state.read_text(encoding="utf-8"), original)

    def test_agent_edits_state_during_session_survive(self) -> None:
        """Гонка больше не теряет правки: агент правит STATE, пока метка жива."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "STATE.md"
            original = (REPO_ROOT / "STATE.md").read_text(encoding="utf-8")
            state.write_text(original, encoding="utf-8")
            module = load_module("run_critic_race_under_test", SCRIPTS_DIR / "run_critic.py")
            module.REPO_ROOT = root
            module.run_label.LABEL_PATH = root / "eval" / ".cost-label"
            module.set_run_label("О4: test-label")
            # агент пишет STATE.md своей копией во время «сессии»
            edited = original.replace("## шаг", "## шаг-правка-агента", 1)
            state.write_text(edited, encoding="utf-8")
            module.clear_run_label()
            self.assertEqual(state.read_text(encoding="utf-8"), edited)


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

    def test_chunk_prompt_splits_over_exec_arg_limit(self) -> None:
        # Промпт >128 КБ одним argv не влезает в лимит exec (E2BIG):
        # chunk_prompt режет его на части ≤120 КБ, не рассекая UTF-8.
        module = load_module("run_ab_chunk_test", EVAL_DIR / "run_ab.py")
        small = "короткий промпт"
        self.assertEqual(module.chunk_prompt(small), [small])
        big = "я" * 200_000  # кириллица — 2 байта на символ, 400 КБ
        chunks = module.chunk_prompt(big)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.encode("utf-8")), module.ARG_LIMIT_BYTES)
        # склейка частей восстанавливает исходный текст (потерь нет)
        self.assertEqual("".join(chunks), big)
        # граница реза не рассекает многобайтовый символ
        emoji = "😀" * 60_000  # 4 байта на символ, 240 КБ
        chunks_emoji = module.chunk_prompt(emoji)
        self.assertEqual("".join(chunks_emoji), emoji)
        for chunk in chunks_emoji:
            chunk.encode("utf-8")  # не бросает decode/encode ошибок


# --------------------------------------------------------------------------
# 2b) eval/run_ab.py — новые руки: council-full, critic-loop2, research
# --------------------------------------------------------------------------


class CouncilFullArmTests(unittest.TestCase):
    """Рука council-full: полный протокол council-design §4 (12 сессий)."""

    def setUp(self) -> None:
        self.module = load_module("run_ab_council_full", EVAL_DIR / "run_ab.py")

    def test_arms_registered(self) -> None:
        for feature, arm in (
            ("options", "council-full"),
            ("options", "critic-loop2"),
            ("research", "curation"),
            ("research", "lean"),
            ("research", "hybrid"),
        ):
            self.assertIn((feature, arm), self.module.ARMS, f"не зарегистрирована рука {arm} ({feature})")
        # прежние руки фичи options не потеряны (обратная совместимость)
        for arm in ("skill", "lean", "hybrid", "critic-loop", "council-lite"):
            self.assertIn(("options", arm), self.module.ARMS)

    def test_same_arm_name_in_other_feature_is_another_function(self) -> None:
        self.assertIsNot(
            self.module.ARMS[("options", "lean")], self.module.ARMS[("research", "lean")]
        )
        self.assertIsNot(
            self.module.ARMS[("options", "hybrid")], self.module.ARMS[("research", "hybrid")]
        )

    def test_sessions_counts(self) -> None:
        self.assertEqual(self.module.sessions_for("options", "council-full"), 12)
        self.assertEqual(self.module.sessions_for("options", "critic-loop2"), 3)
        self.assertEqual(self.module.sessions_for("options", "critic-loop"), 3)
        self.assertEqual(self.module.sessions_for("options", "council-lite"), 4)
        for arm in ("curation", "lean", "hybrid"):
            self.assertEqual(self.module.sessions_for("research", arm), 1)

    def test_five_lenses_and_model_tiering(self) -> None:
        self.assertEqual(
            list(self.module.COUNCIL_FULL_ROLES),
            ["product", "comms", "data", "devil", "user"],
        )
        # council-lite не расширяется: состав и порядок линз сохранены
        self.assertEqual(list(self.module.ROLES), ["product", "devil", "data"])
        for role in ("product", "comms", "devil"):
            self.assertEqual(self.module.ROLE_MODEL[role], "stepfun/step-5-preview", role)
        for role in ("data", "user"):
            self.assertEqual(self.module.ROLE_MODEL[role], "stepfun/step-3.7-flash", role)

    def test_council_lite_flash_devil_on_flash(self) -> None:
        # council-lite-flash (О5 итерация 1): devil переведён на flash,
        # product остаётся на step-5 — отличие РОВНО в одной роли.
        self.assertIn(("options", "council-lite-flash"), self.module.ARMS)
        self.assertEqual(self.module.sessions_for("options", "council-lite-flash"), 4)
        models = self.module.ROLE_MODEL_FLASH_DEVIL
        self.assertEqual(models["devil"], "stepfun/step-3.7-flash")
        self.assertEqual(models["product"], "stepfun/step-5-preview")
        self.assertEqual(models["data"], "stepfun/step-3.7-flash")
        self.assertEqual(self.module.ROLE_MODEL["devil"], "stepfun/step-5-preview")

    def test_council_lite_critic_arm_registered(self) -> None:
        # council-lite-critic (TASK-hermes-7 §2): совет + точечная
        # ревизия по критике на финале; 6 сессий (4 совета + критик +
        # ревизия). Механика ревизии — та же, что у critic-loop2.
        self.assertIn(("options", "council-lite-critic"), self.module.ARMS)
        self.assertEqual(self.module.sessions_for("options", "council-lite-critic"), 6)
        self.assertIs(
            self.module.ARMS[("options", "council-lite-critic")],
            self.module.run_arm_council_lite_critic,
        )

    def test_cross_prompt_states_isolation_rule(self) -> None:
        prompt = self.module.CROSS_PROMPT
        for placeholder in ("{role}", "{lens}", "{brief}", "{others}"):
            self.assertIn(placeholder, prompt)
        text = prompt.format(role="comms", lens="барьеры", brief="БРИФ", others="ЧУЖИЕ ВЫХОДЫ")
        # изоляция Phase 1 названа явно, свой выход исключён
        self.assertIn("НЕ видел", text)
        self.assertIn("ОСТАЛЬНЫХ ЧЕТЫРЁХ", text)
        self.assertIn("ЧУЖИЕ ВЫХОДЫ", text)

    def test_adversarial_prompt_verbatim_and_scope(self) -> None:
        prompt = self.module.ADV_PROMPT
        for placeholder in ("{brief}", "{roles}", "{cross}"):
            self.assertIn(placeholder, prompt)
        text = prompt.format(brief="БРИФ", roles="ВЫХОДЫ", cross="ВОЗРАЖЕНИЯ")
        self.assertIn("ДОСЛОВНО", text)
        self.assertIn("ПРОТИВ ведущего", text)
        self.assertIn("оставить как есть", text)

    def test_synth_full_prompt_has_cross_and_adversarial_blocks(self) -> None:
        prompt = self.module.SYNTH_FULL_PROMPT
        for placeholder in ("{brief}", "{roles}", "{cross}", "{adversarial}"):
            self.assertIn(placeholder, prompt)
        text = prompt.format(brief="Б", roles="R", cross="C", adversarial="A")
        self.assertIn("C", text)
        self.assertIn("A", text)
        # промпт council-lite не сломан: форматируется прежним составом
        lite = self.module.SYNTH_PROMPT.format(brief="Б", roles="R")
        self.assertIn("R", lite)

    def test_dry_run_lists_new_option_arms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # --out во временный каталог: dry-run не должен трогать
            # манифест реального прогона (это артефакт замера).
            proc = run_script(
                EVAL_DIR / "run_ab.py",
                "--task", "demo-retention",
                "--feature", "options",
                "--arms", "skill,critic-loop,council-lite,council-full,critic-loop2",
                "--dry-run",
                "--out", tmp,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[dry-run] council-full", proc.stdout)
            self.assertIn("[dry-run] critic-loop2", proc.stdout)

    def test_dry_run_research_feature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_script(
                EVAL_DIR / "run_ab.py",
                "--task", "heldout-growth-segment",
                "--feature", "research",
                "--arms", "curation,lean,hybrid",
                "--dry-run",
                "--out", tmp,
            )
            self.assertEqual(proc.returncode, 0)
            for arm in ("curation", "lean", "hybrid"):
                self.assertIn(f"[dry-run] {arm}", proc.stdout)

    def test_arm_of_other_feature_is_unknown(self) -> None:
        proc = run_script(
            EVAL_DIR / "run_ab.py",
            "--task", "demo-retention",
            "--feature", "research",
            "--arms", "skill",
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("неизвестные руки", proc.stderr)


class ResearchArmsTests(unittest.TestCase):
    """Фича research: дайджест оснований и единый контракт выхода."""

    def setUp(self) -> None:
        self.module = load_module("run_ab_research", EVAL_DIR / "run_ab.py")

    def test_tasks_have_evidence_dirs(self) -> None:
        self.assertEqual(
            self.module.TASKS["demo-retention"]["evidence"], "project/evidence"
        )
        self.assertEqual(
            self.module.TASKS["heldout-growth-segment"]["evidence"],
            "eval/tasks/heldout-growth-segment/artifacts/evidence",
        )

    def test_evidence_bundle_is_brief_plus_records(self) -> None:
        bundle = self.module.build_evidence_bundle(self.module.TASKS["demo-retention"])
        brief = (REPO_ROOT / "project/council/run-2026-11-16-01/frozen-brief.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(brief[:80], bundle)
        for ident in ("=== ev-001 ===", "=== ev-002 ===", "=== ev-003 ==="):
            self.assertIn(ident, bundle)
        # записи отсортированы по имени файла
        self.assertLess(bundle.index("=== ev-001 ==="), bundle.index("=== ev-003 ==="))
        heldout = self.module.build_evidence_bundle(
            self.module.TASKS["heldout-growth-segment"]
        )
        self.assertIn("=== ev-007 ===", heldout)

    def test_research_prompts_share_output_contract(self) -> None:
        prompts = (
            self.module.RESEARCH_CURATION_PROMPT,
            self.module.RESEARCH_LEAN_PROMPT,
            self.module.RESEARCH_HYBRID_PROMPT,
        )
        for prompt in prompts:
            self.assertIn("{brief}", prompt)
            self.assertIn("{evidence}", prompt)
            text = prompt.format(brief="БРИФ", evidence="ДАЙДЖЕСТ")
            flat = " ".join(text.split())
            self.assertIn("БРИФ", text)
            self.assertIn("ДАЙДЖЕСТ", text)
            # единые требования: структура research.md, конфликты без
            # усреднения, H1..Hn со способом проверки, пробелы, основание
            # числа в той же строке, ответ в чат
            self.assertIn("H1", text)
            self.assertIn("не усредняй", flat)
            self.assertIn("пробел", text.lower())
            self.assertIn("ev-N", text)
            self.assertIn("ТОЙ ЖЕ", text)
            self.assertIn("ОТВЕТОМ В ЧАТ", text)

    def test_curation_prompt_opens_the_skill(self) -> None:
        text = self.module.RESEARCH_CURATION_PROMPT.format(brief="Б", evidence="Э")
        self.assertIn("knowledge/skills/evidence/SKILL.md", text)
        self.assertIn("templates/research.md", text)

    def test_lean_prompt_opens_no_skill_library(self) -> None:
        text = self.module.RESEARCH_LEAN_PROMPT.format(brief="Б", evidence="Э")
        self.assertIn("библиотеки навыков", text)
        self.assertNotIn("knowledge/skills/evidence/SKILL.md", text)

    def test_hybrid_prompt_opens_single_skill(self) -> None:
        text = self.module.RESEARCH_HYBRID_PROMPT.format(brief="Б", evidence="Э")
        self.assertIn("knowledge/skills/evidence/SKILL.md", text)
        self.assertIn("ОДИН навык", text)


CRITIC_LOOP2_DRAFT = """# Черновик options.md (шаг 3)

## Вариант 1 — активация новичков
Суть: довести новичка до первой повторной ценностной точки за 30 дней.
Требует: сегментацию 0–3 мес и контент-план из 3–5 сообщений.
Экономика: бюджет около нуля, broad-рассылки перераспределяются.
Возражение: если ценность не подтверждается, путеводитель — шум [гипотеза].

## Вариант 2 — автоплатёж как дефолт
Суть: убрать ежемесячное перерешение платежа для новичков.
Требует: работу с платёжным шлюзом и коммуникацию перевода.
Экономика: меньше трения на шаге оплаты [гипотеза].
Возражение: автопродление без осознанного выбора — репутационный риск.

## Оставить как есть
Цена бездействия: когорта 0–3 мес несёт 31.94% оттока (ev-002).
"""

CRITIC_LOOP2_REPLY = """Готово, правки точечные.
```json
{"edits": [{"find": "Возражение: если ценность не подтверждается, путеводитель — шум [гипотеза].",
"replace": "Возражение: если ценность не подтверждается, путеводитель — шум; проверить A/B на 30 дней [гипотеза].",
"finding": "нет способа проверки", "action": "apply"}]}
```
"""


class CriticLoop2ArmTests(unittest.TestCase):
    """Рука critic-loop2: сессии подменяются, апдейтер правок — настоящий."""

    def setUp(self) -> None:
        self.module = load_module("run_ab_critic_loop2", EVAL_DIR / "run_ab.py")

    def _run_arm(self, reply: str) -> tuple[int, Path, list[str], list[list[str]]]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        arm_dir = Path(tmp.name) / "cl2-demo" / "critic-loop2"
        arm_dir.mkdir(parents=True)
        sessions: list[str] = []
        commands: list[list[str]] = []

        def fake_session(prompt, out_dir, name, model, timeout):
            sessions.append(name)
            text = CRITIC_LOOP2_DRAFT if name == "session1" else reply
            (out_dir / f"{name}.out").write_text(text, encoding="utf-8")
            return 0, text

        def fake_run(cmd, **kwargs):
            commands.append(list(cmd))
            if "run_critic.py" in " ".join(cmd):
                critic = Path(cmd[cmd.index("--out") + 1])
                critic.mkdir(parents=True, exist_ok=True)
                (critic / "critic.out").write_text(
                    "## Findings\n[важно] нет способа проверки\n", encoding="utf-8"
                )
                return subprocess.CompletedProcess(cmd, 0)
            return subprocess.run(cmd, **kwargs)  # настоящий апдейтер правок

        # подменяются только атрибуты модуля (глобальный subprocess не трогаем)
        with mock.patch.object(self.module, "run_session", side_effect=fake_session):
            with mock.patch.object(self.module, "subprocess") as fake_subprocess:
                fake_subprocess.run.side_effect = fake_run
                code = self.module.run_arm_critic_loop2("options", "БРИФ", arm_dir, 60)
        return code, arm_dir, sessions, commands

    def test_patch_applied_and_report_written(self) -> None:
        code, arm_dir, sessions, _ = self._run_arm(CRITIC_LOOP2_REPLY)
        self.assertEqual(code, 0)
        self.assertEqual(sessions, ["session1", "session2"])
        final = (arm_dir / "final.md").read_text(encoding="utf-8")
        self.assertIn("проверить A/B на 30 дней", final)
        self.assertIn("## Оставить как есть", final)
        self.assertTrue((arm_dir / "draft.md").is_file())
        self.assertTrue((arm_dir / "patches.json").is_file())
        report = (arm_dir / "revision-report.md").read_text(encoding="utf-8")
        self.assertIn("applied=1", report)
        self.assertIn("integrity: ok", report)
        self.assertIn("fallback: no", report)

    def test_unparsable_reply_falls_back_to_draft(self) -> None:
        code, arm_dir, _, _ = self._run_arm("не смог сформировать JSON, извините")
        self.assertEqual(code, 0)
        final = (arm_dir / "final.md").read_text(encoding="utf-8")
        self.assertEqual(final, CRITIC_LOOP2_DRAFT)
        report = (arm_dir / "revision-report.md").read_text(encoding="utf-8")
        self.assertIn("fallback=yes", report)
        self.assertFalse((arm_dir / "patches.json").exists())

    def test_critic_tag_fits_the_40_char_label(self) -> None:
        _, _, _, commands = self._run_arm(CRITIC_LOOP2_REPLY)
        critic_cmd = next(cmd for cmd in commands if "run_critic.py" in " ".join(cmd))
        tag = critic_cmd[critic_cmd.index("--tag") + 1]
        # хук режет колонку «Шаг» до 40 символов; метка регистрируется в
        # ARM_LABELS_BY_RUN как «<прогон>-critic»
        self.assertEqual(tag, "cl2-demo-critic")
        self.assertLessEqual(len(f"О4: {tag}"), 40)

    def test_patch_prompt_json_contract(self) -> None:
        prompt = self.module.PATCH_REVISION_PROMPT
        text = prompt.format(draft="Д", findings="Н")
        self.assertIn('"edits"', text)
        for key in ("find", "replace", "finding", "action", "reason"):
            self.assertIn(f'"{key}"', text)
        self.assertIn("ДОСЛОВНО", text)
        self.assertIn("Не более 15 правок", text)
        self.assertIn("reject", text)
        self.assertIn("«## Вариант", text)
        self.assertIn("«оставить как есть»", text)


# Черновик-фикстура для тестов апдейтера правок: заголовки, секция
# «оставить как есть» и уникальные якоря для точечных правок.
DRAFT = CRITIC_LOOP2_DRAFT


class ApplyRevisionTests(unittest.TestCase):
    """scripts/apply_revision.py — точечные правки и целостность артефакта."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def apply(self, draft: str, edits: list[dict]) -> subprocess.CompletedProcess:
        self.write("draft.md", draft)
        self.write("patches.json", json.dumps({"edits": edits}, ensure_ascii=False))
        return run_script(
            APPLY_REVISION,
            "--draft", str(self.tmp / "draft.md"),
            "--patches", str(self.tmp / "patches.json"),
            "--out", str(self.tmp / "final.md"),
            "--report", str(self.tmp / "report.md"),
        )

    def final(self) -> str:
        return (self.tmp / "final.md").read_text(encoding="utf-8")

    def report(self) -> str:
        return (self.tmp / "report.md").read_text(encoding="utf-8")

    def test_anchor_applied(self) -> None:
        proc = self.apply(DRAFT, [
            {
                "find": "Требует: сегментацию 0–3 мес и контент-план из 3–5 сообщений.",
                "replace": "Требует: сегментацию 0–3 мес и контент-план из 3–5 сообщений (ev-001).",
                "finding": "нет основания",
                "action": "apply",
            }
        ])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("(ev-001)", self.final())
        self.assertIn("applied=1 not_found=0 ambiguous=0 rejected=0", proc.stdout)
        self.assertIn("fallback=no", proc.stdout)
        self.assertIn("integrity=ok", proc.stdout)
        self.assertIn("size_ratio=", proc.stdout)

    def test_not_found_is_reported_and_not_applied(self) -> None:
        proc = self.apply(DRAFT, [
            {"find": "такого фрагмента в черновике нет никак", "replace": "X",
             "finding": "мимо", "action": "apply"}
        ])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("not-found", self.report())
        self.assertIn("applied=0 not_found=1", proc.stdout)
        self.assertIn("fallback=yes", proc.stdout)
        self.assertEqual(self.final(), DRAFT)

    def test_ambiguous_anchor_is_reported_and_not_applied(self) -> None:
        draft = DRAFT + "\nТребует: сегментацию 0–3 мес и контент-план из 3–5 сообщений.\n"
        self.write("draft.md", draft)
        self.write("patches.json", json.dumps({"edits": [
            {"find": "Требует: сегментацию 0–3 мес и контент-план из 3–5 сообщений.",
             "replace": "ЗАМЕНА", "finding": "мимо", "action": "apply"}
        ]}))
        proc = run_script(
            APPLY_REVISION,
            "--draft", str(self.tmp / "draft.md"),
            "--patches", str(self.tmp / "patches.json"),
            "--out", str(self.tmp / "final.md"),
            "--report", str(self.tmp / "report.md"),
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("ambiguous", self.report())
        self.assertIn("applied=0 not_found=0 ambiguous=1", proc.stdout)
        self.assertIn("fallback=yes", proc.stdout)
        self.assertEqual(self.final(), draft)

    def test_rejected_edit_is_not_applied(self) -> None:
        proc = self.apply(DRAFT, [
            {"find": "Возражение: автопродление без осознанного выбора — репутационный риск.",
             "replace": "Убрать возражение.", "finding": "возражение слабое",
             "action": "reject", "reason": "возражение подтверждено ev-002"}
        ])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("rejected", self.report())
        self.assertIn("возражение подтверждено ev-002", self.report())
        self.assertIn("applied=0 not_found=0 ambiguous=0 rejected=1", proc.stdout)
        self.assertEqual(self.final(), DRAFT)

    def test_rejected_and_applied_mixed(self) -> None:
        proc = self.apply(DRAFT, [
            {"find": "Возражение: автопродление без осознанного выбора — репутационный риск.",
             "replace": "Убрать.", "finding": "слабое", "action": "reject",
             "reason": "основание есть"},
            {"find": "Экономика: бюджет около нуля, broad-рассылки перераспределяются.",
             "replace": "Экономика: бюджет около нуля, broad-рассылки перераспределяются (ev-002).",
             "finding": "нет основания", "action": "apply"},
        ])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("applied=1 not_found=0 ambiguous=0 rejected=1", proc.stdout)
        self.assertIn("fallback=no", proc.stdout)
        self.assertIn("(ev-002)", self.final())
        self.assertIn("репутационный риск", self.final())

    def test_header_deletion_breaks_integrity(self) -> None:
        proc = self.apply(DRAFT, [
            {"find": "## Вариант 2 — автоплатёж как дефолт\nСуть: убрать ежемесячное "
                     "перерешение платежа для новичков.\n",
             "replace": "", "finding": "вариант слабый", "action": "apply"}
        ])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("integrity=BROKEN", proc.stdout)
        self.assertIn("fallback=yes", proc.stdout)
        self.assertIn("integrity: BROKEN", self.report())
        self.assertIn("Вариант 2", self.report())
        # честная деградация: финал = черновик дословно
        self.assertEqual(self.final(), DRAFT)

    def test_keep_as_is_section_deletion_breaks_integrity(self) -> None:
        proc = self.apply(DRAFT, [
            {"find": "## Оставить как есть\nЦена бездействия: когорта 0–3 мес несёт "
                     "31.94% оттока (ev-002).\n",
             "replace": "", "finding": "цена бездействия не нужна", "action": "apply"}
        ])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("integrity=BROKEN", proc.stdout)
        self.assertIn("оставить как есть", self.report())
        self.assertEqual(self.final(), DRAFT)

    def test_size_ratio_guard(self) -> None:
        filler = "Подробное обоснование варианта с числами и механизмом. " * 30
        draft = (
            "# Черновик\n\n## Вариант 1 — активация\n" + filler + "\n\n"
            "## Оставить как есть\nЦена бездействия описана [гипотеза].\n"
        )
        proc = self.apply(draft, [
            {"find": filler, "replace": "Кратко.", "finding": "слишком длинно",
             "action": "apply"}
        ])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("integrity=BROKEN", proc.stdout)
        self.assertIn("size_ratio=0.", proc.stdout)
        self.assertLess(float(proc.stdout.split("size_ratio=")[1][:4]), 0.60)
        self.assertIn("fallback=yes", proc.stdout)
        self.assertEqual(self.final(), draft)

    def test_missing_patches_file_exit_2(self) -> None:
        self.write("draft.md", DRAFT)
        proc = run_script(
            APPLY_REVISION,
            "--draft", str(self.tmp / "draft.md"),
            "--patches", str(self.tmp / "нет-такого.json"),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("файл не найден", proc.stderr)

    def test_broken_patches_json_exit_2(self) -> None:
        self.write("draft.md", DRAFT)
        self.write("patches.json", "{не json")
        proc = run_script(
            APPLY_REVISION,
            "--draft", str(self.tmp / "draft.md"),
            "--patches", str(self.tmp / "patches.json"),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("не удалось разобрать правки", proc.stderr)


# --------------------------------------------------------------------------
# 4b) eval/score_arms.py — гейт доказательств (--sources-gate)
# --------------------------------------------------------------------------


class ScoreArmsSourcesGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module("score_arms_gate", EVAL_DIR / "score_arms.py")

    def test_parse_violations(self) -> None:
        self.assertEqual(self.module.parse_violations("итог: нарушений 3 в файлах 1"), 3)
        self.assertEqual(
            self.module.parse_violations("ok: файлов проверено 1, нарушений нет"), 0
        )

    def test_arm_label_fragments_for_new_runs(self) -> None:
        self.assertEqual(
            self.module.arm_label_fragments("cf-heldout", "council-full"),
            ["ab-cf-heldout-council-full"],
        )
        self.assertEqual(
            self.module.arm_label_fragments("cl2-demo", "critic-loop2"),
            ["ab-cl2-demo-critic-loop2", "cl2-demo-critic"],
        )
        self.assertEqual(
            self.module.arm_label_fragments("cl2-heldout", "critic-loop2"),
            ["ab-cl2-heldout-critic-loop2", "cl2-heldout-critic"],
        )

    def test_sources_gate_adds_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "cl2-demo"
            arm_dir = run_dir / "critic-loop2"
            arm_dir.mkdir(parents=True)
            (arm_dir / "final.md").write_text(
                "# options.md\n\n## Вариант 1\nЧисло 61.99% (ev-002).\n\n"
                "## Оставить как есть\nЦена бездействия [гипотеза].\n",
                encoding="utf-8",
            )
            (root / "COST.md").write_text(
                "<!-- cost-rows:begin -->\n"
                "| 2026-11-16 | s1 | О4: ab-cl2-demo-critic-loop2-session1 | step-5-preview "
                "| 1 | 2 | 0 | 0 | 0 | 0 | $0.10 |\n"
                "| 2026-11-16 | s2 | О4: cl2-demo-critic | step-5-preview "
                "| 1 | 2 | 0 | 0 | 0 | 0 | $0.05 |\n"
                "<!-- cost-rows:end -->\n",
                encoding="utf-8",
            )
            self.module.REPO_ROOT = root

            def fake_run(cmd):
                joined = " ".join(cmd)
                if "check_sources.py" in joined:
                    return (
                        2,
                        "critic-loop2/final.md:4: числовое утверждение без основания\n"
                        "итог: нарушений 1 в файлах 1",
                    )
                if "check_citations.py" in joined:
                    return (0, "итог: 1/1")
                if "council_diversity.py" in joined:
                    return (0, "средняя попарная дистанция 0.42")
                return (0, "")  # критик без ключа/сети — метрика рубрики пустая

            self.module.run = fake_run
            code = self.module.main(["--run-dir", str(run_dir), "--sources-gate"])
            self.assertEqual(code, 0)
            metrics_md = (run_dir / "metrics.md").read_text(encoding="utf-8")
            self.assertIn("check_sources", metrics_md)
            self.assertIn("exit=2; нарушений 1", metrics_md)
            payload = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["arms"][0]["sources_gate"], {"exit": 2, "violations": 1})
            # атрибуция $ по новым фрагментам метки: обе строки COST.md
            self.assertAlmostEqual(payload["arms"][0]["usd"], 0.15)
            # без флага колонка остаётся, но пустой (прежний состав метрик)
            self.assertEqual(self.module.main(["--run-dir", str(run_dir)]), 0)
            self.assertIn("| — |", (run_dir / "metrics.md").read_text(encoding="utf-8"))


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
                "| 2026-11-16 | ses_x | О4: ab-run-skill-session | step-5-preview | 1 | 2 | 0 | 0 | 0 | 0 | $0.10 |\n"
                "| 2026-11-16 | ses_y | О4: ab-run-critic-loop-session1 | step-5-preview | 1 | 2 | 0 | 0 | 0 | 0 | $0.25 |\n"
                "| 2026-11-16 | ses_z | О3: council | step-5-preview | 1 | 2 | 0 | 0 | 0 | 0 | $0.99 |\n"
                "<!-- cost-rows:end -->\n",
                encoding="utf-8",
            )
            self.module.REPO_ROOT = root
            usd, rows = self.module.cost_rows_for(["ab-run-skill-session"])
            self.assertAlmostEqual(usd, 0.10)
            self.assertEqual(rows, 1)
            # «ab-run-skil» (обрезок без границы дефиса) не матчит —
            # матч только точный или префикс до дефиса.
            usd_edge, rows_edge = self.module.cost_rows_for(["ab-run-skil"])
            self.assertAlmostEqual(usd_edge, 0.0)
            self.assertEqual(rows_edge, 0)
            # «ab-session» не должен захватить «ab-session1» (нет дефиса).
            usd_edge2, rows_edge2 = self.module.cost_rows_for(["ab-run-skill-session1"])
            self.assertAlmostEqual(usd_edge2, 0.0)
            self.assertEqual(rows_edge2, 0)
            usd2, rows2 = self.module.cost_rows_for(["ab-run"])
            self.assertAlmostEqual(usd2, 0.35)
            self.assertEqual(rows2, 2)


# --------------------------------------------------------------------------
# 5b) eval/trigger_audit.py — аудит триггера council (О5 итерация 3)
# --------------------------------------------------------------------------


class TriggerAuditTests(unittest.TestCase):
    """Аудит триггера: 10 кейсов, парсинг JSON, счётчики вердикта."""

    def setUp(self) -> None:
        self.module = load_module("trigger_audit_under_test", EVAL_DIR / "trigger_audit.py")

    def test_ten_cases_five_per_task(self) -> None:
        self.assertEqual(len(self.module.CASES), 10)
        demo = [c for c in self.module.CASES if c["task"] == "demo-retention"]
        heldout = [c for c in self.module.CASES if c["task"] == "heldout-growth-segment"]
        self.assertEqual((len(demo), len(heldout)), (5, 5))
        # ожидания обоих классов представлены (триггер различает)
        expected = {c["expected"] for c in self.module.CASES}
        self.assertEqual(expected, {"high", "low"})
        # id уникальны
        ids = [c["id"] for c in self.module.CASES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_prompt_mentions_trigger_rule(self) -> None:
        prompt = self.module.AUDIT_PROMPT.format(cases="КЕЙСЫ")
        self.assertIn("НЕОБРАТИМО", prompt)
        self.assertIn("КРОСС-ФУНКЦИОНАЛЬНО", prompt)
        self.assertIn("ВЫШЕ ПОРОГА", prompt)
        self.assertIn("КЕЙСЫ", prompt)

    def test_parse_audit_json(self) -> None:
        text = 'Вот ответ:\n[{"id": "demo-1", "class": "high", "confidence": 0.9, "reason": "необратимо"}]\nготово'
        parsed = self.module.parse_audit(text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[0]["id"], "demo-1")
        self.assertIsNone(self.module.parse_audit("без json"))
        self.assertIsNone(self.module.parse_audit("{}"))


# --------------------------------------------------------------------------
# 5c) eval/run_plainchat.py — рука B11(b): обычный чат той же модели
# --------------------------------------------------------------------------


class PlainChatArmTests(unittest.TestCase):
    """B11(b): дословный запрос РП, один диалог, без папки/навыков."""

    def setUp(self) -> None:
        self.module = load_module("run_plainchat_under_test", EVAL_DIR / "run_plainchat.py")

    def test_extract_request_is_verbatim_quote(self) -> None:
        request = self.module.extract_request(REPO_ROOT / "eval/tasks/demo-retention/task.md")
        self.assertIn("МегаТВ Онлайн", request)
        self.assertIn("удержание на 30-й день упало с 34% до 21%", request)
        self.assertFalse(request.startswith(">"))  # цитата развёрнута в текст

    def test_prompt_adds_chat_instruction_only(self) -> None:
        request = self.module.extract_request(REPO_ROOT / "eval/tasks/demo-retention/task.md")
        prompt = request + self.module.CHAT_INSTRUCTION
        self.assertTrue(prompt.startswith(request))
        self.assertIn("ОДНИМ сообщением", prompt)
        self.assertIn("как обычный чат-ассистент", prompt)
        # промпт НЕ отсылает к навыкам/папке — иначе это не plain-chat
        self.assertNotIn("навык", prompt)
        self.assertNotIn("STATE.md", prompt)

    def test_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_script(
                EVAL_DIR / "run_plainchat.py",
                "--task", "demo-retention",
                "--dry-run",
                "--out", tmp,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[dry-run]", proc.stdout)
            self.assertIn("sha256", proc.stdout)


# --------------------------------------------------------------------------
# 6) Бенчмарк DABstep — вендор-scorer и протокол агента
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

    def test_system_prompt_has_applicability_and_best_effort_rules(self) -> None:
        # TASK-hermes-7 §3: явная фаза проверки применимости (failure mode
        # task 70: «yes» при эталоне «Not Applicable») и правило
        # best-effort при исчерпании шагов (task 2697).
        text = self.agent.SYSTEM.format(max_steps=12)
        self.assertIn("проверь применимость", text)
        self.assertIn("Not Applicable", text)
        self.assertIn("ЛУЧШИЙ", text)

    def test_best_effort_mandate_contract(self) -> None:
        # Мандат дополнительного вывода: без нового кода, строго FINAL.
        mandate = self.agent.BEST_EFFORT_MANDATE
        self.assertIn("НЕ будет", mandate)
        self.assertIn("FINAL", mandate)


class DabstepRunRowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = load_module("dabstep_run_under_test", BENCH_DIR / "run.py")

    def test_build_row_defaults_and_flags(self) -> None:
        task = {"task_id": "2697", "level": "hard", "question": "q?", "answer": "42"}
        # Старый формат выхода (без best_effort/steps_budget) — совместимость.
        row = self.runner.build_row(task, {"answer": "42", "steps": 12, "usage": {}}, 0.05)
        self.assertEqual(row["steps_budget"], 12)
        self.assertFalse(row["best_effort"])
        self.assertEqual(row["gold"], "42")
        # Новый формат: шаги бюджета отделены от best-effort вызова.
        row = self.runner.build_row(
            task, {"answer": "43", "steps": 13, "steps_budget": 12, "best_effort": True, "usage": {}}, 0.06
        )
        self.assertEqual(row["steps"], 13)
        self.assertEqual(row["steps_budget"], 12)
        self.assertTrue(row["best_effort"])


class RescoreArmsTests(unittest.TestCase):
    """Контракт eval/rescore_arms.py (TASK-hermes-7 §1): план реcкоринга
    должен ссылаться только на существующие файлы, иначе замер молча
    теряет строку."""

    def setUp(self) -> None:
        self.module = load_module("rescore_arms_under_test", EVAL_DIR / "rescore_arms.py")

    def test_plan_paths_exist(self) -> None:
        for bucket, items in self.module.PLAN.items():
            for item in items:
                for key in ("artifact", "rubric"):
                    path = REPO_ROOT / item[key]
                    self.assertTrue(path.is_file(), f"{bucket}/{item['name']}: нет {key} {path}")
                if item.get("unified"):
                    self.assertTrue(
                        (REPO_ROOT / item["unified"]).is_file(),
                        f"{bucket}/{item['name']}: нет единорубрикового замера {item['unified']}",
                    )

    def test_references_exist(self) -> None:
        for ref in self.module.REFERENCES:
            for key in ("unified", "typical"):
                self.assertTrue((REPO_ROOT / ref[key]).is_file(), f"{ref['name']}: нет {key}")

    def test_parse_scores_contract(self) -> None:
        text = "| 1. Набор вариантов | 5/5 | 4/5 | 8/10 |\nИтого: 36 /40\n[важность: важно] x\n[незначительно] y"
        parsed = self.module.parse_scores(text)
        self.assertEqual(parsed["total40"], 36.0)
        self.assertEqual(parsed["findings_total"], 2)
        self.assertEqual(parsed["findings_important"], 1)

    def test_parse_scores_table_row_format(self) -> None:
        # Формат «| Итого | | | **22/40** |» — на прогоне clc-heldout
        # оценка терялась (дефект парсинга); контракт зафиксирован.
        text = "| 1. Проработанность | 4/5 | 4/5 | 8/10 |\n| Итого | | | **22/40** (≈5.5/10) |"
        self.assertEqual(self.module.parse_scores(text)["total40"], 22.0)
        text2 = "| Критерий | Проход 1 | Проход 2 | Баллы |\n| 4. Качество | 4/5 | 3/5 | 6/10 |\n| Итого | | | 30/40 |"
        self.assertEqual(self.module.parse_scores(text2)["total40"], 30.0)
        # Шаблон без числа («Итого: __ /40») не матчится — не выдумываем 0.
        self.assertIsNone(self.module.parse_scores("Итого: __ /40")["total40"])

    def test_dry_run_lists_all_plan_runs(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(EVAL_DIR / "rescore_arms.py"), "--dry-run"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        expected = sum(len(items) for items in self.module.PLAN.values())
        self.assertEqual(proc.stdout.count("[dry-run]"), expected)
        self.assertIn("[reused] demo-research-critic", proc.stdout)


if __name__ == "__main__":
    unittest.main()
