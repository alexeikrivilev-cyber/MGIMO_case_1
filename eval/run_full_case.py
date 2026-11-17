#!/usr/bin/env python3
"""run_full_case.py — прогон ПОЛНОГО ПУТИ продукта (шаги 0–5) под
текущим прод-конфигом (TASK-hermes-18 §32, предрегистрация measurements.md §32).

Прод-конфиг (подтверждён владельцем, BRIEF п.27): шаг 3 — база (навык
options); шаги 4–5 — критик-детектор (критик + точечная ревизия,
механика critic-loop2 §17) + все гейты. Шаги 0–1: рамка заморожена
(переносится), evidence перепроверяется, но не переделывается
(анти-круг: закрытое и source-verified основание). Шаги 2–5 — свежая
генерация сессиями продукта.

Механика сессий (урок живого прогона 2026-11-17, первый замер):
контракт стенда — свежая сессия `opencode run`, артефакт возвращается
ОТВЕТОМ В ЧАТ. ВСЕ входы (навык, шаблон, входящие артефакты) даются
ИНЛАЙНОМ, файлы не открывать и инструменты не запускать: сессии с
инструментами и длинной генерацией теряли финальный текст на границе
CLI/провайдера (замер 1: 37K out-токенов модели, 48 байт в stdout —
сессия «успешна» exit=0, артефакта нет; гейты при этом прошли ВАКУУМНО
на файле-заглушке). Защита от вакуумного прохождения: порог размера и
обязательный markdown-заголовок ДО гейтов + ретрай свежей сессией.

Учёт $ — метка «О4: t18-case…» через eval/run_label.py (отдельный файл,
не STATE.md — урок гонки TASK-hermes-6). Один раннер за раз (eval/
.cost-label — single-session).

Контракт CLI:
    python3 eval/run_full_case.py --task demo-retention
        [--runs-dir DIR] [--timeout SEC] [--dry-run] [--force]
        [--from-step N] [--no-critic]

Коды возврата: 0 — путь пройден, все гейты зелёные; 1 — ошибка
использования; 4 — провал прогона или гейта (детали в manifest.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from arg_chunk import chunk_prompt  # noqa: E402
import run_label  # noqa: E402
from run_ab import MAX_PATCH_EDITS, parse_patch_json  # noqa: E402 (единый контракт правок)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_RUN_FAILED = 4

MODEL = "stepfun/step-5-preview"
# Раунды гейт-ревизий на артефакт. Оригинальный продукт на шаге 3
# потребовал 10 итераций check_sources (STATE.md); 3 оказалось мало
# (options замери 1: 4 раунда — sources → options → transferability →
# ranges), поэтому 5 с явным провалом на выходе из полосы.
MAX_GATE_ROUNDS = 5
GATE_TIMEOUT = 300
# Порог годности артефакта из сессии: короче — не артефакт (заглушка
# или нарратив), гейты на ном проходят вакуумно. Заголовок markdown
# обязателен (артефакты продукта — структурированный markdown).
MIN_ARTIFACT_CHARS = 2000
HEADING_RE = re.compile(r"^#{1,3}\s+\S", re.MULTILINE)

TASKS = {
    "demo-retention": {
        "brief": "project/brief.md",
        "evidence": "project/evidence",
        "evidence_task": "demo-retention",
        "label": "t18-case",
        "default_runs_dir": "eval/runs/t18-case",
        "cp2": """Перенесённые решения ЧЕКПОИНТА 2 (источник — оператор,
репетиция демо, непрерывный режим; считать подтверждёнными):
- картина ситуации и гипотезы этого исследования — основание шага 3;
- полный отчёт Mixpanel и 23-колоночную версию датасета Kaggle НЕ
  добываем (за авторизацией/скачиванием; защиту не обходим) —
  соответствующие пробелы остаются в артефакте именованными;
- целевая метрика — 30-дневное удержание сервиса (метрика РП из
  рамки); цель — остановить падение и стабилизировать, конкретные
  целевые цифры — с маркерами [прогноз];
- конфликт определений метрик фиксируется как ограничение сравнения,
  не усредняется.""",
        "cp3": """Перенесённое решение ЧЕКПОИНТА 3 (источник — оператор,
репетиция демо, непрерывный режим; считать подтверждённым):
выбрана комбинация ПРОДУКТОВОГО механизма «Первые 90 дни» и
КОММУНИКАЦИОННОГО «Риск-таргетинг». Коммерческий «Контракт на входе»
отвергнут как выходящий за рамку brief.md «Что НЕ входит» (тарифная
сетка) [допущение]. «Оставить как есть» отвергнут с ценой бездействия.
Зафиксируй выбор в разделе «Ответ человека», сопоставив механизмы с
номерами вариантов ЭТОГО прогона (нумерация своя).""",
    },
    "heldout-growth-segment": {
        "brief": "eval/tasks/heldout-growth-segment/artifacts/brief.md",
        "evidence": "eval/tasks/heldout-growth-segment/artifacts/evidence",
        "evidence_task": "heldout-growth-segment",
        "label": "t18-case-ho",
        "default_runs_dir": "eval/runs/t18-case-heldout",
        "cp2": """Перенесённые решения ЧЕКПОИНТА 2 (источник — оператор,
репетиция демо, непрерывный режим; считать подтверждёнными):
- исследование принимается как основание шага 3; цель — выбрать ОДНО
  направление роста и обосновать выбор (рамка: совет директоров, один
  приоритет, квартал);
- данные — только открытые аналоги (банковский маркетинг, online
  shoppers, arXiv); реальные данные «ДомКниг» не предоставлены
  [допущение];
- ловушки аналогов зафиксированы в рамке ЗАРАНЕЕ (duration — утечка;
  дисбаланс классов; макро-колонки привязаны к 2008–2010; метка
  «покупка» в Online Shoppers — событие сессии, не подписка) — шаг 3
  обязан их соблюдать, а не «обнаруживать» на шаге 4;
