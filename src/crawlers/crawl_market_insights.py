"""src/crawlers/crawl_market_insights.py

Master Crawler & Ingestion Pipeline cho Phân hệ F007b (Insights, Screener, Valuation, Macro).
Kiến trúc Direct REST API (Zero vnstock / Zero API Key):
1. Screener: Thu thập toàn bộ 1.522+ mã cổ phiếu toàn thị trường với 24-51 chỉ tiêu định lượng.
2. Index Valuation: Thu thập toàn bộ chuỗi định giá P/E, P/B lịch sử của VN-Index, VN30, HNX (từ 2017 đến nay, >13.100 điểm dữ liệu).
3. Market Breadth: Thu thập chuỗi độ rộng thị trường (740+ ngày giao dịch cho HOSE, HNX, UPCOM, >2.220 dòng).
4. Market Sentiment: Thu thập chỉ số Sợ hãi & Tham lam (Fear & Greed Index) hàng ngày cho cả 3 sàn.
5. Macroeconomic Series: Thu thập toàn bộ 12 chỉ báo kinh tế vĩ mô (GDP, CPI, Xuất nhập khẩu, Lãi suất, Tỷ giá...).

Lưu trữ vào DuckDB qua ResilientDuckDBWriter (bảo đảm an toàn giao dịch ACID và không bị lock).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.crawlers import market_insights
from src.crawlers.db_writer import ResilientDuckDBWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawl_market_insights")


class MarketInsightsMasterCrawler:
    """Master Crawler cho phân hệ Insights, Screener, Valuation & Macroeconomic Direct REST API."""

    def __init__(self, writer: Optional[ResilientDuckDBWriter] = None) -> None:
        self.writer = writer or ResilientDuckDBWriter()

    # ========================================================================
    # 1. SCREENER FULL MARKET CRAWLER
    # ========================================================================
    def crawl_screener(self) -> int:
        """Thu thập bộ lọc đa nhân tố cho toàn bộ cổ phiếu trên 3 sàn (HSX, HNX, UPCOM)."""
        logger.info("-> [Screener] Bắt đầu quét toàn bộ cổ phiếu toàn thị trường từ Vietcap IQ Direct API...")
        t0 = time.time()
        try:
            df_raw = market_insights.fetch_market_screener(page_size=1600, timeout=20)
        except Exception as exc:
            logger.error("-> [Screener] Lỗi khi gọi Vietcap Screener: %s", exc)
            return 0

        if df_raw.empty:
            logger.warning("-> [Screener] Không có dữ liệu trả về.")
            return 0

        now = dt.datetime.now(dt.timezone.utc)
        today = now.date()

        records: List[Dict[str, Any]] = []
        for _, row in df_raw.iterrows():
            sym = str(row.get("symbol", "")).strip().upper()
            if not sym:
                continue

            raw_dict = row.to_dict()
            clean_dict = {k: (None if pd.isna(v) else v) for k, v in raw_dict.items()}

            records.append({
                "symbol": sym,
                "snapshot_date": today,
                "exchange": str(row.get("exchange", "")).upper() or None,
                "price": float(row["price"]) if pd.notnull(row.get("price")) else None,
                "reference_price": float(row["reference_price"]) if pd.notnull(row.get("reference_price")) else None,
                "ceiling_price": float(row["ceiling_price"]) if pd.notnull(row.get("ceiling_price")) else None,
                "floor_price": float(row["floor_price"]) if pd.notnull(row.get("floor_price")) else None,
                "price_change_percent": float(row["price_change_percent"]) if pd.notnull(row.get("price_change_percent")) else None,
                "market_cap": float(row["market_cap"]) if pd.notnull(row.get("market_cap")) else None,
                "accumulated_value": float(row["accumulated_value"]) if pd.notnull(row.get("accumulated_value")) else None,
                "accumulated_volume": float(row["accumulated_volume"]) if pd.notnull(row.get("accumulated_volume")) else None,
                "stock_strength": float(row["stock_strength"]) if pd.notnull(row.get("stock_strength")) else None,
                "data_json": json.dumps(clean_dict, ensure_ascii=False, default=str),
                "source": "VIETCAP_IQ_DIRECT",
                "fetched_at": now,
            })

        df_to_save = pd.DataFrame(records)

        def _insert_screener(con: duckdb.DuckDBPyConnection) -> int:
            con.register("df_screener_stg", df_to_save)
            con.execute("""
                INSERT INTO staging.market_screener_snapshot
                SELECT * FROM df_screener_stg
            """)
            con.unregister("df_screener_stg")

            con.register("df_screener_core", df_to_save)
            con.execute("""
                INSERT INTO core.market_screener_snapshot
                SELECT * FROM df_screener_core
                ON CONFLICT (symbol, snapshot_date) DO UPDATE SET
                    exchange = EXCLUDED.exchange,
                    price = EXCLUDED.price,
                    reference_price = EXCLUDED.reference_price,
                    ceiling_price = EXCLUDED.ceiling_price,
                    floor_price = EXCLUDED.floor_price,
                    price_change_percent = EXCLUDED.price_change_percent,
                    market_cap = EXCLUDED.market_cap,
                    accumulated_value = EXCLUDED.accumulated_value,
                    accumulated_volume = EXCLUDED.accumulated_volume,
                    stock_strength = EXCLUDED.stock_strength,
                    data_json = EXCLUDED.data_json,
                    source = EXCLUDED.source,
                    fetched_at = EXCLUDED.fetched_at
            """)
            con.unregister("df_screener_core")
            return len(df_to_save)

        count = self.writer.execute_with_retry(_insert_screener)
        el = time.time() - t0
        logger.info("-> [Screener] Đã lưu thành công +%d mã cổ phiếu vào core.market_screener_snapshot (mất %.2fs)", count, el)
        return count

    # ========================================================================
    # 2. HISTORICAL INDEX VALUATION CRAWLER
    # ========================================================================
    def crawl_index_valuation(self) -> int:
        """Thu thập toàn bộ chuỗi định giá P/E và P/B lịch sử của VNINDEX, VN30, HNX."""
        logger.info("-> [Index Valuation] Bắt đầu thu thập toàn bộ lịch sử P/E và P/B của VN-Index, VN30, HNX...")
        t0 = time.time()
        targets = [
            ("VNINDEX", "PRICE_TO_EARNINGS"),
            ("VNINDEX", "PRICE_TO_BOOK"),
            ("VN30", "PRICE_TO_EARNINGS"),
            ("VN30", "PRICE_TO_BOOK"),
            ("HNX", "PRICE_TO_EARNINGS"),
            ("HNX", "PRICE_TO_BOOK"),
        ]

        total_saved = 0
        now = dt.datetime.now(dt.timezone.utc)

        for idx, rc in targets:
            try:
                df = market_insights.fetch_index_valuation(index=idx, ratio_code=rc, start_date="2010-01-01", timeout=12)
            except Exception as exc:
                logger.error("-> [Index Valuation] Lỗi khi lấy %s (%s): %s", idx, rc, exc)
                continue

            if df.empty:
                logger.warning("-> [Index Valuation] Không có dữ liệu cho %s (%s)", idx, rc)
                continue

            records = []
            for _, row in df.iterrows():
                rep_date = pd.to_datetime(row["report_date"]).date()
                val = float(row["value"]) if pd.notnull(row["value"]) else None
                if val is not None:
                    records.append({
                        "index_code": idx,
                        "ratio_code": rc,
                        "report_date": rep_date,
                        "ratio_value": val,
                        "source": "VNDIRECT_FINFO_DIRECT",
                        "fetched_at": now,
                    })

            df_to_save = pd.DataFrame(records)

            def _insert_val(con: duckdb.DuckDBPyConnection) -> int:
                con.register("df_val_stg", df_to_save)
                con.execute("""
                    INSERT INTO staging.index_valuation_series
                    SELECT * FROM df_val_stg
                """)
                con.unregister("df_val_stg")

                con.register("df_val_core", df_to_save)
                con.execute("""
                    INSERT INTO core.index_valuation_series
                    SELECT * FROM df_val_core
                    ON CONFLICT (index_code, ratio_code, report_date) DO UPDATE SET
                        ratio_value = EXCLUDED.ratio_value,
                        source = EXCLUDED.source,
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.unregister("df_val_core")
                return len(df_to_save)

            saved = self.writer.execute_with_retry(_insert_val)
            total_saved += saved
            logger.info("   -> [%s - %s] Đã nạp +%d phiên (từ %s đến %s)", idx, rc, saved, df["report_date"].iloc[0].strftime("%Y-%m-%d"), df["report_date"].iloc[-1].strftime("%Y-%m-%d"))

        el = time.time() - t0
        logger.info("-> [Index Valuation] Tổng cộng đã lưu +%d dòng định giá lịch sử vào core.index_valuation_series (mất %.2fs)", total_saved, el)
        return total_saved

    # ========================================================================
    # 3. HISTORICAL MARKET BREADTH CRAWLER
    # ========================================================================
    def crawl_market_breadth(self) -> int:
        """Thu thập toàn bộ chuỗi lịch sử độ rộng thị trường (>740 ngày) cho HOSE, HNX, UPCOM."""
        logger.info("-> [Market Breadth] Bắt đầu thu thập toàn bộ lịch sử độ rộng thị trường cho HOSE, HNX, UPCOM...")
        t0 = time.time()
        exchanges = ["HOSE", "HNX", "UPCOM"]
        total_saved = 0
        now = dt.datetime.now(dt.timezone.utc)

        for ex in exchanges:
            try:
                df = market_insights.fetch_market_breadth(exchange=ex, timeout=12)
            except Exception as exc:
                logger.error("-> [Market Breadth] Lỗi khi lấy độ rộng sàn %s: %s", ex, exc)
                continue

            if df.empty:
                logger.warning("-> [Market Breadth] Không có dữ liệu cho sàn %s", ex)
                continue

            records = []
            for _, row in df.iterrows():
                t_date = pd.to_datetime(row["trade_date"]).date()
                records.append({
                    "exchange": ex,
                    "trade_date": t_date,
                    "pe": float(row["pe"]) if pd.notnull(row.get("pe")) else None,
                    "pb": float(row["pb"]) if pd.notnull(row.get("pb")) else None,
                    "above_ma20_pct": float(row["above_ma20_pct"]) if pd.notnull(row.get("above_ma20_pct")) else None,
                    "above_ma50_pct": float(row["above_ma50_pct"]) if pd.notnull(row.get("above_ma50_pct")) else None,
                    "above_ma200_pct": float(row["above_ma200_pct"]) if pd.notnull(row.get("above_ma200_pct")) else None,
                    "avg_20d_above_ma50_pct": float(row["avg_20d_above_ma50_pct"]) if pd.notnull(row.get("avg_20d_above_ma50_pct")) else None,
                    "position_line": float(row["position_line"]) if pd.notnull(row.get("position_line")) else None,
                    "close_index": float(row["close_index"]) if pd.notnull(row.get("close_index")) else None,
                    "source": "ASEAN_SC_DIRECT",
                    "fetched_at": now,
                })

            df_to_save = pd.DataFrame(records)

            def _insert_breadth(con: duckdb.DuckDBPyConnection) -> int:
                con.register("df_breadth_stg", df_to_save)
                con.execute("""
                    INSERT INTO staging.market_breadth_series
                    SELECT * FROM df_breadth_stg
                """)
                con.unregister("df_breadth_stg")

                con.register("df_breadth_core", df_to_save)
                con.execute("""
                    INSERT INTO core.market_breadth_series
                    SELECT * FROM df_breadth_core
                    ON CONFLICT (exchange, trade_date) DO UPDATE SET
                        pe = EXCLUDED.pe,
                        pb = EXCLUDED.pb,
                        above_ma20_pct = EXCLUDED.above_ma20_pct,
                        above_ma50_pct = EXCLUDED.above_ma50_pct,
                        above_ma200_pct = EXCLUDED.above_ma200_pct,
                        avg_20d_above_ma50_pct = EXCLUDED.avg_20d_above_ma50_pct,
                        position_line = EXCLUDED.position_line,
                        close_index = EXCLUDED.close_index,
                        source = EXCLUDED.source,
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.unregister("df_breadth_core")
                return len(df_to_save)

            saved = self.writer.execute_with_retry(_insert_breadth)
            total_saved += saved
            logger.info("   -> [%s] Đã nạp +%d ngày độ rộng thị trường (từ %s đến %s)", ex, saved, df["trade_date"].iloc[0].strftime("%Y-%m-%d"), df["trade_date"].iloc[-1].strftime("%Y-%m-%d"))

        el = time.time() - t0
        logger.info("-> [Market Breadth] Tổng cộng đã lưu +%d dòng độ rộng vào core.market_breadth_series (mất %.2fs)", total_saved, el)
        return total_saved

    # ========================================================================
    # 4. MARKET SENTIMENT / FEAR & GREED CRAWLER
    # ========================================================================
    def crawl_market_sentiment(self) -> int:
        """Thu thập chỉ số Sợ hãi & Tham lam (Fear & Greed Index) cho cả 3 sàn."""
        logger.info("-> [Market Sentiment] Bắt đầu thu thập chỉ số Fear & Greed cho HOSE, HNX, UPCOM...")
        t0 = time.time()
        exchanges = ["HOSE", "HNX", "UPCOM"]
        total_saved = 0
        now = dt.datetime.now(dt.timezone.utc)
        today = now.date()

        records = []
        for ex in exchanges:
            try:
                df = market_insights.fetch_market_fear_greed(exchange=ex, timeout=10)
            except Exception as exc:
                logger.error("-> [Market Sentiment] Lỗi khi lấy Fear & Greed sàn %s: %s", ex, exc)
                continue

            if df.empty:
                continue

            row = df.iloc[0]
            clean_json = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            records.append({
                "exchange": ex,
                "snapshot_date": today,
                "fear_greed_score": float(row["fear_greed_score"]) if pd.notnull(row.get("fear_greed_score")) else None,
                "advances": int(row["advances"]) if pd.notnull(row.get("advances")) else None,
                "declines": int(row["declines"]) if pd.notnull(row.get("declines")) else None,
                "no_change": int(row["no_change"]) if pd.notnull(row.get("no_change")) else None,
                "mfi": float(row["mfi"]) if pd.notnull(row.get("mfi")) else None,
                "rsi": float(row["rsi"]) if pd.notnull(row.get("rsi")) else None,
                "index_change": float(row["index_change"]) if pd.notnull(row.get("index_change")) else None,
                "volume_change": float(row["volume_change"]) if pd.notnull(row.get("volume_change")) else None,
                "raw_json": json.dumps(clean_json, ensure_ascii=False, default=str),
                "source": "ASEAN_SC_DIRECT",
                "fetched_at": now,
            })

        if not records:
            return 0

        df_to_save = pd.DataFrame(records)

        def _insert_sentiment(con: duckdb.DuckDBPyConnection) -> int:
            con.register("df_sent_stg", df_to_save)
            con.execute("""
                INSERT INTO staging.market_sentiment_snapshot
                SELECT * FROM df_sent_stg
            """)
            con.unregister("df_sent_stg")

            con.register("df_sent_core", df_to_save)
            con.execute("""
                INSERT INTO core.market_sentiment_snapshot
                SELECT * FROM df_sent_core
                ON CONFLICT (exchange, snapshot_date) DO UPDATE SET
                    fear_greed_score = EXCLUDED.fear_greed_score,
                    advances = EXCLUDED.advances,
                    declines = EXCLUDED.declines,
                    no_change = EXCLUDED.no_change,
                    mfi = EXCLUDED.mfi,
                    rsi = EXCLUDED.rsi,
                    index_change = EXCLUDED.index_change,
                    volume_change = EXCLUDED.volume_change,
                    raw_json = EXCLUDED.raw_json,
                    source = EXCLUDED.source,
                    fetched_at = EXCLUDED.fetched_at
            """)
            con.unregister("df_sent_core")
            return len(df_to_save)

        count = self.writer.execute_with_retry(_insert_sentiment)
        el = time.time() - t0
        logger.info("-> [Market Sentiment] Đã lưu thành công +%d bản ghi tâm lý vào core.market_sentiment_snapshot (mất %.2fs)", count, el)
        return count

    # ========================================================================
    # 5. MACROECONOMIC INDICATORS SERIES CRAWLER
    # ========================================================================
    def crawl_macro_series(self) -> int:
        """Thu thập toàn bộ các chuỗi chỉ số kinh tế vĩ mô từ Direct REST API."""
        logger.info("-> [Macro Series] Bắt đầu thu thập toàn bộ các chỉ số kinh tế vĩ mô dài hạn...")
        t0 = time.time()
        now = dt.datetime.now(dt.timezone.utc)

        indicators_config = [
            ("gdp", "Q", ["agr", "ind", "ser", "tax", "gdp", "vni"]),
            ("cpi", "M", ["total_cpi", "core_cpi", "vni"]),
            ("xm", "M", ["export_val", "import_val", "balance_val", "export_growth", "import_growth", "vni"]),
            ("fdi", "M", ["register_val", "realized_val", "realized_pct"]),
            ("state_budget", "Q", ["budget_in", "budget_out", "budget_net"]),
            ("total_investment", "Q", ["public", "private", "fdi", "other", "vni"]),
            ("credit", "Q", ["credit_growth", "vnindex"]),
            ("liquidity", "Q", ["total", "institutional", "private", "vnindex"]),
        ]

        total_saved_macro = 0

        for ind_name, period, sub_cols in indicators_config:
            try:
                df = market_insights.fetch_macro_indicator(indicator=ind_name, start_date="2010-01-01", period=period, timeout=12)
            except Exception as exc:
                logger.error("-> [Macro] Lỗi khi lấy chỉ số %s: %s", ind_name, exc)
                continue

            if df.empty:
                continue

            records = []
            for _, row in df.iterrows():
                rep_date = row.get("report_date")
                if pd.isnull(rep_date):
                    continue
                p_date = pd.to_datetime(rep_date).date()
                p_str = p_date.strftime("%Y-%m-%d")

                for sub in sub_cols:
                    if sub in row and pd.notnull(row[sub]):
                        records.append({
                            "indicator": ind_name,
                            "sub_indicator": sub,
                            "report_period": p_str,
                            "period_date": p_date,
                            "numeric_value": float(row[sub]),
                            "unit": "%" if "growth" in sub or "cpi" in sub or "pct" in sub or sub == "gdp" else "VND/USD/Index",
                            "meta_json": None,
                            "source": "ASEAN_SC_DIRECT",
                            "fetched_at": now,
                        })

            if not records:
                continue

            df_to_save = pd.DataFrame(records)

            def _insert_macro(con: duckdb.DuckDBPyConnection) -> int:
                con.register("df_macro_stg", df_to_save)
                con.execute("""
                    INSERT INTO staging.macro_economic_series
                    SELECT * FROM df_macro_stg
                """)
                con.unregister("df_macro_stg")

                con.register("df_macro_core", df_to_save)
                con.execute("""
                    INSERT INTO core.macro_economic_series
                    SELECT * FROM df_macro_core
                    ON CONFLICT (indicator, sub_indicator, report_period) DO UPDATE SET
                        period_date = EXCLUDED.period_date,
                        numeric_value = EXCLUDED.numeric_value,
                        unit = EXCLUDED.unit,
                        meta_json = EXCLUDED.meta_json,
                        source = EXCLUDED.source,
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.unregister("df_macro_core")
                return len(df_to_save)

            saved = self.writer.execute_with_retry(_insert_macro)
            total_saved_macro += saved
            logger.info("   -> [%s] Đã nạp +%d dòng dữ liệu (từ %s đến %s)", ind_name, saved, df["report_date"].iloc[0].strftime("%Y-%m-%d"), df["report_date"].iloc[-1].strftime("%Y-%m-%d"))

        # Thu thập lãi suất liên ngân hàng (Interbank) -> nạp vào macro_rates
        try:
            df_ib = market_insights.fetch_macro_indicator(indicator="interbank_rate", start_date="2020-01-01", period="ON", timeout=12)
            if not df_ib.empty:
                ib_records = []
                for _, row in df_ib.iterrows():
                    d = pd.to_datetime(row["report_date"]).date()
                    if pd.notnull(row.get("interest")):
                        ib_records.append({
                            "rate_type": "INTERBANK",
                            "term": "ON",
                            "date": d,
                            "rate_value": float(row["interest"]),
                            "source": "ASEAN_SC_DIRECT",
                            "fetched_at": now,
                        })
                if ib_records:
                    df_ib_save = pd.DataFrame(ib_records)

                    def _insert_ib(con: duckdb.DuckDBPyConnection) -> int:
                        con.register("df_ib_core", df_ib_save)
                        con.execute("""
                            INSERT INTO core.macro_rates
                            SELECT * FROM df_ib_core
                            ON CONFLICT (rate_type, term, date) DO UPDATE SET
                                rate_value = EXCLUDED.rate_value,
                                source = EXCLUDED.source,
                                fetched_at = EXCLUDED.fetched_at
                        """)
                        con.unregister("df_ib_core")
                        return len(df_ib_save)

                    saved_ib = self.writer.execute_with_retry(_insert_ib)
                    logger.info("   -> [Interbank] Đã nạp +%d mốc lãi suất liên ngân hàng vào core.macro_rates", saved_ib)
        except Exception as exc:
            logger.error("-> [Macro] Lỗi khi nạp Interbank rates: %s", exc)

        el = time.time() - t0
        logger.info("-> [Macro Series] Tổng cộng đã lưu +%d dòng chỉ số vĩ mô vào core.macro_economic_series (mất %.2fs)", total_saved_macro, el)
        return total_saved_macro

    # ========================================================================
    # RUN ALL
    # ========================================================================
    def run_all(self) -> Dict[str, int]:
        """Chạy toàn bộ các cấu phần của phân hệ Market Insights & Macro."""
        logger.info("================================================================================")
        logger.info("BẮT ĐẦU CHẠY MASTER CRAWLER CHO PHÂN HỆ F007b (DIRECT REST API)")
        logger.info("================================================================================")
        t_start = time.time()

        res_screener = self.crawl_screener()
        res_val = self.crawl_index_valuation()
        res_breadth = self.crawl_market_breadth()
        res_sentiment = self.crawl_market_sentiment()
        res_macro = self.crawl_macro_series()

        # Đồng bộ buffer sang CSDL vesta_snapshot.duckdb
        logger.info("Đang đồng bộ dữ liệu từ staging buffer sang CSDL chính...")
        sync_res = self.writer.atomic_ingest_buffer()
        logger.info("Kết quả đồng bộ: %s", sync_res)

        total_el = time.time() - t_start
        logger.info("================================================================================")
        logger.info("HOÀN TẤT CÀO DỮ LIỆU F007b! TỔNG THỜI GIAN: %.2fs", total_el)
        logger.info("Chi tiết: Screener=%d, Index Valuation=%d, Breadth=%d, Sentiment=%d, Macro=%d", res_screener, res_val, res_breadth, res_sentiment, res_macro)
        logger.info("================================================================================")

        return {
            "screener_rows": res_screener,
            "valuation_rows": res_val,
            "breadth_rows": res_breadth,
            "sentiment_rows": res_sentiment,
            "macro_rows": res_macro,
            "total_elapsed_seconds": round(total_el, 2),
        }


def main():
    parser = argparse.ArgumentParser(description="Master Crawler cho phân hệ F007b (Insights/Screener/Valuation/Macro)")
    parser.add_argument("--all", action="store_true", help="Chạy toàn bộ tất cả cấu phần")
    parser.add_argument("--screener", action="store_true", help="Chạy cào Screener đa nhân tố toàn thị trường")
    parser.add_argument("--valuation", action="store_true", help="Chạy cào Index Valuation (P/E, P/B lịch sử)")
    parser.add_argument("--breadth", action="store_true", help="Chạy cào Độ rộng thị trường lịch sử")
    parser.add_argument("--sentiment", action="store_true", help="Chạy cào Fear & Greed sentiment")
    parser.add_argument("--macro", action="store_true", help="Chạy cào chuỗi 12 chỉ báo kinh tế vĩ mô")
    args = parser.parse_args()

    crawler = MarketInsightsMasterCrawler()

    if args.all or not any([args.screener, args.valuation, args.breadth, args.sentiment, args.macro]):
        crawler.run_all()
    else:
        if args.screener:
            crawler.crawl_screener()
        if args.valuation:
            crawler.crawl_index_valuation()
        if args.breadth:
            crawler.crawl_market_breadth()
        if args.sentiment:
            crawler.crawl_market_sentiment()
        if args.macro:
            crawler.crawl_macro_series()
        crawler.writer.atomic_ingest_buffer()


if __name__ == "__main__":
    main()
