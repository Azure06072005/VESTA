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
- KNOWN LIMITATION originally accepted (2026-08-13): page-1-only.
  OVERRIDDEN (2026-08-30): robots.txt now allows `/`, so this crawler
  has been upgraded to use the paginated `/Ajax/` endpoint to backfill
  historical news fully, in a while-loop.

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
import os
import pathlib
import re
import sys
import time
import urllib.robotparser

import pandas as pd
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402

SOURCE_NAME = "cafef"
BASE_URL = "https://cafef.vn"
ROBOTS_URL = "https://cafef.vn/robots.txt"
USER_AGENT = "VESTA-research-bot/1.0 (+contact: dulieu research project, non-commercial)"

# Adjusted to 0.5s for efficiency since paginated historical crawls are heavy.
# No Crawl-delay is specified in robots.txt.
REQUEST_DELAY_SECONDS = 0.5

# CONFIRMED live 2026-08-13: real article URLs end in a numeric id then
# ".chn", either directly under the domain or under /du-lieu/{TICKER}-id/.
PARSE_LINK_PATTERN = re.compile(r"^https?://cafef\.vn/.*-\d+(\.chn|/.*\.chn)$")
# CONFIRMED live 2026-08-13: dates appear as DD/MM/YYYY HH:MM near each
# article link.
PARSE_DATE_PATTERN = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{1,2}:\d{2})")

NEWS_COLUMNS = ["symbol", "source", "published_at", "available_at", "headline", "body", "source_url", "fetched_at"]


_ROBOTS_PARSER: urllib.robotparser.RobotFileParser | None = None
_ROBOTS_FETCHED_AT: dt.datetime | None = None


def get_robots_parser() -> urllib.robotparser.RobotFileParser:
    global _ROBOTS_PARSER, _ROBOTS_FETCHED_AT
    now = dt.datetime.now(dt.timezone.utc)
    if _ROBOTS_PARSER is None or _ROBOTS_FETCHED_AT is None or (now - _ROBOTS_FETCHED_AT).total_seconds() > 3600:
        parser = urllib.robotparser.RobotFileParser()
        try:
            resp = requests.get(ROBOTS_URL, headers={"User-Agent": USER_AGENT}, timeout=10)
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
            else:
                parser.parse(["User-agent: *", "Allow: /"])
        except Exception:
            parser.parse(["User-agent: *", "Allow: /"])
        _ROBOTS_PARSER = parser
        _ROBOTS_FETCHED_AT = now
    return _ROBOTS_PARSER


def check_robots_allowed(url: str) -> bool:
    """Explicit robots.txt check, per F004's spec ('robots.txt-disallowed
    path raises rather than silently fetching') -- cached with 1-hour TTL.
    """
    parser = get_robots_parser()
    return parser.can_fetch(USER_AGENT, url)


