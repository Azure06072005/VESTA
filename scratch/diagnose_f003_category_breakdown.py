"""Follow-up to diagnose_f003_body_gap.py: is the 100% empty-body result
specific to a 'disclosure' category, or does Company.news() never return
real articles with body at all? The raw response has a 'category' column
that the prior diagnostic didn't inspect.

Usage (reuse the API key already in your shell's env -- do not retype it
in chat):
    ./.venv/bin/python scratch/diagnose_f003_category_breakdown.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from crawlers import vnstock_news  # noqa: E402


def main() -> None:
    for symbol in ["FPT", "VIC", "VNM", "HPG"]:
        print(f"\n=== {symbol} ===")
        raw_df = vnstock_news.fetch_raw(symbol)

        if "category" not in raw_df.columns:
            print("No 'category' column in this response -- cannot break down by type.")
            continue

        print("Category value counts:")
        print(raw_df["category"].value_counts(dropna=False).to_string())

        print("\nBody presence by category:")
        body_col = vnstock_news._find_column(raw_df, vnstock_news.BODY_ALIASES, "body")
        has_body = raw_df[body_col].notna() & (raw_df[body_col].astype(str).str.len() > 20)
        summary = raw_df.assign(has_real_body=has_body).groupby("category")["has_real_body"].agg(
            ["sum", "count"]
        )
        print(summary.to_string())


if __name__ == "__main__":
    main()