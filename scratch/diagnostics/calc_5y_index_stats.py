import duckdb
import numpy as np
import pandas as pd

con = duckdb.connect("db/vesta.duckdb", read_only=True)
df = con.execute("""
    SELECT date, index_code, close
    FROM core.market_index_daily
    WHERE index_code IN ('VNINDEX', 'HNX-INDEX') AND date >= '2021-09-01'
    ORDER BY date
""").fetchdf()

p = df.pivot(index="date", columns="index_code", values="close").dropna()
ret = p.pct_change().dropna()

print("--- 5-YEAR BENCHMARK INDEX PERFORMANCE (2021-09-01 to 2026-09-07) ---")
for c in ["VNINDEX", "HNX-INDEX"]:
    start_val = p[c].iloc[0]
    end_val = p[c].iloc[-1]
    total_ret = (end_val / start_val - 1) * 100
    cagr = ((end_val / start_val) ** (1 / 5.0) - 1) * 100
    ann_vol = ret[c].std() * np.sqrt(252) * 100
    max_dd = ((p[c] / p[c].cummax() - 1).min()) * 100
    sharpe = (cagr - 4.5) / ann_vol  # assuming 4.5% VN risk-free rate
    print(f"{c}:")
    print(f"  Start (2021-09-01): {start_val:,.2f} pts")
    print(f"  End   (2026-09-07): {end_val:,.2f} pts")
    print(f"  Total Return:       {total_ret:+.2f}%")
    print(f"  CAGR (Annualized):  {cagr:+.2f}%")
    print(f"  Annual Volatility:  {ann_vol:.2f}%")
    print(f"  Maximum Drawdown:   {max_dd:.2f}%")
    print(f"  Sharpe Ratio (Rf=4.5%): {sharpe:.2f}")

corr = ret["VNINDEX"].corr(ret["HNX-INDEX"])
print(f"\nDaily Return Correlation (VNINDEX vs HNX-INDEX): {corr:.4f}")
