import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
sample_query = """
SELECT symbol, snapshot_date, exchange, price, market_cap, data_json, source
FROM core.market_screener_snapshot
WHERE symbol IN ('FPT', 'VNM', 'HPG') AND year(snapshot_date) IN (2010, 2018, 2024)
ORDER BY symbol, snapshot_date;
"""
df = con.execute(sample_query).df()
print("=== MẪU DỮ LIỆU HISTORICAL FACTOR SCREENER 2005 - 2026 ===")
for idx, r in df.iterrows():
    print(f"[{r['symbol']}] Ngày: {r['snapshot_date']} | Sàn: {r['exchange']} | Giá: {r['price']:,.0f} | Vốn hóa: {r['market_cap']/1e9:,.1f} tỷ | Chỉ số: {r['data_json']}")

con.close()
