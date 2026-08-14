"""F004: cafef.vn news scraper (secondary news source).

Confirmed live (2026-08-13, real fetches during research, not guessed):
- robots.txt at cafef.vn allows the path this crawler needs
  ("Allow: /", specific disallows are all technical paths like /Ajax/,
  /Cached/, /images/ -- neither /du-lieu/ nor /tin-doanh-nghiep/ is
  disallowed). This crawler still checks robots.txt at runtime rather
  than hardcoding that conclusion, per F004's spec and B4/legal
  discipline -- if cafef changes robots.txt, this must notice, not assume.
- Real per-symbol URL: https://cafef.vn/du-lieu/tin-doanh-nghiep/{ticker
  lowercase}/Event.chn -- confirmed working and server-rendered (static
  HTML, no JS needed) for FPT. A different-looking URL
  (cafef.vn/du-lieu/hose/{ticker}-tin-tuc.chn) was tried first and is a
  dead end -- that one is JS/AJAX-rendered and returns an empty article
  list to a plain HTTP GET.
- KNOWN LIMITATION, accepted by Tran Dieu (2026-08-13, see DECISIONS.md):
  the page only server-renders ~28 recent items; further items require
  a `javascript:LoadNext();` AJAX call. Reverse-engineering that endpoint
  is explicitly NOT done here -- it would likely hit robots.txt's
  Disallow: /Ajax/. This crawler is page-1-only, full history builds up
  over repeated scheduled runs via the same idempotent-dedup-by-
  source_url pattern F003 uses, not a one-shot backfill.

UNCONFIRMED / BEST-GUESS, flagged explicitly (PROJECT_INSTRUCTIONS.md
A1), to be verified against real HTML per Tran Dieu's direction (build
now, verify after): the exact parsing strategy. Rather than guess a CSS
class name for article rows (fragile, likely to silently break on a
markup tweak), this parses by matching <a> tag href shapes confirmed live
(ending in a numeric-id + ".chn") and pairs each with the nearest
preceding date-shaped text node (DD/MM/YYYY HH:MM). This is more robust
to minor markup changes than a class-name selector, but still unverified
against the raw HTML (my fetch tool renders to markdown, not raw HTML) --
if PARSE_LINK_PATTERN or PARSE_DATE_PATTERN stop matching, this raises
loudly (see parse_articles) rather than silently returning nothing.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import time
import pathlib
import urllib.robotparser

import pandas as pd
import requests
from bs4 import BeautifulSoup

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402

SOURCE_NAME = "cafef"
BASE_URL = "https://cafef.vn"
ROBOTS_URL = "https://cafef.vn/robots.txt"
USER_AGENT = "VESTA-research-bot/1.0 (+contact: dulieu research project, non-commercial)"

# ASSUMED: no official rate limit is published by cafef.vn. Conservative
# default chosen to avoid hammering a site with no stated API contract --
# tune down only with a stated reason, per PROJECT_INSTRUCTIONS.md A1.
REQUEST_DELAY_SECONDS = 2.0

# CONFIRMED live 2026-08-13: real article URLs end in a numeric id then
# ".chn", either directly under the domain or under /du-lieu/{TICKER}-id/.
PARSE_LINK_PATTERN = re.compile(r"^https?://cafef\.vn/.*-\d+(\.chn|/.*\.chn)$")
# CONFIRMED live 2026-08-13: dates appear as DD/MM/YYYY HH:MM near each
# article link.
PARSE_DATE_PATTERN = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{1,2}:\d{2})")

NEWS_COLUMNS = ["symbol", "source", "published_at", "available_at", "headline", "body", "source_url", "fetched_at"]


def check_robots_allowed(url: str) -> bool:
    """Explicit robots.txt check, per F004's spec ('robots.txt-disallowed
    path raises rather than silently fetching') -- checked at runtime,
    not hardcoded from the 2026-08-13 research finding, since robots.txt
    can change.
    """
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(ROBOTS_URL)
    parser.read()
    return parser.can_fetch(USER_AGENT, url)


def fetch_raw(symbol: str) -> str:
    """Live network call. Checks robots.txt first and raises loudly if
    disallowed (never silently skips or silently fetches anyway). Applies
    REQUEST_DELAY_SECONDS before the request as explicit rate limiting.
    Returns raw HTML text -- parsing happens in parse_articles() so that
    logic stays testable without network access.
    """
    url = f"{BASE_URL}/du-lieu/tin-doanh-nghiep/{symbol.lower()}/Event.chn"

    if not check_robots_allowed(url):
        raise PermissionError(
            f"robots.txt at {ROBOTS_URL} disallows fetching {url} for "
            f"user-agent {USER_AGENT!r} -- refusing to fetch. This is a "
            f"hard stop, not a warning; do not bypass it."
        )

    time.sleep(REQUEST_DELAY_SECONDS)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()
    text: str = response.text
    return text


def parse_articles(html: str, symbol: str) -> pd.DataFrame:
    """Pure transform: parse raw HTML into (headline, source_url,
    published_at) rows. No network access -- fully unit-testable against
    saved/synthetic HTML fixtures.

    Raises ValueError (NOT EmptyResultError) if zero article links are
    found -- deliberately NOT treated as F008 "genuine emptiness", since
    for an actively-traded symbol like a real listed company, zero
    results much more likely means PARSE_LINK_PATTERN/PARSE_DATE_PATTERN
    stopped matching real markup (a parsing bug) than that the company
    genuinely has zero news ever. Treating that as EmptyResultError would
    let a broken scraper silently mark itself "done" instead of alerting.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("a", href=True)

    rows = []
    for link in links:
        href = str(link["href"])
        if not href.startswith("http"):
            href = BASE_URL + href
        if not PARSE_LINK_PATTERN.match(href):
            continue

        headline = link.get_text(strip=True)
        if not headline:
            continue

        # Look for a date in this link's own surrounding text, or its
        # parent element's text (covers both markup shapes observed live:
        # date text as a sibling, or date+link inside the same <li>).
        search_text = link.parent.get_text(" ", strip=True) if link.parent else ""
        date_match = PARSE_DATE_PATTERN.search(search_text)
        if not date_match:
            continue

        date_str, time_str = date_match.group(1), date_match.group(2)
        published_at = dt.datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")

        rows.append({"headline": headline, "source_url": href, "published_at": published_at})

    if not rows:
        raise ValueError(
            f"parse_articles found zero matching article links for "
            f"symbol={symbol!r}. This most likely means PARSE_LINK_PATTERN "
            f"or PARSE_DATE_PATTERN no longer match cafef.vn's real markup "
            f"(selector drift), not that this symbol genuinely has no "
            f"news -- treated as a parsing failure, not F008 genuine "
            f"emptiness. Inspect the raw HTML and update the patterns."
        )

    df = pd.DataFrame(rows).drop_duplicates(subset=["source_url"], keep="first")

    out = pd.DataFrame(
        {
            "symbol": symbol,
            "source": SOURCE_NAME,
            "published_at": df["published_at"],
            "available_at": df["published_at"],
            "headline": df["headline"],
            "body": None,  # KNOWN GAP: article body is on a separate page
            # per article, not fetched by this crawler -- see DECISIONS.md.
            "source_url": df["source_url"],
        }
    )
    out["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    return out[NEWS_COLUMNS]


def write_news(df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Shares core.news/staging.news with F003 -- same shared schema
    (DECISIONS.md 'Dual news source' entry), same idempotent dedup-by-
    source_url write pattern.
    """
    missing = set(NEWS_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"News DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    urls = df["source_url"].unique().tolist()

    con.execute("DELETE FROM staging.news WHERE source_url IN ?", [urls])
    con.register("news_df", df[NEWS_COLUMNS])
    con.execute("INSERT INTO staging.news SELECT * FROM news_df")

    con.execute("DELETE FROM core.news WHERE source_url IN ?", [urls])
    con.execute("INSERT INTO core.news SELECT * FROM news_df")
    con.unregister("news_df")

    return len(df)


def run(symbol: str) -> int:
    """Entry point: fetch live, parse, write. Returns row count written.

    Prefer calling this through F008's run_job()/retry_all() -- scraping
    is inherently more fragile than the API crawlers.
    """
    html = fetch_raw(symbol)
    parsed = parse_articles(html, symbol)
    return write_news(parsed)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F004: scrape cafef.vn news for one symbol")
    parser.add_argument("symbol")
    args = parser.parse_args()

    n = run(args.symbol)
    print(f"F004 cafef_news: wrote {n} rows for {args.symbol} to core.news")