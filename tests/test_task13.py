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
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]

# TASK-hermes-21: сырьё прогонов (eval/runs/**) вне git. Драйверы
# читаются на данных, доступных в свежем клоне:
#   * judge_agreement/second_critic парсят ЗАПИСАННЫЕ оценки — фикстуры
#     tests/fixtures/eval-runs/ (сверено: выход judge_agreement на
#     фикстурах == выход на живых прогонах);
#   * build_blind_pairs и выборка second_critic синтезируются во
#     временном каталоге (там же, где фикстуры STATE.md в
#     test_scripts.py) — проверяется контракт и слепление, не архив;
#   * курируемый артефакт замера (eval/runs/t13-blindpairs/pairs.md)
#     проверяется на закоммиченном файле.
FIXTURE_RUNS = REPO_ROOT / "tests" / "fixtures" / "eval-runs"

# Артефакты рук для сборщика слепых пар: подписи рук в преамбуле есть
# (слепление снимает именно их), варианты — нейтральный текст.
BLINDPAIR_ARMS: dict[str, tuple[str, str]] = {
    "eval/runs/b11-plainchat/final.md": (
        "plain-chat", "один диалог на дословный запрос РП (дизайн B11)"),
    "eval/runs/ab-options-demo-retention/skill/final.md": (
        "skill", "шаг 3, навык options (прогон ab-options)"),
    "eval/runs/ab-options-demo-retention/council-lite/final.md": (
        "council-lite", "совет 3 роли + синтез (протокол council-design §4)"),
    "eval/runs/cl2-demo/critic-loop2/final.md": (
        "critic-loop2", "навык + критик + точечная ревизия (прогон cl2-demo)"),
    "eval/runs/t12-skills/options/curation/final.md": (
        "curation#0", "курация (навык options), цепочка 0 серии t12-skills"),
    "eval/runs/t12-skills/options/curation/final-1.md": (
        "curation#1", "курация, цепочка 1 серии t12-skills"),
    "eval/runs/t12-skills/options/curation/final-2.md": (
        "curation#2", "курация, цепочка 2 серии t12-skills"),
    "eval/runs/t12-skills/options/lean/final.md": (
        "lean#0", "lean, цепочка 0 серии t12-skills"),
    "eval/runs/t12-skills/options/lean/final-1.md": (
        "lean#1", "lean, цепочка 1 серии t12-skills"),
    "eval/runs/t12-skills/options/lean/final-2.md": (
        "lean#2", "lean, цепочка 2 серии t12-skills"),
    "eval/runs/t12-skills/options/hybrid/final.md": (
        "hybrid#0", "гибрид, цепочка 0 серии t12-skills"),
}

ARM_CARD = """# options.md — шаг 3 (фикстура TASK-hermes-21)

Преамбула руки {arm}: {preamble}

## 1. Вариант 1 — «Первые 90 дней»

- **Суть:** довести новичка до первой повторной ценностной точки за 30 дней.
- **Что требует:** сегментацию 0–3 мес и контент-план из 3–5 сообщений.
- **Экономика:** бюджет около нуля, broad-рассылки перераспределяются [гипотеза].
- **Сильнейшее возражение:** метрика замерла на конфликте определений [допущение].

## 2. Вариант 2 — «Риск-таргетинг»

- **Суть:** скоринг сегмента риска и точечная коммуникация вместо массовой.
- **Что требует:** выгрузку признаков и порог скоринга.
- **Экономика:** тот же бюджет, выше плотность сигнала [гипотеза].
- **Сильнейшее возражение:** без данных сервиса скоринг слепой [допущение].

## Оставить как есть

Цена бездействия: когорта 0–3 мес несёт 31.94% оттока (ev-002).
"""


def write_blindpair_arms(root: Path) -> None:
    for rel, (arm, preamble) in BLINDPAIR_ARMS.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ARM_CARD.format(arm=arm, preamble=preamble), encoding="utf-8")


# Выборка second_critic: минимальные артефакты рук без токенов рук
# (артефакты серии t12 были чисты по ослеплению — свойство сохранено).
RESEARCH_CARD = """# research.md — фикстура TASK-hermes-21

Карточка-артефакт для проверки контракта драйвера (сухой прогон).

## Ситуация

- Удержание падает второй квартал подряд; числа — из записи ev-002.
- Контракт month-to-month даёт 42.71% оттока против 2.83% у two-year.

## Гипотезы

- H1: структура контракта объясняет отток новичков [гипотеза].
- H2: первые 90 дней дают измеримый рычаг [гипотеза].
"""

