"""
Point the Power BI report at this copy of the repo.

Power Query has no relative paths, so the semantic model keeps an absolute
DataFolder parameter. This script rewrites it to <repo>/outputs/.

Usage:  python scripts/configure_powerbi.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPRESSIONS = ROOT / "powerbi" / "OlistDashboard.SemanticModel" / "definition" / "expressions.tmdl"


def _utf8_console() -> None:
    """Windows consoles default to cp1251/cp866 and cannot print "→" or Cyrillic reliably."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    _utf8_console()
    folder = str(ROOT / "outputs") + "\\"
    text = EXPRESSIONS.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r'(expression DataFolder = )"[^"]*"',
        lambda m: f'{m.group(1)}"{folder}"',
        text,
    )
    if n != 1:
        raise SystemExit(f"DataFolder parameter not found in {EXPRESSIONS}")
    EXPRESSIONS.write_text(new_text, encoding="utf-8")
    print(f"DataFolder → {folder}")
    missing = [f for f in ("powerbi_orders.csv", "powerbi_order_items.csv", "retention_heatmap.csv")
               if not (ROOT / "outputs" / f).exists()]
    if missing:
        print(f"Missing {', '.join(missing)}: run `python scripts/run_analysis.py` first.")


if __name__ == "__main__":
    main()
