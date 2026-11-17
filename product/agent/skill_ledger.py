#!/usr/bin/env python3
"""skill_ledger.py — журнал мутаций навыков + откат (TASK-hermes-14 §2).

Адаптация механики learned-скиллов Hermes под strategy-agent. Источник
(изучение 2026-11-17, ~/.hermes/hermes-agent/tools/skill_ledger.py):
«Per-mutation skill audit ledger + single-edit rollback. Every skill
mutation (any actor) appends one JSONL entry … with before/after file
manifests whose contents are stored content-addressed (sha256-deduped) …
TELEMETRY, NOT A GATE: every public write path swallows and logs — except
``rollback_entry``, which FAILS CLOSED when its safety capture fails.»

Что взято как есть:
- JSONL-журнал (дуrable, greppable, переживает сбросы состояния) вместо БД;
- до/после-манифесты {path, sha256} с блобами, дедуплицированными по sha256;
- актор мутации (agent/po/user) + evidence в записи;
- откат FAILS CLOSED: если блоб перед-состояния потерян — откат отказает,
  а не «откатит частично».

Что добавлено под продукт (отличие от Hermes):
- предохранитель «только по замеру» живёт НЕ здесь, а в skill_guard.py:
  ledger пишет любую допущенную мутацию, решение «можно ли» — до него;
- корень журнала — knowledge/skills/.evolution/ (журнал едет вместе с
  навыками в git, откат возможен на любом клоне).

Контракт:
    ledger_path(), blobs_dir(), snapshot_skill(skill_dir) -> list[dict],
    append_entry(entry: dict) -> dict, find_entry(entry_id) -> dict|None,
    rollback_entry(entry_id, actor, reason) -> dict  (raises RollbackError),
    verify() -> list[str]  (список проблем; пусто = целостность на месте).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
EVOLUTION_DIRNAME = ".evolution"

# Локальные артефакты, которые никогда не попадают в снимок (урок Hermes:
# stray venv превращает снимок в гигабайты блобов).
TRANSIENT_DIRS = frozenset({
    ".venv", "venv", "env", ".env", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git",
})

VALID_ACTORS = ("agent", "po", "user")


class RollbackError(RuntimeError):
    """Откат невозможен fail-closed: блоб перед-состояния потерян."""


def skills_root(root: Optional[Path] = None) -> Path:
    """Корень навыков: knowledge/skills внутри корня репозитория."""
    return (root or REPO_ROOT) / "knowledge" / "skills"


def evolution_dir(root: Optional[Path] = None) -> Path:
    return skills_root(root) / EVOLUTION_DIRNAME


def ledger_path(root: Optional[Path] = None) -> Path:
    return evolution_dir(root) / "ledger.jsonl"


def blobs_dir(root: Optional[Path] = None) -> Path:
    return evolution_dir(root) / "blobs"


@contextmanager
def _ledger_lock(root: Optional[Path] = None) -> Iterator[None]:
    """Эксклюзивная межпроцессная блокировка журнала (идиома Hermes:
    <skills>/.locks/ledger.lock; no-op там, где fcntl нет)."""
    lock_path = evolution_dir(root) / ".locks" / "ledger.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except OSError:
            yield
            return
        yield
    finally:
        fh.close()


def _store_blob(data: bytes, root: Optional[Path] = None) -> str:
    """Контент-адресуемое хранилище: имя файла = sha256 содержимого."""
    digest = hashlib.sha256(data).hexdigest()
    dest = blobs_dir(root) / digest
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f".tmp-{uuid.uuid4().hex[:8]}-{digest}")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    return digest


def read_blob(sha256: str, root: Optional[Path] = None) -> Optional[bytes]:
    if not sha256 or not all(c in "0123456789abcdef" for c in sha256):
        return None
    path = blobs_dir(root) / sha256
    try:
        return path.read_bytes() if path.is_file() else None
    except OSError:
        return None


def snapshot_skill(skill_dir: Path, root: Optional[Path] = None) -> list[dict]:
    """{path, sha256} для каждого файла навыка; блобы сохранены.

    path — POSIX-путь относительно корня навыков (knowledge/skills),
    чтобы запись не зависела от абсолютного расположения репозитория.
    Транзитные каталоги исключены на любой глубине.
    """
    skills_root_ = skills_root(root)
    out: list[dict] = []
    if not skill_dir.is_dir():
        return out
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(skill_dir).parts
        if any(part in TRANSIENT_DIRS for part in rel_parts[:-1]):
            continue
        if rel_parts and rel_parts[0] == EVOLUTION_DIRNAME:
            continue
        data = path.read_bytes()
        out.append({
            "path": path.relative_to(skills_root_).as_posix(),
            "sha256": _store_blob(data, root),
        })
    return out


def _new_entry_id(payload: str) -> str:
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def append_entry(entry: dict, root: Optional[Path] = None) -> dict:
    """Дописать запись в журнал. Возвращает запись с присвоенным id/ts."""
    import time
    entry = dict(entry)
    entry.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime()))
    entry.setdefault("id", _new_entry_id(
        f"{entry.get('ts')}|{entry.get('skill')}|{entry.get('action')}|{uuid.uuid4().hex}"))
    if entry.get("actor") not in VALID_ACTORS:
        entry["actor"] = "agent"
    with _ledger_lock(root):
        path = ledger_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def iter_entries(root: Optional[Path] = None) -> Iterator[dict]:
    path = ledger_path(root)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def find_entry(entry_id: str, root: Optional[Path] = None) -> Optional[dict]:
    for entry in iter_entries(root):
        if entry.get("id") == entry_id:
            return entry
    return None


def rollback_entry(entry_id: str, actor: str = "agent", reason: str = "",
                   root: Optional[Path] = None) -> dict:
    """Откат одиночной мутации: восстановить before-состояние записи.

    Fail-closed: если хоть один блоб before потерян — RollbackError,
    файлы не трогаем. Файлы, появившиеся в after и отсутствующие в before
    (добавленные), удаляются. Откат сам становится записью журнала
    (action=rollback, parent=id откатываемой записи).
    """
    skills_root_ = skills_root(root)
    entry = find_entry(entry_id, root)
    if entry is None:
        raise RollbackError(f"запись {entry_id} не найдена в журнале")
    if entry.get("action") == "rollback":
        raise RollbackError(f"запись {entry_id} — уже откат")
    before = entry.get("before") or []
    after = entry.get("after") or []
    # Проверка наличия ВСЕХ блобов до любых изменений (fail-closed).
    for item in before:
        if read_blob(item["sha256"], root) is None:
            raise RollbackError(
                f"блоб {item['sha256']} ({item['path']}) потерян — откат отказан")
    before_paths = {item["path"] for item in before}
    with _ledger_lock(root):
        for item in before:
            data = read_blob(item["sha256"], root)
            assert data is not None
            dest = skills_root_ / item["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        for item in after:
            if item["path"] not in before_paths:
                victim = skills_root_ / item["path"]
                if victim.is_file():
                    victim.unlink()
    return append_entry({
        "action": "rollback", "skill": entry.get("skill"), "actor": actor,
        "evidence": reason or "откат по требованию", "parent": entry_id,
        "before": after, "after": before,
    }, root)


def verify(root: Optional[Path] = None) -> list[str]:
    """Проверка целостности журнала: все блобы на месте, записи читаемы.

    Пустой список = целостность на месте. Это проверочная механика
    минимума (аналог «automated checks» из retro-навыка mattpocock):
    потерянный блоб = откат стал невозможен, и это должно быть видно
    ДО попытки отката.
    """
    problems: list[str] = []
    entries = list(iter_entries(root))
    seen_ids: set[str] = set()
    for entry in entries:
        eid = entry.get("id")
        if not eid:
            problems.append(f"запись без id: {json.dumps(entry, ensure_ascii=False)[:120]}")
            continue
        if eid in seen_ids:
            problems.append(f"дубликат id записи: {eid}")
        seen_ids.add(eid)
        for state in ("before", "after"):
            for item in entry.get(state) or []:
                if read_blob(item.get("sha256", ""), root) is None:
                    problems.append(
                        f"запись {eid}: блоб {item.get('sha256')} ({item.get('path')}) потерян")
        parent = entry.get("parent")
        if parent and parent not in seen_ids and not any(
                e.get("id") == parent for e in entries):
            problems.append(f"запись {eid}: parent {parent} не найден в журнале")
    return problems


def usage_record(skill: str, root: Optional[Path] = None) -> dict:
    """Статистика использования навыка — из журнала, без второго источника."""
    entries = [e for e in iter_entries(root) if e.get("skill") == skill]
    mutations = [e for e in entries if e.get("action") != "rollback"]
    rollbacks = [e for e in entries if e.get("action") == "rollback"]
    return {
        "skill": skill,
        "patch_count": len(mutations),
        "rollback_count": len(rollbacks),
        "patch_generation": len(mutations),
        "last_mutated_at": mutations[-1]["ts"] if mutations else None,
        "evidence": [e.get("evidence") for e in mutations if e.get("evidence")],
    }
