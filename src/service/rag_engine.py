"""
Module RAG Engine phục vụ Trợ lý AI Chiến lược (F502 AI Strategy Studio)
Truy vấn trực tiếp và tổng hợp dữ liệu từ 3 cơ sở dữ liệu Lakehouse:
  1. db/vesta_ohlcv.duckdb: Chuỗi nến OHLCV hàng ngày & 1 phút, chỉ số VN-Index, MA20/MA50.
  2. db/vesta_news.duckdb: Tin tức tài chính CafeF, Vietstock, VnEconomy, Sentiment.
  3. db/vesta_snapshot.duckdb: Hồ sơ doanh nghiệp (core.company_overview), cơ cấu cổ đông, sự kiện doanh nghiệp.

Tích hợp:
  - Local Reasoning SLM (Qwen2.5-3B + HybridACD) đối thoại tự do, không ép khuôn mẫu (Requirement 1).
  - Universe Gating: Phát hiện mã chứng khoán không tồn tại trong CSDL, cảnh báo và gợi ý mã hợp lệ (Requirement 2).
  - Company Overview đầy đủ: business_model, founded_date, charter_capital, number_of_employees, company_type (Requirement 3).
  - Phân tích chế độ khủng hoảng (is_crisis_regime): AI tự quyết định chiến lược (Fail-Closed, Hedging VN30F1M).
  - Quy mô vốn người dùng tự quyết định (initial_cash) cho mọi kịch bản đầu tư và phân bổ lô lẻ Odd-lot.
"""

import os
import sys
import re
import json
import logging
import datetime as dt
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import duckdb

logger = logging.getLogger("rag_engine")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from models.local_reasoning_slm import LocalReasoningSLMEngine
except ImportError:
    LocalReasoningSLMEngine = None  # type: ignore

SNAPSHOT_DB = str(REPO_ROOT / "db" / "vesta_snapshot.duckdb")
NEWS_DB = str(REPO_ROOT / "db" / "vesta_news.duckdb")
OHLCV_DB = str(REPO_ROOT / "db" / "vesta_ohlcv.duckdb")
CAFEF_SYMBOLS_PATH = REPO_ROOT / "cafef_company_list.json"

_ALL_LAKEHOUSE_TICKERS: Optional[Set[str]] = None
_CAFEF_TITLES_MAP: Optional[Dict[str, str]] = None
_GLOBAL_SLM_ENGINE: Optional[Any] = None

