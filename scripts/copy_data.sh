#!/usr/bin/env bash
# Copy Olist CSVs from Downloads/archive into ./data
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$HOME/Downloads/archive}"
DEST="$ROOT/data"
mkdir -p "$DEST"
cp -v "$SRC"/olist_*.csv "$DEST/"
cp -v "$SRC"/product_category_name_translation.csv "$DEST/"
echo "Data ready in $DEST"
