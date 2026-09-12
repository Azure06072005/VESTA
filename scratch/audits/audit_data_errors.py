import duckdb
import pandas as pd
import numpy as np
import json
from datetime import datetime

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)

print("=" * 80)
print(" VESTA DATA INTEGRITY & ASSERTION AUDIT REPORT ")
print(" Time:", datetime.now().isoformat())
print("=" * 80)

# -------------------------------------------------------------
# 1. NEWS & MACRO_POLICY DATE & TEXT AUDIT
# -------------------------------------------------------------
print("\n[1] NEWS & MACRO_POLICY AUDIT")
news_count = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
macro_count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
print(f"Total core.news rows: {news_count:,}")
print(f"Total core.macro_policy rows: {macro_count:,}")

# Check future dates (> 2026-09-13)
future_news = con.execute("SELECT count(*) FROM core.news WHERE published_at > '2026-09-13'").fetchone()[0]
pre2000_news = con.execute("SELECT count(*) FROM core.news WHERE published_at < '2000-01-01'").fetchone()[0]
print(f"News with published_at > 2026-09-13: {future_news}")
print(f"News with published_at < 2000-01-01: {pre2000_news}")

# Check 2026-09-05 header clock anomaly
p0905_news = con.execute("SELECT count(*) FROM core.news WHERE CAST(published_at AS DATE) = '2026-09-05'").fetchone()[0]
print(f"News with date = 2026-09-05: {p0905_news}")

macro_0905 = con.execute("""
    SELECT source, count(*) 
    FROM core.macro_policy 
    WHERE CAST(published_at AS DATE) = '2026-09-05' 
    GROUP BY source
""").fetchall()
print(f"Macro_policy with date = 2026-09-05 by source:")
for src, cnt in macro_0905:
    print(f"  - {src}: {cnt:,} rows")

# Check time component in published_at
time_0000_news = con.execute("""
    SELECT count(*) 
    FROM core.news 
    WHERE EXTRACT(HOUR FROM published_at) = 0 
      AND EXTRACT(MINUTE FROM published_at) = 0 
      AND EXTRACT(SECOND FROM published_at) = 0
""").fetchone()[0]
pct_0000 = (time_0000_news / news_count) * 100 if news_count else 0
print(f"News with published_at at exactly 00:00:00 (no intraday time): {time_0000_news:,} ({pct_0000:.2f}%)")

# Nulls in news
null_titles = con.execute("SELECT count(*) FROM core.news WHERE headline IS NULL OR length(trim(headline)) = 0").fetchone()[0]
null_bodies = con.execute("SELECT count(*) FROM core.news WHERE body IS NULL OR length(trim(body)) = 0").fetchone()[0]
print(f"News null/empty headline: {null_titles}, null/empty body: {null_bodies}")

# -------------------------------------------------------------
# 2. OHLCV PRICE GEOMETRY AUDIT
# -------------------------------------------------------------
print("\n[2] OHLCV GEOMETRY AUDIT (core.market_ohlcv_daily)")
ohlcv_count = con.execute("SELECT count(*) FROM core.market_ohlcv_daily").fetchone()[0]
print(f"Total OHLCV rows: {ohlcv_count:,}")

bad_prices = con.execute("""
    SELECT count(*) 
    FROM core.market_ohlcv_daily 
    WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
""").fetchone()[0]
print(f"OHLCV non-positive prices (<=0): {bad_prices}")

bad_high_low = con.execute("""
    SELECT count(*) 
    FROM core.market_ohlcv_daily 
    WHERE high < low
""").fetchone()[0]
print(f"OHLCV High < Low: {bad_high_low}")

bad_open_close = con.execute("""
    SELECT count(*) 
    FROM core.market_ohlcv_daily 
    WHERE open > high OR open < low OR close > high OR close < low
""").fetchone()[0]
print(f"OHLCV Open/Close outside [Low, High]: {bad_open_close}")

zero_volume = con.execute("""
    SELECT count(*) 
    FROM core.market_ohlcv_daily 
    WHERE volume <= 0
""").fetchone()[0]
print(f"OHLCV zero/negative volume: {zero_volume:,} ({(zero_volume/ohlcv_count)*100:.2f}%)")

duplicate_bars = con.execute("""
    SELECT count(*) FROM (
        SELECT symbol, time, count(*) 
        FROM core.market_ohlcv_daily 
        GROUP BY symbol, time 
        HAVING count(*) > 1
    )
""").fetchone()[0]
print(f"Duplicate (symbol, time) bars: {duplicate_bars}")

# -------------------------------------------------------------
# 3. PIT_EVENTS AUDIT & RETURN DISTRIBUTIONS
# -------------------------------------------------------------
print("\n[3] PIT_EVENTS AUDIT (core.pit_events)")
pit_count = con.execute("SELECT count(*) FROM core.pit_events").fetchone()[0]
print(f"Total pit_events: {pit_count:,}")

# Describe columns
cols = [c[0] for c in con.execute("DESCRIBE core.pit_events").fetchall()]
print(f"Columns: {cols}")

# Check look-ahead violations
# Rule: effective_trading_date should NOT be earlier than published_at::date
earlier_trading_date = con.execute("""
    SELECT count(*) 
    FROM core.pit_events 
    WHERE effective_trading_date < CAST(published_at AS DATE)
""").fetchone()[0]
print(f"Look-ahead violation: effective_trading_date < published_at::date: {earlier_trading_date}")

