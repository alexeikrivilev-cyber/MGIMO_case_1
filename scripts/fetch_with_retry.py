#!/usr/bin/env python3
"""fetch_with_retry.py — добыча источника с retry/backoff и деградацией.

Поведение по PRD §12 («поиск/фетч упал»): retry с backoff → деградация:
работа с локальными материалами + явная запись пробела; ссылка
помечается «не проверена». Скрипт делает первый шаг этого конвейера
детерминированным: либо сохраняет тело ответа в файл, либо печатает
готовую запись-пробел (gap-record) для журнала доказательств.

Контракт CLI:
    python3 scripts/fetch_with_retry.py <url> <out-file> [--attempts N]
        [--backoff-base SEC] [--timeout SEC] [--min-bytes N]

Коды возврата:
    0 — источник сохранён (файл создан, в заголовке — URL и дата);
    1 — ошибка использования (нет аргументов, URL не http(s));
    2 — все попытки упали: на stdout напечатана запись-пробел
        (gap-record) для ручной вставки в evidence; файл не создан;
    3 — сработала fault-injection (STRATEGY_FAULT_INJECT=net):
        первые попытки принудительно падают — шов для тестов
        устойчивости; поведение как у кода 2 при исчерпании попыток.

Переменная окружения STRATEGY_FAULT_INJECT=net заставляет первые
(attempts-1) попытку падать с сетевой ошибкой — используется
fault-injection прогонами (measurements.md §3) и тестами.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NETWORK = 2
EXIT_FAULT_INJECTED = 3

USER_AGENT = "strategy-agent-fetch/1.0 (+https://example.invalid; contact: repo)"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fetch_with_retry.py",
        description="Fetch URL с retry/backoff; при неудаче — запись-пробел на stdout.",
    )
    parser.add_argument("url", nargs="?", help="http(s) URL источника")
    parser.add_argument("out", nargs="?", help="путь файла для сохранения тела")
    parser.add_argument("--attempts", type=int, default=3, help="попыток (по умолчанию 3)")
    parser.add_argument(
        "--backoff-base", type=float, default=1.0, help="база backoff в секундах"
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="таймаут попытки, с")
    parser.add_argument("--min-bytes", type=int, default=1, help="минимум байт в ответе")
    args = parser.parse_args(argv)
    if not args.url or not args.out:
        print(
            "использование: fetch_with_retry.py <url> <out-file> [--attempts N] "
            "[--backoff-base SEC] [--timeout SEC] [--min-bytes N]",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    if not args.url.startswith(("http://", "https://")):
        print(f"URL должен быть http(s): {args.url}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    if args.attempts < 1:
        print("--attempts должен быть ≥ 1", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    return args


def gap_record(url: str, reason: str) -> str:
    """Готовая запись-пробел для журнала доказательств (деградация)."""
    today = date.today().isoformat()
    return (
        f"# gap — источник недоступен: {url}\n\n"
        f"- URL: {url}\n"
        f"- Дата попытки: {today}\n"
        f"- Причина: {reason}\n"
        f"- Статус: НЕ ПРОВЕРЕН — ссылка помечается «не проверена»\n"
        f"- Что делать: работать с локальными материалами "
        f"(`project/materials/`) и явно named gap; при появлении доступа — "
        f"повторить fetch и заменить запись.\n"
    )


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    fault_inject = os.environ.get("STRATEGY_FAULT_INJECT") == "net"

    last_reason = "не attempted"
    for attempt in range(1, args.attempts + 1):
        forced = fault_inject and attempt < args.attempts
        try:
            if forced:
                raise urllib.error.URLError("fault-injection: сеть отключена принудительно")
            request = urllib.request.Request(args.url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                body = response.read()
                status = getattr(response, "status", 200)
            if len(body) < args.min_bytes:
                raise urllib.error.URLError(
                    f"ответ меньше {args.min_bytes} байт ({len(body)})"
                )
            header = (
                f"<!-- источник: {args.url}; дата доступа: {date.today().isoformat()}; "
                f"HTTP {status}; attempts: {attempt}/{args.attempts} -->\n"
            )
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(header.encode("utf-8") + body)
            print(f"ok: сохранено {len(body)} байт в {out_path} (попытка {attempt})")
            return EXIT_OK
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_reason = f"{type(exc).__name__}: {exc}"
            print(
                f"попытка {attempt}/{args.attempts} упала: {last_reason}",
                file=sys.stderr,
            )
            if attempt < args.attempts:
                delay = args.backoff_base * (2 ** (attempt - 1))
                delay += random.uniform(0, args.backoff_base)  # jitter
                print(f"backoff: {delay:.2f}s", file=sys.stderr)
                time.sleep(delay)

    print(gap_record(args.url, last_reason))
    if fault_inject:
        print(
            "fault-injection: путь продолжен в режиме деградации "
            "(локальные материалы + явный пробел)",
            file=sys.stderr,
        )
        return EXIT_FAULT_INJECTED
    return EXIT_NETWORK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
