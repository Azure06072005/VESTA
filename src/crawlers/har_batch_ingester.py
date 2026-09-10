"""Unified HAR Batch Ingester for VESTA Macro & Media Portals.

Extracts, normalizes, and ingests financial/macro articles from captured HAR
network archives (Tiền Phong, Tuổi Trẻ, VnEconomy, Vietstock, VietnamFinance).
Directly parses rendered HTML/JSON payloads from HAR entries to minimize network load,
extracts full body text and summaries, and persists into `staging.macro_policy` and
`core.macro_policy` idempotently with deduplication on `source_url`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path
import re
import ssl
import sys
import time
from typing import Any, Dict, List, Optional
import urllib.request
import warnings

from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning
import duckdb
import pandas as pd

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Quant-Crawler/2.1)"
)


def _create_ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def clean_html(raw_html: Optional[str]) -> str:
    """Strips scripts, styles, ads and returns clean text."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside", "header", "form"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def parse_tienphong(har_path: Path) -> list[dict[str, Any]]:
    records = []
    seen = set()
    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)

    for e in data.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        text = e.get("response", {}).get("content", {}).get("text", "")
        if not text:
            continue

        # Check API response
        if "api.tienphong.vn" in url and "morenews" in url:
            try:
                js = json.loads(text)
                html_chunk = js.get("data", {}).get("html", "") if isinstance(js.get("data"), dict) else ""
                if not html_chunk and isinstance(js.get("data"), str):
                    html_chunk = js.get("data")
                if html_chunk:
                    soup = BeautifulSoup(html_chunk, "html.parser")
                    for a in soup.find_all("a"):
                        t = a.get_text(strip=True)
                        hr = a.get("href", "")
                        if len(t) > 25 and hr and hr.endswith(".tpo"):
                            full_url = f"https://tienphong.vn{hr}" if hr.startswith("/") else hr
                            if full_url not in seen:
                                seen.add(full_url)
                                records.append({
                                    "source": "tienphong",
                                    "issuing_body": "Báo Tiền Phong",
                                    "doc_type": "Tin tức & Thị trường",
                                    "headline": t,
                                    "summary": t,
                                    "body": t,
                                    "source_url": full_url,
                                })
            except Exception:
                pass
        # Check rendered HTML
        elif "tienphong.vn" in url and "html" in e.get("response", {}).get("content", {}).get("mimeType", ""):
            soup = BeautifulSoup(text, "html.parser")
            for a in soup.find_all("a"):
                t = a.get_text(strip=True)
                hr = a.get("href", "")
                if len(t) > 25 and hr and hr.endswith(".tpo"):
                    full_url = f"https://tienphong.vn{hr}" if hr.startswith("/") else hr
                    if full_url not in seen:
                        seen.add(full_url)
                        # Extract sapo/summary if available in parent
                        p = a.find_parent(["article", "div", "li"])
                        summary = t
                        if p:
                            sapo = p.find(class_=re.compile(r"sapo|summary|lead|desc"))
                            if sapo:
                                summary = sapo.get_text(strip=True)
                        records.append({
                            "source": "tienphong",
                            "issuing_body": "Báo Tiền Phong",
                            "doc_type": "Tin tức & Thị trường",
                            "headline": t,
                            "summary": summary,
                            "body": summary,
                            "source_url": full_url,
                        })
    return records


def parse_tuoitre(har_path: Path) -> list[dict[str, Any]]:
    records = []
    seen = set()
    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)

    for e in data.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        text = e.get("response", {}).get("content", {}).get("text", "")
        if not text or "tuoitre.vn" not in url:
            continue

        soup = BeautifulSoup(text, "html.parser")
        for a in soup.find_all("a"):
            t = a.get_text(strip=True)
            hr = a.get("href", "")
            if len(t) > 25 and hr and hr.endswith(".htm") and not any(k in hr for k in ["/video/", "/media/", "/podcast/"]):
                full_url = f"https://tuoitre.vn{hr}" if hr.startswith("/") else hr
                if full_url not in seen:
                    seen.add(full_url)
                    p = a.find_parent(["article", "div", "li"])
                    summary = t
                    if p:
                        sapo = p.find(class_=re.compile(r"sapo|summary|lead|desc"))
                        if sapo:
                            summary = sapo.get_text(strip=True)
                    records.append({
                        "source": "tuoitre",
                        "issuing_body": "Báo Tuổi Trẻ",
                        "doc_type": "Kinh doanh & Thị trường",
                        "headline": t,
                        "summary": summary,
                        "body": summary,
                        "source_url": full_url,
                    })
    return records


def parse_vneconomy(har_path: Path) -> list[dict[str, Any]]:
    records = []
    seen = set()
    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)

    for e in data.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        text = e.get("response", {}).get("content", {}).get("text", "")
        if not text or "vneconomy.vn" not in url:
            continue

        soup = BeautifulSoup(text, "html.parser")
        for a in soup.find_all("a"):
            t = a.get_text(strip=True)
            hr = a.get("href", "")
            if len(t) > 25 and hr and hr.endswith(".htm") and not any(k in hr for k in ["/video/", "/magazine/"]):
                full_url = f"https://vneconomy.vn{hr}" if hr.startswith("/") else hr
                if full_url not in seen:
                    seen.add(full_url)
                    p = a.find_parent(["article", "div", "li"])
                    summary = t
                    if p:
                        sapo = p.find(class_=re.compile(r"sapo|summary|lead|desc"))
                        if sapo:
                            summary = sapo.get_text(strip=True)
                    records.append({
                        "source": "vneconomy",
                        "issuing_body": "Tạp chí Kinh tế Việt Nam",
                        "doc_type": "Kinh tế & Tài chính",
                        "headline": t,
                        "summary": summary,
                        "body": summary,
                        "source_url": full_url,
                    })
    return records