- бюджет — только перераспределение spend'а на привлечение; срок —
  квартал; получатель — совет директоров, формат «на утверждение».""",
        "cp3": """Перенесённое решение ЧЕКПОИНТА 3 (источник — оператор,
репетиция демо, непрерывный режим; считать подтверждённым):
выбрана комбинация: вариант «Второй месяц» (механика продления на
текущей базе) как ОСНОВНАЯ ставка + «Премиум на том, что есть» как
подчинённый монетизационный тест с holdout внутри той же ставки.
Отвергнуты: B2B «библиотеки для компаний» (холодный приток против
измеренного градиента аналогий; цикл корпоративной продажи вне
квартала [прогноз]), линейка 65+ (единственное количественное
основание снято контролем по периоду, ev-007), «оставить как есть»
(цена бездействия названа и необратима по времени [прогноз]).
Зафиксируй выбор в разделе «Ответ человека», сопоставив механизмы с
номерами вариантов ЭТОГО прогона (нумерация своя).""",
    },
}

CHAIN = ("research.md", "options.md", "strategy-product.md",
         "strategy-comms.md", "verification-plan.md", "decisions.md")

# Артефакты этапа «стратегии + решения» (шаги 4–5). Гейты чек-листа и
# управляемости применяются ко ВСЕМ артефактам этапа, не к одному:
# дефект области действия (TASK-hermes-20) — гейты acceptance/
# actionability винтили только на strategy-product.md, и comms /
# verification-plan / decisions дошли до сдачи без секции приёмного
# чек-листа и структурных признаков плана (вердикт владельца, BRIEF
# п.27: шаги 4–5 отвечают за «готовность к действию»).
STEP45_ARTIFACTS = ("strategy-product.md", "strategy-comms.md",
                    "verification-plan.md", "decisions.md")

UNITARY_RUBRIC = "eval/rubrics/hackathon-criteria.md"

EVIDENCE_NOTE = """Каждое существенное число несёт основание (ev-N / URL) В
ТОЙ ЖЕ строке, и маркер типа утверждения ([гипотеза]/[прогноз]/
[допущение]) — тоже в той же строке: перенос строки в списке разрывает
основание для механических гейтов (урок TASK-3, check_sources)."""

CHAT_CONTRACT = """Верни готовый markdown артефакт ОТВЕТОМ В ЧАТ — целиком,
одним ответом, без оглавления и пояснений вокруг. НЕ открывай файлы и
НЕ запускай инструменты: все входы даны ниже инлайном. Файлы не пиши,
ничего не коммить, гейты не запускай — их прогонит драйвер."""

# Навыки и шаблоны шагов (пути от корня репозитория).
STEP_SOURCES = {
    "research.md": ("knowledge/skills/evidence/SKILL.md",
                    "templates/research.md"),
    "options.md": ("knowledge/skills/options/SKILL.md",
                   "templates/options.md"),
    "strategy-product.md": ("knowledge/skills/strategy-product/SKILL.md",
                            "templates/strategy-product.md"),
    "strategy-comms.md": ("knowledge/skills/strategy-comms/SKILL.md",
                          "templates/strategy-comms.md"),
    "verification-plan.md": ("knowledge/skills/verification/SKILL.md",
                             "templates/verification-plan.md"),
    "decisions.md": ("knowledge/skills/decisions/SKILL.md",
                     "templates/decisions.md"),
}

RESEARCH_BODY = """Ты — агент «Стратег» (папочный агент для руководителя
цифрового продукта), выполняешь шаг 2 (ИССЛЕДОВАНИЕ) рабочего процесса.
Примени навык (раздел «Шаг 2») и шаблон — оба даны ниже.

{inputs_block}

{cp2}

Требования к выходу: решающие вопросы со статусами (частично / пробел);
картина ситуации — только с основаниями (ev-N, URL, маркеры); конфликты
источников — парами, без усреднения; гипотезы со способом проверки;
именованные пробелы — явно («не знаем X, потому что …»); факт / гипотеза
/ прогноз разделены. {evidence_note} ЖЁСТКИЙ лимит: ≤ 300 строк, без
воды (провайдер обрывает ответ на лимите вывода — перегенерация
теряется).

{chat_contract}"""

OPTIONS_BODY = """Ты — агент «Стратег», выполняешь шаг 3 (ВАРИАНТЫ)
рабочего процесса по навыку options (§2–3) и шаблону — оба даны ниже.

{inputs_block}

{cp3}

Требования к выходу: не менее трёх вариантов с РАЗНЫМИ механизмами
воздействия (не разным размером бюджета) + «оставить как есть» с ценой
бездействия; у каждого: суть / что требует / экономика / сильные
возражения (сильнейшее первым) / риски; таблица сравнения по общим
критериям; маркеры на не-фактах. ЖЁСТКИЕ лимиты объёма (провайдер
обрывает ответ на лимите вывода — перегенерация теряется): черновик
≤ 250 строк; карточка варианта — до 12 строк (суть 1–2, требует 2–3,
экономика 2–3, возражения 2, риски 1–2); одна сильнейшая аргументация
на вариант, НЕ перечисление всех оснований; таблица — одна строка на
критерий. {evidence_note}

{chat_contract}"""

STRATEGY_PRODUCT_BODY = """Ты — агент «Стратег», выполняешь шаг 4
(ПРОДУКТОВАЯ СТРАТЕГИЯ) по навыку strategy-product и шаблону — оба
даны ниже.

{inputs_block}

Основание стратегии — выбранная человеком комбинация механизмов
(«Ответ человека» в options.md), не «усреднение всех вариантов».
Инициативы с приоритетами по критерию «эффект × скорость сигнала ×
стоимость»; метрики с baseline из evidence или явным пробелом;
экономика — в структурных единицах, денежный ROI не считаем (ARPU
неизвестен [допущение]).

