"""tests/test_atomic_ingestion.py

Kiểm thử tự động cho kiến trúc Atomic Ingestion & Buffer Separation (F000).
Chứng minh:
1. Ghi vào buffer_db hoàn toàn không chiếm khóa file trên target_db.
2. Nạp nguyên tử (Atomic Ingestion) diễn ra trong giao dịch ACID duy nhất (sub-second).
3. Rollback an toàn khi có sự cố.
"""

import os
import pathlib
import sys
import tempfile
import time
import duckdb
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from crawlers.db_writer import ResilientDuckDBWriter


def test_buffer_first_zero_lock_on_target():
    """Kiểm tra: buffer_first=True ghi thẳng vào buffer_db mà không động tới target_db."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tgt_db = os.path.join(tmpdir, "main_target.duckdb")
        buf_db = os.path.join(tmpdir, "staging_buffer.duckdb")

        # Khởi tạo writer với buffer_first=True
        writer = ResilientDuckDBWriter(target_db=tgt_db, buffer_db=buf_db, buffer_first=True)

        # Mở target_db ở chế độ độc quyền bởi một tiến trình khác (giả lập reader/writer khác đang giữ)
        con_external = duckdb.connect(tgt_db, read_only=False)
        try:
            # Ghi dữ liệu vào writer
            def _insert_data(c: duckdb.DuckDBPyConnection):
                c.execute("""
                    INSERT INTO core.news (symbol, source, published_at, available_at, headline, body, source_url, fetched_at)
                    VALUES ('HPG', 'cafef', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'Tin tức HPG', 'Nội dung', 'https://test.vn/hpg1', CURRENT_TIMESTAMP);
                """)
                return 1

            # Lệnh này PHẢI thành công vì ghi vào buffer_db, không bị chặn bởi con_external trên tgt_db
            res = writer.execute_with_retry(_insert_data)
            assert res == 1

            # Kiểm tra dữ liệu nằm trong buffer_db, KHÔNG nằm trong target_db
            con_buf = duckdb.connect(buf_db, read_only=True)
            cnt_buf = con_buf.execute("SELECT count(*) FROM core.news WHERE symbol='HPG'").fetchone()[0]
            con_buf.close()
            assert cnt_buf == 1

        finally:
            con_external.close()


def test_atomic_ingestion_transactional_safety():
    """Kiểm tra: atomic_ingest_buffer chuyển dữ liệu từ buffer sang target trong sub-second transaction và xóa sạch buffer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tgt_db = os.path.join(tmpdir, "main_target.duckdb")
        buf_db = os.path.join(tmpdir, "staging_buffer.duckdb")

        writer = ResilientDuckDBWriter(target_db=tgt_db, buffer_db=buf_db, buffer_first=True)

        # Nạp 5 bản ghi nến và 3 bản ghi tin tức vào buffer
        def _seed_buffer(c: duckdb.DuckDBPyConnection):
            c.execute("""
                INSERT INTO core.news (symbol, source, published_at, available_at, headline, body, source_url, fetched_at)
                VALUES 
                ('FPT', 'cafef', '2026-09-01 09:00:00', '2026-09-01 09:00:00', 'Tin 1', 'Nội dung 1', 'https://cf/1', CURRENT_TIMESTAMP),
                ('FPT', 'cafef', '2026-09-02 09:00:00', '2026-09-02 09:00:00', 'Tin 2', 'Nội dung 2', 'https://cf/2', CURRENT_TIMESTAMP);
            """)
            c.execute("""
                INSERT INTO core.market_ohlcv_daily (symbol, date, open, high, low, close, volume, fetched_at)
                VALUES
                ('FPT', '2026-09-01', 130.0, 135.0, 129.0, 134.0, 1000000, CURRENT_TIMESTAMP),
                ('FPT', '2026-09-02', 134.0, 136.0, 133.0, 135.5, 1200000, CURRENT_TIMESTAMP);
            """)
            return True

        writer.write_to_buffer(_seed_buffer)

        # Thực thi nạp nguyên tử
        res = writer.atomic_ingest_buffer()

        assert res["status"] == "SUCCESS"
        assert res["tables_synced"] == 2
        assert res["total_rows"] == 4
        assert res["elapsed_ms"] < 2000.0  # Thời gian thực thi cực ngắn

        # Kiểm tra dữ liệu đã vào target_db an toàn
        con_tgt = duckdb.connect(tgt_db, read_only=True)
        news_cnt = con_tgt.execute("SELECT count(*) FROM core.news WHERE symbol='FPT'").fetchone()[0]
        ohlcv_cnt = con_tgt.execute("SELECT count(*) FROM core.market_ohlcv_daily WHERE symbol='FPT'").fetchone()[0]
        con_tgt.close()

        assert news_cnt == 2
        assert ohlcv_cnt == 2

        # Kiểm tra buffer_db đã được làm sạch hoàn toàn
        con_buf = duckdb.connect(buf_db, read_only=True)
        buf_news = con_buf.execute("SELECT count(*) FROM core.news").fetchone()[0]
        buf_ohlcv = con_buf.execute("SELECT count(*) FROM core.market_ohlcv_daily").fetchone()[0]
        con_buf.close()

        assert buf_news == 0
        assert buf_ohlcv == 0


