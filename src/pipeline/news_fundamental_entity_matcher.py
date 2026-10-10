"""src/pipeline/news_fundamental_entity_matcher.py

Phân hệ Ánh xạ Thực thể Tin tức sang Dữ liệu Cơ bản & Cổng Kiểm định Tính Liên quan Tài chính (F105).
(News-to-Fundamental Entity Resolution & Financial Relevance Gate).

Mục tiêu kiến trúc:
1. Sàng lọc rác & tin phi tài chính (Lifestyle, Gossip, Showbiz, Tội phạm, Tai nạn giao thông).
2. Ánh xạ thực thể tên người (Cổ đông lớn, Chủ tịch HĐQT, CEO, Ban kiểm soát) và Tên doanh nghiệp
   từ CSDL vesta_snapshot / vesta_backup sang Mã chứng khoán (Ticker Symbol).
3. Khôi phục hàng trăm nghìn bài báo vĩ mô/tổng hợp có `symbol IS NULL` sang đúng mã cổ phiếu
   được đề cập trong tiêu đề và nội dung toàn văn (Body).
4. Lưu trữ theo chuẩn 3NF vào bảng quan hệ `core.news_entity_map` và cờ phân loại mềm `core.news_relevance_meta`.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

import duckdb
import pandas as pd

logger = logging.getLogger("news_fundamental_entity_matcher")

DEFAULT_MARKET_INDEX_DB = "db/vesta_market_index.duckdb"
DEFAULT_ADMIN_INDEX_DB = "db/admin/vesta_market_index.duckdb"
DEFAULT_BACKUP_DB = "db/vesta_backup.duckdb"
DEFAULT_NEWS_DB = "db/vesta_news.duckdb"


def normalize_vietnamese_key(text: str) -> str:
    """Chuẩn hóa chuỗi tiếng Việt: NFC, chữ thường, loại bỏ dấu câu và khoảng trắng thừa."""
    if not text or not isinstance(text, str):
        return ""
    n = unicodedata.normalize("NFC", text.strip().lower())
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


@dataclasses.dataclass(frozen=True)
class FundamentalEntity:
    symbol: str
    entity_type: str  # 'SHAREHOLDER', 'CEO', 'INSPECTOR', 'COMPANY_NAME'
    entity_name: str  # Tên gốc có dấu
    normalized_name: str  # Tên chuẩn hóa không dấu câu
    entity_role: str  # Chức vụ hoặc vai trò (ví dụ: 'Chủ tịch HĐQT', 'Cổ đông lớn')
    company_type: str  # Loại hình DN (ví dụ: 'Công ty cổ phần', 'Ngân hàng')
    ownership_percentage: Optional[float] = None


@dataclasses.dataclass
class EntityMatchResult:
    source_url: str
    symbol: str
    entity_type: str
    entity_name: str
    entity_role: str
    company_type: str
    ownership_pct: Optional[float]
    confidence_score: float
    matched_location: str  # 'HEADLINE' hoặc 'BODY'


# =============================================================================
# 1. BỘ LỌC TÍNH LIÊN QUAN TÀI CHÍNH & TIN RÁC (RELEVANCE GATE)
# =============================================================================

# Từ khóa nhiễu phi tài chính (Lifestyle, Showbiz, Án mạng, Tai nạn, Thể thao, Sức khỏe đời thường)
NOISE_KEYWORDS = (
    r"showbiz|hoa hậu|người mẫu|ca sĩ|diễn viên|nghệ sĩ|scandal|hẹn hò|ly hôn|tiểu tam|ngoại tình|"
    r"tai nạn|va chạm giao thông|tử vong|chết đuối|án mạng|giết người|ma túy|trộm cắp|cướp giật|"
    r"bóng đá|ngoại hạng anh|world cup|v-league|u23|bàn thắng|huấn luyện viên|"
    r"làm đẹp|chăm sóc da|thực đơn|món ăn|ngộ độc|bệnh viện|ung thư|giảm cân|tập gym|phượt"
)

# Từ khóa cốt lõi kinh tế, thị trường tài chính và vĩ mô
FINANCE_KEYWORDS = (
    r"chứng khoán|cổ phiếu|cổ tức|lợi nhuận|doanh thu|lãi ròng|báo cáo tài chính|thua lỗ|tăng trưởng|hđqt|đại hội cổ đông|"
    r"ngân hàng|lãi suất|tín dụng|nợ xấu|tỷ giá|ngoại tệ|sbv|nhnn|trái phiếu|room tín dụng|"
    r"kinh tế|gdp|cpi|lạm phát|fdi|xuất khẩu|nhập khẩu|thương mại|vốn đầu tư|đầu tư công|"
    r"bất động sản|dự án|khu công nghiệp|thương vụ|thâu tóm|sáp nhập|ipo"
)

RE_NOISE = re.compile(rf"\b({NOISE_KEYWORDS})\b", re.IGNORECASE)
RE_FINANCE = re.compile(rf"\b({FINANCE_KEYWORDS})\b", re.IGNORECASE)


class FinancialRelevanceClassifier:
    """Phân loại bài báo theo 5 nhóm và gán cờ liên quan tài chính (Soft Tagging)."""

    @staticmethod
    def classify_article(
        headline: str,
        body: Optional[str] = None,
        has_matched_entity: bool = False,
    ) -> Tuple[str, bool, float]:
        """
        Trả về:
        - relevance_category: 'FINANCIAL_EQUITY', 'FINANCIAL_MACRO', 'IRRELEVANT_NOISE', 'AMBIGUOUS_MIXED', 'GENERAL_NEWS'
        - is_financial_relevant: True/False
        - relevance_score: float từ 0.0 đến 1.0
        """
        full_text = (headline or "") + " " + (body[:1500] if body else "")
        if not full_text.strip():
            return "GENERAL_NEWS", False, 0.0

        has_noise = bool(RE_NOISE.search(full_text))
        has_finance = bool(RE_FINANCE.search(full_text))

        # Ưu tiên 1: Đã khớp thực thể doanh nghiệp / cổ đông / mã CK -> Luôn là FINANCIAL_EQUITY
        if has_matched_entity:
            return "FINANCIAL_EQUITY", True, 1.0

        # Ưu tiên 2: Có từ khóa tài chính, không có từ khóa rác
        if has_finance and not has_noise:
            return "FINANCIAL_MACRO", True, 0.90

        # Ưu tiên 3: Có từ khóa rác, không có bất kỳ từ khóa kinh tế nào -> Rác đời sống
        if has_noise and not has_finance:
            return "IRRELEVANT_NOISE", False, 0.05

        # Ưu tiên 4: Lẫn lộn cả 2 (ví dụ: nghệ sĩ kinh doanh, hoa hậu đầu tư bất động sản)
        if has_noise and has_finance:
            return "AMBIGUOUS_MIXED", True, 0.60

        # Ưu tiên 5: Tin tức chung chung (chính sách hành chính, giao lưu xã hội)
        return "GENERAL_NEWS", False, 0.35


# =============================================================================
# 2. BỘ ĐIỀU PHỐI ÁNH XẠ THỰC THỂ CƠ BẢN (FUNDAMENTAL ENTITY RESOLVER)
# =============================================================================

STOPWORDS_VN = frozenset({
    "viet nam", "vietnam", "tap doan", "cong ty", "ngan hang",
    "co phan", "tnhh", "nha nuoc", "chinh phu", "tong cong ty",
    "bo tai chinh", "uy ban", "thi truong", "dau tu", "phat trien",
    "thuong mai", "dich vu", "san xuat", "kinh doanh", "xuat nhap khau",
    "tai chinh", "chung khoan", "bao hiem", "dia oc", "bat dong san",
})

BRAND_BLACKLIST = frozenset({
    "vietnam", "viet nam", "holdings", "group", "investment",
    "company", "corp", "corporation", "bank", "securities",
    "commercial", "joint", "stock", "international", "vn",
})

COMMON_VIETNAMESE_MONOSYLLABLES = frozenset({
    "trang", "duc", "nam", "viet", "thanh", "binh", "minh", "hai", "an", "toan",
    "phat", "tai", "dong", "tay", "hung", "tien", "ngoc", "long", "quang", "anh",
    "hoa", "phu", "thao", "nhon", "tuan", "tam", "loc", "loi", "van", "lan", "huong",
    "son", "ha", "bac", "trung", "mai", "yen", "xuan", "thu", "nhi", "dai",
})

CANONICAL_TYCOONS = {
    "phạm nhật vượng", "trần đình long", "nguyễn đăng quang", "hồ hùng anh",
    "trương gia bình", "nguyễn thị phương thảo", "đoàn nguyên đức", "bùi thành nhơn",
    "nguyễn đức tài", "nguyễn duy hưng", "phạm minh hương", "dương công minh",
    "nguyễn đức thụy", "nguyễn văn tuấn", "đặng thành tâm"
}

RE_CONTEXT_TICKER = re.compile(
    r"\b(?:cổ phiếu|mã cổ phiếu|mã chứng khoán|mã ck|mã)\s+([A-Z]{3})\b",
    re.IGNORECASE
)


class FundamentalEntityRegistry:
    """Tải và quản lý danh bạ thực thể: Cổ đông, Lãnh đạo CEO/Chủ tịch, Tên công ty & Thương hiệu."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or (
            DEFAULT_MARKET_INDEX_DB if os.path.exists(DEFAULT_MARKET_INDEX_DB) else DEFAULT_BACKUP_DB
        )
        self.entities_by_norm_name: Dict[str, List[FundamentalEntity]] = {}
        self.company_names_by_symbol: Dict[str, Set[str]] = {}
        self.valid_symbols: Set[str] = set()
        self.compiled_patterns: List[Tuple[re.Pattern, List[FundamentalEntity]]] = []
        self._is_loaded = False

    def load_registry(self) -> int:
        """Đọc dữ liệu từ DuckDB snapshot/backup và biên dịch regex index siêu tốc."""
        candidate_paths = [p for p in [self.db_path, DEFAULT_MARKET_INDEX_DB, DEFAULT_ADMIN_INDEX_DB, DEFAULT_BACKUP_DB] if os.path.exists(p)]
        con: Optional[duckdb.DuckDBPyConnection] = None

        for path in candidate_paths:
            try:
                con = duckdb.connect(path, read_only=True, config={"access_mode": "read_only"})
                logger.info(f"Kết nối thành công CSDL thực thể: {path}")
                break
            except Exception as e:
                logger.debug(f"Không thể mở {path}: {e}")

        if con is None:
            logger.warning("Không tìm thấy CSDL DuckDB thực thể, sử dụng danh mục dự phòng tối thiểu.")
            return self._load_fallback_entities()

        total_loaded = 0
        try:
            # 1. Tải Doanh nghiệp niêm yết & Thương hiệu thương mại từ core.dim_symbol
            df_sym = con.execute("""
                SELECT symbol, organ_name, en_organ_name
                FROM core.dim_symbol
                WHERE symbol IS NOT NULL;
            """).df()

            for _, row in df_sym.iterrows():
                sym = str(row["symbol"]).strip().upper()
                self.valid_symbols.add(sym)
                self.company_names_by_symbol.setdefault(sym, set())

                # A. Tên tiếng Việt rút gọn
                raw_org = str(row["organ_name"]).strip() if pd.notnull(row["organ_name"]) else ""
                short_org = re.sub(
                    r"^(công ty cổ phần|ctcp|tập đoàn|ngân hàng thương mại cổ phần|ngân hàng tmcp|tổng công ty|tct)\s*",
                    "", raw_org, flags=re.IGNORECASE
                ).strip()
                norm_short = normalize_vietnamese_key(short_org)

                if norm_short and norm_short not in STOPWORDS_VN and norm_short not in BRAND_BLACKLIST and len(norm_short) >= 3:
                    words = norm_short.split()
                    if len(words) == 1 and norm_short in COMMON_VIETNAMESE_MONOSYLLABLES:
                        # Từ đơn âm tiết tiếng Việt thông thường -> Chỉ cho phép match dạng "công ty [tên]"
                        prefixed = f"cong ty {norm_short}"
                        ent = FundamentalEntity(
                            symbol=sym,
                            entity_type="COMPANY_NAME",
                            entity_name=f"Công ty {short_org}",
                            normalized_name=prefixed,
                            entity_role="Doanh nghiệp niêm yết",
                            company_type="Niêm yết",
                            ownership_percentage=None,
                        )
                        self.entities_by_norm_name.setdefault(prefixed, []).append(ent)
                        self.company_names_by_symbol[sym].add(prefixed)
                        total_loaded += 1
                    else:
                        ent = FundamentalEntity(
                            symbol=sym,
                            entity_type="COMPANY_NAME",
                            entity_name=short_org,
                            normalized_name=norm_short,
                            entity_role="Doanh nghiệp niêm yết",
                            company_type="Niêm yết",
                            ownership_percentage=None,
                        )
                        self.entities_by_norm_name.setdefault(norm_short, []).append(ent)
                        self.company_names_by_symbol[sym].add(norm_short)
                        total_loaded += 1

                # B. Tên thương hiệu tiếng Anh / thương mại (en_organ_name: Vietcombank, Vinamilk, Techcombank...)
                raw_en = str(row["en_organ_name"]).strip() if pd.notnull(row["en_organ_name"]) else ""
                norm_en = normalize_vietnamese_key(raw_en)
                if norm_en and norm_en not in STOPWORDS_VN and norm_en not in BRAND_BLACKLIST and len(norm_en) >= 3:
                    if norm_en != norm_short:
                        words_en = norm_en.split()
                        if not (len(words_en) == 1 and norm_en in COMMON_VIETNAMESE_MONOSYLLABLES):
                            ent = FundamentalEntity(
                                symbol=sym,
                                entity_type="COMPANY_NAME",
                                entity_name=raw_en,
                                normalized_name=norm_en,
                                entity_role="Thương hiệu niêm yết",
                                company_type="Niêm yết",
                                ownership_percentage=None,
                            )
                            self.entities_by_norm_name.setdefault(norm_en, []).append(ent)
                            self.company_names_by_symbol[sym].add(norm_en)
                            total_loaded += 1

            # 2. Tải Ban lãnh đạo CEO/Chủ tịch từ core.company_overview
            df_ov = con.execute("""
                SELECT symbol, ceo_name, ceo_position, company_type
                FROM core.company_overview
                WHERE ceo_name IS NOT NULL AND length(trim(ceo_name)) >= 5;
            """).df()

            for _, row in df_ov.iterrows():
                raw_ceo = str(row["ceo_name"]).strip()
                clean_ceo = re.sub(r"^(mr\.|ms\.|mrs\.|ông|bà)\s*", "", raw_ceo, flags=re.IGNORECASE).strip()
                norm = normalize_vietnamese_key(clean_ceo)
                if len(norm.split()) >= 2 and norm not in STOPWORDS_VN and len(norm) >= 5:
                    sym = str(row["symbol"]).strip().upper()
                    ent = FundamentalEntity(
                        symbol=sym,
                        entity_type="EXECUTIVE",
                        entity_name=clean_ceo,
                        normalized_name=norm,
                        entity_role=str(row["ceo_position"]).strip() if pd.notnull(row["ceo_position"]) else "Lãnh đạo cấp cao",
                        company_type=str(row["company_type"]).strip() if pd.notnull(row["company_type"]) else "Công ty cổ phần",
                        ownership_percentage=None,
                    )
                    self.entities_by_norm_name.setdefault(norm, []).append(ent)
                    total_loaded += 1

            # 3. Tải cổ đông lớn từ core.company_shareholders
            df_sh = con.execute("""
                SELECT symbol, shareholder_name, ownership_percentage
                FROM core.company_shareholders
                WHERE shareholder_name IS NOT NULL AND length(trim(shareholder_name)) >= 5;
            """).df()

            for _, row in df_sh.iterrows():
                raw_name = str(row["shareholder_name"]).strip()
                norm = normalize_vietnamese_key(raw_name)
                if len(norm.split()) >= 2 and norm not in STOPWORDS_VN and len(norm) >= 5:
                    sym = str(row["symbol"]).strip().upper()
                    ent = FundamentalEntity(
                        symbol=sym,
                        entity_type="SHAREHOLDER",
                        entity_name=raw_name,
                        normalized_name=norm,
                        entity_role="Cổ đông lớn",
                        company_type="Doanh nghiệp niêm yết",
                        ownership_percentage=float(row["ownership_percentage"]) if pd.notnull(row["ownership_percentage"]) else None,
                    )
                    self.entities_by_norm_name.setdefault(norm, []).append(ent)
                    total_loaded += 1

            con.close()
        except Exception as e:
            logger.error(f"Lỗi khi đọc thực thể từ DuckDB: {e}")
            if con:
                con.close()

        # Bổ sung danh bạ doanh nhân nổi tiếng hàng đầu thị trường (Canonical Benchmark)
        self._inject_canonical_benchmarks()

        self._is_loaded = True
        logger.info(f"Đã biên dịch danh bạ thực thể: {len(self.entities_by_norm_name)} cụm từ từ {total_loaded} bản ghi gốc.")
        return total_loaded

    def _inject_canonical_benchmarks(self) -> None:
        """Nạp các tên tuổi lớn nhất thị trường chứng khoán Việt Nam đảm bảo 100% không bị bỏ sót."""
        canonical = [
            ("VIC", "Phạm Nhật Vượng", "Chủ tịch HĐQT", "Tập đoàn Đa ngành", 17.85),
            ("HPG", "Trần Đình Long", "Chủ tịch HĐQT", "Tập đoàn Thép", 25.80),
            ("MSN", "Nguyễn Đăng Quang", "Chủ tịch HĐQT", "Hàng tiêu dùng & Bán lẻ", 25.50),
            ("TCB", "Hồ Hùng Anh", "Chủ tịch HĐQT", "Ngân hàng", 1.12),
            ("FPT", "Trương Gia Bình", "Chủ tịch HĐQT", "Công nghệ thông tin", 6.88),
            ("VJC", "Nguyễn Thị Phương Thảo", "Chủ tịch HĐQT", "Hàng không", 8.76),
            ("HDB", "Nguyễn Thị Phương Thảo", "Phó Chủ tịch HĐQT", "Ngân hàng", 3.73),
            ("HAG", "Đoàn Nguyên Đức", "Chủ tịch HĐQT", "Nông nghiệp", 34.50),
            ("NVL", "Bùi Thành Nhơn", "Chủ tịch HĐQT", "Bất động sản", 4.96),
            ("MWG", "Nguyễn Đức Tài", "Chủ tịch HĐQT", "Bán lẻ", 2.41),
            ("SSI", "Nguyễn Duy Hưng", "Chủ tịch HĐQT", "Chứng khoán", 1.05),
            ("VND", "Phạm Minh Hương", "Chủ tịch HĐQT", "Chứng khoán", 2.95),
            ("STB", "Dương Công Minh", "Chủ tịch HĐQT", "Ngân hàng", 3.32),
            ("LPB", "Nguyễn Đức Thụy", "Chủ tịch HĐQT", "Ngân hàng", 2.80),
            ("GEX", "Nguyễn Văn Tuấn", "Tổng Giám đốc", "Thiết bị điện & Hạ tầng", 23.76),
            ("KBC", "Đặng Thành Tâm", "Chủ tịch HĐQT", "Bất động sản công nghiệp", 18.06),
        ]
        for sym, name, role, ctype, pct in canonical:
            norm = normalize_vietnamese_key(name)
            ent = FundamentalEntity(
                symbol=sym,
                entity_type="EXECUTIVE" if "Chủ tịch" in role or "Tổng" in role else "SHAREHOLDER",
                entity_name=name,
                normalized_name=norm,
                entity_role=role,
                company_type=ctype,
                ownership_percentage=pct,
            )
            self.entities_by_norm_name.setdefault(norm, []).append(ent)
            self.company_names_by_symbol.setdefault(sym, set()).add(norm)
            self.valid_symbols.add(sym)

    def _load_fallback_entities(self) -> int:
        self._inject_canonical_benchmarks()
        self._is_loaded = True
        return len(self.entities_by_norm_name)

    def match_entities_in_text(
        self,
        headline: str,
        body: Optional[str] = None,
        source_url: str = "",
    ) -> List[EntityMatchResult]:
        """Quét và trích xuất thực thể với Co-occurrence Disambiguation Guard chống va chạm đa nghĩa."""
        if not self._is_loaded:
            self.load_registry()

        results: List[EntityMatchResult] = []
        seen_matches: Set[Tuple[str, str, str]] = set()

        norm_headline = normalize_vietnamese_key(headline or "")
        spaced_headline = f" {norm_headline} "
        norm_body = normalize_vietnamese_key(body[:2500] if body else "")
        spaced_body = f" {norm_body} "
        full_spaced_text = f"{spaced_headline} {spaced_body}"

        # 1. Quét Contextual Tickers (ví dụ "cổ phiếu FPT", "mã HPG")
        full_raw_text = f"{headline or ''} {body[:1500] if body else ''}"
        for m in RE_CONTEXT_TICKER.finditer(full_raw_text):
            candidate_sym = m.group(1).upper()
            if candidate_sym in self.valid_symbols:
                key = (candidate_sym, "TICKER_SYMBOL", candidate_sym)
                if key not in seen_matches:
                    is_in_hl = m.start() < len(headline or "")
                    results.append(
                        EntityMatchResult(
                            source_url=source_url,
                            symbol=candidate_sym,
                            entity_type="TICKER_SYMBOL",
                            entity_name=f"Cổ phiếu {candidate_sym}",
                            entity_role="Mã niêm yết",
                            company_type="Niêm yết",
                            ownership_pct=None,
                            confidence_score=0.98 if is_in_hl else 0.90,
                            matched_location="HEADLINE" if is_in_hl else "BODY",
                        )
                    )
                    seen_matches.add(key)

        # 2. Quét Tên Doanh nghiệp & Thương hiệu (COMPANY_NAME)
        confirmed_company_symbols: Set[str] = {r.symbol for r in results}

        for norm_name, entities in self.entities_by_norm_name.items():
            company_ents = [e for e in entities if e.entity_type == "COMPANY_NAME"]
            if not company_ents:
                continue

            needle = f" {norm_name} "
            in_hl = needle in spaced_headline
            in_body = needle in spaced_body if not in_hl else False

            if in_hl or in_body:
                for ent in company_ents:
                    key = (ent.symbol, ent.entity_type, ent.entity_name)
                    if key not in seen_matches:
                        results.append(
                            EntityMatchResult(
                                source_url=source_url,
                                symbol=ent.symbol,
                                entity_type=ent.entity_type,
                                entity_name=ent.entity_name,
                                entity_role=ent.entity_role,
                                company_type=ent.company_type,
                                ownership_pct=ent.ownership_percentage,
                                confidence_score=0.95 if in_hl else 0.85,
                                matched_location="HEADLINE" if in_hl else "BODY",
                            )
                        )
                        seen_matches.add(key)
                        confirmed_company_symbols.add(ent.symbol)

        # 3. Quét Tên Lãnh đạo (EXECUTIVE) & Cổ đông (SHAREHOLDER) với Co-occurrence Guard
        for norm_name, entities in self.entities_by_norm_name.items():
            person_ents = [e for e in entities if e.entity_type in ("EXECUTIVE", "SHAREHOLDER")]
            if not person_ents:
                continue

            needle = f" {norm_name} "
            in_hl = needle in spaced_headline
            in_body = needle in spaced_body if not in_hl else False

            if in_hl or in_body:
                is_canonical = norm_name in CANONICAL_TYCOONS

                for ent in person_ents:
                    key = (ent.symbol, ent.entity_type, ent.entity_name)
                    if key in seen_matches:
                        continue

                    # CO-OCCURRENCE DISAMBIGUATION GUARD:
                    if is_canonical:
                        conf = 0.95 if in_hl else 0.85
                    else:
                        has_cooccurrence = False
                        sym_needle = f" {ent.symbol.lower()} "
                        if sym_needle in full_spaced_text:
                            has_cooccurrence = True
                        else:
                            company_names = self.company_names_by_symbol.get(ent.symbol, set())
                            for cname in company_names:
                                if f" {cname} " in full_spaced_text:
                                    has_cooccurrence = True
                                    break

                        # Nếu KHÔNG có co-occurrence với công ty của vị lãnh đạo này,
                        # mà bài báo lại có các thương hiệu công ty khác xuất hiện áp đảo -> LOẠI BỎ
                        if not has_cooccurrence:
                            if len(confirmed_company_symbols) > 0 and ent.symbol not in confirmed_company_symbols:
                                continue
                            conf = 0.60
                        else:
                            conf = 0.90 if in_hl else 0.80

                    results.append(
                        EntityMatchResult(
                            source_url=source_url,
                            symbol=ent.symbol,
                            entity_type=ent.entity_type,
                            entity_name=ent.entity_name,
                            entity_role=ent.entity_role,
                            company_type=ent.company_type,
                            ownership_pct=ent.ownership_percentage,
                            confidence_score=conf,
                            matched_location="HEADLINE" if in_hl else "BODY",
                        )
                    )
                    seen_matches.add(key)

        return results


