#!/usr/bin/env bash
# fetch_data.sh — качает context-файлы и dev-задачи DABstep (вне git).
# Источник: датасет adyen/DABstep (HuggingFace, CC-BY-4.0).
#   context: https://huggingface.co/datasets/adyen/DABstep/tree/main/data/context
#   задачи:  https://huggingface.co/datasets/adyen/DABstep (config=tasks, split=dev)
# Дата доступа: 2026-11-16.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DATA="$HERE/data"
CONTEXT="$DATA/context"
mkdir -p "$CONTEXT"

BASE="https://huggingface.co/datasets/adyen/DABstep/resolve/main/data/context"
for f in payments.csv payments-readme.md fees.json merchant_data.json \
         merchant_category_codes.csv acquirer_countries.csv manual.md; do
  if [ ! -f "$CONTEXT/$f" ]; then
    echo "качаю $f ..."
    curl -sL --fail -o "$CONTEXT/$f" "$BASE/$f"
  fi
done

if [ ! -f "$DATA/tasks-dev.json" ]; then
  echo "качаю dev-задачи (10, с эталонными ответами) ..."
  curl -s "https://datasets-server.huggingface.co/rows?dataset=adyen%2FDABstep&config=tasks&split=dev&offset=0&length=10" \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
rows = [r['row'] for r in d['rows']]
json.dump(rows, open('$DATA/tasks-dev.json','w'), ensure_ascii=False, indent=1)
print(f'задач: {len(rows)}')"
fi

echo "готово: $DATA"
