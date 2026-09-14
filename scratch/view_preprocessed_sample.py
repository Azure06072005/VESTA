"""scratch/view_preprocessed_sample.py

Views formatted samples from test_pipeline/db/vesta_preprocessed.duckdb
"""
import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("test_pipeline/db/vesta_preprocessed.duckdb", read_only=True)
df = con.execute("""
    SELECT 
        symbol,
        exchange,
        event_date,
        is_midnight_ts,
        headline_clean,
        sentiment_score,
        rankgauss_sentiment_z,
        p0,
        p5,
        p30,
        ret_t5_pct,
        ret_t30_pct,
        raw_diff_pct,
        winsorized_diff_pct,
        market_regime,
        vnindex_fracdiff_d020,
        rankgauss_volume_z
    FROM preprocessed_features 
    ORDER BY event_date DESC
    LIMIT 6
""").df()
con.close()

print("=== 6 SAMPLE PREPROCESSED RECORDS FROM test_pipeline/db/vesta_preprocessed.duckdb ===")
for idx, r in df.iterrows():
    print(f"\n--- [Record {idx+1}] Mã: {r['symbol']} ({r['exchange']}) | Ngày: {r['event_date']} | Giờ nửa đêm T+1: {r['is_midnight_ts']} ---")
    print(f" Tiêu đề sạch (Text Cleaned) : {r['headline_clean']}")
    print(f" Sentiment Gốc -> RankGauss Z: {r['sentiment_score']:.2f} -> {r['rankgauss_sentiment_z']:.4f} sigma")
    print(f" Giá P0 -> P5 -> P30        : {r['p0']:.2f} -> {r['p5']:.2f} -> {r['p30']:.2f}")
    print(f" Lợi nhuận T+5 / T+30        : {r['ret_t5_pct']:+.2f}% / {r['ret_t30_pct']:+.2f}%")
    print(f" Biến động Gốc -> Winsorized : {r['raw_diff_pct']:+.2f}% -> {r['winsorized_diff_pct']:+.2f}%")
    print(f" Chế độ Thị trường (Regime)  : {r['market_regime']}")
    print(f" VNINDEX FracDiff (d=0.20)   : {r['vnindex_fracdiff_d020']:.4f}")
    print(f" Rolling RankGauss Volume Z  : {r['rankgauss_volume_z']:.4f} sigma")