ОБЯЗАТЕЛЬНО: заполни приёмный чек-лист 6 вопросов владельца —
что знаем / чего не знаем; какие решения; что проверять первым и
почему; деньги / команды / сроки; метрики успеха; когда остановить.
Это ответственность шага 4 за «готовность к действию» (решение
владельца, BRIEF п.27). {evidence_note} ЖЁСТКИЙ лимит: ≤ 300 строк
(провайдер обрывает перегенерацию на лимите вывода).

{chat_contract}"""

STRATEGY_COMMS_BODY = """Ты — агент «Стратег», выполняешь шаг 4
(КОММУНИКАЦИОННАЯ СТРАТЕГИЯ) по навыку strategy-comms и шаблону — оба
даны ниже.

{inputs_block}

Получатель — РП + руководство, формат «на утверждение»: сообщения с
основаниями, именованные возражения с ответами, однозначное «что
просим утвердить». Детали и цифры — по ссылке на продуктовую
стратегию (один дом факта), не копией. {evidence_note} Объём —
100–200 строк.

ОБЯЗАТЕЛЬНО (решение владельца, BRIEF п.27 — «готовность к действию»):
артефакт несёт секцию «Приёмный чек-лист (6 вопросов владельца)» с
ответами по сути ЭТОГО артефакта — что знаем / чего не знаем; какие
решения просим утвердить; что проверять первым и почему; деньги /
команды / сроки коммуникации; метрики успеха коммуникации; когда
остановить. Плюс структурные признаки плана: приоритеты P0–P2 с
последовательностью сообщений и согласований, контрольная группа
(holdout) как способ замера эффекта коммуникации, критерии остановки
кампании. {chat_contract}"""

VERIFICATION_BODY = """Ты — агент «Стратег», выполняешь шаг 4 (ПЛАН
ПРОВЕРКИ) по навыку verification и шаблону — оба даны ниже.

{inputs_block}

Требования: метрики с двумя зонами («работает» / «не работает»),
способ и частота измерения, предрегистрированное правило при
опровержении (возврат отвергнутого варианта — ТОЛЬКО отдельным
решением человека со снятием ограничения рамки). Метрики и пороги
каждого решения шага 5 берутся ОТСЮДА. {evidence_note} Объём —
100–200 строк.

ОБЯЗАТЕЛЬНО (решение владельца, BRIEF п.27 — «готовность к действию»):
артефакт несёт секцию «Приёмный чек-лист (6 вопросов владельца)» с
ответами по сути ЭТОГО артефакта — что знаем / чего не знаем о
проверяемости; какие решения уже предрегистрированы; что проверять
первым и почему (порядок замеров); деньги / команды / сроки плана
проверки; метрики успеха; когда остановить. Плюс структурные признаки
плана: приоритеты P0–P2 самой проверки (какие замеры и пилоты идут
первыми и почему), контрольная группа (holdout) и A/B как способ
отделить эффект от сопутствующих изменений, критерии остановки.

{chat_contract}"""

DECISIONS_BODY = """Ты — агент «Стратег», выполняешь шаг 5 (ПОСЛЕ
РЕШЕНИЯ, дополнительный уровень) по навыку decisions и шаблону — оба
даны ниже.

{inputs_block}

Требования: реестр решений — у каждого владелец, дата, метрика и
порог (из verification-plan.md), условие пересмотра, статус;
основания каждого решения со ссылками на артефакты; незакрытые
возражения сохранены, не усреднены; история пересмотров (append-only).
Решения — перенесённые решениями чекпоинтов (источник — оператор,
репетиция демо): целевая метрика и критерий успеха; выбранная
комбинация механизмов шага 3; отвергнутые варианты с причинами; цена
бездействия. {evidence_note} Объём — 80–150 строк.

ОБЯЗАТЕЛЬНО (решение владельца, BRIEF п.27 — «готовность к действию»):
артефакт несёт секцию «Приёмный чек-лист (6 вопросов владельца)» с
ответами по сути ЭТОГО артефакта — что знаем / чего не знаем на
момент решения; какие решения зафиксированы; что проверять первым и
почему; деньги / команды / сроки исполнения; метрики успеха (KPI с
порогами из verification-plan.md); когда остановить. Плюс структурные
признаки плана: приоритеты P0–P2 решений с последовательностью
исполнения (что блокирует что), контрольная группа (holdout) / A-B
как условие доказательности эффекта, критерии остановки. Артефакт —
ЧИСТЫЙ markdown: без кодовых фенсов вокруг содержания и без
преамбулы вне содержания (гейты исключают фенсы из анализа —
артефакт внутри ```markdown для них невидим, прецедент TASK-hermes-18).

{chat_contract}"""

GATE_FIX_PROMPT = """Ты — тот же агент «Стратег», дорабатываешь свой
артефакт «{name}» по находкам АВТОМАТИЧЕСКИХ ГЕЙТОВ (механические
проверки, не критик). Ниже — текущий артефакт и вывод гейтов.

Правила доработки:
- Находки гейтов механические: чаще всего основание на другой строке,
  маркер типа утверждения не в той строке, структурный элемент
  отсутствует. Исправь по существу.
- Не цитируй вывод гейтов дословно: номера строк и диапазоны из
  находок (например «строки 26–32») сами попадают под ranges-гейт
  (дефект замери 1: ревизия вставила цитату находки в «Ответ на
  находки» — ranges упал на ней).
- Не подгоняй под гейт: не ослабляй возражения, не удаляй пробелы и
  не меняй числа. Если находка требует удалить содержание — отклони с
  явной причиной в блоке «Ответ на находки гейтов».
- Сохрани маркеры [факт]/[гипотеза]/[прогноз]/[допущение].

=== АРТЕФАКТ ===
{draft}
=== ВЫВОД ГЕЙТОВ ===
{gate_output}
=== КОНЕЦ ===

Верни доработанный markdown артефакта «{name}» ОТВЕТОМ В ЧАТ, целиком.
Файлы не пиши."""

PATCH_REVISION_PROMPT = """Ты — тот же агент «Стратег», дорабатываешь свой
артефакт «{name}» по находкам внутреннего критика (рубрика — критерии
хакатона). Это ТОЧЕЧНАЯ правка (targeted patch), а не переписывание:
полный артефакт заново не выдаётся.

Верни ТОЛЬКО JSON-блок (в фи ```json или голым JSON) такого вида:

