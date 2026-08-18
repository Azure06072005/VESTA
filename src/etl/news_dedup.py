"""F009 item 5: near-duplicate news detection across F003/F004.

DECISION (2026-08-16, see DECISIONS.md): F003 (vnstock) and F004 (cafef)
currently dedupe only by exact source_url match, so the same real-world
event covered by both sources with different URLs is treated as two
independent signals -- this would double-weight that event in any
sentiment aggregation F201 does (e.g. daily average/sum sentiment per
symbol). Rather than delete either row (raw-payload-preserving principle,
F009 item 7 -- we never silently discard crawled data), near-duplicates
are FLAGGED via a nullable duplicate_of column (added by
etl.migrations.migrate_news_add_duplicate_of_column): the later-published
row of a detected pair points at the earlier row's source_url;
duplicate_of stays NULL for canonical (first-seen, or non-duplicate) rows.
Downstream consumers (F102/F201) can do `WHERE duplicate_of IS NULL` to
count each real-world event once, while both raw articles remain queryable
for anyone who wants them.

Heuristic, not exact: same symbol, published_at within
DUPLICATE_TIME_WINDOW of each other, headline similarity (difflib
SequenceMatcher ratio) >= DUPLICATE_SIMILARITY_THRESHOLD. Both constants
are ASSUMED starting points, not tuned against real labeled duplicate
pairs -- flagged explicitly rather than presented as validated (PROJECT_
INSTRUCTIONS.md A1). Revisit once real F003+F004 data overlaps enough to
manually inspect candidate pairs.
"""
from __future__ import annotations

import datetime as dt
import difflib
import sys
import pathlib

import pandas as pd

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402

# ASSUMED starting points -- see module docstring. Not yet validated
# against real labeled duplicate pairs.
DUPLICATE_TIME_WINDOW = dt.timedelta(hours=6)
DUPLICATE_SIMILARITY_THRESHOLD = 0.75


def _headline_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def find_near_duplicates(news_df: pd.DataFrame) -> pd.DataFrame:
    """Pure transform: given a DataFrame of news rows for ONE symbol
    (needs symbol, published_at, headline, source_url columns -- pass in
    core.news rows already filtered to a single symbol), returns a
    (source_url, duplicate_of) mapping for rows detected as near-
    duplicates of an earlier row. Rows not returned here should have
    duplicate_of left/set to NULL. O(n^2) headline comparisons -- fine for
    a single symbol's article volume, not intended to run across the
    whole news table at once.
    """
    if news_df.empty:
        return pd.DataFrame(columns=["source_url", "duplicate_of"])

    sorted_df = news_df.sort_values("published_at").reset_index(drop=True)
    records: list[dict[object, object]] = sorted_df.to_dict(orient="records")
    duplicate_of: dict[str, str] = {}

    for i, row_i in enumerate(records):
        url_i = str(row_i["source_url"])
        if url_i in duplicate_of:
            continue  # i itself is already a known duplicate; don't chain through it
        published_i = pd.Timestamp(str(row_i["published_at"]))
        headline_i = str(row_i["headline"])

        for row_j in records[i + 1 :]:
            url_j = str(row_j["source_url"])
            if url_j in duplicate_of:
                continue
            published_j = pd.Timestamp(str(row_j["published_at"]))
            time_gap = published_j - published_i
            if time_gap > DUPLICATE_TIME_WINDOW:
                break  # sorted by time -- no later row can be within window either
            similarity = _headline_similarity(headline_i, str(row_j["headline"]))
            if similarity >= DUPLICATE_SIMILARITY_THRESHOLD:
                duplicate_of[url_j] = url_i

    return pd.DataFrame(
        [{"source_url": url, "duplicate_of": canonical} for url, canonical in duplicate_of.items()]
    )


def apply_duplicate_flags(mapping_df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Writes the duplicate_of mapping into core.news (and staging.news)
    for the given rows. Only ever sets duplicate_of on rows currently
    NULL -- never overwrites an existing flag, so re-running detection
    doesn't fight with a manual correction someone made.
    """
    if mapping_df.empty:
        return 0

    con = con or db.bootstrap_schema()
    con.register("mapping_df", mapping_df[["source_url", "duplicate_of"]])
    con.execute(
        "UPDATE core.news SET duplicate_of = mapping_df.duplicate_of "
        "FROM mapping_df WHERE core.news.source_url = mapping_df.source_url "
        "AND core.news.duplicate_of IS NULL"
    )
    con.execute(
        "UPDATE staging.news SET duplicate_of = mapping_df.duplicate_of "
        "FROM mapping_df WHERE staging.news.source_url = mapping_df.source_url "
        "AND staging.news.duplicate_of IS NULL"
    )
    con.unregister("mapping_df")

    return len(mapping_df)


def run_dedup_for_symbol(symbol: str, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Entry point: read a symbol's news from core.news, detect near-
    duplicates, flag them. Returns count of rows flagged."""
    con = con or db.bootstrap_schema()
    news_df: pd.DataFrame = con.execute(
        "SELECT symbol, published_at, headline, source_url FROM core.news WHERE symbol = ?", [symbol]
    ).df()
    mapping = find_near_duplicates(news_df)
    return apply_duplicate_flags(mapping, con)