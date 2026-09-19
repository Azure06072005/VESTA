"""tests/test_master_crawlers.py

Kiểm thử tự động cho hệ thống Master Crawlers & ResilientDuckDBWriter:
- Kiểm tra tính đầy đủ của Fundamental Registry & News Registry.
- Kiểm tra cơ chế đăng ký nguồn mới động (Dynamic Registration).
- Kiểm tra cơ chế ghi DuckDB an toàn khóa (ResilientDuckDBWriter).
- Kiểm tra phân tích cú pháp CLI (Argument Parsing).
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import tempfile
import duckdb
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from crawlers.db_writer import ResilientDuckDBWriter
from crawlers.master_fundamentals_crawler import (
    FUNDAMENTAL_REGISTRY,
    register_fundamental,
)
from crawlers.master_news_crawler import (
    NEWS_REGISTRY,
    register_news,
)


def test_fundamental_registry_completeness():
    """Xác nhận tất cả các nguồn dữ liệu cơ bản trọng yếu đã được nạp vào Registry."""
    expected_sources = [
        "vnstock_fundamentals",
        "cafef_finance",
        "vietstock_finance",
        "financial_notes",
        "corporate_events",
        "proprietary_flow",
        "foreign_flow",
        "macro_rates",
        "market_ohlcv",
    ]
    for src in expected_sources:
        assert src in FUNDAMENTAL_REGISTRY, f"Nguồn {src} chưa được đăng ký trong FUNDAMENTAL_REGISTRY"
        spec = FUNDAMENTAL_REGISTRY[src]
        assert callable(spec.runner), f"Runner của {src} phải là hàm có thể gọi được"
        assert len(spec.description) > 0


def test_news_registry_completeness():
    """Xác nhận tất cả các phân loại tin tức & chính sách trọng yếu đã được nạp vào Registry."""
    expected_sources = [
        "vnstock_news",
        "cafef_news",
        "cafef_disclosures",
        "cafef_categories",
        "vietstock_news",
        "tinnhanhchungkhoan",
        "vneconomy",
        "thoibaonganhang",
        "sbv_policy",
        "ssc_policy",
        "baochinhphu",
        "associations",
        "international",
    ]
    for src in expected_sources:
        assert src in NEWS_REGISTRY, f"Nguồn tin tức {src} chưa được đăng ký trong NEWS_REGISTRY"
        spec = NEWS_REGISTRY[src]
        assert callable(spec.runner), f"Runner của {src} phải là hàm có thể gọi được"
        assert spec.category in ["equity", "portals", "policy", "associations", "international"]


def test_dynamic_crawler_registration():
    """Xác minh cơ chế mở rộng khi lập trình viên import và đăng ký thêm crawler mới."""
    test_src_name = "test_custom_provider"

    @register_fundamental(name=test_src_name, description="Nhà cung cấp tài chính thử nghiệm")
    def dummy_fundamental_runner(symbols, writer, args):
        return len(symbols) * 10

    assert test_src_name in FUNDAMENTAL_REGISTRY
    assert FUNDAMENTAL_REGISTRY[test_src_name].runner(["VCB", "FPT"], None, None) == 20

    test_news_name = "test_custom_news"

    @register_news(name=test_news_name, category="portals", description="Nguồn tin tức thử nghiệm")
    def dummy_news_runner(symbols, writer, args):
        return 5

    assert test_news_name in NEWS_REGISTRY
    assert NEWS_REGISTRY[test_news_name].runner([], None, None) == 5


def test_resilient_duckdb_writer_operations():
    """Kiểm tra khởi tạo schema và khả năng ghi/đồng bộ dữ liệu của ResilientDuckDBWriter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tgt_db = os.path.join(tmpdir, "test_target.duckdb")
        buf_db = os.path.join(tmpdir, "test_buffer.duckdb")

        writer = ResilientDuckDBWriter(target_db=tgt_db, buffer_db=buf_db)

        # Kiểm tra các bảng đã được khởi tạo tự động
        con = duckdb.connect(tgt_db, read_only=True)
        tables = [r[0] for r in con.execute("SHOW TABLES FROM core").fetchall()]
        con.close()

        expected_core_tables = [
            "fundamentals",
            "corporate_events",
            "news",
            "news_resources",
            "macro_policy",
            "cafef_disclosures",
            "proprietary_flow",
            "financial_notes",
            "macro_rates",
        ]
        for tbl in expected_core_tables:
            assert tbl in tables, f"Bảng core.{tbl} thiếu trong database đích"

        # Kiểm tra ghi dữ liệu qua execute_with_retry
        def _insert_test_news(c: duckdb.DuckDBPyConnection):
            c.execute("""
                INSERT OR IGNORE INTO core.news 
                (symbol, source, published_at, available_at, headline, body, source_url, fetched_at)
                VALUES ('VCB', 'test', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'Tiêu đề kiểm thử', 'Nội dung', 'https://test.vn/1', CURRENT_TIMESTAMP);
            """)
            c.execute("""
                INSERT OR IGNORE INTO core.news_resources
                (source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at)
                VALUES ('baochinhphu', 'Chính phủ', 'Nghị quyết', '01/NQ-CP', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'Tiêu đề vĩ mô', 'Tóm tắt', 'Nội dung', 'https://bcp.vn/1', CURRENT_TIMESTAMP);
            """)
            return 2

        res = writer.execute_with_retry(_insert_test_news)
        assert res == 2

        con_verify = duckdb.connect(tgt_db, read_only=True)
        count_news = con_verify.execute("SELECT count(*) FROM core.news WHERE symbol='VCB'").fetchone()[0]
        count_res = con_verify.execute("SELECT count(*) FROM core.news_resources WHERE source='baochinhphu'").fetchone()[0]
        con_verify.close()
        assert count_news == 1
        assert count_res == 1


