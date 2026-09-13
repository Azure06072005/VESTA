"""F004d: Sector-level news-to-symbol matcher & taxonomy engine.

File: src/pipeline/sector_news_matcher.py
Description:
    Implements 2-tier fail-closed matching for sector-level financial news:
    - Tier A: Explicit sector trigger with required market context anchors
              (e.g., 'cổ phiếu', 'nhóm ngành', 'rổ cổ phiếu', 'các mã').
              Guarantees zero false positives against civil/administrative headlines
              (e.g. 'Bộ Xây dựng ban hành thông tư...', 'Bất động sản Hà Nội...').
    - Tier B: Multi-symbol company co-occurrence trigger:
              Detects if >= 2 symbols from the exact same sector appear together
              in a market headline.
    - Database integration: Writes to core.sector_news_signal with exact audit provenance.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import duckdb

logger = logging.getLogger("sector_news_matcher")

# =====================================================================
# TIER A: MARKET CONTEXT ANCHOR PATTERNS (Fail-closed Gate)
# Headlines MUST contain a market/equity anchor to trigger sector matching.
# Pure economic/administrative news without market context are rejected.
# =====================================================================
MARKET_ANCHOR_PATTERN = re.compile(
    r"\b(?i:"
    r"cổ\s+phiếu|"
    r"nhóm\s+(?:cổ\s+phiếu|ngành)|"
    r"nhóm\s+ngành|"
    r"rổ\s+(?:cổ\s+phiếu|chỉ\s+số)|"
    r"các\s+mã(?:\s+(?:chứng\s+khoán|CK|cổ\s+phiếu))?|"
    r"mã\s+(?:chứng\s+khoán|CK|cổ\s+phiếu)|"
    r"dòng\s+(?:tiền|cổ\s+phiếu)|"
    r"sóng\s+(?:ngành|cổ\s+phiếu)"
    r")\b"
)

# Negative filter for purely civil / administrative policy news
ADMIN_POLICY_PATTERNS = re.compile(
    r"\b(?i:"
    r"bộ\s+xây\s+dựng|"
    r"bộ\s+tài\s+chính|"
    r"ngân\s+hàng\s+nhà\s+nước|"
    r"thông\s+tư|"
    r"nghị\s+định|"
    r"chính\s+sách\s+thuế|"
    r"giá\s+thuê(?:\s+văn\s+phòng)?|"
    r"nhà\s+ở\s+xã\s+hội"
    r")\b"
)

# BUGFIX (2026-09-13): the admin-policy override used to hardcode a check
# for the single literal substring "cổ phiếu", but MARKET_ANCHOR_PATTERN
# accepts several other anchors ("nhóm ngành", "dòng tiền", "rổ cổ phiếu",
# "sóng ngành", "các mã", "mã chứng khoán"). A real headline like "Nhóm
# ngành bất động sản hưởng lợi từ nghị định gỡ vướng pháp lý" passed the
# market-anchor gate but was then incorrectly dropped by the admin-override
# check -- a false negative (recall loss), not a false positive, but real.
MARKET_ANCHOR_OVERRIDE_KEYWORDS: tuple[str, ...] = (
    "cổ phiếu", "nhóm ngành", "dòng tiền", "rổ cổ phiếu",
    "sóng ngành", "các mã", "mã chứng khoán",
)

# =====================================================================
# SECTOR TAXONOMY & KEYWORD PATTERNS (Derived from Vietstock 25 Sectors)
# =====================================================================
SECTOR_TAXONOMY_DICT: Dict[int, Dict[str, Any]] = {
    3: {
        "name": "Bất động sản",
        "pattern": re.compile(r"\b(?i:bất\s+động\s+sản|địa\s+ốc|bđs|nhà\s+đất|đô\s+thị|bất\s+động\s+sản\s+khu\s+công\s+nghiệp)\b"),
        "keywords": ["bất động sản", "địa ốc", "bđs", "nhà đất", "đô thị"]
    },
    5: {
        "name": "Chứng khoán",
        "pattern": re.compile(r"\b(?i:chứng\s+khoán|ctck|môi\s+giới\s+chứng\s+khoán|công\s+ty\s+chứng\s+khoán)\b"),
        "keywords": ["chứng khoán", "ctck", "môi giới chứng khoán", "công ty chứng khoán"]
    },
    11: {
        "name": "Ngân hàng",
        "pattern": re.compile(r"\b(?i:ngân\s+hàng|nhà\s+băng|ngân\s+hàng\s+thương\s+mại|tín\s+dụng)\b"),
        "keywords": ["ngân hàng", "nhà băng", "ngân hàng thương mại", "tín dụng"]
    },
    21: {
        "name": "Vật liệu xây dựng",
        "pattern": re.compile(r"\b(?i:thép|kim\s+loại|vật\s+liệu\s+xây\s+dựng|xi\s+măng|tôn\s+mạ)\b"),
        "keywords": ["thép", "kim loại", "vật liệu xây dựng", "xi măng", "tôn mạ"]
    },
    24: {
        "name": "Xây dựng",
        "pattern": re.compile(r"\b(?i:xây\s+dựng|xây\s+lắp|nhà\s+thầu|hạ\s+tầng|đầu\s+tư\s+công)\b"),
        "keywords": ["xây dựng", "xây lắp", "nhà thầu", "hạ tầng", "đầu tư công"]
    },
    10: {
        "name": "Khai khoáng",
        "pattern": re.compile(r"\b(?i:dầu\s+khí|khai\s+khoáng|than|xăng\s+dầu|khí\s+đốt)\b"),
        "keywords": ["dầu khí", "khai khoáng", "than", "xăng dầu", "khí đốt"]
    },
    18: {
        "name": "SX Nhựa - Hóa chất",
        "pattern": re.compile(r"\b(?i:hóa\s+chất|phân\s+bón|nhựa|phốt\s+pho|đạm)\b"),
        "keywords": ["hóa chất", "phân bón", "nhựa", "phốt pho", "đạm"]
    },
    6: {
        "name": "Công nghệ và thông tin",
        "pattern": re.compile(r"\b(?i:công\s+nghệ\s+thông\s+tin|phần\s+mềm|viễn\s+thông|cntt|chuyển\s+đổi\s+số)\b"),
        "keywords": ["công nghệ thông tin", "phần mềm", "viễn thông", "cntt", "chuyển đổi số"]
    },
    7: {
        "name": "Bán lẻ",
        "pattern": re.compile(r"\b(?i:bán\s+lẻ|chuỗi\s+bán\s+lẻ|siêu\s+thị)\b"),
        "keywords": ["bán lẻ", "chuỗi bán lẻ", "siêu thị"]
    },
    19: {
        "name": "Thực phẩm - Đồ uống",
        "pattern": re.compile(r"\b(?i:thực\s+phẩm|đồ\s+uống|sữa|bia|thịt\s+lợn|đường|chăn\s+nuôi)\b"),
        "keywords": ["thực phẩm", "đồ uống", "sữa", "bia", "thịt lợn", "đường", "chăn nuôi"]
    },
    20: {
        "name": "Chế biến Thủy sản",
        "pattern": re.compile(r"\b(?i:thủy\s+sản|thủy\s+hải\s+sản|tôm|cá\s+tra|xuất\s+khẩu\s+thủy\s+sản)\b"),
        "keywords": ["thủy sản", "thủy hải sản", "tôm", "cá tra", "xuất khẩu thủy sản"]
    },
    23: {
        "name": "Vận tải - kho bãi",
        "pattern": re.compile(r"\b(?i:vận\s+tải|kho\s+bãi|logistics|cảng\s+biển|vận\s+tải\s+biển|hàng\s+không)\b"),
        "keywords": ["vận tải", "kho bãi", "logistics", "cảng biển", "vận tải biển", "hàng không"]
    },
    22: {
        "name": "Tiện ích",
        "pattern": re.compile(r"\b(?i:tiện\s+ích|năng\s+lượng|điện|nước|cấp\s+thoát\s+nước|năng\s+lượng\s+tái\s+tạo)\b"),
        "keywords": ["tiện ích", "năng lượng", "điện", "nước", "cấp thoát nước", "năng lượng tái tạo"]
    },
    8: {
        "name": "Chăm sóc sức khỏe",
        "pattern": re.compile(r"\b(?i:chăm\s+sóc\s+sức\s+khỏe|dược\s+phẩm|y\s+tế|thuốc)\b"),
        "keywords": ["chăm sóc sức khỏe", "dược phẩm", "y tế", "thuốc"]
    },
    2: {
        "name": "Bảo hiểm",
        "pattern": re.compile(r"\b(?i:bảo\s+hiểm|phi\s+nhân\s+thọ)\b"),
        "keywords": ["bảo hiểm", "phi nhân thọ"]
    },
    16: {
        "name": "SX Hàng gia dụng",
        "pattern": re.compile(r"\b(?i:dệt\s+may|may\s+mặc|hàng\s+gia\s+dụng|sợi)\b"),
        "keywords": ["dệt may", "may mặc", "hàng gia dụng", "sợi"]
    },
    17: {
        "name": "Sản phẩm cao su",
        "pattern": re.compile(r"\b(?i:cao\s+su|mủ\s+cao\s+su|săm\s+lốp)\b"),
        "keywords": ["cao su", "mủ cao su", "săm lốp"]
    },
    12: {
        "name": "Nông - Lâm - Ngư",
        "pattern": re.compile(r"\b(?i:nông\s+nghiệp|lâm\s+sản|gỗ|trồng\s+trọt)\b"),
        "keywords": ["nông nghiệp", "lâm sản", "gỗ", "trồng trọt"]
    },
    25: {
        "name": "Dịch vụ lưu trú, ăn uống, giải trí",
        "pattern": re.compile(r"\b(?i:du\s+lịch|khách\s+sạn|nghỉ\s+dưỡng|giải\s+trí)\b"),
        "keywords": ["du lịch", "khách sạn", "nghỉ dưỡng", "giải trí"]
    }
}


def match_sector_tier_a(title: str, url: str = "") -> List[Dict[str, Any]]:
    """Tier A matcher: Requires explicit market/equity anchor words before matching sector keywords.
    Fails closed (returns empty list) if:
    1. No market context anchor is found in title.
    2. The title is purely administrative policy (without stock context).
    """
    if not title:
        return []

    # 1. Must pass Market Context Gate
    m_anchor = MARKET_ANCHOR_PATTERN.search(title)
    if not m_anchor:
        return []
    
    # Check if this is administrative news without explicit stock context
    title_lower = title.lower()
    if ADMIN_POLICY_PATTERNS.search(title) and not any(
        kw in title_lower for kw in MARKET_ANCHOR_OVERRIDE_KEYWORDS
    ):
        return []

    anchor_text = m_anchor.group(0)
    matched_results: List[Dict[str, Any]] = []

    # 2. Check each sector pattern
    for sector_id, sec_data in SECTOR_TAXONOMY_DICT.items():
        m_sec = sec_data["pattern"].search(title)
        if m_sec:
            matched_results.append({
                "source_url": url,
                "sector_id": sector_id,
                "sector_name": sec_data["name"],
                "matched_keyword": m_sec.group(0),
                "market_anchor": anchor_text,
                "match_tier": "explicit_sector_trigger",
            })

    return matched_results


def match_sector_tier_b(
    title: str,
    symbol_to_sector: Dict[str, Tuple[int, str]],
    valid_symbols: Set[str],
    url: str = ""
) -> List[Dict[str, Any]]:
    """Tier B matcher: Co-occurrence of >= 2 ticker symbols belonging to the same sector.
    Returns the sector match if and only if at least 2 distinct symbols belonging to
    the SAME sector are found in the headline.
    """
    if not title:
        return []

    # Extract all uppercase candidate tokens (length 3-4)
    tokens = re.findall(r"\b[A-Z0-9]{3,4}\b", title)
    matched_syms = [tok for tok in tokens if tok in valid_symbols and tok in symbol_to_sector]

    if len(matched_syms) < 2:
        return []

    # Group by sector_id
    sector_counts: Dict[int, List[str]] = {}
    for sym in set(matched_syms):
        s_id, _ = symbol_to_sector[sym]
        sector_counts.setdefault(s_id, []).append(sym)

    results: List[Dict[str, Any]] = []
    for s_id, sym_list in sector_counts.items():
        if len(sym_list) >= 2:
            s_name = symbol_to_sector[sym_list[0]][1]
            results.append({
                "source_url": url,
                "sector_id": s_id,
                "sector_name": s_name,
                "matched_keyword": ", ".join(sym_list),
                "market_anchor": "company_list_cooccurrence",
                "match_tier": "company_list_mention",
            })

    return results


def load_symbol_sector_map(con: duckdb.DuckDBPyConnection) -> Tuple[Dict[str, Tuple[int, str]], Set[str]]:
    """Loads symbol -> (sector_id, sector_name) lookup mapping from core.dim_symbol_sector."""
    try:
        rows = con.execute("SELECT symbol, sector_id, sector_name FROM core.dim_symbol_sector").fetchall()
        mapping = {r[0]: (int(r[1]), r[2]) for r in rows}
        return mapping, set(mapping.keys())
    except Exception as e:
        logger.warning(f"Could not load core.dim_symbol_sector: {e}")
        return {}, set()
