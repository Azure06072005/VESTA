"""Exports every symbol in core.dim_symbol to a plain text file, one per
line -- the input format src/etl/batch_orchestrator.py's CLI expects.
Run this after F001 has crawled the full symbol universe.
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402


def export_symbols(output_path: str = "symbols.txt") -> int:
    con = db.bootstrap_schema()
    rows = con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()
    symbols = [r[0] for r in rows]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(symbols) + "\n")
    return len(symbols)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export core.dim_symbol to a plain symbols file")
    parser.add_argument("--out", default="symbols.txt")
    args = parser.parse_args()

    n = export_symbols(args.out)
    print(f"Wrote {n} symbols to {args.out}")