"""Comprehensive test script to crawl and verify all data for symbol 'VIC' across F001-F009."""
import os
import sys
import json
import pathlib
import datetime as dt

# Set UTF-8 encoding
sys.stdout.reconfigure(encoding="utf-8")

# Ensure VNSTOCK_API_KEY is populated from ~/.vnstock/api_key.json if not present
if not os.environ.get("VNSTOCK_API_KEY"):
    key_path = pathlib.Path.home() / ".vnstock" / "api_key.json"
    if key_path.exists():
        key_data = json.loads(key_path.read_text(encoding="utf-8"))
        os.environ["VNSTOCK_API_KEY"] = key_data.get("api_key", "")

# Add src to sys.path
sys.path.insert(0, str(pathlib.Path.cwd() / "src"))

from etl import db, adjustments, news_dedup
from etl.retry_failed_jobs import EmptyResultError
from crawlers import (
    dim_symbol,
    market_ohlcv,
    vnstock_news,
    cafef_news,
    fundamentals,
    corporate_events,
    snapshots,
)

TARGET_SYMBOL = "VIC"

def run_all_crawlers():
    con = db.bootstrap_schema()
    results = {}

    print(f"=== 1. Testing F001: Reference Crawler (dim_symbol) ===")
    try:
        n_dim = dim_symbol.run()
        vic_dim = con.execute("SELECT * FROM core.dim_symbol WHERE symbol = ?", [TARGET_SYMBOL]).df()
        results["dim_symbol"] = {
            "status": "success",
            "total_universe_rows": n_dim,
            "vic_found": not vic_dim.empty,
            "vic_data": vic_dim.to_dict(orient="records")[0] if not vic_dim.empty else None
        }
        print(f"  ✓ dim_symbol: wrote {n_dim} rows. VIC found: {not vic_dim.empty}")
    except Exception as e:
        results["dim_symbol"] = {"status": "error", "error": str(e)}
        print(f"  ✗ dim_symbol failed: {e}")

    print(f"\n=== 2. Testing F002: Market OHLCV Daily for {TARGET_SYMBOL} ===")
    try:
        # Crawling from 2024-01-01 to today
        today_str = dt.date.today().isoformat()
        n_ohlcv = market_ohlcv.run(TARGET_SYMBOL, start="2024-01-01", end=today_str)
        ohlcv_df = con.execute(
            "SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as cnt, AVG(close) as avg_close FROM core.market_ohlcv_daily WHERE symbol = ?",
            [TARGET_SYMBOL]
        ).df()
        sample_ohlcv = con.execute(
            "SELECT * FROM core.market_ohlcv_daily WHERE symbol = ? ORDER BY date DESC LIMIT 5",
            [TARGET_SYMBOL]
        ).df()
        results["market_ohlcv"] = {
            "status": "success",
            "rows_written": n_ohlcv,
            "date_range": {
                "min": str(ohlcv_df["min_date"].iloc[0]),
                "max": str(ohlcv_df["max_date"].iloc[0]),
                "count": int(ohlcv_df["cnt"].iloc[0]),
            },
            "sample": sample_ohlcv.to_dict(orient="records")
        }
        print(f"  ✓ market_ohlcv: wrote {n_ohlcv} rows ({ohlcv_df['min_date'].iloc[0]} to {ohlcv_df['max_date'].iloc[0]})")
    except Exception as e:
        results["market_ohlcv"] = {"status": "error", "error": str(e)}
        print(f"  ✗ market_ohlcv failed: {e}")

    print(f"\n=== 3. Testing F003: vnstock News for {TARGET_SYMBOL} ===")
    try:
        n_news_vnstock = vnstock_news.run(TARGET_SYMBOL)
        sample_vnstock = con.execute(
            "SELECT symbol, source, published_at, headline, source_url FROM core.news WHERE symbol = ? AND source = 'vnstock' ORDER BY published_at DESC LIMIT 3",
            [TARGET_SYMBOL]
        ).df()
        results["vnstock_news"] = {
            "status": "success",
            "rows_written": n_news_vnstock,
            "sample": sample_vnstock.to_dict(orient="records")
        }
        print(f"  ✓ vnstock_news: wrote {n_news_vnstock} rows")
    except EmptyResultError as e:
        results["vnstock_news"] = {"status": "empty", "message": str(e)}
        print(f"  ✓ vnstock_news returned empty (valid): {e}")
    except Exception as e:
        results["vnstock_news"] = {"status": "error", "error": str(e)}
        print(f"  ✗ vnstock_news failed: {e}")

    print(f"\n=== 4. Testing F004: CafeF News for {TARGET_SYMBOL} ===")
    try:
        n_news_cafef = cafef_news.run(TARGET_SYMBOL)
        sample_cafef = con.execute(
            "SELECT symbol, source, published_at, headline, source_url FROM core.news WHERE symbol = ? AND source = 'cafef' ORDER BY published_at DESC LIMIT 3",
            [TARGET_SYMBOL]
        ).df()
        results["cafef_news"] = {
            "status": "success",
            "rows_written": n_news_cafef,
            "sample": sample_cafef.to_dict(orient="records")
        }
        print(f"  ✓ cafef_news: wrote {n_news_cafef} rows")
    except Exception as e:
        results["cafef_news"] = {"status": "error", "error": str(e)}
        print(f"  ✗ cafef_news failed: {e}")

    print(f"\n=== 5. Testing F005: Fundamentals Suite for {TARGET_SYMBOL} ===")
    fund_results = {}
    for r_type in ["income_statement", "balance_sheet", "cash_flow", "ratio"]:
        try:
            n_f = fundamentals.run(TARGET_SYMBOL, report_type=r_type, period="quarter")
            periods = con.execute(
                "SELECT MIN(period_end) as min_p, MAX(period_end) as max_p, COUNT(*) as cnt FROM core.fundamentals WHERE symbol = ? AND report_type = ?",
                [TARGET_SYMBOL, r_type]
            ).df()
            fund_results[r_type] = {
                "status": "success",
                "rows_written": n_f,
                "period_min": str(periods["min_p"].iloc[0]),
                "period_max": str(periods["max_p"].iloc[0]),
                "count": int(periods["cnt"].iloc[0]),
            }
            print(f"  ✓ fundamentals ({r_type}): wrote {n_f} rows (range: {periods['min_p'].iloc[0]} to {periods['max_p'].iloc[0]})")
        except EmptyResultError as e:
            fund_results[r_type] = {
                "status": "empty (accepted API gap)",
                "message": str(e)
            }
            print(f"  ✓ fundamentals ({r_type}): empty response accepted per DECISIONS.md")
        except Exception as e:
            fund_results[r_type] = {"status": "error", "error": str(e)}
            print(f"  ✗ fundamentals ({r_type}) failed: {e}")
    results["fundamentals"] = fund_results

    print(f"\n=== 6. Testing F006: Corporate Events for {TARGET_SYMBOL} ===")
    try:
        n_events = corporate_events.run(TARGET_SYMBOL)
        events_df = con.execute(
            "SELECT event_type, COUNT(*) as cnt FROM core.corporate_events WHERE symbol = ? GROUP BY event_type",
            [TARGET_SYMBOL]
        ).df()
        sample_events = con.execute(
            "SELECT event_id, event_type, event_date, detail_json FROM core.corporate_events WHERE symbol = ? ORDER BY event_date DESC NULLS LAST LIMIT 3",
            [TARGET_SYMBOL]
        ).df()
        results["corporate_events"] = {
            "status": "success",
            "rows_written": n_events,
            "type_breakdown": events_df.to_dict(orient="records"),
            "sample": sample_events.to_dict(orient="records")
        }
        print(f"  ✓ corporate_events: wrote {n_events} rows. Breakdown: {events_df.to_dict(orient='records')}")
    except EmptyResultError as e:
        results["corporate_events"] = {"status": "empty", "message": str(e)}
        print(f"  ✓ corporate_events returned empty: {e}")
    except Exception as e:
        results["corporate_events"] = {"status": "error", "error": str(e)}
        print(f"  ✗ corporate_events failed: {e}")

    print(f"\n=== 7. Testing F007: Realtime Price Board Snapshot for [{TARGET_SYMBOL}] ===")
    try:
        n_snap = snapshots.run([TARGET_SYMBOL])
        latest_snap = con.execute(
            "SELECT symbol, snapshot_at, data_json, fetched_at FROM core.realtime_quote_snapshot WHERE symbol = ? ORDER BY snapshot_at DESC LIMIT 1",
            [TARGET_SYMBOL]
        ).df()
        data_json_parsed = json.loads(latest_snap["data_json"].iloc[0]) if not latest_snap.empty else {}
        results["realtime_snapshot"] = {
            "status": "success",
            "rows_written": n_snap,
            "snapshot_at": str(latest_snap["snapshot_at"].iloc[0]) if not latest_snap.empty else None,
            "key_metrics": {
                "listing_symbol": data_json_parsed.get("listing_symbol"),
                "listing_ceiling": data_json_parsed.get("listing_ceiling"),
                "listing_floor": data_json_parsed.get("listing_floor"),
                "listing_ref_price": data_json_parsed.get("listing_ref_price"),
                "match_match_price": data_json_parsed.get("match_match_price"),
                "match_accumulated_volume": data_json_parsed.get("match_accumulated_volume"),
                "match_highest": data_json_parsed.get("match_highest"),
                "match_lowest": data_json_parsed.get("match_lowest"),
                "bid_1_price": data_json_parsed.get("bid_ask_bid_1_price"),
                "ask_1_price": data_json_parsed.get("bid_ask_ask_1_price"),
            }
        }
        print(f"  ✓ realtime_snapshot: wrote {n_snap} row(s). Match price: {data_json_parsed.get('match_match_price')}")
    except Exception as e:
        results["realtime_snapshot"] = {"status": "error", "error": str(e)}
        print(f"  ✗ realtime_snapshot failed: {e}")

    print(f"\n=== 8. Testing F009: News Dedup & Price Adjustments for {TARGET_SYMBOL} ===")
    try:
        # Run news dedup
        n_flagged = news_dedup.run_dedup_for_symbol(TARGET_SYMBOL, con)
        print(f"  ✓ news_dedup executed: flagged {n_flagged} duplicates for {TARGET_SYMBOL}")
        
        # Run price adjustments
        events_df = con.execute("SELECT * FROM core.corporate_events WHERE symbol = ?", [TARGET_SYMBOL]).df()
        ohlcv_df = con.execute("SELECT * FROM core.market_ohlcv_daily WHERE symbol = ?", [TARGET_SYMBOL]).df()
        adj_events = adjustments.compute_adjustment_events(events_df, ohlcv_df, TARGET_SYMBOL)
        n_adj = adjustments.write_adjustment_events(adj_events, TARGET_SYMBOL, con)
        adj_sample = con.execute(
            "SELECT * FROM core.price_adjustment_events WHERE symbol = ? ORDER BY ex_date DESC LIMIT 5",
            [TARGET_SYMBOL]
        ).df()
        results["f009_post_processing"] = {
            "news_dedup_flagged": n_flagged,
            "price_adjustment_events_written": n_adj,
            "adjustment_sample": adj_sample.to_dict(orient="records")
        }
        print(f"  ✓ price_adjustments: wrote {n_adj} adjustment events for {TARGET_SYMBOL}")
    except Exception as e:
        results["f009_post_processing"] = {"status": "error", "error": str(e)}
        print(f"  ✗ F009 post-processing failed: {e}")

    # Write full output to scratch/vic_crawl_report.json
    out_file = pathlib.Path.cwd() / "scratch" / "vic_crawl_report.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n✓ Full report saved to {out_file}")

if __name__ == "__main__":
    run_all_crawlers()