OPTIONS_CARD = """# options.md — фикстура TASK-hermes-21

Карточка-артефакт для проверки контракта драйвера (сухой прогон).

## 1. Вариант 1 — «Первые 90 дней»

- **Суть:** довести новичка до первой повторной ценностной точки за 30 дней.
- **Что требует:** сегментацию 0–3 мес и контент-план из 3–5 сообщений.

## 2. Вариант 2 — «Риск-таргетинг»

- **Суть:** скоринг сегмента риска и точечная коммуникация.

## Оставить как есть

Цена бездействия: когорта 0–3 мес несёт 31.94% оттока (ev-002).
"""


def write_second_critic_runs(root: Path) -> None:
    """Каталог выборки second_critic: summary.json + артефакты клеток."""
    import re as _re
    records = []
    for cell_id, rel, rubric in sc.SAMPLE:
        parts = rel.split("/")
        group, arm = parts[0], parts[1]
        m = _re.search(r"final(?:-(\d))?\.md$", parts[2])
        i = int(m.group(1)) if m and m.group(1) else 0
        records.append({"group": group, "arm": arm, "i": i, "rubric": rubric,
                        "total40": 20.0, "findings_total": 0,
                        "findings_important": 0,
                        "artifact": rel, "error": None})
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        card = OPTIONS_CARD if group in ("options", "o5b-F") else RESEARCH_CARD
        path.write_text(card, encoding="utf-8")
    (root / "scores").mkdir(parents=True, exist_ok=True)
    (root / "scores" / "summary.json").write_text(
        json.dumps({"records": records, "failures": 0}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bp = load_module("build_blind_pairs", REPO_ROOT / "eval" / "build_blind_pairs.py")
sc = load_module("second_critic", REPO_ROOT / "eval" / "second_critic.py")
sc_ja: Any = load_module("judge_agreement", REPO_ROOT / "eval" / "judge_agreement.py")
sc_ja.RUNS_ROOT = FIXTURE_RUNS  # записи оценок — из фикстур, не из прогонов
sc_th = load_module("trigger_audit_heldout", REPO_ROOT / "eval" / "trigger_audit_heldout.py")
ta = load_module("trigger_audit", REPO_ROOT / "eval" / "trigger_audit.py")
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


class PartialAssessmentTests(unittest.TestCase):
    """Частичная оценка критика #2 («Итого: N/20 по оценимым, остальные
    н/д») — исход протокола, не провал прогона и не мусорный выход."""

    def test_full_score_not_partial(self):
        res = sc.assess_critic_out("## Оценки\n\nИтого: 20 / 40\n\n## Findings\n")
        self.assertEqual(res["total40"], 20.0)
        self.assertFalse(res.get("partial"))

    def test_partial_detected(self):
        text = ("Итого: 16/20 по оценимым критериям; критерии 2 и 3 — н/д: "
                "из options.md их не проверить (нужны README, STATE.md).")
        res = sc.assess_critic_out(text)
        self.assertIsNone(res["total40"])
        self.assertTrue(res["partial"])
        self.assertIn("частичная оценка", res["error"])

    def test_partial_detected_n30_format(self):
        # Формат из прогона held-out серии (options-lean-2-unified):
        # «Итого: 20/30 по оцениваемому (полная шкала /40; критерий 3
        # вне области options.md — не оценивался)».
        text = ("Итого: 20/30 по оцениваемому (полная шкала /40; критерий 3 "
                "вне области options.md — не оценивался).")
        res = sc.assess_critic_out(text)
        self.assertIsNone(res["total40"])
        self.assertTrue(res["partial"])

    def test_garbage_is_failure_not_partial(self):
        res = sc.assess_critic_out("Критик не смог оценить артефакт.")
        self.assertIsNone(res["total40"])
        self.assertFalse(res.get("partial"))


class TriggerHeldoutTests(unittest.TestCase):
    """Аудит триггера на held-out артефактах (§27.1): кейсы из реальных
    решений прогона, правило и формат — дословно §19.3."""

    def test_cases_from_heldout_artifacts(self):
        self.assertEqual(len(sc_th.CASES), 5)
        for case in sc_th.CASES:
            self.assertTrue(case["id"].startswith("ho-"))
            self.assertIn(case["expected"], ("high", "low"))
        # Ожидания по правилу council-design §3: необратимо/кросс-функционально
        # → high; обратимо и один контур → low.
        expected = {c["id"]: c["expected"] for c in sc_th.CASES}
        self.assertEqual(expected, {"ho-1": "high", "ho-2": "low", "ho-3": "low",
                                    "ho-4": "high", "ho-5": "low"})

    def test_rule_text_parity_with_193(self):
        # Правило триггера дословно то же, что в аудите §19.3 — меняется
        # только блок кейсов (хеш промпта фиксируется в отчёте).
        self.assertIn("НЕОБРАТИМО (или дорого обратить)", sc_th.AUDIT_PROMPT)
        self.assertIn("НЕОБРАТИМО (или дорого обратить)", ta.AUDIT_PROMPT)
        self.assertIn("high|low", sc_th.AUDIT_PROMPT)

    def test_render_cases_contains_all_ids(self):
        rendered = sc_th.render_cases()
        for case in sc_th.CASES:
            self.assertIn(case["id"], rendered)

    def test_parse_audit_rejects_garbage(self):
        self.assertIsNone(sc_th.parse_audit("нет массива здесь"))
        parsed = sc_th.parse_audit('текст [{"id": "ho-1", "class": "high"}] текст')
        self.assertEqual(parsed, [{"id": "ho-1", "class": "high"}])

    def test_no_key_exit_4(self):
        import os

        env = dict(os.environ)
        env.pop("STEPFUN_API_KEY", None)
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "eval" / "trigger_audit_heldout.py")],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120, env=env,
        )
        self.assertEqual(proc.returncode, 4, proc.stderr)