{{"edits": [{{"find": "<дословный фрагмент черновика, 40–800 символов>",
"replace": "<новый текст>", "finding": "<какую находку закрывает>",
"action": "apply|reject", "reason": "<обязательно при reject>"}}]}}

Правила:
- Не переписывай артефакт целиком: каждая правка — замена одного
  фрагмента (find → replace). Допустимы добавления нового текста.
- find копируется из черновика ДОСЛОВНО (символ в символ): иначе правка
  не применится (0 вхождений — not-found, больше одного — ambiguous).
- Не удаляй целиком секции и не ослабляй возражения.
- Сохрани маркеры [факт]/[гипотеза]/[прогноз]/[допущение].
- Отклонённая находка — action "reject" с явной причиной в reason.
- Не более {max_edits} правок.

=== ЧЕРНОВИК ===
{draft}
=== НАХОДКИ КРИТИКА ===
{findings}
=== КОНЕЦ ===

Верни только JSON-блок ответом в чат. Файлы не пиши."""


# ---------------------------------------------------------------- хелперы

def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def strip_fence(text: str) -> str:
    """Снять внешний markdown-фенс, если модель завернула артефакт."""
    stripped = text.strip()
    match = re.match(r"^```(?:markdown|md)?\s*\n(.*?)\n?```\s*$",
                     stripped, re.DOTALL)
    return match.group(1) if match else stripped


def artifact_sane(text: str) -> tuple[bool, str]:
    """Годность артефакта из сессии (защита от вакуумного прохождения
    гейтов на заглушке — дефект живого прогона 1)."""
    body = strip_fence(text).strip()
    if len(body) < MIN_ARTIFACT_CHARS:
        return False, f"слишком коротко ({len(body)} < {MIN_ARTIFACT_CHARS})"
    if not HEADING_RE.search(body):
        return False, "нет markdown-заголовка"
    return True, ""


def read_inline(path: Path, label: str) -> str:
    return (f"=== {label} ({path.as_posix()}) ===\n"
            + path.read_text(encoding="utf-8-sig", errors="replace")
            + f"\n=== КОНЕЦ {label} ===")


def build_inputs_block(task: dict, artifacts: Path, name: str) -> str:
    """Инлайновый блок входов шага: навык + шаблон + входящие артефакты.

    Входы по шагам: research — рамка + evidence; options — рамка +
    research; strategy-product — рамка + research + options; comms —
    рамка + options + strategy-product; verification — рамка + options +
    strategy-product; decisions — options + strategy-product +
    verification-plan. Прежние project-артефакты (кроме рамки и
    evidence) не входят — цепочка строится из входов ЭТОГО прогона.
    """
    skill, template = STEP_SOURCES[name]
    blocks = [read_inline(REPO_ROOT / skill, "НАВЫК"),
              read_inline(REPO_ROOT / template, "ШАБЛОН")]
    # Рамка нужна всем шагам, кроме решений: там ограничения рамки уже
    # перенесены в тело промпта и в «Ответ человека» внутри options.md
    # (размер промпта решений и так большой — 89 КБ без рамки).
    if name != "decisions.md":
        blocks.append(read_inline(REPO_ROOT / task["brief"],
                                  "РАМКА (замороженный бриф)"))
    if name == "research.md":
        for path in sorted((REPO_ROOT / task["evidence"]).glob("ev-*.md")):
            blocks.append(read_inline(path, path.stem))
    if name in ("options.md", "strategy-product.md", "strategy-comms.md",
                "verification-plan.md", "decisions.md"):
        blocks.append(read_inline(artifacts / "research.md", "ИССЛЕДОВАНИЕ (шаг 2 этого прогона)"))
    if name in ("strategy-product.md", "strategy-comms.md",
                "verification-plan.md", "decisions.md"):
        blocks.append(read_inline(artifacts / "options.md", "ВАРИАНТЫ (шаг 3 этого прогона)"))
    if name in ("strategy-comms.md", "verification-plan.md", "decisions.md"):
        blocks.append(read_inline(artifacts / "strategy-product.md",
                                  "ПРОДУКТОВАЯ СТРАТЕГИЯ (шаг 4 этого прогона)"))
    if name == "decisions.md":
        blocks.append(read_inline(artifacts / "verification-plan.md",
                                  "ПЛАН ПРОВЕРКИ (шаг 4 этого прогона)"))
    return "\n\n".join(blocks)


BODIES = {
    "research.md": RESEARCH_BODY,
    "options.md": OPTIONS_BODY,
    "strategy-product.md": STRATEGY_PRODUCT_BODY,
    "strategy-comms.md": STRATEGY_COMMS_BODY,
    "verification-plan.md": VERIFICATION_BODY,
    "decisions.md": DECISIONS_BODY,
}


def build_prompt(task: dict, artifacts: Path, name: str) -> str:
    return BODIES[name].format(
        inputs_block=build_inputs_block(task, artifacts, name),
        cp2=task["cp2"], cp3=task["cp3"], evidence_note=EVIDENCE_NOTE,
        chat_contract=CHAT_CONTRACT)


def set_run_label(label: str) -> None:
    run_label.set_run_label(label)


def clear_run_label() -> None:
    run_label.clear_run_label()


def run_session(prompt: str, out_dir: Path, name: str, model: str,
                timeout: int, label: str) -> tuple[int, str]:
    """Свежая сессия opencode run; выход — в <out_dir>/<name>.out.

    Механика и учёт $ — как в run_ab.py (метка через eval/run_label.py).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.start").write_text(
        datetime.now(timezone.utc).isoformat() + f" model={model}\n",
        encoding="utf-8")
    set_run_label(label)
    try:
        proc = subprocess.run(
            ["opencode", "run", "--model", model, *chunk_prompt(prompt)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        (out_dir / f"{name}.end").write_text(
            datetime.now(timezone.utc).isoformat() + " TIMEOUT\n",
            encoding="utf-8")
        return EXIT_RUN_FAILED, ""
    finally:
        clear_run_label()
    (out_dir / f"{name}.out").write_text(proc.stdout, encoding="utf-8")
    (out_dir / f"{name}.err").write_text(proc.stderr, encoding="utf-8")
    (out_dir / f"{name}.end").write_text(
        datetime.now(timezone.utc).isoformat() + f" exit={proc.returncode}\n",
        encoding="utf-8")
    return proc.returncode, proc.stdout


def run_gate(argv: list[str], log_dir: Path, name: str) -> tuple[int, str]:
    """Прогон гейта-скрипта репозитория; лог — в <log_dir>/<name>.gate.txt."""
    log_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([sys.executable, *argv], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=GATE_TIMEOUT)
    output = (proc.stdout or "") + (proc.stderr or "")
    (log_dir / f"{name}.gate.txt").write_text(
        f"$ python3 {' '.join(argv)}\nexit={proc.returncode}\n\n{output}",
        encoding="utf-8")
    return proc.returncode, output


def gates_for_artifact(name: str, artifacts: Path, task: dict) -> list[tuple[str, list[str]]]:
    """Гейты шага для артефакта цепочки: (имя, argv)."""
    path = str(artifacts / name)
    gates: list[tuple[str, list[str]]] = [
        (f"sources-{name}", ["scripts/check_sources.py", path]),
        (f"transferability-{name}",
         ["scripts/check_transferability.py", path]),
    ]
    if name == "options.md":
        gates.append(("options", ["scripts/check_options.py", path]))
        gates.append(("complexity", ["scripts/check_complexity.py", path]))
        gates.append(("ranges", ["scripts/check_ranges.py", path]))
    if name in STEP45_ARTIFACTS:
        # Гейты «готовности к действию» — на весь этап 4–5 (дефект
        # области действия TASK-hermes-20: было только strategy-product).
        gates.append(("acceptance", ["scripts/check_acceptance.py", path]))
        gates.append(("actionability",
                      ["scripts/check_actionability.py", path]))
    if name in ("strategy-product.md", "strategy-comms.md",
                "verification-plan.md", "decisions.md"):
        gates.append(("ranges", ["scripts/check_ranges.py", path]))
    if name == "decisions.md":
        gates.append(("decisions", ["scripts/check_decisions.py", path]))
    return gates


def generate_with_gates(prompt: str, artifact: Path, gates: list,
                        work_dir: Path, name: str, timeout: int,
                        label: str, manifest: list, force: bool) -> bool:
    """Сессия → артефакт → гейты; провал гейтов — ревизионная сессия
    с выводом гейтов (до MAX_GATE_ROUNDS). Идемпотентность: готовый
    зелёный артефакт переиспользуется (урок t11). Негодный выход
    сессии (заглушка/нарратив) — ретрай свежей сессией, гейты на нём
    не запускаются (дефект живого прогона 1: вакуумный зелёный)."""
    if artifact.is_file() and artifact.stat().st_size > 0 and not force:
        sane, _ = artifact_sane(artifact.read_text(encoding="utf-8"))
        failures = []
        if sane:
            for gate_name, argv in gates:
                code, _ = run_gate(argv, work_dir / "gates", gate_name)
                if code != 0:
                    failures.append(gate_name)
        if sane and not failures:
            manifest.append(f"- {name}: ПЕРЕИСПОЛЬЗОВАН (зелёный, сессия не запускалась)")
            print(f"[{name}] переиспользован (гейты зелёные)", flush=True)
            return True

    for attempt in (1, 2):
        code, text = run_session(prompt, work_dir / name.replace(".md", ""),
                                 f"session{attempt}", MODEL, timeout,
                                 f"О4: {label}-{name.replace('.md', '')}")
        manifest.append(f"- {name}: session{attempt} exit={code}, "
                        f"символов в выходе {len(text.strip())}")
        if code == 0 and text.strip():
            sane, why = artifact_sane(text)
            if sane:
                break
            manifest.append(f"- {name}: выход негоден ({why}) — "
                            f"сессия не засчитана")
            print(f"[{name}] выход негоден ({why})", flush=True)
        else:
            manifest.append(f"- {name}: сессия без годного выхода "
                            f"(exit={code})")
        if attempt == 2:
            manifest.append(f"- {name}: ПРОВАЛ — две сессии без годного "
                            f"артефакта")
            print(f"[{name}] ПРОВАЛ: нет годного артефакта", flush=True)
            return False

    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(strip_fence(text), encoding="utf-8")

    for round_no in range(1, MAX_GATE_ROUNDS + 1):
        failures = []
        for gate_name, argv in gates:
            code, output = run_gate(argv, work_dir / "gates",
                                    f"{gate_name}-r{round_no}")
            if code != 0:
                failures.append((gate_name, output))
        if not failures:
            manifest.append(f"- {name}: гейты зелёные (раунд {round_no})")
            print(f"[{name}] гейты зелёные (раунд {round_no})", flush=True)
            return True
        joined = "\n\n".join(f"--- {n} (exit≠0) ---\n{o.strip()[:1500]}"
                             for n, o in failures)
        manifest.append(f"- {name}: раунд {round_no} — провал гейтов: "
                        f"{[n for n, _ in failures]} → ревизия")
        print(f"[{name}] раунд {round_no}: провал {[n for n, _ in failures]}"
              f" → ревизия", flush=True)
        code, text = run_session(
            GATE_FIX_PROMPT.format(name=name, draft=artifact.read_text(
                encoding="utf-8"), gate_output=joined),
            work_dir / name.replace(".md", ""), f"fix-r{round_no}", MODEL,
            timeout, f"О4: {label}-{name.replace('.md', '')}-fix{round_no}")
        manifest.append(f"- {name}: fix-r{round_no} exit={code}")
        if code != 0 or not text.strip():
            manifest.append(f"- {name}: ПРОВАЛ ревизии (exit={code})")
            return False
        sane, why = artifact_sane(text)
        if not sane:
            manifest.append(f"- {name}: ревизия негодна ({why}) — "
                            f"артефакт не перезаписан")
            return False
        artifact.write_text(strip_fence(text), encoding="utf-8")

    codes = {g: run_gate(argv, work_dir / "gates", f"{g}-final")[0]
             for g, argv in gates}
    bad = [g for g, c in codes.items() if c != 0]
    manifest.append(f"- {name}: ИТОГ — гейты {codes}")
    print(f"[{name}] итог гейтов: {codes}", flush=True)
    return not bad


def critic_detector(artifacts: list[Path], out_dir: Path, tag: str,
                    timeout: int, manifest: list) -> str:
    """Критик-детектор: свежая изолированная сессия критика на пакете
    артефактов (механика run_critic.py, единая рубрика). Возвращает
    текст находок (пустая строка — провал)."""
    code = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "run_critic.py"),
         "--artifact", ",".join(str(p) for p in artifacts),
         "--rubric", UNITARY_RUBRIC, "--mode", "critic",
         "--out", str(out_dir), "--tag", tag,
         "--timeout", str(timeout)],
        cwd=REPO_ROOT).returncode
    manifest.append(f"- критик {tag}: exit={code}")
    findings_path = out_dir / "critic.out"
    if code != 0 or not findings_path.is_file():
        return ""
    findings = findings_path.read_text(encoding="utf-8-sig", errors="replace")
    if not findings.strip():
        # Дефект «exit 0 ≠ непустой выход» (TASK-5/9): пустой выход —
        # не измерение и не находки.
        manifest.append(f"- критик {tag}: ПУСТОЙ выход при exit=0 — "
                        f"находок нет")
        return ""
    return findings


