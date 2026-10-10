import duckdb
import os
import sys
import time
import shutil
import datetime as dt
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = r"d:\VESTA"
OHLCV_DB = os.path.join(REPO_ROOT, "db", "vesta_ohlcv.duckdb")
MARKET_INDEX_DB = os.path.join(REPO_ROOT, "db", "vesta_market_index.duckdb")
NEWS_DB = os.path.join(REPO_ROOT, "db", "vesta_news.duckdb")
ADMIN_DIR = os.path.join(REPO_ROOT, "db", "admin")

today = dt.date.today().isoformat()
print(f"[*] Bắt đầu dọn dẹp bảng 0 dòng và cào bổ sung dữ liệu mới nhất (Hôm nay: {today})")

# 1. Dọn dẹp bảng 0 dòng trong vesta_ohlcv.duckdb
con_ohlcv = duckdb.connect(OHLCV_DB, read_only=False)
tables_ohlcv = [r[0] for r in con_ohlcv.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core' AND table_type='BASE TABLE'").fetchall()]

dropped_count = 0
for tbl in tables_ohlcv:
    cnt = con_ohlcv.execute(f"SELECT COUNT(*) FROM core.{tbl}").fetchone()[0]
    if cnt == 0:
        con_ohlcv.execute(f"DROP TABLE core.{tbl}")
        print(f"  [-] Đã xóa bảng 0 dòng khỏi ohlcv: core.{tbl}")
        dropped_count += 1

print(f"[OK] Đã xóa tổng cộng {dropped_count} bảng 0 dòng khỏi vesta_ohlcv.duckdb.")

# 2. Cào bổ sung dữ liệu chỉ số mới nhất (VNINDEX, VN30, HNX, UPCOM, VN100, VNFINLEAD, VNDIAMOND)
indices = ["VNINDEX", "VN30", "HNX", "UPCOM", "VN100", "VNFINLEAD", "VNDIAMOND", "VNMID", "VNSML"]
now_ts = int(time.time())
from_ts = int(dt.datetime(2026, 9, 25).timestamp())

session = requests.Session()
headers = {"User-Agent": "Mozilla/5.0"}

ingested_index_rows = 0
new_index_records = []

for idx in indices:
    url = f"https://dchart-api.vndirect.com.vn/dchart/history?resolution=D&symbol={idx}&from={from_ts}&to={now_ts}"
    try:
        r = session.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            data = r.json()
            if data.get("s") == "ok" and data.get("t"):
                t_list = data["t"]
                o_list = data["o"]
                h_list = data["h"]
                l_list = data["l"]
                c_list = data["c"]
                v_list = data["v"]
                for i in range(len(t_list)):
                    bar_date = dt.datetime.fromtimestamp(t_list[i]).strftime("%Y-%m-%d")
                    new_index_records.append((
                        idx,
                        bar_date,
                        float(o_list[i]),
                        float(h_list[i]),
                        float(l_list[i]),
                        float(c_list[i]),
                        int(v_list[i]),
                        dt.datetime.now().isoformat(),
                    ))
    except Exception as e:
        print(f"  [!] Lỗi tải chỉ số {idx}: {e}")

if new_index_records:
    # Nạp vào core.market_index_daily trong vesta_ohlcv
    con_ohlcv.execute("""
        CREATE TABLE IF NOT EXISTS core.market_index_daily (
            index_code VARCHAR NOT NULL,
            date DATE NOT NULL,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            fetched_at TIMESTAMP,
            PRIMARY KEY (index_code, date)
        )
    """)
    for r in new_index_records:
        con_ohlcv.execute("""
            INSERT OR REPLACE INTO core.market_index_daily (index_code, date, open, high, low, close, volume, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, r)
    print(f"[OK] Đã cập nhật {len(new_index_records)} bản ghi chỉ số mới nhất (lên đến {today}) vào vesta_ohlcv.duckdb.")

# Kiểm tra max date của market_index_daily
max_idx_date = con_ohlcv.execute("SELECT MAX(date) FROM core.market_index_daily").fetchone()[0]
print(f"[VERIFIED] Max date của core.market_index_daily hiện tại là: {max_idx_date}")
con_ohlcv.close()

# Nạp vào vesta_market_index.duckdb
con_idx = duckdb.connect(MARKET_INDEX_DB, read_only=False)
con_idx.execute("""
    CREATE TABLE IF NOT EXISTS core.market_index_daily (
        index_code VARCHAR NOT NULL,
        date DATE NOT NULL,
        open DOUBLE,
        high DOUBLE,
        low DOUBLE,
        close DOUBLE,
        volume BIGINT,
        fetched_at TIMESTAMP,
        PRIMARY KEY (index_code, date)
    )
""")
for r in new_index_records:
    con_idx.execute("""
        INSERT OR REPLACE INTO core.market_index_daily (index_code, date, open, high, low, close, volume, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, r)
con_idx.close()

# 3. Đồng bộ lại vào db/admin
for f in [OHLCV_DB, MARKET_INDEX_DB]:
    dest = os.path.join(ADMIN_DIR, os.path.basename(f))
    shutil.copy2(f, dest)

print("[OK] Hoàn tất dọn dẹp và cập nhật chỉ số lên ngày mới nhất!")
