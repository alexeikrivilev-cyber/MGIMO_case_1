#!/usr/bin/env python3
"""merge_l3_retry.py — сшивание доборной цепочки L3 в серию (TASK-hermes-11).

Цепочка 1 потеряла сбой провайдера (HTTP 502 на ревизии round 1) —
прогон измерял незавершённый протокол. Правило добора (зафиксировано
ДО добора, не пост-фактум): перегенерируется ОДНА независимая цепочка
тем же промптом (sha совпадает — проверяется), принимается в серию
цепочкой №1 КАК ЕСТЬ, безотносительно к результату; старая цепочка
сохраняется как evidence (как замена run4 → run4b в TASK-hermes-9).

Контракт CLI:
    python3 eval/merge_l3_retry.py --series DIR --retry DIR

Коды возврата: 0 — сшито; 2 — проверки не прошли (sha промпта, файлы).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2

# Файлы цепочки idx=1 (суффикс -1) и их источники в доборном прогоне (idx=0).
CHAIN_FILES = {
    "draft.out": "draft.out",
    "draft.md": "draft.md",
    "round1.md": "round1.md",
    "integrity-round0.json": "integrity-round0.json",
    "checks.md": "checks.md",
    "final.md": "final.md",
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="merge_l3_retry.py",
        description="Сшивание доборной цепочки L3 (индекс 1) в серию k=3.",
    )
    parser.add_argument("--series", required=True, help="каталог руки L3 серии")
    parser.add_argument("--retry", required=True, help="каталог доборного прогона L3")
    args = parser.parse_args(argv)

    series = Path(args.series)
    retry = Path(args.retry)

    series_meta_path = series / "meta.json"
    retry_meta_path = retry / "meta.json"
    if not series_meta_path.is_file() or not retry_meta_path.is_file():
        print("meta.json не найден", file=sys.stderr)
        return EXIT_USAGE

    series_meta = json.loads(series_meta_path.read_text(encoding="utf-8"))
    retry_meta = json.loads(retry_meta_path.read_text(encoding="utf-8"))

    # 1. Промпт обязан быть тем же (иначе это другая рука, не добор).
    if series_meta.get("prompt_sha256_16") != retry_meta.get("prompt_sha256_16"):
        print(
            "sha промпта различается — добор не той рукой: "
            f"{series_meta.get('prompt_sha256_16')} vs {retry_meta.get('prompt_sha256_16')}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    # 2. Файлы цепочки с суффиксом -1.
    for target, source in CHAIN_FILES.items():
        src = retry / source
        if not src.is_file():
            print(f"в доборном прогоне нет {source}", file=sys.stderr)
            return EXIT_USAGE
        (series / f"{Path(target).stem}-1{Path(target).suffix}").write_text(
            src.read_text(encoding="utf-8"), encoding="utf-8"
        )

    # 3. Мета: убрать провальную цепочку 1, вставить доборную с именами -1.
    failed_names = {"draft-1", "revision0-1", "revision1-1"}
    kept = [s for s in series_meta["sessions"] if s["name"] not in failed_names]
    retry_sessions = []
    for s in retry_meta["sessions"]:
        name = s["name"]
        retry_sessions.append({**s, "name": f"{name}-1" if name != "draft" else "draft-1"})
    # порядок: цепочка 0, цепочка 1 (добор), цепочка 2
    chain0 = [s for s in kept if not s["name"].endswith("-2") and s["name"] not in ("draft-2", "revision0-2")]
    chain2 = [s for s in kept if s not in chain0]
    series_meta["sessions"] = chain0 + retry_sessions + chain2
    series_meta["cost_usd_total"] = round(sum(s["cost_usd"] for s in series_meta["sessions"]), 6)
    series_meta["tokens_total"] = {
        field: sum(s["tokens"][field] for s in series_meta["sessions"])
        for field in ("input", "output", "reasoning", "cache_read")
    }
    series_meta["retry_note"] = (
        "цепочка 1 перегенерирована после сбоя провайдера (HTTP 502); "
        "правило добора зафиксировано до добора, цепочка принята как есть"
    )
    series_meta_path.write_text(
        json.dumps(series_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"цепочка 1 сшита: сессий {len(series_meta['sessions'])}, "
        f"итого ${series_meta['cost_usd_total']:.4f}"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
