"""
Phân tích chi tiết 7 khuyết tật dữ liệu phát hiện bởi F103 trên 3 Lakehouses.
"""
import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_news.duckdb' AS news_db (READ_ONLY);")

print("=" * 80)
print("CHI TIẾT 7 KHUYẾT TẬT DỮ LIỆU F103")
print("=" * 80)

# 1. Phân tích 11,548 dòng close <= 0 và 94 dòng close > 2000
print("\n[1] PHÂN TÍCH OHLCV RANGE OUTLIERS (close <= 0 & close > 2000):")
sample_zero = con.execute("""
    SELECT symbol, count(*) as cnt, min(date) as min_d, max(date) as max_d, avg(volume) as avg_vol
    FROM ohlcv_db.core.market_ohlcv_daily
    WHERE close <= 0
    GROUP BY symbol
    ORDER BY cnt DESC
    LIMIT 10
""").df()
print("Top 10 mã có close <= 0:")
print(sample_zero.to_string(index=False))

sample_high = con.execute("""
    SELECT symbol, date, open, high, low, close, volume
    FROM ohlcv_db.core.market_ohlcv_daily
    WHERE close > 2000.0
    LIMIT 5
""").df()
print("\nMẫu các dòng có close > 2000:")
print(sample_high.to_string(index=False))

# 2. Phân tích 23 URL lỗi protocol trong 1.15M tin tức
print("\n[2] PHÂN TÍCH 23 TIN TỨC CÓ URL LỖI PROTOCOL:")
bad_urls = con.execute("""
    SELECT source, source_url, headline, published_at
    FROM news_db.core.news
    WHERE source_url IS NOT NULL 
      AND NOT regexp_matches(source_url, '^(https?://|vnstock://|cafef://|baochinhphu://|vietstock://)')
    LIMIT 10
""").df()
print(bad_urls.to_string(index=False))

# 3. Phân tích 15 dòng nến High < Low
print("\n[3] PHÂN TÍCH 15 DÒNG NẾN BẤT KHẢ THI (High < Low):")
inverted_candles = con.execute("""
    SELECT symbol, date, open, high, low, close, volume
    FROM ohlcv_db.core.market_ohlcv_daily
    WHERE high < low
""").df()
print(inverted_candles.to_string(index=False))

# 4. Phân tích 73 BCTC mất cân đối A != L + E
print("\n[4] PHÂN TÍCH BCTC MẤT CÂN ĐỐI KẾ TOÁN (A != L + E):")
imbalanced_bs = con.execute("""
    WITH bs AS (
        SELECT 
            symbol, period_end,
            CAST(json_extract(data_json, '$.BS_TOTAL_ASSETS') AS DOUBLE) as assets,
            CAST(json_extract(data_json, '$.BS_TOTAL_LIABILITIES_AND_EQUITY') AS DOUBLE) as liab_eq
        FROM core.fundamentals
        WHERE report_type = 'balance_sheet'
    )
    SELECT symbol, period_end, assets, liab_eq, (assets - liab_eq) as diff
    FROM bs
    WHERE assets IS NOT NULL AND liab_eq IS NOT NULL AND abs(assets - liab_eq) > 1000000.0
    ORDER BY abs(assets - liab_eq) DESC
    LIMIT 10
""").df()
print(imbalanced_bs.to_string(index=False))

# 5. Phân tích 148 dòng PIT Events rò rỉ Lookahead Leakage
print("\n[5] PHÂN TÍCH 148 DÒNG PIT EVENTS RÒ RỈ LOOKAHEAD LEAKAGE (>15:00 NEO VÀO T0):")
leak_symbols = con.execute("""
    WITH ohlcv_with_next AS (
        SELECT symbol, date, close,
               LEAD(date) OVER (PARTITION BY symbol ORDER BY date) as next_date,
               LEAD(close) OVER (PARTITION BY symbol ORDER BY date) as next_close
        FROM ohlcv_db.core.market_ohlcv_daily
    )
    SELECT p.symbol, count(*) as leak_count, min(p.published_at) as earliest_leak, max(p.published_at) as latest_leak
    FROM core.pit_events p
    JOIN ohlcv_with_next o 
      ON p.symbol = o.symbol AND CAST(p.published_at AS DATE) = o.date
    WHERE CAST(p.published_at AS TIME) >= '15:00:00'
      AND o.next_close IS NOT NULL
      AND o.next_close != o.close
      AND p.price_at_publish = o.close
      AND p.price_at_publish != o.next_close
    GROUP BY p.symbol
    ORDER BY leak_count DESC
    LIMIT 10
""").df()
print(leak_symbols.to_string(index=False))

# 6. Phân tích 2,034 mã trong OHLCV chưa đăng ký trong dim_symbol
print("\n[6] PHÂN TÍCH 2,034 MÃ CHỨNG KHOÁN NGOẠI LAI TRONG OHLCV:")
unreg_sample = con.execute("""
    WITH valid_syms AS (
        SELECT symbol FROM core.dim_symbol
        UNION
        SELECT symbol FROM core.dim_symbol_cafef
    )
    SELECT 
        CASE 
            WHEN regexp_matches(symbol, '^VN30F[0-9]{4}$') THEN 'Phái sinh VN30 Future'
            WHEN regexp_matches(symbol, '^C[A-Z0-9]{8}$') THEN 'Chứng quyền có bảo đảm (CW)'
            WHEN regexp_matches(symbol, '^E1VFVN30|FUESSV30|FUEVFVND') THEN 'Chứng chỉ quỹ ETF'
            WHEN regexp_matches(symbol, '^[A-Z0-9]{3}_[0-9]{4}$') THEN 'Trái phiếu doanh nghiệp'
            ELSE 'Cổ phiếu / Mã khác'
        END as asset_class,
        count(DISTINCT symbol) as unique_symbols,
        count(*) as total_bars
    FROM ohlcv_db.core.market_ohlcv_daily
    WHERE symbol NOT IN (SELECT symbol FROM valid_syms)
      AND NOT regexp_matches(symbol, '^(VNINDEX|HNXIndex|UpcomIndex|VN30|VN100|VNALL)$')
    GROUP BY asset_class
    ORDER BY total_bars DESC
""").df()
print(unreg_sample.to_string(index=False))