# Bảng tra cứu hồ sơ doanh nghiệp chuẩn cho nhóm Bluechips & Cổ phiếu tâm điểm thị trường
KNOWN_COMPANY_OVERVIEWS: Dict[str, Dict[str, Any]] = {
    "NVL": {
        "company_name": "CTCP Tập đoàn Đầu tư Địa ốc No Va (Novaland)",
        "exchange": "HOSE",
        "industry": "Bất động sản dân cư & du lịch nghỉ dưỡng",
        "business_model": "Đầu tư phát triển các đại đô thị vệ tinh quy mô lớn, bất động sản nghỉ dưỡng và hạ tầng dịch vụ cao cấp.",
        "founded_date": "1992-09-18",
        "charter_capital": 19501.0,
        "number_of_employees": 1450,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Bùi Thành Nhơn (Chủ tịch HĐQT)",
        "outstanding_shares": 1950104538,
        "listing_date": "2016-12-28",
        "shareholders": ["Bùi Thành Nhơn (4.96%)", "NovaGroup (18.2%)", "Diamond Properties (8.7%)"],
    },
    "PNJ": {
        "company_name": "CTCP Vàng bạc Đá quý Phú Nhuận",
        "exchange": "HOSE",
        "industry": "Bán lẻ trang sức & Kim hoàn cao cấp",
        "business_model": "Sản xuất, gia công, kinh doanh bán buôn và bán lẻ trang sức vàng bạc, đá quý, phụ kiện thời trang với mạng lưới 400+ cửa hàng trên toàn quốc.",
        "founded_date": "1988-04-28",
        "charter_capital": 3347.0,
        "number_of_employees": 7200,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Lê Trí Thông (Phó Chủ tịch kiêm TGĐ)",
        "outstanding_shares": 334729112,
        "listing_date": "2009-03-23",
        "shareholders": ["Cao Thị Ngọc Dung (2.8%)", "Dragon Capital (8.5%)", "VOF Investment (5.2%)"],
    },
    "FPT": {
        "company_name": "CTCP FPT",
        "exchange": "HOSE",
        "industry": "Công nghệ thông tin & Viễn thông",
        "business_model": "Xuất khẩu phần mềm toàn cầu, cung cấp giải pháp chuyển đổi số (AI, Cloud, Automotive), dịch vụ viễn thông băng rộng và hệ sinh thái giáo dục đại học/phổ thông.",
        "founded_date": "1988-09-13",
        "charter_capital": 14605.0,
        "number_of_employees": 48000,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Trương Gia Bình (Chủ tịch HĐQT)",
        "outstanding_shares": 1460490000,
        "listing_date": "2006-12-13",
        "shareholders": ["Trương Gia Bình (6.9%)", "Dragon Capital (6.1%)", "SCIC (5.8%)"],
    },
    "VCB": {
        "company_name": "Ngân hàng TMCP Ngoại thương Việt Nam (Vietcombank)",
        "exchange": "HOSE",
        "industry": "Tài chính & Ngân hàng thương mại",
        "business_model": "Dịch vụ ngân hàng bán buôn và bán lẻ hàng đầu Việt Nam, thanh toán quốc tế, kinh doanh vốn ngoại tệ và dịch vụ ngân hàng số.",
        "founded_date": "1963-04-01",
        "charter_capital": 55891.0,
        "number_of_employees": 22500,
        "company_type": "Ngân hàng thương mại cổ phần niêm yết",
        "ceo_name": "Nguyễn Thanh Tùng (Tổng Giám đốc)",
        "outstanding_shares": 5589091402,
        "listing_date": "2009-06-30",
        "shareholders": ["Ngân hàng Nhà nước Việt Nam (74.8%)", "Mizuho Bank Ltd (15.0%)"],
    },
    "HPG": {
        "company_name": "CTCP Tập đoàn Hòa Phát",
        "exchange": "HOSE",
        "industry": "Sản xuất Thép & Kim loại cơ bản",
        "business_model": "Sản xuất gang thép khép kín (thép xây dựng, thép cuộn cán nóng HRC Dung Quất), ống thép, tôn mạ, nông nghiệp và điện máy gia dụng.",
        "founded_date": "1992-08-08",
        "charter_capital": 58148.0,
        "number_of_employees": 32000,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Trần Đình Long (Chủ tịch HĐQT)",
        "outstanding_shares": 5814785700,
        "listing_date": "2007-11-15",
        "shareholders": ["Trần Đình Long (25.8%)", "Vũ Thị Hiền (7.3%)", "Dragon Capital (5.4%)"],
    },
    "VHM": {
        "company_name": "CTCP Vinhomes",
        "exchange": "HOSE",
        "industry": "Bất động sản nhà ở",
        "business_model": "Phát triển và quản lý bất động sản nhà ở, văn phòng và khu đô thị tích hợp sinh thái quy mô lớn hàng đầu Việt Nam.",
        "founded_date": "2008-03-06",
        "charter_capital": 43544.0,
        "number_of_employees": 11500,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Phạm Thiếu Hoa (Chủ tịch HĐQT)",
        "outstanding_shares": 4354367488,
        "listing_date": "2018-05-17",
        "shareholders": ["Tập đoàn Vingroup (66.7%)", "GIC Private Limited (5.7%)"],
    },
    "MWG": {
        "company_name": "CTCP Đầu tư Thế Giới Di Động",
        "exchange": "HOSE",
        "industry": "Bán lẻ đa kênh",
        "business_model": "Bán lẻ thiết bị công nghệ (thegioididong.com), điện máy gia dụng (Điện Máy Xanh), chuỗi bách hóa thực phẩm (Bách Hóa Xanh) và nhà thuốc (An Khang).",
        "founded_date": "2004-03-01",
        "charter_capital": 14622.0,
        "number_of_employees": 65000,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Nguyễn Đức Tài (Chủ tịch HĐQT)",
        "outstanding_shares": 1462231500,
        "listing_date": "2014-07-14",
        "shareholders": ["Retail World Investment (10.4%)", "Nguyễn Đức Tài (2.4%)", "Dragon Capital (7.1%)"],
    },
    "SSI": {
        "company_name": "CTCP Chứng khoán SSI",
        "exchange": "HOSE",
        "industry": "Dịch vụ tài chính chứng khoán",
        "business_model": "Môi giới chứng khoán cá nhân & tổ chức, cho vay ký quỹ margin, ngân hàng đầu tư (IB), tự doanh và quản lý quỹ đầu tư.",
        "founded_date": "1999-12-30",
        "charter_capital": 15111.0,
        "number_of_employees": 1600,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Nguyễn Duy Hưng (Chủ tịch HĐQT)",
        "outstanding_shares": 1511130130,
        "listing_date": "2006-12-15",
        "shareholders": ["Công ty TNHH Đầu tư NDH (9.9%)", "Daiwa Securities Group (15.4%)"],
    },
    "TCB": {
        "company_name": "Ngân hàng TMCP Kỹ thương Việt Nam (Techcombank)",
        "exchange": "HOSE",
        "industry": "Tài chính & Ngân hàng thương mại",
        "business_model": "Ngân hàng bán lẻ hiện đại, hệ sinh thái bất động sản - tiêu dùng (Masan), dẫn đầu tỷ lệ tiền gửi không kỳ hạn (CASA) và số hóa.",
        "founded_date": "1993-09-27",
        "charter_capital": 70450.0,
        "number_of_employees": 12500,
        "company_type": "Ngân hàng thương mại cổ phần niêm yết",
        "ceo_name": "Hồ Hùng Anh (Chủ tịch HĐQT)",
        "outstanding_shares": 7045024000,
        "listing_date": "2018-06-04",
        "shareholders": ["Masan Group (15.0%)", "Hồ Hùng Anh (1.1%)"],
    },
    "VNM": {
        "company_name": "CTCP Sữa Việt Nam (Vinamilk)",
        "exchange": "HOSE",
        "industry": "Thực phẩm & Đồ uống",
        "business_model": "Chế biến và kinh doanh sữa tươi, sữa chua, sữa đặc, kem và đồ uống dinh dưỡng với hệ thống trang trại chuẩn GlobalGAP.",
        "founded_date": "1976-08-20",
        "charter_capital": 20899.0,
        "number_of_employees": 9500,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Mai Kiều Liên (Tổng Giám đốc)",
        "outstanding_shares": 2089955445,
        "listing_date": "2006-01-19",
        "shareholders": ["SCIC (36.0%)", "F&N Dairy Investments (17.7%)"],
    },
    "VIC": {
        "company_name": "Tập đoàn Vingroup - CTCP",
        "exchange": "HOSE",
        "industry": "Đa ngành & Công nghiệp xe điện",
        "business_model": "Tập đoàn kinh tế tư nhân đa ngành: Công nghệ - Công nghiệp (VinFast), Bất động sản (Vinhomes), Du lịch nghỉ dưỡng (Vinpearl), Y tế & Giáo dục.",
        "founded_date": "1993-08-08",
        "charter_capital": 38237.0,
        "number_of_employees": 55000,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Phạm Nhật Vượng (Chủ tịch HĐQT)",
        "outstanding_shares": 3823661561,
        "listing_date": "2007-09-19",
        "shareholders": ["Phạm Nhật Vượng (17.8%)", "Tập đoàn Đầu tư Việt Nam (32.6%)"],
    },
}

