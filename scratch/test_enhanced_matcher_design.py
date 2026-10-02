import duckdb
import os
import re
import sys
import unicodedata
from typing import Dict, List, Optional, Set, Tuple
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, "src")
from pipeline.news_fundamental_entity_matcher import (
    DEFAULT_BACKUP_DB,
    DEFAULT_SNAPSHOT_DB,
    FundamentalEntity,
    EntityMatchResult,
    normalize_vietnamese_key,
)

CANONICAL_TYCOONS = {
    "phạm nhật vượng", "trần đình long", "nguyễn đăng quang", "hồ hùng anh",
    "trương gia bình", "nguyễn thị phương thảo", "đoàn nguyên đức", "bùi thành nhơn",
    "nguyễn đức tài", "nguyễn duy hưng", "phạm minh hương", "dương công minh",
    "nguyễn đức thụy", "nguyễn văn tuấn", "đặng thành tâm"
}

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

RE_CONTEXT_TICKER = re.compile(
    r"\b(?:cổ phiếu|mã cổ phiếu|mã chứng khoán|mã ck|mã)\s+([A-Z]{3})\b",
    re.IGNORECASE
)

class EnhancedFundamentalEntityRegistry:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or (
            DEFAULT_SNAPSHOT_DB if os.path.exists(DEFAULT_SNAPSHOT_DB) else DEFAULT_BACKUP_DB
        )
        self.entities_by_norm_name: Dict[str, List[FundamentalEntity]] = {}
        self.company_names_by_symbol: Dict[str, Set[str]] = {}
        self.valid_symbols: Set[str] = set()
        self._is_loaded = False

    def load_registry(self) -> int:
        con = duckdb.connect(self.db_path, read_only=True, config={"access_mode": "read_only"})
        total_loaded = 0
        try:
            # 1. Tải symbols và tên công ty
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
                
                # Kiểm tra tính hợp lệ: Nếu 1 từ mà là từ đơn âm tiết thông dụng -> BỎ QUA không cho match độc lập
                if norm_short and norm_short not in STOPWORDS_VN and norm_short not in BRAND_BLACKLIST and len(norm_short) >= 3:
                    words = norm_short.split()
                    if len(words) == 1 and norm_short in COMMON_VIETNAMESE_MONOSYLLABLES:
                        # Thêm phiên bản có tiền tố "công ty [tên]" để match an toàn
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
                        if len(words_en) == 1 and norm_en in COMMON_VIETNAMESE_MONOSYLLABLES:
                            pass
                        else:
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

            # 2. Tải Ban lãnh đạo CEO/Chủ tịch
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

            # 3. Tải Cổ đông lớn
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
            print(f"Lỗi khi đọc snapshot: {e}")
            if con:
                con.close()

        # Canonical Benchmarks
        self._inject_canonical_benchmarks()

        self._is_loaded = True
        print(f"Đã nạp {len(self.entities_by_norm_name)} cụm thực thể chuẩn hóa từ {total_loaded} bản ghi gốc.")
        return total_loaded

    def _inject_canonical_benchmarks(self) -> None:
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

    def match_entities_in_text(
        self,
        headline: str,
        body: Optional[str] = None,
        source_url: str = "",
    ) -> List[EntityMatchResult]:
        if not self._is_loaded:
            self.load_registry()

        results: List[EntityMatchResult] = []
        seen_matches: Set[Tuple[str, str, str]] = set()

        norm_hl = normalize_vietnamese_key(headline or "")
        spaced_hl = f" {norm_hl} "
        norm_body = normalize_vietnamese_key(body[:2500] if body else "")
        spaced_body = f" {norm_body} "
        full_spaced_text = f"{spaced_hl} {spaced_body}"

        # 1. Quét Contextual Tickers (ví dụ "cổ phiếu FPT", "mã HPG")
        for m in RE_CONTEXT_TICKER.finditer(f"{headline or ''} {body[:1000] if body else ''}"):
            candidate_sym = m.group(1).upper()
            if candidate_sym in self.valid_symbols:
                key = (candidate_sym, "TICKER_SYMBOL", candidate_sym)
                if key not in seen_matches:
                    results.append(
                        EntityMatchResult(
                            source_url=source_url,
                            symbol=candidate_sym,
                            entity_type="TICKER_SYMBOL",
                            entity_name=f"Cổ phiếu {candidate_sym}",
                            entity_role="Mã niêm yết",
                            company_type="Niêm yết",
                            ownership_pct=None,
                            confidence_score=0.98 if m.start() < len(headline or '') else 0.90,
                            matched_location="HEADLINE" if m.start() < len(headline or '') else "BODY",
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
            in_hl = needle in spaced_hl
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

        # 3. Quét Tên Lãnh đạo (EXECUTIVE) & Cổ đông (SHAREHOLDER) với Co-occurrence Disambiguation Guard
        for norm_name, entities in self.entities_by_norm_name.items():
            person_ents = [e for e in entities if e.entity_type in ("EXECUTIVE", "SHAREHOLDER")]
            if not person_ents:
                continue

            needle = f" {norm_name} "
            in_hl = needle in spaced_hl
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
                        has_company_cooccurrence = False
                        sym_needle = f" {ent.symbol.lower()} "
                        if sym_needle in full_spaced_text:
                            has_company_cooccurrence = True
                        else:
                            company_names = self.company_names_by_symbol.get(ent.symbol, set())
                            for cname in company_names:
                                if f" {cname} " in full_spaced_text:
                                    has_company_cooccurrence = True
                                    break

                        # Nếu KHÔNG có co-occurrence với công ty của vị lãnh đạo này,
                        # và bài báo lại có các thương hiệu công ty khác xuất hiện áp đảo -> LOẠI BỎ
                        if not has_company_cooccurrence:
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

reg = EnhancedFundamentalEntityRegistry()
reg.load_registry()

con_news = duckdb.connect("db/vesta_news.duckdb", read_only=True)
row_fpt = con_news.execute("""
    SELECT n.headline, r.body, n.source_url
    FROM core.news n
    JOIN core.news_resources r ON n.source_url = r.source_url
    WHERE n.source = 'baochinhphu' AND n.headline LIKE '%FPT%' AND n.headline LIKE '%Ba Huân%'
    LIMIT 1;
""").fetchone()
con_news.close()

if row_fpt:
    matches = reg.match_entities_in_text(row_fpt[0], row_fpt[1], row_fpt[2])
    print(f"\nHeadline: {row_fpt[0]}")
    print(f"Số lượng thực thể khớp: {len(matches)}")
    for m in matches:
        print(f" -> [{m.symbol}] {m.entity_type:15s} | {m.entity_name:25s} | Conf: {m.confidence_score:.2f} | Loc: {m.matched_location}")