class BlindPairArtifactTests(unittest.TestCase):
    """Артефактные проверки слепых пар: предъявляемое не несёт имён рук."""

    ARM_TOKENS = ("curation", "lean", "hybrid", "council-lite", "critic-loop2",
                  "t12-skills", "b11-plainchat", "cl2-demo", "ab-options")

    def test_pairs_md_has_no_arm_tokens(self):
        # TASK-hermes-21: сырьё прогонов вне git — сборщик прогоняется на
        # синтезированных артефактах рук; слепление проверяется
        # по-настоящему: подписи рук в фикстурах есть, в предъявляемом
        # их быть не должно.
        with tempfile.TemporaryDirectory() as tmp:
            arms_root = Path(tmp) / "arms"
            write_blindpair_arms(arms_root)
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "eval" / "build_blind_pairs.py"),
                 "--out", tmp, "--root", str(arms_root)],
                capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = (Path(tmp) / "pairs.md").read_text(encoding="utf-8")
            for token in self.ARM_TOKENS:
                self.assertNotIn(token, text)
            # ключ не упоминается в предъявляемом
            self.assertNotIn("key.md", text)

    def test_committed_pairs_md_has_no_arm_tokens(self):
        # Курируемый артефакт замера (eval/runs/t13-blindpairs/pairs.md —
        # то, что предъявлялось владельцу) тоже не несёт имён рук.
        text = (REPO_ROOT / "eval" / "runs" / "t13-blindpairs" / "pairs.md").read_text(
            encoding="utf-8")
        for token in self.ARM_TOKENS:
            self.assertNotIn(token, text)
        self.assertNotIn("key.md", text)


class JudgeAgreementTests(unittest.TestCase):
    """г2: согласие критиков с человеком-судьёй (драйвер eval/judge_agreement.py).

    Состав пар — из key.md после раскрытия; суждения — BRIEF п.27.
    """

    def test_pairs_match_key_composition(self):
        # 10 пар: 4 «против чата», 6 форков; человеческий победитель — из BRIEF п.27.
        self.assertEqual(len(sc_ja.PAIRS), 10)
        chats = [p for p in sc_ja.PAIRS if p["cls"] == "chat"]
        forks = [p for p in sc_ja.PAIRS if p["cls"] == "fork"]
        self.assertEqual((len(chats), len(forks)), (4, 6))
        humans = {p["n"]: p["human"] for p in sc_ja.PAIRS}
        self.assertEqual(humans[1], "plain-chat")
        self.assertEqual(humans[3], "council-lite")
        self.assertEqual(humans[7], "curation#0")
        self.assertEqual(humans[10], "hybrid#0")
        # победитель человека всегда одна из рук пары
        for p in sc_ja.PAIRS:
            self.assertIn(p["human"], (p["a"], p["b"]))

    def test_implied_winner_logic(self):
        self.assertEqual(sc_ja.implied_winner(20.0, 14.0), "A")
        self.assertEqual(sc_ja.implied_winner(14.0, 20.0), "B")
        self.assertEqual(sc_ja.implied_winner(18.0, 18.0), "tie")
        self.assertIsNone(sc_ja.implied_winner(None, 20.0))

    def test_legacy_scores_only_for_first_critic(self):
        # РЕГРЕСС: легаси-оценки t6 (plain-chat/skill/council-lite/cl2) —
        # только протокол одного критика; у критика #2 на этих руках
        # покрытия нет и подставлять чужие оценки нельзя.
        c1 = sc_ja.c1_t12_scores()
        c2 = sc_ja.c2_t13_scores()
        self.assertIn("curation#0", c1)
        self.assertIn("curation#1", c2)
        for arm in ("plain-chat", "skill", "council-lite", "critic-loop2"):
            self.assertNotIn(arm, c2)

    def test_cli_produces_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "eval" / "judge_agreement.py"),
                 "--out", tmp, "--runs-root", str(FIXTURE_RUNS)],
                capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = (Path(tmp) / "judge-agreement.md").read_text(encoding="utf-8")
            self.assertIn("критик #1 (протокол одного)", text)
            payload = json.loads((Path(tmp) / "judge-agreement.json").read_text(encoding="utf-8"))
            self.assertEqual(len(payload["pairs"]), 10)


