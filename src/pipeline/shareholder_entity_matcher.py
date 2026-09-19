"""src/pipeline/shareholder_entity_matcher.py

Shareholder and Executive Entity Disambiguation Engine for VESTA.
Resolves news articles mentioning major shareholders, key executives, founders,
or strategic institutional investors to their corresponding equity tickers.

Connects to:
- db/vesta_snapshot.duckdb (table: core.company_shareholders, 4,268 records)
- Fallback: db/vesta.duckdb (core.company_shareholders)

CRITICAL USAGE NOTE:
Per user instruction, this script provides the processing classes and lookup functions,
ready to be invoked during ETL/preprocessing, but DOES NOT automatically run batch
updates on the database tables until explicitly triggered.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

import duckdb
import pandas as pd

logger = logging.getLogger("shareholder_entity_matcher")

DEFAULT_SNAPSHOT_DB = "db/vesta_snapshot.duckdb"
DEFAULT_CANONICAL_DB = "db/vesta.duckdb"


@dataclasses.dataclass(frozen=True)
class ShareholderRecord:
    symbol: str
    shareholder_name: str
    normalized_name: str
    shares_owned: Optional[int]
    ownership_percentage: Optional[float]
    update_date: Optional[str]


@dataclasses.dataclass
class ShareholderMatch:
    symbol: str
    matched_name: str
    ownership_percentage: Optional[float]
    start_pos: int
    end_pos: int
    context_snippet: str


def _normalize_name_key(name: str) -> str:
    """Normalizes names: NFC, lowercases, removes redundant spaces and punctuation."""
    if not name or not isinstance(name, str):
        return ""
    n = unicodedata.normalize("NFC", name.strip().lower())
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _strip_accents(text: str) -> str:
    """Strips Vietnamese diacritics for fallback matching."""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


# Blacklist of generic or common corporate terms that should not be matched alone
SHAREHOLDER_NAME_STOPWORDS = frozenset({
    "viet nam", "vietnam", "tap doan", "cong ty", "ngan hang",
    "quy dau tu", "co phan", "tnhh", "nha nuoc", "scic", "chinh phu",
    "tong cong ty", "uy ban", "bo tai chinh",
})


class ShareholderEntityRegistry:
    """In-memory indexing and fast entity resolver for Vietnamese equity shareholders."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or (
            DEFAULT_SNAPSHOT_DB if os.path.exists(DEFAULT_SNAPSHOT_DB) else DEFAULT_CANONICAL_DB
        )
        self.records_by_symbol: Dict[str, List[ShareholderRecord]] = {}
        self.name_to_records: Dict[str, List[ShareholderRecord]] = {}
        self.compiled_patterns: List[Tuple[re.Pattern, List[ShareholderRecord]]] = []
        self._is_loaded = False

    def load_registry(self) -> int:
        """Loads shareholder records from DuckDB and builds regex index."""
        if not os.path.exists(self.db_path):
            logger.warning(f"Database path not found: {self.db_path}. Entity registry will remain empty.")
            return 0

        con = duckdb.connect(self.db_path, read_only=True)
        try:
            # Check table existence in core schema
            tables = [
                row[0].lower()
                for row in con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='core';"
                ).fetchall()
            ]
            if "company_shareholders" not in tables:
                logger.warning(f"Table core.company_shareholders not found in {self.db_path}.")
                return 0

            df = con.execute("""
                SELECT symbol, shareholder_name, shares_owned, ownership_percentage, update_date
                FROM core.company_shareholders
                WHERE shareholder_name IS NOT NULL AND LENGTH(TRIM(shareholder_name)) >= 4;
            """).df()
        finally:
            con.close()

        count = 0
        for _, row in df.iterrows():
            sym = str(row["symbol"]).strip().upper()
            raw_name = str(row["shareholder_name"]).strip()
            norm_name = _normalize_name_key(raw_name)

            # Skip generic stop-words or excessively short names
            if norm_name in SHAREHOLDER_NAME_STOPWORDS or len(norm_name.split()) < 2:
                continue

            record = ShareholderRecord(
                symbol=sym,
                shareholder_name=raw_name,
                normalized_name=norm_name,
                shares_owned=int(row["shares_owned"]) if pd.notnull(row["shares_owned"]) else None,
                ownership_percentage=float(row["ownership_percentage"]) if pd.notnull(row["ownership_percentage"]) else None,
                update_date=str(row["update_date"]) if pd.notnull(row["update_date"]) else None,
            )

            if sym not in self.records_by_symbol:
                self.records_by_symbol[sym] = []
            self.records_by_symbol[sym].append(record)

            if norm_name not in self.name_to_records:
                self.name_to_records[norm_name] = []
            self.name_to_records[norm_name].append(record)
            count += 1

        # Build compiled regex patterns sorted by descending length to match longest specific name first
        sorted_names = sorted(self.name_to_records.keys(), key=lambda k: len(k), reverse=True)
        self.compiled_patterns = []
        for name in sorted_names:
            # Escape regex characters
            esc = re.escape(name)
            pattern = re.compile(rf"\b{esc}\b", re.IGNORECASE)
            self.compiled_patterns.append((pattern, self.name_to_records[name]))

        self._is_loaded = True
        logger.info(f"Loaded {count} shareholder records for {len(self.records_by_symbol)} symbols from {self.db_path}.")
        return count

    def match_shareholders(self, text: str) -> List[ShareholderMatch]:
        """Scans a text snippet (headline or body) and returns all referenced shareholders & tickers."""
        if not text or not self._is_loaded:
            return []

        norm_text = _normalize_name_key(text)
        matches: List[ShareholderMatch] = []
        seen_symbols: Set[str] = set()

        for pattern, records in self.compiled_patterns:
            for m in pattern.finditer(norm_text):
                start, end = m.start(), m.end()
                snippet_start = max(0, start - 30)
                snippet_end = min(len(norm_text), end + 30)
                snippet = norm_text[snippet_start:snippet_end]

                for rec in records:
                    if rec.symbol not in seen_symbols:
                        matches.append(
                            ShareholderMatch(
                                symbol=rec.symbol,
                                matched_name=rec.shareholder_name,
                                ownership_percentage=rec.ownership_percentage,
                                start_pos=start,
                                end_pos=end,
                                context_snippet=snippet,
                            )
                        )
                        seen_symbols.add(rec.symbol)

        return matches

    def resolve_symbol_from_news(self, headline: str, body: Optional[str] = None) -> Optional[str]:
        """Resolves the most likely ticker symbol if major shareholder is mentioned in headline/body."""
        # 1. Headline has highest priority
        headline_matches = self.match_shareholders(headline)
        if headline_matches:
            # Sort by ownership percentage descending
            headline_matches.sort(key=lambda x: (x.ownership_percentage or 0.0), reverse=True)
            return headline_matches[0].symbol

        # 2. Body fallback
        if body:
            body_matches = self.match_shareholders(body[:1000])  # Scan first 1,000 characters
            if body_matches:
                body_matches.sort(key=lambda x: (x.ownership_percentage or 0.0), reverse=True)
                return body_matches[0].symbol

        return None


# Global singleton instance for easy import across crawlers and pipeline
shareholder_registry = ShareholderEntityRegistry()
