#!/usr/bin/env python3
"""build_submission_pdf.py — описание работы (PDF) из docs/submission/*.md.

ТЗ: «Описание работы — PDF или документ по ссылке, со скриншотами:
архитектура; полный перечень моделей/сервисов; ключевые промпты;
доп. возможности; время и расходы, ошибки и помощь человека;
заявленные возможности и ограничения.»

Плашки («скриншоты») — НЕ нарисованы, а отрендерены из РЕАЛЬНЫХ файлов
проекта (лог запуска, фрагменты артефактов, вывод гейтов, STATE, COST):
capture → моноширинная плашка. Ничего не выдумывается.

Запуск: python3 docs/submission/build_submission_pdf.py
Выход:  docs/submission/описание-работы.pdf
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path("/home/alex/projects/strategy-agent")
SUB = ROOT / "docs" / "submission"
FONT_DIR = Path("/home/alex/.openclaw/workspace/media/fonts")
OUT = SUB / "описание-работы.pdf"

W, H = 1240, 1754          # A4 @150dpi
MARGIN = 90
FONT = FONT_DIR / "PTSans-Regular.ttf"
FONT_B = FONT_DIR / "PTSans-Bold.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

INK = (28, 28, 32)
ACCENT = (16, 84, 160)
MUTED = (110, 110, 120)
PLATE_BG = (24, 26, 30)
PLATE_FG = (226, 230, 236)
PLATE_ACCENT = (120, 200, 255)


def f(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_B if bold else FONT), size)


def mono(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MONO, size)


# ---------- минимальный markdown ----------

def inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
    return text


def wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


# ---------- плашки из реальных файлов ----------

def plate_from_file(path: Path, title: str, max_lines: int = 22) -> Image.Image | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    raw = [ln.rstrip()[:110] for ln in raw if ln.strip()]
    if len(raw) > max_lines:
        raw = raw[: max_lines - 1] + [f"… (+{len(raw) - max_lines + 1} строк, полный файл в репозитории)"]
    if not raw:
        return None
    mf = mono(19)
    lh = 27
    img = Image.new("RGB", (W - 2 * MARGIN, 44 + lh * len(raw) + 20), PLATE_BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width, 34], fill=(36, 40, 48))
    d.text((14, 8), title, font=mono(17), fill=PLATE_ACCENT)
    for i, ln in enumerate(raw):
        d.text((14, 44 + i * lh), ln, font=mf, fill=PLATE_FG)
    return img


def plate_from_text(text: str, title: str, max_lines: int = 20) -> Image.Image:
    raw = [ln.rstrip()[:110] for ln in text.splitlines() if ln.strip()][:max_lines]
    mf = mono(19)
    lh = 27
    img = Image.new("RGB", (W - 2 * MARGIN, 44 + lh * len(raw) + 20), PLATE_BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width, 34], fill=(36, 40, 48))
    d.text((14, 8), title, font=mono(17), fill=PLATE_ACCENT)
    for i, ln in enumerate(raw):
        d.text((14, 44 + i * lh), ln, font=mf, fill=PLATE_FG)
    return img


def fragment_plate(path: Path, title: str, needle: str | None = None,
                   before: int = 3, after: int = 12) -> Image.Image | None:
    """Плашка-фрагмент артефакта: строки вокруг needle (реальный файл)."""
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = 0
    if needle:
        for i, ln in enumerate(lines):
            if needle.lower() in ln.lower():
                start = max(0, i - before)
                break
    chunk = [ln.rstrip()[:110] for ln in lines[start:start + after]][:14]
    if not chunk:
        return None
    return plate_from_text("\n".join(chunk), title)


# ---------- рендер страниц ----------

class Doc:
    def __init__(self) -> None:
        self.pages: list[Image.Image] = []
        self.page = self._new_page()
        self.draw = ImageDraw.Draw(self.page)
        self.y = 0

    def _new_page(self) -> Image.Image:
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 10], fill=ACCENT)
        return img

    def _ensure(self, h: int) -> None:
        if self.y + h > H - MARGIN:
            self.pages.append(self.page)
            self.page = self._new_page()
            self.draw = ImageDraw.Draw(self.page)
            self.y = MARGIN

    def text(self, s: str, size: int = 24, bold: bool = False,
             color=INK, gap: int = 12, indent: int = 0) -> None:
        font = f(size, bold)
        for ln in wrap(self.draw, inline(s), font, W - 2 * MARGIN - indent):
            self._ensure(size + 8)
            self.draw.text((MARGIN + indent, self.y), ln, font=font, fill=color)
            self.y += size + 8
        self.y += gap

    def h1(self, s: str) -> None:
        self._ensure(120)
        self.y += 26
        self.text(s, size=38, bold=True, color=ACCENT, gap=6)
        self.draw.line([MARGIN, self.y, W - MARGIN, self.y], fill=(210, 214, 222), width=2)
        self.y += 26

    def h2(self, s: str) -> None:
        self.y += 14
        self.text(s, size=28, bold=True, gap=4)

    def bullet(self, s: str) -> None:
        self.text("•  " + s, size=22, indent=26, gap=6)

    def code(self, block: str) -> None:
        lines = [ln.rstrip()[:110] for ln in block.splitlines() if ln.strip()][:26]
        if not lines:
            return
        mf = mono(18)
        lh = 26
        self._ensure(30 + lh * len(lines))
        y0 = self.y
        self.draw.rectangle([MARGIN - 10, y0, W - MARGIN + 10, y0 + 30 + lh * len(lines)],
                            fill=(245, 246, 249), outline=(214, 218, 226))
        for i, ln in enumerate(lines):
            self.draw.text((MARGIN, y0 + 14 + i * lh), ln, font=mf, fill=(40, 44, 52))
        self.y = y0 + 30 + lh * len(lines) + 18

    def plate(self, img: Image.Image | None, caption: str) -> None:
        if img is None:
            return
        if img.width > W - 2 * MARGIN:
            img = img.resize((W - 2 * MARGIN, int(img.height * (W - 2 * MARGIN) / img.width)))
        self._ensure(img.height + 60)
        self.page.paste(img, (MARGIN, self.y))
        self.y += img.height + 10
        self.text(caption, size=18, color=MUTED, gap=22)

    def save(self) -> None:
        self.pages.append(self.page)
        self.pages[0].save(OUT, save_all=True, append_images=self.pages[1:],
                           resolution=150.0)


# ---------- сборка ----------

SECTIONS = [
    ("1-architecture.md", "1. Архитектура агента"),
    ("2-models-services.md", "2. Модели, сервисы и инструменты"),
    ("3-key-prompts.md", "3. Ключевые промпты и инструкции"),
    ("4-extra-features.md", "4. Возможности дополнительного уровня"),
    ("5-time-costs-errors.md", "5. Время, расходы, ошибки и помощь человека"),
    ("6-capabilities-limitations.md", "6. Заявленные возможности и ограничения"),
]

# Плашки: реальные файлы проекта (capture), по одной-две на раздел
PLATES: dict[str, list[tuple[str, object]]] = {
    "1-architecture.md": [
        ("Реальный прогон полного пути (лог запуска): гейты падают — ревизия — зелёные",
         lambda: plate_from_file(ROOT / "eval/runs/t18-case-launch.log",
                                 "eval/runs/t18-case-launch.log", 14)),
        ("Состояние задачи — resume-карта (продолжение после перерыва)",
         lambda: fragment_plate(ROOT / "STATE.md", "STATE.md (фрагмент)",
                                needle="Resume = новый чат", before=1, after=12)),
    ],
    "2-models-services.md": [
        ("Учёт стоимости по прогонам (COST.md, фрагмент)",
         lambda: fragment_plate(ROOT / "COST.md", "COST.md (фрагмент)",
                                needle="О4:", before=2, after=12)),
    ],
    "3-key-prompts.md": [
        ("Инструкция агента — AGENTS.md (фрагмент рабочего процесса)",
         lambda: fragment_plate(ROOT / "AGENTS.md", "AGENTS.md (фрагмент)",
                                needle="Workflow", before=2, after=14)),
    ],
    "4-extra-features.md": [
        ("Навык агента — knowledge/skills/critic/SKILL.md (фрагмент)",
         lambda: fragment_plate(ROOT / "knowledge/skills/critic/SKILL.md",
                                "knowledge/skills/critic/SKILL.md (фрагмент)",
                                needle="изоляция", before=2, after=12)),
    ],
    "5-time-costs-errors.md": [
        ("Журнал работы — LOG.md (фрагмент: раунды, находки, правки)",
         lambda: fragment_plate(ROOT / "LOG.md", "LOG.md (фрагмент)",
                                needle="task 19", before=1, after=13)),
        ("Демо-проект: манифест полного пути (фрагмент)",
         lambda: fragment_plate(ROOT / "eval/runs/t18-case/manifest.md",
                                "eval/runs/t18-case/manifest.md (фрагмент)",
                                needle="раунд 1", before=1, after=13)),
    ],
    "6-capabilities-limitations.md": [
        ("Замеры — measurements.md (фрагмент: вердикты и MDD)",
         lambda: fragment_plate(ROOT / "docs/research/measurements.md",
                                "docs/research/measurements.md (фрагмент)",
                                needle="MDD", before=2, after=12)),
    ],
}


def render_md(doc: Doc, md_path: Path) -> None:
    in_code = False
    buf: list[str] = []
    for raw in md_path.read_text(encoding="utf-8").splitlines():
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


def main() -> int:
    doc = Doc()
    doc.y = 260
    doc.text("«Стратег Фабрики продуктов»", size=52, bold=True, color=ACCENT, gap=10)
    doc.text("ИИ-агент — помощник руководителя цифрового продукта", size=30, gap=6)
    doc.text("Описание работы (по требованиям ТЗ)", size=24, color=MUTED, gap=40)
    doc.plate(plate_from_text(
        "Запрос руководителя продукта → артефакты → стратегии → план проверки\n"
        "Репозиторий: AGENTS.md + knowledge/ + scripts/ + project/\n"
        "Среда: OpenCode CLI (также Cursor / Claude Code / Codex / GigaCode)\n"
        "Модель сессий: stepfun/step-5-preview\n"
        "Полный путь демо-проекта: eval/runs/t18-case (гейты зелёные)",
        "Кратко"), "Общее описание решения")

    readme = SUB / "README.md"
    if readme.is_file():
        doc.h1("О документе")
        render_md(doc, readme)

    for fname, title in SECTIONS:
        doc.h1(title)
        render_md(doc, SUB / fname)
        for caption, maker in PLATES.get(fname, []):
            doc.plate(maker(), caption)

    doc.h1("Чек-лист требований ТЗ")
    render_md(doc, SUB / "tz-checklist.md")

    doc.save()
    print(f"OK: {OUT} ({len(doc.pages)} страниц, {OUT.stat().st_size // 1024} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
