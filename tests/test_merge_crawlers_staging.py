"""Unit tests cho merge_crawlers_staging.py."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etl.merge_crawlers_staging import merge_staging_to_main


def test_merge_staging_to_main(tmp_path, monkeypatch):
    main_db = tmp_path / "test_main.duckdb"
    staging_db = tmp_path / "test_staging.duckdb"

    # Setup schemas
    m_conn = duckdb.connect(str(main_db))
    m_conn.execute("CREATE SCHEMA core;")
    m_conn.execute("""
        CREATE TABLE core.macro_policy (
            source VARCHAR,
            issuing_body VARCHAR,
            doc_type VARCHAR,
            doc_number VARCHAR,
            published_at TIMESTAMP,
            available_at TIMESTAMP,
            headline VARCHAR,
            summary VARCHAR,
            body VARCHAR,
            source_url VARCHAR PRIMARY KEY,
            fetched_at TIMESTAMP
        );
    """)
    m_conn.close()

    s_conn = duckdb.connect(str(staging_db))
    s_conn.execute("CREATE SCHEMA core;")
    s_conn.execute("""
        CREATE TABLE core.macro_policy (
            source VARCHAR,
            issuing_body VARCHAR,
            doc_type VARCHAR,
            doc_number VARCHAR,
            published_at TIMESTAMP,
            available_at TIMESTAMP,
            headline VARCHAR,
            summary VARCHAR,
            body VARCHAR,
            source_url VARCHAR PRIMARY KEY,
            fetched_at TIMESTAMP
        );
    """)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    s_conn.execute("""
        INSERT INTO core.macro_policy VALUES
        ('vneconomy', 'VnEconomy', 'Báo cáo', '123/TT-BTC', ?, ?, 'Tiêu đề staging', 'Tóm tắt', 'Nội dung', 'https://vneconomy.vn/test.htm', ?)
    """, [now, now, now])
    s_conn.close()

    # Monkeypatch paths
    monkeypatch.setattr("etl.merge_crawlers_staging.MAIN_DB_PATH", main_db)
    monkeypatch.setattr("etl.merge_crawlers_staging.STAGING_DB_PATH", staging_db)

    count = merge_staging_to_main()
    assert count == 1

    # Verify merged in main_db
    chk = duckdb.connect(str(main_db), read_only=True)
    res = chk.execute("SELECT headline, doc_number FROM core.macro_policy").fetchall()
    assert len(res) == 1
    assert res[0][0] == "Tiêu đề staging"
    assert res[0][1] == "123/TT-BTC"
    chk.close()
