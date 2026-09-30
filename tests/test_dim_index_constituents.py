"""
Unit tests for F001c: Index constituents and group rooms crawler
(core.dim_index_metadata, core.dim_index_constituents, core.v_active_index_constituents).
"""

from datetime import date, datetime
import duckdb
import pytest
from unittest.mock import patch, MagicMock

from src.crawlers.dim_index_constituents import (
    INDEX_CATALOG,
    fetch_ssi_group_symbols,
    sync_index_metadata,
    crawl_and_sync_constituents,
)


@pytest.fixture
def mem_db():
    """Tạo database in-memory với schema đầy đủ của F000 + F001 + F001c."""
    con = duckdb.connect(":memory:")
    with open("configs/duckdb_schema.sql", "r", encoding="utf-8") as f:
        con.execute(f.read())
    
    # Thêm một vài mã mẫu vào core.dim_symbol để test JOIN view
    con.execute("""
        INSERT INTO core.dim_symbol (symbol, organ_name, exchange, fetched_at)
        VALUES 
            ('ACB', 'Ngân hàng TMCP Á Châu', 'HOSE', CURRENT_TIMESTAMP),
            ('FPT', 'CTCP FPT', 'HOSE', CURRENT_TIMESTAMP),
            ('MWG', 'CTCP Đầu tư Thế Giới Di Động', 'HOSE', CURRENT_TIMESTAMP)
    """)
    yield con
    con.close()


def test_index_catalog_completeness():
    """Kiểm tra danh mục 22 rổ chỉ số chuẩn."""
    assert len(INDEX_CATALOG) == 22
    expected_categories = {"BENCHMARK", "MARKET_CAP", "ESG", "THEMATIC", "SECTOR"}
    for code, info in INDEX_CATALOG.items():
        assert "name" in info
        assert info["exchange"] in {"HOSE", "HNX", "VNX"}
        assert info["category"] in expected_categories
        assert "cycle" in info
        assert "description" in info


def test_sync_index_metadata(mem_db):
    """Kiểm tra đồng bộ metadata vào core.dim_index_metadata."""
    count = sync_index_metadata(mem_db)
    assert count == 22

    rows = mem_db.execute("SELECT count(*) FROM core.dim_index_metadata").fetchone()[0]
    assert rows == 22

    # Kiểm tra phân bổ danh mục
    thematic_count = mem_db.execute(
        "SELECT count(*) FROM core.dim_index_metadata WHERE category = 'THEMATIC'"
    ).fetchone()[0]
    assert thematic_count == 3  # VNDIAMOND, VNFINLEAD, VNFINSELECT

    sector_count = mem_db.execute(
        "SELECT count(*) FROM core.dim_index_metadata WHERE category = 'SECTOR'"
    ).fetchone()[0]
    assert sector_count == 10  # 10 chỉ số ngành HOSE


def test_fetch_ssi_group_symbols_mocked():
    """Kiểm tra hàm parse JSON từ SSI iBoard."""
    mock_payload = {
        "data": [
            {"stockSymbol": "fpt", "isin": "VN000000FPT1"},
            {"stockSymbol": "acb", "isin": "VN000000ACB8"},
            {"stockSymbol": "fpt", "isin": "VN000000FPT1"},  # duplicate
            {"invalid": "no_symbol"},
        ]
    }
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json_str = (
            '{"data": [{"stockSymbol": "fpt"}, {"stockSymbol": "acb"}, {"stockSymbol": "fpt"}]}'
        ).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        symbols = fetch_ssi_group_symbols("VN30")
        assert symbols == ["ACB", "FPT"]


def test_idempotent_constituents_upsert(mem_db):
    """Kiểm tra tính bất biến (idempotent) khi ghi rổ chỉ số nhiều lần."""
    sync_index_metadata(mem_db)
    
    # Insert lần 1
    mem_db.execute("""
        INSERT INTO core.dim_index_constituents 
        (index_code, symbol, rank, effective_date, is_current, source, fetched_at)
        VALUES 
            ('VN30', 'FPT', 1, DATE '2026-09-01', TRUE, 'TEST', CURRENT_TIMESTAMP),
            ('VN30', 'ACB', 2, DATE '2026-09-01', TRUE, 'TEST', CURRENT_TIMESTAMP)
    """)
    assert mem_db.execute("SELECT count(*) FROM core.dim_index_constituents").fetchone()[0] == 2

    # Re-run upsert cùng khóa chính (index_code, symbol, effective_date)
    mem_db.execute("""
        INSERT INTO core.dim_index_constituents 
        (index_code, symbol, rank, effective_date, is_current, source, fetched_at)
        VALUES 
            ('VN30', 'FPT', 3, DATE '2026-09-01', TRUE, 'TEST_V2', CURRENT_TIMESTAMP)
        ON CONFLICT (index_code, symbol, effective_date) DO UPDATE SET
            rank = EXCLUDED.rank,
            source = EXCLUDED.source
    """)
    # Số dòng không tăng, giá trị rank được cập nhật
    assert mem_db.execute("SELECT count(*) FROM core.dim_index_constituents").fetchone()[0] == 2
    updated_rank = mem_db.execute(
        "SELECT rank, source FROM core.dim_index_constituents WHERE index_code='VN30' AND symbol='FPT'"
    ).fetchone()
    assert updated_rank[0] == 3
    assert updated_rank[1] == "TEST_V2"


def test_active_index_constituents_view(mem_db):
    """Kiểm tra query view core.v_active_index_constituents kết hợp thông tin symbol và metadata."""
    sync_index_metadata(mem_db)
    mem_db.execute("""
        INSERT INTO core.dim_index_constituents 
        (index_code, symbol, rank, effective_date, is_current, source, fetched_at)
        VALUES 
            ('VNDIAMOND', 'MWG', 1, DATE '2026-09-01', TRUE, 'SSI_IBOARD', CURRENT_TIMESTAMP),
            ('VNDIAMOND', 'FPT', 2, DATE '2026-09-01', TRUE, 'SSI_IBOARD', CURRENT_TIMESTAMP),
            ('VNDIAMOND', 'OLD_SYM', 3, DATE '2026-01-01', FALSE, 'SSI_IBOARD', CURRENT_TIMESTAMP)
    """)

    # View chỉ lấy các mã is_current = TRUE
    res = mem_db.execute("""
        SELECT index_code, index_name, category, symbol, organ_name, rank
        FROM core.v_active_index_constituents
        WHERE index_code = 'VNDIAMOND'
        ORDER BY rank
    """).fetchall()

    assert len(res) == 2
    assert res[0][3] == "MWG"
    assert res[0][4] == "CTCP Đầu tư Thế Giới Di Động"
    assert res[0][1] == "Chỉ số Cổ phiếu Kim Cương"
    assert res[0][2] == "THEMATIC"
    assert res[1][3] == "FPT"
    assert res[1][4] == "CTCP FPT"


@pytest.mark.network
def test_live_fetch_ssi_vn30_and_diamond():
    """Live smoke test kết nối SSI iBoard lấy VN30 và VNDIAMOND."""
    vn30 = fetch_ssi_group_symbols("VN30")
    assert len(vn30) == 30
    assert "FPT" in vn30
    assert "VCB" in vn30

    diamond = fetch_ssi_group_symbols("VNDIAMOND")
    assert len(diamond) >= 15
    assert "FPT" in diamond
    assert "MWG" in diamond