def patch_revision(artifact: Path, findings: str, work_dir: Path,
                   name: str, timeout: int, label: str,
                   manifest: list,
                   prompt_template: str | None = None) -> bool:
    """Точечная ревизия по находкам критика (механика critic-loop2):
    JSON-правок → apply_revision.py с проверками целостности; при
    BROKEN/нуле правок финал = черновик дословно (честная деградация).

    prompt_template — переопределение промпта правок (по умолчанию
    PATCH_REVISION_PROMPT для находок критика); используется драйвером
    ревизии по находкам ГЕЙТОВ (TASK-hermes-20). Формат тот же:
    name/draft/findings/max_edits.
    """
    template = prompt_template or PATCH_REVISION_PROMPT
    draft = artifact.read_text(encoding="utf-8")
    backup = artifact.with_suffix(".md.critic-backup")
    backup.write_text(draft, encoding="utf-8")
    code, reply = run_session(
        template.format(name=name, draft=draft,
                        findings=findings, max_edits=MAX_PATCH_EDITS),
        work_dir / name.replace(".md", ""), "patch", MODEL, timeout,
        f"О4: {label}-{name.replace('.md', '')}-patch")
    manifest.append(f"- {name}: patch-сессия exit={code}")
    if code != 0 or not reply.strip():
        manifest.append(f"- {name}: патч-сессия пуста — финал = черновик")
        return False
    patches = parse_patch_json(reply)
    if patches is None:
        artifact.write_text(draft, encoding="utf-8")
        manifest.append(f"- {name}: JSON правок не разобран — финал = "
                        f"черновик (fallback)")
        return False
    edits = [e for e in patches.get("edits", []) if isinstance(e, dict)]
    patches["edits"] = edits[:MAX_PATCH_EDITS]
    patches_path = work_dir / name.replace(".md", "") / "patches.json"
    patches_path.parent.mkdir(parents=True, exist_ok=True)
    patches_path.write_text(json.dumps(patches, ensure_ascii=False,
                                       indent=2), encoding="utf-8")
    final_path = work_dir / name.replace(".md", "") / "final.md"
    applier = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "apply_revision.py"),
         "--draft", str(backup), "--patches", str(patches_path),
         "--out", str(final_path),
         "--report", str(work_dir / name.replace(".md", "") / "revision-report.md")],
        cwd=REPO_ROOT, capture_output=True, text=True)
    manifest.append(f"- {name}: apply_revision exit={applier.returncode}")
    summary = (applier.stdout or "").strip()
    if summary:
        # Итог точечных правок в журнал: applied/not_found/fallback/
        # integrity — честная деградация видна в манифесте прогона.
        manifest.append(f"- {name}: {summary}")
    if applier.returncode != 0 or not final_path.is_file():
        artifact.write_text(draft, encoding="utf-8")
        manifest.append(f"- {name}: апдейтер упал — финал = черновик")
        return False
    artifact.write_text(final_path.read_text(encoding="utf-8"),
                        encoding="utf-8")
    return True