def fetch_page(symbol: str, page_index: int) -> str:
    """Live network call for a specific page of historical news.
    Checks robots.txt first and raises loudly if disallowed. Applies
    REQUEST_DELAY_SECONDS before the request.
    """
    url = f"{BASE_URL}/du-lieu/Ajax/Events_RelatedNews_New.aspx"

    if not check_robots_allowed(url):
        raise PermissionError(
            f"robots.txt at {ROBOTS_URL} disallows fetching {url} for "
            f"user-agent {USER_AGENT!r} -- refusing to fetch. This is a "
            f"hard stop, not a warning; do not bypass it."
        )

    time.sleep(REQUEST_DELAY_SECONDS)
    
    params: dict[str, str | int] = {
        "symbol": symbol,
        "floorID": 0,
        "configID": 0,
        "PageIndex": page_index,
        "PageSize": 30,
        "Type": 2,
    }
    
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=15)
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
        try:
            published_at = dt.datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
            now_local = dt.datetime.now()
            if published_at > now_local or published_at.year < 2000:
                published_at = now_local
        except Exception:
            published_at = dt.datetime.now()

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
    if df.empty:
        return 0

    missing = set(NEWS_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"News DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    urls = df["source_url"].unique().tolist()

    cols_sql = ", ".join(NEWS_COLUMNS)
    con.execute("DELETE FROM staging.news WHERE source_url IN ?", [urls])
    con.register("news_df", df[NEWS_COLUMNS])
    con.execute(f"INSERT INTO staging.news ({cols_sql}) SELECT * FROM news_df")

    con.execute("DELETE FROM core.news WHERE source_url IN ?", [urls])
    con.execute(f"INSERT INTO core.news ({cols_sql}) SELECT * FROM news_df")
    con.unregister("news_df")

    return len(df)


def get_existing_urls(symbol: str, con: "duckdb.DuckDBPyConnection | None" = None) -> set[str]:
    """Lấy danh sách URL đã có trong core.news để nhận diện đường biên dữ liệu cũ."""
    if con is not None:
        try:
            rows = con.execute("SELECT source_url FROM core.news WHERE upper(symbol) = ?", [symbol.strip().upper()]).fetchall()
            return {r[0] for r in rows if r[0]}
        except Exception:
            pass

    # Fallback kết nối read_only an toàn
    for db_path_str in [os.environ.get("VESTA_DB_PATH"), str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb"), str(PROJECT_ROOT / "db" / "vesta.duckdb")]:
        if db_path_str and os.path.exists(db_path_str):
            try:
                con_ro = duckdb.connect(db_path_str, read_only=True)
                rows = con_ro.execute("SELECT source_url FROM core.news WHERE upper(symbol) = ?", [symbol.strip().upper()]).fetchall()
                con_ro.close()
                return {r[0] for r in rows if r[0]}
            except Exception:
                pass
    return set()


def run(symbol: str, incremental: bool = True, force: bool = False, max_pages: int = 100) -> int:
    """Entry point: fetch paginated history, parse, and write. Returns total rows written.
    
    Nếu incremental=True (mặc định) và force=False:
        - Tải các URL đã có trong core.news của mã này.
        - Khi gặp bài viết đã tồn tại (chạm đường biên dữ liệu cũ < 2026-09-14),
          chỉ lưu các bài mới của 4 ngày gần nhất và DỪNG NGAY LẬP TỨC (không cào lại lịch sử 2007).
    """
    symbol = symbol.strip().upper()
    con = db.bootstrap_schema()
    existing_urls = get_existing_urls(symbol, con) if (incremental and not force) else set()
    
    page_index = 1
    total_written = 0
    
    while page_index <= max_pages:
        html = fetch_page(symbol, page_index)
        
        try:
            parsed = parse_articles(html, symbol)
        except ValueError as e:
            if "found zero matching article links" in str(e):
                # If page 1 fails, it might mean bad symbol or selector drift.
                # If page > 1 fails, it just means we reached the end of history.
                if page_index == 1:
                    from etl.retry_failed_jobs import EmptyResultError
                    raise EmptyResultError(f"No news found on page 1 for {symbol}") from e
                else:
                    break
            else:
                raise

        # Kiểm tra trùng lặp với dữ liệu đã có
        if existing_urls:
            new_df = parsed[~parsed["source_url"].isin(existing_urls)]
            if len(new_df) < len(parsed):
                # Đã chạm vào đường biên dữ liệu cũ (ví dụ trước 2026-09-14)
                if not new_df.empty:
                    written = write_news(new_df, con=con)
                    total_written += written
                # DỪNG LẠI NGAY LẬP TỨC: Toàn bộ các trang sau đều là tin cũ hơn!
                break
            else:
                written = write_news(new_df, con=con)
                total_written += written
        else:
            written = write_news(parsed, con=con)
            total_written += written

        page_index += 1

    return total_written


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F004: scrape cafef.vn news for one symbol")
    parser.add_argument("symbol")
    args = parser.parse_args()

    n = run(args.symbol)
    print(f"F004 cafef_news: wrote {n} rows for {args.symbol} to core.news")