#!/usr/bin/env python3
"""council_diversity.py — разнообразие набора вариантов (proxy-метрика).

Embeddings-модели в провайдере нет (проверено 2026-11-16: /v1/models не
содержит embedding-модели, /v1/embeddings → quota_exceeded), поэтому
семантическая дистанция считается ЛЕКСИЧЕСКИМ прокси: TF-IDF по словам
вариантов + косинусная близость. Это proxy, не embeddings — пометка
обязательна в отчётах (правило R3 PRD §17: всё, что не полный бенчмарк,
помечать «proxy»).

Что делает: разбирает файл с секциями «### Вариант …» (как options.md или
synthesis.md Консилиума), считает попарные косинусные дистанции между
вариантами и печатает матрицу + среднюю дистанцию + число вариантов.

Коды возврата: 0 — ок; 1 — ошибка использования; 2 — нарушение (напр.,
файл не UTF-8 или вариантов меньше двух).

Использование:
  python3 scripts/council_diversity.py project/options.md
  python3 scripts/council_diversity.py project/council/run-*/synthesis.md
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_VIOLATION = 2

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")
VARIANT_RE = re.compile(r"^###\s+(Вариант\s+[^\n]+)$", re.M)
STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще",
    "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли",
    "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь",
    "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей",
    "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя",
    "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже",
    "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти",
    "мой", "тем", "чтобы", "нее", "были", "куда", "зачем", "всех", "никогда",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="council_diversity.py",
        description="Proxy-разнообразие набора вариантов (TF-IDF, косинус).",
    )
    parser.add_argument("file", nargs="?", help="markdown-файл с секциями «### Вариант …»")
    args = parser.parse_args(argv)
    if not args.file:
        print(
            "использование: council_diversity.py <файл с секциями «### Вариант …»",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    return args


def variant_sections(text: str) -> list[tuple[str, str]]:
    """[(заголовок, тело)] по секциям «### Вариант …»."""
    matches = list(VARIANT_RE.finditer(text))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((match.group(1).strip(), text[start:end]))
    return sections


def tokens(text: str) -> list[str]:
    words = WORD_RE.findall(text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def cosine_distance(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 1.0
    dot = sum(a[k] * b.get(k, 0.0) for k in a)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    path = Path(args.file)
    if not path.is_file():
        print(f"файл не найден: {path}", file=sys.stderr)
        return EXIT_USAGE
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"файл не в UTF-8: {path}", file=sys.stderr)
        return EXIT_VIOLATION

    sections = variant_sections(text)
    if len(sections) < 2:
        print(
            f"нарушение: найдено вариантов {len(sections)} (<2) — сравнивать нечего",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    # TF-IDF: вариант = документ; IDF по вариантам.
    docs = [tokens(body) for _, body in sections]
    n_docs = len(docs)
    df: dict[str, int] = {}
    for doc in docs:
        for word in set(doc):
            df[word] = df.get(word, 0) + 1
    vectors: list[dict[str, float]] = []
    for doc in docs:
        counts: dict[str, int] = {}
        for word in doc:
            counts[word] = counts.get(word, 0) + 1
        total = sum(counts.values()) or 1
        vectors.append(
            {
                word: (count / total) * math.log((n_docs + 1) / (df[word] + 1))
                for word, count in counts.items()
            }
        )

    print(f"proxy-diversity (TF-IDF, не embeddings): {path}")
    print(f"вариантов: {n_docs}")
    labels = [title.split(":")[0].strip()[:28] for title, _ in sections]
    distances: list[float] = []
    print("матрица попарных дистанций (1.0 = полностью разные):")
    for i in range(n_docs):
        row = []
        for j in range(n_docs):
            if i == j:
                row.append("  —  ")
                continue
            distance = cosine_distance(vectors[i], vectors[j])
            distances.append(distance)
            row.append(f"{distance:5.3f}")
        print(f"  {labels[i]:30s} " + " ".join(row))
    mean = sum(distances) / len(distances)
    print(f"средняя попарная дистанция: {mean:.3f} (по {len(distances)} парам)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
