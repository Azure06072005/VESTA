"""Diagnostic for F003: the stored core.news rows (source='vnstock') show
body=NULL for every sampled row, and their source_url is the SYNTHETIC
vnstock:// fallback URI, not a real news_source_link. But normalize_news()
has NO fallback for a missing body (only source_url has one) -- a real
missing body would be written as the literal string "None", not SQL NULL.
This mismatch strongly suggests the stored rows predate the current
crawler code, the same pattern already found in core.dim_symbol's
contamination (2026-08-31).

This calls the REAL fetch_raw()/normalize_news() functions fresh, right
now, for a couple of symbols, and reports:
  - what fraction of rows have a real (non-"None") body today
  - whether the headline "corporate disclosure notice" pattern is a
    distinct row-type that structurally lacks a body, or whether real
    articles for the same symbol DO carry news_full_content today

Usage:
    ./.venv/bin/python scratch/diagnose_f003_body_gap.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from crawlers import vnstock_news  # noqa: E402


def main() -> None:
    for symbol in ["FPT", "VIC"]:
        print(f"\n=== {symbol} ===")
        raw_df = vnstock_news.fetch_raw(symbol)
        print(f"fetch_raw() columns: {list(raw_df.columns)}")
        print(f"fetch_raw() row count: {len(raw_df)}")

        body_col = vnstock_news._find_column(raw_df, vnstock_news.BODY_ALIASES, "body")
        url_col = vnstock_news._find_column(raw_df, vnstock_news.URL_ALIASES, "source_url")
        print(f"Resolved body column: {body_col!r}, url column: {url_col!r}")

        real_body_count = raw_df[body_col].notna().sum()
        empty_string_count = (raw_df[body_col].astype(str).str.strip() == "").sum()
        none_string_count = (raw_df[body_col].astype(str) == "None").sum()
        print(f"Rows with non-null body (pandas notna): {real_body_count} / {len(raw_df)}")
        print(f"Rows where body casts to empty string: {empty_string_count}")
        print(f"Rows where body casts to literal 'None': {none_string_count}")

        real_url_count = (raw_df[url_col].astype(str) != "None").sum()
        print(f"Rows with a real (non-'None') source_url today: {real_url_count} / {len(raw_df)}")

        print("\nSample of one row WITH a real body (if any):")
        with_body = raw_df[raw_df[body_col].notna() & (raw_df[body_col].astype(str).str.len() > 20)]
        if len(with_body):
            r = with_body.iloc[0]
            print(f"  headline: {r.get('news_title', r.get('title', '?'))}")
            print(f"  body (first 200 chars): {str(r[body_col])[:200]}")
        else:
            print("  NONE FOUND -- no row for this symbol has real body text today.")

        print("\nSample of one row WITHOUT a real body (if any), to check headline pattern:")
        without_body = raw_df[raw_df[body_col].isna() | (raw_df[body_col].astype(str).isin(["None", ""]))]
        if len(without_body):
            r = without_body.iloc[0]
            print(f"  headline: {r.get('news_title', r.get('title', '?'))}")
        else:
            print("  NONE FOUND -- every row for this symbol has a real body today.")


if __name__ == "__main__":
    main()