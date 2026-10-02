import sys
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
con.execute("ATTACH 'db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")
con.execute("ATTACH 'db/vesta_news.duckdb' AS news_db (READ_ONLY);")

symbol = 'HPG'
print(f"=== TRÍCH XUẤT DỮ LIỆU MẪU MÃ: {symbol} XUYÊN SUỐT 3 DATABASE ===")

queries = [
    ("Snapshot: Dim Symbol", f"SELECT symbol, organ_name, exchange, industry_name FROM core.dim_symbol WHERE symbol = '{symbol}'"),
    ("Snapshot: Company Overview", f"SELECT symbol, exchange, charter_capital, number_of_employees, business_model[:60] as model FROM core.company_overview WHERE symbol = '{symbol}'"),
    ("Snapshot: Top Shareholders", f"SELECT symbol, shareholder_name, ownership_percentage, shares_owned FROM core.company_shareholders WHERE symbol = '{symbol}' ORDER BY ownership_percentage DESC LIMIT 2"),
    ("Snapshot: Corporate Events", f"SELECT symbol, event_type, event_date, payout_delay_days, detail_json[:60] as detail FROM core.corporate_events WHERE symbol = '{symbol}' ORDER BY event_date DESC NULLS LAST LIMIT 2"),
    ("Snapshot: Fundamentals Ratios", f"SELECT symbol, period_end, pe_ratio, pb_ratio, roe, net_margin FROM preprocessed.fundamentals_ratios WHERE symbol = '{symbol}' ORDER BY period_end DESC LIMIT 2"),
    ("Snapshot: Financial Notes", f"SELECT symbol, period, note_name, value FROM core.financial_notes WHERE symbol = '{symbol}' ORDER BY period DESC LIMIT 2"),
    ("Snapshot: Screener Snapshot", f"SELECT symbol, snapshot_date, price, market_cap, stock_strength FROM core.market_screener_snapshot WHERE symbol = '{symbol}' ORDER BY snapshot_date DESC LIMIT 2"),
    ("Snapshot: Realtime Quote", f"SELECT symbol, snapshot_at, data_json[:70] as quote_json FROM core.realtime_quote_snapshot WHERE symbol = '{symbol}' LIMIT 1"),
    ("Snapshot: Order Book Depth", f"SELECT symbol, bid_price_1, bid_vol_1, ask_price_1, ask_vol_1, ofi_ratio FROM core.order_book_depth WHERE symbol = '{symbol}' LIMIT 1"),
    ("Snapshot: Intraday Trades", f"SELECT symbol, time, price, volume, match_type, is_shark_sweep FROM core.intraday_trades WHERE symbol = '{symbol}' ORDER BY time DESC LIMIT 2"),
    ("Snapshot: Foreign Flow Daily", f"SELECT symbol, date, net_volume, net_value, foreign_room FROM core.market_foreign_flow_daily WHERE symbol = '{symbol}' ORDER BY date DESC LIMIT 2"),
    ("OHLCV: Market OHLCV Daily", f"SELECT symbol, date, open, high, low, close, volume FROM ohlcv_db.core.market_ohlcv_daily WHERE symbol = '{symbol}' ORDER BY date DESC LIMIT 2"),
    ("OHLCV: Market OHLCV 1M", f"SELECT symbol, time, open, high, low, close, volume FROM ohlcv_db.core.market_ohlcv_1m WHERE symbol = '{symbol}' ORDER BY time DESC LIMIT 2"),
    ("News: Direct Tagged News", f"SELECT symbol, published_at, headline FROM news_db.core.news WHERE symbol = '{symbol}' ORDER BY published_at DESC LIMIT 2"),
]

for title, q in queries:
    print(f"\n--- {title} ---")
    try:
        res = con.execute(q).df()
        print(res.to_string(index=False))
    except Exception as e:
        print(f"Error: {e}")

con.close()
