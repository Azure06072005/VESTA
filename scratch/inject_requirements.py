"""
Inject 'requirements' key into all F0xx features in Harness/feature_list.json.
Requirements define:
- target_universe: full index, symbols, or specific asset class
- min_date: earliest date (min 2000-01-01 or market/asset inception)
- max_date: CURRENT_DATE (istoday())
- cadence: DAILY, INTRADAY_1M, QUARTERLY, EVENT_DRIVEN, REALTIME
- depth_rule: Deep historical from year 2000 to today, or retention window
- freshness_sla: T-0 / T-1
- exception_rule: note for limited range datasets
"""
import json
from pathlib import Path

FEATURE_FILE = Path("Harness/feature_list.json")

with open(FEATURE_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

for feat in data["features"]:
    fid = feat["id"]
    if not fid.startswith("F0"):
        continue

    # Default requirement template
    req = {
        "target_universe": "FULL_UNIVERSE (1,751 symbols across HOSE, HNX, UPCOM) + 22 Benchmark Indices",
        "min_date": "2000-01-01",
        "max_date": "CURRENT_DATE (istoday())",
        "cadence": "DAILY",
        "depth_rule": "DEEP_HISTORICAL: Ingest full historical records back to year 2000 (or earliest market listing)",
        "freshness_sla": "T-0 (Latest Available Trading Session)",
        "exception_rule": None
    }

    # Customizations based on feature specialization
    if fid in ("F000", "F009", "F072"):
        req["target_universe"] = "ALL_SYSTEM_TABLES"
        req["cadence"] = "PIPELINE_LIFECYCLE"
        req["depth_rule"] = "Full schema and audit consistency verification"
        req["freshness_sla"] = "ON_COMMIT"

    elif fid in ("F001", "F001b", "F001c"):
        req["target_universe"] = "FULL_EQUITY_UNIVERSE (1,751 symbols) + VN30/VN100/VNFINLEAD/VNDIAMOND/HNX30 baskets"
        req["cadence"] = "DAILY_REFERENCE_REFRESH"
        req["depth_rule"] = "Master reference metadata for all active, suspended, and delisted Vietnamese equities"
        req["freshness_sla"] = "T-0"

    elif fid == "F002":
        req["target_universe"] = "FULL_EQUITY_UNIVERSE (1,751 symbols across HOSE, HNX, UPCOM)"
        req["min_date"] = "2000-07-28"  # HOSE opening day
        req["cadence"] = "DAILY"
        req["depth_rule"] = "Full daily OHLCV candlestick history from inception (2000) to current date"
        req["freshness_sla"] = "T-0 (End-of-day daily bar after 15:30 ICT)"

    elif fid == "F002b":
        req["target_universe"] = "VN30 universe + High-liquidity tier (>1B VND daily turn)"
        req["min_date"] = "2023-01-01"
        req["cadence"] = "INTRADAY_1M"
        req["depth_rule"] = "Rolling 3-year intraday 1-minute microstructure bars"
        req["freshness_sla"] = "T-0"
        req["exception_rule"] = "Intraday 1M storage is bounded to rolling 3-year window (2023 - Present) to balance duckdb disk size (22.8M rows = ~1.8GB)"

    elif fid in ("F003", "F004", "F004b", "F004c", "F004d"):
        req["target_universe"] = "ALL_LISTED_SYMBOLS + Macro/Industry Channels"
        req["min_date"] = "2005-01-01"
        req["cadence"] = "HOURLY_INCREMENTAL"
        req["depth_rule"] = "Exhaustive financial news lakehouse back to 2005"
        req["freshness_sla"] = "T-0 (< 15 mins publication lag)"
        req["exception_rule"] = "Online financial journalism archives begin reliably from 2005 onwards"

    elif fid in ("F005", "F052", "F053"):
        req["target_universe"] = "FULL_EQUITY_UNIVERSE (1,751 symbols)"
        req["min_date"] = "2000-Q1"
        req["cadence"] = "QUARTERLY / ANNUAL"
        req["depth_rule"] = "Point-in-time financial statements (BS, IS, CF, Ratios) across all reporting quarters since 2000"
        req["freshness_sla"] = "T+45 days post-quarter end (per SSC disclosure regulation)"

    elif fid == "F006":
        req["target_universe"] = "FULL_EQUITY_UNIVERSE (1,751 symbols)"
        req["min_date"] = "2000-01-01"
        req["cadence"] = "EVENT_DRIVEN"
        req["depth_rule"] = "Historical corporate events (dividends, cash/stock, bonus shares, AGM/EGM, rights issues)"
        req["freshness_sla"] = "T-0 on corporate announcement"

    elif fid in ("F007", "F007b"):
        req["target_universe"] = "FULL_EQUITY_UNIVERSE + Realtime Market Stream"
        req["cadence"] = "REALTIME_TICK / DAILY_CLOSE"
        req["depth_rule"] = "Live order book snapshots, screener metrics, valuation multiples"
        req["freshness_sla"] = "T-0 Realtime / EOD"
        req["exception_rule"] = "Market live snapshots maintain rolling 30-day window; screener and valuation compute EOD historical series"

    elif fid == "F050":
        req["target_universe"] = "22 Benchmark Indices (VNINDEX, VN30, HNX, HNX30, UPCOM, VN100, VNFINLEAD, VNDIAMOND, VNMID, VNSML, etc.)"
        req["min_date"] = "2000-07-28"
        req["cadence"] = "DAILY"
        req["depth_rule"] = "Exhaustive index OHLCV history from HOSE launch date to current date"
        req["freshness_sla"] = "T-0"

    elif fid == "F051":
        req["target_universe"] = "ALL_LISTED_SYMBOLS + Exchange-wide foreign aggregates"
        req["min_date"] = "2005-01-01"
        req["cadence"] = "DAILY"
        req["depth_rule"] = "Daily foreign investor buy/sell volume and net flow value"
        req["freshness_sla"] = "T-0 (EOD after 15:30 ICT)"

    elif fid == "F054":
        req["target_universe"] = "TOP_SECTORS & VN100 research coverage"
        req["min_date"] = "2010-01-01"
        req["cadence"] = "DAILY"
        req["depth_rule"] = "Securities brokerage equity research PDFs and price target forecasts"
        req["freshness_sla"] = "T-0"

    elif fid in ("F055", "F056", "F058", "F059", "F060", "F061", "F062", "F063", "F064", "F065", "F066", "F067", "F068", "F069", "F070", "F071"):
        req["target_universe"] = "Macroeconomic, Regulatory, Ministry, and Trade Association RSS/Feeds"
        req["min_date"] = "2010-01-01"
        req["cadence"] = "DAILY_INCREMENTAL"
        req["depth_rule"] = "Full textual regulatory directives, macro indicators, and sector policies"
        req["freshness_sla"] = "T-0"

    elif fid == "F073":
        req["target_universe"] = "All VN30 Index Futures (VN30F1M, VN30F2M, VN30F1Q, VN30F2Q) + Government Bond Futures (GB05F)"
        req["min_date"] = "2017-08-10"  # Vietnam derivatives market inception date
        req["cadence"] = "DAILY"
        req["depth_rule"] = "Complete historical trading history of all expired and active derivative contracts"
        req["freshness_sla"] = "T-0"
        req["exception_rule"] = "Vietnam derivatives exchange commenced operations on 2017-08-10; data before this date does not exist in the market"

    elif fid == "F074":
        req["target_universe"] = "All Covered Warrants (CW) issued on HOSE (SSI, HSC, VPS, VND, KIS, etc.)"
        req["min_date"] = "2019-06-28"  # Vietnam covered warrants inception date
        req["cadence"] = "DAILY"
        req["depth_rule"] = "Complete lifecycle OHLCV, strike price, conversion ratio, and expiry for all CWs"
        req["freshness_sla"] = "T-0"
        req["exception_rule"] = "Vietnam covered warrant market commenced on 2019-06-28; data before this date does not exist in the market"

    elif fid == "F075":
        req["target_universe"] = "All Vietnamese ETFs (E1VFVN30, FUEVFVND, FUESSVFL, FUESSV50, FUEKIV30, FUEIP100, etc.)"
        req["min_date"] = "2014-10-06"  # E1VFVN30 inception date
        req["cadence"] = "DAILY"
        req["depth_rule"] = "Full trading history, NAV per unit, basket constituent weights, and tracking error"
        req["freshness_sla"] = "T-0"
        req["exception_rule"] = "First ETF in Vietnam (E1VFVN30) launched in Oct 2014"

    elif fid == "F076":
        req["target_universe"] = "HNX Government Bonds, Municipal Bonds, and Corporate Bond trading board"
        req["min_date"] = "2009-09-24"  # HNX specialized bond trading system launch
        req["cadence"] = "DAILY"
        req["depth_rule"] = "Yield curves, coupon rates, maturity dates, and daily bond trade transactions"
        req["freshness_sla"] = "T-0"
        req["exception_rule"] = "HNX electronic bond trading system inaugurated on 2009-09-24"

    elif fid in ("F095", "F096", "F097", "F098", "F099", "F099b"):
        req["target_universe"] = "FULL_INGESTED_LAKEHOUSE (Equities, Indices, Derivatives, CW, ETF, Bonds, News)"
        req["min_date"] = "2000-01-01"
        req["cadence"] = "PIPELINE_TRANSFORMATION"
        req["depth_rule"] = "Comprehensive normalization, timezone alignment, corporate action adjustment, and anomaly profiling"
        req["freshness_sla"] = "T-0"

    feat["requirements"] = req

with open(FEATURE_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Successfully injected 'requirements' key into all F0xx features in Harness/feature_list.json.")