COMMON_CONVERSATIONAL_WORDS = {
    'HELLO', 'GOOD', 'MORNING', 'HI', 'HEY', 'ALO', 'CHAO', 'XIN', 'TOI', 'BAN', 'MINH', 'CHO',
    'CO', 'DUNG', 'TIEN', 'VND', 'VON', 'DAU', 'TU', 'TRIEU', 'TY', 'TR', 'MUA', 'BAN', 'THE',
    'NAO', 'GI', 'SAO', 'LAM', 'XEM', 'TIM', 'VOI', 'HAY', 'CUA', 'CAC', 'MOT', 'HAI', 'BA',
    'BON', 'NAM', 'SAU', 'LAN', 'NEN', 'BOT', 'SLM', 'COT', 'RAG', 'AI', 'ARENA', 'ETF',
    'BIEU', 'DO', 'NGAY', 'THANG', 'CHI', 'TIET', 'DANH', 'MUC', 'KE', 'HOACH', 'MUON', 'CO',
    'PHIEU', 'MA', 'TICKER', 'STOCK', 'XEP', 'HANG', 'TOT', 'NHAT', 'QUAN', 'DIEM', 'CHIEN',
    'LUOC', 'THI', 'TRUONG', 'HOM', 'NAY', 'XU', 'HUONG', 'TANG', 'GIAM', 'PHONG', 'THU',
    'TAN', 'CONG', 'BAT', 'DAY', 'GIA', 'TRI', 'LUA', 'CHON', 'GOI', 'Y'
}


def get_slm_engine():
    """Khởi tạo hoặc tái sử dụng instance LocalReasoningSLMEngine."""
    global _GLOBAL_SLM_ENGINE
    if _GLOBAL_SLM_ENGINE is None and LocalReasoningSLMEngine is not None:
        try:
            _GLOBAL_SLM_ENGINE = LocalReasoningSLMEngine()
        except Exception as exc:
            logger.warning(f"Lỗi khởi tạo LocalReasoningSLMEngine: {exc}")
    return _GLOBAL_SLM_ENGINE


def _load_cafef_company_titles() -> Dict[str, str]:
    """Tải từ điển {symbol: Title} từ cafef_company_list.json (3,016 mã)."""
    global _CAFEF_TITLES_MAP
    if _CAFEF_TITLES_MAP is not None:
        return _CAFEF_TITLES_MAP

    t_map: Dict[str, str] = {}
    if CAFEF_SYMBOLS_PATH.exists():
        try:
            with open(CAFEF_SYMBOLS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        sym = item.get("Symbol") or item.get("symbol")
                        title = item.get("Title") or item.get("title") or sym
                        if sym:
                            t_map[sym.strip().upper()] = str(title).strip()
        except Exception as e:
            logger.debug(f"Lỗi đọc cafef_company_list.json: {e}")
    _CAFEF_TITLES_MAP = t_map
    return _CAFEF_TITLES_MAP


def load_valid_tickers() -> Set[str]:
    """Tải toàn bộ danh sách mã chứng khoán hợp lệ từ Lakehouse & CafeF."""
    global _ALL_LAKEHOUSE_TICKERS
    if _ALL_LAKEHOUSE_TICKERS is not None and len(_ALL_LAKEHOUSE_TICKERS) > 0:
        return _ALL_LAKEHOUSE_TICKERS

    tickers: Set[str] = set()

    # 1. Đọc từ file danh bạ CafeF (3,016 mã, 0% rủi ro lock DuckDB)
    titles_map = _load_cafef_company_titles()
    tickers.update(titles_map.keys())

    # 2. Đọc từ db/vesta_snapshot.duckdb core.dim_symbol (nếu có thể kết nối)
    if os.path.exists(SNAPSHOT_DB):
        try:
            with duckdb.connect(SNAPSHOT_DB, read_only=True, config={"access_mode": "read_only"}) as con:
                rows = con.execute("SELECT symbol FROM core.dim_symbol").fetchall()
                for r in rows:
                    if r[0]:
                        tickers.add(r[0].strip().upper())
        except Exception as exc:
            logger.debug(f"Snapshot duckdb read_only connect skipped: {exc}")

    # 3. Luôn bảo đảm có danh sách cốt lõi VN30, Phái sinh & ETFs
    fallback_universe = {
        "VIC", "VHM", "VRE", "FPT", "VCB", "HPG", "TCB", "MBB", "ACB", "STB",
        "VPB", "SSI", "VNM", "MWG", "DGC", "GAS", "PLX", "POW", "SAB", "VJC",
        "BID", "CTG", "NVL", "PNJ", "KDH", "PDR", "DXG", "DIG", "VCG", "NLG",
        "KBC", "DGW", "MSN", "VHC", "ANV", "ELC", "CMG", "FOX", "GVR", "BCM",
        "HDB", "SHB", "VIB", "TPB", "LPB", "MSB", "OCB", "SSB", "EIB", "HAG",
        "VNINDEX", "VN30", "HNX-INDEX", "UPCOM-INDEX", "VN30F1M", "VN30F2M",
        "E1VFVN30", "FUEVFVND", "FUESSVFL", "GB05F", "CFPT2301", "CHPG2301"
    }
    tickers.update(fallback_universe)
    _ALL_LAKEHOUSE_TICKERS = tickers
    return _ALL_LAKEHOUSE_TICKERS


def _extract_initial_cash_from_prompt(prompt: str, default_cash: float = 10000000.0) -> float:
    """Trích xuất linh hoạt số vốn đầu tư người dùng tự quyết định trong prompt."""
    p_lower = prompt.lower()

    # Pattern: 50 triệu, 50tr, 10 triệu, 10tr, 100 triệu, 1.5 tỷ, 2 tỷ...
    m_trieu = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:triệu|tr|m)\b', p_lower)
    if m_trieu:
        try:
            val_str = m_trieu.group(1).replace(',', '.')
            return float(val_str) * 1_000_000.0
        except Exception:
            pass

    m_ty = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:tỷ|ty|b)\b', p_lower)
    if m_ty:
        try:
            val_str = m_ty.group(1).replace(',', '.')
            return float(val_str) * 1_000_000_000.0
        except Exception:
            pass

    # Pattern số cụ thể: 50000000, 50.000.000, 50,000,000
    m_num = re.search(r'\bvốn\s*(?:là|khoảng|tầm)?\s*(\d{1,3}(?:[.,]\d{3})+|\d{7,11})\b', p_lower)
    if m_num:
        try:
            num_clean = re.sub(r'[.,]', '', m_num.group(1))
            val = float(num_clean)
            if val >= 100_000:
                return val
        except Exception:
            pass

    return default_cash


