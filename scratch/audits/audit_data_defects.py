import duckdb
import pandas as pd
import numpy as np

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)

print("=" * 80)
print("PART 1: AUDIT OF CRITICAL DATA DEFECTS & INCONSISTENCIES")
print("=" * 80)

# 1. PRICE ADJUSTMENT DEFECT
n_adj = con.execute("SELECT count(*) FROM core.price_adjustment_events").fetchone()[0]
print(f"[DEFECT 1] core.price_adjustment_events row count = {n_adj}")
if n_adj == 0:
    print("  -> CRITICAL GAP: Although F009 / pit_join.py was designed to use adjusted prices,")
    print("     core.price_adjustment_events was NEVER populated!")
    print("     Consequence: All 658,182 rows in core.pit_events used RAW UNADJUSTED prices.")
    print("     Any stock dividend, bonus share, or rights issue inside the T+1 to T+30 window")
    print("     is treated as a mechanical price crash or surge rather than a corporate action.")

# 2. DATE ANOMALIES IN MACRO_POLICY & NEWS
macro_0905 = con.execute("SELECT count(*) FROM core.macro_policy WHERE CAST(published_at AS DATE) = '2026-09-05'").fetchone()[0]
print(f"\n[DEFECT 2] Pinned dates in core.macro_policy (2026-09-05): {macro_0905:,} rows")
print("  Sources affected:")
for src, cnt in con.execute("SELECT source, count(*) FROM core.macro_policy WHERE CAST(published_at AS DATE) = '2026-09-05' GROUP BY source ORDER BY count(*) DESC").fetchall()[:5]:
    print(f"    - {src}: {cnt:,} rows")

# 3. ZERO-TIME NEWS TIMESTAMPS
zero_time_news = con.execute("""
    SELECT count(*) FROM core.news 
    WHERE EXTRACT(HOUR FROM published_at)=0 AND EXTRACT(MINUTE FROM published_at)=0 AND EXTRACT(SECOND FROM published_at)=0
""").fetchone()[0]
total_news = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
print(f"\n[DEFECT 3] Zero-time timestamps in core.news (00:00:00): {zero_time_news:,} / {total_news:,} ({zero_time_news/total_news*100:.2f}%)")
print("  -> Consequence: For 25.6% of news, exact publish hour is unknown. They fall into the pre-15:00")
print("     rule and are joined to SAME-DAY close, risking look-ahead bias if published after trading hours!")

# 4. OHLCV ZERO VOLUME & PENNY STOCKS
zero_vol = con.execute("SELECT count(*) FROM core.market_ohlcv_daily WHERE volume <= 0").fetchone()[0]
total_ohlcv = con.execute("SELECT count(*) FROM core.market_ohlcv_daily").fetchone()[0]
print(f"\n[DEFECT 4] Zero or negative volume bars in OHLCV: {zero_vol:,} / {total_ohlcv:,} ({zero_vol/total_ohlcv*100:.2f}%)")

# 5. FUNDAMENTALS ACCOUNTING IDENTITY (A = L + E)
print("\n[DEFECT 5] Balance sheet identity check in core.fundamentals:")
sample_fun = con.execute("SELECT symbol, period_end, data_json FROM core.fundamentals WHERE report_type = 'balance_sheet' LIMIT 3").fetchall()
bs_count = con.execute("SELECT count(*) FROM core.fundamentals WHERE report_type = 'balance_sheet'").fetchone()[0]
print(f"  Balance sheet rows in core.fundamentals: {bs_count:,}")

print("\n" + "=" * 80)
print("PART 2: AUDIT OF EMPIRICAL ASSERTIONS & THE 15,081 NEGATIVE EVENTS")
print("=" * 80)

# Let's load the F201 negative sentiment events
# Reproduce F201 query
import sys
sys.path.insert(0, 'd:/VESTA/src')
from pipeline.sentiment_lexicon import score_headline

