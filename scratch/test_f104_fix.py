"""
Thử nghiệm sửa đổi logic trích xuất đặc trưng của F104:
1. Đọc đúng nến từ ohlcv_db.core.market_ohlcv_daily (4.09M nến)
2. Đọc đúng tỷ số tài chính từ nested 'ratio' dict (RT_VALUE_PE, RT_VALUE_PB, RT_PRT_ROE)
"""
import sys
import duckdb
import json
import math
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")

# 1. Hàm extract fundamental nâng cấp
def extract_fundamental_features_v2(fundamentals_json: str | None) -> dict[str, float | None]:
    if not fundamentals_json:
        return {"pe_ratio": None, "pb_ratio": None, "roe": None}
    try:
        data = json.loads(fundamentals_json)
        if not isinstance(data, dict):
            return {"pe_ratio": None, "pb_ratio": None, "roe": None}

        # Tìm cả ở root lẫn trong sub-dict 'ratio'
        lookup = {str(k).upper(): v for k, v in data.items()}
        if "RATIO" in lookup and isinstance(lookup["RATIO"], dict):
            for rk, rv in lookup["RATIO"].items():
                lookup[str(rk).upper()] = rv

        def _get_float(*keys: str) -> float | None:
            for k in keys:
                ku = k.upper()
                if ku in lookup and lookup[ku] is not None:
                    try:
                        val = float(lookup[ku])
                        if not math.isnan(val) and not math.isinf(val):
                            return val
                    except (ValueError, TypeError):
                        pass
            return None

        pe = _get_float("RT_VALUE_PE", "PE", "PRICE_TO_EARNINGS", "RT_PE", "P/E")
        pb = _get_float("RT_VALUE_PB", "PB", "PRICE_TO_BOOK", "RT_PB", "P/B")
        roe = _get_float("RT_PRT_ROE", "ROE", "RETURN_ON_EQUITY", "RT_ROE")
        return {"pe_ratio": pe, "pb_ratio": pb, "roe": roe}
    except Exception:
        return {"pe_ratio": None, "pb_ratio": None, "roe": None}

# 2. Test trên các mã có BCTC trong pit_events
symbols_in_pit = con.execute("SELECT symbol, count(fundamentals_json) as cnt FROM core.pit_events WHERE fundamentals_json IS NOT NULL GROUP BY symbol ORDER BY cnt DESC LIMIT 5").fetchall()
print("Top symbols with fundamentals in pit_events:", symbols_in_pit)
test_sym = symbols_in_pit[0][0]

sample_events = con.execute(f"""
    SELECT symbol, published_at, headline, fundamentals_json, price_at_publish, price_t1, price_t5, price_t30
    FROM core.pit_events
    WHERE symbol = '{test_sym}' AND fundamentals_json IS NOT NULL
    LIMIT 5
""").df()

print(f"=== TEST FUNDAMENTALS EXTRACTION V2 TRÊN {test_sym} ===")
for idx, row in sample_events.iterrows():
    f = extract_fundamental_features_v2(row["fundamentals_json"])
    print(f"[{row['symbol']}] Date: {row['published_at']} | P/E: {f['pe_ratio']} | P/B: {f['pb_ratio']} | ROE: {f['roe']}")

# 3. Test momentum với ohlcv_db
print(f"\n=== TEST MOMENTUM ENGINE VỚI OHLCV_DB TRÊN {test_sym} ===")
vectorized_sql = f"""
WITH daily_returns AS (
    SELECT 
        symbol,
        date,
        close,
        CASE WHEN LAG(close, 1) OVER w > 0 THEN (close - LAG(close, 1) OVER w) / LAG(close, 1) OVER w ELSE NULL END AS ret_1d,
        CASE WHEN LAG(close, 5) OVER w > 0 THEN (close - LAG(close, 5) OVER w) / LAG(close, 5) OVER w ELSE NULL END AS mom_5d,
        CASE WHEN LAG(close, 20) OVER w > 0 THEN (close - LAG(close, 20) OVER w) / LAG(close, 20) OVER w ELSE NULL END AS mom_20d
    FROM ohlcv_db.core.market_ohlcv_daily
    WHERE symbol = '{test_sym}' AND close > 0
    WINDOW w AS (PARTITION BY symbol ORDER BY date)
),
daily_stats AS (
    SELECT 
        symbol,
        date,
        close,
        ret_1d AS mom_1d,
        mom_5d,
        mom_20d,
        STDDEV_SAMP(ret_1d) OVER (
            PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS vol_20d
    FROM daily_returns
),
events AS (
    SELECT 
        symbol,
        published_at,
        CAST(published_at AS DATE) AS effective_date,
        headline,
        price_at_publish,
        price_t1,
        price_t5,
        price_t30,
        fundamentals_json
    FROM core.pit_events e
    WHERE symbol = '{test_sym}'
    ORDER BY published_at ASC
    LIMIT 5
)
SELECT 
    e.symbol,
    e.published_at,
    e.effective_date,
    s.close,
    s.mom_1d,
    s.mom_5d,
    s.mom_20d,
    s.vol_20d
FROM events e
ASOF JOIN daily_stats s
  ON e.symbol = s.symbol AND e.effective_date >= s.date
"""
df_mom = con.execute(vectorized_sql).df()
print(df_mom.to_string(index=False))

con.close()
