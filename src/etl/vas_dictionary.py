"""VAS (Thông tư 200/2014/TT-BTC) & IFRS Financial Statement Mapping Dictionary.

Chuẩn hóa toàn diện các chỉ tiêu tài chính từ nguồn CafeF / Vietstock (tiếng Việt & mã VAS)
sang hệ mã danh mục tiếng Anh chuẩn hoá đồng nhất với vnstock_data và downstream ML features.

Bảo đảm tính tương thích:
1. Giữ nguyên mã số VAS (ví dụ: '100', '110', '300', '400')
2. Giữ nguyên tên tiếng Việt gốc ('TỔNG CỘNG TÀI SẢN', 'Nợ phải trả')
3. Bổ sung các chuẩn key tiếng Anh ('total_assets', 'liabilities', 'net_revenue'...)
"""

from __future__ import annotations

import unicodedata
from typing import Any

# ==============================================================================
# 1. BẢNG CÂN ĐỐI KẾ TOÁN (BALANCE SHEET - CDKT)
# ==============================================================================
# Mapping từ (Mã VAS / Tên tiếng Việt chuẩn) sang (List các key tiếng Anh chuẩn)
BALANCE_SHEET_MAP: dict[str, list[str]] = {
    # TÀI SẢN (ASSETS)
    "100": ["total_assets", "assets"],
    "tổng cộng tài sản": ["total_assets", "assets"],
    "tổng tài sản": ["total_assets", "assets"],
    
    "110": ["current_assets", "short_term_assets"],
    "tài sản ngắn hạn": ["current_assets", "short_term_assets"],
    
    "111": ["cash_and_equivalents", "cash"],
    "tiền và tương đương tiền": ["cash_and_equivalents", "cash"],
    "tiền": ["cash_and_equivalents", "cash"],
    
    "112": ["cash_equivalents"],
    "các khoản tương đương tiền": ["cash_equivalents"],
    
    "120": ["short_term_investments"],
    "đầu tư tài chính ngắn hạn": ["short_term_investments"],
    
    "130": ["accounts_receivable", "short_term_receivables"],
    "các khoản phải thu ngắn hạn": ["accounts_receivable", "short_term_receivables"],
    
    "131": ["short_term_trade_receivables"],
    "phải thu ngắn hạn của khách hàng": ["short_term_trade_receivables"],
    
    "140": ["inventories", "inventory"],
    "hàng tồn kho": ["inventories", "inventory"],
    "hàng tồn kho ròng": ["inventories", "inventory"],
    
    "150": ["other_current_assets"],
    "tài sản ngắn hạn khác": ["other_current_assets"],
    
    "200": ["long_term_assets", "non_current_assets"],
    "tài sản dài hạn": ["long_term_assets", "non_current_assets"],
    
    "210": ["long_term_receivables"],
    "các khoản phải thu dài hạn": ["long_term_receivables"],
    
    "220": ["fixed_assets"],
    "tài sản cố định": ["fixed_assets"],
    
    "221": ["tangible_fixed_assets"],
    "tài sản cố định hữu hình": ["tangible_fixed_assets"],
    
    "227": ["intangible_fixed_assets"],
    "tài sản cố định vô hình": ["intangible_fixed_assets"],
    
    "230": ["investment_properties"],
    "bất động sản đầu tư": ["investment_properties"],
    
    "240": ["long_term_assets_in_progress"],
    "tài sản dở dang dài hạn": ["long_term_assets_in_progress"],
    
    "250": ["long_term_investments"],
    "đầu tư tài chính dài hạn": ["long_term_investments"],
    
    "260": ["other_long_term_assets"],
    "tài sản dài hạn khác": ["other_long_term_assets"],

    # NGUỒN VỐN (LIABILITIES & EQUITY)
    "300": ["liabilities", "total_liabilities"],
    "nợ phải trả": ["liabilities", "total_liabilities"],
    "tổng nợ phải trả": ["liabilities", "total_liabilities"],
    
    "310": ["current_liabilities", "short_term_liabilities"],
    "nợ ngắn hạn": ["current_liabilities", "short_term_liabilities"],
    
    "311": ["short_term_trade_payables"],
    "phải trả người bán ngắn hạn": ["short_term_trade_payables"],
    
    "320": ["long_term_liabilities", "non_current_liabilities"],
    "nợ dài hạn": ["long_term_liabilities", "non_current_liabilities"],
    
    "330": ["total_borrowings", "debt"],
    "vay và nợ thuê tài chính": ["total_borrowings", "debt"],
    
    "400": ["owners_equity", "equity"],
    "vốn chủ sở hữu": ["owners_equity", "equity"],
    "tổng vốn chủ sở hữu": ["owners_equity", "equity"],
    
    "410": ["capital_and_reserves"],
    "vốn và các quỹ": ["capital_and_reserves"],
    
    "411": ["capital_share", "charter_capital"],
    "vốn góp của chủ sở hữu": ["capital_share", "charter_capital"],
    "vốn đầu tư của chủ sở hữu": ["capital_share", "charter_capital"],
    
    "412": ["share_premium"],
    "thặng dư vốn cổ phần": ["share_premium"],
    
    "421": ["retained_earnings", "undistributed_earnings"],
    "lợi nhuận sau thuế chưa phân phối": ["retained_earnings", "undistributed_earnings"],
    
    "440": ["total_resources", "total_capital"],
    "tổng cộng nguồn vốn": ["total_resources", "total_capital", "total_assets"],
}