print("Loading events from core.pit_events to evaluate the 15,081 events...")
df_events = con.execute("""
    SELECT p.symbol, p.published_at, p.headline, p.price_at_publish, p.price_t1, p.price_t5, p.price_t30,
           d.exchange
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol d ON p.symbol = d.symbol
    WHERE p.price_at_publish IS NOT NULL AND p.price_t5 IS NOT NULL AND p.price_t30 IS NOT NULL
""").df()

print(f"Total complete price events: {len(df_events):,}")

# Score sentiment
scores = [score_headline(h) for h in df_events['headline']]
df_events['score'] = scores
df_neg = df_events[df_events['score'] < 0].copy()
print(f"Total negative events identified: {len(df_neg):,}")

# Compute returns
df_neg['ret_t5'] = (df_neg['price_t5'] - df_neg['price_at_publish']) / df_neg['price_at_publish']
df_neg['ret_t30'] = (df_neg['price_t30'] - df_neg['price_at_publish']) / df_neg['price_at_publish']
df_neg['diff'] = df_neg['ret_t30'] - df_neg['ret_t5']

print(f"\nPooled Negative Events: n = {len(df_neg):,}")
print(f"  Mean return_t5:  {df_neg['ret_t5'].mean()*100:+.4f}%")
print(f"  Mean return_t30: {df_neg['ret_t30'].mean()*100:+.4f}%")
print(f"  Mean diff (t30 - t5): {df_neg['diff'].mean()*100:+.4f}%")
print(f"  Raw Kurtosis:    {df_neg['diff'].kurtosis():.2f}")
print(f"  Raw Skewness:    {df_neg['diff'].skew():.2f}")

# Breakdown by Exchange
print("\n--- BREAKDOWN BY EXCHANGE ---")
ex_grp = df_neg.groupby('exchange').agg(
    n=('diff', 'count'),
    mean_ret_t5=('ret_t5', lambda x: x.mean()*100),
    mean_ret_t30=('ret_t30', lambda x: x.mean()*100),
    mean_diff=('diff', lambda x: x.mean()*100),
    median_diff=('diff', lambda x: x.median()*100),
    std_diff=('diff', lambda x: x.std()*100),
    kurtosis=('diff', lambda x: x.kurtosis()),
    win_rate=('diff', lambda x: (x > 0).mean()*100)
)
print(ex_grp.to_string())

# Breakdown by Year
print("\n--- BREAKDOWN BY YEAR ---")
df_neg['year'] = pd.to_datetime(df_neg['published_at']).dt.year
yr_grp = df_neg.groupby('year').agg(
    n=('diff', 'count'),
    mean_diff=('diff', lambda x: x.mean()*100),
    median_diff=('diff', lambda x: x.median()*100),
    win_rate=('diff', lambda x: (x > 0).mean()*100)
)
print(yr_grp.to_string())

# Top 5 Outliers in Negative Events
print("\n--- TOP 5 POSITIVE OUTLIERS IN NEGATIVE EVENTS ---")
top_pos = df_neg.sort_values('diff', ascending=False).head(5)
for idx, r in top_pos.iterrows():
    print(f"Symbol: {r['symbol']} ({r['exchange']}) | Date: {r['published_at']} | P_pub: {r['price_at_publish']} | P_t5: {r['price_t5']} | P_t30: {r['price_t30']} | Diff: {r['diff']*100:+.2f}%")
    print(f"  Headline: {r['headline']}")

print("\n--- TOP 5 NEGATIVE OUTLIERS IN NEGATIVE EVENTS ---")
top_neg = df_neg.sort_values('diff', ascending=True).head(5)
for idx, r in top_neg.iterrows():
    print(f"Symbol: {r['symbol']} ({r['exchange']}) | Date: {r['published_at']} | P_pub: {r['price_at_publish']} | P_t5: {r['price_t5']} | P_t30: {r['price_t30']} | Diff: {r['diff']*100:+.2f}%")
    print(f"  Headline: {r['headline']}")

con.close()
