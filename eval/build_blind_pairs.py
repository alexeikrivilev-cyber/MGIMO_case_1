#!/usr/bin/env python3
"""build_blind_pairs.py — слепые пары для владельца (TASK-hermes-13 §2, BRIEF п.22).

Решение владельца (2026-11-17 10:15): слепое попарное сравнение с
человеком-судьёй — основной ground truth проекта. Этот сборщик готовит
10 пар ответов на ОДНОЙ задаче (демо-retention): агент (руки продукта)
против обычного чата + пары развилки «курация vs lean/hybrid».

Правила (зафиксированы ДО сборки, анти-cherry-picking):
1. Один артефакт на руку — без выбора «лучшего из нескольких»: для рук
   с k=3 (t12) берётся цепочка с ИНДЕКСОМ, общим для обеих рук пары
   (правило «та же цепочка i»), выбор индекса не по оценкам.
2. Обычный чат отвечает на ДОСЛОВНЫЙ запрос РП (дизайн B11: чат не
   производит брифа), агенты — на замороженном брифе. Асимметрия
   входов названа явно: это продуктовая сравнение «путь агента против
   одного диалога», а не «одинаковый вход».
3. Слепление снимает ПОДПИСИ (имена рук, пути, id прогонов), не
   сигнатуры: артефактыCritic-loop2/совета несят структурные следы в
   самом содержимом — это часть их реального выхода, названо в отчёте.
4. Порядок A/B в каждой паре перемешивается детерминированно
   (random.Random(SEED)), seed и правило записаны; ключ лежит отдельно
   и предъявляется ПОСЛЕ суждения владельца.

Выход (eval/runs/t13-blindpairs/):
  pairs.md     — дайджесты пар (формат Telegram: структура + суть
                 вариантов), слепые A/B;
  pairs.json   — полные слепые тексты + метаданные (для владельца,
                 кто откроет репозиторий);
  key.md       — ключ «буква → рука» + provenance (путь, sha256,
                 байты) — НЕ для предъявления до суждения.

Контракт CLI:
    python3 eval/build_blind_pairs.py [--out DIR] [--dry-run]

Коды возврата: 0 — собрано; 2 — артефакт не найден.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_USAGE = 2

SEED = 20261117

# Руки и их артефакты (путь относительно корня). Один запуск на руку.
ARMS: dict[str, dict] = {
    "plain-chat": {"artifact": "eval/runs/b11-plainchat/final.md",
                   "step": "один диалог на дословный запрос РП (B11)"},
    "skill": {"artifact": "eval/runs/ab-options-demo-retention/skill/final.md",
              "step": "шаг 3, навык options"},
    "critic-loop2": {"artifact": "eval/runs/cl2-demo/critic-loop2/final.md",
                     "step": "шаг 3, навык + критик + точечная ревизия"},
    "council-lite": {"artifact": "eval/runs/ab-options-demo-retention/council-lite/final.md",
                     "step": "шаг 3, совет 3 роли + синтез"},
    "curation#0": {"artifact": "eval/runs/t12-skills/options/curation/final.md",
                   "step": "шаг 3, курация (навык options), цепочка 0"},
    "curation#1": {"artifact": "eval/runs/t12-skills/options/curation/final-1.md",
                   "step": "шаг 3, курация, цепочка 1"},
    "curation#2": {"artifact": "eval/runs/t12-skills/options/curation/final-2.md",
                   "step": "шаг 3, курация, цепочка 2"},
    "lean#0": {"artifact": "eval/runs/t12-skills/options/lean/final.md",
               "step": "шаг 3, lean, цепочка 0"},
    "lean#1": {"artifact": "eval/runs/t12-skills/options/lean/final-1.md",
               "step": "шаг 3, lean, цепочка 1"},
    "lean#2": {"artifact": "eval/runs/t12-skills/options/lean/final-2.md",
               "step": "шаг 3, lean, цепочка 2"},
    "hybrid#0": {"artifact": "eval/runs/t12-skills/options/hybrid/final.md",
                 "step": "шаг 3, гибрид, цепочка 0"},
}

# Пары (порядок в списке — порядок предъявления; A/B внутри пары
# перемешивается seed'ом). Правило отбора: без выбора по оценкам.
# note — вопрос пары БЕЗ имён рук (слепление: имена только в key.md);
# arm_note — человекочитаемое пояснение для ключа.
PAIRS: list[tuple[str, str, str, str]] = [
    ("plain-chat", "skill", "Полный путь против одного диалога",
     "агент против обычного чата (база шага 3)"),
    ("plain-chat", "critic-loop2", "Полный путь против одного диалога",
     "агент против обычного чата (сильная рука)"),
    ("plain-chat", "council-lite", "Полный путь против одного диалога",
     "агент против обычного чата (совет)"),
    ("plain-chat", "curation#0", "Полный путь против одного диалога",
     "агент против обычного чата (свежая курация)"),
    ("skill", "council-lite", "Два способа получить набор вариантов (шаг 3)",
     "развилка прод-конфига: база против совета"),
    ("skill", "critic-loop2", "Два способа получить набор вариантов (шаг 3)",
     "развилка прод-конфига: база против ревизии"),
    ("curation#0", "lean#0", "Два дизайна инструкций для одного шага",
     "развилка навыков: курация против lean (цепочка 0)"),
    ("curation#1", "lean#1", "Два дизайна инструкций для одного шага",
     "развилка навыков: курация против lean (цепочка 1)"),
    ("curation#2", "lean#2", "Два дизайна инструкций для одного шага",
     "развилка навыков: курация против lean (цепочка 2)"),
    ("lean#0", "hybrid#0", "Два дизайна инструкций для одного шага",
     "развилка навыков: lean против гибрида (цепочка 0)"),
]

HEADER_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)
SUBTITLE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?\*\*\s*(?:Суть|Что требует|Экономика)\s*[.:]?\s*\*\*\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def digest(text: str, limit: int = 1100) -> str:
    """Компактный дайджест артефакта: каркас вариантов + суть.

    Для Telegram: заголовки секций и строка «Суть» каждой карточки
    (форматы карточек разные: «**Суть.** …» у навыка, «- **Суть:** …»
    у t12 — оба разобраны). Полный текст — в pairs.json / репозитории.
    """
    text = strip_identifiers(text)
    lines: list[str] = []
    title = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title:
        lines.append(f"• {title.group(1).strip()}")
    sections = re.split(r"\n(?=#{2,3}\s)", text)
    for section in sections:
        section_lines = section.splitlines()
        if not section_lines:
            continue
        match = re.match(r"^(#{2,3})\s+(.*)$", section_lines[0])
        if not match:
            continue
        level, head = match.groups()
        head = head.strip()
        lines.append(f"{'  ' * (len(level) - 2)}• {head}")
        subtitle = re.search(r"^\s*(?:[-*]\s*)?\*\*\s*Суть\s*[.:]?\s*\*\*\s*(.+)$",
                             section, re.MULTILINE | re.IGNORECASE)
        if subtitle:
            lines.append(f"    {subtitle.group(1).strip()[:220]}")
    out = "\n".join(lines)
    return out[:limit]


def strip_identifiers(text: str) -> str:
    """Слепление на уровне подписей: имена рук, пути, id прогонов.

    Снимаются ПОДПИСИ (метаданные), не содержимое: преамбула council-
    артефакта («протокол council-design §4 Phase 4») — самоидентификация
    руки, её убираем; структурные следы в самом разборе (dissent-секция,
    «Ответ на находки критика») — часть выхода руки, названы в отчёте.
    """
    for token in ("critic-loop2", "council-lite", "council-full", "council-design",
                  "council", "plain-chat", "curation", "lean", "hybrid", "skill",
                  "t12-skills", "b11-plainchat", "ab-options", "cl2-demo",
                  "eval/runs", "run-2026-11-16-01"):
        text = re.sub(rf"\b{re.escape(token)}\b", "…", text, flags=re.IGNORECASE)
    text = re.sub(r"ses_[A-Za-z0-9]+", "…", text)
    return text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="build_blind_pairs.py",
        description="Слепые пары для владельца (TASK-hermes-13 §2, BRIEF п.22).",
    )
    parser.add_argument("--out", default=str(REPO_ROOT / "eval" / "runs" / "t13-blindpairs"))
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    rng = random.Random(SEED)

    loaded: dict[str, dict] = {}
    for arm, spec in ARMS.items():
        path = REPO_ROOT / spec["artifact"]
        if not path.is_file():
            print(f"артефакт не найден: {path} (рука {arm})", file=sys.stderr)
            return EXIT_USAGE
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        loaded[arm] = {"text": text, "sha": sha256_file(path), "bytes": len(text.encode())}

    pairs_out: list[dict] = []
    for idx, (arm_a, arm_b, note, arm_note) in enumerate(PAIRS, start=1):
        # Детерминированный слепой порядок A/B.
        flip = rng.random() < 0.5
        first, second = (arm_b, arm_a) if flip else (arm_a, arm_b)
        pairs_out.append({
            "n": idx,
            "note": note,
            "A": first,
            "B": second,
            "A_digest": digest(loaded[first]["text"]),
            "B_digest": digest(loaded[second]["text"]),
            "A_text": strip_identifiers(loaded[first]["text"]),
            "B_text": strip_identifiers(loaded[second]["text"]),
        })

    out_dir.mkdir(parents=True, exist_ok=True)

    # pairs.json — полные слепые тексты + метаданные (без имён рук в текстах).
    public_pairs = [{k: v for k, v in p.items() if k not in ("A", "B")} for p in pairs_out]
    (out_dir / "pairs.json").write_text(json.dumps({
        "seed": SEED,
        "task": "demo-retention (замороженный бриф project/council/run-2026-11-16-01)",
        "rules": [
            "один артефакт на руку; для рук с k=3 — цепочка с общим индексом (правило «та же цепочка i»), не по оценкам",
            "plain-chat отвечал на дословный запрос РП (дизайн B11), агенты — на замороженном брифе; асимметрия входов названа",
            "слепление снимает подписи, не сигнатуры содержимого",
            "порядок A/B — random.Random(seed), детерминирован",
        ],
        "pairs": public_pairs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # pairs.md — формат для Telegram (дайджесты).
    lines = [
        "# Слепые пары для суждения владельца (TASK-hermes-13 §2, BRIEF п.22)",
        "",
        f"Задача: demo-retention (один замороженный бриф). Seed: {SEED}.",
        "В каждой паре — два полных ответа на одну задачу (A и B).",
        "Полные тексты — в `pairs.json` (и в репозитории по ключу после",
        "суждения). Просьба: по каждой паре выбрать, какой ответ лучше",
        "для руководителя продукта, и коротко — почему.",
        "",
        "> Асимметрия входов названа: обычный чат отвечал на дословный",
        "> запрос РП (как в замере B11), агенты — на замороженном брифе",
        "> полного пути. Слепление снимает подписи, не сигнатуры",
        "> содержимого (ревизия и совет несят структурные следы в самом",
        "> артефакте — это часть их реального выхода).",
        "",
    ]
    for pair in pairs_out:
        lines.append(f"## Пара {pair['n']} ({pair['note']})")
        lines.append("")
        lines.append(f"**A:**")
        lines.append("")
        lines.append("```")
        lines.append(pair["A_digest"])
        lines.append("```")
        lines.append("")
        lines.append(f"**B:**")
        lines.append("")
        lines.append("```")
        lines.append(pair["B_digest"])
        lines.append("```")
        lines.append("")
    (out_dir / "pairs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # key.md — ключ и provenance (предъявляется после суждения).
    key_lines = [
        "# Ключ слепых пар (НЕ предъявлять до суждения владельца)",
        "",
        f"Seed: {SEED}; перемешивание A/B — random.Random(seed), детерминировано.",
        "note в парах — нейтральный вопрос; пояснения с именами рук — только здесь.",
        "",
        "| Пара | A | B | Вопрос пары (нейтральный) | Состав пары (после суждения) |",
        "|---|---|---|---|---|",
    ]
    for pair, spec in zip(pairs_out, PAIRS):
        key_lines.append(
            f"| {pair['n']} | {pair['A']} | {pair['B']} | {pair['note']} | {spec[3]} |"
        )
    key_lines += ["", "## Provenance (путь, sha256, байты)", "",
                  "| Рука | Путь | sha256 | Байт |", "|---|---|---|---|"]
    for arm, spec in ARMS.items():
        info = loaded[arm]
        key_lines.append(f"| {arm} | `{spec['artifact']}` | {info['sha']} | {info['bytes']} |")
    (out_dir / "key.md").write_text("\n".join(key_lines) + "\n", encoding="utf-8")

    print(f"пары: {len(pairs_out)}; выход: {out_dir}")
    for pair in pairs_out:
        print(f"  пара {pair['n']}: A={pair['A']} B={pair['B']}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
