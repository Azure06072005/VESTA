"""tests/test_dim_icb.py

Kiểm thử toàn diện khuyến nghị F001 - Phân cấp ngành chuẩn 4 tầng ICB
(Industry Standard ICB 4-tier Hierarchy).

Mục tiêu kiểm thử:
1. Xác thực tính toàn vẹn của từ điển tĩnh configs/icb_classification.json (177 mã chuẩn).
2. Kiểm tra phân bổ chuẩn xác 4 tầng: 11 Industry, 19 Supersector, 40 Sector, 107 Subsector.
3. Kiểm tra tính toàn vẹn cấu trúc phân cấp (Mỗi Subsector đều thuộc đúng Sector, Supersector, Industry).
4. Kiểm tra tính idempotent và schema validation khi ghi vào DuckDB.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd
import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crawlers import dim_icb  # noqa: E402
from etl import db  # noqa: E402


def test_icb_static_json_exists_and_complete():
    """Kiểm tra file tĩnh tồn tại và có đủ 177 mã chuẩn."""
    config_path = PROJECT_ROOT / "configs" / "icb_classification.json"
    assert config_path.exists(), f"Không tìm thấy file {config_path}"

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 177, f"Tổng số mã ICB phải là 177, hiện tại là {len(data)}"


def test_icb_levels_distribution():
    """Kiểm tra số lượng mã ở từng tầng phân cấp (11 - 19 - 40 - 107)."""
    mapping = dim_icb.load_static_icb_classification()
    assert len(mapping) == 177

    l1 = [v for v in mapping.values() if v["level"] == 1]
    l2 = [v for v in mapping.values() if v["level"] == 2]
    l3 = [v for v in mapping.values() if v["level"] == 3]
    l4 = [v for v in mapping.values() if v["level"] == 4]

    assert len(l1) == 11, f"Tầng 1 (Industry) phải có 11 mã, tìm thấy {len(l1)}"
    assert len(l2) == 19, f"Tầng 2 (Supersector) phải có 19 mã, tìm thấy {len(l2)}"
    assert len(l3) == 40, f"Tầng 3 (Sector) phải có 40 mã, tìm thấy {len(l3)}"
    assert len(l4) == 107, f"Tầng 4 (Subsector) phải có 107 mã, tìm thấy {len(l4)}"


def test_icb_hierarchy_parent_child_integrity():
    """Kiểm tra tính nhất quán quan hệ phả hệ cha-con (Lineage)."""
    df = dim_icb.build_icb_hierarchy_df()
    assert len(df) == 177

    # 1. Kiểm tra tất cả mã L4 (Subsector)
    l4_df = df[df["level"] == 4]
    assert len(l4_df) == 107

    # Tất cả L4 phải có đầy đủ thông tin Sector, Supersector và Industry
    assert l4_df["sector_code"].notna().all()
    assert l4_df["supersector_code"].notna().all()
    assert l4_df["industry_code"].notna().all()
    assert l4_df["industry_name_vi"].notna().all()

    # 2. Kiểm tra cụ thể ngành Ngân hàng (8355)
    # 8355 (Ngân hàng) -> Sector 8350 (Ngân hàng) -> Supersector 8300 (Ngân hàng) -> Industry 8000 (Tài chính)
    bank_row = df[df["icb_code"] == "8355"].iloc[0]
    assert bank_row["level"] == 4
    assert bank_row["sector_code"] == "8350"
    assert bank_row["supersector_code"] == "8300"
    assert bank_row["industry_code"] == "8000"
    assert "Tài chính" in bank_row["industry_name_vi"]

    # 3. Kiểm tra ngành Phần mềm & Dịch vụ máy tính (9530 / 9533)
    # Thuộc Supersector 9500 (Công nghệ) -> Industry 9000 (Công nghệ thông tin)
    tech_row = df[df["icb_code"] == "9533"].iloc[0]
    assert tech_row["supersector_code"] == "9500"
    assert tech_row["industry_code"] == "9000"
    assert "công nghệ thông tin" in tech_row["industry_name_vi"].lower()


def test_write_icb_hierarchy_idempotency(tmp_path):
    """Kiểm tra ghi vào DuckDB độc lập, đảm bảo idempotent không nhân bản dòng."""
    db_path = tmp_path / "test_icb.duckdb"
    con = db.bootstrap_schema(db_path)

    df = dim_icb.build_icb_hierarchy_df()

    # Lần ghi 1
    n1 = dim_icb.write_icb_hierarchy(df, con)
    assert n1 == 177
    cnt1 = con.execute("SELECT COUNT(*) FROM core.dim_icb_hierarchy").fetchone()[0]
    assert cnt1 == 177

    # Lần ghi 2 (ghi đè đồng bộ)
    n2 = dim_icb.write_icb_hierarchy(df, con)
    assert n2 == 177
    cnt2 = con.execute("SELECT COUNT(*) FROM core.dim_icb_hierarchy").fetchone()[0]
    assert cnt2 == 177


def test_write_icb_hierarchy_schema_validation(tmp_path):
    """Kiểm tra bắt lỗi nếu DataFrame thiếu cột bắt buộc."""
    db_path = tmp_path / "test_icb_invalid.duckdb"
    con = db.bootstrap_schema(db_path)

    bad_df = pd.DataFrame({"icb_code": ["8355"], "level": [4]})
    with pytest.raises(ValueError, match="DataFrame thiếu các cột bắt buộc"):
        dim_icb.write_icb_hierarchy(bad_df, con)
