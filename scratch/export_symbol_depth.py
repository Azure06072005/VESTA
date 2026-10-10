import duckdb
import json
import pathlib
import pandas as pd

out_dir = pathlib.Path("out")
out_dir.mkdir(parents=True, exist_ok=True)

con = duckdb.connect("db/admin/vesta_ohlcv.duckdb", read_only=True)
df = con.execute("""
    SELECT 
        symbol, 
        COUNT(*) as bar_count, 
        MIN(date::DATE) as min_date, 
        MAX(date::DATE) as max_date,
        ROUND(DATEDIFF('day', MIN(date::DATE), MAX(date::DATE)) / 365.25, 2) as years_span
    FROM core.market_ohlcv_daily
    GROUP BY symbol
""").fetchdf()
con.close()

list_10y = df[df['years_span'] >= 10.0].sort_values(['years_span', 'bar_count'], ascending=[False, False])
list_5y = df[(df['years_span'] >= 5.0) & (df['years_span'] < 10.0)].sort_values(['years_span', 'bar_count'], ascending=[False, False])
list_1y = df[(df['years_span'] >= 1.0) & (df['years_span'] < 5.0)].sort_values(['years_span', 'bar_count'], ascending=[False, False])
list_under_1y = df[df['years_span'] < 1.0].sort_values(['years_span', 'bar_count'], ascending=[False, False])

summary = {
    "total_symbols": len(df),
    "list_over_10_years": {
        "count": len(list_10y),
        "symbols": list_10y['symbol'].tolist(),
        "top_sample": list_10y.head(50).to_dict(orient='records')
    },
    "list_over_5_years": {
        "count": len(list_5y),
        "symbols": list_5y['symbol'].tolist(),
        "top_sample": list_5y.head(50).to_dict(orient='records')
    },
    "list_over_1_year": {
        "count": len(list_1y),
        "symbols": list_1y['symbol'].tolist(),
        "top_sample": list_1y.head(50).to_dict(orient='records')
    },
    "under_1_year": {
        "count": len(list_under_1y),
        "note": "Phần lớn là chứng quyền ngắn hạn (CW) và cổ phiếu mới chào sàn UPCOM/HOSE",
        "sample": list_under_1y['symbol'].head(30).tolist()
    }
}

with open(out_dir / "symbol_depth_classification.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

print(f"Exported symbol_depth_classification.json successfully.")
print(f"- Over 10 years: {len(list_10y)} symbols")
print(f"- Over 5 years (5-10y): {len(list_5y)} symbols (including NVL: {len(df[df['symbol']=='NVL'])} rows, span {df[df['symbol']=='NVL']['years_span'].values[0]} years)")
print(f"- Over 1 year (1-5y): {len(list_1y)} symbols")
print(f"- Under 1 year: {len(list_under_1y)} symbols")