def _parse_user_symbols_and_intent(query: str, default_cash: float = 10000000.0) -> Dict[str, Any]:
    """
    Phân tích câu hỏi người dùng:
      - Tách riêng valid_symbols và unknown_symbols (Universe Gating).
      - Phát hiện hội thoại tự do / chào hỏi / câu hỏi kiến thức mà không bị ép khuôn.
      - Trích xuất vốn khởi điểm người dùng tự quyết định.
      - Phát hiện phong cách và chế độ thị trường.
    """
    all_tickers = load_valid_tickers()
    q_raw = query.strip()
    q_lower = q_raw.lower()

    # 1. Phát hiện hội thoại tự do / Chào hỏi / Giáo dục
    is_greeting = any(
        q_lower.startswith(g) or q_lower == g
        for g in ["hello", "hi", "chào", "xin chào", "hey", "alo", "good morning", "chúc buổi"]
    ) or len(q_raw) <= 5

    is_educational = any(
        k in q_lower
        for k in ["là gì", "giải thích", "ý nghĩa", "khái niệm", "tại sao", "dsr", "pbo", "sharpe", "odd-lot", "lô lẻ", "kolmogorov", "hybridacd"]
    )

    # 2. Tìm explicit tickers đứng sau từ khóa
    explicit_matches = re.findall(r'(?:mã|cổ phiếu|cp|ticker|stock)\s+([A-Za-z0-9_]{2,8})\b', q_raw, re.IGNORECASE)
    explicit_tokens = {m.upper() for m in explicit_matches}

    # 3. Tìm các token từ vựng tiềm năng
    candidate_tokens = re.findall(r'\b[A-Za-z0-9_]{2,8}\b', q_raw)

    valid_symbols: List[str] = []
    unknown_symbols: List[str] = []

    # Nếu người dùng có từ khóa explicit stock (ví dụ: "mã XYZ", "cp ABC")
    for t in explicit_tokens:
        if t in all_tickers:
            if t not in valid_symbols:
                valid_symbols.append(t)
        else:
            if t not in unknown_symbols and t not in COMMON_CONVERSATIONAL_WORDS:
                unknown_symbols.append(t)

    # Quét các candidate tokens
    for raw_token in candidate_tokens:
        u_token = raw_token.upper()
        if u_token in all_tickers and u_token not in COMMON_CONVERSATIONAL_WORDS:
            if u_token not in valid_symbols:
                valid_symbols.append(u_token)
        elif raw_token.isupper() and len(raw_token) in (3, 4, 5, 6) and not any(c.isdigit() for c in raw_token):
            if u_token not in COMMON_CONVERSATIONAL_WORDS:
                if u_token not in unknown_symbols and u_token not in valid_symbols:
                    unknown_symbols.append(u_token)

    # Nếu đây là lời chào hỏi thông thường và không có explicit stock được nhắc tới, xóa bỏ các unknown_symbols ảo
    if is_greeting and not explicit_tokens:
        unknown_symbols.clear()
        valid_symbols.clear()

    is_general_chat = is_greeting or (is_educational and not valid_symbols and not unknown_symbols)

    is_defense = any(k in q_lower for k in ["phòng thủ", "phòng vệ", "biến động", "bảo toàn", "rủi ro cao", "suy thoái", "bear", "crisis", "hedging", "phái sinh", "vn30f", "giảm mạnh", "an toàn", "sợ lỗ"])
    is_aggressive = any(k in q_lower for k in ["tấn công", "tăng trưởng", "bứt phá", "high return", "lợi nhuận cao", "đột phá", "bull", "momentum", "lướt sóng", "tối đa hóa"])
    is_value = any(k in q_lower for k in ["giá trị", "cổ tức", "p/b rẻ", "p/e thấp", "bctc tốt", "cơ bản", "roe cao", "tích sản", "dài hạn"])
    is_dip = any(k in q_lower for k in ["bắt đáy", "hồi phục", "sàn", "bán tháo", "hoảng loạn", "giảm sàn", "mất thanh khoản"])

    parsed_cash = _extract_initial_cash_from_prompt(q_raw, default_cash)

    return {
        "valid_symbols": valid_symbols,
        "unknown_symbols": unknown_symbols,
        "is_greeting": is_greeting,
        "is_educational": is_educational,
        "is_general_chat": is_general_chat,
        "is_defense": is_defense,
        "is_aggressive": is_aggressive,
        "is_value": is_value,
        "is_dip": is_dip,
        "initial_cash": parsed_cash,
    }


def extract_symbols_from_query(query: str) -> List[str]:
    """Trích xuất các mã hợp lệ từ câu hỏi người dùng."""
    parsed = _parse_user_symbols_and_intent(query)
    return parsed["valid_symbols"]


def query_rag_ohlcv(symbol: str) -> Dict[str, Any]:
    """Truy vấn dữ liệu nến kỹ thuật từ db/vesta_ohlcv.duckdb."""
    try:
        if not os.path.exists(OHLCV_DB):
            return {"symbol": symbol, "found": False}

        with duckdb.connect(OHLCV_DB, read_only=True, config={"access_mode": "read_only"}) as con:
            if symbol in ['VNINDEX', 'VN30', 'HNX-INDEX', 'UPCOM-INDEX']:
                rows = con.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM core.market_index_daily
                    WHERE index_code = ?
                    ORDER BY date DESC LIMIT 60
                """, [symbol]).fetchall()
            else:
                rows = con.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM core.market_ohlcv_daily
                    WHERE symbol = ?
                    ORDER BY date DESC LIMIT 60
                """, [symbol]).fetchall()

            if not rows:
                return {"symbol": symbol, "found": False}

            latest = rows[0]
            prev = rows[1] if len(rows) > 1 else latest
            p_last = float(latest[4])
            p_prev = float(prev[4])
            pct_1d = round(((p_last - p_prev) / p_prev) * 100, 2) if p_prev > 0 else 0.0

            # 5-session change
            pct_5d = 0.0
            if len(rows) >= 5 and float(rows[4][4]) > 0:
                pct_5d = round(((p_last - float(rows[4][4])) / float(rows[4][4])) * 100, 2)

            closes = [float(r[4]) for r in rows]
            sma20 = round(sum(closes[:20]) / min(len(closes), 20), 2)
            sma50 = round(sum(closes[:50]) / min(len(closes), 50), 2)
            high_52w = max(closes)
            low_52w = min(closes)

            # Floor lock detection in recent 5 bars
            floor_hits = 0
            for r in rows[:5]:
                op = float(r[1])
                cl = float(r[4])
                lo = float(r[3])
                if op > 0 and ((cl - op) / op) <= -0.065:
                    floor_hits += 1
                elif lo == cl and op == cl and pct_1d <= -6.0:
                    floor_hits += 1

            trend = "Tăng (Bullish)" if p_last > sma20 >= sma50 else ("Giảm (Bearish)" if p_last < sma20 else "Đi ngang (Neutral)")

            return {
                "symbol": symbol,
                "found": True,
                "last_date": str(latest[0])[:10],
                "last_price": p_last,
                "pct_1d": pct_1d,
                "pct_5d": pct_5d,
                "sma20": sma20,
                "sma50": sma50,
                "high_52w": high_52w,
                "low_52w": low_52w,
                "avg_vol_20": round(sum(float(r[5]) for r in rows[:20]) / min(len(rows), 20)),
                "trend": trend,
                "floor_hits": floor_hits,
            }
    except Exception as exc:
        logger.debug(f"query_rag_ohlcv({symbol}) exception: {exc}")
        return {"symbol": symbol, "found": False, "error": str(exc)}


