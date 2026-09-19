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


# Canonical fallback dictionary of key Vietnamese corporate executives and major shareholders
# Used when DuckDB is locked by another process or database snapshot is updating
CANONICAL_FALLBACK_SHAREHOLDERS: List[Tuple[str, str, float]] = [
    ("ACB", "Trần Hùng Huy", 3.42),
    ("ACB", "Tran Hung Huy", 3.42),
    ("VIC", "Phạm Nhật Vượng", 17.85),
    ("VIC", "Pham Nhat Vuong", 17.85),
    ("VHM", "Phạm Nhật Vượng", 0.0),
    ("VRE", "Phạm Nhật Vượng", 0.0),
    ("HAG", "Đoàn Nguyên Đức", 34.50),
    ("HAG", "Doan Nguyen Duc", 34.50),
    ("HAG", "bầu Đức", 34.50),
    ("HAG", "bau Duc", 34.50),
    ("HPG", "Trần Đình Long", 25.80),
    ("HPG", "Tran Dinh Long", 25.80),
    ("HPG", "bầu Long", 25.80),
    ("FPT", "Trương Gia Bình", 6.88),
    ("FPT", "Truong Gia Binh", 6.88),
    ("MSN", "Nguyễn Đăng Quang", 25.50),
    ("MSN", "Nguyen Dang Quang", 25.50),
    ("TCB", "Hồ Hùng Anh", 1.12),
    ("TCB", "Ho Hung Anh", 1.12),
    ("VJC", "Nguyễn Thị Phương Thảo", 8.76),
    ("VJC", "Nguyen Thi Phuong Thao", 8.76),
    ("HDB", "Nguyễn Thị Phương Thảo", 3.73),
    ("MWG", "Nguyễn Đức Tài", 2.41),
    ("MWG", "Nguyen Duc Tai", 2.41),
    ("KBC", "Đặng Thành Tâm", 14.81),
    ("KBC", "Dang Thanh Tam", 14.81),
    ("SSI", "Nguyễn Duy Hưng", 1.05),
    ("SSI", "Nguyen Duy Hung", 1.05),
    ("VND", "Phạm Minh Hương", 2.95),
    ("VND", "Pham Minh Huong", 2.95),
    ("STB", "Dương Công Minh", 3.32),
    ("STB", "Duong Cong Minh", 3.32),
    ("LPB", "Nguyễn Đức Thụy", 2.80),
    ("LPB", "bầu Thụy", 2.80),
    ("GEX", "Nguyễn Văn Tuấn", 23.76),
    ("GEX", "Tuấn mượt", 23.76),
    ("NVL", "Bùi Thành Nhơn", 4.96),
    ("NVL", "Bui Thanh Nhon", 4.96),
    ("PDR", "Nguyễn Văn Đạt", 38.34),
    ("DIG", "Nguyễn Thiện Tuấn", 8.12),
    ("DXG", "Lương Trí Thìn", 17.15),
    ("VNM", "SCIC", 36.00),
    ("VCB", "Dragon Capital", 5.10),
]


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
        """Loads shareholder records from DuckDB and builds regex index with canonical fallback."""
        df: Optional[pd.DataFrame] = None

        # 1. Attempt DuckDB load if file exists and is accessible
        candidate_paths = [p for p in [self.db_path, DEFAULT_SNAPSHOT_DB, DEFAULT_CANONICAL_DB] if os.path.exists(p)]
        for path in candidate_paths:
            try:
                con = duckdb.connect(path, read_only=True, config={"access_mode": "read_only"})
                tables = [
                    row[0].lower()
                    for row in con.execute(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema='core';"
                    ).fetchall()
                ]
                if "company_shareholders" in tables:
                    res_df = con.execute("""
                        SELECT symbol, shareholder_name, shares_owned, ownership_percentage, update_date
                        FROM core.company_shareholders
                        WHERE shareholder_name IS NOT NULL AND LENGTH(TRIM(shareholder_name)) >= 4;
                    """).df()
                    con.close()
                    if len(res_df) > 0:
                        df = res_df
                        logger.info(f"Loaded {len(df)} shareholder records from {path}.")
                        break
                con.close()
            except Exception as e:
                logger.debug(f"Could not read shareholders from {path} ({e}). Proceeding to fallback...")

        self.records_by_symbol.clear()
        self.name_to_records.clear()
        count = 0

        # Process DuckDB rows if available
        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                sym = str(row["symbol"]).strip().upper()
                raw_name = str(row["shareholder_name"]).strip()
                norm_name = _normalize_name_key(raw_name)

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

        # Populate canonical fallbacks (vital executive names & market aliases)
        for sym, name, pct in CANONICAL_FALLBACK_SHAREHOLDERS:
            norm_name = _normalize_name_key(name)
            if norm_name in self.name_to_records:
                continue
            rec = ShareholderRecord(
                symbol=sym,
                shareholder_name=name,
                normalized_name=norm_name,
                shares_owned=None,
                ownership_percentage=pct,
                update_date=None,
            )
            if sym not in self.records_by_symbol:
                self.records_by_symbol[sym] = []
            self.records_by_symbol[sym].append(rec)
            self.name_to_records[norm_name] = [rec]
            count += 1

        # Build compiled regex patterns sorted by descending length to match longest specific name first
        sorted_names = sorted(self.name_to_records.keys(), key=lambda k: len(k), reverse=True)
        self.compiled_patterns = []
        for name in sorted_names:
            esc = re.escape(name)
            pattern = re.compile(rf"\b{esc}\b", re.IGNORECASE)
            self.compiled_patterns.append((pattern, self.name_to_records[name]))

        self._is_loaded = True
        logger.info(f"Initialized shareholder registry with {count} records across {len(self.records_by_symbol)} symbols.")
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
