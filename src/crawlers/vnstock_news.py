"""F003: vnstock News crawler.

BODY-AVAILABILITY CLAIM RETRACTED (2026-09-02): the "full article body"
claim below is WRONG as currently observed. Re-tested live across 4
symbols (FPT, VIC, VNM, HPG; 68 rows total, scratch/diagnose_f003_body_gap.py
+ diagnose_f003_category_breakdown.py): content/summary/category are None
for 100% of rows. Company.news() currently functions as a corporate
disclosure/announcement headline feed (e.g. "FPT: Thông báo về việc giao
dịch chứng khoán thay đổi đăng ký niêm yết"), not an article-body source,
for every symbol tested. This is not a code bug -- normalize_news()
correctly passes through whatever the API returns. The original
2026-08-13 claim was evidently verified against an unrepresentative
sample (a real article that happened to have body content), not
re-tested broadly before being written up as confirmed fact. See
DECISIONS.md 2026-08-31 and 2026-09-02 entries.

SCHEMA ALSO DRIFTED (2026-09-02): a fresh live fetch_raw() call today
returns columns ['id', 'symbol', 'title', 'summary', 'content',
'publish_time', 'source', 'url', 'category', 'image_url'] -- NOT the
news_title/news_full_content/news_source_link/public_date names confirmed
2026-08-13 below. This is the same vnstock_data version-drift pattern
already found and documented for F001/dim_symbol.py (3.2.7 documented vs
3.2.2 actually installed) -- not a bug here either, since BODY_ALIASES/
URL_ALIASES already resolve both the old and new column names correctly
(confirmed: _find_column resolved body_col='content', url_col='url'
against today's live response without any code change needed). Kept as a
documented fact for the next person who sees a column-name mismatch and
wonders if something broke.

--- Original 2026-08-13 docstring (STALE on both counts above, kept for
history) ---
Confirmed live against vnstock==4.0.5 (2026-08-13, real discovery output
pasted by Tran Dieu): `Company(source='VCI', symbol=symbol).news()`
returns 21 columns for FPT, 50 rows. CONFIRMED SCHEMA (replaces the
earlier alias-guessing version):
    news_title           -- headline
    news_full_content     -- full article body (news_short_content is a
                             shorter summary, kept as fallback alias)
    news_source_link      -- article URL, used as the dedup/PRIMARY KEY
    public_date            -- ISO-ish string e.g. '2026-08-03T16:13:52'
Also present but not currently mapped: news_id, news_category_code,
icb_code, news_author, news_keyword, news_image_url, and others --
available in the raw fetch if a later feature needs them, but not carried
into core.news's fixed schema (which stays shared with F004 per
DECISIONS.md "Dual news source" entry).

DEPRIORITIZED per DECISIONS.md (2026-08-11): an earlier report flagged
this endpoint as prone to intermittent HTTP 500s. Built here WITH F008
retry-awareness from the start (raises EmptyResultError for genuine
emptiness, lets any other exception -- including HTTP failures -- bubble
as a transient failure for F008's run_job()/retry_all() to catch), unlike
F001/F002/F005/F006 which needed a separate retrofit pass.

STILL UNCONFIRMED: whether `.news()` takes any pagination/date-range
arguments, or always returns the same fixed-size window (50 rows was the
live result -- unknown if that's a hard cap or just this symbol's recent
volume). fetch_raw() currently takes no such arg.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import pathlib

import pandas as pd

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402

REQUIRED_ENV_VAR = "VNSTOCK_API_KEY"
SOURCE_NAME = "vnstock"

# CONFIRMED live 2026-08-13 (real output for FPT) -- see module docstring.
HEADLINE_ALIASES = ["news_title", "title", "headline"]
PUBLISHED_AT_ALIASES = ["public_date", "published_at", "date", "publish_time"]
BODY_ALIASES = ["news_full_content", "news_short_content", "content", "body"]
URL_ALIASES = ["news_source_link", "source_url", "url", "link"]

NEWS_COLUMNS = ["symbol", "source", "published_at", "available_at", "headline", "body", "source_url", "fetched_at"]


def _authenticate() -> None:
    db.load_env()
    api_key = os.environ.get(REQUIRED_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{REQUIRED_ENV_VAR} is not set. Export it before running this "
            f"crawler -- credentials never go in code or configs/."
        )
    try:
        import vnstock_data as vs
    except ImportError:
        import vnstock as vs  # type: ignore[no-redef]

    if hasattr(vs, "change_api_key"):
        vs.change_api_key(api_key)


def fetch_raw(symbol: str) -> pd.DataFrame:
    """Live network call. Requires VNSTOCK_API_KEY to be set.

    Any exception here (including the HTTP 500s DECISIONS.md flags this
    endpoint for) should be left to bubble to the caller -- F008's
    run_job() wraps this and records it as a transient failure, eligible
    for retry. Do not catch-and-suppress here.
    """
    _authenticate()
    try:
        import vnstock_data as vs
    except ImportError:
        import vnstock as vs  # type: ignore[no-redef]

    company = vs.Company(source="VCI", symbol=symbol)
    result: pd.DataFrame = company.news()
    return result


def _find_column(df: pd.DataFrame, aliases: list[str], field: str) -> str:
    for candidate in aliases:
        if candidate in df.columns:
            return candidate
    raise ValueError(
        f"Could not find a source column for '{field}' in fetched news "
        f"data. Columns present: {list(df.columns)}. Aliases tried: "
        f"{aliases}. Run discover_news_schema.py against a live key and "
        f"update the alias list rather than guessing."
    )


def normalize_news(raw_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Pure transform: map raw columns -> shared F003/F004 news schema,
    dedup by source_url (spec requirement), available_at = published_at
    (no separate disclosure-lag concept for news, unlike F005). Genuinely
    empty results raise EmptyResultError (F008-compatible: a symbol with
    no recent news is valid, not a failure). No network access -- fully
    unit-testable with synthetic DataFrames.
    """
    if raw_df.empty:
        raise EmptyResultError(
            f"fetch_raw returned an empty DataFrame for symbol={symbol!r} -- "
            f"F008-compatible: a symbol with no recent news is a valid, "
            f"non-failure outcome -- recorded via record_empty(), NOT "
            f"retried."
        )

    headline_col = _find_column(raw_df, HEADLINE_ALIASES, "headline")
    published_col = _find_column(raw_df, PUBLISHED_AT_ALIASES, "published_at")
    body_col = _find_column(raw_df, BODY_ALIASES, "body")
    url_col = _find_column(raw_df, URL_ALIASES, "source_url")

    published_at = pd.to_datetime(raw_df[published_col])

    out = pd.DataFrame(
        {
            "symbol": symbol,
            "source": SOURCE_NAME,
            "published_at": published_at,
            "available_at": published_at,
            "headline": raw_df[headline_col].astype(str),
            "body": raw_df[body_col].astype(str),
            "source_url": raw_df[url_col].astype(str),
        }
    )
    
    # Generate synthetic URL if source_url is "None"
    missing_urls = out["source_url"] == "None"
    if missing_urls.any():
        out.loc[missing_urls, "source_url"] = out[missing_urls].apply(
            lambda r: f"vnstock://{symbol}/{r['published_at'].isoformat()}/{abs(hash(r['headline']))}", axis=1
        )
    
    out["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    before = len(out)
    out = out.drop_duplicates(subset=["source_url"], keep="first")
    dropped = before - len(out)
    if dropped:
        print(f"[F003] dropped {dropped} duplicate source_url row(s) for {symbol!r} within a single fetch")

    return out[NEWS_COLUMNS]


def write_news(df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Validate + write to staging, then promote to core, deduped on
    source_url (the PRIMARY KEY -- see F003/F004's shared schema).
    Idempotent: re-running with overlapping articles doesn't duplicate.
    """
    missing = set(NEWS_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"News DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    urls = df["source_url"].unique().tolist()

    cols_sql = ", ".join(NEWS_COLUMNS)
    temp_name = f"news_df_{id(df)}"
    con.execute("DELETE FROM staging.news WHERE source_url IN ?", [urls])
    con.register(temp_name, df[NEWS_COLUMNS])
    con.execute(f"INSERT INTO staging.news ({cols_sql}) SELECT * FROM {temp_name}")

    con.execute("DELETE FROM core.news WHERE source_url IN ?", [urls])
    con.execute(f"INSERT INTO core.news ({cols_sql}) SELECT * FROM {temp_name}")
    con.unregister(temp_name)

    return len(df)


def run(symbol: str, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Entry point: fetch live, normalize, write. Returns row count written.

    Prefer calling this through F008's run_job()/retry_all() rather than
    directly, given this endpoint's documented flakiness -- see
    DECISIONS.md.
    """
    raw = fetch_raw(symbol)
    normalized = normalize_news(raw, symbol)
    return write_news(normalized, con=con)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F003: crawl vnstock news for one symbol")
    parser.add_argument("symbol")
    args = parser.parse_args()

    n = run(args.symbol)
    print(f"F003 vnstock_news: wrote {n} rows for {args.symbol} to core.news")