def step0_carry_brief(task: dict, artifacts: Path, manifest: list) -> bool:
    """Шаг 0: рамка заморожена (ЧЕКПОИНТ 1 пройден) — перенос дословно."""
    src = REPO_ROOT / task["brief"]
    dst = artifacts / "brief.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8-sig"), encoding="utf-8")
    manifest.append(f"- brief.md перенесён дословно из {task['brief']} "
                    f"(sha256={sha256_of(dst)}); ЧЕКПОИНТ 1 пройден ранее, "
                    f"источник — оператор, репетиция демо")
    code, _ = run_gate(["scripts/check_sources.py", str(dst)],
                       artifacts.parent / "gates", "sources-brief")
    manifest.append(f"- brief.md: check_sources exit={code}")
    return code == 0


def step1_verify_evidence(task: dict, artifacts: Path, work_dir: Path,
                          manifest: list) -> bool:
    """Шаг 1: материалы перепроверяются, не переделываются.

    Перепроверка: резолвимость ссылок вживую (check_citations), гейт
    «число → содержание evidence» (check_evidence_links), сверка
    оснований (check_sources) и детерминированный пересчёт срезов из
    первоисточника (recompute_telco_slices --out в каталог прогона).
    """
    ok = True
    if task["evidence_task"] == "demo-retention":
        ev = [str(REPO_ROOT / task["evidence"] / p)
              for p in ("ev-001-mixpanel-benchmarks.md",
                        "ev-002-telco-dataset-stats.md",
                        "ev-003-arxiv-churn-drivers.md")]
    else:
        ev = [str(p) for p in
              sorted((REPO_ROOT / task["evidence"]).glob("ev-*.md"))]
    checks = [
        ("citations", ["scripts/check_citations.py", *ev]),
        ("evidence-links",
         ["scripts/check_evidence_links.py", "--task", task["evidence_task"]]),
        ("sources", ["scripts/check_sources.py", *ev]),
    ]
    if task["evidence_task"] == "demo-retention":
        checks.append(("recompute", ["eval/recompute_telco_slices.py",
                                     "--out", str(work_dir / "recompute")]))
    for name, argv in checks:
        code, _ = run_gate(argv, work_dir / "gates", f"step1-{name}")
        manifest.append(f"- шаг 1: {name} exit={code}")
        ok = ok and code == 0
    note = work_dir / "step1-verification.md"
    lines = ["# Шаг 1 (перепроверка, не переделка)",
             "",
             "Основание закрыто и source-verified (TASK-8: 137 срезов, 0",
             "расхождений). Переделка закрытого evidence — анти-круг;",
             "перепроверяем резолвимость, живой HTTP и детерминированный",
             "пересчёт. Провенанс записей:"]
    for path in ev:
        lines.append(f"- `{Path(path).relative_to(REPO_ROOT).as_posix()}` "
                     f"sha256={sha256_of(Path(path))}")
    note.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ok


