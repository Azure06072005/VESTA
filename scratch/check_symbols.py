import duckdb

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)
syms_dim = [r[0] for r in con.execute('SELECT symbol FROM core.dim_symbol WHERE length(symbol) = 3 ORDER BY symbol').fetchall()]
print('Distinct 3-letter symbols in core.dim_symbol:', len(syms_dim))

syms_active = [r[0] for r in con.execute("SELECT symbol, sum(volume) as vol FROM core.market_ohlcv_daily WHERE date >= '2026-01-01' AND length(symbol) = 3 GROUP BY symbol ORDER BY vol DESC").fetchall()]
print('Actively traded symbols in 2026:', len(syms_active))

# Check symbols already having BCTC in core.fundamentals
syms_fund = [r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.fundamentals").fetchall()]
print('Symbols already having records in core.fundamentals:', len(syms_fund))
con.close()