# Check 15:00 cutoff violation
# If published_at has hour >= 15, effective_trading_date MUST be strictly > published_at::date
cutoff_violations = con.execute("""
    SELECT count(*) 
    FROM core.pit_events 
    WHERE EXTRACT(HOUR FROM published_at) >= 15 
      AND effective_trading_date <= CAST(published_at AS DATE)
""").fetchone()[0]
print(f"Cutoff violation: news after 15:00 with effective_trading_date <= publish date: {cutoff_violations}")

# Missing prices in pit_events
null_p_pub = con.execute("SELECT count(*) FROM core.pit_events WHERE price_at_publish IS NULL OR price_at_publish <= 0").fetchone()[0]
null_pt1 = con.execute("SELECT count(*) FROM core.pit_events WHERE price_t1 IS NULL").fetchone()[0]
null_pt5 = con.execute("SELECT count(*) FROM core.pit_events WHERE price_t5 IS NULL").fetchone()[0]
null_pt30 = con.execute("SELECT count(*) FROM core.pit_events WHERE price_t30 IS NULL").fetchone()[0]
print(f"Price at publish NULL or <= 0: {null_p_pub}")
print(f"Missing price_t1: {null_pt1:,} ({(null_pt1/pit_count)*100:.2f}%)")
print(f"Missing price_t5: {null_pt5:,} ({(null_pt5/pit_count)*100:.2f}%)")
print(f"Missing price_t30: {null_pt30:,} ({(null_pt30/pit_count)*100:.2f}%)")

# Quantiles of returns
df_ret = con.execute("""
    SELECT 
        return_t1, return_t5, return_t30,
        (return_t30 - return_t5) as diff_t30_t5
    FROM core.pit_events 
    WHERE return_t5 IS NOT NULL AND return_t30 IS NOT NULL
""").fetchdf()

print(f"\nLoaded {len(df_ret):,} complete events for return distribution analysis:")
quantiles = [0.0001, 0.001, 0.01, 0.05, 0.50, 0.95, 0.99, 0.999, 0.9999]
q_table = df_ret.quantile(quantiles)
print("Return quantiles:")
print(q_table.applymap(lambda x: f"{x*100:+.2f}%"))

# Outlier analysis
diff = df_ret['diff_t30_t5']
print(f"\nDiff (return_t30 - return_t5) summary:")
print(f"  Mean: {diff.mean()*100:+.4f}%")
print(f"  Median: {diff.median()*100:+.4f}%")
print(f"  Std: {diff.std()*100:.4f}%")
print(f"  Skewness: {diff.skew():.2f}")
print(f"  Kurtosis: {diff.kurtosis():.2f}")
print(f"  Min: {diff.min()*100:+.2f}%")
print(f"  Max: {diff.max()*100:+.2f}%")

gt_100pct = (diff.abs() > 1.0).sum()
gt_500pct = (diff.abs() > 5.0).sum()
print(f"  Events with |diff| > 100%: {gt_100pct:,} ({(gt_100pct/len(diff))*100:.3f}%)")
print(f"  Events with |diff| > 500%: {gt_500pct:,}")

# Top 10 extreme positive and negative diffs in pit_events
print("\nTop 5 Extreme Positive Diffs (Potential manipulations, data errors, or reverse splits):")
top_pos = con.execute("""
    SELECT p.symbol, d.exchange, p.published_at, p.effective_trading_date,
           p.price_at_publish, p.price_t5, p.price_t30,
           p.return_t5, p.return_t30, (p.return_t30 - p.return_t5) as diff
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol d ON p.symbol = d.symbol
    WHERE p.return_t5 IS NOT NULL AND p.return_t30 IS NOT NULL
    ORDER BY (p.return_t30 - p.return_t5) DESC
    LIMIT 5
""").fetchdf()
print(top_pos[['symbol', 'exchange', 'published_at', 'price_at_publish', 'price_t5', 'price_t30', 'diff']])

print("\nTop 5 Extreme Negative Diffs (Potential unadjusted splits, dilutive crashes):")
top_neg = con.execute("""
    SELECT p.symbol, d.exchange, p.published_at, p.effective_trading_date,
           p.price_at_publish, p.price_t5, p.price_t30,
           p.return_t5, p.return_t30, (p.return_t30 - p.return_t5) as diff
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol d ON p.symbol = d.symbol
    WHERE p.return_t5 IS NOT NULL AND p.return_t30 IS NOT NULL
    ORDER BY (p.return_t30 - p.return_t5) ASC
    LIMIT 5
""").fetchdf()
print(top_neg[['symbol', 'exchange', 'published_at', 'price_at_publish', 'price_t5', 'price_t30', 'diff']])

# -------------------------------------------------------------
# 4. SENTIMENT BACKTEST SUBSET AUDIT
# -------------------------------------------------------------
print("\n[4] SENTIMENT SUBSET AUDIT (The 15,081 Negative Events)")
# Check how many events have sentiment classified in pit_events
# pit_events has a sentiment column or sentiment_score
sent_counts = con.execute("""
    SELECT sentiment, count(*) 
    FROM core.pit_events 
    GROUP BY sentiment
""").fetchall()
print("Sentiment column distribution in core.pit_events:", sent_counts)

# Let's check how F201 selects negative events
# From F201 evidence: "negative sentiment n=15,081 events"
# Let's see how F201 is implemented
print("=" * 80)
con.close()