def run_path(task_name: str, runs_dir: Path, timeout: int, force: bool,
             from_step: int, no_critic: bool) -> int:
    task = TASKS[task_name]
    artifacts = runs_dir / "artifacts"
    work_dir = runs_dir
    label = task["label"]
    manifest: list[str] = [
        f"# Полный путь под текущим прод-конфигом — {task_name}",
        "",
        f"- старт: {datetime.now(timezone.utc).isoformat()}",
        f"- конфиг: шаг 3 — база (навык options); шаги 4–5 — критик-"
        f"детектор + все гейты (§32.0)",
        f"- прод-конфиг и предрегистрация: measurements.md §32",
        f"- модель сессий: {MODEL}",
        f"- контракт сессий: входы инлайном, артефакт — ответом в чат; "
        f"порог годности {MIN_ARTIFACT_CHARS} символов + заголовок",
    ]
    print(f"== полный путь {task_name} → {runs_dir}", flush=True)

    if from_step <= 0 and not step0_carry_brief(task, artifacts, manifest):
        (runs_dir / "manifest.md").write_text("\n".join(manifest) + "\n",
                                              encoding="utf-8")
        return EXIT_RUN_FAILED

    if from_step <= 1 and not step1_verify_evidence(task, artifacts,
                                                    work_dir, manifest):
        (runs_dir / "manifest.md").write_text("\n".join(manifest) + "\n",
                                              encoding="utf-8")
        return EXIT_RUN_FAILED

    for name, step_no in (("research.md", 2), ("options.md", 3)):
        if from_step > step_no:
            continue
        prompt = build_prompt(task, artifacts, name)
        ok = generate_with_gates(prompt, artifacts / name,
                                 gates_for_artifact(name, artifacts, task),
                                 work_dir, name, timeout, label, manifest,
                                 force)
        if not ok:
            (runs_dir / "manifest.md").write_text("\n".join(manifest) + "\n",
                                                  encoding="utf-8")
            return EXIT_RUN_FAILED

    # Шаг 4: три артефакта стратегий, каждый под своим навыком.
    step4 = ["strategy-product.md", "strategy-comms.md",
             "verification-plan.md"]
    if from_step <= 4:
        for name in step4:
            prompt = build_prompt(task, artifacts, name)
            ok = generate_with_gates(prompt, artifacts / name,
                                     gates_for_artifact(name, artifacts, task),
                                     work_dir, name, timeout, label,
                                     manifest, force)
            if not ok:
                (runs_dir / "manifest.md").write_text(
                    "\n".join(manifest) + "\n", encoding="utf-8")
                return EXIT_RUN_FAILED

        # Критик-детектор шага 4: пакетный прогон на три артефакта.
        if not no_critic:
            findings = critic_detector(
                [artifacts / n for n in step4],
                work_dir / "critic4", f"{label}-critic4", timeout, manifest)
            if findings:
                (work_dir / "critic4" / "findings.md").write_text(
                    findings, encoding="utf-8")
                for name in step4:
                    patch_revision(artifacts / name, findings, work_dir,
                                   name, timeout, label, manifest)
                codes = {}
                for name in step4:
                    for gate_name, argv in gates_for_artifact(
                            name, artifacts, task):
                        code, _ = run_gate(argv, work_dir / "gates",
                                           f"post-critic-{gate_name}")
                        codes[gate_name] = code
                bad = [g for g, c in codes.items() if c != 0]
                manifest.append(f"- шаг 4 после критика: гейты {codes}")
                print(f"[шаг 4 после критика] гейты: {codes}", flush=True)
                if bad:
                    for name in step4:
                        artifact = artifacts / name
                        fails = []
                        for g, argv in gates_for_artifact(name, artifacts,
                                                           task):
                            code, output = run_gate(argv, work_dir / "gates",
                                                    f"post-critic2-{g}")
                            if code != 0:
                                fails.append((g, output))
                        if not fails:
                            continue
                        joined = "\n\n".join(
                            f"--- {n} ---\n{o.strip()[:1500]}"
                            for n, o in fails)
                        code, text = run_session(
                            GATE_FIX_PROMPT.format(
                                name=name,
                                draft=artifact.read_text(encoding="utf-8"),
                                gate_output=joined),
                            work_dir / name.replace(".md", ""),
                            "fix-post-critic", MODEL, timeout,
                            f"О4: {label}-{name.replace('.md', '')}-fixpc")
                        if code == 0 and text.strip():
                            sane, _ = artifact_sane(text)
                            if sane:
                                artifact.write_text(strip_fence(text),
                                                    encoding="utf-8")
                                manifest.append(f"- {name}: fix-post-critic "
                                                f"exit={code}")

    # Шаг 5: решения.
    if from_step <= 5:
        prompt = build_prompt(task, artifacts, "decisions.md")
        ok = generate_with_gates(prompt, artifacts / "decisions.md",
                                 gates_for_artifact("decisions.md",
                                                    artifacts, task),
                                 work_dir, "decisions.md", timeout, label,
                                 manifest, force)
        if not ok:
            (runs_dir / "manifest.md").write_text("\n".join(manifest) + "\n",
                                                  encoding="utf-8")
            return EXIT_RUN_FAILED
        if not no_critic:
            findings = critic_detector([artifacts / "decisions.md"],
                                       work_dir / "critic5",
                                       f"{label}-critic5", timeout, manifest)
            if findings:
                (work_dir / "critic5" / "findings.md").write_text(
                    findings, encoding="utf-8")
                patch_revision(artifacts / "decisions.md", findings,
                               work_dir, "decisions.md", timeout, label,
                               manifest)
                codes = {}
                for gate_name, argv in gates_for_artifact(
                        "decisions.md", artifacts, task):
                    code, _ = run_gate(argv, work_dir / "gates",
                                       f"post-critic-{gate_name}")
                    codes[gate_name] = code
                manifest.append(f"- шаг 5 после критика: гейты {codes}")
                print(f"[шаг 5 после критика] гейты: {codes}", flush=True)
                if any(c != 0 for c in codes.values()):
                    (runs_dir / "manifest.md").write_text(
                        "\n".join(manifest) + "\n", encoding="utf-8")
                    return EXIT_RUN_FAILED

    # Финальная сводка гейтов по всей цепочке (цепочка &&, коды явно).
    manifest.append("")
    manifest.append("## Финальная сводка гейтов")
    manifest.append("")
    all_ok = True
    for name in CHAIN:
        artifact = artifacts / name
        if not artifact.is_file():
            manifest.append(f"- {name}: ОТСУТСТВУЕТ")
            all_ok = False
            continue
        for gate_name, argv in gates_for_artifact(name, artifacts, task):
            code, _ = run_gate(argv, work_dir / "gates", f"final-{gate_name}")
            manifest.append(f"- {gate_name}: exit={code}")
            all_ok = all_ok and code == 0
        manifest.append(f"- {name}: sha256={sha256_of(artifact)}")
    manifest.append("")
    manifest.append(f"- ИТОГ: {'все гейты зелёные' if all_ok else 'ЕСТЬ ПРОВАЛЫ'}")
    (runs_dir / "manifest.md").write_text("\n".join(manifest) + "\n",
                                          encoding="utf-8")
    print(f"== итог: {'зелено' if all_ok else 'ПРОВАЛЫ'}", flush=True)
    return EXIT_OK if all_ok else EXIT_RUN_FAILED


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_full_case.py",
        description="Полный путь продукта (шаги 0–5) под текущим "
                    "прод-конфигом (TASK-hermes-18 §32).")
    parser.add_argument("--task", required=True, choices=sorted(TASKS))
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="перегенерировать артефакты, не переиспользовать")
    parser.add_argument("--from-step", type=int, default=0, choices=range(0, 6))
    parser.add_argument("--no-critic", action="store_true",
                        help="без критик-детектора на шагах 4–5")
    args = parser.parse_args(argv)

    task = TASKS[args.task]
    runs_dir = (Path(args.runs_dir) if args.runs_dir
                else REPO_ROOT / task["default_runs_dir"])
    if args.dry_run:
        print(f"task={args.task} runs-dir={runs_dir} timeout={args.timeout}")
        print("шаги: 0 (перенос рамки) → 1 (перепроверка evidence) → "
              "2 (research) → 3 (options, база) → 4 (стратегии + критик) → "
              "5 (decisions + критик)")
        print("контракт сессий: входы инлайном, артефакт — ответом в чат, "
              f"порог годности {MIN_ARTIFACT_CHARS} символов + заголовок")
        print("гейты финала: sources/transferability по всей цепочке; "
              "options/complexity/ranges на options; acceptance/"
              "actionability/ranges на всех артефактах шагов 4–5 "
              "(strategy-product, strategy-comms, verification-plan, "
              "decisions); decisions на decisions.md")
        return EXIT_OK
    return run_path(args.task, runs_dir, args.timeout, args.force,
                    args.from_step, args.no_critic)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
