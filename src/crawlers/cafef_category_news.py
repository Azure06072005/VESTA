"""F004c: cafef.vn editorial category-page crawler.

CONFIRMED LIVE 2026-09-02 (real .har capture,
cafef_du-lieu_tintuc_sample_more.har, category=tai-chinh-quoc-te, 376
entries, real browsing session with scroll/pagination):

Unlike F003/F004's per-symbol feeds (confirmed 2026-09-02 to be ~99.99%
corporate disclosures, see DECISIONS.md), category pages are genuine
editorial journalism -- 15/15 real articles verified on two different
pages (page 2 and page 5 of the same category), zero disclosure-type
rows.

TWO CONFIRMED LISTING TEMPLATES, ONE SHARED EXTRACTION RULE:
- Page 1 (the category landing page itself, e.g. cafef.vn/tai-chinh-quoc-te.chn)
  server-renders a MIX of layout classes: 'firstitem wp100 clearfix'
  (hero), 'big' (secondary), 'item' (list). No 'time-ago' timestamp span
  present in this variant.
- Pages 2+ are fetched via a separate AJAX endpoint (see TIMELINE_URL_TEMPLATE
  below) and use a single uniform class: 'tlitem box-category-item'. This
  variant DOES include a real timestamp span.
- CONFIRMED: despite the different wrapper classes, every listing article
  on both templates is `<div role="article">` containing `<h3><a href=...>`
  for the title+URL. This single rule (div[role='article'] -> h3 a) covers
  every variant seen so far -- verified against 37 landing-page articles
  (4 distinct classes) and 30 AJAX-page articles (1 class, across 2
  different pages) with zero misses.
- published_at is intentionally NOT sourced from the listing page (only
  the tlitem variant has it, inconsistently) -- use
  cafef_article_body.parse_article_body()'s confirmed
  <meta property="article:published_time"> extraction on the article
  detail page instead, for a consistent source across both variants.

PAGINATION ENDPOINT (confirmed real, live headers captured):
    GET https://cafef.vn/timelinelist/{category_id}/{page_number}.chn
    Required headers: Referer: https://cafef.vn/{category_slug}.chn
                       X-Requested-With: XMLHttpRequest
Category IDs are NOT yet mapped for categories other than
tai-chinh-quoc-te (id=18832, confirmed from this capture). Each new
category needs its own one-time id discovery (visit the category page,
capture one timelinelist request) before it can be crawled -- do not
guess an id for an unconfirmed category.

STILL UNCONFIRMED, explicitly flagged:
- How many total pages exist per category (this capture only exercised
  pages 1-10 via scrolling; the real ceiling, and whether it changes as
  new articles are published, is unknown).
- Whether AJAX pages are 100% editorial for every category, or whether
  some categories (e.g. a hypothetical disclosure-adjacent category) mix
  in non-editorial content -- only tai-chinh-quoc-te has been checked.
- robots.txt permissiveness was already confirmed generally (2026-08-31,
  cross-checked against sitemap.xml) but re-verify if this crawler is
  built out further, since that check predates this specific endpoint.
"""
from __future__ import annotations

import time

import requests
from bs4 import BeautifulSoup

from crawlers.cafef_news import REQUEST_DELAY_SECONDS, USER_AGENT, check_robots_allowed

BASE_URL = "https://cafef.vn"

# Confirmed live 2026-09-02 for exactly this one category. Extend only
# after capturing a real request for a new category -- do not guess ids.
CATEGORY_IDS = {
    "tai-chinh-quoc-te": 18832,
}

TIMELINE_URL_TEMPLATE = "https://cafef.vn/timelinelist/{category_id}/{page}.chn"


def fetch_category_landing_page(category_slug: str) -> str:
    url = f"{BASE_URL}/{category_slug}.chn"
    if not check_robots_allowed(url):
        raise PermissionError(f"robots.txt disallows fetching {url}")
    time.sleep(REQUEST_DELAY_SECONDS)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    return resp.text


def fetch_timeline_page(category_slug: str, page: int) -> str:
    """page=1 is NOT valid here -- confirmed only pages 2+ exist on this
    AJAX endpoint; page 1 content comes from the landing page itself.
    """
    if category_slug not in CATEGORY_IDS:
        raise ValueError(
            f"No confirmed category_id for {category_slug!r}. "
            f"CATEGORY_IDS only contains verified, live-captured ids -- "
            f"capture a real .har for this category before adding it."
        )
    category_id = CATEGORY_IDS[category_slug]
    url = TIMELINE_URL_TEMPLATE.format(category_id=category_id, page=page)
    referer = f"{BASE_URL}/{category_slug}.chn"
    if not check_robots_allowed(url):
        raise PermissionError(f"robots.txt disallows fetching {url}")
    time.sleep(REQUEST_DELAY_SECONDS)
    resp = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.text


def parse_article_links(html: str) -> list[dict]:
    """Shared extraction rule confirmed across BOTH listing templates
    (landing page's mixed layout classes and the AJAX tlitem fragments):
    every article is `<div role="article">` containing `<h3><a href=...>`.
    Raises loudly if zero articles are found -- a page that structurally
    can't be parsed should not silently return an empty list that looks
    like "no new articles" to a caller.
    """
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.find_all("div", attrs={"role": "article"})

    results = []
    for art in articles:
        h3 = art.find("h3")
        link = (h3.find("a") if h3 else None) or art.find("a")
        if link is None or not link.get("href"):
            continue
        href = link["href"]
        if not isinstance(href, str):
            continue  # malformed attribute (list-valued), not a real URL
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        results.append({"url": url, "title": link.get_text(strip=True)})

    if not results:
        raise ValueError(
            "No div[role='article'] with a title link found -- either the "
            "page structure changed (needs a fresh .har check, not a "
            "guessed selector fix) or this page genuinely has no articles."
        )
    return results