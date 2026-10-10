"""src/etl/merge_temp_to_canonical.py

Phân hệ Hợp nhất & Thăng cấp Dữ liệu Cào từ 3 CSDL Tạm (Temp) vào 3 CSDL Chính (Main Canonical).
Kiến trúc Staging-to-Core:
1. Trong quá trình cào:
   - Dữ liệu OHLCV ghi vào: `db/temp/temp_ohlcv.duckdb`
   - Dữ liệu Tin tức ghi vào: `db/temp/temp_news.duckdb`
   - Dữ liệu Snapshot/BCTC ghi vào: `db/temp/temp_snapshot.duckdb`
   -> CSDL chính (`vesta_ohlcv.duckdb`, `vesta_news.duckdb`, `vesta_snapshot.duckdb`) hoàn toàn KHÔNG BỊ KHÓA,
      cho phép Web Console, API và Backtest đọc với tốc độ tối đa không bị gián đoạn.
2. Sau khi cào xong:
   - Module này thực thi ATTACH CSDL tạm và MERGE (INSERT OR REPLACE / INSERT OR IGNORE) vào CSDL chính một cách an toàn.
   - Làm sạch / làm mới dữ liệu trong CSDL tạm để chuẩn bị cho chu kỳ cào tiếp theo.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional, Tuple

import duckdb

logger = logging.getLogger("merge_temp_canonical")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMP_DIR = REPO_ROOT / "db" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

TEMP_OHLCV_DB = str(TEMP_DIR / "temp_ohlcv.duckdb")
TEMP_NEWS_DB = str(TEMP_DIR / "temp_news.duckdb")
TEMP_MARKET_INDEX_DB = str(TEMP_DIR / "temp_market_index.duckdb")
TEMP_FUNDAMENTALS_DB = str(TEMP_DIR / "temp_fundamentals.duckdb")
TEMP_EVENTS_DB = str(TEMP_DIR / "temp_events.duckdb")
TEMP_SNAPSHOT_DB = str(TEMP_DIR / "temp_snapshot.duckdb")

MAIN_OHLCV_DB = str(REPO_ROOT / "db" / "vesta_ohlcv.duckdb")
MAIN_NEWS_DB = str(REPO_ROOT / "db" / "vesta_news.duckdb")
MAIN_FUNDAMENTALS_DB = str(REPO_ROOT / "db" / "vesta_fundamentals.duckdb")
MAIN_EVENTS_DB = str(REPO_ROOT / "db" / "vesta_events.duckdb")
MAIN_MARKET_INDEX_DB = str(REPO_ROOT / "db" / "vesta_market_index.duckdb")
ADMIN_DIR = REPO_ROOT / "db" / "admin"
ADMIN_DIR.mkdir(parents=True, exist_ok=True)


def merge_single_temp_db(
    temp_db_path: str,
    main_db_path: str,
    label: str,
) -> Dict[str, Any]:
    """Hợp nhất tất cả bảng từ một CSDL tạm vào CSDL chính tương ứng."""
    if not os.path.exists(temp_db_path):
        return {"label": label, "status": "SKIPPED_NOT_FOUND", "tables": {}}

    logger.info(f"[{label}] Bắt đầu hợp nhất từ {temp_db_path} -> {main_db_path}...")
    merged_stats = {}

    try:
        # Kiểm tra CSDL tạm có bảng nào có dữ liệu không
        con_temp = duckdb.connect(temp_db_path, read_only=True)
        tables_to_merge = []
        for schema in ["core", "staging"]:
            try:
                tbls = con_temp.execute(f"""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = '{schema}' AND table_type = 'BASE TABLE'
                """).fetchall()
                for (t,) in tbls:
                    cnt = con_temp.execute(f"SELECT COUNT(*) FROM {schema}.{t}").fetchone()[0]
                    if cnt > 0:
                        tables_to_merge.append((schema, t, cnt))
            except Exception:
                pass
        con_temp.close()

        if not tables_to_merge:
            logger.info(f"[{label}] Không có bản ghi mới trong CSDL tạm. Bỏ qua.")
            return {"label": label, "status": "EMPTY", "tables": {}}

        # Mở kết nối ghi vào CSDL chính hoặc dự phòng sang db/admin/ nếu bị khóa file bởi tiến trình khác
        target_db_path = main_db_path
        con_main = None
        for cand in [main_db_path, str(ADMIN_DIR / os.path.basename(main_db_path))]:
            try:
                con_main = duckdb.connect(cand, read_only=False)
                target_db_path = cand
                break
            except Exception as e:
                logger.warning(f"[{label}] Không thể mở ghi {cand}: {e}")

        if con_main is None:
            raise RuntimeError(f"Không thể mở kết nối ghi tới {main_db_path} hoặc dự phòng admin")

        con_main.execute(f"ATTACH '{temp_db_path}' AS temp_src (READ_ONLY);")

        for schema, table, count in tables_to_merge:
            try:
                con_main.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
                
                # Kiểm tra bảng đích đã tồn tại chưa
                dest_exists = con_main.execute(f"""
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_schema = '{schema}' AND table_name = '{table}'
                """).fetchone()[0] > 0

                if not dest_exists:
                    # Tạo bảng mới sao chép schema từ bảng tạm
                    con_main.execute(f"CREATE TABLE {schema}.{table} AS SELECT * FROM temp_src.{schema}.{table} WHERE 1=0;")

                # CỔNG KIỂM SOÁT CHẤT LƯỢNG & KHỬ TRÙNG LẶP DO FETCHED_AT (DATA QUALITY & DEDUP GATE)
                col_info = con_main.execute(f"PRAGMA table_info(temp_src.{schema}.{table});").fetchall()
                cols = [c[1] for c in col_info]

                bkeys = []
                if "symbol" in cols and "date" in cols:
                    bkeys = ["symbol", "date"]
                elif "symbol" in cols and "time" in cols:
                    bkeys = ["symbol", "time"]
                elif "symbol" in cols and "period_end" in cols:
                    bkeys = ["symbol", "period_end"]
                elif "index_code" in cols and "date" in cols:
                    bkeys = ["index_code", "date"]
                elif "article_id" in cols:
                    bkeys = ["article_id"]
                elif "source_url" in cols:
                    bkeys = ["source_url"]
                elif "url" in cols:
                    bkeys = ["url"]
                elif "symbol" in cols and "event_date" in cols and "event_type" in cols:
                    bkeys = ["symbol", "event_date", "event_type"]
                elif "symbol" in cols and "shareholder_name" in cols:
                    bkeys = ["symbol", "shareholder_name"]
                elif "source" in cols and "doc_number" in cols:
                    bkeys = ["source", "doc_number"]

                if bkeys:
                    key_cols_str = ", ".join([f'"{k}"' for k in bkeys])
                    order_col = "fetched_at" if "fetched_at" in cols else "rowid"
                    
                    # 1. Deduplicate dữ liệu tạm trước khi nạp
                    con_main.execute(f"""
                        CREATE OR REPLACE TEMPORARY TABLE _incoming_clean AS
                        SELECT * EXCLUDE (_rn) FROM (
                            SELECT *, ROW_NUMBER() OVER(PARTITION BY {key_cols_str} ORDER BY "{order_col}" DESC) as _rn
                            FROM temp_src.{schema}.{table}
                        ) WHERE _rn = 1;
                    """)

                    # 2. Xóa các bản ghi cũ trùng khóa nghiệp vụ trong CSDL chính
                    con_main.execute(f"""
                        DELETE FROM {schema}.{table}
                        WHERE ({key_cols_str}) IN (SELECT {key_cols_str} FROM _incoming_clean);
                    """)

                    # 3. Nạp bản ghi mới nhất sạch 100%
                    con_main.execute(f"""
                        INSERT INTO {schema}.{table}
                        SELECT * FROM _incoming_clean;
                    """)
                    con_main.execute("DROP TABLE IF EXISTS _incoming_clean;")
                else:
                    # Fallback cho bảng không xác định được khóa đơn lẻ
                    try:
                        con_main.execute(f"""
                            INSERT OR REPLACE INTO {schema}.{table}
                            SELECT * FROM temp_src.{schema}.{table};
                        """)
                    except Exception:
                        try:
                            con_main.execute(f"""
                                INSERT OR IGNORE INTO {schema}.{table}
                                SELECT * FROM temp_src.{schema}.{table};
                            """)
                        except Exception:
                            con_main.execute(f"""
                                INSERT INTO {schema}.{table}
                                SELECT DISTINCT * FROM temp_src.{schema}.{table};
                            """)

                total_in_main = con_main.execute(f"SELECT COUNT(*) FROM {schema}.{table}").fetchone()[0]
                merged_stats[f"{schema}.{table}"] = {
                    "temp_rows": count,
                    "main_total_rows": total_in_main,
                }
                logger.info(f"  • {schema}.{table}: Đã hợp nhất {count:,} hàng -> Tổng {total_in_main:,} hàng.")
            except Exception as te:
                logger.warning(f"  ⚠ Lỗi hợp nhất bảng {schema}.{table}: {te}")
                merged_stats[f"{schema}.{table}"] = {"error": str(te)}

        con_main.execute("DETACH temp_src;")
        con_main.close()

        # Làm sạch CSDL tạm sau khi đã hợp nhất thành công
        try:
            con_temp_clear = duckdb.connect(temp_db_path, read_only=False)
            for schema, table, _ in tables_to_merge:
                try:
                    con_temp_clear.execute(f"DELETE FROM {schema}.{table};")
                except Exception:
                    pass
            con_temp_clear.close()
            logger.info(f"[{label}] Đã xóa bộ đệm CSDL tạm thành công.")
        except Exception as ce:
            logger.warning(f"[{label}] Cảnh báo khi xóa bộ đệm tạm: {ce}")

        return {
            "label": label,
            "status": "SUCCESS",
            "tables": merged_stats,
        }

    except Exception as e:
        logger.error(f"[{label}] Lỗi trong quá trình hợp nhất: {e}", exc_info=True)
        return {
            "label": label,
            "status": "ERROR",
            "error": str(e),
            "tables": merged_stats,
        }


def merge_all_temp_databases() -> Dict[str, Any]:
    """Hợp nhất toàn bộ các CSDL tạm vào các CSDL chính và đồng bộ sang db/admin/."""
    import shutil
    t0 = dt.datetime.now()
    results = {
        "timestamp": t0.isoformat(),
        "ohlcv": merge_single_temp_db(TEMP_OHLCV_DB, MAIN_OHLCV_DB, "OHLCV"),
        "news": merge_single_temp_db(TEMP_NEWS_DB, MAIN_NEWS_DB, "NEWS"),
    }
    # Hợp nhất các CSDL tạm chuyên biệt
    if os.path.exists(TEMP_MARKET_INDEX_DB):
        results["market_index"] = merge_single_temp_db(TEMP_MARKET_INDEX_DB, MAIN_MARKET_INDEX_DB, "MARKET_INDEX")
    if os.path.exists(TEMP_FUNDAMENTALS_DB):
        results["fundamentals"] = merge_single_temp_db(TEMP_FUNDAMENTALS_DB, MAIN_FUNDAMENTALS_DB, "FUNDAMENTALS")
    if os.path.exists(TEMP_EVENTS_DB):
        results["events"] = merge_single_temp_db(TEMP_EVENTS_DB, MAIN_EVENTS_DB, "EVENTS")

    # Hỗ trợ tương thích ngược nếu còn bảng tạm trong temp_snapshot.duckdb
    if os.path.exists(TEMP_SNAPSHOT_DB):
        if os.path.exists(MAIN_MARKET_INDEX_DB):
            results["legacy_market_index"] = merge_single_temp_db(TEMP_SNAPSHOT_DB, MAIN_MARKET_INDEX_DB, "LEGACY_MARKET_INDEX")
        if os.path.exists(MAIN_FUNDAMENTALS_DB):
            results["legacy_fundamentals"] = merge_single_temp_db(TEMP_SNAPSHOT_DB, MAIN_FUNDAMENTALS_DB, "LEGACY_FUNDAMENTALS")
        if os.path.exists(MAIN_EVENTS_DB):
            results["legacy_events"] = merge_single_temp_db(TEMP_SNAPSHOT_DB, MAIN_EVENTS_DB, "LEGACY_EVENTS")

    # Tự động đồng bộ các CSDL giữa db/ và db/admin/
    admin_sync_count = 0
    canonical_dbs = [MAIN_OHLCV_DB, MAIN_NEWS_DB, MAIN_FUNDAMENTALS_DB, MAIN_EVENTS_DB, MAIN_MARKET_INDEX_DB]
    for db_file in canonical_dbs:
        admin_file = os.path.join(str(ADMIN_DIR), os.path.basename(db_file))
        # 1. Thử copy db -> admin nếu db mới hơn
        if os.path.exists(db_file) and (not os.path.exists(admin_file) or os.path.getmtime(db_file) > os.path.getmtime(admin_file)):
            try:
                shutil.copy2(db_file, admin_file)
                admin_sync_count += 1
            except Exception as se:
                logger.debug(f"Không thể sync sang admin cho {db_file}: {se}")
        # 2. Thử copy admin -> db nếu admin mới hơn
        elif os.path.exists(admin_file) and (not os.path.exists(db_file) or os.path.getmtime(admin_file) > os.path.getmtime(db_file)):
            try:
                shutil.copy2(admin_file, db_file)
                admin_sync_count += 1
            except Exception as se:
                logger.debug(f"db/{os.path.basename(db_file)} đang bị khóa, giữ nguyên tại admin: {se}")
    results["admin_synced_databases"] = admin_sync_count

    elapsed = (dt.datetime.now() - t0).total_seconds()
    results["elapsed_seconds"] = round(elapsed, 2)
    logger.info(f"Hoàn thành hợp nhất và đồng bộ sang admin trong {elapsed:.2f} giây.")
    return results


if __name__ == "__main__":
    import json
    res = merge_all_temp_databases()
    print(json.dumps(res, indent=2, ensure_ascii=False))
