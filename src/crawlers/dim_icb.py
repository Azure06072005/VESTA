"""src/crawlers/dim_icb.py

Xây dựng từ điển ánh xạ phân ngành chuẩn ICB 4 cấp (F001 Khuyến nghị):
- Cấp 1 (Industry): 11 ngành cơ bản (0001 Dầu khí, 1000 Nguyên vật liệu, 2000 Công nghiệp,...)
- Cấp 2 (Supersector): 19 ngành cấp 2 (0500, 1300, 1700, 2300, 8300 Ngân hàng, 8600 BĐS,...)
- Cấp 3 (Sector): 40 ngành cấp 3
- Cấp 4 (Subsector): 107 tiểu ngành chi tiết

Dựa trên chuẩn phân ngành ICB chính thức áp dụng tại HOSE và HNX,
loại bỏ hoàn toàn sự không nhất quán từ chuỗi ký tự tự do của các vendor khác nhau.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crawlers.db_writer import DEFAULT_TARGET_DB, ResilientDuckDBWriter
from etl import db

logger = logging.getLogger("dim_icb")

# Ánh xạ tĩnh từ Supersector (Cấp 2) về Industry (Cấp 1) chuẩn ICB
SUPERSECTOR_TO_INDUSTRY: Dict[str, str] = {
    "0500": "0001",  # Dầu khí -> Dầu khí
    "1300": "1000",  # Hóa chất -> Nguyên vật liệu
    "1700": "1000",  # Tài nguyên Cơ bản -> Nguyên vật liệu
    "2300": "2000",  # Xây dựng và Vật liệu -> Công nghiệp
    "2700": "2000",  # Hàng & Dịch vụ Công nghiệp -> Công nghiệp
    "3300": "3000",  # Thực phẩm và Đồ uống -> Hàng Tiêu dùng
    "3500": "3000",  # Đồ dùng cá nhân và đồ gia dụng -> Hàng Tiêu dùng
    "3700": "3000",  # Ô tô và phụ tùng -> Hàng Tiêu dùng
    "4500": "4000",  # Y tế -> Dược phẩm và Y tế
    "5300": "5000",  # Bán lẻ -> Dịch vụ Tiêu dùng
    "5500": "5000",  # Truyền thông -> Dịch vụ Tiêu dùng
    "5700": "5000",  # Du lịch và Giải trí -> Dịch vụ Tiêu dùng
    "6500": "6000",  # Viễn thông -> Viễn thông
    "7500": "7000",  # Tiện ích Cộng đồng (Điện, nước, xăng dầu) -> Tiện ích
    "8300": "8000",  # Ngân hàng -> Tài chính
    "8500": "8000",  # Bảo hiểm -> Tài chính
    "8600": "8000",  # Bất động sản -> Tài chính
    "8700": "8000",  # Dịch vụ tài chính (Chứng khoán, Quỹ) -> Tài chính
    "8900": "8000",  # Quỹ đầu tư -> Tài chính
    "9500": "9000",  # Công nghệ Thông tin -> Công nghệ
}

# Bổ sung mã alias nhà cung cấp hay dùng cho ngân hàng
VENDOR_ALIAS_MAP: Dict[str, str] = {
    "8301": "8300",  # Alias Ngân hàng của vnstock
}

ICB_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS core.dim_icb_hierarchy (
    icb_code            VARCHAR NOT NULL PRIMARY KEY,
    level               INTEGER NOT NULL,
    icb_name_vi         VARCHAR NOT NULL,
    icb_name_en         VARCHAR NOT NULL,
    parent_code         VARCHAR,
    industry_code       VARCHAR NOT NULL,
    industry_name_vi    VARCHAR NOT NULL,
    industry_name_en    VARCHAR NOT NULL,
    supersector_code    VARCHAR,
    supersector_name_vi VARCHAR,
    supersector_name_en VARCHAR,
    sector_code         VARCHAR,
    sector_name_vi      VARCHAR,
    sector_name_en      VARCHAR,
    subsector_code      VARCHAR,
    subsector_name_vi   VARCHAR,
    subsector_name_en   VARCHAR,
    updated_at          TIMESTAMP NOT NULL
);
"""


