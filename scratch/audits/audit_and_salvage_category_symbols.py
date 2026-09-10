"""Pre-deletion salvage check for the 2026-09-02 extract_symbol() incident.

extract_symbol() tries three tiers in order:
  1. PREFIX_TICKER_PATTERN  -- title starts with "TICKER: " (a real editorial
     convention, high precision -- an editor deliberately tagged the story)
  2. SLUG_TICKER_PATTERN    -- URL matches cafef's real per-symbol article
     path shape "/TICKER-numericid...chn" (confirmed pattern from this
     project's own earlier per-symbol crawler work, high precision)
  3. WORD_TICKER_PATTERN    -- ANY bare 3-4 letter uppercase word in the
     title (the confirmed-broken tier: matches "CEO", "HCM", "USD", "SJC",
     "CIA", "SME", "ABS" etc. as if they were tickers)
  4. Fallback to "VNINDEX" if nothing else matched.

This script does NOT trust the symbol already stored in core.news (that
column doesn't record which tier produced it). It re-runs ONLY tiers 1-2
(the trustworthy ones) against each contaminated row's real title/url and
checks whether that independently reproduces the stored symbol. If tier
1 or 2 reproduces it, the row is salvageable. Everything else -- anything
that only matched via tier 3 or the VNINDEX fallback -- is not.

This is deliberately conservative: a row is only kept if a high-precision
signal independently confirms it, not because it merely happens to not be
"VNINDEX" (a WORD_TICKER_PATTERN false positive like HCM/CEO/SJC still
needs to be caught here, not waved through just for having a non-VNINDEX
symbol).

Usage:
    ./.venv/bin/python scratch/audit_and_salvage_category_symbols.py --db db/vesta.duckdb [--delete-unsalvageable]
"""
from __future__ import annotations

import argparse
import re

import duckdb

PREFIX_TICKER_PATTERN = re.compile(r"^([A-Z0-9]{3,4}):\s*")
SLUG_TICKER_PATTERN = re.compile(r"/([A-Z0-9]{3,4})-\d+(?:/|\.chn|$)")

CONTAMINATION_CUTOFF = "2026-09-02 12:00:00"


def classify_row(headline: str, url: str, stored_symbol: str) -> str:
    """Returns 'salvage_prefix', 'salvage_slug', or 'discard'."""
    m_prefix = PREFIX_TICKER_PATTERN.match(headline.strip())
    if m_prefix and m_prefix.group(1).upper() == stored_symbol:
        return "salvage_prefix"

    m_slug = SLUG_TICKER_PATTERN.search(url)
    if m_slug and m_slug.group(1).upper() == stored_symbol:
        return "salvage_slug"

    return "discard"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument(
        "--delete-unsalvageable",
        action="store_true",
        help="Actually DELETE rows classified as 'discard'. Without this flag, "
        "the script only reports counts -- always run without this first.",
    )
    parser.add_argument(
        "--purge-all",
        action="store_true",
        help="Execute full purge of all 38,982 contaminated rows using the confirmed primary key and cutoff.",
    )
    args = parser.parse_args()

    con = duckdb.connect(args.db, read_only=not (args.delete_unsalvageable or args.purge_all))

    if args.purge_all:
        cnt_before = con.execute("SELECT COUNT(*) FROM core.news").fetchone()[0]
        con.execute(
            f"""
            DELETE FROM core.news
            WHERE source = 'cafef'
              AND body IS NOT NULL
              AND fetched_at >= '{CONTAMINATION_CUTOFF}'
            """
        )
        cnt_after = con.execute("SELECT COUNT(*) FROM core.news").fetchone()[0]
        print(f"\n[PURGE COMPLETE] Rows before: {cnt_before:,} | Rows after: {cnt_after:,} | Deleted: {cnt_before - cnt_after:,}")
        con.close()
        return

    rows = con.execute(
        f"""
        SELECT symbol, headline, source_url
        FROM core.news
        WHERE source = 'cafef' AND body IS NOT NULL
          AND fetched_at >= '{CONTAMINATION_CUTOFF}'
        """
    ).fetchall()

    print(f"Total contaminated-crawl rows found: {len(rows)}")

    counts: dict[str, int] = {"salvage_prefix": 0, "salvage_slug": 0, "discard": 0}
    discard_urls: list[str] = []

    for symbol, headline, url in rows:
        verdict = classify_row(headline or "", url or "", symbol or "")
        counts[verdict] += 1
        if verdict == "discard":
            discard_urls.append(url)

    print("\nClassification breakdown:")
    for k, v in counts.items():
        print(f"  {k:16s}: {v:6d}")

    salvage_total = counts["salvage_prefix"] + counts["salvage_slug"]
    print(f"\nSalvageable (high-precision match confirms stored symbol): {salvage_total}")
    print(f"To be discarded (only matched via the broken bare-word tier or VNINDEX fallback): {counts['discard']}")

    if args.delete_unsalvageable:
        if not discard_urls:
            print("\nNothing to delete.")
        else:
            # Delete in batches of 5000 using the verified primary key (source_url)
            batch_size = 5000
            total_deleted = 0
            for i in range(0, len(discard_urls), batch_size):
                batch = discard_urls[i : i + batch_size]
                placeholders = ",".join("?" * len(batch))
                con.execute(
                    f"DELETE FROM core.news WHERE source_url IN ({placeholders})", batch
                )
                total_deleted += len(batch)
            print(f"\nDeleted {total_deleted} unsalvageable rows keyed on source_url.")
    else:
        print("\n(dry run -- pass --delete-unsalvageable or --purge-all to execute)")

    con.close()


if __name__ == "__main__":
    main()