#!/usr/bin/env python3
"""check_citations.py — резолвимость ссылок в доказательствах (proxy citation accuracy).

Что делает: собирает URL из markdown-файлов (evidence и артефакты),
проверяет каждый запросом HEAD (при 405/501 — GET со stream и
отбросом тела), печатает статус по каждому и итог. Это proxy-метрика
«ссылки живые» — не «ссылка подтверждает утверждение» (содержательная
проверка — за человеком/экспертом).

Контракт CLI:
    python3 scripts/check_citations.py <file.md> [<file.md> ...]
        [--timeout SEC]

Коды возврата:
    0 — все ссылки резолвятся (2xx/3xx);
    1 — ошибка использования (нет файлов/аргументов);
    2 — хотя бы одна ссылка не резолвится (4xx/5xx/сеть).
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_UNRESOLVED = 2

URL_RE = re.compile(r"https?://[^\s)>\]]+")
# Browser-like заголовки: часть сайтов (напр. Kaggle) отдаёт 404 ботам по
# одному UA — нужен полный набор браузерных заголовков, иначе пробник
# принимает живую ссылку за мёртвую (найдено 2026-11-16 на demo-цитатах).
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_citations.py",
        description="Проверка резолвимости URL в доказательствах (proxy).",
    )
    parser.add_argument("files", nargs="*", help="markdown-файлы с URL")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    if not args.files:
        print(
            "использование: check_citations.py <file.md> [<file.md> ...] [--timeout SEC]",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    return args


def probe(url: str, timeout: float) -> tuple[bool, str]:
    """(ок, статус) — HEAD; при 404/405/501 подтверждаем GET (некоторые
    сайты отвечают 404 на HEAD, но 200 на GET — напр. Kaggle)."""
    request = urllib.request.Request(url, method="HEAD", headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return True, f"HTTP {getattr(response, 'status', 200)}"
    except urllib.error.HTTPError as exc:
        if exc.code not in (404, 405, 501):
            return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"сеть: {exc}"
    try:
        request = urllib.request.Request(url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return True, f"HTTP {getattr(response, 'status', 200)}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"сеть: {exc}"


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    seen: dict[str, str] = {}
    for name in args.files:
        path = Path(name)
        if not path.is_file():
            print(f"файл не найден: {path}", file=sys.stderr)
            return EXIT_USAGE
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for url in URL_RE.findall(text):
            seen.setdefault(url, name)

    if not seen:
        print("URL не найдены — проверять нечего")
        return EXIT_OK

    bad: list[str] = []
    for url, source in seen.items():
        ok, status = probe(url, args.timeout)
        mark = "ok " if ok else "НЕ РЕЗОЛВИТСЯ"
        print(f"{mark} {status:24s} {url}  ({source})")
        if not ok:
            bad.append(url)

    print(f"итог: {len(seen) - len(bad)}/{len(seen)} ссылок резолвятся")
    return EXIT_OK if not bad else EXIT_UNRESOLVED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
