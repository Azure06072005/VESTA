"""Script tính toán và nạp price adjustment events từ corporate_events và market_ohlcv_daily
cho tất cả các mã chứng khoán (và toàn thị trường) vào db/test_db/vesta_test.duckdb.
"""
import sys
import duckdb
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.etl.adjustments import compute_adjustment_events, write_adjustment_events

sys.stdout.reconfigure(encoding='utf-8')

main_db = "db/vesta.duckdb"
test_db = "db/test_db/vesta_test.duckdb"

con_main = duckdb.connect(main_db, read_only=True)
con_test = duckdb.connect(test_db, read_only=False)

# Make sure staging and core price_adjustment_events exist in test_db
con_test.execute("""
    CREATE TABLE IF NOT EXISTS staging.price_adjustment_events (
        symbol           VARCHAR NOT NULL,
        ex_date          DATE NOT NULL,
        adjustment_type  VARCHAR NOT NULL,
        multiplier       DOUBLE NOT NULL,
        source_event_id  VARCHAR NOT NULL,
        computed_at      TIMESTAMP NOT NULL
    );
""")
con_test.execute("""
    CREATE TABLE IF NOT EXISTS core.price_adjustment_events (
        symbol           VARCHAR NOT NULL,
        ex_date          DATE NOT NULL,
        adjustment_type  VARCHAR NOT NULL,
        multiplier       DOUBLE NOT NULL,
        source_event_id  VARCHAR NOT NULL,
        computed_at      TIMESTAMP NOT NULL,
        PRIMARY KEY (symbol, ex_date, source_event_id)
    );
""")

# Get all symbols that have corporate events
symbols_with_events = con_main.execute("""
    SELECT distinct symbol 
    FROM core.corporate_events 
    ORDER BY symbol
""").df()['symbol'].tolist()

print(f"Tổng số mã có sự kiện doanh nghiệp: {len(symbols_with_events)}")

total_promoted = 0
symbols_processed = 0

for s in symbols_with_events:
    events_df = con_main.execute("""
        SELECT event_id, event_type, detail_json 
        FROM core.corporate_events 
        WHERE symbol = ?
    """, [s]).df()
    
    ohlcv_df = con_main.execute("""
        SELECT date, close 
        FROM core.market_ohlcv_daily 
        WHERE symbol = ?
        ORDER BY date
    """, [s]).df()
    
    adj_df = compute_adjustment_events(events_df, ohlcv_df, s)
    if not adj_df.empty:
        n = write_adjustment_events(adj_df, s, con_test)
        total_promoted += n
    
    symbols_processed += 1
    if symbols_processed % 100 == 0:
        print(f"Đã xử lý {symbols_processed}/{len(symbols_with_events)} mã. Số hệ số điều chỉnh đã tính: {total_promoted}")

print(f"\n[HOÀN TẤT] Đã tính toán hệ số điều chỉnh giá cho {symbols_processed} mã.")
print(f"Tổng số bản ghi price_adjustment_events nạp vào CSDL: {total_promoted}")

# Check summary for securities companies
securities_symbols = [
    'SSI', 'VND', 'VCI', 'HCM', 'SHS', 'MBS', 'FTS', 'CTS', 'BSI', 'VDS', 
    'AGR', 'ORS', 'BVS', 'TVS', 'EVS', 'APG', 'WSS', 'TCI', 'SBS', 'HBS', 
    'VIG', 'IVS', 'PSI'
]
sec_adj = con_test.execute("""
    SELECT symbol, count(*) as adjustments_count, min(ex_date) as earliest_ex_date, max(ex_date) as latest_ex_date
    FROM core.price_adjustment_events 
    WHERE symbol IN ({})
    GROUP BY symbol
    ORDER BY adjustments_count DESC
""".format(','.join([f"'{x}'" for x in securities_symbols]))).df()

print("\n--- KẾT QUẢ ĐIỀU CHỈNH GIÁ CHO CÁC CÔNG TY CHỨNG KHOÁN ---")
print(sec_adj.to_string())

con_main.close()
con_test.close()