# ==============================================================================
# 2. BÁO CÁO KẾT QUẢ KINH DOANH (INCOME STATEMENT - KQKD)
# ==============================================================================
INCOME_STATEMENT_MAP: dict[str, list[str]] = {
    "01": ["gross_revenue"],
    "doanh thu bán hàng và cung cấp dịch vụ": ["gross_revenue"],
    
    "02": ["revenue_deductions"],
    "các khoản giảm trừ doanh thu": ["revenue_deductions"],
    
    "10": ["net_revenue", "revenue"],
    "1": ["net_revenue", "revenue"],
    "doanh thu thuần về bán hàng và cung cấp dịch vụ": ["net_revenue", "revenue"],
    "doanh thu thuần": ["net_revenue", "revenue"],
    
    "11": ["cost_of_goods_sold", "cogs"],
    "2": ["cost_of_goods_sold", "cogs"],
    "giá vốn hàng bán": ["cost_of_goods_sold", "cogs"],
    
    "20": ["gross_profit"],
    "3": ["gross_profit"],
    "lợi nhuận gộp về bán hàng và cung cấp dịch vụ": ["gross_profit"],
    "lợi nhuận gộp": ["gross_profit"],
    
    "21": ["financial_income"],
    "4": ["financial_income"],
    "doanh thu hoạt động tài chính": ["financial_income"],
    
    "22": ["financial_expenses"],
    "5": ["financial_expenses"],
    "chi phí tài chính": ["financial_expenses"],
    
    "23": ["interest_expenses"],
    "chi phí lãi vay": ["interest_expenses"],
    
    "25": ["selling_expenses"],
    "6": ["selling_expenses"],
    "chi phí bán hàng": ["selling_expenses"],
    
    "26": ["general_administrative_expenses", "admin_expenses"],
    "7": ["general_administrative_expenses", "admin_expenses"],
    "chi phí quản lý doanh nghiệp": ["general_administrative_expenses", "admin_expenses"],
    
    "30": ["operating_profit"],
    "8": ["operating_profit"],
    "lợi nhuận thuần từ hoạt động kinh doanh": ["operating_profit"],
    
    "31": ["other_income"],
    "thu nhập khác": ["other_income"],
    
    "32": ["other_expenses"],
    "chi phí khác": ["other_expenses"],
    
    "40": ["other_profit"],
    "lợi nhuận khác": ["other_profit"],
    
    "50": ["profit_before_tax", "ebit"],
    "tổng lợi nhuận kế toán trước thuế": ["profit_before_tax", "ebit"],
    "lợi nhuận trước thuế": ["profit_before_tax", "ebit"],
    
    "51": ["current_corporate_income_tax"],
    "chi phí thuế tndn hiện hành": ["current_corporate_income_tax"],
    
    "60": ["net_profit_after_tax", "net_profit", "profit_after_tax"],
    "14": ["net_profit_after_tax", "net_profit", "profit_after_tax"],
    "lợi nhuận sau thuế thu nhập doanh nghiệp": ["net_profit_after_tax", "net_profit", "profit_after_tax"],
    "lợi nhuận sau thuế của công ty mẹ": ["net_profit_after_tax", "net_profit", "profit_after_tax"],
    "lợi nhuận sau thuế": ["net_profit_after_tax", "net_profit", "profit_after_tax"],
    
    "70": ["eps", "earning_per_share"],
    "lãi cơ bản trên một cổ phiếu": ["eps", "earning_per_share"],
    "lãi cơ bản trên cổ phiếu (eps)": ["eps", "earning_per_share"],
    "lãi cơ bản trên cổ phiếu": ["eps", "earning_per_share"],
}

