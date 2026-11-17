#!/usr/bin/env python3
"""skill_guard.py — предохранитель «самоулучшение только по замеру»
(TASK-hermes-14 §2, BRIEF п.26).

Отличие от Hermes намеренное и названо: в Hermes мутация скилла
допускается всегда (ledger — «TELEMETRY, NOT A GATE»), защита идёт от
других угроз (pinned/locked/read-before-write). Для strategy-agent
главный измеренный риск — ДРУГОЙ: агент правит свои инструкции «по
ощущению», и качество дрейфует без следа (четыре отрицательных измерения
улучшательных гипотез critic-loop, measurements.md §22.4/§22.7/§23.6 —
все правки «на глаз» не дали прироста). Поэтому здесь гейт:

    патч навыка допускается ТОЛЬКО с evidence — ссылкой на артефакт
    ЗАМЕРА (файл в репозитории, непустой), либо на секцию measurements.md.

Fail-closed: при сомнении — отказ. Отказ назвает причину.

Контракт:
    validate_patch(skill_dir, rel_file, old, new) -> (ok, reason)
    validate_evidence(evidence, repo_root) -> (ok, reason)
    guard_patch(skill, rel_file, old, new, evidence, repo_root) -> (ok, reason)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

# Слова-маркеры вердикта в артефакте-основании: файл должен выглядеть
# как результат замера, а не как произвольная заметка.
VERDICT_HINTS = (
    "вердикт", "verdict", "замер", "измерен", "measurement", "предрегистрац",
    "итог:", "mdd", "δ", "sd(", "p=", "$",
)

# Формы evidence, которые принимаются:
#   1) путь к файлу репозитория — в бэктиках, голый путь со «/» или голое
#      имя файла (README.md, measurements.md);
#   2) ссылка на секцию measurements.md («measurements.md §28», «§28»).
BACKTICK_PATH_RE = re.compile(r"`([^`]+)`")
BARE_PATH_RE = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:md|py|json|csv|txt))(?![\w/])")
SECTION_RE = re.compile(r"(measurements\.md\s*)?§\s*(\d+(?:\.\d+)?(?:-[А-Яа-яA-Za-z]+)?)", re.IGNORECASE)


def _resolves_to_existing(candidate: str, repo_root: Path) -> Optional[Path]:
    """Путь кандидата относительно корня репо; None если файла нет."""
    candidate = candidate.strip()
    if not candidate or candidate.startswith(("http://", "https://")):
        return None
    # Из пути вида product/agent/... или ./product/... или абсолютного
    # внутри репо — берём хвост относительно корня.
    pure = candidate[2:] if candidate.startswith("./") else candidate
    for probe in (repo_root / pure, repo_root / "docs/research" / Path(pure).name):
        try:
            if probe.is_file() and probe.stat().st_size > 0:
                return probe
        except OSError:
            continue
    return None


def _looks_like_measurement(path: Path) -> bool:
    """Артефакт-основание должен нести вердикт/итог замера, а быть просто
    непустым файлом. Порог намеренно мягкий: гейт ловит «патч по
    ощущению», а не оценивает качество замера — это дело критиков."""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4000].lower()
    except OSError:
        return False
    return any(hint.lower() in head for hint in VERDICT_HINTS)


def validate_patch(skill_dir: Path, rel_file: str, old: str, new: str
                   ) -> Tuple[bool, str]:
    """Патч применяем единственно и однозначно (урок integrity-гейта:
    неоднозначный old_string — источник «плавающих» правок)."""
    if not rel_file:
        return False, "не указан файл навыка"
    if old == new:
        return False, "old_string и new_string совпадают — патч ничего не меняет"
    if not old:
        return False, "пустой old_string — только write_file, не patch"
    target = skill_dir / rel_file
    if not target.is_file():
        return False, f"файл не найден: {target}"
    text = target.read_text(encoding="utf-8-sig", errors="replace")
    count = text.count(old)
    if count == 0:
        return False, "old_string не найден в файле (возможно, файл изменился)"
    if count > 1:
        return False, f"old_string встречается {count} раз — уточни патч (единичность)"
    return True, "ok"


def validate_evidence(evidence: str, repo_root: Path) -> Tuple[bool, str]:
    """Evidence обязателен и должен резолвиться в артефакт замера.

    Пустой evidence, ссылка на несуществующий файл или файл без следа
    замера — отказ. Fail-closed по построению: перебираем все кандидаты,
    допустим любой резолвящийся; отказ только если НИ ОДИН не подошёл.

    §-указание — точная ссылка: если в evidence есть «measurements.md
    §N» (или «§N») и такой секции нет, отказ БЕЗ отката к резолву
    всего файла: молчаливый проброс битой ссылки через «файл-то есть»
    прячет опечатку в основании (регрессия, найденная живой пробой
    2026-11-17: «measurements.md §99» проходил по файлу).
    """
    if not evidence or not evidence.strip():
        return False, ("evidence обязателен: самоулучшение только по замеру "
                       "(BRIEF п.26). Дай путь к артефакту замера или «measurements.md §N»")
    reasons: list[str] = []
    # Кандидаты-файлы (бэктики и голые пути) — резолвим ДО разбора §:
    # если evidence называет файл, §N в той же строке относится к НЕМУ.
    named: list[tuple[str, Path]] = []
    for candidate in BACKTICK_PATH_RE.findall(evidence) + BARE_PATH_RE.findall(evidence):
        resolved = _resolves_to_existing(candidate, repo_root)
        if resolved is not None:
            named.append((candidate, resolved))
    section_refs = SECTION_RE.findall(evidence)
    if section_refs:
        # §-указания: точная ссылка, битая — отказ (не fallback на файл).
        # Названный файл, который НЕ measurements.md: секция принадлежит
        # ему. Иначе evidence «<другой-файл>.md §N» молча резолвился бы
        # в measurements.md §N — чужой документ (дефект найден живой
        # пробой TASK-hermes-15: «…decomposition.md §13» проходил как
        # measurements.md §13 — раздел про живую ре-проверку ссылок).
        foreign = [(c, p) for c, p in named if p.name != "measurements.md"]
        if foreign:
            for candidate, path in foreign:
                body = path.read_text(encoding="utf-8", errors="replace")
                missing = [s for _prefix, s in section_refs if f"§{s}" not in body]
                if missing:
                    reasons.append(f"{candidate}: секция "
                                   + "/".join(f"§{m}" for m in missing)
                                   + " не найдена в этом файле (проброс на "
                                     "measurements.md запрещён)")
                    continue
                if not _looks_like_measurement(path):
                    reasons.append(f"{candidate}: файл есть, но не похож на артефакт "
                                   "замера (нет вердикта/итога/Δ/MDD)")
                    continue
                return True, (str(path.relative_to(repo_root)) + " "
                              + " ".join(f"§{s}" for _prefix, s in section_refs))
            return False, ("evidence не резолвится в артефакт замера: "
                           + "; ".join(reasons))
        measurements = repo_root / "docs" / "research" / "measurements.md"
        body = (measurements.read_text(encoding="utf-8", errors="replace")
                if measurements.is_file() else "")
        for _prefix, section in section_refs:
            if f"§{section}" in body:
                return True, f"measurements.md §{section}"
            reasons.append(f"§{section}: секция не найдена в measurements.md")
        return False, ("evidence не резолвится в артефакт замера: "
                       + "; ".join(reasons))
    # 2) Пути к файлам (бэктики и голые).
    candidates = BACKTICK_PATH_RE.findall(evidence) + BARE_PATH_RE.findall(evidence)
    for candidate in candidates:
        resolved = _resolves_to_existing(candidate, repo_root)
        if resolved is None:
            reasons.append(f"{candidate}: файл не найден или пуст")
            continue
        if not _looks_like_measurement(resolved):
            reasons.append(f"{candidate}: файл есть, но не похож на артефакт замера "
                           "(нет вердикта/итога/Δ/MDD) — гейт ловит «патч по ощущению»")
            continue
        return True, str(resolved.relative_to(repo_root))
    detail = "; ".join(reasons) if reasons else "в evidence нет пути к файлу или §N"
    return False, f"evidence не резолвится в артефакт замера: {detail}"


def guard_patch(skill: str, rel_file: str, old: str, new: str, evidence: str,
                repo_root: Optional[Path] = None) -> Tuple[bool, str]:
    """Полный гейт: сначала evidence (зачем), затем патч (что именно)."""
    root = repo_root or Path(__file__).resolve().parents[2]
    skill_dir = root / "knowledge" / "skills" / skill
    if not skill_dir.is_dir():
        return False, f"навык не найден: {skill_dir}"
    ok, ev_reason = validate_evidence(evidence, root)
    if not ok:
        return False, ev_reason
    ok, reason = validate_patch(skill_dir, rel_file, old, new)
    if not ok:
        return False, reason
    return True, f"evidence → {ev_reason}"
