import duckdb

con = duckdb.connect('d:/VESTA/db/vesta_market_index.duckdb', read_only=True)
r = con.execute("SELECT COUNT(*), SUM(buy_value)/1e9, SUM(sell_value)/1e9, SUM(net_value)/1e9 FROM core.market_foreign_flow_daily WHERE date = '2026-10-09'").fetchone()
print('2026-10-09 foreign flow agg:', r)

# check foreign flow daily table structure and past dates
r2 = con.execute("SELECT date, COUNT(*), SUM(buy_value)/1e9, SUM(sell_value)/1e9, SUM(net_value)/1e9 FROM core.market_foreign_flow_daily GROUP BY date ORDER BY date DESC LIMIT 5").fetchall()
print('Foreign flow daily aggregated top 5:', r2)
con.close()