# ==============================================================================
# 3. BÁO CÁO LƯU CHUYỂN TIỀN TỆ (CASH FLOW - LCTT)
# ==============================================================================
CASH_FLOW_MAP: dict[str, list[str]] = {
    "20": ["operating_cash_flow", "cfo"],
    "hdkd": ["operating_cash_flow", "cfo"],
    "lưu chuyển tiền thuần từ hoạt động kinh doanh": ["operating_cash_flow", "cfo"],
    "lưu chuyển tiền từ đh kinh doanh": ["operating_cash_flow", "cfo"],
    
    "30": ["investing_cash_flow", "cfi"],
    "hddt": ["investing_cash_flow", "cfi"],
    "lưu chuyển tiền thuần từ hoạt động đầu tư": ["investing_cash_flow", "cfi"],
    "lưu chuyển tiền từ hoạt động đầu tư": ["investing_cash_flow", "cfi"],
    
    "40": ["financing_cash_flow", "cff"],
    "hdtc": ["financing_cash_flow", "cff"],
    "lưu chuyển tiền thuần từ hoạt động tài chính": ["financing_cash_flow", "cff"],
    "lưu chuyển tiền từ hoạt động tài chính": ["financing_cash_flow", "cff"],
    
    "50": ["net_cash_flow"],
    "lưu chuyển tiền thuần trong kỳ": ["net_cash_flow"],
    
    "60": ["cash_at_beginning_of_period"],
    "tiền và tương đương tiền đầu kỳ": ["cash_at_beginning_of_period"],
    
    "70": ["cash_at_end_of_period"],
    "tiền và tương đương tiền cuối kỳ": ["cash_at_end_of_period"],
}

# ==============================================================================
# 4. CHỈ SỐ TÀI CHÍNH CHUYÊN SÂU (RATIOS / FINANCIAL INDICATORS)
# ==============================================================================
RATIO_MAP: dict[str, list[str]] = {
    "p/e": ["pe", "price_to_earnings", "pe_ratio", "rt_pe"],
    "pe": ["pe", "price_to_earnings", "pe_ratio", "rt_pe"],
    "p/b": ["pb", "price_to_book", "pb_ratio", "rt_pb"],
    "pb": ["pb", "price_to_book", "pb_ratio", "rt_pb"],
    "roe": ["roe", "return_on_equity", "rt_roe"],
    "roa": ["roa", "return_on_assets", "rt_roa"],
    "eps": ["eps", "earning_per_share"],
    "bvps": ["bvps", "book_value_per_share"],
    "biên lợi nhuận gộp": ["gross_margin"],
    "gross_margin": ["gross_margin"],
    "biên lợi nhuận ròng": ["net_profit_margin"],
    "net_margin": ["net_profit_margin"],
    "hệ số thanh toán hiện hành": ["current_ratio"],
    "current_ratio": ["current_ratio"],
    "hệ số thanh toán nhanh": ["quick_ratio"],
    "quick_ratio": ["quick_ratio"],
    "nợ/vốn chủ sở hữu": ["debt_to_equity"],
    "debt_to_equity": ["debt_to_equity"],
}


def _strip_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để so khớp không dấu."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", text).lower().strip()


def normalize_financial_dict(raw_metrics: dict[str, Any], report_type: str) -> dict[str, Any]:
    """Chuẩn hóa dictionary metrics:
    
    1. Giữ nguyên 100% các cặp key-value ban đầu (mã VAS, tên tiếng Việt).
    2. Bổ sung các key chuẩn tiếng Anh tương ứng để tương thích với downstream models.
    """
    normalized = dict(raw_metrics)
    
    # Chọn bảng mapping tương ứng
    target_map = {}
    if report_type == "balance_sheet":
        target_map = BALANCE_SHEET_MAP
    elif report_type == "income_statement":
        target_map = INCOME_STATEMENT_MAP
    elif report_type == "cash_flow":
        target_map = CASH_FLOW_MAP
    elif report_type in ["ratio", "financial_health"]:
        target_map = RATIO_MAP
    else:
        # Nếu chưa rõ, gộp tất cả
        target_map = {**BALANCE_SHEET_MAP, **INCOME_STATEMENT_MAP, **CASH_FLOW_MAP, **RATIO_MAP}

    # Quét qua từng item trong raw_metrics
    for k, v in raw_metrics.items():
        if v is None:
            continue
            
        clean_k = str(k).strip()
        lower_k = clean_k.lower()
        no_accents_k = _strip_accents(clean_k)
        
        # 1. So khớp trực tiếp (code số hoặc tên đầy đủ)
        english_keys = None
        if clean_k in target_map:
            english_keys = target_map[clean_k]
        elif lower_k in target_map:
            english_keys = target_map[lower_k]
        elif no_accents_k in target_map:
            english_keys = target_map[no_accents_k]
        else:
            # 2. Tìm kiếm chứa từ khóa (Partial Substring Matching)
            for map_key, mapped_engs in target_map.items():
                if map_key.isdigit():
                    continue
                map_no_accents = _strip_accents(map_key)
                if map_no_accents in no_accents_k or no_accents_k in map_no_accents:
                    english_keys = mapped_engs
                    break
        
        # Gán giá trị vào các key tiếng Anh chuẩn hóa
        if english_keys:
            for eng in english_keys:
                if eng not in normalized:
                    normalized[eng] = v

    return normalized