def test_boundary_manager_filtering_and_strategy():
    """Kiểm tra chức năng lọc mã đã có và phân tích khoảng trống ngày (Forward vs Backward)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tgt_db = os.path.join(tmpdir, "test_boundary.duckdb")
        writer = ResilientDuckDBWriter(target_db=tgt_db)

        # Giả lập nạp dữ liệu cho VCB từ 2020-01-01 đến 2026-01-01
        def _seed(c: duckdb.DuckDBPyConnection):
            c.execute("""
                INSERT INTO core.news (symbol, source, published_at, available_at, headline, body, source_url, fetched_at)
                VALUES 
                ('VCB', 'cafef', '2020-01-02 08:00:00', '2020-01-02 08:00:00', 'Tin VCB 2020', 'nd', 'https://cf/1', '2020-01-02 08:00:00'),
                ('VCB', 'cafef', '2026-01-02 08:00:00', '2026-01-02 08:00:00', 'Tin VCB 2026', 'nd', 'https://cf/2', '2026-01-02 08:00:00');
            """)
            c.execute("""
                INSERT INTO core.news_resources (source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at)
                VALUES 
                ('baochinhphu', 'CP', 'NQ', '01', '2020-05-01 00:00:00', '2020-05-01 00:00:00', 'NQ 2020', 'tt', 'nd', 'https://bcp/1', '2020-05-01 00:00:00'),
                ('baochinhphu', 'CP', 'NQ', '02', '2026-01-15 00:00:00', '2026-01-15 00:00:00', 'NQ 2026', 'tt', 'nd', 'https://bcp/2', '2026-01-15 00:00:00');
            """)
        writer.execute_with_retry(_seed)

        from crawlers.boundary_manager import BoundaryManager
        mgr = BoundaryManager(db_path=tgt_db)

        # 1. Kiểm tra Symbol Skip: VCB đã có dữ liệu -> Bị skip, FPT chưa có -> Cần cào
        to_crawl, skipped = mgr.filter_symbols_to_crawl("news", ["VCB", "FPT"], force=False, date_column="published_at")
        assert "VCB" in skipped
        assert "FPT" in to_crawl

        # Nếu có --force: VCB không bị skip
        to_crawl_force, skipped_force = mgr.filter_symbols_to_crawl("news", ["VCB", "FPT"], force=True, date_column="published_at")
        assert "VCB" in to_crawl_force
        assert len(skipped_force) == 0

        # 2. Kiểm tra Date Boundary Analysis
        b_info = mgr.audit_source_date_boundary("news_resources", "baochinhphu", target_earliest_year=2000)
        assert b_info["total_records"] == 2
        assert b_info["min_date"] == "2020-05-01"
        assert b_info["max_date"] == "2026-01-15"
        assert b_info["forward_gap"] is not None  # Cần cào tiến từ 2026-01-15 đến hôm nay (Priority 1)
        assert b_info["backward_gap"] is not None # Cần cào lùi từ 2000-01-01 về 2020-05-01 (Priority 2)
        assert b_info["already_covered_range"] == ("2020-05-01", "2026-01-15") # Dải ngày đã có -> Bỏ qua


def test_progress_tracker_generation():
    """Kiểm tra báo cáo tổng quan của CrawlingProgressTracker."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tgt_db = os.path.join(tmpdir, "test_track.duckdb")
        writer = ResilientDuckDBWriter(target_db=tgt_db)

        from crawlers.track_crawling_progress import CrawlingProgressTracker
        tracker = CrawlingProgressTracker(db_path=tgt_db)
        rep = tracker.generate_report()

        assert rep["connection_status"] == "OK"
        assert len(rep["tables"]) == 11
        assert "core.news" in [t["table"] for t in rep["tables"]]
        assert "core.news_resources" in [t["table"] for t in rep["tables"]]