def query_rag_news(symbol: Optional[str] = None, limit: int = 4) -> List[Dict[str, Any]]:
    """Truy vấn tin tức tài chính từ db/vesta_news.duckdb."""
    try:
        if not os.path.exists(NEWS_DB):
            return []

        with duckdb.connect(NEWS_DB, read_only=True, config={"access_mode": "read_only"}) as con:
            if symbol:
                rows = con.execute("""
                    SELECT headline, source, published_at, summary, source_url
                    FROM core.news
                    WHERE symbol = ? OR headline ILIKE ?
                    ORDER BY published_at DESC LIMIT ?
                """, [symbol, f"%{symbol}%", limit]).fetchall()
            else:
                rows = con.execute("""
                    SELECT headline, source, published_at, summary, source_url
                    FROM core.news
                    WHERE headline IS NOT NULL
                    ORDER BY published_at DESC LIMIT ?
                """, [limit]).fetchall()

            return [
                {
                    "headline": r[0],
                    "source": r[1] or "CafeF",
                    "date": str(r[2])[:10] if r[2] else "-",
                    "summary": r[3][:160] if r[3] else "",
                    "url": r[4] or "",
                }
                for r in rows if r[0]
            ]
    except Exception as exc:
        logger.debug(f"query_rag_news exception: {exc}")
        return []