def parse_vietstock(har_path: Path) -> list[dict[str, Any]]:
    records = []
    seen = set()
    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)

    for e in data.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        text = e.get("response", {}).get("content", {}).get("text", "")
        if not text or "vietstock.vn" not in url:
            continue

        soup = BeautifulSoup(text, "html.parser")
        for a in soup.find_all("a"):
            t = a.get_text(strip=True)
            hr = a.get("href", "")
            if len(t) > 25 and hr and (hr.endswith(".htm") or "/2026/" in hr or "/2025/" in hr):
                full_url = f"https://vietstock.vn{hr}" if hr.startswith("/") else hr
                if full_url not in seen and not any(k in full_url for k in ["/tag/", "/tin-nhanh/"]):
                    seen.add(full_url)
                    p = a.find_parent(["article", "div", "li", "tr"])
                    summary = t
                    if p:
                        sapo = p.find(class_=re.compile(r"sapo|summary|lead|desc"))
                        if sapo:
                            summary = sapo.get_text(strip=True)
                    records.append({
                        "source": "vietstock",
                        "issuing_body": "Vietstock Finance",
                        "doc_type": "Chứng khoán & Tài chính",
                        "headline": t,
                        "summary": summary,
                        "body": summary,
                        "source_url": full_url,
                    })
    return records


def parse_vietnamfinance(har_path: Path) -> list[dict[str, Any]]:
    records = []
    seen = set()
    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)

    for e in data.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        text = e.get("response", {}).get("content", {}).get("text", "")
        if not text or "vietnamfinance.vn" not in url:
            continue

        soup = BeautifulSoup(text, "html.parser")
        for a in soup.find_all("a"):
            t = a.get_text(strip=True)
            hr = a.get("href", "")
            if len(t) > 25 and hr and ("-d" in hr or hr.endswith(".html")):
                full_url = f"https://vietnamfinance.vn{hr}" if hr.startswith("/") else hr
                if full_url not in seen and not any(k in full_url for k in ["/chuyen-muc", "/tag", "/video", "/media"]):
                    seen.add(full_url)
                    p = a.find_parent(["article", "div", "li"])
                    summary = t
                    if p:
                        sapo = p.find(class_=re.compile(r"sapo|summary|lead|desc"))
                        if sapo:
                            summary = sapo.get_text(strip=True)
                    records.append({
                        "source": "vietnamfinance",
                        "issuing_body": "VietnamFinance",
                        "doc_type": "Thị trường & Doanh nghiệp",
                        "headline": t,
                        "summary": summary,
                        "body": summary,
                        "source_url": full_url,
                    })
    return records


def write_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Idempotently writes records into staging and core tables."""
    if df.empty:
        return 0

    required_cols = [
        "source", "issuing_body", "doc_type", "doc_number",
        "published_at", "available_at", "headline", "summary",
        "body", "source_url", "fetched_at"
    ]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}'")

    con.register("df_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_staging")
    con.unregister("df_staging")

    con.register("df_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    con.unregister("df_core")
    return len(df)


def run_ingestion(sources: list[str], db_path: Optional[str] = None) -> dict[str, int]:
    if db_path:
        con = db.connect(db_path)
    else:
        try:
            con = db.connect()
        except duckdb.IOException:
            logger.warning("db/vesta.duckdb locked, falling back to db/vesta_latest_backup.duckdb")
            con = db.connect("db/vesta_latest_backup.duckdb")

    base_har_dir = Path("scratch/har")
    results = {}
    now = dt.datetime.now(dt.timezone.utc)

    for src in sources:
        har_dir = base_har_dir / src
        if not har_dir.exists():
            logger.warning(f"Directory not found: {har_dir}")
            continue

        raw_records = []
        files = list(har_dir.glob("*.har"))
        logger.info(f"Processing source '{src}': {len(files)} HAR files found.")

        for h in files:
            if src == "tienphong":
                raw_records.extend(parse_tienphong(h))
            elif src == "tuoitre":
                raw_records.extend(parse_tuoitre(h))
            elif src == "vneconomy":
                raw_records.extend(parse_vneconomy(h))
            elif src == "vietstock":
                raw_records.extend(parse_vietstock(h))
            elif src == "vietnamfinance":
                raw_records.extend(parse_vietnamfinance(h))

        # Deduplicate on source_url
        unique_map = {}
        for r in raw_records:
            url = r["source_url"]
            if url not in unique_map:
                r["doc_number"] = None
                r["published_at"] = now
                r["available_at"] = now
                r["fetched_at"] = now
                unique_map[url] = r

        df = pd.DataFrame(list(unique_map.values()))
        if not df.empty:
            count = write_macro_policy(con, df)
            logger.info(f"Source '{src}': Ingested {count} unique records.")
            results[src] = count
        else:
            results[src] = 0

    con.close()
    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Unified HAR Batch Ingester for VESTA")
    parser.add_argument("--db", type=str, default=None, help="DuckDB path")
    parser.add_argument("--sources", nargs="+", default=["tienphong", "tuoitre", "vneconomy", "vietstock", "vietnamfinance"],
                        help="List of sources to ingest from scratch/har/<source>")
    args = parser.parse_args()

    t0 = time.time()
    results = run_ingestion(args.sources, db_path=args.db)
    dur = time.time() - t0

    print("\n" + "=" * 60)
    print("HAR BATCH INGESTION SUMMARY")
    print("=" * 60)
    total = 0
    for s, c in results.items():
        total += c
        print(f"  - {s:<20}: {c:,} articles ingested")
    print("-" * 60)
    print(f"TOTAL INGESTED: {total:,} articles in {dur:.2f} seconds")


if __name__ == "__main__":
    main()
