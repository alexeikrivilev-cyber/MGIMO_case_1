#!/usr/bin/env python3
"""arg_chunk.py — защита от лимита exec на один аргумент.

Linux ограничивает ОДИН argv-аргумент 128 КБ (MAX_ARG_STRLEN). Промпт
сессии (бриф + выходы линз, или артефакт + рубрика) может превысить
этот лимит — процесс тогда падает с OSError E2BIG, что в фоне выглядит
как «тихое убийство» раннера. Поэтому промпт режется по границам
UTF-8 на части и передаётся несколькими позиционными аргументами
`opencode run` (склейка message через пробел — проверено).

Источник урока: прогон council-full на held-out (О4), 133 КБ одним argv.
"""

from __future__ import annotations

# Лимит части: чуть ниже системного 128 КБ — запас на служебные байты.
ARG_LIMIT_BYTES = 120_000


def chunk_prompt(prompt: str, limit_bytes: int = ARG_LIMIT_BYTES) -> list[str]:
    """Промпт → части, каждая ≤ limit_bytes байт и валидный UTF-8.

    Граница реза никогда не рассекает многобайтовый символ (откат до
    lead-byte). Промпт в пределах лимита возвращается как есть.
    """
    data = prompt.encode("utf-8")
    if len(data) <= limit_bytes:
        return [prompt]
    chunks: list[bytes] = []
    start = 0
    while start < len(data):
        end = min(start + limit_bytes, len(data))
        if end < len(data):
            while end > start and (data[end] & 0xC0) == 0x80:
                end -= 1  # откат из середины многобайтового символа
        chunks.append(data[start:end])
        start = end
    return [chunk.decode("utf-8") for chunk in chunks]
