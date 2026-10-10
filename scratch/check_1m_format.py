import duckdb

con = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)
q = "SELECT time, open, high, low, close, volume FROM core.market_ohlcv_1m WHERE symbol='VNM' AND time >= '2026-09-18' ORDER BY time"
res = con.execute(q).fetchall()
print('Total VNM bars on 2026-09-18:', len(res))
if res:
    print('First bar:', res[0])
    print('Last bar:', res[-1])

# Check overall min/max hour for all bars on that day
q_hours = "SELECT min(strftime(time, '%H:%M')), max(strftime(time, '%H:%M')) FROM core.market_ohlcv_1m WHERE time >= '2026-09-18'"
print('Hour range on 2026-09-18:', con.execute(q_hours).fetchone())
