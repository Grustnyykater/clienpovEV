#!/usr/bin/env bash
# Copy Olist CSVs from an unzipped Kaggle archive into ./data
# Usage: bash scripts/copy_data.sh [path/to/archive]   (default: ~/Downloads/archive)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$HOME/Downloads/archive}"
DEST="$ROOT/data"
mkdir -p "$DEST"
cp -v "$SRC"/olist_*.csv "$SRC"/product_category_name_translation.csv "$DEST/"
echo "Data ready in $DEST"
