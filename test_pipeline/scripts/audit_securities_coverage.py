import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta.duckdb', read_only=True)

symbols = [
    'AAS', 'ABW', 'AGR', 'APG', 'APS', 'ART', 'BMS', 'BSI', 'BVS', 'CSI', 
    'CTS', 'DSC', 'DSE', 'EVS', 'FTS', 'HAC', 'HBS', 'HCM', 'IVS', 'LPS', 
    'MBS', 'ORS', 'PHS', 'PSI', 'SBS', 'SHS', 'SSI', 'TCI', 'TCX', 'TVB', 
    'TVS', 'UPS', 'VCI', 'VCK', 'VDS', 'VFS', 'VIG', 'VIX', 'VND', 'VPX', 
    'VUA', 'WSS'
]

results = []
for s in symbols:
    ohlcv = con.execute('SELECT count(*), min(date)::VARCHAR, max(date)::VARCHAR FROM core.market_ohlcv_daily WHERE symbol = ?', [s]).fetchone()
    funds = con.execute("SELECT count(distinct period_end), min(period_end)::VARCHAR, max(period_end)::VARCHAR FROM core.fundamentals WHERE symbol = ?", [s]).fetchone()
    events = con.execute('SELECT count(*), min(event_date)::VARCHAR, max(event_date)::VARCHAR FROM core.corporate_events WHERE symbol = ?', [s]).fetchone()
    news = con.execute('SELECT count(*), min(published_at)::VARCHAR, max(published_at)::VARCHAR FROM core.news WHERE symbol = ?', [s]).fetchone()
    
    results.append({
        'symbol': s,
        'ohlcv_bars': ohlcv[0],
        'ohlcv_min': ohlcv[1] or 'MISSING',
        'ohlcv_max': ohlcv[2] or 'MISSING',
        'funds_periods': funds[0],
        'funds_min': funds[1] or 'MISSING',
        'funds_max': funds[2] or 'MISSING',
        'events_cnt': events[0],
        'news_cnt': news[0]
    })

df_res = pd.DataFrame(results)
print(f"==========================================================================================")
print(f"AUDIT TOÀN BỘ CÁC CÔNG TY CHỨNG KHOÁN TRONG CƠ SỞ DỮ LIỆU CHÍNH (VESTA.DUCKDB)")
print(f"Tổng số công ty chứng khoán được kiểm tra: {len(df_res)}")
print(f"==========================================================================================")
print(df_res.to_string())

# Summarize any tickers with 0 bars or 0 fundamentals
missing_ohlcv = df_res[df_res['ohlcv_bars'] == 0]['symbol'].tolist()
missing_funds = df_res[df_res['funds_periods'] == 0]['symbol'].tolist()
print("\n" + "="*50)
print("TỔNG HỢP CÁC LỖ HỔNG / THIẾU DỮ LIỆU:")
print(f"- Mã thiếu OHLCV ({len(missing_ohlcv)}): {missing_ohlcv}")
print(f"- Mã thiếu Báo cáo tài chính ({len(missing_funds)}): {missing_funds}")
print("="*50)

con.close()
