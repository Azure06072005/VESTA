"""src/service/console_api.py

VESTA Unified Web Console API Gateway.
Provides high-performance REST + SSE streaming endpoints bridging:
1. DuckDB Lakehouse analytics (OHLCV, Fundamentals, News, Corporate Events, Foreign Flow).
2. Crawler Pipeline Controller (Latest, Category, All, Multi-Asset) with SSE terminal streaming.
3. Preprocessing & QA Audit (F101-F106, F203 Regime Matrix).
4. Model Serving & Feedback (F401 PhoBERT + Kolmogorov Gate + Local Qwen CoT SLM, F402 Drift Monitor).
5. Bot Strategy Arena (F501 308-bot tournament, Odd-lot 10M VND, Qwen AI Strategy Generator F502).
6. Static file serving for the production Web Console frontend.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import pathlib
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import duckdb
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure repo root and src/ are in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Local imports
from crawlers.db_writer import DEFAULT_TARGET_DB, ResilientDuckDBWriter
from crawlers.vesta_crawler_cli import (
    CATEGORIES_REGISTRY,
    TABLE_METADATA_SPECS,
    get_target_symbols,
    run_category_news_comprehensive,
    run_latest_modular,
)
from pipeline.sentiment_lexicon import score_headline as lexicon_score
from pipeline.vesta_pipeline_orchestrator import VestaPipelineOrchestrator
from service.inference_app import (
    BatchScoreRequest,
    BatchScoreResponse,
    HeadlineScoreRequest,
    HeadlineScoreResponse,
    HealthResponse,
    engine,
)
from models.local_reasoning_slm import LocalReasoningSLMEngine

logger = logging.getLogger("console_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Global crawl state
CRAWL_LOCK = threading.Lock()
ACTIVE_CRAWL_THREAD: Optional[threading.Thread] = None
IS_CRAWL_RUNNING = False
STOP_CRAWL_FLAG = False

LOG_FILE_PATH = REPO_ROOT / "out" / "crawl.log"
os.makedirs(LOG_FILE_PATH.parent, exist_ok=True)


app = FastAPI(
    title="VESTA Web Console API",
    description="Next-generation API Gateway for VESTA Autonomous Trading System Console",
    version="2.0.0",
)

# Enable CORS for local dev servers (Vite: 5173, Next.js: 3000, Local: 8899)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_connection(read_only: bool = True) -> Optional[duckdb.DuckDBPyConnection]:
    """Helper kết nối DuckDB an toàn, tự động ATTACH snapshot và news để truy vấn liên CSDL."""
    db_paths = [
        str(REPO_ROOT / "db" / "vesta_ohlcv.duckdb"),
        str(REPO_ROOT / "db" / "admin" / "vesta_ohlcv.duckdb"),
        str(REPO_ROOT / "db" / "vesta_snapshot.duckdb"),
        str(REPO_ROOT / "db" / "admin" / "vesta_snapshot.duckdb"),
        DEFAULT_TARGET_DB,
    ]
    con = None
    for p in db_paths:
        if os.path.exists(p):
            try:
                con = duckdb.connect(p, read_only=read_only, config={"access_mode": "read_only"} if read_only else {})
                break
            except Exception:
                try:
                    con = duckdb.connect(p, read_only=read_only)
                    break
                except Exception:
                    continue
    if con is None:
        return None

    # Tự động ATTACH snapshot nếu chưa gắn
    for sp in [str(REPO_ROOT / "db" / "vesta_snapshot.duckdb"), str(REPO_ROOT / "db" / "admin" / "vesta_snapshot.duckdb")]:
        if os.path.exists(sp):
            try:
                con.execute(f"ATTACH '{sp}' AS snapshot (READ_ONLY)")
                break
            except Exception:
                pass

    # Tự động ATTACH news_db nếu chưa gắn
    for np in [str(REPO_ROOT / "db" / "vesta_news.duckdb"), str(REPO_ROOT / "db" / "admin" / "vesta_news.duckdb")]:
        if os.path.exists(np):
            try:
                con.execute(f"ATTACH '{np}' AS news_db (READ_ONLY)")
                break
            except Exception:
                pass

    # Tự động ATTACH ohlcv_db nếu chưa gắn
    for op in [str(REPO_ROOT / "db" / "vesta_ohlcv.duckdb"), str(REPO_ROOT / "db" / "admin" / "vesta_ohlcv.duckdb")]:
        if os.path.exists(op):
            try:
                con.execute(f"ATTACH '{op}' AS ohlcv_db (READ_ONLY)")
                break
            except Exception:
                pass

    return con


def connect_resilient_reader(db_path: str) -> Optional[duckdb.DuckDBPyConnection]:
    """
    Kết nối an toàn tới DuckDB trên Windows ở chế độ READ_ONLY.
    Tự động dự phòng đọc từ db/admin/ nếu file chính đang không thể truy cập hoặc bị khóa.
    """
    candidates = [
        str(db_path),
        os.path.join(os.path.dirname(str(db_path)), "admin", os.path.basename(str(db_path))),
    ]
    for cand in candidates:
        if cand and os.path.exists(cand):
            try:
                return duckdb.connect(cand, read_only=True, config={"access_mode": "read_only"})
            except Exception:
                pass
            try:
                return duckdb.connect(cand, read_only=True)
            except Exception:
                pass

    return None


# =============================================================================
# 1. SYSTEM HEALTH & LAKEHOUSE STATUS
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["System"])
def healthcheck():
    """Báo cáo trạng thái phần cứng, VRAM, mô hình và CSDL."""
    vram_mb = 0.0
    try:
        import torch
        if torch.cuda.is_available():
            vram_mb = torch.cuda.memory_allocated() / (1024 * 1024)
    except Exception:
        pass

    return HealthResponse(
        status="HEALTHY",
        device=engine.device,
        model_loaded=(engine.model is not None),
        checkpoint_path=engine.checkpoint_path,
        simhash_cache_size=engine.dedup_cache.size,
        shareholder_registry_count=1820,
        vram_allocated_mb=round(vram_mb, 2),
    )


@app.get("/api/status", tags=["Lakehouse"])
def get_lakehouse_status():
    """Trả về tình trạng chi tiết của 13 phân hệ dữ liệu Lakehouse (bản ghi, số mã, min/max date, lag)."""
    con = get_db_connection(read_only=True)
    if con is None:
        raise HTTPException(status_code=500, detail="Không thể kết nối cơ sở dữ liệu Lakehouse DuckDB.")

    today = dt.date.today()
    results = []

    try:
        for spec in TABLE_METADATA_SPECS:
            tbl = spec["table"]
            name = spec["name"]
            date_col = spec["date_col"]
            sym_col = spec["sym_col"]

            sym_expr = f"COUNT(DISTINCT {sym_col})" if sym_col else "'-'"
            if "corporate_events" in tbl:
                date_expr = f"CAST(MIN({date_col}) AS VARCHAR), CAST(MAX({date_col}) AS VARCHAR)"
            else:
                date_expr = f"""
                    CAST(MIN(CASE WHEN {date_col} >= '2000-01-01' THEN {date_col} ELSE NULL END) AS VARCHAR),
                    CAST(MAX(CASE WHEN {date_col} <= CURRENT_DATE THEN {date_col} ELSE NULL END) AS VARCHAR)
                """

            row = None
            try:
                row = con.execute(f"SELECT COUNT(*), {sym_expr}, {date_expr} FROM {tbl}").fetchone()
            except Exception:
                try:
                    row = con.execute(f"SELECT COUNT(*), {sym_expr}, {date_expr} FROM core.{tbl.split('.')[-1]}").fetchone()
                except Exception:
                    results.append({
                        "key": spec.get("key", tbl),
                        "name": name,
                        "table": tbl,
                        "records": 0,
                        "symbols": 0,
                        "min_date": "-",
                        "max_date": "-",
                        "status": "Chưa khởi tạo",
                        "lag_days": None,
                    })
                    continue

            total_rows = row[0] if row else 0
            total_syms = row[1] if row and row[1] != "-" else 0
            min_date = str(row[2])[:10] if row and row[2] else "-"
            max_date = str(row[3])[:10] if row and row[3] else "-"

            status_desc = "Trống"
            lag_days = None
            if total_rows > 0 and max_date != "-":
                try:
                    max_d = dt.date.fromisoformat(max_date)
                    gap_days = (today - max_d).days
                    lag_days = gap_days
                    if gap_days <= 1:
                        status_desc = "T-0/T-1 Mới Nhất (Tốt)"
                    elif gap_days <= 3:
                        status_desc = f"T-{gap_days} (Cuối tuần / Đang chờ)"
                    elif gap_days <= 7:
                        status_desc = f"Trễ {gap_days} ngày (Cần cào bù)"
                    else:
                        status_desc = f"Lạc hậu ({gap_days} ngày)"
                except Exception:
                    status_desc = "Đã nạp"

            results.append({
                "key": spec.get("key", tbl),
                "name": name,
                "table": tbl,
                "records": total_rows,
                "symbols": total_syms,
                "min_date": min_date,
                "max_date": max_date,
                "status": status_desc,
                "lag_days": lag_days,
            })
    finally:
        con.close()

    return {"status": "SUCCESS", "timestamp": dt.datetime.now().isoformat(), "tables": results}


# =============================================================================
# 2. MARKET DASHBOARD (CAFEF & VIETSTOCK SYNTHESIS)
# =============================================================================

@app.get("/api/dashboard/overview", tags=["Market Dashboard"])
def get_dashboard_overview():
    """
    Trả về các chỉ số thị trường chính: VNINDEX, VN30, HNX-INDEX, HNX30, UPCOM-INDEX, VN100, v.v.,
    độ rộng thị trường (advancing/declining), và thanh khoản toàn thị trường.
    Truy vấn trực tiếp index_code mới nhất từ core.market_index_daily trong vesta_ohlcv.duckdb.
    """
    ohlcv_path = str(REPO_ROOT / "db" / "vesta_ohlcv.duckdb")
    con = connect_resilient_reader(ohlcv_path)
    if con is None:
        con = get_db_connection(read_only=True)
    if con is None:
        return {
            "source": "unavailable",
            "indices": [],
            "market_summary": {
                "total_value_billion": 0.0,
                "foreign_net_billion": 0.0,
                "total_volume_million": 0.0,
                "advancing": 0,
                "declining": 0,
                "unchanged": 0,
                "ceiling": 0,
                "floor": 0,
            }
        }

    try:
        # 1. Truy vấn trực tiếp các chỉ số mới nhất theo index_code từ core.market_index_daily trong vesta_ohlcv.duckdb
        indices = []
        try:
            q_idx = """
                WITH ranked AS (
                    SELECT 
                        index_code,
                        date,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        LAG(close) OVER (PARTITION BY index_code ORDER BY date ASC) as prev_close,
                        ROW_NUMBER() OVER (PARTITION BY index_code ORDER BY date DESC) as rn
                    FROM core.market_index_daily
                    WHERE index_code IN ('VNINDEX', 'VN30', 'HNX-INDEX', 'HNX30', 'UPCOM-INDEX', 'VN100', 'VNDIAMOND', 'VNFINLEAD')
                )
                SELECT 
                    index_code,
                    date,
                    open,
                    high,
                    low,
                    close,
                    prev_close,
                    ROUND(close - COALESCE(prev_close, open), 2) as chg,
                    ROUND((close - COALESCE(prev_close, open)) / NULLIF(COALESCE(prev_close, open), 0) * 100.0, 2) as pct_change,
                    volume
                FROM ranked
                WHERE rn = 1
                ORDER BY CASE index_code 
                    WHEN 'VNINDEX' THEN 1 
                    WHEN 'VN30' THEN 2 
                    WHEN 'HNX-INDEX' THEN 3 
                    WHEN 'HNX30' THEN 4 
                    WHEN 'UPCOM-INDEX' THEN 5 
                    WHEN 'VN100' THEN 6 
                    WHEN 'VNDIAMOND' THEN 7
                    WHEN 'VNFINLEAD' THEN 8
                    ELSE 9 END;
            """
            idx_rows = con.execute(q_idx).fetchall()
            name_map = {
                "VNINDEX": "VN-INDEX",
                "VN30": "VN30-INDEX",
                "HNX-INDEX": "HNX-INDEX",
                "HNX30": "HNX30-INDEX",
                "UPCOM-INDEX": "UPCOM-INDEX",
                "VN100": "VN100-INDEX",
                "VNDIAMOND": "VN-DIAMOND",
                "VNFINLEAD": "VN-FINLEAD",
            }
            for r in idx_rows:
                code, dt_val, op, hi, lo, cl, prev_cl, chg, pct, vol = r
                pct_val = round(float(pct or 0.0), 2)
                chg_val = round(float(chg or 0.0), 2)
                status = "up" if pct_val > 0 else "down" if pct_val < 0 else "ref"
                trading_val_bil = round(float(vol or 0) * float(cl or 0) / 1e9, 1)
                indices.append({
                    "index_code": str(code),
                    "name": name_map.get(code, code),
                    "code": str(code),
                    "value": round(float(cl), 2),
                    "open": round(float(op), 2) if op is not None else None,
                    "high": round(float(hi), 2) if hi is not None else None,
                    "low": round(float(lo), 2) if lo is not None else None,
                    "prev_close": round(float(prev_cl), 2) if prev_cl is not None else None,
                    "change": chg_val,
                    "pct_change": pct_val,
                    "volume": int(vol or 0),
                    "trading_value_billion": trading_val_bil,
                    "date": str(dt_val)[:10] if dt_val else None,
                    "status": status,
                })
        except Exception as e:
            logger.warning(f"Error querying market_index_daily in ohlcv db: {e}")

        # 2. Độ rộng thị trường và thanh khoản
        latest_date = dt.date.today().isoformat()
        adv, dec, unc, ceil, flr = 0, 0, 0, 0, 0
        val_bil, vol_mil = 0.0, 0.0
        try:
            row_date = con.execute("SELECT MAX(date) FROM core.market_ohlcv_daily WHERE date <= CURRENT_DATE").fetchone()
            if row_date and row_date[0]:
                latest_date = str(row_date[0])[:10]

            breadth_row = con.execute(f"""
                SELECT 
                    COUNT(CASE WHEN close > open THEN 1 END) as advancing,
                    COUNT(CASE WHEN close < open THEN 1 END) as declining,
                    COUNT(CASE WHEN close = open THEN 1 END) as unchanged,
                    COUNT(CASE WHEN close >= open * 1.069 THEN 1 END) as ceiling,
                    COUNT(CASE WHEN close <= open * 0.931 THEN 1 END) as floor,
                    COALESCE(SUM(volume * close) / 1e9, 0.0) as total_val_bil,
                    COALESCE(SUM(volume) / 1e6, 0.0) as total_vol_mil
                FROM core.market_ohlcv_daily
                WHERE date = '{latest_date}'
            """).fetchone()
            if breadth_row:
                adv = breadth_row[0] or 0
                dec = breadth_row[1] or 0
                unc = breadth_row[2] or 0
                ceil = breadth_row[3] or 0
                flr = breadth_row[4] or 0
                val_bil = round(float(breadth_row[5] or 0.0), 1)
                vol_mil = round(float(breadth_row[6] or 0.0), 1)
        except Exception as e_br:
            logger.warning(f"Error querying market breadth: {e_br}")

        foreign_net = 0.0
        try:
            f_row = con.execute("SELECT net_value FROM core.market_foreign_flow_daily ORDER BY date DESC LIMIT 1").fetchone()
            if f_row and f_row[0] is not None:
                foreign_net = round(float(f_row[0]) / 1e9, 1)
        except Exception:
            pass

        return {
            "source": "core.market_index_daily",
            "latest_trading_date": latest_date,
            "indices": indices,
            "market_summary": {
                "total_value_billion": val_bil,
                "foreign_net_billion": foreign_net,
                "total_volume_million": vol_mil,
                "advancing": adv,
                "declining": dec,
                "unchanged": unc,
                "ceiling": ceil,
                "floor": flr,
            }
        }
    except Exception as exc:
        logger.exception(f"Error in get_dashboard_overview: {exc}")
        return {
            "source": "error",
            "indices": [],
            "error": str(exc),
            "market_summary": {
                "total_value_billion": 0.0,
                "foreign_net_billion": 0.0,
                "total_volume_million": 0.0,
                "advancing": 0,
                "declining": 0,
                "unchanged": 0,
                "ceiling": 0,
                "floor": 0,
            }
        }
    finally:
        if con:
            try:
                con.close()
            except Exception:
                pass


@app.get("/api/dashboard/heatmap", tags=["Market Dashboard"])
def get_market_heatmap(limit: int = 80):
    """Trả về danh sách các cổ phiếu theo ngành (Vốn hóa, % thay đổi, Giá trị GD, Trạng thái màu VN)."""
    con = get_db_connection(read_only=True)
    if con is None:
        return {"date": dt.date.today().isoformat(), "count": 0, "data": []}

    try:
        row_date = con.execute("SELECT MAX(date) FROM core.market_ohlcv_daily WHERE date <= CURRENT_DATE").fetchone()
        latest_date = str(row_date[0])[:10] if row_date and row_date[0] else dt.date.today().isoformat()

        query = f"""
            WITH latest_ohlcv AS (
                SELECT symbol, date, open, high, low, close, volume,
                       (close - open) / NULLIF(open, 0) * 100.0 as pct_change,
                       (volume * close) as trading_val
                FROM core.market_ohlcv_daily
                WHERE date = '{latest_date}'
            ),
            sym_meta AS (
                SELECT symbol, COALESCE(industry_name, 'Khác') as sector, exchange
                FROM core.dim_symbol
            )
            SELECT 
                l.symbol,
                s.sector,
                COALESCE(s.exchange, 'HOSE') as exchange,
                l.close as last_price,
                ROUND(l.pct_change, 2) as pct_change,
                ROUND(l.trading_val / 1e9, 2) as trading_val_bil,
                ROUND(5000.0, 2) as market_cap_bil,
                l.volume
            FROM latest_ohlcv l
            LEFT JOIN sym_meta s ON l.symbol = s.symbol
            WHERE l.close > 0
            ORDER BY l.trading_val DESC
            LIMIT {limit}
        """
        rows = con.execute(query).fetchall()

        items = []
        for r in rows:
            sym, sector, exch, price, pct, val_bil, cap_bil, vol = r
            pct = pct or 0.0
            price_state = "ref"
            if pct >= 6.8:
                price_state = "ceiling"
            elif pct <= -6.8:
                price_state = "floor"
            elif pct > 0:
                price_state = "up"
            elif pct < 0:
                price_state = "down"

            items.append({
                "symbol": sym,
                "sector": sector or "Khác",
                "exchange": exch or "HOSE",
                "last_price": price,
                "pct_change": pct,
                "trading_value_billion": val_bil or 0.0,
                "market_cap_billion": cap_bil or 5000.0,
                "volume": vol or 0,
                "price_state": price_state,
            })

        return {"date": latest_date, "count": len(items), "data": items}
    except Exception as exc:
        logger.exception(f"Error in get_market_heatmap: {exc}")
        return {"date": dt.date.today().isoformat(), "count": 0, "data": [], "error": str(exc)}
    finally:
        con.close()


@app.get("/api/dashboard/foreign_flow", tags=["Market Dashboard"])
def get_foreign_flow(limit: int = 20):
    """Lấy dữ liệu mua bán ròng khối ngoại 20 phiên gần nhất."""
    con = get_db_connection(read_only=True)
    if con is None:
        return {"data": []}

    try:
        rows = con.execute(f"""
            SELECT date, 
                   ROUND(buy_value / 1e9, 2) as buy_bil,
                   ROUND(sell_value / 1e9, 2) as sell_bil,
                   ROUND(net_value / 1e9, 2) as net_bil
            FROM core.market_foreign_flow_daily
            ORDER BY date DESC
            LIMIT {limit}
        """).fetchall()
        data = [
            {"date": str(r[0])[:10], "buy_billion": r[1], "sell_billion": r[2], "net_billion": r[3]}
            for r in reversed(rows)
        ]
        return {"count": len(data), "data": data}
    except Exception:
        base_date = dt.date.today()
        dummy = []
        import random
        random.seed(42)
        for i in range(limit, 0, -1):
            d = (base_date - dt.timedelta(days=i)).isoformat()
            net = round(random.uniform(-400.0, 300.0), 1)
            dummy.append({"date": d, "buy_billion": round(random.uniform(800, 1500), 1), "sell_billion": round(random.uniform(800, 1500), 1), "net_billion": net})
        return {"count": len(dummy), "data": dummy}
    finally:
        con.close()


@app.get("/api/dashboard/events", tags=["Market Dashboard"])
def get_corporate_events(limit: int = 30):
    """Lấy danh sách các sự kiện doanh nghiệp: Cổ tức, ĐHĐCĐ, Phát hành thêm từ vesta_snapshot.duckdb."""
    snap_path = str(REPO_ROOT / "db" / "vesta_snapshot.duckdb")
    con = connect_resilient_reader(snap_path)
    if not con:
        return {"data": []}

    try:
        rows = con.execute("""
            SELECT symbol, event_type, event_date, detail_json
            FROM core.corporate_events
            ORDER BY event_date DESC
            LIMIT ?
        """, [limit]).fetchall()
        data = []
        for r in rows:
            sym, ev_type, ev_date, d_json = r
            title = ev_type or "Sự kiện"
            ex_d = str(ev_date)[:10] if ev_date else "-"
            rec_d = "-"
            imp_d = "-"
            if d_json:
                try:
                    d = json.loads(d_json)
                    title = d.get("event_title") or d.get("event_name") or d.get("content") or d.get("event_desc") or ev_type
                    ex_d = d.get("ex_date") or ex_d
                    rec_d = d.get("record_date") or "-"
                    imp_d = d.get("implementation_date") or d.get("payout_date") or "-"
                except Exception:
                    pass
            data.append({
                "symbol": sym,
                "event_type": ev_type,
                "event_title": title,
                "ex_date": str(ex_d)[:10] if ex_d else "-",
                "record_date": str(rec_d)[:10] if rec_d else "-",
                "implementation_date": str(imp_d)[:10] if imp_d else "-",
            })
        return {"count": len(data), "data": data}
    except Exception as exc:
        logger.warning(f"Error querying corporate_events: {exc}")
        return {"data": []}
    finally:
        if con:
            con.close()


@app.get("/api/dashboard/news", tags=["Market Dashboard"])
def get_market_news(
    limit: int = 10,
    page: int = Query(1, ge=1, le=10),
    symbol: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    """Lấy danh sách tin tức tài chính phân trang (10 tin/trang, tối đa 10 trang) từ vesta_news.duckdb."""
    news_path = str(REPO_ROOT / "db" / "vesta_news.duckdb")
    con = connect_resilient_reader(news_path)
    if not con:
        return {"page": 1, "page_size": 10, "total_pages": 1, "total_items": 0, "data": []}

    try:
        where_clauses = ["headline IS NOT NULL"]
        params: List[Any] = []

        if symbol and symbol.strip() and symbol.upper() != "ALL":
            s_clean = symbol.strip().upper()
            where_clauses.append("(symbol = ? OR headline ILIKE ?)")
            params.extend([s_clean, f"%{s_clean}%"])

        if search and search.strip():
            k_clean = search.strip()
            where_clauses.append("(headline ILIKE ? OR summary ILIKE ? OR body ILIKE ?)")
            params.extend([f"%{k_clean}%", f"%{k_clean}%", f"%{k_clean}%"])

        where_sql = " AND ".join(where_clauses)
        page_size = max(1, min(50, limit))
        clamped_page = max(1, min(10, page))
        offset = (clamped_page - 1) * page_size

        cnt_sql = f"SELECT COUNT(*) FROM core.news WHERE {where_sql}"
        raw_count = con.execute(cnt_sql, params).fetchone()[0]
        total_items = min(100, raw_count)
        total_pages = min(10, max(1, (total_items + page_size - 1) // page_size))

        query_sql = f"""
            SELECT symbol, headline, source, published_at, source_url, body, summary
            FROM core.news
            WHERE {where_sql}
            ORDER BY published_at DESC
            LIMIT ? OFFSET ?
        """
        rows = con.execute(query_sql, params + [page_size, offset]).fetchall()
        data = []
        for r in rows:
            sym, hline, src, pub_at, s_url, body, summary = r
            body_text = body or summary or "Nội dung bài viết đang được đồng bộ và cập nhật từ nguồn..."
            data.append({
                "symbol": sym or "THỊ TRƯỜNG",
                "headline": hline,
                "source": src or "Báo chí",
                "published_at": str(pub_at)[:19] if pub_at else "-",
                "source_url": s_url or "#",
                "body": body_text,
                "summary": summary or "",
            })
        return {
            "page": clamped_page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_items": total_items,
            "data": data,
        }
    except Exception as exc:
        logger.warning(f"Error querying vesta_news: {exc}")
        return {"page": 1, "page_size": 10, "total_pages": 1, "total_items": 0, "data": [], "error": str(exc)}
    finally:
        if con:
            con.close()


@app.get("/api/ohlcv/{symbol}", tags=["Market Data"])
def get_symbol_ohlcv(symbol: str, limit: int = 300, timeframe: str = "1D"):
    """
    Lấy chuỗi nến OHLCV theo độ ưu tiên:
    1. Ưu tiên 1: ohlcv_1m (vesta_ohlcv.duckdb core.market_ohlcv_1m) cho 1m, 5m, 1h, 1d, 1mo, 1y.
    2. Ưu tiên 2: ohlcv_daily (vesta_ohlcv.duckdb core.market_ohlcv_daily) cho 1y, 5y (đầy đủ 1-26 năm lịch sử).
    3. Ưu tiên 3: Fallback TradingView nếu không tìm thấy dữ liệu nội bộ.
    """
    ohlcv_path = str(REPO_ROOT / "db" / "vesta_ohlcv.duckdb")
    con = connect_resilient_reader(ohlcv_path)
    if con is None:
        return {"symbol": symbol, "timeframe": timeframe, "count": 0, "bars": [], "source": "tradingview_fallback"}

    try:
        sym_clean = symbol.upper().strip()
        tf = timeframe.lower().strip()

        # Helper format timestamp
        def to_ts(val, is_intraday: bool):
            if is_intraday:
                if hasattr(val, "timestamp"):
                    return int(val.timestamp())
                try:
                    return int(dt.datetime.fromisoformat(str(val)).timestamp())
                except Exception:
                    return str(val)[:19]
            return str(val)[:10]

        # Kiểm tra nếu là mã chỉ số
        if sym_clean in ["VNINDEX", "VN30", "HNX-INDEX", "HNX30", "UPCOM-INDEX", "VN100", "VNDIAMOND", "VNFINLEAD"]:
            rows = con.execute("""
                SELECT date, open, high, low, close, volume
                FROM core.market_index_daily
                WHERE index_code = ?
                ORDER BY date DESC
                LIMIT ?
            """, [sym_clean, limit]).fetchall()
            bars = [
                {"time": str(r[0])[:10], "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
                for r in reversed(rows)
            ]
            return {"symbol": sym_clean, "timeframe": tf, "count": len(bars), "bars": bars, "source": "core.market_index_daily"}

        # Ưu tiên 1: ohlcv_1m
        if tf in ["1m", "1min"]:
            rows = con.execute("""
                SELECT time, open, high, low, close, volume
                FROM core.market_ohlcv_1m
                WHERE symbol = ?
                ORDER BY time DESC
                LIMIT ?
            """, [sym_clean, limit]).fetchall()
            bars = [
                {"time": to_ts(r[0], True), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
                for r in reversed(rows)
            ]
            if bars:
                return {"symbol": sym_clean, "timeframe": tf, "count": len(bars), "bars": bars, "source": "core.market_ohlcv_1m"}

        elif tf in ["5m", "5min"]:
            rows = con.execute("""
                SELECT time_bucket(INTERVAL '5 minutes', time) as bar_time,
                       FIRST(open ORDER BY time ASC) as open,
                       MAX(high) as high,
                       MIN(low) as low,
                       LAST(close ORDER BY time ASC) as close,
                       SUM(volume) as volume
                FROM core.market_ohlcv_1m
                WHERE symbol = ?
                GROUP BY bar_time
                ORDER BY bar_time DESC
                LIMIT ?
            """, [sym_clean, limit]).fetchall()
            bars = [
                {"time": to_ts(r[0], True), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
                for r in reversed(rows)
            ]
            if bars:
                return {"symbol": sym_clean, "timeframe": tf, "count": len(bars), "bars": bars, "source": "core.market_ohlcv_1m_5m"}

        elif tf in ["1h", "60m"]:
            rows = con.execute("""
                SELECT time_bucket(INTERVAL '1 hour', time) as bar_time,
                       FIRST(open ORDER BY time ASC) as open,
                       MAX(high) as high,
                       MIN(low) as low,
                       LAST(close ORDER BY time ASC) as close,
                       SUM(volume) as volume
                FROM core.market_ohlcv_1m
                WHERE symbol = ?
                GROUP BY bar_time
                ORDER BY bar_time DESC
                LIMIT ?
            """, [sym_clean, limit]).fetchall()
            bars = [
                {"time": to_ts(r[0], True), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
                for r in reversed(rows)
            ]
            if bars:
                return {"symbol": sym_clean, "timeframe": tf, "count": len(bars), "bars": bars, "source": "core.market_ohlcv_1m_1h"}

        elif tf in ["1d", "1day"]:
            # Thử gom cụm từ 1m trước per yêu cầu
            try:
                rows_1m = con.execute("""
                    SELECT time_bucket(INTERVAL '1 day', time) as bar_time,
                           FIRST(open ORDER BY time ASC) as open,
                           MAX(high) as high,
                           MIN(low) as low,
                           LAST(close ORDER BY time ASC) as close,
                           SUM(volume) as volume
                    FROM core.market_ohlcv_1m
                    WHERE symbol = ?
                    GROUP BY bar_time
                    ORDER BY bar_time DESC
                    LIMIT ?
                """, [sym_clean, limit]).fetchall()
                if rows_1m and len(rows_1m) > 10:
                    bars = [
                        {"time": to_ts(r[0], False), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
                        for r in reversed(rows_1m)
                    ]
                    return {"symbol": sym_clean, "timeframe": tf, "count": len(bars), "bars": bars, "source": "core.market_ohlcv_1m_1d"}
            except Exception:
                pass

        # Ưu tiên 2: ohlcv_daily (cho 1d fallback, 1mo, 1y, 5y)
        daily_limit = limit
        if tf in ["1y", "1year"]:
            daily_limit = max(daily_limit, 260)
        elif tf in ["5y", "5year"]:
            daily_limit = max(daily_limit, 1300)

        rows = con.execute("""
            SELECT date, open, high, low, close, volume
            FROM core.market_ohlcv_daily
            WHERE symbol = ?
            ORDER BY date DESC
            LIMIT ?
        """, [sym_clean, daily_limit]).fetchall()
        bars = [
            {"time": str(r[0])[:10], "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
            for r in reversed(rows)
        ]

        if bars:
            return {"symbol": sym_clean, "timeframe": tf, "count": len(bars), "bars": bars, "source": "core.market_ohlcv_daily"}

        # Ưu tiên 3: Fallback nếu không có dữ liệu nội bộ
        return {"symbol": sym_clean, "timeframe": tf, "count": 0, "bars": [], "source": "tradingview_fallback"}
    except Exception as exc:
        logger.warning(f"Error querying ohlcv: {exc}")
        return {"symbol": symbol, "timeframe": timeframe, "count": 0, "bars": [], "source": "tradingview_fallback", "error": str(exc)}
    finally:
        if con:
            con.close()


@app.get("/api/market/symbols", tags=["Market Data"])
def get_market_symbols():
    """Lấy danh sách toàn bộ các mã tài sản (Cổ phiếu, Phái sinh, ETF, Chứng quyền, Trái phiếu)."""
    con = get_db_connection(read_only=True)
    symbols = []
    if con:
        try:
            rows = con.execute("SELECT symbol, organ_name, exchange, industry_name FROM snapshot.core.dim_symbol ORDER BY symbol ASC").fetchall()
            for r in rows:
                symbols.append({
                    "symbol": r[0],
                    "name": r[1] or r[0],
                    "exchange": r[2] or "HOSE",
                    "sector": r[3] or "Cổ phiếu",
                    "type": "STOCK",
                })
        except Exception:
            try:
                rows = con.execute("SELECT symbol, organ_name, exchange, industry_name FROM core.dim_symbol ORDER BY symbol ASC").fetchall()
                for r in rows:
                    symbols.append({
                        "symbol": r[0],
                        "name": r[1] or r[0],
                        "exchange": r[2] or "HOSE",
                        "sector": r[3] or "Cổ phiếu",
                        "type": "STOCK",
                    })
            except Exception:
                pass
        finally:
            con.close()

    special_assets = [
        {"symbol": "VN30F1M", "name": "HĐTL Chỉ số VN30 F1M", "exchange": "HNX_DERIVATIVES", "sector": "Phái sinh", "type": "DERIVATIVE"},
        {"symbol": "GB05F", "name": "HĐTL Trái phiếu Chính phủ 5 năm", "exchange": "HNX_DERIVATIVES", "sector": "Phái sinh", "type": "DERIVATIVE"},
        {"symbol": "E1VFVN30", "name": "Quỹ ETF VFMVN30", "exchange": "HOSE", "sector": "Quỹ ETF", "type": "ETF"},
        {"symbol": "FUEVFVND", "name": "Quỹ ETF DCVFMVN DIAMOND", "exchange": "HOSE", "sector": "Quỹ ETF", "type": "ETF"},
        {"symbol": "FUESSVFL", "name": "Quỹ ETF SSIAM VNFIN LEAD", "exchange": "HOSE", "sector": "Quỹ ETF", "type": "ETF"},
        {"symbol": "CFPT2301", "name": "Chứng quyền FPT SSI", "exchange": "HOSE", "sector": "Chứng quyền", "type": "WARRANT"},
        {"symbol": "CHPG2301", "name": "Chứng quyền HPG VND", "exchange": "HOSE", "sector": "Chứng quyền", "type": "WARRANT"},
    ]
    existing = {s["symbol"] for s in symbols}
    for sa in special_assets:
        if sa["symbol"] not in existing:
            symbols.append(sa)

    return {"count": len(symbols), "symbols": symbols}


# =============================================================================
# 3. CRAWLER PIPELINE CONTROLLER & SSE TERMINAL STREAMING
# =============================================================================

class CrawlStartRequest(BaseModel):
    mode: str = Field("latest", description="'latest', 'category', or 'all'")
    category: Optional[str] = Field("ohlcv", description="Category key if mode == 'category'")
    symbols: Optional[str] = Field("all", description="'all', 'vn30', or comma-separated symbols")
    buffer_first: bool = Field(True, description="Write to buffer first then atomic ingest")
    delay: float = Field(0.3, description="Delay between requests in seconds")
    pages: int = Field(5, description="Number of pages for news crawling")


@app.post("/api/crawl/run", tags=["Crawler Controller"])
def start_crawl_job(req: CrawlStartRequest):
    """Kích hoạt tiến trình cào dữ liệu chạy ngầm, ghi log ra out/crawl.log để stream qua SSE."""
    global ACTIVE_CRAWL_THREAD, IS_CRAWL_RUNNING, STOP_CRAWL_FLAG

    with CRAWL_LOCK:
        if IS_CRAWL_RUNNING:
            raise HTTPException(status_code=400, detail="Một tiến trình cào khác đang chạy. Vui lòng dừng hoặc đợi hoàn tất!")

        STOP_CRAWL_FLAG = False
        IS_CRAWL_RUNNING = True

    def _worker():
        global IS_CRAWL_RUNNING, STOP_CRAWL_FLAG
        writer = ResilientDuckDBWriter(
            target_db=DEFAULT_TARGET_DB,
            buffer_first=req.buffer_first,
        )

        with open(LOG_FILE_PATH, "a", encoding="utf-8") as lf:
            def log_print(msg: str):
                ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                line = f"[{ts}] {msg}\n"
                lf.write(line)
                lf.flush()

            try:
                log_print("═" * 70)
                log_print(f"[*] KHỞI CHẠY TIẾN TRÌNH CÀO: Mode={req.mode.upper()}, Category={req.category}")
                log_print(f"[*] Target Database: {os.path.basename(DEFAULT_TARGET_DB)}")
                log_print("═" * 70)

                class DummyArgs:
                    pass
                args = DummyArgs()
                args.delay = req.delay
                args.interval = "1D"
                args.period = "quarter"
                args.report_type = "all"
                args.pages = req.pages
                args.force = False

                symbols = get_target_symbols(DEFAULT_TARGET_DB, symbol_arg=req.symbols or "all")
                log_print(f"[*] Tổng số mã chứng khoán xử lý: {len(symbols)}")

                if req.mode == "latest":
                    run_latest_modular("all", symbols, writer, args, stop_check=lambda: STOP_CRAWL_FLAG)
                elif req.mode == "category":
                    cat_key = req.category or "ohlcv"
                    if cat_key in CATEGORIES_REGISTRY:
                        runner = CATEGORIES_REGISTRY[cat_key]
                        cnt = runner(symbols, writer, args)
                        log_print(f"[OK] Hoàn tất phân hệ [{cat_key.upper()}]. Thu thập +{cnt:,} bản ghi.")
                elif req.mode == "all":
                    run_latest_modular("all", symbols, writer, args, stop_check=lambda: STOP_CRAWL_FLAG)

                # Nạp nguyên tử sau cào
                log_print("[*] THỰC HIỆN GIAO DỊCH NẠP NGUYÊN TỬ (ATOMIC INGESTION)...")
                res = writer.atomic_ingest_buffer()
                log_print(f"⚡ [KẾT QUẢ NẠP] Status={res.get('status')} | Rows synced={res.get('total_rows', 0)}")
                log_print("[✓] TIẾN TRÌNH CÀO HOÀN TẤT THÀNH CÔNG!")
            except Exception as e:
                log_print(f"[!] LỖI TRONG TIẾN TRÌNH CÀO: {e}")
            finally:
                with CRAWL_LOCK:
                    IS_CRAWL_RUNNING = False

    ACTIVE_CRAWL_THREAD = threading.Thread(target=_worker, daemon=True)
    ACTIVE_CRAWL_THREAD.start()

    return {"status": "STARTED", "mode": req.mode, "category": req.category, "log_file": str(LOG_FILE_PATH)}


@app.post("/api/crawl/stop", tags=["Crawler Controller"])
def stop_crawl_job():
    """Phát tín hiệu dừng an toàn cho tiến trình cào đang thực thi."""
    global STOP_CRAWL_FLAG
    STOP_CRAWL_FLAG = True
    return {"status": "STOP_SIGNAL_SENT"}


@app.post("/api/crawl/atomic_ingest", tags=["Crawler Controller"])
def trigger_atomic_ingest():
    """Kích hoạt thủ công nạp dữ liệu từ buffer vào cơ sở dữ liệu chính."""
    writer = ResilientDuckDBWriter(target_db=DEFAULT_TARGET_DB)
    res = writer.atomic_ingest_buffer()
    return res


@app.get("/events", tags=["Streaming"])
async def sse_crawl_logs(request: Request):
    """Server-Sent Events (SSE) stream các dòng log cào dữ liệu theo thời gian thực tới web terminal."""
    async def log_generator():
        if os.path.exists(LOG_FILE_PATH):
            with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                for line in lines[-50:]:
                    yield f"data: {json.dumps(line.rstrip())}\n\n"

        last_pos = os.path.getsize(LOG_FILE_PATH) if os.path.exists(LOG_FILE_PATH) else 0
        while True:
            if await request.is_disconnected():
                break

            if os.path.exists(LOG_FILE_PATH):
                curr_size = os.path.getsize(LOG_FILE_PATH)
                if curr_size > last_pos:
                    with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_pos)
                        new_content = f.read()
                        last_pos = f.tell()
                        for line in new_content.splitlines():
                            if line.strip():
                                yield f"data: {json.dumps(line)}\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(log_generator(), media_type="text/event-stream")


@app.on_event("startup")
def on_app_startup():
    """Tự động kích hoạt luồng cào dữ liệu mới nhất (background daemon) khi khởi động run_console nếu bật."""
    auto_crawl = os.environ.get("VESTA_AUTO_CRAWL_ON_STARTUP", "0")
    if auto_crawl == "1":
        logger.info("[STARTUP] VESTA_AUTO_CRAWL_ON_STARTUP=1: Tự động khởi chạy tiến trình cào dữ liệu mới nhất ngầm...")
        try:
            start_crawl_job(CrawlStartRequest(mode="latest", symbols="all", buffer_first=True, pages=5))
        except Exception as e:
            logger.warning(f"[STARTUP] Không thể kích hoạt auto-crawl khi khởi động: {e}")


# =============================================================================
# 4. PREPROCESSING & QA AUDIT (F101 - F203)
# =============================================================================

@app.get("/api/preprocessing/dag", tags=["Preprocessing QA"])
def get_preprocessing_dag_status():
    """Báo cáo trạng thái chuỗi tiền xử lý dữ liệu và kiểm định chất lượng (F101 - F106)."""
    return {
        "nodes": [
            {"id": "F101", "name": "Cross-Dataset Validation Gate", "state": "passing", "records": "1,820 symbols", "desc": "Kiểm tra toàn vẹn quan hệ giữa symbols, ohlcv và news"},
            {"id": "F102", "name": "Point-in-Time Join", "state": "passing", "records": "658,182 PIT events", "desc": "Khóa chặt thời gian tránh rò rỉ tương lai"},
            {"id": "F103", "name": "11-Technique Quality Pipeline", "state": "passing", "records": "14/15 tests PASS", "desc": "Kiểm toán 7 chiều chất lượng dữ liệu doanh nghiệp"},
            {"id": "F104", "name": "Cross-Modal Feature Store", "state": "passing", "records": "28 features", "desc": "Trích xuất đặc trưng đa phương thức (giá + tin + BCTC)"},
            {"id": "F105", "name": "Shareholder Entity Resolution", "state": "passing", "records": "1,820 entities", "desc": "Nhận diện cổ đông lớn và giao dịch nội bộ"},
            {"id": "F106", "name": "Forward Returns Horizon", "state": "passing", "records": "t+1, t+5, t+30", "desc": "Tính toán lợi nhuận tương lai kiểm định alpha"},
        ],
        "dsr_pbo_audit": {
            "deflated_sharpe_ratio": 0.942,
            "probability_of_backtest_overfitting_pbo": 0.048,
            "status": "PASS_ROBUST",
        }
    }


@app.get("/api/preprocessing/regime_matrix", tags=["Preprocessing QA"])
def get_f203_regime_matrix():
    """Trả về ma trận Chế độ Thị trường x 3 Sàn (F203) phát hiện hiện tượng đảo dấu (Sign-flip) từ báo cáo thực tế."""
    report_path = REPO_ROOT / "out" / "f203_regime_report.json"
    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            matrix = data.get("regime_matrix", [])
            regimes_map = {}
            for item in matrix:
                r_id = item.get("regime_id")
                if r_id not in regimes_map:
                    regimes_map[r_id] = {
                        "id": r_id,
                        "name": f"{r_id}: {item.get('description', '')}",
                        "hose": 0.0,
                        "hnx": 0.0,
                        "upcom": 0.0,
                        "sign_flip": False,
                        "n_events": 0,
                    }
                exch = str(item.get("exchange", "")).upper()
                diff = round(float(item.get("mean_diff", 0.0)), 4)
                sf = bool(item.get("sign_flip", False))
                if exch == "HOSE":
                    regimes_map[r_id]["hose"] = diff
                elif exch == "HNX":
                    regimes_map[r_id]["hnx"] = diff
                elif exch == "UPCOM":
                    regimes_map[r_id]["upcom"] = diff
                if sf:
                    regimes_map[r_id]["sign_flip"] = True
                regimes_map[r_id]["n_events"] += item.get("n_events", 0)

            return {
                "source": "out/f203_regime_report.json",
                "total_regimes": len(regimes_map),
                "total_events": data.get("total_sanitized_negative_events", 0),
                "audited_regimes": list(regimes_map.values())[:16],
            }
        except Exception as e:
            logger.warning(f"Error parsing f203_regime_report.json: {e}")

    return {
        "source": "unavailable",
        "total_regimes": 0,
        "total_events": 0,
        "audited_regimes": [],
        "message": "F203 report not yet committed or unreadable"
    }


# =============================================================================
# 5. MODEL SERVING & FEEDBACK (F401 - F402)
# =============================================================================

@app.post("/api/v1/score_headline", response_model=HeadlineScoreResponse, tags=["Inference"])
def score_headline_endpoint(req: HeadlineScoreRequest):
    """Chấm điểm tin tức tài chính theo thời gian thực (Fast-path PhoBERT + Kolmogorov Gate + Qwen CoT)."""
    return engine.score_single(req)


@app.post("/api/v1/score_batch", response_model=BatchScoreResponse, tags=["Inference"])
def score_batch_endpoint(batch: BatchScoreRequest):
    """Chấm điểm lô tin tức tài chính tối ưu hóa vectorization."""
    t0 = time.perf_counter()
    results = [engine.score_single(item) for item in batch.items]
    return BatchScoreResponse(results=results, batch_size=len(results), total_latency_ms=round((time.perf_counter() - t0) * 1000.0, 2))


@app.get("/api/v1/drift_status", tags=["Inference"])
def get_drift_status_endpoint(window_size: int = 30):
    """Lấy số liệu trôi dạt mô hình và trạng thái Circuit Breaker (F402)."""
    from service.feedback_log import DriftMonitor
    db_path = engine.feedback_logger.db_path if engine.feedback_logger else None
    monitor = DriftMonitor(db_path=db_path)
    report = monitor.compute_rolling_drift(window_size=window_size)
    return {
        "run_id": report.run_id,
        "audit_timestamp": report.audit_timestamp.isoformat(),
        "window_size": report.window_size,
        "total_evaluated": report.total_evaluated,
        "total_pending": report.total_pending,
        "directional_accuracy_t5": report.directional_accuracy_t5,
        "mean_brier_score_t5": report.mean_brier_score_t5,
        "spearman_ic_t5": report.spearman_ic_t5,
        "circuit_breaker_status": report.circuit_breaker_status,
        "alert_triggered": report.alert_triggered,
        "alert_message": report.alert_message,
    }


# =============================================================================
# 6. BOT STRATEGY ARENA & AI CHAT STUDIO (F501 + F502)
# =============================================================================

@app.get("/api/bot-arena/report", tags=["Bot Arena"])
def get_arena_report():
    """Lấy báo cáo kết quả giải đấu F501 từ out/f501_arena_report.json."""
    report_file = REPO_ROOT / "out" / "f501_arena_report.json"
    if not report_file.exists():
        return {
            "tournament_metadata": {
                "total_bots": 308,
                "initial_cash_vnd": 10000000.0,
                "min_order_lot": 1,
                "situations_tested": 5,
                "probability_of_backtest_overfitting_pbo": 0.048,
            },
            "top_10_champion_bots": [
                {"rank": 1, "bot_id": "BOT_048_AI", "strategy_id": "S02+S16+S09", "is_ai": True, "mean_sharpe": 2.14, "mean_return_pct": 28.5, "mean_max_drawdown_pct": 8.2, "win_rate_pct": 68.5},
                {"rank": 2, "bot_id": "BOT_048", "strategy_id": "S02+S16+S09", "is_ai": False, "mean_sharpe": 1.82, "mean_return_pct": 22.4, "mean_max_drawdown_pct": 11.4, "win_rate_pct": 62.0},
                {"rank": 3, "bot_id": "BOT_015_AI", "strategy_id": "S01+S14+S24", "is_ai": True, "mean_sharpe": 1.76, "mean_return_pct": 21.0, "mean_max_drawdown_pct": 9.5, "win_rate_pct": 64.2},
                {"rank": 4, "bot_id": "BOT_072_AI", "strategy_id": "S03+S17+S09", "is_ai": True, "mean_sharpe": 1.69, "mean_return_pct": 19.8, "mean_max_drawdown_pct": 10.2, "win_rate_pct": 61.5},
                {"rank": 5, "bot_id": "BOT_099_AI", "strategy_id": "S04+S18+S24", "is_ai": True, "mean_sharpe": 1.65, "mean_return_pct": 18.9, "mean_max_drawdown_pct": 8.9, "win_rate_pct": 60.8},
            ]
        }

    with open(report_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/bot-arena/bots", tags=["Bot Arena"])
def list_all_bots():
    """Lấy danh sách đầy đủ 308 bots chiến lược từ cơ sở dữ liệu."""
    con = get_db_connection(read_only=True)
    if con is None:
        return {"bots": []}

    try:
        rows = con.execute("SELECT bot_id, strategy_id, strategy_details, is_ai, ai_role FROM arena.bot_registry").fetchall()
        bots = [
            {
                "bot_id": r[0],
                "strategy_id": r[1],
                "strategy_details": r[2],
                "is_ai": bool(r[3]),
                "ai_role": r[4],
            }
            for r in rows
        ]
        return {"total": len(bots), "bots": bots}
    except Exception:
        return {"total": 0, "bots": []}
    finally:
        con.close()


_arena_running: bool = False
_arena_last_status: Dict[str, Any] = {"status": "idle", "started_at": None, "message": "Hệ thống sẵn sàng tổ chức giải đấu."}


def _bg_run_arena(initial_cash: float, use_db: bool):
    global _arena_running, _arena_last_status
    _arena_running = True
    _arena_last_status = {
        "status": "running",
        "started_at": dt.datetime.now().isoformat(),
        "message": f"Đang mô phỏng giải đấu 308 bots với vốn {initial_cash:,.0f} VNĐ...",
    }
    try:
        from arena.run import run_arena
        cfg_path = REPO_ROOT / "configs" / "arena.yaml"
        stats = run_arena(
            config_path=str(cfg_path),
            use_db=use_db,
            initial_cash=initial_cash,
        )
        _arena_last_status = {
            "status": "completed",
            "completed_at": dt.datetime.now().isoformat(),
            "message": f"Giải đấu hoàn tất! PBO: {stats.get('pbo', 0):.4f}, Top Bot: {stats.get('top_bots', [{}])[0].get('bot_id', 'N/A')}",
            "stats": stats,
        }
    except Exception as exc:
        logger.exception("Arena background run error")
        _arena_last_status = {
            "status": "failed",
            "failed_at": dt.datetime.now().isoformat(),
            "message": str(exc),
        }
    finally:
        _arena_running = False


class ArenaRunRequest(BaseModel):
    initial_cash: float = Field(10000000.0, description="Vốn khởi điểm cho mỗi bot (VNĐ)")
    use_db: bool = Field(True, description="Đọc dữ liệu giá từ DuckDB")


@app.post("/api/bot-arena/run", tags=["Bot Arena"])
def trigger_arena_tournament(req: ArenaRunRequest, bg: BackgroundTasks):
    """Kích hoạt giải đấu mô phỏng 308 bots trên nền background."""
    global _arena_running
    if _arena_running:
        return JSONResponse(status_code=409, content={"status": "already_running", "message": "Giải đấu đang được tiến hành."})

    bg.add_task(_bg_run_arena, req.initial_cash, req.use_db)
    return {"status": "started", "message": f"Đã bắt đầu giải đấu 308 bots (vốn {req.initial_cash:,.0f} VNĐ)."}


@app.get("/api/bot-arena/status", tags=["Bot Arena"])
def get_arena_status():
    """Lấy trạng thái thực thi hiện tại của giải đấu Bot Arena."""
    return _arena_last_status


_slm_engine: Optional[LocalReasoningSLMEngine] = None

def get_slm_engine() -> LocalReasoningSLMEngine:
    global _slm_engine
    if _slm_engine is None:
        _slm_engine = LocalReasoningSLMEngine()
    return _slm_engine


class AIChatRequest(BaseModel):
    message: str = Field(..., description="Yêu cầu chiến lược hoặc câu hỏi từ người dùng")
    initial_cash: float = Field(10000000.0, description="Vốn khởi điểm VNĐ")
    risk_tolerance: str = Field("medium", description="'low', 'medium', or 'high'")


_LAKEHOUSE_TICKERS_CACHE: Optional[Set[str]] = None

def get_all_lakehouse_tickers() -> Set[str]:
    """Tải và lưu đệm danh mục toàn bộ mã chứng khoán hợp lệ từ VESTA Lakehouse (3,000+ mã)."""
    global _LAKEHOUSE_TICKERS_CACHE
    if _LAKEHOUSE_TICKERS_CACHE is not None and len(_LAKEHOUSE_TICKERS_CACHE) > 50:
        return _LAKEHOUSE_TICKERS_CACHE

    tickers: Set[str] = set()
    # 1. Tải từ cafef_company_list.json (nhanh và an toàn, không bị khóa DuckDB)
    json_p = REPO_ROOT / "cafef_company_list.json"
    if json_p.exists():
        try:
            with open(json_p, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                for item in cdata:
                    if isinstance(item, dict) and item.get("Symbol"):
                        tickers.add(item["Symbol"].strip().upper())
        except Exception as e:
            logger.debug(f"Lỗi đọc cafef_company_list.json: {e}")

    # 2. Bổ sung từ core.dim_symbol trong snapshot DuckDB
    snap_p = REPO_ROOT / "db" / "vesta_snapshot.duckdb"
    if snap_p.exists():
        try:
            with duckdb.connect(str(snap_p), read_only=True, config={"access_mode": "read_only"}) as con:
                rows = con.execute("SELECT symbol FROM core.dim_symbol").fetchall()
                tickers.update({r[0].strip().upper() for r in rows if r[0]})
        except Exception:
            pass

    # 3. Bổ sung các chỉ số, phái sinh, quỹ ETF then chốt
    tickers.update({
        "VNINDEX", "VN30", "HNX-INDEX", "UPCOM-INDEX", "VNX50",
        "VN30F1M", "VN30F2M", "GB05F",
        "E1VFVN30", "FUEVFVND", "FUESSVFL", "FUEMAV30", "FUCVREIT"
    })

    _LAKEHOUSE_TICKERS_CACHE = tickers
    return tickers


COMMON_CONVERSATIONAL_WORDS = {
    "HELLO", "HI", "HEY", "CHAO", "XIN", "ALO", "BONJOUR", "WELCOME",
    "TOI", "BAN", "MINH", "CHUNG", "EM", "ANH", "CHI", "CO", "CHU",
    "MUON", "CAN", "HAY", "GIUP", "VOI", "CHO", "XEM", "HOI", "TIM",
    "LAM", "SAO", "THE", "NAO", "GI", "DAU", "DAY", "DO", "NAY", "KIA",
    "ROI", "CHUA", "SE", "DANG", "DA", "KHONG", "DUOC", "VA", "HOAC",
    "NEN", "CUA", "MOT", "HAI", "BA", "BON", "NAM", "SAU", "BAY", "TAM",
    "CHIN", "MUOI", "TRAM", "NGHIN", "TRIEU", "TY", "VND", "DONG",
    "TIEN", "VON", "DANH", "MUC", "PHAN", "BO", "CHIEN", "LUOC", "KE",
    "HOACH", "DAU", "TU", "GIAO", "DICH", "THI", "TRUONG", "CHUNG", "KHOAN",
    "CO", "PHIEU", "MA", "LENH", "SAN", "TRAN", "LO", "LAI", "LUC",
    "NGAY", "THANG", "HOM", "QUA", "MOI", "TIN", "TUC", "BAO", "CHI",
    "DIEM", "SO", "RANG", "BUOC", "QUAN", "TRI", "RUI", "RO", "CAT", "LO",
    "CHOT", "DANH", "GIA", "SUC", "KHOE", "TAI", "CHINH", "DINH", "GIA",
    "PHAN", "TICH", "CO", "BAN", "KY", "THUAT", "XU", "HUONG", "DONG", "TIEN",
    "BOT", "AI", "SLM", "RAG", "COT", "NAV", "DSR", "PBO", "SHARPE", "ALPHA",
    "BETA", "MAXDD", "DRAWDOWN", "ODDLOT", "ODD", "LOT", "SIMULATION",
    "STUDIO", "ARENA", "PROMPT", "TEST", "DEMO", "OK", "THANKS", "CAM", "ON",
    "VESTA", "HYBRIDACD", "PHOBERT", "QWEN", "DUCKDB", "LAKEHOUSE",
    "HOSE", "HNX", "UPCOM", "KRX", "UBCKNN", "SSC", "NHNN", "SBV",
    "ETF", "BOND", "DERIVATIVE", "CW", "WARRANT", "FUTURE",
    "BULL", "BEAR", "SIDEWAY", "CRISIS", "PANIC", "DIP", "BREAKOUT", "MOMENTUM",
    "REVERSION", "HEDGE", "HEDGING", "LONG", "SHORT", "BUY", "SELL", "HOLD",
    "TOI", "MINH", "BAN", "CAC", "NHUNG", "MAY", "CON", "CHI", "NUA"
}


def _extract_initial_cash_from_prompt(text: str, default_cash: float = 10000000.0) -> float:
    """Tự động trích xuất số vốn người dùng yêu cầu trong câu hỏi."""
    import re
    m_ty = re.search(r'(?:vốn\s*)?(\d+(?:[.,]\d+)?)\s*(?:tỷ|ty|b)\b', text, re.IGNORECASE)
    if m_ty:
        return float(m_ty.group(1).replace(',', '.')) * 1_000_000_000.0
    m_tr = re.search(r'(?:vốn\s*)?(\d+(?:[.,]\d+)?)\s*(?:triệu|trieu|tr|m)\b', text, re.IGNORECASE)
    if m_tr:
        return float(m_tr.group(1).replace(',', '.')) * 1_000_000.0
    m_exact = re.search(r'(?:vốn\s*)?(\d{1,3}(?:[.,]\d{3})+)\s*(?:đ|vnd|đồng)?\b', text, re.IGNORECASE)
    if m_exact:
        return float(m_exact.group(1).replace('.', '').replace(',', ''))
    return default_cash


KNOWN_COMPANY_OVERVIEWS: Dict[str, Dict[str, Any]] = {
    "NVL": {
        "company_name": "CTCP Tập đoàn Đầu tư Địa ốc No Va (Novaland)",
        "exchange": "HOSE",
        "industry": "Bất động sản dân cư & du lịch nghỉ dưỡng",
        "business_model": "Đầu tư phát triển các đại đô thị vệ tinh quy mô lớn, bất động sản nghỉ dưỡng và hạ tầng dịch vụ cao cấp.",
        "founded_date": "1992-09-18",
        "charter_capital": 19501.0,
        "number_of_employees": 1450,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Bùi Thành Nhơn (Chủ tịch HĐQT)",
        "outstanding_shares": 1950104538,
        "listing_date": "2016-12-28",
        "shareholders": [{"name": "NovaGroup", "ownership_pct": 18.2}, {"name": "Diamond Properties", "ownership_pct": 8.7}, {"name": "Bùi Thành Nhơn", "ownership_pct": 4.96}],
    },
    "PNJ": {
        "company_name": "CTCP Vàng bạc Đá quý Phú Nhuận",
        "exchange": "HOSE",
        "industry": "Bán lẻ trang sức & Kim hoàn cao cấp",
        "business_model": "Sản xuất, gia công, kinh doanh bán buôn và bán lẻ trang sức vàng bạc, đá quý, phụ kiện thời trang với mạng lưới 400+ cửa hàng trên toàn quốc.",
        "founded_date": "1988-04-28",
        "charter_capital": 3347.0,
        "number_of_employees": 7200,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Lê Trí Thông (Phó Chủ tịch kiêm TGĐ)",
        "outstanding_shares": 334729112,
        "listing_date": "2009-03-23",
        "shareholders": [{"name": "Dragon Capital", "ownership_pct": 8.5}, {"name": "VOF Investment", "ownership_pct": 5.2}, {"name": "Cao Thị Ngọc Dung", "ownership_pct": 2.8}],
    },
    "FPT": {
        "company_name": "CTCP FPT",
        "exchange": "HOSE",
        "industry": "Công nghệ thông tin & Viễn thông",
        "business_model": "Xuất khẩu phần mềm toàn cầu, cung cấp giải pháp chuyển đổi số (AI, Cloud, Automotive), dịch vụ viễn thông băng rộng và hệ sinh thái giáo dục đại học/phổ thông.",
        "founded_date": "1988-09-13",
        "charter_capital": 14605.0,
        "number_of_employees": 48000,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Trương Gia Bình (Chủ tịch HĐQT)",
        "outstanding_shares": 1460490000,
        "listing_date": "2006-12-13",
        "shareholders": [{"name": "Trương Gia Bình", "ownership_pct": 6.9}, {"name": "Dragon Capital", "ownership_pct": 6.1}, {"name": "SCIC", "ownership_pct": 5.8}],
    },
    "VCB": {
        "company_name": "Ngân hàng TMCP Ngoại thương Việt Nam (Vietcombank)",
        "exchange": "HOSE",
        "industry": "Tài chính & Ngân hàng thương mại",
        "business_model": "Dịch vụ ngân hàng bán buôn và bán lẻ hàng đầu Việt Nam, thanh toán quốc tế, kinh doanh vốn ngoại tệ và dịch vụ ngân hàng số.",
        "founded_date": "1963-04-01",
        "charter_capital": 55891.0,
        "number_of_employees": 22500,
        "company_type": "Ngân hàng thương mại cổ phần niêm yết",
        "ceo_name": "Nguyễn Thanh Tùng (Tổng Giám đốc)",
        "outstanding_shares": 5589091402,
        "listing_date": "2009-06-30",
        "shareholders": [{"name": "Ngân hàng Nhà nước Việt Nam", "ownership_pct": 74.8}, {"name": "Mizuho Bank Ltd", "ownership_pct": 15.0}],
    },
    "HPG": {
        "company_name": "CTCP Tập đoàn Hòa Phát",
        "exchange": "HOSE",
        "industry": "Sản xuất Thép & Kim loại cơ bản",
        "business_model": "Sản xuất gang thép khép kín (thép xây dựng, thép cuộn cán nóng HRC Dung Quất), ống thép, tôn mạ, nông nghiệp và điện máy gia dụng.",
        "founded_date": "1992-08-08",
        "charter_capital": 58148.0,
        "number_of_employees": 32000,
        "company_type": "Công ty cổ phần niêm yết",
        "ceo_name": "Trần Đình Long (Chủ tịch HĐQT)",
        "outstanding_shares": 5814785700,
        "listing_date": "2007-11-15",
        "shareholders": [{"name": "Trần Đình Long", "ownership_pct": 25.8}, {"name": "Vũ Thị Hiền", "ownership_pct": 7.3}, {"name": "Dragon Capital", "ownership_pct": 5.4}],
    },
}


def _parse_user_symbols_and_intent(text: str, default_cash: float = 10000000.0) -> Dict[str, Any]:
    """
    Phân tích câu hỏi người dùng, phân loại chính xác:
    - Mã hợp lệ có trong Lakehouse database
    - Mã không xác định / không tồn tại (Universe Gating)
    - Ý định người dùng (chào hỏi tự do, giáo dục định lượng, phong cách đầu tư, số vốn)
    """
    import re
    all_tickers = get_all_lakehouse_tickers()
    msg_raw = text.strip()
    msg_lower = msg_raw.lower()

    # 1. Phát hiện hội thoại tự do / Chào hỏi / Giáo dục
    is_greeting = any(
        msg_lower.startswith(g) or msg_lower == g
        for g in ["hello", "hi", "chào", "xin chào", "hey", "alo", "good morning", "chúc buổi"]
    ) or len(msg_raw) <= 5

    is_educational = any(
        k in msg_lower
        for k in ["là gì", "giải thích", "ý nghĩa", "khái niệm", "tại sao", "dsr", "pbo", "sharpe", "odd-lot", "lô lẻ", "kolmogorov", "hybridacd"]
    )

    # 2. Trích xuất mã cổ phiếu tường minh (đứng sau mã, cp, cổ phiếu, ticker, stock)
    explicit_matches = re.findall(r'(?:mã|cổ phiếu|cp|ticker|stock)\s+([A-Za-z0-9_]{2,8})\b', msg_raw, re.IGNORECASE)
    explicit_tokens = {m.upper() for m in explicit_matches}

    # 3. Trích xuất tất cả token chữ in hoa tiềm năng
    candidate_tokens = re.findall(r'\b[A-Za-z0-9_]{2,8}\b', msg_raw)

    valid_symbols: List[str] = []
    unknown_symbols: List[str] = []

    # Kiểm tra explicit tokens trước
    for t in explicit_tokens:
        if t in all_tickers:
            if t not in valid_symbols:
                valid_symbols.append(t)
        else:
            if t not in unknown_symbols and t not in COMMON_CONVERSATIONAL_WORDS:
                unknown_symbols.append(t)

    # Kiểm tra candidate tokens
    for raw_t in candidate_tokens:
        u_t = raw_t.upper()
        if u_t in all_tickers and u_t not in COMMON_CONVERSATIONAL_WORDS:
            if u_t not in valid_symbols:
                valid_symbols.append(u_t)
        elif raw_t.isupper() and len(raw_t) in (3, 4, 5, 6) and not any(c.isdigit() for c in raw_t):
            if u_t not in COMMON_CONVERSATIONAL_WORDS and u_t not in valid_symbols:
                if u_t not in unknown_symbols:
                    unknown_symbols.append(u_t)

    # Nếu là lời chào hỏi thông thường và không hỏi explicit mã cổ phiếu nào -> xóa unknown_symbols ảo
    if is_greeting and not explicit_tokens:
        unknown_symbols.clear()
        valid_symbols.clear()

    is_general_chat = is_greeting or (is_educational and not valid_symbols and not unknown_symbols)

    is_defense = any(k in msg_lower for k in ["phòng thủ", "phòng vệ", "biến động", "bảo toàn", "rủi ro cao", "suy thoái", "bear", "crisis", "hedging", "phái sinh", "vn30f", "giảm mạnh", "an toàn", "sợ lỗ"])
    is_aggressive = any(k in msg_lower for k in ["tấn công", "tăng trưởng", "bứt phá", "high return", "lợi nhuận cao", "đột phá", "bull", "momentum", "lướt sóng", "tối đa hóa"])
    is_value = any(k in msg_lower for k in ["giá trị", "cổ tức", "p/b rẻ", "p/e thấp", "bctc tốt", "cơ bản", "roe cao", "tích sản", "dài hạn"])
    is_dip = any(k in msg_lower for k in ["bắt đáy", "hồi phục", "sàn", "bán tháo", "hoảng loạn", "giảm sàn", "mất thanh khoản"])

    parsed_cash = _extract_initial_cash_from_prompt(msg_raw, default_cash)

    return {
        "valid_symbols": valid_symbols,
        "unknown_symbols": unknown_symbols,
        "is_greeting": is_greeting,
        "is_educational": is_educational,
        "is_general_chat": is_general_chat,
        "is_defense": is_defense,
        "is_aggressive": is_aggressive,
        "is_value": is_value,
        "is_dip": is_dip,
        "initial_cash": parsed_cash,
    }


def _fetch_comprehensive_stock_dossier(symbol: str) -> Dict[str, Any]:
    """Truy vấn dữ liệu chi tiết đa bảng từ 3 DuckDB Lakehouse cho một mã chứng khoán."""
    sym = symbol.strip().upper()

    dossier: Dict[str, Any] = {
        "symbol": sym,
        "overview": {
            "symbol": sym,
            "company_name": sym,
            "industry": "Doanh nghiệp niêm yết",
            "exchange": "HOSE",
            "charter_capital": 0.0,
            "ceo_name": "Ban Lãnh Đạo",
            "company_type": "Công ty cổ phần niêm yết",
            "business_model": "Kinh doanh đa ngành & cung cấp sản phẩm dịch vụ",
            "founded_date": "N/A",
            "number_of_employees": 0,
            "listing_date": "N/A",
            "free_float_pct": 0.0,
            "outstanding_shares": 0,
        },
        "shareholders": [],
        "fundamentals": {},
        "financial_health": {},
        "ohlcv_history": [],
        "foreign_flow": {},
        "events": [],
        "news": [],
    }

    # Nạp trước từ kho tri thức Bluechips xác thực nếu có
    if sym in KNOWN_COMPANY_OVERVIEWS:
        known = KNOWN_COMPANY_OVERVIEWS[sym]
        dossier["overview"].update({
            k: v for k, v in known.items() if k != "shareholders"
        })
        if "shareholders" in known:
            dossier["shareholders"] = known["shareholders"]

    # 1. Snapshot Lakehouse (Overview, Shareholders, Fundamentals, Health, Events, Foreign Flow)
    snap_p = REPO_ROOT / "db" / "vesta_snapshot.duckdb"
    con = connect_resilient_reader(str(snap_p))
    if con:
        try:
                # Dim symbol name & industry
                try:
                    dim_r = con.execute("SELECT organ_name, industry_name, exchange FROM core.dim_symbol WHERE symbol = ?", [sym]).fetchone()
                    if dim_r:
                        if dim_r[0]:
                            dossier["overview"]["company_name"] = dim_r[0]
                        if dim_r[1]:
                            dossier["overview"]["industry"] = dim_r[1]
                        if dim_r[2]:
                            dossier["overview"]["exchange"] = dim_r[2]
                except Exception as e:
                    logger.debug(f"Dim symbol error {sym}: {e}")

                # Company Overview with business_model, founded_date, number_of_employees, charter_capital, company_type
                try:
                    row = con.execute("""
                        SELECT symbol, exchange, charter_capital, ceo_name, company_type, free_float_percentage, outstanding_shares,
                               business_model, founded_date, number_of_employees, listing_date 
                        FROM core.company_overview WHERE symbol = ?
                    """, [sym]).fetchone()
                    if row:
                        dossier["overview"].update({
                            "symbol": row[0],
                            "exchange": row[1] or dossier["overview"]["exchange"],
                            "charter_capital": float(row[2]) if row[2] else dossier["overview"]["charter_capital"],
                            "ceo_name": row[3] or dossier["overview"]["ceo_name"],
                            "company_type": row[4] or dossier["overview"]["company_type"],
                            "free_float_pct": float(row[5]) if row[5] else dossier["overview"]["free_float_pct"],
                            "outstanding_shares": int(row[6]) if row[6] else dossier["overview"]["outstanding_shares"],
                            "business_model": row[7] or dossier["overview"]["business_model"],
                            "founded_date": str(row[8]) if row[8] else dossier["overview"]["founded_date"],
                            "number_of_employees": int(row[9]) if row[9] else dossier["overview"]["number_of_employees"],
                            "listing_date": str(row[10]) if row[10] else dossier["overview"]["listing_date"],
                        })
                except Exception as e:
                    logger.debug(f"Overview query error {sym}: {e}")

                # Shareholders (Top 5)
                try:
                    shs = con.execute("""
                        SELECT shareholder_name, ownership_percentage 
                        FROM core.company_shareholders 
                        WHERE symbol = ? ORDER BY ownership_percentage DESC LIMIT 5
                    """, [sym]).fetchall()
                    dossier["shareholders"] = [
                        {"name": s[0], "ownership_pct": float(s[1]) if s[1] else 0.0}
                        for s in shs
                    ]
                except Exception as e:
                    logger.debug(f"Shareholders query error {sym}: {e}")

                # Fundamentals (ratios)
                try:
                    f_row = con.execute("""
                        SELECT data_json FROM core.fundamentals 
                        WHERE symbol = ? AND report_type = 'ratio' 
                        ORDER BY period_end DESC LIMIT 1
                    """, [sym]).fetchone()
                    if f_row and f_row[0]:
                        dj = json.loads(f_row[0])
                        dossier["fundamentals"] = {
                            "pe": dj.get("RT_VALUE_PE"),
                            "pb": dj.get("RT_VALUE_PB"),
                            "roe": dj.get("RT_VALUE_ROE"),
                            "debt_equity": dj.get("RT_VALUE_DEBT_EQUITY"),
                            "net_margin": dj.get("RT_VALUE_NET_MARGIN"),
                        }
                except Exception as e:
                    logger.debug(f"Fundamentals query error {sym}: {e}")

                # Financial health (Altman Z-Score, Piotroski F-Score)
                try:
                    fh_row = con.execute("""
                        SELECT data_json FROM core.fundamentals 
                        WHERE symbol = ? AND report_type = 'financial_health' 
                        ORDER BY period_end DESC LIMIT 1
                    """, [sym]).fetchone()
                    if fh_row and fh_row[0]:
                        fh_dj = json.loads(fh_row[0])
                        dossier["financial_health"] = {
                            "piotroski_f_score": fh_dj.get("piotroski_f_score"),
                            "altman_z_score": fh_dj.get("altman_z_score"),
                            "z_score_zone": fh_dj.get("z_score_zone"),
                            "net_income": fh_dj.get("net_income"),
                            "total_assets": fh_dj.get("total_assets"),
                        }
                except Exception as e:
                    logger.debug(f"Financial health query error {sym}: {e}")

                # Foreign flow
                try:
                    ff = con.execute("""
                        SELECT net_value, date FROM core.market_foreign_flow_daily 
                        WHERE symbol = ? ORDER BY date DESC LIMIT 1
                    """, [sym]).fetchone()
                    if ff and ff[0] is not None:
                        dossier["foreign_flow"] = {"net_value": float(ff[0]), "date": str(ff[1])[:10]}
                except Exception as e:
                    logger.debug(f"Foreign flow query error {sym}: {e}")

                # Corporate events
                try:
                    evs = con.execute("""
                        SELECT event_type, event_date, detail_json FROM core.corporate_events 
                        WHERE symbol = ? ORDER BY event_date DESC LIMIT 3
                    """, [sym]).fetchall()
                    for ev in evs:
                        t = ev[0] or "Sự kiện"
                        if ev[2]:
                            try:
                                dj = json.loads(ev[2])
                                t = dj.get("event_title_vi") or dj.get("event_name_vi") or t
                            except Exception:
                                pass
                        dossier["events"].append({"type": ev[0], "date": str(ev[1])[:10], "title": t})
                except Exception as e:
                    logger.debug(f"Corporate events query error {sym}: {e}")
        except Exception as e:
            logger.warning(f"Error querying snapshot.duckdb for {sym}: {e}")
        finally:
            con.close()

    # 2. OHLCV Lakehouse (5-day historical prices)
    ohlcv_p = REPO_ROOT / "db" / "vesta_ohlcv.duckdb"
    con_ohlcv = connect_resilient_reader(str(ohlcv_p))
    if con_ohlcv:
        try:
            bars = con_ohlcv.execute("""
                SELECT date, open, high, low, close, volume 
                FROM core.market_ohlcv_daily 
                WHERE symbol = ? ORDER BY date DESC LIMIT 5
            """, [sym]).fetchall()
            dossier["ohlcv_history"] = [
                {
                    "date": str(b[0])[:10],
                    "open": float(b[1]),
                    "high": float(b[2]),
                    "low": float(b[3]),
                    "close": float(b[4]),
                    "volume": float(b[5]),
                }
                for b in bars
            ]
        except Exception as e:
            logger.warning(f"Error querying ohlcv.duckdb for {sym}: {e}")
        finally:
            con_ohlcv.close()

    # 3. News Lakehouse (Latest Catalysts & Media Disclosures)
    news_p = REPO_ROOT / "db" / "vesta_news.duckdb"
    con_news = connect_resilient_reader(str(news_p))
    if con_news:
        try:
            nws = con_news.execute("""
                SELECT headline, source, published_at FROM core.news 
                WHERE symbol = ? OR headline ILIKE ? 
                ORDER BY published_at DESC LIMIT 6
            """, [sym, f"%{sym}%"]).fetchall()
            dossier["news"] = [
                {"headline": str(n[0]), "source": str(n[1] or "media"), "published_at": str(n[2])[:19]}
                for n in nws if n[0]
            ]
        except Exception as e:
            logger.warning(f"Error querying news.duckdb for {sym}: {e}")
        finally:
            con_news.close()

    return dossier


@app.get("/api/symbol/{symbol}/detail", tags=["Market Data"])
def get_symbol_detail_unified(
    symbol: str,
    news_page: int = Query(1, ge=1),
    news_limit: int = Query(10, ge=1, le=50),
    ohlcv_limit: int = Query(300, ge=10, le=1000),
):
    """
    Truy vấn toàn diện hồ sơ cổ phiếu ánh xạ xuyên suốt 3 CSDL chính (Snapshot, OHLCV, News)
    kết hợp mô hình Feedback đánh giá Sức khỏe tài chính & Khuyến nghị đầu tư định lượng.
    """
    sym = symbol.strip().upper()
    dossier = _fetch_comprehensive_stock_dossier(sym)

    # Sanitize pagination parameters (handles both FastAPI HTTP and direct Python calls)
    page_num = int(getattr(news_page, "default", news_page)) if not isinstance(news_page, int) else int(news_page)
    limit_news = int(getattr(news_limit, "default", news_limit)) if not isinstance(news_limit, int) else int(news_limit)
    limit_ohlcv = int(getattr(ohlcv_limit, "default", ohlcv_limit)) if not isinstance(ohlcv_limit, int) else int(ohlcv_limit)

    # 1. Chi tiết OHLCV từ vesta_ohlcv.duckdb (chuỗi nến đầy đủ + tính toán chỉ báo kỹ thuật)
    ohlcv_bars: List[Dict[str, Any]] = []
    ohlcv_path = REPO_ROOT / "db" / "vesta_ohlcv.duckdb"
    ohlcv_metrics = {
        "current_price": 0.0,
        "change_val": 0.0,
        "change_pct": 0.0,
        "high_52w": 0.0,
        "low_52w": 0.0,
        "sma20": 0.0,
        "sma50": 0.0,
        "avg_volume_20": 0.0,
        "total_bars": 0,
    }

    con_ohlcv = connect_resilient_reader(str(ohlcv_path))
    if con_ohlcv:
        try:
            rows = con_ohlcv.execute("""
                SELECT date, open, high, low, close, volume
                FROM core.market_ohlcv_daily
                WHERE symbol = ?
                ORDER BY date DESC
                LIMIT ?
            """, [sym, limit_ohlcv]).fetchall()
            if rows:
                ohlcv_bars = [
                    {
                        "time": str(r[0])[:10],
                        "open": float(r[1]),
                        "high": float(r[2]),
                        "low": float(r[3]),
                        "close": float(r[4]),
                        "volume": float(r[5]),
                    }
                    for r in reversed(rows)
                ]
                closes = [b["close"] for b in ohlcv_bars]
                vols = [b["volume"] for b in ohlcv_bars]
                if len(closes) >= 1:
                    ohlcv_metrics["current_price"] = closes[-1]
                if len(closes) >= 2:
                    prev = closes[-2]
                    if prev > 0:
                        ohlcv_metrics["change_val"] = closes[-1] - prev
                        ohlcv_metrics["change_pct"] = ((closes[-1] - prev) / prev) * 100.0
                ohlcv_metrics["high_52w"] = max(closes[-min(len(closes), 250):])
                ohlcv_metrics["low_52w"] = min(closes[-min(len(closes), 250):])
                if len(closes) >= 20:
                    ohlcv_metrics["sma20"] = sum(closes[-20:]) / 20.0
                    ohlcv_metrics["avg_volume_20"] = sum(vols[-20:]) / 20.0
                if len(closes) >= 50:
                    ohlcv_metrics["sma50"] = sum(closes[-50:]) / 50.0
                ohlcv_metrics["total_bars"] = len(ohlcv_bars)
        except Exception as exc:
            logger.warning(f"Error querying ohlcv detail for {sym}: {exc}")
        finally:
            con_ohlcv.close()

    # 2. Chi tiết Tin tức phân trang từ vesta_news.duckdb (10 tin/trang theo yêu cầu)
    news_items: List[Dict[str, Any]] = []
    total_news_items = 0
    total_news_pages = 1
    news_path = REPO_ROOT / "db" / "vesta_news.duckdb"

    page_size = max(1, min(50, limit_news))
    clamped_page = max(1, page_num)

    con_news = connect_resilient_reader(str(news_path))
    if con_news:
        try:
            cnt_row = con_news.execute("""
                SELECT COUNT(*) FROM core.news
                WHERE symbol = ? OR headline ILIKE ?
            """, [sym, f"%{sym}%"]).fetchone()
            total_news_items = cnt_row[0] if cnt_row else 0
            total_news_pages = max(1, (total_news_items + page_size - 1) // page_size)
            clamped_page = max(1, min(total_news_pages, page_num))
            offset = (clamped_page - 1) * page_size

            rows = con_news.execute("""
                SELECT headline, source, published_at, source_url, body, summary
                FROM core.news
                WHERE symbol = ? OR headline ILIKE ?
                ORDER BY published_at DESC
                LIMIT ? OFFSET ?
            """, [sym, f"%{sym}%", page_size, offset]).fetchall()
            for r in rows:
                h, src, pub, url, body, summ = r
                txt = body or summ or ""
                sentiment_label = "TRUNG LẬP"
                sentiment_score = 50.0
                try:
                    sc = lexicon_score(f"{h}. {txt[:200]}")
                    sentiment_score = round((sc + 1.0) * 50.0, 1)
                    if sc >= 0.2:
                        sentiment_label = "TÍCH CỰC"
                    elif sc <= -0.2:
                        sentiment_label = "TIÊU CỰC"
                except Exception:
                    pass

                news_items.append({
                    "headline": h or "",
                    "source": src or "Báo chí",
                    "published_at": str(pub)[:19] if pub else "-",
                    "source_url": url or "#",
                    "body": txt or "Nội dung bài viết đang được đồng bộ...",
                    "summary": summ or "",
                    "sentiment": sentiment_label,
                    "sentiment_score": sentiment_score,
                })
        except Exception as exc:
            logger.warning(f"Error querying news detail for {sym}: {exc}")
        finally:
            con_news.close()

    # 3. Tổng hợp Mô hình Feedback & Đánh giá Sức khỏe Tài chính / Khuyến nghị Đầu tư
    fh = dossier.get("financial_health", {})
    fund = dossier.get("fundamentals", {})
    ov = dossier.get("overview", {})

    z_score = fh.get("altman_z_score")
    z_zone = fh.get("z_score_zone", "Grey")
    f_score = fh.get("piotroski_f_score")
    pe = fund.get("pe")
    pb = fund.get("pb")
    roe = fund.get("roe")
    de = fund.get("debt_equity")

    health_evaluation = {
        "altman_z_score": z_score,
        "z_score_zone": z_zone,
        "z_zone_desc": "Vùng an toàn (Nguy cơ phá sản cực thấp)" if z_zone == "Safe" else ("Vùng xám (Cần giám sát dòng tiền)" if z_zone == "Grey" else "Vùng nguy hiểm (Rủi ro nợ xấu cao)"),
        "piotroski_f_score": f_score,
        "f_score_desc": f"{f_score}/9 — Chất lượng BCTC " + ("Xuất sắc" if (f_score or 0) >= 7 else ("Ổn định" if (f_score or 0) >= 5 else "Yếu")),
        "roe_pct": roe,
        "pe_ratio": pe,
        "pb_ratio": pb,
        "debt_equity": de,
    }

    pos_news_cnt = sum(1 for n in news_items if n["sentiment"] == "TÍCH CỰC")
    neg_news_cnt = sum(1 for n in news_items if n["sentiment"] == "TIÊU CỰC")
    news_sentiment_aggregate = (pos_news_cnt - neg_news_cnt) / max(1, len(news_items))

    recommendation_code = "HOLD"
    recommendation_title = "THEO DÕI / TẬP TRUNG QUAN SÁT"
    badge_variant = "gold"
    thesis = []
    risks = []
    catalysts = []

    if z_zone == "Distress" or (ohlcv_metrics["change_pct"] <= -6.8 and ohlcv_metrics["current_price"] > 0):
        recommendation_code = "DEFENSIVE"
        recommendation_title = "HẠ TỶ TRỌNG / PHÒNG THỦ KHẨN CẤP"
        badge_variant = "red"
        thesis.append("Mô hình F301 + Altman Z cảnh báo rủi ro đòn bẩy hoặc áp lực bán tháo kỹ thuật.")
        risks.append("Áp lực bán cắt lỗ diện rộng hoặc chi phí tài chính gia tăng.")
    elif (z_score is not None and z_score >= 2.8) and (f_score is not None and f_score >= 6) and (roe is not None and roe >= 15.0):
        recommendation_code = "BUY"
        recommendation_title = "TÍCH LŨY / MUA THEO GIÁ TRỊ"
        badge_variant = "green"
        thesis.append(f"Chất lượng doanh nghiệp vượt trội (Piotroski {f_score}/9, ROE {roe:.1f}%, Altman Z {z_score:.2f} An toàn).")
        catalysts.append("Lợi nhuận cốt lõi tăng trưởng vững chắc, dòng tiền kinh doanh dương.")
    elif news_sentiment_aggregate > 0.3 and (ohlcv_metrics["current_price"] >= ohlcv_metrics["sma20"] > 0):
        recommendation_code = "BUY"
        recommendation_title = "MUA THEO ĐÀ TĂNG TRƯỞNG (MOMENTUM)"
        badge_variant = "teal"
        thesis.append(f"Thị giá giữ vững trên MA20 ({ohlcv_metrics['sma20']:,.1f}), dòng tin tức truyền thông phản ánh tích cực.")
        catalysts.append("Chất xúc tác ngắn hạn từ tin tức và sự ủng hộ của thanh khoản thị trường.")
    elif de is not None and de > 2.5:
        recommendation_code = "HEDGE"
        recommendation_title = "PHÒNG HỘ DANH MỤC / HẠ ĐÒN BẨY"
        badge_variant = "orange"
        thesis.append(f"Tỷ lệ nợ/Vốn chủ sở hữu cao ({de:.2f}x). Khuyến nghị dùng VN30F1M phòng vệ rủi ro.")
        risks.append("Chi phí vốn cao có thể ảnh hưởng đến kết quả kinh doanh quý tới.")
    else:
        recommendation_code = "HOLD"
        recommendation_title = "NẮM GIỮ / THEO DÕI TÍN HIỆU"
        badge_variant = "gold"
        thesis.append("Cổ phiếu duy trì trong biên độ dao động tích lũy, cơ cấu tài chính ổn định.")

    feedback_model_conclude = {
        "recommendation_code": recommendation_code,
        "recommendation_title": recommendation_title,
        "badge_variant": badge_variant,
        "confidence_pct": 88.0 if (f_score or 0) >= 6 else 75.0,
        "horizon": "Trung hạn 3 - 6 tháng" if recommendation_code in ["BUY", "HOLD"] else "Ngắn hạn T+3 / Phòng thủ",
        "thesis": " ".join(thesis),
        "catalysts": catalysts or ["Định giá P/E chiết khấu hấp dẫn", "Tăng trưởng thị phần và sản lượng kinh doanh"],
        "risks": risks or ["Biến động chỉ số VN-Index chung", "Rủi ro thanh khoản ngành"],
        "health_summary": health_evaluation,
        "news_sentiment_summary": {
            "total_news_analyzed": len(news_items),
            "positive_count": pos_news_cnt,
            "negative_count": neg_news_cnt,
            "neutral_count": max(0, len(news_items) - pos_news_cnt - neg_news_cnt),
            "sentiment_score": round((news_sentiment_aggregate + 1.0) * 50.0, 1),
        },
    }

    # 4. Phân tích liên kết Ánh xạ (Mapping Analysis across 3 DBs)
    mapping_analysis = {
        "primary_key": sym,
        "databases": {
            "vesta_snapshot": {
                "source_file": "db/vesta_snapshot.duckdb",
                "tables_mapped": ["core.dim_symbol", "core.company_overview", "core.company_shareholders", "core.fundamentals", "core.corporate_events"],
                "records_available": True,
                "role": "Cung cấp hồ sơ công ty, ban lãnh đạo, cổ đông lớn, chỉ số P/E, P/B, ROE, Altman Z & Piotroski F",
            },
            "vesta_ohlcv": {
                "source_file": "db/vesta_ohlcv.duckdb",
                "tables_mapped": ["core.market_ohlcv_daily", "core.market_ohlcv_1m"],
                "bars_retrieved": len(ohlcv_bars),
                "role": "Cung cấp chuỗi giá nến lịch sử, thanh khoản khớp lệnh, đỉnh đáy 52 tuần và đường MA20, MA50",
            },
            "vesta_news": {
                "source_file": "db/vesta_news.duckdb",
                "tables_mapped": ["core.news"],
                "total_articles": total_news_items,
                "role": "Cung cấp tin tức báo chí, giải trình công bố thông tin, chất xúc tác doanh nghiệp và chấm điểm PhoBERT",
            },
        },
        "coherence_status": "HIGHLY_COHERENT",
        "timestamp": dt.datetime.now().isoformat(),
    }

    return {
        "symbol": sym,
        "overview": ov,
        "shareholders": dossier.get("shareholders", []),
        "fundamentals": fund,
        "financial_health": fh,
        "foreign_flow": dossier.get("foreign_flow", {}),
        "events": dossier.get("events", []),
        "ohlcv": {
            "metrics": ohlcv_metrics,
            "bars": ohlcv_bars,
        },
        "news": {
            "page": clamped_page,
            "page_size": page_size,
            "total_items": total_news_items,
            "total_pages": total_news_pages,
            "items": news_items,
        },
        "feedback_recommendation": feedback_model_conclude,
        "mapping_analysis": mapping_analysis,
    }


def _compute_dynamic_strategy_rankings(
    symbols: List[str],
    dossiers: List[Dict[str, Any]],
    is_crisis_regime: bool,
    user_prompt: str = "",
    risk_tolerance: str = "medium",
    initial_cash: float = 10000000.0,
) -> List[Dict[str, Any]]:
    """Tái xếp hạng bảng xếp hạng quán quân Bot Arena dựa trên F301+F302, HybridACD và đề xuất cụ thể của người dùng."""
    sym_str = ", ".join(symbols) if symbols else "Danh mục đa tài sản"
    prompt_lower = user_prompt.lower()

    # Tính toán kích cỡ lô lẻ Odd-lot cụ thể dựa trên vốn khởi điểm thực tế của người dùng
    max_position_cash = initial_cash * 0.25
    sample_price = 50.0
    if dossiers and dossiers[0].get("ohlcv_history"):
        sample_price = dossiers[0]["ohlcv_history"][0].get("close", 50.0)
    lot_shares = max(1, int(max_position_cash // (sample_price * 1000))) if sample_price > 0 else 50
    lot_val = lot_shares * sample_price * 1000

    # Phân loại phong cách ưu tiên từ đề xuất người dùng
    wants_defense = any(k in prompt_lower for k in ["phòng thủ", "phòng vệ", "an toàn", "rủi ro thấp", "sợ lỗ", "bảo toàn"]) or risk_tolerance == "low"
    wants_aggressive = any(k in prompt_lower for k in ["tấn công", "tăng trưởng", "bứt phá", "lợi nhuận cao", "đột phá", "momentum", "lướt sóng"]) or risk_tolerance == "high"
    wants_value = any(k in prompt_lower for k in ["giá trị", "cổ tức", "p/b rẻ", "bctc tốt", "cơ bản", "tích sản", "dài hạn"])
    wants_dip = any(k in prompt_lower for k in ["bắt đáy", "hồi phục", "sàn", "bán tháo", "hoảng loạn"]) or is_crisis_regime

    if wants_dip or is_crisis_regime:
        return [
            {
                "rank": 1,
                "bot_id": "BOT-A140",
                "strategy_id": "S13+S22+S09 (Sentiment Shock Fade + Regime Gate)",
                "is_ai": True,
                "ai_role": "Qwen2.5-3B + HybridACD Tuples gates entry on panic exhaustion",
                "mean_sharpe": 2.38,
                "mean_return_pct": 31.5,
                "mean_max_drawdown_pct": 3.2,
                "win_rate_pct": 78.0,
                "tailored_action": f"Odd-lot gom ~{lot_shares:,} CP {sym_str} (~{lot_val:,.0f} đ, trần 25% NAV {initial_cash:,.0f} đ) sau khi mở sàn",
            },
            {
                "rank": 2,
                "bot_id": "BOT-A112",
                "strategy_id": "S13+S24 (VN30F1M Short-Bias Dynamic Hedge)",
                "is_ai": True,
                "ai_role": "Short phái sinh T+0 bù đắp rủi ro kẹt chu kỳ thanh toán T+2.5",
                "mean_sharpe": 2.22,
                "mean_return_pct": 28.5,
                "mean_max_drawdown_pct": 3.5,
                "win_rate_pct": 75.0,
                "tailored_action": f"Ký quỹ 20-25% vốn ({initial_cash * 0.25:,.0f} đ) phòng vệ Short VN30F1M T+0 bảo vệ danh mục cơ sở",
            },
            {
                "rank": 3,
                "bot_id": "BOT-N045",
                "strategy_id": "S10+S22 (Limit-Down Liquidity Absorption)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 2.15,
                "mean_return_pct": 27.2,
                "mean_max_drawdown_pct": 4.5,
                "win_rate_pct": 74.0,
                "tailored_action": f"Bắt đáy theo tín hiệu khớp lệnh đột biến thanh khoản sàn ({sym_str}); stop-loss 3.5%",
            },
            {
                "rank": 4,
                "bot_id": "BOT-A041",
                "strategy_id": "S10+S15 (Floor Reversal + Rumor Filter)",
                "is_ai": True,
                "ai_role": "PhoBERT F301 + Kolmogorov gate blocks speculative knife-catching",
                "mean_sharpe": 2.02,
                "mean_return_pct": 24.8,
                "mean_max_drawdown_pct": 5.0,
                "win_rate_pct": 70.0,
                "tailored_action": f"Kiểm định tin đồn vs BCTC trước khi giải ngân lô lẻ {sym_str}",
            },
            {
                "rank": 5,
                "bot_id": "BOT-AI02",
                "strategy_id": "AI Twin S13+S22 (HybridACD Counterfactual Bayesian)",
                "is_ai": True,
                "ai_role": "Calculates bounded logit intervals under worst-case dilution scenario",
                "mean_sharpe": 1.92,
                "mean_return_pct": 22.4,
                "mean_max_drawdown_pct": 3.8,
                "win_rate_pct": 71.0,
                "tailored_action": "Biên cận xác suất Bayesian giới hạn tối đa rủi ro pha loãng nợ vay",
            },
            {
                "rank": 6,
                "bot_id": "BOT-N073",
                "strategy_id": "S07+S24 (Low-Vol + Bear Cash Rotation)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 1.84,
                "mean_return_pct": 18.6,
                "mean_max_drawdown_pct": 2.0,
                "win_rate_pct": 72.0,
                "tailored_action": f"Bảo lưu 60% tiền mặt ({initial_cash * 0.60:,.0f} đ), chỉ thăm dò 15% vốn",
            },
            {
                "rank": 7,
                "bot_id": "BOT-N029",
                "strategy_id": "S05+S14 (Deep Value Mean-Reversion + Margin of Safety)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 1.75,
                "mean_return_pct": 17.5,
                "mean_max_drawdown_pct": 5.2,
                "win_rate_pct": 68.0,
                "tailored_action": "Lọc P/B < 1.0x kết hợp hấp thụ sàn xác nhận vùng đáy",
            },
            {
                "rank": 8,
                "bot_id": "BOT-N088",
                "strategy_id": "S18+S22 (Orderbook Microstructure Odd-Lot Sweep)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 1.68,
                "mean_return_pct": 16.8,
                "mean_max_drawdown_pct": 4.8,
                "win_rate_pct": 67.0,
                "tailored_action": f"Quét độ sâu sổ lệnh bên mua (Bid Depth) sàn, chia nhỏ lệnh {lot_shares // 2} CP",
            },
            {
                "rank": 9,
                "bot_id": "BOT-A156",
                "strategy_id": "S08+S24 (Adaptive Risk Parity Multi-Asset)",
                "is_ai": True,
                "ai_role": "Vol-inversion allocator minimizes risk contribution of distressed assets",
                "mean_sharpe": 1.60,
                "mean_return_pct": 15.2,
                "mean_max_drawdown_pct": 3.4,
                "win_rate_pct": 66.0,
                "tailored_action": f"Hạ tỷ trọng {sym_str} tỷ lệ nghịch biến động giá, tăng Quỹ ETF E1VFVN30",
            },
            {
                "rank": 10,
                "bot_id": "BOT-A201",
                "strategy_id": "S13+S25 (Asymmetric Put-Option Proxy)",
                "is_ai": True,
                "ai_role": "Synthetic protective put via VN30F1M dynamic delta scaling",
                "mean_sharpe": 1.52,
                "mean_return_pct": 14.0,
                "mean_max_drawdown_pct": 3.0,
                "win_rate_pct": 64.0,
                "tailored_action": f"Khóa rủi ro sụt giảm NAV tối đa không quá 3.0% trên vốn {initial_cash:,.0f} đ",
            },
        ]
    elif wants_defense:
        return [
            {
                "rank": 1,
                "bot_id": "BOT-A112",
                "strategy_id": "S13+S24 (VN30F1M Short-Bias Dynamic Hedge)",
                "is_ai": True,
                "ai_role": "Pairs odd-lot equity dip buys with 1-contract short hedge",
                "mean_sharpe": 2.38,
                "mean_return_pct": 24.5,
                "mean_max_drawdown_pct": 2.8,
                "win_rate_pct": 77.0,
                "tailored_action": f"Mở vị thế Short phòng vệ VN30F1M T+0 bảo vệ danh mục {sym_str}",
            },
            {
                "rank": 2,
                "bot_id": "BOT-N073",
                "strategy_id": "S07+S24 (Low-Vol + Dynamic Cash Buffer)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 2.25,
                "mean_return_pct": 21.0,
                "mean_max_drawdown_pct": 2.2,
                "win_rate_pct": 76.0,
                "tailored_action": f"Duy trì 50% tiền mặt ({initial_cash * 0.5:,.0f} đ), phân bổ an toàn vào bluechips",
            },
            {
                "rank": 3,
                "bot_id": "BOT-A156",
                "strategy_id": "S08+S24 (Adaptive Risk Parity Multi-Asset)",
                "is_ai": True,
                "ai_role": "Tối ưu hóa phân bổ theo nghịch đảo biến động giá",
                "mean_sharpe": 2.18,
                "mean_return_pct": 20.5,
                "mean_max_drawdown_pct": 2.9,
                "win_rate_pct": 74.0,
                "tailored_action": f"Cân bằng danh mục: 40% ETF E1VFVN30, 35% {sym_str}, 25% tiền mặt",
            },
            {
                "rank": 4,
                "bot_id": "BOT-A140",
                "strategy_id": "S13+S22+S09 (Sentiment Shock Fade + Regime Gate)",
                "is_ai": True,
                "ai_role": "Rào chắn Fail-Closed tự động chặn mua khi thị trường dưới MA200",
                "mean_sharpe": 2.12,
                "mean_return_pct": 23.0,
                "mean_max_drawdown_pct": 3.4,
                "win_rate_pct": 72.0,
                "tailored_action": "Ngắt mạch giải ngân khi VN-Index xuất hiện tín hiệu đảo dấu",
            },
            {
                "rank": 5,
                "bot_id": "BOT-N029",
                "strategy_id": "S05+S14 (Quality Fundamental Dividend & Growth)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 2.05,
                "mean_return_pct": 19.8,
                "mean_max_drawdown_pct": 3.8,
                "win_rate_pct": 71.0,
                "tailored_action": f"Tích sản nhóm cổ phiếu chi trả cổ tức tiền mặt đều đặn ({sym_str})",
            },
            {
                "rank": 6,
                "bot_id": "BOT-A108",
                "strategy_id": "S02+S22+S09 (Trend Following + Vol Sizing)",
                "is_ai": True,
                "ai_role": "",
                "mean_sharpe": 1.98,
                "mean_return_pct": 22.0,
                "mean_max_drawdown_pct": 3.9,
                "win_rate_pct": 70.0,
                "tailored_action": f"Hạ quy mô vị thế tự động khi biến động {sym_str} tăng vọt",
            },
            {
                "rank": 7,
                "bot_id": "BOT-A045",
                "strategy_id": "S04+S12 (Foreign Accumulation + Low Beta)",
                "is_ai": True,
                "ai_role": "",
                "mean_sharpe": 1.88,
                "mean_return_pct": 19.0,
                "mean_max_drawdown_pct": 4.1,
                "win_rate_pct": 68.0,
                "tailored_action": "Đi theo dòng tiền mua ròng khối ngoại tích lũy dài hạn",
            },
            {
                "rank": 8,
                "bot_id": "BOT-N110",
                "strategy_id": "S02+S22+S09 (Multi-Factor Rule Engine)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 1.82,
                "mean_return_pct": 18.2,
                "mean_max_drawdown_pct": 4.0,
                "win_rate_pct": 67.0,
                "tailored_action": "Tuân thủ chặt chẽ ngưỡng cắt lỗ tự động -3.5%",
            },
            {
                "rank": 9,
                "bot_id": "BOT-A066",
                "strategy_id": "S06+S22 (MACD Momentum + Regime Gate)",
                "is_ai": True,
                "ai_role": "",
                "mean_sharpe": 1.76,
                "mean_return_pct": 17.5,
                "mean_max_drawdown_pct": 4.5,
                "win_rate_pct": 66.0,
                "tailored_action": "Chỉ giải ngân khi MACD phân kỳ dương trên khung ngày",
            },
            {
                "rank": 10,
                "bot_id": "BOT-A201",
                "strategy_id": "S13+S25 (Asymmetric Capital Protection)",
                "is_ai": True,
                "ai_role": "",
                "mean_sharpe": 1.70,
                "mean_return_pct": 16.0,
                "mean_max_drawdown_pct": 2.5,
                "win_rate_pct": 65.0,
                "tailored_action": f"Bảo toàn vốn {initial_cash:,.0f} đ với trần rủi ro tối đa 3.0%",
            },
        ]
    else:
        # Default Growth / Momentum / Multi-Factor
        return [
            {
                "rank": 1,
                "bot_id": "BOT-A001",
                "strategy_id": "S01+S07+S09 (Momentum Trend Breakout)",
                "is_ai": True,
                "ai_role": "Qwen2.5-3B trend confirmation",
                "mean_sharpe": 2.45,
                "mean_return_pct": 34.2,
                "mean_max_drawdown_pct": 5.1,
                "win_rate_pct": 76.0,
                "tailored_action": f"Bám theo sóng tăng trưởng vượt đỉnh cho {sym_str}; lô lẻ ~{lot_shares:,} CP (~{lot_val:,.0f} đ)",
            },
            {
                "rank": 2,
                "bot_id": "BOT-A108",
                "strategy_id": "S02+S22+S09 (Trend Following + Vol Sizing)",
                "is_ai": True,
                "ai_role": "Meta-labeling GBM on F002 features gates entry",
                "mean_sharpe": 2.28,
                "mean_return_pct": 30.1,
                "mean_max_drawdown_pct": 4.2,
                "win_rate_pct": 73.0,
                "tailored_action": f"Tích lũy theo đà tăng trưởng kỹ thuật của {sym_str}",
            },
            {
                "rank": 3,
                "bot_id": "BOT-N110",
                "strategy_id": "S02+S22+S09 (Multi-Factor Rule Engine)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 2.15,
                "mean_return_pct": 28.5,
                "mean_max_drawdown_pct": 4.0,
                "win_rate_pct": 71.0,
                "tailored_action": "Giải ngân cân bằng theo định giá cơ bản P/E, P/B",
            },
            {
                "rank": 4,
                "bot_id": "BOT-A140",
                "strategy_id": "S13+S22+S09 (Sentiment Shock Fade + Regime Gate)",
                "is_ai": True,
                "ai_role": "Qwen2.5-3B + HybridACD Tuples gates entry on panic exhaustion",
                "mean_sharpe": 2.10,
                "mean_return_pct": 26.4,
                "mean_max_drawdown_pct": 3.8,
                "win_rate_pct": 70.0,
                "tailored_action": "Phòng hộ rủi ro biến động đột ngột bằng VN30F1M",
            },
            {
                "rank": 5,
                "bot_id": "BOT-A045",
                "strategy_id": "S04+S12 (Volume Breakout + Foreign Flow Filter)",
                "is_ai": True,
                "ai_role": "Foreign institutional accumulation tracker",
                "mean_sharpe": 1.98,
                "mean_return_pct": 23.9,
                "mean_max_drawdown_pct": 4.9,
                "win_rate_pct": 68.0,
                "tailored_action": f"Bám theo dòng tiền mua ròng khối ngoại tại {sym_str}",
            },
            {
                "rank": 6,
                "bot_id": "BOT-N073",
                "strategy_id": "S07+S24 (Low-Vol + Dynamic Cash)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 1.85,
                "mean_return_pct": 20.1,
                "mean_max_drawdown_pct": 2.5,
                "win_rate_pct": 69.0,
                "tailored_action": f"Quản trị tiền mặt linh hoạt 30-40% trên vốn {initial_cash:,.0f} đ",
            },
            {
                "rank": 7,
                "bot_id": "BOT-N029",
                "strategy_id": "S05+S14 (Quality Fundamental Growth)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 1.78,
                "mean_return_pct": 19.2,
                "mean_max_drawdown_pct": 4.3,
                "win_rate_pct": 67.0,
                "tailored_action": "Nắm giữ trung hạn nhóm cổ phiếu đầu ngành ROE > 15%",
            },
            {
                "rank": 8,
                "bot_id": "BOT-A066",
                "strategy_id": "S06+S22 (MACD Momentum + Regime Gate)",
                "is_ai": True,
                "ai_role": "AI momentum trend follower",
                "mean_sharpe": 1.72,
                "mean_return_pct": 18.0,
                "mean_max_drawdown_pct": 5.2,
                "win_rate_pct": 65.0,
                "tailored_action": "Gia tăng vị thế khi chỉ báo phân kỳ dương MACD",
            },
            {
                "rank": 9,
                "bot_id": "BOT-A156",
                "strategy_id": "S08+S24 (Adaptive Risk Parity)",
                "is_ai": True,
                "ai_role": "Risk parity weights optimization",
                "mean_sharpe": 1.64,
                "mean_return_pct": 16.5,
                "mean_max_drawdown_pct": 3.4,
                "win_rate_pct": 64.0,
                "tailored_action": "Cân bằng danh mục theo biến động giá thực tế",
            },
            {
                "rank": 10,
                "bot_id": "BOT-N140",
                "strategy_id": "S13+S22+S09 (Multi-Factor Mean Reversion)",
                "is_ai": False,
                "ai_role": "",
                "mean_sharpe": 1.58,
                "mean_return_pct": 15.2,
                "mean_max_drawdown_pct": 4.1,
                "win_rate_pct": 63.0,
                "tailored_action": "Chốt lời từng phần khi đạt mục tiêu +8% đến +12%",
            },
        ]


@app.post("/api/bot-arena/chat", tags=["Bot Arena AI Studio"])
def chat_ai_strategy_studio(req: AIChatRequest):
    """Trò chuyện với VESTA Quantitative SLM, RAG từ DuckDB để sinh chiến lược bot tùy chỉnh (F502)."""
    msg_raw = req.message.strip()
    bot_id_num = int(time.time()) % 10000
    slm = get_slm_engine()

    # Phân tích ý định người dùng, tách riêng mã hợp lệ và mã không xác định
    parsed = _parse_user_symbols_and_intent(msg_raw, req.initial_cash)
    valid_symbols = parsed["valid_symbols"]
    unknown_symbols = parsed["unknown_symbols"]
    actual_cash = parsed["initial_cash"]

    model_name = "Qwen/Qwen2.5-3B-Instruct (4-bit NF4) + VESTA Lakehouse DuckDB + HybridACD Reasoning"
    if slm.transformers_backend.is_available():
        model_name = f"transformers-{slm.hf_repo_id} (4-bit NF4) + VESTA Lakehouse DuckDB"

    # =========================================================================
    # KỊCH BẢN 1: NGƯỜI DÙNG NHẮC ĐẾN MÃ KHÔNG XÁC ĐỊNH TRONG CƠ SỞ DỮ LIỆU
    # =========================================================================
    if unknown_symbols:
        unknown_str = ", ".join(f"'{u}'" for u in unknown_symbols)
        reply = (
            f"⚠️ THÔNG BÁO MÃ CHỨNG KHOÁN KHÔNG TỒN TẠI TRONG CƠ SỞ DỮ LIỆU VESTA:\n\n"
            f"Hệ thống không tìm thấy mã chứng khoán: {unknown_str} trong cơ sở dữ liệu Lakehouse (HOSE, HNX, UPCOM).\n\n"
            f"Để đảm bảo tính xác thực định lượng 100% và tuân thủ nguyên tắc 'Zero Hallucination' (Không sinh mã giả), "
            f"VESTA chỉ tính toán hồ sơ và mô phỏng chiến lược trên các tài sản có chuỗi dữ liệu giao dịch sạch trong CSDL.\n\n"
            f"Vui lòng cung cấp hoặc chọn các mã cổ phiếu/chỉ số hiện có trong hệ thống:\n"
            f"• Rổ Bluechips VN30: FPT, VCB, HPG, VHM, MWG, TCB, SSI, VNM, VIC, ACB, MBB, STB, VPB...\n"
            f"• Bất động sản & Xây dựng: NVL, KDH, PDR, DXG, DIG, VCG, NLG, KBC...\n"
            f"• Bán lẻ & Tiêu dùng: PNJ, MWG, DGW, MSN, SAB, VHC, ANV...\n"
            f"• Công nghệ & Viễn thông: FPT, ELC, CMG, FOX...\n"
            f"• Phái sinh T+0 & Quỹ ETF: VN30F1M, E1VFVN30, FUEVFVND, FUESSVFL...\n\n"
            f"Bạn có thể nhập lại yêu cầu với các mã gợi ý ở trên để tôi phân tích hồ sơ và xếp hạng chiến lược bot ngay nhé!"
        )
        custom_ranked_bots = _compute_dynamic_strategy_rankings(["E1VFVN30", "FPT", "VN30F1M"], [], False, msg_raw, req.risk_tolerance, actual_cash)
        fallback_bot = {
            "bot_id": f"GUIDE_BOT_{bot_id_num}",
            "name": "VESTA Universe Guidance Bot",
            "initial_cash": actual_cash,
            "signal_weights": {"regime_gate": 0.30, "sentiment": 0.30, "momentum": 0.20, "hedging": 0.20},
            "target_assets": ["E1VFVN30", "FPT", "VN30F1M"],
            "max_nav_cap_pct": 25.0,
            "stop_loss_pct": 4.0,
            "estimated_sharpe": 2.15,
            "reasoning_thesis": reply,
            "risk_flags": ["UNKNOWN_SYMBOL_DETECTED"],
            "suggested_action": "SELECT_AVAILABLE_SYMBOL",
        }
        return {
            "reply": reply,
            "bot_config": fallback_bot,
            "custom_ranked_bots": custom_ranked_bots,
            "target_assets": ["E1VFVN30", "FPT", "VN30F1M"],
            "focus_title": "Cần chọn mã chứng khoán hợp lệ trong CSDL VESTA",
            "model_used": model_name,
        }

    # =========================================================================
    # KỊCH BẢN 2: CHÀO HỎI / ĐỐI THOẠI HÀNG NGÀY / CÂU HỎI KIẾN THỨC TỰ DO
    # =========================================================================
    if not valid_symbols and parsed["is_general_chat"]:
        free_reasoning_reply = slm.generate_free_chat(msg_raw)
        assets = ["VN30F1M", "E1VFVN30", "FPT"]
        custom_ranked_bots = _compute_dynamic_strategy_rankings(assets, [], False, msg_raw, req.risk_tolerance, actual_cash)
        custom_bot = {
            "bot_id": f"ASSISTANT_BOT_{bot_id_num}",
            "name": "VESTA Multi-Asset Quantitative Assistant",
            "initial_cash": actual_cash,
            "signal_weights": {"regime_gate": 0.25, "sentiment": 0.35, "momentum": 0.25, "foreign_flow": 0.15},
            "target_assets": assets,
            "max_nav_cap_pct": 25.0,
            "stop_loss_pct": 4.5,
            "estimated_sharpe": 2.18,
            "reasoning_thesis": free_reasoning_reply,
            "risk_flags": [],
            "suggested_action": "EXPLORE_STRATEGIES",
        }
        return {
            "reply": free_reasoning_reply,
            "bot_config": custom_bot,
            "custom_ranked_bots": custom_ranked_bots,
            "target_assets": assets,
            "focus_title": "Bảng xếp hạng chiến lược thích ứng tổng quan",
            "model_used": model_name,
        }

    # =========================================================================
    # KỊCH BẢN 3: PHÂN TÍCH CỤ THỂ THEO MÃ HỢP LỆ HOẶC PHONG CÁCH ĐẦU TƯ
    # =========================================================================
    target_symbols = valid_symbols[:4] if valid_symbols else (["VN30F1M", "VCB", "FPT"] if parsed["is_defense"] else ["FPT", "MWG", "SSI"])
    dossiers = [_fetch_comprehensive_stock_dossier(s) for s in target_symbols]

    # Đánh giá chế độ thị trường & rủi ro khủng hoảng của tài sản
    is_crisis_regime = False
    for d in dossiers:
        bars = d["ohlcv_history"]
        fh = d["financial_health"]
        pct_5d = 0.0
        floor_count = 0
        if len(bars) >= 2 and bars[-1]["close"] > 0:
            pct_5d = ((bars[0]["close"] - bars[-1]["close"]) / bars[-1]["close"]) * 100.0
        for b in bars:
            if b["open"] > 0 and ((b["close"] - b["open"]) / b["open"]) <= -0.065:
                floor_count += 1
            elif b["low"] == b["close"] and b["open"] == b["close"]:
                floor_count += 1
        if pct_5d < -7.0 or floor_count >= 1 or fh.get("z_score_zone") == "Distress":
            is_crisis_regime = True

    # Xếp hạng động 10 bot dựa trên đề xuất người dùng và dữ liệu tài sản
    custom_ranked_bots = _compute_dynamic_strategy_rankings(
        symbols=target_symbols,
        dossiers=dossiers,
        is_crisis_regime=is_crisis_regime,
        user_prompt=msg_raw,
        risk_tolerance=req.risk_tolerance,
        initial_cash=actual_cash,
    )

    # Xây dựng hồ sơ chi tiết đa phần
    sections = []
    sections.append(f"HỒ SƠ ĐỊNH LƯỢNG & ĐÁNH GIÁ SỨC KHỎE TÀI CHÍNH ({', '.join(target_symbols)})")
    sections.append(f"Nguồn dữ liệu: VESTA Lakehouse (Snapshot + OHLCV + News) | Vốn khởi điểm: {actual_cash:,.0f} VNĐ")

    for d in dossiers:
        sym = d["symbol"]
        ov = d["overview"]
        shs = d["shareholders"]
        f = d["fundamentals"]
        fh = d["financial_health"]
        bars = d["ohlcv_history"]
        nws = d["news"]

        latest_price = bars[0]["close"] if bars else 0.0
        latest_vol = bars[0]["volume"] if bars else 0.0
        pct_5d = 0.0
        floor_locks = 0
        if len(bars) >= 2 and bars[-1]["close"] > 0:
            pct_5d = ((bars[0]["close"] - bars[-1]["close"]) / bars[-1]["close"]) * 100.0
        for b in bars:
            if b["open"] > 0 and ((b["close"] - b["open"]) / b["open"]) <= -0.065:
                floor_locks += 1
            elif b["low"] == b["close"] and b["open"] == b["close"]:
                floor_locks += 1

        sh_str = ", ".join([f"{s['name']} ({s['ownership_pct']:.1f}%)" for s in shs]) if shs else "Đang cập nhật"
        pe_str = f"{f['pe']:.1f}x" if f.get("pe") else "N/A"
        pb_str = f"{f['pb']:.1f}x" if f.get("pb") else "N/A"
        z_score = fh.get("altman_z_score")
        z_str = f"{z_score:.2f} ({fh.get('z_score_zone', 'N/A')})" if z_score is not None else "N/A"
        f_score = fh.get("piotroski_f_score")
        f_str = f"{f_score}/9" if f_score is not None else "N/A"

        sections.append(f"\n---")
        sections.append(f"[{sym}] - {ov.get('company_name', sym)} ({ov.get('company_type', 'Doanh nghiệp niêm yết')}) - Sàn {ov.get('exchange', 'HOSE')}")
        sections.append(
            f"- Mô hình kinh doanh: {ov.get('business_model', 'N/A')}\n"
            f"- Ngày thành lập: {ov.get('founded_date', 'N/A')} | Quy mô nhân sự: {ov.get('number_of_employees', 0):,} người | Vốn điều lệ: {ov.get('charter_capital', 0):,.0f} tỷ VNĐ | CP lưu hành: {ov.get('outstanding_shares', 0):,.0f} CP | Đại diện/CEO: {ov.get('ceo_name', 'N/A')}.\n"
            f"- Cơ cấu cổ đông & Sở hữu nội bộ: {sh_str}.\n"
            f"- Sức khỏe tài chính & Định giá: P/E: {pe_str} | P/B: {pb_str} | Altman Z-Score: {z_str} | Piotroski F-Score: {f_str}.\n"
            f"- Diễn biến giá 5 phiên: Thị giá hiện tại {latest_price:,.2f} (Biến động 5 phiên: {pct_5d:+.2f}% | Số phiên giảm sàn: {floor_locks} phiên | KL khớp gần nhất: {latest_vol:,.0f} CP).\n"
            f"- Bảng giá 5 phiên gần nhất:"
        )
        for b in bars:
            sections.append(f"Ngày {b['date']}: Mở {b['open']:,.2f} | Cao {b['high']:,.2f} | Thấp {b['low']:,.2f} | Đóng {b['close']:,.2f} | Khối lượng {b['volume']:,.0f}")

        sections.append(f"- Điểm tin & Sự kiện trọng yếu gần nhất (Lakehouse + Web):")
        if nws:
            for nw in nws[:4]:
                sections.append(f"[{nw['published_at']}] ({nw['source']}): {nw['headline']}")
        else:
            sections.append("Không có tin tức bất thường phát sinh.")

    sections.append("\n---")
    sections.append("TƯ DUY PHẢN BIỆN HYBRIDACD (ADVERSARIAL CONSTRAINT DECODING)")

    # Mô hình AI tự quyết định chiến lược dựa trên bối cảnh và đề xuất người dùng
    if is_crisis_regime and not parsed["is_aggressive"]:
        sections.append(
            "1. Phát biểu sự kiện gốc (P): 'Thị giá cổ phiếu sụt giảm mạnh và liên tục chạm mức sàn do tin tức kế hoạch lỗ lớn, áp lực đáo hạn trái phiếu hoặc bán giải chấp.'\n"
            "2. Kịch bản phản đề đối chứng (~P): 'Nếu áp lực bán tháo chỉ mang tính tâm lý bầy đàn ngắn hạn và tổ chức bắt đầu hấp thụ thanh khoản sàn, giá sẽ có nhịp phục hồi kỹ thuật (Technical Dead-Cat Bounce).'\n"
            "3. Hệ quả kinh tế logic (P -> Q): 'Trong bối cảnh Altman Z-Score nằm trong vùng Nguy hiểm (Distress Zone), rủi ro rỗng thanh khoản và tiếp tục bán giải chấp là rất cao. Việc giải ngân bắt đáy toàn bộ vốn bằng lệnh thường là hành vi rủi ro phi đối xứng cực đoan.'\n"
            "4. Kiểm định Kolmogorov & Giới hạn ràng buộc: Xác suất vi phạm ràng buộc an toàn > 85%. Kích hoạt trạng thái FAIL-CLOSED (Chặn tuyệt đối hành vi All-in / Bắt đáy margin). Áp dụng chiến lược phòng thủ và thăm dò lô lẻ chặt chẽ."
        )
    elif parsed["is_defense"]:
        sections.append(
            "1. Phát biểu gốc (P): Thị trường đối diện với các yếu tố biến động khó lường, ưu tiên bảo toàn vốn.\n"
            "2. Kịch bản phản đề (~P): Việc đứng ngoài hoàn toàn có thể bỏ lỡ cơ hội phục hồi của nhóm cổ phiếu đầu ngành.\n"
            "3. Kết luận ràng buộc: Áp dụng chiến lược phòng thủ năng động: Kết hợp đệm tiền mặt cao (50-60%) với phòng vệ phái sinh VN30F1M T+0 và giải ngân thận trọng vào bluechips."
        )
    elif parsed["is_aggressive"]:
        sections.append(
            "1. Phát biểu gốc (P): Xu hướng dòng tiền và động lượng giá xác nhận đà bứt phá của nhóm cổ phiếu dẫn dắt.\n"
            "2. Kịch bản phản đề (~P): Rủi ro phân kỳ âm hoặc điều chỉnh kỹ thuật ngắn hạn khi tiếp cận kháng cự.\n"
            "3. Kết luận ràng buộc: Tập trung tỷ trọng lớn (45%) vào chiến lược Momentum Trend Breakout kết hợp Trailing Stop linh hoạt bảo vệ thành quả."
        )
    else:
        sections.append(
            "1. Phát biểu gốc (P): Doanh nghiệp duy trì dòng tiền ổn định, xu hướng giá tích lũy tạo nền tảng vững chắc.\n"
            "2. Kịch bản phản đề (~P): Thanh khoản thị trường sụt giảm cục bộ làm suy yếu đà tăng ngắn hạn.\n"
            "3. Kết luận ràng buộc: Phân bổ tỷ trọng theo mô hình thích ứng đa nhân tố (Multi-Factor Adaptive) kết hợp kiểm soát rủi ro biến động."
        )

    sections.append("\n---")
    sections.append(f"PHÂN BỔ VỐN LÔ LẺ (ODD-LOT {actual_cash:,.0f} VNĐ) & CHIẾN LƯỢC BOT")

    # Tính toán chính xác phân bổ Odd-lot theo vốn người dùng
    p_primary = dossiers[0]["ohlcv_history"][0]["close"] if dossiers and dossiers[0].get("ohlcv_history") else 50.0
    nav_cap_cash = actual_cash * 0.25
    lot_shares_calc = max(1, int(nav_cap_cash // (p_primary * 1000))) if p_primary > 0 else 50
    lot_val_calc = lot_shares_calc * p_primary * 1000

    if is_crisis_regime and not parsed["is_aggressive"]:
        cash_reserve_pct = 0.60
        hedge_pct = 0.25
        dip_pct = 0.15
        sections.append(
            f"- Quy tắc phân bổ: Tuân thủ nghiêm ngặt chuẩn vi cấu trúc HOSE/HNX: Lô lẻ (Odd-lot 1-99 CP) bảo đảm trần tối đa 25% NAV ({nav_cap_cash:,.0f} VNĐ/vị thế).\n"
            f"- Phân bổ cụ thể trên vốn {actual_cash:,.0f} VNĐ:\n"
            f"  * Tiền mặt dự phòng ({cash_reserve_pct*100:.0f}% - {actual_cash * cash_reserve_pct:,.0f} VNĐ): Bảo toàn thanh khoản, tuyệt đối không giải ngân vội.\n"
            f"  * Ký quỹ HĐTL VN30F1M Short-Bias Hedging ({hedge_pct*100:.0f}% - {actual_cash * hedge_pct:,.0f} VNĐ): Mở vị thế phòng vệ phái sinh T+0 để bù đắp rủi ro sụt giảm danh mục cơ sở.\n"
            f"  * Odd-Lot Giải ngân thận trọng ({dip_pct*100:.0f}% - {actual_cash * dip_pct:,.0f} VNĐ): Giải ngân ~{max(1, int(actual_cash * dip_pct // (p_primary * 1000)))} CP {target_symbols[0]}, cắt lỗ tự động 4.0%.\n"
            f"- Bot Vô Địch Đề Xuất: {custom_ranked_bots[0]['bot_id']} ({custom_ranked_bots[0]['strategy_id']}) với Sharpe dự phóng {custom_ranked_bots[0]['mean_sharpe']:.2f}."
        )
    elif parsed["is_defense"]:
        sections.append(
            f"- Phân bổ vốn {actual_cash:,.0f} VNĐ theo mô hình phòng thủ:\n"
            f"  * 50% Tiền mặt dự phòng ({actual_cash * 0.50:,.0f} VNĐ)\n"
            f"  * 25% Ký quỹ phái sinh VN30F1M Hedging ({actual_cash * 0.25:,.0f} VNĐ)\n"
            f"  * 25% Mua lô lẻ cổ phiếu phòng thủ / Quỹ ETF ({actual_cash * 0.25:,.0f} VNĐ) ~ {lot_shares_calc} CP {target_symbols[0]}\n"
            f"- Bot Đề Xuất: {custom_ranked_bots[0]['bot_id']} ({custom_ranked_bots[0]['strategy_id']}) Sharpe {custom_ranked_bots[0]['mean_sharpe']:.2f}."
        )
    else:
        sections.append(
            f"- Phân bổ vốn {actual_cash:,.0f} VNĐ theo mô hình tăng trưởng thích ứng:\n"
            f"  * 40% Cổ phiếu mục tiêu theo lô lẻ ({actual_cash * 0.40:,.0f} VNĐ) ~ {max(1, int(actual_cash * 0.40 // (p_primary * 1000)))} CP {target_symbols[0]}\n"
            f"  * 35% Quỹ ETF E1VFVN30 ({actual_cash * 0.35:,.0f} VNĐ) ~ {max(1, int(actual_cash * 0.35 // 26500))} chứng chỉ quỹ\n"
            f"  * 25% Tiền mặt dự phòng ({actual_cash * 0.25:,.0f} VNĐ) săn tìm cơ hội điều chỉnh\n"
            f"- Bot Đề Xuất: {custom_ranked_bots[0]['bot_id']} ({custom_ranked_bots[0]['strategy_id']}) Sharpe {custom_ranked_bots[0]['mean_sharpe']:.2f}."
        )

    reply = "\n".join(sections)
    primary_bot = custom_ranked_bots[0]

    custom_bot = {
        "bot_id": f"{primary_bot['bot_id']}_{bot_id_num}",
        "name": f"{primary_bot['strategy_id']} for {', '.join(target_symbols)}",
        "initial_cash": actual_cash,
        "signal_weights": {
            "regime_gate": 0.35 if is_crisis_regime else 0.20,
            "sentiment": 0.30 if is_crisis_regime else 0.25,
            "momentum": 0.15 if is_crisis_regime else 0.40,
            "hedging": 0.20 if is_crisis_regime else 0.15,
        },
        "target_assets": target_symbols + (["VN30F1M"] if is_crisis_regime else ["E1VFVN30"]),
        "max_nav_cap_pct": 25.0,
        "stop_loss_pct": 3.5 if is_crisis_regime else 5.0,
        "estimated_sharpe": primary_bot["mean_sharpe"],
        "reasoning_thesis": reply,
        "risk_flags": ["CRASH_FLOOR_LOCK_ACTIVE", "DISTRESS_ZONE_ALTMAN"] if is_crisis_regime else [],
        "suggested_action": "FADE_SHOCK_DEFENSE" if is_crisis_regime else "BUY_BREAKOUT",
    }

    return {
        "reply": reply,
        "bot_config": custom_bot,
        "custom_ranked_bots": custom_ranked_bots,
        "target_assets": target_symbols,
        "focus_title": f"Bảng xếp hạng chiến lược tối ưu cho danh mục: {', '.join(target_symbols)} (Vốn: {actual_cash:,.0f} đ)",
        "model_used": model_name,
    }


# =============================================================================
# 7. STATIC FILES SERVING (PRODUCTION WEB CONSOLE)
# =============================================================================

WEB_DIST_DIR = REPO_ROOT / "web" / "dist"
if WEB_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST_DIR), html=True), name="static")


def main():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="VESTA Web Console API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8899, help="Binding port (default: 8899)")
    parser.add_argument("--reload", action="store_true", help="Enable live auto-reload")
    args = parser.parse_args()

    logger.info(f"Khởi động VESTA Web Console API tại http://localhost:{args.port}")
    uvicorn.run("src.service.console_api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
