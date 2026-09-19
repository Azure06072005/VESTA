"""Script tối ưu hóa tính toán price adjustment events bằng cách gom nhóm dữ liệu một lần (single-pass),
không quét toàn bảng 5 triệu dòng nhiều lần.
"""
import sys
import json
import duckdb
import pandas as pd
from pathlib import Path
import datetime as dt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.etl.adjustments import _parse_float

sys.stdout.reconfigure(encoding='utf-8')

main_db = "db/vesta.duckdb"
test_db = "db/test_db/vesta_test.duckdb"

print("Đang kết nối CSDL...")
con_main = duckdb.connect(main_db, read_only=True)
con_test = duckdb.connect(test_db, read_only=False)

# Đảm bảo schema tồn tại
con_test.execute("CREATE SCHEMA IF NOT EXISTS staging;")
con_test.execute("CREATE SCHEMA IF NOT EXISTS core;")
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

print("Đang nạp toàn bộ 40,277 sự kiện doanh nghiệp...")
events_df = con_main.execute("""
    SELECT symbol, event_id, event_type, detail_json 
    FROM core.corporate_events
""").df()
print(f" -> Đã nạp {len(events_df):,} corporate events.")

# Tìm danh sách các symbol có sự kiện
symbols = events_df['symbol'].unique().tolist()
print(f" -> Tổng số mã cổ phiếu có sự kiện: {len(symbols)}")

# Nạp dữ liệu giá đóng cửa cho các mã có sự kiện
print("Đang nạp dữ liệu giá đóng cửa lịch sử cho các mã liên quan...")
ohlcv_df = con_main.execute("""
    SELECT m.symbol, m.date, m.close
    FROM core.market_ohlcv_daily m
    SEMI JOIN core.corporate_events c ON m.symbol = c.symbol
    ORDER BY m.symbol, m.date
""").df()
print(f" -> Đã nạp {len(ohlcv_df):,} thanh nến liên quan.")

# Group OHLCV by symbol into dict for O(1) lookup
print("Đang lập chỉ mục dữ liệu trong RAM...")
ohlcv_by_symbol = {}
for sym, group in ohlcv_df.groupby("symbol"):
    ohlcv_by_symbol[sym] = group.sort_values("date").reset_index(drop=True)

events_by_symbol = {}
for sym, group in events_df.groupby("symbol"):
    events_by_symbol[sym] = group

all_adj_rows = []
now_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

print("Bắt đầu tính toán hệ số điều chỉnh giá...")
for sym in symbols:
    sym_events = events_by_symbol.get(sym)
    sym_ohlcv = ohlcv_by_symbol.get(sym)
    if sym_events is None or sym_ohlcv is None or sym_ohlcv.empty:
        continue
    
    date_series = pd.to_datetime(sym_ohlcv["date"])
    
    for _, event in sym_events.iterrows():
        try:
            detail = json.loads(event["detail_json"])
        except Exception:
            continue

        exright_date_str = detail.get("exright_date")
        if not exright_date_str or str(exright_date_str).strip().lower() in ("nan", "none", ""):
            continue
        try:
            ex_date = pd.to_datetime(exright_date_str).date()
        except Exception:
            continue

        event_code = detail.get("event_code")
        exercise_ratio = _parse_float(detail.get("exercise_ratio"))
        value_per_share = _parse_float(detail.get("value_per_share"))

        if event_code == "ISS" and exercise_ratio is not None and exercise_ratio > 0:
            multiplier = 1.0 / (1.0 + exercise_ratio)
            adjustment_type = "share_issue"
        elif event.get("event_type") == "DIVIDEND" and value_per_share is not None and value_per_share > 0:
            ex_ts = pd.to_datetime(ex_date)
            prior_rows = sym_ohlcv[date_series < ex_ts]
            if prior_rows.empty:
                continue
            cum_close = float(prior_rows.iloc[-1]["close"])
            if cum_close <= value_per_share:
                continue
            multiplier = (cum_close - value_per_share) / cum_close
            adjustment_type = "dividend"
        else:
            continue

        all_adj_rows.append({
            "symbol": sym,
            "ex_date": ex_date,
            "adjustment_type": adjustment_type,
            "multiplier": multiplier,
            "source_event_id": str(event["event_id"]),
            "computed_at": now_utc
        })

adj_res_df = pd.DataFrame(all_adj_rows)
print(f" -> Đã tính toán xong {len(adj_res_df):,} sự kiện điều chỉnh giá trên toàn thị trường!")

# Bulk insert into staging and core
print("Đang ghi vào CSDL db/test_db/vesta_test.duckdb...")
con_test.register("df_to_insert", adj_res_df)
con_test.execute("""
    INSERT INTO staging.price_adjustment_events 
    SELECT * FROM df_to_insert;
""")
con_test.execute("""
    INSERT INTO core.price_adjustment_events 
    SELECT * FROM df_to_insert
    ON CONFLICT (symbol, ex_date, source_event_id) DO NOTHING;
""")
con_test.unregister("df_to_insert")

# Check count in core
cnt = con_test.execute("SELECT count(*) FROM core.price_adjustment_events").fetchone()[0]
print(f"Tổng số bản ghi trong core.price_adjustment_events: {cnt:,}")

# Audit securities symbols
securities_symbols = [
    'AAS', 'ABW', 'AGR', 'APG', 'APS', 'ART', 'BMS', 'BSI', 'BVS', 'CSI', 
    'CTS', 'DSC', 'DSE', 'EVS', 'FTS', 'HAC', 'HBS', 'HCM', 'IVS', 'LPS', 
    'MBS', 'ORS', 'PHS', 'PSI', 'SBS', 'SHS', 'SSI', 'TCI', 'TCX', 'TVB', 
    'TVS', 'UPS', 'VCI', 'VCK', 'VDS', 'VFS', 'VIG', 'VIX', 'VND', 'VPX', 
    'VUA', 'WSS'
]
sec_adj = con_test.execute("""
    SELECT symbol, count(*) as adjustments_count, min(ex_date) as earliest_ex_date, max(ex_date) as latest_ex_date
    FROM core.price_adjustment_events 
    WHERE symbol IN ({})
    GROUP BY symbol
    ORDER BY adjustments_count DESC
""".format(','.join([f"'{x}'" for x in securities_symbols]))).df()

print("\n--- KẾT QUẢ ĐIỀU CHỈNH GIÁ CHO CÁC CÔNG TY CHỨNG KHOÁN ---")
print(f"Số công ty chứng khoán có sự kiện chia tách/cổ tức: {len(sec_adj)}/{len(securities_symbols)}")
print(sec_adj.to_string())

con_main.close()
con_test.close()
print("\n[THÀNH CÔNG] Hoàn tất tính toán hệ số điều chỉnh giá.")
