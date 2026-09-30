"""F007b: Market Insights, Screener, Valuation & Macroeconomic Direct REST API Crawler.

Kiến trúc Direct REST API (Zero vnstock / Zero API Key):
- Thay thế hoàn toàn các lớp Insights, Analytics.valuation và Macro trong gói vnstock_data (Sponsor).
- 100% public REST endpoints từ các tổ chức tài chính lớn tại Việt Nam:
  1. Vietcap IQ Direct API (iq.vietcap.com.vn):
     - Screener (bộ lọc đa nhân tố 24-51 chỉ tiêu cho hơn 1.500 cổ phiếu HSX, HNX, UPCOM).
     - Screener criteria (danh mục định nghĩa các trường chỉ số cơ bản & kỹ thuật).
  2. VNDIRECT FINFO Direct API (api-finfo.vndirect.com.vn/v4):
     - Top stocks rankings (top tăng/giảm giá, top giá trị, top khối lượng, giao dịch đột biến).
     - Top foreign flows (top khối ngoại mua ròng / bán ròng theo ngày).
     - Index valuation ratios (chuỗi lịch sử P/E, P/B của VN-Index, VN30, HNX-Index).
  3. ASEAN Securities Research API (asean-apigw.aseansc.com.vn/pbapi/api):
     - Market breadth (độ rộng thị trường, tỷ lệ mã trên MA20/MA50/MA200, dải định giá).
     - Market fear & greed index (chỉ số Tham lam & Sợ hãi, MFI, RSI, dòng tiền).
     - Macroeconomic series (GDP, CPI, Xuất nhập khẩu XM, Lãi suất liên ngân hàng, Tỷ giá trung tâm, FDI...).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl.retry_failed_jobs import EmptyResultError

logger = logging.getLogger("market_insights")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

VCI_HEADERS = {
    **DEFAULT_HEADERS,
    "Content-Type": "application/json",
    "Origin": "https://trading.vietcap.com.vn",
    "Referer": "https://trading.vietcap.com.vn/",
}

ASEAN_HEADERS = {
    **DEFAULT_HEADERS,
    "Origin": "https://research.aseansc.com.vn",
    "Referer": "https://research.aseansc.com.vn/",
}

VND_HEADERS = {
    **DEFAULT_HEADERS,
}

VCI_COLUMN_MAP = {
    "ticker": "symbol",
    "ref_price": "reference_price",
    "ceiling": "ceiling_price",
    "floor": "floor_price",
    "market_price": "price",
    "daily_price_change_percent": "price_change_percent",
    "price_change_pct_1d": "price_change_percent",
    "price_change_pct1_d": "price_change_percent",
    "volume_spike_20d_pct": "volume_spike_20d_percent",
    "volume_spike20_d_pct": "volume_spike_20d_percent",
    "ttm_pe": "pe",
    "ttm_pb": "pb",
    "ttm_roe": "roe",
}

VND_TOP_STOCK_COLS = {
    "code": "symbol",
    "index": "index",
    "lastPrice": "last_price",
    "lastUpdated": "last_updated",
    "priceChgCr1D": "price_change_1d",
    "priceChgPctCr1D": "price_change_percent_1d",
    "accumulatedVal": "accumulated_value",
    "nmVolumeAvgCr20D": "avg_volume_20d",
    "nmVolNmVolAvg20DPctCr": "volume_spike_20d_percent",
    "totalVolumeAvgCr20D": "total_volume_avg_20d",
    "ptVolTotalVolAvg20DPctCr": "deal_volume_spike_20d_percent",
    "ptVolAvg5DTotalVolAvg20DPctCr": "deal_volume_spike_5d_20d_percent",
    "ptVolSumCr5D": "deal_volume_sum_5d",
    "ptValAvgCr5D": "deal_value_avg_5d",
    "ptVolAvgCr5D": "deal_volume_avg_5d",
}


def _camel_to_snake(s: str) -> str:
    """Chuyển chuỗi camelCase hoặc PascalCase sang snake_case (bảo toàn từ viết hoa toàn bộ)."""
    if not s:
        return ""
    if s.isupper():
        return s.lower()
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


# ============================================================================
# 1. VIETCAP IQ DIRECT API (SCREENER & MULTI-FACTOR RANKING)
# ============================================================================

def fetch_market_screener(
    filters: Optional[List[Dict[str, Any]]] = None,
    exchanges: Optional[List[str]] = None,
    page_size: int = 1600,
    timeout: int = 15,
) -> pd.DataFrame:
    """Truy vấn bộ lọc cổ phiếu đa nhân tố trực tiếp từ Vietcap IQ API.

    Tham số:
        filters: Danh sách cấu hình bộ lọc tùy chỉnh. Nếu None, lấy tất cả mã sàn.
        exchanges: Danh sách sàn lọc ('hsx', 'hnx', 'upcom'). Mặc định lấy cả 3 sàn.
        page_size: Số lượng mã trả về (thị trường VN có ~1.520 mã, 1.600 quét trọn vẹn trong 1 lượt).
        timeout: Thời gian timeout (giây).

    Trả về:
        pd.DataFrame chứa các trường định lượng (P/E, P/B, ROE, RS_3M, MACD, RSI, Trend...).
    """
    url = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/screening/paging"

    if filters is None:
        target_exchanges = exchanges or ["hsx", "hnx", "upcom"]
        cond_options = [{"type": "value", "value": ex.lower()} for ex in target_exchanges]
        filters = [{"name": "exchange", "conditionOptions": cond_options}]

    payload = {
        "page": 0,
        "pageSize": page_size,
        "sortFields": [],
        "sortOrders": [],
        "filter": filters,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=VCI_HEADERS,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Lỗi khi gọi Vietcap Screener API: %s", exc)
        raise

    content = data.get("data", {}).get("content", [])
    if not content:
        raise EmptyResultError("Vietcap Screener API trả về danh sách rỗng.")

    df = pd.DataFrame(content)

    # Chuẩn hóa tên cột sang snake_case
    cleaned_cols = []
    for col in df.columns:
        s = _camel_to_snake(col)
        cleaned_cols.append(VCI_COLUMN_MAP.get(s, s))
    df.columns = cleaned_cols

    if "id" in df.columns:
        df = df.drop(columns=["id"])

    # Chuyển đổi kiểu dữ liệu số
    numeric_candidates = [
        "pe", "pb", "roe", "market_cap", "price", "reference_price", "ceiling_price",
        "floor_price", "accumulated_value", "accumulated_volume", "rs_3m", "rsi",
        "macd", "macd_signal", "histogram", "price_change_percent", "net_margin",
        "gross_margin", "profit_growth_yoy", "revenue_growth_yoy", "adx", "ao"
    ]
    for col in numeric_candidates:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df.attrs["source"] = "VIETCAP_IQ_DIRECT"
    df.attrs["total_elements"] = data.get("data", {}).get("totalElements", len(df))
    return df


def fetch_screener_criteria(lang: str = "vi", timeout: int = 10) -> pd.DataFrame:
    """Lấy danh mục các trường chỉ số và định nghĩa tiêu chí từ Vietcap IQ API."""
    url = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/screening/criteria"
    req = urllib.request.Request(url, headers=VCI_HEADERS, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Lỗi khi lấy criteria từ Vietcap IQ API: %s", exc)
        raise

    raw_items = data.get("data", [])
    if not raw_items:
        raise EmptyResultError("Vietcap Criteria API trả về danh sách rỗng.")

    rows = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        field_name = item.get("name")
        snake_name = _camel_to_snake(field_name) if field_name else ""
        readable = item.get("viName" if lang == "vi" else "enName", field_name)
        rows.append({
            "category": item.get("category"),
            "field_name": field_name,
            "column_name": VCI_COLUMN_MAP.get(snake_name, snake_name),
            "readable_name": readable,
            "select_type": item.get("selectType"),
        })

    df = pd.DataFrame(rows)
    df.attrs["source"] = "VIETCAP_IQ_DIRECT"
    return df


# ============================================================================
# 2. VNDIRECT FINFO DIRECT API (RANKINGS, VALUATION, FOREIGN FLOWS)
# ============================================================================

def fetch_market_rankings(
    category: str = "gainer",
    index: str = "VNINDEX",
    limit: int = 10,
    timeout: int = 10,
) -> pd.DataFrame:
    """Truy vấn bảng xếp hạng top cổ phiếu thị trường từ VNDIRECT FINFO Direct API.

    Tham số:
        category: 'gainer' (tăng mạnh nhất), 'loser' (giảm mạnh nhất), 'value' (giá trị GD lớn nhất),
                  'volume' (khối lượng đột biến), 'deal' (giao dịch thỏa thuận đột biến).
        index: 'VNINDEX', 'VN30', hoặc 'HNX'.
        limit: Số lượng mã xếp hạng cần lấy.
        timeout: Thời gian timeout (giây).
    """
    idx_map = {
        "VNINDEX": "VNIndex",
        "VN30": "VN30",
        "HNX": "HNX",
    }
    target_idx = idx_map.get(index.upper(), "VNIndex")

    if category == "gainer":
        query = f"index:{target_idx}~nmVolumeAvgCr20D:gte:10000~priceChgPctCr1D:gt:0&size={limit}&sort=priceChgPctCr1D:desc"
    elif category == "loser":
        query = f"index:{target_idx}~nmVolumeAvgCr20D:gte:10000~priceChgPctCr1D:lt:0&size={limit}&sort=priceChgPctCr1D:asc"
    elif category == "value":
        query = f"index:{target_idx}~accumulatedVal:gt:0&size={limit}&sort=accumulatedVal:desc"
    elif category == "volume":
        query = f"index:{target_idx}~nmVolumeAvgCr20D:gte:10000~nmVolNmVolAvg20DPctCr:gte:100&size={limit}&sort=nmVolNmVolAvg20DPctCr:desc"
    elif category == "deal":
        query = f"index:{target_idx}~nmVolumeAvgCr20D:gte:10000&size={limit}&sort=ptVolTotalVolAvg20DPctCr:desc"
    else:
        raise ValueError(f"Category '{category}' không hợp lệ. Hỗ trợ: gainer, loser, value, volume, deal")

    url = f"https://api-finfo.vndirect.com.vn/v4/top_stocks?q={query}"
    req = urllib.request.Request(url, headers=VND_HEADERS, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Lỗi khi truy vấn VNDIRECT FINFO Top Stocks: %s", exc)
        raise

    items = data.get("data", [])
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)
    df = df.rename(columns=VND_TOP_STOCK_COLS)

    numeric_cols = [
        "last_price", "price_change_1d", "price_change_percent_1d", "accumulated_value",
        "avg_volume_20d", "volume_spike_20d_percent", "total_volume_avg_20d",
        "deal_volume_spike_20d_percent"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df.attrs["source"] = "VNDIRECT_FINFO_DIRECT"
    df.attrs["category"] = category
    return df


def fetch_foreign_top_flows(
    mode: str = "buy",
    trading_date: Optional[str] = None,
    limit: int = 10,
    timeout: int = 10,
) -> pd.DataFrame:
    """Lấy top mua ròng / bán ròng của khối ngoại theo ngày từ VNDIRECT FINFO API."""
    if trading_date is None:
        trading_date = dt.datetime.now().strftime("%Y-%m-%d")

    if mode == "buy":
        query = f"type:STOCK,IFC,ETF~netVal:gt:0~tradingDate:{trading_date}&sort=tradingDate~netVal:desc&size={limit}&fields=code,netVal,tradingDate"
    elif mode == "sell":
        query = f"type:STOCK,IFC,ETF~netVal:lt:0~tradingDate:{trading_date}&sort=tradingDate~netVal:asc&size={limit}&fields=code,netVal,tradingDate"
    else:
        raise ValueError(f"Mode '{mode}' không hợp lệ. Hỗ trợ: buy, sell")

    url = f"https://api-finfo.vndirect.com.vn/v4/foreigns?q={query}"
    req = urllib.request.Request(url, headers=VND_HEADERS, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Lỗi khi truy vấn VNDIRECT Foreign Flows: %s", exc)
        raise

    items = data.get("data", [])
    if not items:
        return pd.DataFrame(columns=["symbol", "net_val", "trading_date"])

    df = pd.DataFrame(items)
    df = df.rename(columns={"code": "symbol", "netVal": "net_val", "tradingDate": "trading_date"})
    if "net_val" in df.columns:
        df["net_val"] = pd.to_numeric(df["net_val"], errors="coerce")

    df.attrs["source"] = "VNDIRECT_FINFO_DIRECT"
    df.attrs["mode"] = mode
    return df


def fetch_index_valuation(
    index: str = "VNINDEX",
    ratio_code: str = "PRICE_TO_EARNINGS",
    start_date: str = "2020-01-01",
    timeout: int = 10,
) -> pd.DataFrame:
    """Truy vấn chuỗi lịch sử định giá chỉ số (P/E, P/B) từ VNDIRECT FINFO API.

    Tham số:
        index: 'VNINDEX', 'VN30', hoặc 'HNX'.
        ratio_code: 'PRICE_TO_EARNINGS' (P/E) hoặc 'PRICE_TO_BOOK' (P/B).
        start_date: Ngày bắt đầu (định dạng 'YYYY-MM-DD').
        timeout: Thời gian timeout (giây).
    """
    idx_clean = index.upper()
    if idx_clean == "HNXINDEX":
        idx_clean = "HNX"

    url = (
        f"https://api-finfo.vndirect.com.vn/v4/ratios?"
        f"q=ratioCode:{ratio_code}~code:{idx_clean}~reportDate:gte:{start_date}"
        f"&sort=reportDate:desc&size=10000&fields=value,reportDate"
    )
    req = urllib.request.Request(url, headers=VND_HEADERS, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Lỗi khi truy vấn VNDIRECT Index Valuation: %s", exc)
        raise

    items = data.get("data", [])
    if not items:
        return pd.DataFrame(columns=["report_date", "value"])

    df = pd.DataFrame(items)
    df = df.rename(columns={"reportDate": "report_date"})
    df["report_date"] = pd.to_datetime(df["report_date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.sort_values("report_date", ascending=True).reset_index(drop=True)

    df.attrs["source"] = "VNDIRECT_FINFO_DIRECT"
    df.attrs["index"] = index
    df.attrs["ratio_code"] = ratio_code
    return df


# ============================================================================
# 3. ASEAN SECURITIES RESEARCH API (SENTIMENT, BREADTH, FEAR & GREED)
# ============================================================================

def fetch_market_breadth(exchange: str = "HOSE", timeout: int = 10) -> pd.DataFrame:
    """Truy vấn chuỗi thời gian độ rộng thị trường (Advance/Decline/MA20/MA50) từ ASEAN Securities."""
    ex_clean = exchange.upper()
    url = f"https://asean-apigw.aseansc.com.vn/pbapi/api/mktBreadth?indexCode={ex_clean}"
    req = urllib.request.Request(url, headers=ASEAN_HEADERS, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Lỗi khi truy vấn ASEAN Market Breadth: %s", exc)
        raise

    items = data.get("data", [])
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)
    col_rename = {
        "ExchangeCode": "exchange",
        "TradeDate": "trade_date",
        "PE": "pe",
        "PB": "pb",
        "ABOVE_MA50_PCT": "above_ma50_pct",
        "AVG_20D_ABOVE_MA50_PCT": "avg_20d_above_ma50_pct",
        "close_index": "close_index",
        "above_ma20_pct": "above_ma20_pct",
        "position_line": "position_line",
        "AVG_20D_ABOVE_MA20_PCT": "avg_20d_above_ma20_pct",
        "ABOVE_MA200_PCT": "above_ma200_pct",
    }
    df = df.rename(columns=col_rename)

    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")

    numeric_cols = [
        "pe", "pb", "above_ma20_pct", "above_ma50_pct", "above_ma200_pct",
        "avg_20d_above_ma20_pct", "avg_20d_above_ma50_pct", "close_index", "position_line"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("trade_date", ascending=True).reset_index(drop=True)
    df.attrs["source"] = "ASEAN_SC_DIRECT"
    return df


def fetch_market_fear_greed(exchange: str = "HOSE", timeout: int = 10) -> pd.DataFrame:
    """Truy vấn chỉ số Sợ hãi & Tham lam (Fear & Greed Index) từ ASEAN Securities."""
    ex_clean = exchange.upper()
    url = f"https://asean-apigw.aseansc.com.vn/pbapi/api/aseanfeargreed?indexCode={ex_clean}"
    req = urllib.request.Request(url, headers=ASEAN_HEADERS, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Lỗi khi truy vấn ASEAN Fear & Greed: %s", exc)
        raise

    items = data.get("data", [])
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)
    col_rename = {
        "FEAR_GREED": "fear_greed_score",
        "ADVANCES": "advances",
        "DECLINES": "declines",
        "NOCHANGE": "no_change",
        "MFI": "mfi",
        "RSI": "rsi",
        "INDEX_CHANGE": "index_change",
        "VOL_CHANGE": "volume_change",
    }
    df = df.rename(columns=col_rename)

    for col in ["fear_greed_score", "advances", "declines", "no_change", "mfi", "rsi", "index_change", "volume_change"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df.attrs["source"] = "ASEAN_SC_DIRECT"
    return df


# ============================================================================
# 4. ASEAN SECURITIES MACROECONOMIC SERIES (GDP, CPI, TRADE, RATES)
# ============================================================================

def _format_asean_date(date_str: Optional[str], default_years: int = 3) -> str:
    """Chuyển đổi ngày YYYY-MM-DD sang định dạng MM-DD-YYYY của ASEAN API."""
    if date_str:
        d = dt.datetime.strptime(date_str, "%Y-%m-%d")
    else:
        d = dt.datetime.now() - dt.timedelta(days=365 * default_years)
    return d.strftime("%m-%d-%Y")


def fetch_macro_indicator(
    indicator: str = "gdp",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: Optional[str] = None,
    timeout: int = 10,
) -> pd.DataFrame:
    """Truy vấn chuỗi chỉ số kinh tế vĩ mô từ ASEAN Securities Direct API.

    Tham số:
        indicator:
            - 'gdp': Tăng trưởng GDP tổng sản phẩm quốc nội (theo quý 'Q' hoặc năm 'Y').
            - 'cpi' / 'cpi_overall': Chỉ số giá tiêu dùng (theo tháng 'M').
            - 'xm' / 'import_export': Kim ngạch xuất nhập khẩu (theo tháng 'M').
            - 'interbank' / 'interbank_rate': Lãi suất liên ngân hàng (ON, 1W, 1M...).
            - 'exchange_rate': Tỷ giá USD/VND (Trung tâm, Vietcombank, Tự do).
            - 'fdi': Vốn đầu tư trực tiếp nước ngoài.
            - 'state_budget': Ngân sách nhà nước (thu/chi/thặng dư).
            - 'total_investment': Tổng vốn đầu tư toàn xã hội.
            - 'policy_rate': Lãi suất điều hành (tái cấp vốn, tái chiết khấu).
            - 'omo': Nghiệp vụ thị trường mở OMO.
            - 'credit': Tăng trưởng tín dụng.
            - 'liquidity': Thanh khoản hệ thống ngân hàng.
        start_date: Ngày bắt đầu (YYYY-MM-DD).
        end_date: Ngày kết thúc (YYYY-MM-DD).
        period: Chu kỳ báo cáo ('M', 'Q', 'Y').
        timeout: Thời gian timeout (giây).
    """
    ind_norm = indicator.strip().lower()

    endpoint_map = {
        "gdp": ("macro/GDP", period or "Q"),
        "cpi": ("macro/CPIoverall", period or "M"),
        "cpi_overall": ("macro/CPIoverall", period or "M"),
        "xm": ("macro/XM", period or "M"),
        "import_export": ("macro/XM", period or "M"),
        "fdi": ("macro/FDI", period or "M"),
        "interbank": ("macro/interbankinterest", None),
        "interbank_rate": ("macro/interbankinterest", None),
        "exchange_rate": ("macro/exchangerate", None),
        "state_budget": ("macro/stateBudget", period or "Q"),
        "total_investment": ("macro/totalInvestment", period or "Q"),
        "policy_rate": ("macro/policyRate", None),
        "omo": ("macro/omo", None),
        "credit": ("macro/creditGrTotal", period or "Q"),
        "liquidity": ("macro/liquidity", period or "Q"),
    }

    if ind_norm not in endpoint_map:
        raise ValueError(f"Chỉ số vĩ mô '{indicator}' không được hỗ trợ. Các chỉ số: {list(endpoint_map.keys())}")

    path, default_period = endpoint_map[ind_norm]

    # Format ngày MM-DD-YYYY theo chuẩn ASEAN API
    start_fmt = _format_asean_date(start_date, default_years=5)
    end_fmt = dt.datetime.strptime(end_date, "%Y-%m-%d").strftime("%m-%d-%Y") if end_date else dt.datetime.now().strftime("%m-%d-%Y")

    url = f"https://asean-apigw.aseansc.com.vn/pbapi/api/{path}?startDate={start_fmt}&endDate={end_fmt}"
    if default_period:
        url += f"&period={default_period}"
    if "interbank" in ind_norm:
        url += f"&interestperiod={period or 'ON'}"

    req = urllib.request.Request(url, headers=ASEAN_HEADERS, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Lỗi khi truy vấn ASEAN Macro [%s]: %s", ind_norm, exc)
        raise

    items = data.get("data", [])
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)
    if "reportDate" in df.columns:
        df["reportDate"] = pd.to_datetime(df["reportDate"], errors="coerce")
        df = df.rename(columns={"reportDate": "report_date"})

    # Chuẩn hóa tên cột sang snake_case
    df.columns = [_camel_to_snake(c) for c in df.columns]

    # Chuyển đổi kiểu số cho tất cả cột trừ report_date
    for col in df.columns:
        if col != "report_date":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "report_date" in df.columns:
        df = df.sort_values("report_date", ascending=True).reset_index(drop=True)

    df.attrs["source"] = "ASEAN_SC_DIRECT"
    df.attrs["indicator"] = ind_norm
    return df