def fetch_raw_icb(force_online: bool = False) -> pd.DataFrame:
    """Lấy danh bạ mã ngành gốc và tên song ngữ từ từ điển tĩnh hoặc vnstock."""
    fallback_json = PROJECT_ROOT / "configs" / "icb_classification.json"
    if not force_online and fallback_json.exists():
        with open(fallback_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return pd.DataFrame(data)

    db.load_env()
    try:
        import vnstock_data as vs
        listing = vs.Listing(source="vci")
        df = listing.industries_icb()
        return df
    except Exception as e:
        logger.warning("Không thể gọi API online cho ICB: %s. Sử dụng bộ fallback tĩnh.", e)
        if fallback_json.exists():
            with open(fallback_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            return pd.DataFrame(data)
        raise RuntimeError("Không có nguồn dữ liệu ICB online lẫn fallback tĩnh.")


def build_icb_hierarchy(df_raw: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Xây dựng bảng phân cấp hoàn chỉnh 4 tầng từ danh bạ ICB gốc."""
    if df_raw is None:
        df_raw = fetch_raw_icb()
    df = df_raw.copy()
    if "icb_name_vi" in df.columns and "icb_name" not in df.columns:
        # Đã là DataFrame phân cấp hoàn chỉnh (đọc từ configs/icb_classification.json)
        return df

    df["icb_code"] = df["icb_code"].astype(str).str.strip().str.zfill(4)
    df["level"] = df["level"].astype(int)
    df["icb_name"] = df["icb_name"].fillna("").astype(str).str.strip()
    df["en_icb_name"] = df["en_icb_name"].fillna(df["icb_name"]).astype(str).str.strip()

    # Tạo từ điển tra cứu nhanh từng cấp
    code_to_meta: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        code = row["icb_code"]
        code_to_meta[code] = {
            "level": row["level"],
            "name_vi": row["icb_name"],
            "name_en": row["en_icb_name"],
        }

    # Bổ sung mã alias nếu cần
    for alias, canonical in VENDOR_ALIAS_MAP.items():
        if canonical in code_to_meta and alias not in code_to_meta:
            code_to_meta[alias] = code_to_meta[canonical].copy()

    records = []
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    for _, row in df.iterrows():
        code = row["icb_code"]
        lvl = row["level"]
        name_vi = row["icb_name"]
        name_en = row["en_icb_name"]

        l1_code, l1_vi, l1_en = "", "", ""
        l2_code, l2_vi, l2_en = None, None, None
        l3_code, l3_vi, l3_en = None, None, None
        l4_code, l4_vi, l4_en = None, None, None
        parent_code = None

        if lvl == 1:
            l1_code = code
            l1_vi = name_vi
            l1_en = name_en
            parent_code = None

        elif lvl == 2:
            l2_code = code
            l2_vi = name_vi
            l2_en = name_en
            l1_code = SUPERSECTOR_TO_INDUSTRY.get(code, "8000" if code.startswith("8") else code[0] + "000")
            parent_code = l1_code
            if l1_code in code_to_meta:
                l1_vi = code_to_meta[l1_code]["name_vi"]
                l1_en = code_to_meta[l1_code]["name_en"]

        elif lvl == 3:
            l3_code = code
            l3_vi = name_vi
            l3_en = name_en
            # Cấp 3 -> Cấp 2
            cand_l2 = code[:2] + "00"
            if cand_l2 == "8900":
                cand_l2 = "8700"
            if cand_l2 in code_to_meta:
                l2_code = cand_l2
                l2_vi = code_to_meta[cand_l2]["name_vi"]
                l2_en = code_to_meta[cand_l2]["name_en"]
            parent_code = l2_code or (code[:2] + "00")
            # Cấp 2 -> Cấp 1
            if l2_code and l2_code in SUPERSECTOR_TO_INDUSTRY:
                l1_code = SUPERSECTOR_TO_INDUSTRY[l2_code]
            else:
                l1_code = code[0] + "000" if code != "0530" else "0001"
            if l1_code in code_to_meta:
                l1_vi = code_to_meta[l1_code]["name_vi"]
                l1_en = code_to_meta[l1_code]["name_en"]

        elif lvl == 4:
            l4_code = code
            l4_vi = name_vi
            l4_en = name_en
            if not code.isdigit() or len(code) != 4:
                l3_code, l3_vi, l3_en = "OTHER", "Khác", "Other"
                l2_code, l2_vi, l2_en = "OTHER", "Khác", "Other"
                l1_code, l1_vi, l1_en = "OTHER", "Khác", "Other"
                parent_code = "OTHER"
            else:
                # Cấp 4 -> Cấp 3
                cand_l3 = code[:3] + "0"
                if cand_l3 in code_to_meta:
                    l3_code = cand_l3
                    l3_vi = code_to_meta[cand_l3]["name_vi"]
                    l3_en = code_to_meta[cand_l3]["name_en"]
                parent_code = l3_code or cand_l3
                # Cấp 3 -> Cấp 2
                cand_l2 = code[:2] + "00"
                if cand_l2 == "8900":
                    cand_l2 = "8700"
                if cand_l2 in code_to_meta:
                    l2_code = cand_l2
                    l2_vi = code_to_meta[cand_l2]["name_vi"]
                    l2_en = code_to_meta[cand_l2]["name_en"]
                # Cấp 2 -> Cấp 1
                if l2_code and l2_code in SUPERSECTOR_TO_INDUSTRY:
                    l1_code = SUPERSECTOR_TO_INDUSTRY[l2_code]
                else:
                    l1_code = code[0] + "000" if code.startswith("0") else "1000"
                if l1_code in code_to_meta:
                    l1_vi = code_to_meta[l1_code]["name_vi"]
                    l1_en = code_to_meta[l1_code]["name_en"]

        records.append({
            "icb_code": code,
            "level": lvl,
            "icb_name_vi": name_vi,
            "icb_name_en": name_en,
            "parent_code": parent_code,
            "industry_code": l1_code,
            "industry_name_vi": l1_vi,
            "industry_name_en": l1_en,
            "supersector_code": l2_code,
            "supersector_name_vi": l2_vi,
            "supersector_name_en": l2_en,
            "sector_code": l3_code,
            "sector_name_vi": l3_vi,
            "sector_name_en": l3_en,
            "subsector_code": l4_code,
            "subsector_name_vi": l4_vi,
            "subsector_name_en": l4_en,
            "updated_at": now,
        })

    out_df = pd.DataFrame(records)
    return out_df


def save_static_config(df_hierarchy: pd.DataFrame) -> pathlib.Path:
    """Lưu bản từ điển tĩnh vào configs/icb_classification.json."""
    config_path = PROJECT_ROOT / "configs" / "icb_classification.json"
    records = df_hierarchy.to_dict(orient="records")
    # Chuyển đổi timestamp sang isoformat
    for r in records:
        if isinstance(r["updated_at"], dt.datetime):
            r["updated_at"] = r["updated_at"].isoformat()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    logger.info("Đã lưu từ điển ICB tĩnh vào: %s (%d mã ngành)", config_path, len(records))
    return config_path


build_icb_hierarchy_df = build_icb_hierarchy


def load_static_icb_classification() -> Dict[str, Dict[str, Any]]:
    """Nạp từ điển phân ngành tĩnh từ configs/icb_classification.json."""
    config_path = PROJECT_ROOT / "configs" / "icb_classification.json"
    if not config_path.exists():
        df = build_icb_hierarchy()
        save_static_config(df)
    with open(config_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    return {str(item["icb_code"]).zfill(4): item for item in items}


def write_icb_hierarchy(
    df_hierarchy: pd.DataFrame,
    writer: Optional[ResilientDuckDBWriter | duckdb.DuckDBPyConnection] = None,
    con: Optional[duckdb.DuckDBPyConnection] = None,
) -> int:
    """Ghi bảng phân ngành 4 tầng vào core.dim_icb_hierarchy an toàn với ResilientDuckDBWriter."""
    required_cols = {"icb_code", "icb_name_vi", "level"}
    if not required_cols.issubset(set(df_hierarchy.columns)):
        raise ValueError(f"DataFrame thiếu các cột bắt buộc: {required_cols - set(df_hierarchy.columns)}")

    if con is None and isinstance(writer, duckdb.DuckDBPyConnection):
        con = writer
        writer = None

    if con is not None:
        con.execute(ICB_SCHEMA_DDL)
        con.execute("DELETE FROM core.dim_icb_hierarchy")
        con.register("df_icb_view", df_hierarchy)
        con.execute("""
            INSERT INTO core.dim_icb_hierarchy
            SELECT * FROM df_icb_view
        """)
        con.unregister("df_icb_view")
        cnt = con.execute("SELECT count(*) FROM core.dim_icb_hierarchy").fetchone()[0]
        return cnt

    writer = writer or ResilientDuckDBWriter()

    def _action(c: duckdb.DuckDBPyConnection):
        c.execute(ICB_SCHEMA_DDL)
        c.execute("DELETE FROM core.dim_icb_hierarchy")
        c.register("df_icb_view", df_hierarchy)
        c.execute("""
            INSERT INTO core.dim_icb_hierarchy
            SELECT * FROM df_icb_view
        """)
        c.unregister("df_icb_view")
        return len(df_hierarchy)

    cnt = writer.execute_with_retry(_action)
    try:
        writer.atomic_ingest_buffer()
    except Exception as e:
        logger.debug("Atomic ingest skipped/deferred: %s", e)
    return cnt


def run(
    target_db: Optional[str] = None,
    con: Optional[duckdb.DuckDBPyConnection] = None,
) -> int:
    """Hàm chạy chính của crawler dim_icb."""
    logger.info(">>> [F001] Bắt đầu xây dựng từ điển phân ngành chuẩn ICB 4 cấp...")
    df_raw = fetch_raw_icb()
    df_hier = build_icb_hierarchy(df_raw)
    save_static_config(df_hier)

    if con is not None:
        cnt = write_icb_hierarchy(df_hier, con=con)
        logger.info(">>> [F001] Hoàn tất từ điển phân ngành ICB: %d bản ghi đã lưu.", cnt)
        return cnt

    if target_db:
        writer = ResilientDuckDBWriter(target_db=target_db)
    else:
        writer = ResilientDuckDBWriter()

    cnt = write_icb_hierarchy(df_hier, writer=writer)
    logger.info(">>> [F001] Hoàn tất từ điển phân ngành ICB: %d bản ghi đã lưu.", cnt)
    return cnt


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run()