# =============================================================================
# 3. QUẢN LÝ SCHEMA DDL & PERSISTENCE HELPER
# =============================================================================

DDL_NEWS_ENTITY_MAP = """
CREATE TABLE IF NOT EXISTS core.news_entity_map (
    source_url VARCHAR,
    symbol VARCHAR,
    entity_type VARCHAR,        -- 'SHAREHOLDER', 'EXECUTIVE', 'COMPANY_NAME'
    entity_name VARCHAR,
    entity_role VARCHAR,
    company_type VARCHAR,
    ownership_pct DOUBLE,
    confidence_score DOUBLE,
    matched_location VARCHAR,   -- 'HEADLINE', 'BODY'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_url, symbol, entity_type, entity_name)
);
"""

DDL_NEWS_RELEVANCE_META = """
CREATE TABLE IF NOT EXISTS core.news_relevance_meta (
    source_url VARCHAR PRIMARY KEY,
    relevance_category VARCHAR, -- 'FINANCIAL_EQUITY', 'FINANCIAL_MACRO', 'IRRELEVANT_NOISE', 'AMBIGUOUS_MIXED', 'GENERAL_NEWS'
    is_financial_relevant BOOLEAN,
    relevance_score DOUBLE,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_entity_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Tạo bảng quan hệ thực thể và siêu dữ liệu liên quan nếu chưa tồn tại."""
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute(DDL_NEWS_ENTITY_MAP)
    con.execute(DDL_NEWS_RELEVANCE_META)
    logger.info("Đã khởi tạo/xác nhận cấu trúc bảng core.news_entity_map & core.news_relevance_meta.")


# Singleton toàn cục
global_entity_registry = FundamentalEntityRegistry()
global_relevance_classifier = FinancialRelevanceClassifier()
