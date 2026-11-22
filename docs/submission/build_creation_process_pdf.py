#!/usr/bin/env python3
"""build_creation_process_pdf.py — «Описание процесса создания» (PDF).

Ответ жюри на вопрос «как создавалась работа»: проблема и разделы,
ИИ-инструменты, ключевые промпты, шаги от идеи до кабинета, вход и
защита данных, ручные этапы. Текст — docs/submission/7-creation-process.md.

Плашки («скриншоты») — НЕ нарисованы: часть отрендерена из РЕАЛЬНЫХ
файлов репозитория (фрагменты), часть — дословные выводы команд,
снятые при сборке контура (systemctl/git/pytest/cost_report; команды
указаны в самих плашках). Reusable-часть стиля берётся из
build_submission_pdf.py, чтобы документы сдачи выглядели единообразно.

Запуск: python3 docs/submission/build_creation_process_pdf.py
Выход:  docs/submission/описание-процесса-создания.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_submission_pdf import (  # noqa: E402
    ACCENT,
    Doc,
    MARGIN,
    MUTED,
    ROOT,
    W,
    f,
    fragment_plate,
    plate_from_file,
    plate_from_text,
    wrap,
)
from PIL import ImageDraw  # noqa: E402

MD = HERE / "7-creation-process.md"
OUT = HERE / "описание-процесса-создания.pdf"

# --- дословные выводы, снятые с контура создания (команды в плашках) ---
LIVE_PLATE = """\
$ systemctl status opencode-server.service hermes-gateway.service --no-pager
● opencode-server.service - OpenCode Headless Server
     Active: active (running) since Mon 2026-11-16 18:48:34 +04; 6 days ago
   Main PID: 103786 (opencode)   Tasks: 21   Memory: 251.9M (peak: 493.0M)
● hermes-gateway.service - Hermes Agent Gateway - Messaging Platform Integration
     Active: active (running) since Mon 2026-11-16 15:11:01 +04; 6 days ago
   Main PID: 8151 (hermes)       Tasks: 323  Memory: 6.7G (peak: 10.1G)

$ git log --format='%ad' --date=format:'%d.%m' | sort | uniq -c
     35 16.11        # init → day-1 research → PRD/ROADMAP
     32 17.11        # агент «Стратег», демо-проект, council
     43 18.11        # стенд 20 задач с предрегистрацией, held-out, task 26
      1 22.11        # правка доков сдачи + этот документ
$ git log --oneline | wc -l
111

$ python3 -m pytest -q
561 passed in 52.52s

$ python3 scripts/cost_report.py
Итого (dev + prod): 60.02"""

REGLAMENT_PLATE = """\
# Регламент харнесса (AGENTS.md контрольной плоскости, оригинал на англ.):
- Code / implementation / refactor / test tasks: delegate through Hermes —
  hermes-lead --dir <project> "<prompt>". ... NEVER call opencode-worker or
  opencode run directly from the project agent — that skips review and
  breaks the quality loop.
- Visual / design / UI tasks: opendesign-worker --dir <project> "<prompt>",
  also routed via Hermes for non-trivial work.
- NEVER start opencode serve, hermes, openclaw gateway or any harness
  daemon by hand (no &, no nohup, no direct binary).
- One OpenClaw agent per project: own workspace, own state, own sessions,
  own heartbeat (30m), own skills. One Telegram bot per project."""

SECRETS_PLATE = """\
$ git log -p --all | grep -cE "sk-[A-Za-z0-9]{20,}"
0
# .opencode/opencode.json (конфиг разработки):
#   "apiKey": "{env:STEPFUN_API_KEY}"   ← значение только из окружения
# README §5: простой grep "sk-" для этой проверки НЕ годится —
# он матчит task-, ask-matt, disk-based (25 совпадений, ни одного — ключ)"""


def render_text(doc: Doc, text: str) -> None:
    """Минимальный markdown-рендер (как render_md, но из строки)."""
    import re

    in_code, buf = False, []
    for raw in text.splitlines():
        if raw.strip().startswith("```"):
            if in_code:
                doc.code("\n".join(buf))
                buf, in_code = [], False
            else:
                in_code = True
            continue
        if in_code:
            buf.append(raw)
            continue
        s = raw.strip()
        if not s:
            doc.y += 6
            continue
        if s.startswith("### "):
            doc.h2(s[4:])
        elif s.startswith("## "):
            doc.h2(s[3:])
        elif s.startswith("# "):
            doc.h1(s[2:])
        elif s.startswith("|"):
            doc.code(raw[:110])
        elif s.startswith(("- ", "* ")):
            doc.bullet(s[2:])
        elif re.match(r"^\d+\. ", s):
            doc.bullet(re.sub(r"^\d+\. ", "", s))
        elif s.startswith(">"):
            doc.text(s.lstrip("> "), size=21, color=MUTED)
        else:
            doc.text(s)
    if in_code and buf:
        doc.code("\n".join(buf))