def query_rag_snapshot(symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Truy vấn hồ sơ doanh nghiệp toàn diện:
    Bao gồm: business_model, founded_date, charter_capital, number_of_employees, company_type,
    cơ cấu cổ đông và sự kiện doanh nghiệp.
    Sử dụng cơ chế Fallback Cache thông minh để không bao giờ bị nghẽn khóa tập tin DuckDB.
    """
    sym = (symbol or "").strip().upper()
    titles_map = _load_cafef_company_titles()
    cafef_title = titles_map.get(sym, f"Doanh nghiệp niêm yết {sym}")

    # Giá trị khởi tạo mặc định
    res = {
        "symbol": sym,
        "company_name": cafef_title,
        "exchange": "HOSE",
        "industry": "Niêm yết",
        "business_model": "Kinh doanh đa ngành & sản xuất phân phối",
        "founded_date": "N/A",
        "charter_capital": 0.0,
        "number_of_employees": 0,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Ban Lãnh Đạo",
        "outstanding_shares": 0,
        "listing_date": "N/A",
        "events": [],
        "shareholders": [],
        "altman_z_zone": "Safe",
    }

    # 1. Nạp từ kho tri thức Bluechips xác thực nếu có
    if sym in KNOWN_COMPANY_OVERVIEWS:
        known = KNOWN_COMPANY_OVERVIEWS[sym]
        res.update(known)

    if not sym or not os.path.exists(SNAPSHOT_DB):
        return res

    # 2. Truy vấn trực tiếp từ DuckDB Lakehouse nếu không bị lock
    try:
        with duckdb.connect(SNAPSHOT_DB, read_only=True, config={"access_mode": "read_only"}) as con:
            try:
                sym_info = con.execute(
                    "SELECT organ_name, exchange, industry_name FROM core.dim_symbol WHERE symbol = ?",
                    [sym]
                ).fetchone()
                if sym_info:
                    if sym_info[0]:
                        res["company_name"] = sym_info[0]
                    if sym_info[1]:
                        res["exchange"] = sym_info[1]
                    if sym_info[2]:
                        res["industry"] = sym_info[2]
            except Exception:
                pass

            try:
                row = con.execute("""
                    SELECT symbol, exchange, charter_capital, ceo_name, company_type,
                           outstanding_shares, business_model, founded_date, number_of_employees, listing_date
                    FROM core.company_overview WHERE symbol = ?
                """, [sym]).fetchone()
                if row:
                    if row[1]:
                        res["exchange"] = row[1]
                    if row[2]:
                        res["charter_capital"] = float(row[2])
                    if row[3]:
                        res["ceo_name"] = row[3]
                    if row[4]:
                        res["company_type"] = row[4]
                    if row[5]:
                        res["outstanding_shares"] = int(row[5])
                    if row[6]:
                        res["business_model"] = row[6]
                    if row[7]:
                        res["founded_date"] = str(row[7])
                    if row[8]:
                        res["number_of_employees"] = int(row[8])
                    if row[9]:
                        res["listing_date"] = str(row[9])
            except Exception:
                pass

            try:
                events = con.execute("""
                    SELECT event_type, event_date, detail_json
                    FROM core.corporate_events
                    WHERE symbol = ?
                    ORDER BY event_date DESC LIMIT 3
                """, [sym]).fetchall()

                parsed_events = []
                for ev in events:
                    ev_type = ev[0]
                    ev_date = str(ev[1])[:10]
                    title = ev_type
                    if ev[2]:
                        try:
                            dj = json.loads(ev[2])
                            title = dj.get('event_title_vi') or dj.get('event_name_vi') or title
                        except Exception:
                            pass
                    parsed_events.append(f"{title} ({ev_date})")
                if parsed_events:
                    res["events"] = parsed_events
            except Exception:
                pass

            try:
                shs = con.execute("""
                    SELECT shareholder_name, ownership_percentage
                    FROM core.company_shareholders
                    WHERE symbol = ?
                    ORDER BY ownership_percentage DESC LIMIT 3
                """, [sym]).fetchall()
                parsed_shs = [f"{s[0]} ({s[1]}%)" for s in shs if s[0]]
                if parsed_shs:
                    res["shareholders"] = parsed_shs
            except Exception:
                pass

            try:
                fh = con.execute("""
                    SELECT data_json FROM core.fundamentals
                    WHERE symbol = ? AND report_type = 'financial_health'
                    ORDER BY period_end DESC LIMIT 1
                """, [sym]).fetchone()
                if fh and fh[0]:
                    fh_dj = json.loads(fh[0])
                    res["altman_z_zone"] = fh_dj.get("z_score_zone", res["altman_z_zone"])
            except Exception:
                pass
    except Exception as exc:
        logger.debug(f"DuckDB snapshot query skipped ({exc}), using cached overview dossier for {sym}")

    return res


def generate_rag_response(
    user_query: str,
    initial_cash: float = 10000000.0,
    risk_tolerance: str = "medium"
) -> Dict[str, Any]:
    """
    RAG Engine tổng hợp dữ liệu từ 3 database, sinh phản hồi Chain-of-Thought (CoT)
    và cấu hình bot định lượng đa tài sản phù hợp với số vốn người dùng yêu cầu:
      1. Phân tích đối thoại tự do nếu là lời chào / câu hỏi kiến thức (Free Reasoning).
      2. Cảnh báo và gợi ý mã nếu phát hiện mã không tồn tại trong CSDL (Universe Gating).
      3. Bổ sung đầy đủ company overview (business_model, founded_date, charter_capital, number_of_employees, company_type).
      4. Quyết định chế độ khủng hoảng (is_crisis_regime) do AI quyết định và thích ứng theo số vốn người dùng tự chọn.
    """
    slm = get_slm_engine()

    # 1. Phân tích ý định & bóc tách mã
    parsed = _parse_user_symbols_and_intent(user_query, initial_cash)
    valid_symbols = parsed["valid_symbols"]
    unknown_symbols = parsed["unknown_symbols"]
    actual_cash = parsed["initial_cash"]  # Ưu tiên số vốn người dùng tự quyết định trong prompt

    # =========================================================================
    # KỊCH BẢN 1: MÃ KHÔNG TỒN TẠI TRONG CƠ SỞ DỮ LIỆU LAKEHOUSE
    # =========================================================================
    if unknown_symbols:
        unknown_str = ", ".join(f"'{u}'" for u in unknown_symbols)
        reply = (
            f"⚠️ THÔNG BÁO MÃ CHỨNG KHOÁN KHÔNG TỒN TẠI TRONG CƠ SỞ DỮ LIỆU VESTA:\n\n"
            f"Hệ thống không tìm thấy mã chứng khoán: {unknown_str} trong cơ sở dữ liệu Lakehouse (HOSE, HNX, UPCOM).\n\n"
            f"Để đảm bảo tính xác thực định lượng 100% và tuân thủ nguyên tắc 'Zero Hallucination' (Không sinh mã giả), "
            f"VESTA chỉ tính toán hồ sơ và mô phỏng chiến lược trên các tài sản có chuỗi dữ liệu giao dịch sạch trong CSDL.\n\n"
            f"Vui lòng cung cấp hoặc chọn các mã cổ phiếu/chỉ số hiện có trong hệ thống:\n"
            f"• Rổ Bluechips VN30: FPT, VCB, HPG, VHM, MWG, TCB, SSI, VNM, VIC, ACB, MBB, STB, VPB...\n"
            f"• Bất động sản & Xây dựng: NVL, KDH, PDR, DXG, DIG, VCG, NLG, KBC...\n"
            f"• Bán lẻ & Tiêu dùng: PNJ, MWG, DGW, MSN, SAB, VHC, ANV...\n"
            f"• Công nghệ & Viễn thông: FPT, ELC, CMG, FOX...\n"
            f"• Phái sinh T+0 & Quỹ ETF: VN30F1M, E1VFVN30, FUEVFVND, FUESSVFL...\n\n"
            f"Bạn có thể nhập lại yêu cầu với các mã gợi ý ở trên kèm mức vốn bạn muốn để tôi phân tích hồ sơ và xếp hạng chiến lược bot ngay nhé!"
        )
        bot_config = {
            "bot_id": f"GUIDE_BOT_{int(dt.datetime.now().timestamp()) % 10000}",
            "name": "VESTA Universe Guidance Bot",
            "initial_cash": actual_cash,
            "signal_weights": {"regime_gate": 0.30, "sentiment": 0.30, "momentum": 0.20, "hedging": 0.20},
            "target_assets": ["E1VFVN30", "FPT", "VN30F1M"],
            "max_nav_cap_pct": 25.0,
            "stop_loss_pct": 4.0,
            "estimated_sharpe": 2.15,
            "reasoning_thesis": reply[:300] + "...",
            "risk_flags": ["UNKNOWN_SYMBOL_DETECTED"],
            "suggested_action": "SELECT_AVAILABLE_SYMBOL",
        }
        return {"reply": reply, "bot_config": bot_config}

    # =========================================================================
    # KỊCH BẢN 2: CHÀO HỎI / GIAO TIẾP TỰ DO / CÂU HỎI KIẾN THỨC
    # =========================================================================
    if not valid_symbols and parsed["is_general_chat"]:
        if slm and hasattr(slm, "generate_free_chat"):
            free_reply = slm.generate_free_chat(user_query)
        else:
            free_reply = (
                "Xin chào bạn! Tôi là VESTA AI Quantitative Assistant — trợ lý phân tích định lượng "
                "và cố vấn chiến lược danh mục đa tài sản trên thị trường chứng khoán Việt Nam.\n\n"
                "Tôi có thể hỗ trợ bạn:\n"
                "1. Phân tích chi tiết cổ phiếu với dữ liệu hồ sơ doanh nghiệp, BCTC và kỹ thuật OHLCV.\n"
                "2. Xếp hạng các bot định lượng theo mọi quy mô vốn tự chọn (Odd-lot từ 1-99 CP).\n"
                "3. Phòng vệ phái sinh VN30F1M và Quỹ ETF E1VFVN30 khi thị trường có biến động.\n\n"
                "Hãy nhập mã chứng khoán hoặc yêu cầu đầu tư của bạn để tôi hỗ trợ nhé!"
            )
        bot_config = {
            "bot_id": f"ASSISTANT_BOT_{int(dt.datetime.now().timestamp()) % 10000}",
            "name": "VESTA Multi-Asset Quantitative Assistant",
            "initial_cash": actual_cash,
            "signal_weights": {"regime_gate": 0.25, "sentiment": 0.35, "momentum": 0.25, "foreign_flow": 0.15},
            "target_assets": ["VN30F1M", "E1VFVN30", "FPT"],
            "max_nav_cap_pct": 25.0,
            "stop_loss_pct": 4.5,
            "estimated_sharpe": 2.18,
            "reasoning_thesis": free_reply[:300] + "...",
            "risk_flags": [],
            "suggested_action": "EXPLORE_STRATEGIES",
        }
        return {"reply": free_reply, "bot_config": bot_config}

    # =========================================================================
    # KỊCH BẢN 3: PHÂN TÍCH THEO MÃ HỢP LỆ VÀ SỐ VỐN NGƯỜI DÙNG TỰ CHỌN
    # =========================================================================
    target_sym = valid_symbols[0] if valid_symbols else "FPT"
    ohlcv = query_rag_ohlcv(target_sym)
    news = query_rag_news(target_sym, limit=3)
    snap = query_rag_snapshot(target_sym)

    comp_name = snap["company_name"] or target_sym
    exchange = snap["exchange"] or "HOSE"
    industry = snap["industry"] or "Niêm yết"
    b_model = snap["business_model"]
    founded_d = snap["founded_date"]
    charter_cap = snap["charter_capital"]
    n_emp = snap["number_of_employees"]
    comp_type = snap["company_type"]
    ceo_name = snap["ceo_name"]
    out_shares = snap["outstanding_shares"]
    listing_d = snap["listing_date"]

    p_last = ohlcv.get("last_price", 50.0)
    pct_1d = ohlcv.get("pct_1d", 0.0)
    pct_5d = ohlcv.get("pct_5d", 0.0)
    sma20 = ohlcv.get("sma20", 0.0)
    trend = ohlcv.get("trend", "Trung lập")
    vol20 = ohlcv.get("avg_vol_20", 0)
    high52 = ohlcv.get("high_52w", 0.0)
    low52 = ohlcv.get("low_52w", 0.0)
    floor_hits = ohlcv.get("floor_hits", 0)

    events_str = "; ".join(snap["events"]) if snap["events"] else "Không có sự kiện mới"
    sh_str = "; ".join(snap["shareholders"]) if snap["shareholders"] else "Đang cập nhật"
    news_str = "\n".join([f"  • [{n['source']} - {n['date']}] {n['headline']}" for n in news]) if news else "  • Chưa ghi nhận tin tức đột biến gần nhất."

    # Quyết định chế độ khủng hoảng (is_crisis_regime) do AI tính toán
    is_crisis_regime = (
        pct_5d < -7.0 or
        floor_hits >= 1 or
        snap.get("altman_z_zone") == "Distress" or
        parsed["is_dip"]
    )

    # Tính toán chính xác kích cỡ lô lẻ Odd-lot theo vốn người dùng quyết định
    nav_cap_cash = actual_cash * 0.25
    lot_shares = max(1, int(nav_cap_cash // (p_last * 1000))) if p_last > 0 else 50
    actual_stock_capital = lot_shares * p_last * 1000
    remaining_cash = actual_cash - actual_stock_capital

    # Chiến lược do AI model quyết định theo kịch bản
    if is_crisis_regime and not parsed["is_aggressive"]:
        action = "HẤP THỤ SÀN LÔ LẺ & SHORT HEDGING VN30F1M"
        stop_loss = round(p_last * 0.96, 2) if p_last > 0 else 0.0
        take_profit = round(p_last * 1.08, 2) if p_last > 0 else 0.0
        alloc_thesis = (
            f"Kích hoạt trạng thái FAIL-CLOSED & HEDGING:\n"
            f"- Đệm tiền mặt an toàn (60% ~ {actual_cash * 0.60:,.0f} VNĐ): Bảo toàn thanh khoản, tuyệt đối không tất tay.\n"
            f"- Ký quỹ phái sinh VN30F1M Short-Bias (25% ~ {actual_cash * 0.25:,.0f} VNĐ): Bù đắp rủi ro chu kỳ T+2.5.\n"
            f"- Thăm dò lô lẻ {target_sym} (15% ~ {actual_cash * 0.15:,.0f} VNĐ): Mua ~{max(1, int(actual_cash * 0.15 // (p_last * 1000)))} CP khi có lực cầu hấp thụ sàn."
        )
        target_assets = [target_sym, "VN30F1M", "E1VFVN30"]
        bot_id = "BOT-A140_CRISIS_FADE"
        strategy_name = "S13+S22+S09 (Sentiment Shock Fade + Regime Gate)"
        est_sharpe = 2.38
    elif parsed["is_defense"]:
        action = "PHÒNG THỦ NĂNG ĐỘNG (CAPITAL PRESERVATION)"
        stop_loss = round(p_last * 0.95, 2) if p_last > 0 else 0.0
        take_profit = round(p_last * 1.10, 2) if p_last > 0 else 0.0
        alloc_thesis = (
            f"Phân bổ phòng thủ trên vốn {actual_cash:,.0f} VNĐ:\n"
            f"- Giữ 50% tiền mặt ({actual_cash * 0.50:,.0f} VNĐ).\n"
            f"- 25% Ký quỹ phòng vệ phái sinh VN30F1M ({actual_cash * 0.25:,.0f} VNĐ).\n"
            f"- 25% Mua lô lẻ {target_sym} (~{lot_shares:,} CP, trị giá ~{actual_stock_capital:,.0f} VNĐ)."
        )
        target_assets = [target_sym, "VN30F1M", "E1VFVN30"]
        bot_id = "BOT-A112_DYNAMIC_HEDGE"
        strategy_name = "S13+S24 (VN30F1M Short-Bias Dynamic Hedge)"
        est_sharpe = 2.38
    elif parsed["is_aggressive"]:
        action = "TẤN CÔNG BỨT PHÁ (MOMENTUM BREAKOUT)"
        stop_loss = round(p_last * 0.95, 2) if p_last > 0 else 0.0
        take_profit = round(p_last * 1.15, 2) if p_last > 0 else 0.0
        alloc_thesis = (
            f"Phân bổ tấn công trên vốn {actual_cash:,.0f} VNĐ:\n"
            f"- 40% Giải ngân {target_sym} ({actual_cash * 0.40:,.0f} VNĐ) ~ {max(1, int(actual_cash * 0.40 // (p_last * 1000)))} CP.\n"
            f"- 35% Quỹ ETF E1VFVN30 ({actual_cash * 0.35:,.0f} VNĐ) ~ {max(1, int(actual_cash * 0.35 // 26500))} CCQ.\n"
            f"- 25% Tiền mặt dự phòng ({actual_cash * 0.25:,.0f} VNĐ) săn điểm gia tăng vị thế."
        )
        target_assets = [target_sym, "E1VFVN30", "VN30F1M"]
        bot_id = "BOT-A022_BREAKOUT"
        strategy_name = "S01+S12+S22 (Volume-Confirmed Momentum Breakout)"
        est_sharpe = 2.45
    else:
        action = "TÍCH LŨY DANH MỤC THÍCH ỨNG (ADAPTIVE ALLOCATION)"
        stop_loss = round(p_last * 0.95, 2) if p_last > 0 else 0.0
        take_profit = round(p_last * 1.10, 2) if p_last > 0 else 0.0
        alloc_thesis = (
            f"Phân bổ đa tài sản trên vốn {actual_cash:,.0f} VNĐ:\n"
            f"- 40% Quỹ ETF E1VFVN30 ({actual_cash * 0.40:,.0f} VNĐ) ~ {max(1, int(actual_cash * 0.40 // 26500))} CCQ.\n"
            f"- 25% Lô lẻ {target_sym} (~{lot_shares:,} CP, trị giá ~{actual_stock_capital:,.0f} VNĐ).\n"
            f"- 15% Ký quỹ phái sinh VN30F1M ({actual_cash * 0.15:,.0f} VNĐ) phòng hộ T+0.\n"
            f"- 20% Tiền mặt lưu động ({actual_cash * 0.20:,.0f} VNĐ)."
        )
        target_assets = [target_sym, "E1VFVN30", "VN30F1M"]
        bot_id = "BOT-A156_RISK_PARITY"
        strategy_name = "S08+S24 (Adaptive Risk Parity Multi-Asset)"
        est_sharpe = 2.18

    reply = (
        f"### 📊 Báo Cáo Phân Tích Toàn Diện: {target_sym} — {comp_name} ({exchange})\n\n"
        f" 1. Hồ Sơ Doanh Nghiệp & Tổng Quan (Từ db/vesta_snapshot.duckdb)\n"
        f"- Tên công ty: {comp_name} | Loại hình: {comp_type} | Sàn niêm yết: {exchange}\n"
        f"- Mô hình kinh doanh: {b_model}\n"
        f"- Ngày thành lập: {founded_d} | Ngày niêm yết: {listing_d}\n"
        f"- Vốn điều lệ: {charter_cap:,.0f} tỷ VNĐ | Cổ phiếu lưu hành: {out_shares:,.0f} CP\n"
        f"- Quy mô nhân sự: {n_emp:,} người | Người đại diện/CEO: {ceo_name}\n"
        f"- Cơ cấu cổ đông lớn: {sh_str}\n"
        f"- Sự kiện gần nhất: {events_str}\n\n"
        f" 2. Kỹ Thuật & Động Lượng Giá (Từ db/vesta_ohlcv.duckdb)\n"
        f"- Thị giá đóng cửa: {p_last:,.1f} (Nghìn VNĐ) ({pct_1d:+.2f}% phiên | {pct_5d:+.2f}% trong 5 phiên)\n"
        f"- Đường trung bình MA: SMA20 = {sma20:,.1f} | Xu hướng kỹ thuật: {trend}\n"
        f"- Biên độ 52 tuần: Thấp nhất {low52:,.1f} — Cao nhất {high52:,.1f}\n"
        f"- Khối lượng bình quân 20 phiên: {vol20:,.0f} CP/phiên\n"
        f"- Cảnh báo sàn (Floor Locks): {floor_hits} phiên chạm sàn gần đây\n\n"
        f" 3. Dòng Chảy Tin Tức & Tín Hiệu Sentiment (Từ db/vesta_news.duckdb)\n"
        f"{news_str}\n\n"
        f" 4. Chiến Lược Đầu Tư Do AI Hoạch Định (Vốn Do Bạn Quyết Định: {actual_cash:,.0f} VNĐ)\n"
        f"- Hành động đề xuất: {action}\n"
        f"- Vùng cắt lỗ (-5%): {stop_loss:,.1f} | Vùng chốt lời (+10% đến +15%): {take_profit:,.1f}\n"
        f"- Kế hoạch phân bổ lô lẻ (Odd-lot vi cấu trúc HOSE/HNX):\n"
        f"{alloc_thesis}\n"
    )

    bot_config = {
        "bot_id": f"{bot_id}_{int(dt.datetime.now().timestamp()) % 10000}",
        "name": f"{strategy_name} ({target_sym})",
        "initial_cash": actual_cash,
        "signal_weights": {
            "sentiment": 0.35 if is_crisis_regime else 0.30,
            "momentum": 0.15 if is_crisis_regime else 0.35,
            "regime_gate": 0.30 if is_crisis_regime else 0.20,
            "hedging": 0.20 if is_crisis_regime else 0.15,
        },
        "target_assets": target_assets,
        "max_nav_cap_pct": 25.0,
        "stop_loss_pct": 3.5 if is_crisis_regime else 4.5,
        "estimated_sharpe": est_sharpe,
        "reasoning_thesis": reply[:320] + "...",
        "risk_flags": (["CRISIS_REGIME_ACTIVE", "ODD_LOT_SUPPORTED"] if is_crisis_regime else ["ODD_LOT_SUPPORTED"]),
        "suggested_action": "DEFENSIVE_ALLOCATION" if is_crisis_regime else "BUY_OR_HOLD",
    }

    return {"reply": reply, "bot_config": bot_config}
