"""Symbol classification and known non-equity exception rules for VESTA.

Relationship to src/crawlers/cafef_symbol_directory.py:
  In `cafef_symbol_directory.py`, directory entries carry `Title` and `RedirectUrl`
  metadata, allowing bonds and funds to be classified via title markers
  ("Trái phiếu...", "Chứng chỉ quỹ...", "Quỹ...") and URL markers ("lich-su-giao-dich-symbol-").
  In contrast, `validate_crossref.py` inspects bare exchange ticker strings from
  market feeds (OHLCV, quotes, news) with no directory metadata.
  
  To prevent parallel logic drift:
  - Covered Warrants DIRECTLY reuses `WARRANT_CODE_PATTERN` from `cafef_symbol_directory`.
  - Corporate Bonds, HNX Derivatives, and ETFs use strictly verified ticker syntax
    patterns that have been proven to have ZERO false positives against the full
    active equity universe (core.dim_symbol union core.dim_symbol_cafef: 2,735 symbols).
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from crawlers.cafef_symbol_directory import WARRANT_CODE_PATTERN  # noqa: E402

# 1. Covered Warrants (Chứng quyền có bảo đảm): directly imported from cafef_symbol_directory.
# Format: 'C' + 2-4 letter underlying stock symbol + 4-digit issuance/expiry code (^C[A-Z]{2,4}\d{4}$).
# Examples: 'CHPG2541', 'CFPT2602', 'CSTB2610'. Lifespan: 3-9 months.
# Verified: 1,974 matches in OHLCV/quotes, exactly 0 false positives against active equities.
COVERED_WARRANT_PATTERN = WARRANT_CODE_PATTERN

# 2. Corporate Bonds (Trái phiếu doanh nghiệp): debt instruments traded on exchange.
# Confirmed 100% against all 79 real bond entries in CafeF directory + market data:
# - Standard exchange debt: 3-4 alphanumeric issuer + 5-6 digits (e.g. 'BID122005', 'BAB123032', 'MSN12202', 'F88126002')
# - HNX private/special tranche: 3-4 letter issuer + 'H' + 7 digits (e.g. 'MSNH2328002', 'MBBH2430001', 'CMXH2326001')
# - Tenor-coded bond tranche: 3-4 letter issuer + 1-2 digit tenor + 'Y' + 6 digits (e.g. 'LPB10Y202204', 'LPB7Y202203')
# Verified: 79/79 bonds matched, exactly 0 false positives against all 2,735 active equities.
CORPORATE_BOND_PATTERN = re.compile(r"^[A-Z0-9]{3,4}(?:H\d{7}|\d{1,2}Y\d{6}|\d{5,6})$")

# 3. HNX Derivatives / Futures Contracts (Hợp đồng tương lai Phái sinh):
# Official HNX derivatives market convention:
# - '41': HNX derivatives product identifier code.
# - 'I': VN30 Index Futures (e.g. '41I1G9000' = VN30 Futures Sept 2026).
# - 'B': Government Bond Futures (e.g. '41B5G9000' = 5Y Govt Bond Futures Sept 2026,
#        '41BAG9000' = 10Y Govt Bond Futures Sept 2026).
# Total length: exactly 9 characters (^41[IB][A-Z0-9]{6}$).
# Verified: exactly 0 false positives against active equities.
HNX_DERIVATIVE_PATTERN = re.compile(r"^41[IB][A-Z0-9]{6}$")

# 4. Exchange-Traded Funds & Fund Certificates (Chứng chỉ quỹ / ETF):
# Tickers traded on HOSE/HNX fund boards.
# Format: 8-character string starting with 'FU' (^FU[A-Z0-9]{6}$) or the flagship
# VFMVN30 ETF series (^E1VFVN\d{2}$).
# Examples: 'E1VFVN30', 'FUEVFVND', 'FUCTVGF4', 'FUESSVFL'.
# Prevents false positive collisions with OTC equities like 'FUTA' (Futabus) or 'E12' (VNECO 12).
# Verified: exactly 0 false positives against active equities.
FUND_ETF_PATTERN = re.compile(r"^(?:FU[A-Z0-9]{6}|E1VFVN\d{2})$")

# 5. Market Indices (Chỉ số thị trường):
# Explicit allowlist of composite market index tickers present in historical market OHLCV feeds.
KNOWN_INDEX_TICKERS = frozenset({
    "VNX-ALL",    # VNX Allshare composite index
    "VNXALL",     # Alternate ticker representation for VNX Allshare
    "HN0-INDEX",  # HNX legacy market index
})

# 6. Documented Permanent Residual Equity Gaps:
# Genuine historical equities with trading rows in market_ohlcv_daily whose companies
# delisted or dissolved years before directory indexing, verified absent from both vnstock
# and CafeF live company directories. Documented in DECISIONS.md per F001 precedent.
PERMANENT_RESIDUAL_EQUITY_GAPS = frozenset({
    # Habubank (Ngân hàng TMCP Nhà Hà Nội): delisted from HNX in August 2012 upon merger
    # into Saigon - Hanoi Bank (SHB). 1 historical trading row from 2011.
    "HBB",
    # Công ty Cổ phần Than Cao Sơn - Vinacomin: delisted from HNX on August 4, 2020 to execute
    # share-swap merger with Than Đèo Nai. 2,506 historical rows (2008-2020), max date 2020-08-03.
    "TCS",
    # Công ty Cổ phần Đầu tư và Xây dựng 40: delisted from UPCoM on February 13, 2014 after
    # no longer meeting public company requirements. 20 historical rows (2011-2013).
    "I40",
    # Temporary OTC/test trading symbol with 3 rows from May 2025.
    "NAN",
})


def is_known_non_dim_symbol(symbol: str) -> bool:
    """Returns True if symbol matches a verified non-equity instrument pattern,
    an explicit market index, or a documented historical residual gap.
    """
    sym = symbol.strip().upper()
    if sym in KNOWN_INDEX_TICKERS:
        return True
    if sym in PERMANENT_RESIDUAL_EQUITY_GAPS:
        return True
    if COVERED_WARRANT_PATTERN.match(sym):
        return True
    if CORPORATE_BOND_PATTERN.match(sym):
        return True
    if HNX_DERIVATIVE_PATTERN.match(sym):
        return True
    if FUND_ETF_PATTERN.match(sym):
        return True
    return False
