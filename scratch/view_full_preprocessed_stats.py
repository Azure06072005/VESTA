"""scratch/view_full_preprocessed_stats.py

Extracts complete statistics and real sample records from db/vesta_preprocessed_full.duckdb
"""
import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_preprocessed_full.duckdb", read_only=True)

print("=" * 85)
print("FULL-SCALE PRODUCTION PREPROCESSED DATABASE AUDIT")
print("Database File: db/vesta_preprocessed_full.duckdb")
print("=" * 85)

print("\n1. TABLE ROW COUNTS:")
for tbl in ["market_regimes", "macro_policy", "events"]:
    cnt = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
    print(f" -> Table '{tbl:<15}' : {cnt:>10,} rows")

print("\n2. MACRO POLICY PILLARS BREAKDOWN (Total: 477,733 docs):")
df_pol = con.execute("""
    SELECT policy_pillar, count(*) as cnt 
    FROM macro_policy 
    GROUP BY policy_pillar 
    ORDER BY cnt DESC 
    LIMIT 8
""").df()
print(df_pol.to_string(index=False))

print("\n3. PREPROCESSED EVENTS REGIME BREAKDOWN (Total: 581,944 events):")
df_reg = con.execute("""
    SELECT market_regime, count(*) as cnt, 
           round(avg(winsorized_diff_pct), 2) as avg_diff,
           round(avg(ret_t5_pct), 2) as avg_t5,
           round(avg(ret_t30_pct), 2) as avg_t30
    FROM events 
    GROUP BY market_regime 
    ORDER BY cnt DESC
""").df()
print(df_reg.to_string(index=False))

print("\n4. 5 SAMPLE REAL PREPROCESSED EVENTS (BLUECHIP & MIDCAP):")
df_samples = con.execute("""
    SELECT symbol, exchange, event_date, is_midnight_ts, 
           headline_clean, sentiment_score, rankgauss_sentiment_z,
           p0, p5, p30, winsorized_diff_pct, market_regime, 
           vni_fracdiff_d020, rankgauss_volume_z
    FROM events
    WHERE symbol IN ('HPG', 'VCB', 'FPT', 'SSI', 'VHM')
      AND sentiment_score != 0
    ORDER BY event_date DESC
    LIMIT 5
""").df()

for idx, r in df_samples.iterrows():
    print(f"\n[Sample {idx+1}] Mã: {r['symbol']} ({r['exchange']}) | Ngày: {r['event_date']} | Chế độ: {r['market_regime']}")
    print(f" Tiêu đề sạch       : {r['headline_clean']}")
    print(f" Sentiment -> Z-score: {r['sentiment_score']:.2f} -> {r['rankgauss_sentiment_z']:.4f} sigma")
    print(f" Giá P0 -> P5 -> P30: {r['p0']:.2f} -> {r['p5']:.2f} -> {r['p30']:.2f} | Biến động: {r['winsorized_diff_pct']:+.2f}%")
    print(f" VNINDEX FracDiff   : {r['vni_fracdiff_d020']:.4f} | Volume Z: {r['rankgauss_volume_z']:.4f} sigma")

con.close()
