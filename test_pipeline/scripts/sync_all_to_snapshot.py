"""Script đồng bộ toàn bộ các bảng dữ liệu bổ sung và hệ số điều chỉnh giá
từ db/test_db/vesta_test.duckdb sang db/vesta_snapshot.duckdb (CSDL chính không bị lock).
"""
import sys
import duckdb
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

snapshot_db = "db/vesta_snapshot.duckdb"
test_db = "db/test_db/vesta_test.duckdb"

print(f"Bắt đầu đồng bộ dữ liệu vào {snapshot_db}...")
con = duckdb.connect(snapshot_db, read_only=False)

try:
    # 1. Đảm bảo các schema tồn tại
    con.execute("CREATE SCHEMA IF NOT EXISTS staging;")
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("CREATE SCHEMA IF NOT EXISTS meta;")

    # 2. Tạo cấu trúc các bảng mới
    con.execute("""
        CREATE TABLE IF NOT EXISTS staging.proprietary_flow (
            symbol                VARCHAR NOT NULL,
            date                  DATE NOT NULL,
            buy_vol               DOUBLE,
            sell_vol              DOUBLE,
            net_vol               DOUBLE,
            buy_val               DOUBLE,
            sell_val              DOUBLE,
            net_val               DOUBLE,
            fetched_at            TIMESTAMP NOT NULL
        );
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS core.proprietary_flow (
            symbol                VARCHAR NOT NULL,
            date                  DATE NOT NULL,
            buy_vol               DOUBLE,
            sell_vol              DOUBLE,
            net_vol               DOUBLE,
            buy_val               DOUBLE,
            sell_val              DOUBLE,
            net_val               DOUBLE,
            fetched_at            TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, date)
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS staging.financial_notes (
            symbol        VARCHAR NOT NULL,
            period        VARCHAR NOT NULL,
            note_id       VARCHAR NOT NULL,
            note_name     VARCHAR,
            item_order    INTEGER,
            item_level    INTEGER,
            unit          VARCHAR,
            value         DOUBLE,
            fetched_at    TIMESTAMP NOT NULL
        );
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS core.financial_notes (
            symbol        VARCHAR NOT NULL,
            period        VARCHAR NOT NULL,
            note_id       VARCHAR NOT NULL,
            note_name     VARCHAR,
            item_order    INTEGER,
            item_level    INTEGER,
            unit          VARCHAR,
            value         DOUBLE,
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, period, note_id)
        );
    """)

    con.execute("DROP TABLE IF EXISTS staging.macro_rates;")
    con.execute("DROP TABLE IF EXISTS core.macro_rates;")
    con.execute("""
        CREATE TABLE staging.macro_rates (
            rate_type     VARCHAR NOT NULL,
            term          VARCHAR NOT NULL,
            date          DATE NOT NULL,
            rate_value    DOUBLE NOT NULL,
            source        VARCHAR NOT NULL,
            fetched_at    TIMESTAMP NOT NULL
        );
    """)
    con.execute("""
        CREATE TABLE core.macro_rates (
            rate_type     VARCHAR NOT NULL,
            term          VARCHAR NOT NULL,
            date          DATE NOT NULL,
            rate_value    DOUBLE NOT NULL,
            source        VARCHAR NOT NULL,
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (rate_type, term, date)
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS staging.price_adjustment_events (
            symbol           VARCHAR NOT NULL,
            ex_date          DATE NOT NULL,
            adjustment_type  VARCHAR NOT NULL,
            multiplier       DOUBLE NOT NULL,
            source_event_id  VARCHAR NOT NULL,
            computed_at      TIMESTAMP NOT NULL
        );
    """)
    con.execute("""
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

    # 3. ATTACH database test_db ở chế độ read_only
    con.execute(f"ATTACH '{test_db}' AS src_db (READ_ONLY);")

    # 4. Sao chép và merge dữ liệu
    print("Đang đồng bộ core.proprietary_flow...")
    con.execute("""
        INSERT INTO core.proprietary_flow 
        SELECT * FROM src_db.core.proprietary_flow
        ON CONFLICT (symbol, date) DO NOTHING;
    """)
    cnt_prop = con.execute("SELECT count(*) FROM core.proprietary_flow;").fetchone()[0]
    print(f" -> core.proprietary_flow: {cnt_prop:,} dòng.")

    print("Đang đồng bộ core.financial_notes...")
    con.execute("""
        INSERT INTO core.financial_notes 
        SELECT * FROM src_db.core.financial_notes
        ON CONFLICT (symbol, period, note_id) DO NOTHING;
    """)
    cnt_notes = con.execute("SELECT count(*) FROM core.financial_notes;").fetchone()[0]
    print(f" -> core.financial_notes: {cnt_notes:,} dòng.")

    print("Đang đồng bộ core.macro_rates...")
    con.execute("""
        INSERT INTO core.macro_rates 
        SELECT * FROM src_db.core.macro_rates
        ON CONFLICT (rate_type, term, date) DO NOTHING;
    """)
    cnt_rates = con.execute("SELECT count(*) FROM core.macro_rates;").fetchone()[0]
    print(f" -> core.macro_rates: {cnt_rates:,} dòng.")

    print("Đang đồng bộ core.price_adjustment_events...")
    con.execute("""
        INSERT INTO core.price_adjustment_events 
        SELECT * FROM src_db.core.price_adjustment_events
        ON CONFLICT (symbol, ex_date, source_event_id) DO NOTHING;
    """)
    cnt_adj = con.execute("SELECT count(*) FROM core.price_adjustment_events;").fetchone()[0]
    print(f" -> core.price_adjustment_events: {cnt_adj:,} dòng.")

    con.execute("DETACH src_db;")
    print("\n[ĐỒNG BỘ THÀNH CÔNG] Toàn bộ dữ liệu bổ sung đã được tích hợp vào vesta_snapshot.duckdb!")

finally:
    con.close()