class JudgeAgreementProtocolTests(unittest.TestCase):
    """TASK-hermes-15 §29: протокол двух критиков против человека.

    Проверяют метрики ПРОТОКОЛА (среднее/единогласно) на записанных
    артефактах добора — без API: регрессия ловит потерю покрытия или
    тихий слом чтений.
    """

    def test_second_critic_coverage_is_complete(self):
        # Добор t15 закрыл покрытие: все 6 артефактов вне t12 имеют
        # полную оценку критика #2 (артефакты eval/runs/t15-blindpairs-c2/).
        scores, _shifts = sc_ja.c2_blindpair_scores()
        self.assertEqual(set(scores), {"plain-chat", "skill", "council-lite",
                                       "critic-loop2", "lean#0", "hybrid#0"})
        for arm, value in scores.items():
            self.assertIsNotNone(value, f"{arm}: покрытие потеряно")

    def test_class_shift_detector_names_only_real_partials(self):
        # «Нет покрытия» ≠ «частичная оценка»: сдвиг класса фиксируется
        # только там, где t13 дал частичную оценку, а t15 — полную.
        _scores, shifts = sc_ja.c2_blindpair_scores()
        self.assertEqual(set(shifts), {"lean#0: t13 частичная → t15 полная 16.0",
                                       "hybrid#0: t13 частичная → t15 полная 20.0"})

    def test_protocol_readings_on_recorded_data(self):
        # На записанных оценках: среднее покрывает все 10 пар; единогласие
        # молчит там, где критики разошлись между собой (§26.4).
        c1_t12 = sc_ja.c1_t12_scores()
        c2 = dict(sc_ja.c2_t13_scores())
        c2.update(sc_ja.c2_blindpair_scores()[0])

        def c1_of(arm: str):
            # Как в драйвере: легаси-оценки t6 — только для критика #1.
            return c1_t12.get(arm, sc_ja.C1_LEGACY.get(arm))

        rows = []
        for pair in sc_ja.PAIRS:
            sa1, sb1 = c1_of(pair["a"]), c1_of(pair["b"])
            sa2, sb2 = c2.get(pair["a"]), c2.get(pair["b"])
            w1, w2 = sc_ja.implied_winner(sa1, sb1), sc_ja.implied_winner(sa2, sb2)
            mean_w = (sc_ja.implied_winner((sa1 + sa2) / 2, (sb1 + sb2) / 2)
                      if None not in (sa1, sb1, sa2, sb2) else None)
            unan = None if w1 is None or w2 is None else (
                "no-direction" if w1 != w2 else w1)
            rows.append({"mean": mean_w, "unan": unan})
        self.assertTrue(all(r["mean"] is not None for r in rows),
                        "среднее чтение потеряло покрытие")
        silent = sum(1 for r in rows if r["unan"] == "no-direction")
        self.assertEqual(silent, 5)  # замер §29.1: протокол молчит на 5/10


class CliContractTests(unittest.TestCase):
    def test_blind_pairs_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            arms_root = Path(tmp) / "arms"
            write_blindpair_arms(arms_root)
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "eval" / "build_blind_pairs.py"),
                 "--out", tmp, "--root", str(arms_root)],
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
        # TASK-hermes-21: runs-dir выборки синтезируется (сырьё вне git);
        # проверяется контракт: 27 клеток выборки резолвятся и печатаются.
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "t12-skills"
            write_second_critic_runs(runs_dir)
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "eval" / "second_critic.py"), "--dry-run",
                 "--runs-dir", str(runs_dir)],
                capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.count("[dry-run]"), 27)


if __name__ == "__main__":
    unittest.main()