def _safe(text: str, title: str) -> Image.Image:
    """Плашка с обрезкой строк по ширине (110 символов монадриного 19px
    не влезают в 1060px плашки — режем по 90)."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    lines = [ln[:90] for ln in lines][:20]
    return plate_from_text("\n".join(lines), title)


def _frag(path: Path, title: str, needle: str, before: int = 2,
          after: int = 10) -> Image.Image | None:
    """Фрагмент реального файла вокруг needle (как fragment_plate, но
    с безопасной обрезкой по ширине)."""
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = 0
    if needle:
        for i, ln in enumerate(lines):
            if needle.lower() in ln.lower():
                start = max(0, i - before)
                break
    chunk = [ln.rstrip()[:90] for ln in lines[start:start + after]][:14]
    if not chunk:
        return None
    return plate_from_text("\n".join(chunk), title)


def title_page(doc: Doc) -> None:
    doc._ensure(700)
    d = doc.draw
    y = 300
    font = f(64, bold=True)
    for ln in wrap(d, "Описание процесса создания", font, W - 2 * MARGIN):
        d.text((MARGIN, y), ln, font=font, fill=ACCENT)
        y += 76
    y += 10
    d.line([MARGIN, y, W - MARGIN, y], fill=(210, 214, 222), width=2)
    y += 40
    font = f(30)
    for ln in wrap(d, "Как создавалась работа: автономный контур, команда агентов, "
                      "дисциплина доказательств", font, W - 2 * MARGIN):
        d.text((MARGIN, y), ln, font=font, fill=(28, 28, 32))
        y += 42
    y += 30
    font = f(23)
    for ln in wrap(d, "Разделы (по требованию ТЗ «Описание работы» + вопросы жюри): "
                      "проблема и разделы · ИИ-инструменты · ключевые промпты · "
                      "шаги от идеи до кабинета · вход и защита данных · "
                      "ручные этапы", font, W - 2 * MARGIN):
        d.text((MARGIN, y), ln, font=font, fill=MUTED)
        y += 34
    y += 60
    font = f(24, bold=True)
    for ln in wrap(d, "Кейс MGIMO · «Фабрика продуктов» · 16–22.11.2026 · "
                      "владелец: капитан команды", font, W - 2 * MARGIN):
        d.text((MARGIN, y), ln, font=font, fill=(28, 28, 32))
        y += 36
    doc.y = y + 80


def main() -> int:
    doc = Doc()
    title_page(doc)

    sections = MD.read_text(encoding="utf-8").split("\n## ")
    # первая часть — заголовок + §0
    head = sections[0]
    render_text(doc, head)
    doc.plate(_safe(LIVE_PLATE, "Контур создания — живые выводы (22.11.2026)"),
              "Сервер под автономной работой и результат — как есть")

    after = {
        "2. ИИ-инструменты: перечень и роль каждого": [
            (_safe(REGLAMENT_PLATE, "Регламент харнесса (выдержка)"),
             "Дисциплина исполнения: делегирование и запрет ручного запуска сервисов"),
        ],
        "3. Ключевые промпты и инструкции": [
            (_frag(ROOT / "BRIEF.md", "BRIEF.md — правило останова (п.10)",
                            needle="Правило останова", before=0, after=5),
             "Бриф владельца: остановка фичи — только на плато бенчмарка"),
            (_frag(ROOT / "AGENTS.md", "AGENTS.md — мандат агента",
                            needle="Ты — «Стратег»", before=0, after=5),
             "Мандат продукта: роль и граница «не автономный агент»"),
            (_frag(ROOT / "eval" / "run_full_case.py", "GATE_FIX_PROMPT",
                            needle="GATE_FIX_PROMPT = ", before=0, after=10),
             "Промпт цикла доработки по гейтам (eval/run_full_case.py)"),
        ],
        "4. Шаги от идеи до кабинета": [
            (_safe(
                "$ git log --reverse --format='%h %ad %s' --date=format:'%d.%m %H:%M' | head -3\n"
                "5dc2d8e 16.11 17:23 init: BRIEF.md with hackathon case and owner requirements\n"
                "c002e61 16.11 17:31 add owner stopping rule: feature done only at benchmark plateau\n"
                "90c6480 16.11 17:38 day1: research (benchmarks, hypothesis validation, council,\n"
                "                  ecosystem, pricing) + PRD + ROADMAP\n"
                "\n"
                "$ git log --oneline | wc -l          # всего коммитов\n"
                "111\n"
                "$ ls docs/process/tasks/ TASK-hermes-2[2-6].md | wc -l   # задачи тимлиду\n"
                "26",
                "История репозитория — начало и итог"),
             "От идеи до кабинета: первый коммит 16.11 17:23 → сдача"),
        ],
        "5. Вход и защита данных": [
            (_safe(SECRETS_PLATE, "Аудит секретов (команда и конфиг)"),
             "Защита: ключи только через окружение, история чиста"),
            (_frag(ROOT / "COST.md", "COST.md — правило учёта",
                            needle="Правило (PO R1)", before=0, after=7),
             "Полный учёт стоимости, включая потерянные и отвергнутые прогоны"),
        ],
        "6. Ручные этапы (что делал только человек)": [
            (_frag(ROOT / "STATE.md", "STATE.md — resume-карта прогона",
                            needle="## objective", before=0, after=8),
             "Состояние задачи: продолжение после перерыва новым чатом"),
        ],
    }

    for chunk in sections[1:]:
        title = chunk.splitlines()[0].strip()
        render_text(doc, "## " + chunk)
        for plate, caption in after.get(title, []):
            if plate is not None:
                doc.plate(plate, caption)

    doc.h1("Проверяемость")
    doc.text("Все числа и плашки этого документа воспроизводятся командами "
             "из README §1.1 и регламента харнесса; живая сверка на 22.11.2026: "
             "561 тест, cost_report — $60.02, git — 111 коммитов. "
             "Протоколы экспериментов — docs/research/measurements.md; "
             "манифесты прогонов — eval/runs/.")
    # Doc.save() пишет в OUT основного сборщика — сохраняем явно своим путём
    doc.pages.append(doc.page)
    doc.pages[0].save(OUT, save_all=True, append_images=doc.pages[1:],
                      resolution=150.0)
    print(f"OK: {OUT} ({len(doc.pages)} страниц, {OUT.stat().st_size // 1024} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