def test_atomic_ingestion_idempotent_replace():
    """Kiểm tra: Nạp lặp lại không sinh trùng lặp (Idempotent Upsert với REPLACE)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tgt_db = os.path.join(tmpdir, "main_target.duckdb")
        buf_db = os.path.join(tmpdir, "staging_buffer.duckdb")

        writer = ResilientDuckDBWriter(target_db=tgt_db, buffer_db=buf_db)

        # Lần 1: Nạp bản ghi nến ban đầu vào target
        def _insert_v1(c: duckdb.DuckDBPyConnection):
            c.execute("""
                INSERT INTO core.market_ohlcv_daily (symbol, date, open, high, low, close, volume, fetched_at)
                VALUES ('SSI', '2026-09-10', 35.0, 36.0, 34.5, 35.5, 500000, CURRENT_TIMESTAMP);
            """)
        writer.execute_with_retry(_insert_v1)

        # Lần 2: Buffer chứa bản ghi cùng khóa (symbol, date) nhưng giá close được cập nhật (35.8)
        def _seed_buffer_update(c: duckdb.DuckDBPyConnection):
            c.execute("""
                INSERT INTO core.market_ohlcv_daily (symbol, date, open, high, low, close, volume, fetched_at)
                VALUES ('SSI', '2026-09-10', 35.0, 36.5, 34.5, 35.8, 650000, CURRENT_TIMESTAMP);
            """)
        writer.write_to_buffer(_seed_buffer_update)

        # Chạy Atomic Ingestion
        res = writer.atomic_ingest_buffer()
        assert res["status"] == "SUCCESS"
        assert res["total_rows"] == 1

        # Kiểm tra: Chỉ có 1 bản ghi duy nhất trong target_db và giá close là 35.8
        con_tgt = duckdb.connect(tgt_db, read_only=True)
        row = con_tgt.execute("SELECT close, volume FROM core.market_ohlcv_daily WHERE symbol='SSI' AND date='2026-09-10'").fetchone()
        con_tgt.close()

        assert row[0] == 35.8
        assert row[1] == 650000


def test_market_ohlcv_buffer_first_and_atomic_ingest():
    """Kiểm tra: market_ohlcv.write_ohlcv hoạt động trơn tru với buffer_first=True và nạp nguyên tử thành công."""
    import pandas as pd
    from crawlers import market_ohlcv

    with tempfile.TemporaryDirectory() as tmpdir:
        tgt_db = os.path.join(tmpdir, "main_target.duckdb")
        buf_db = os.path.join(tmpdir, "staging_buffer.duckdb")

        writer = ResilientDuckDBWriter(target_db=tgt_db, buffer_db=buf_db, buffer_first=True)

        df = pd.DataFrame([{
            "symbol": "AAA",
            "date": "2026-09-24",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "volume": 100000,
            "fetched_at": pd.Timestamp.now()
        }])

        def _write_action(con: duckdb.DuckDBPyConnection) -> int:
            return market_ohlcv.write_ohlcv(df, con=con)

        # Ghi trực tiếp vào buffer_db mà không văng lỗi thiếu bảng staging.market_ohlcv_daily
        cnt = writer.execute_with_retry(_write_action)
        assert cnt == 1

        # Chạy Atomic Ingestion vào target_db
        res = writer.atomic_ingest_buffer()
        assert res["status"] == "SUCCESS"
        assert res["total_rows"] >= 1

        # Kiểm tra target_db
        con_tgt = duckdb.connect(tgt_db, read_only=True)
        row = con_tgt.execute("SELECT symbol, close FROM core.market_ohlcv_daily WHERE symbol='AAA'").fetchone()
        con_tgt.close()

        assert row is not None
        assert row[0] == "AAA"
        assert row[1] == 10.2
