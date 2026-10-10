import duckdb

con = duckdb.connect('d:/VESTA/db/vesta_ohlcv.duckdb', read_only=True)
print("ETF cols:", [c[1] for c in con.execute("PRAGMA table_info('core.market_etf_daily')").fetchall()])
print("CW cols:", [c[1] for c in con.execute("PRAGMA table_info('core.market_covered_warrants_daily')").fetchall()])
print("Derivatives cols:", [c[1] for c in con.execute("PRAGMA table_info('core.market_derivatives_daily')").fetchall()])

# Sample ETF row
r_etf = con.execute("SELECT * FROM core.market_etf_daily ORDER BY date DESC LIMIT 2").fetchall()
print("Sample ETF:", r_etf)

# Sample CW row
r_cw = con.execute("SELECT * FROM core.market_covered_warrants_daily ORDER BY date DESC LIMIT 2").fetchall()
print("Sample CW:", r_cw)

con.close()
