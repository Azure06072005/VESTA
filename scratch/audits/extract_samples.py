"""Extract 1 sample record from every single dataset table in VESTA DuckDB."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "d:/VESTA/db/vesta.duckdb"

def default_serializer(obj):
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    return str(obj)

def get_samples():
    con = duckdb.connect(DB_PATH, read_only=True)
    samples = {}

    queries = {
        "core.dim_symbol": "SELECT * FROM core.dim_symbol WHERE symbol = 'FPT' LIMIT 1",
        "core.dim_symbol_cafef": "SELECT * FROM core.dim_symbol_cafef LIMIT 1",
        "core.market_ohlcv_daily": "SELECT * FROM core.market_ohlcv_daily WHERE symbol = 'FPT' AND date = '2026-09-04' LIMIT 1",
        "core.market_index_daily": "SELECT * FROM core.market_index_daily WHERE index_code = 'VNINDEX' ORDER BY date DESC LIMIT 1",
        "core.market_foreign_flow_daily": "SELECT * FROM core.market_foreign_flow_daily WHERE symbol = 'HPG' ORDER BY date DESC LIMIT 1",
        "core.news_vnstock": "SELECT * FROM core.news WHERE source_url LIKE 'vnstock://%' AND symbol = 'FPT' ORDER BY published_at DESC LIMIT 1",
        "core.news_cafef": "SELECT * FROM core.news WHERE source_url LIKE 'https://cafef.vn%' AND symbol = 'HPG' ORDER BY published_at DESC LIMIT 1",
        "core.fundamentals_balance_sheet": "SELECT * FROM core.fundamentals WHERE symbol = 'HPG' AND report_type = 'balance_sheet' ORDER BY period_end DESC LIMIT 1",
        "core.fundamentals_income_statement": "SELECT * FROM core.fundamentals WHERE symbol = 'FPT' AND report_type = 'income_statement' ORDER BY period_end DESC LIMIT 1",
        "core.fundamentals_cash_flow": "SELECT * FROM core.fundamentals WHERE symbol = 'VCB' AND report_type = 'cash_flow' ORDER BY period_end DESC LIMIT 1",
        "core.fundamentals_ratio": "SELECT * FROM core.fundamentals WHERE symbol = 'VNM' AND report_type = 'ratio' ORDER BY period_end DESC LIMIT 1",
        "core.corporate_events_dividend": "SELECT * FROM core.corporate_events WHERE event_type = 'DIVIDEND' AND symbol = 'FPT' ORDER BY event_date DESC LIMIT 1",
        "core.corporate_events_trading": "SELECT * FROM core.corporate_events WHERE event_type = 'MAJOR_SHAREHOLDER_TRADING' AND symbol = 'HPG' ORDER BY event_date DESC LIMIT 1",
        "core.corporate_events_meeting": "SELECT * FROM core.corporate_events WHERE event_type = 'SHAREHOLDER_MEETING' AND symbol = 'MWG' ORDER BY event_date DESC LIMIT 1",
        "core.realtime_quote_snapshot": "SELECT * FROM core.realtime_quote_snapshot WHERE symbol = 'FPT' LIMIT 1",
        "core.stock_research_reports": "SELECT * FROM core.stock_research_reports WHERE recommendation IS NOT NULL AND target_price IS NOT NULL ORDER BY report_date DESC LIMIT 1",
        "core.macro_policy_baochinhphu": "SELECT * FROM core.macro_policy WHERE source = 'baochinhphu' ORDER BY published_at DESC LIMIT 1",
        "core.macro_policy_worldbank": "SELECT * FROM core.macro_policy WHERE source = 'worldbank' ORDER BY published_at DESC LIMIT 1",
        "meta.crawl_progress": "SELECT * FROM meta.crawl_progress WHERE status = 'success' LIMIT 1",
    }

    for key, q in queries.items():
        try:
            cur = con.execute(q)
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            if row:
                d_row = dict(zip(cols, row))
                # If json field, parse for nicer display
                for fld in ['data_json', 'detail_json']:
                    if fld in d_row and isinstance(d_row[fld], str):
                        try:
                            d_row[fld] = json.loads(d_row[fld])
                        except Exception:
                            pass
                samples[key] = d_row
            else:
                samples[key] = None
        except Exception as e:
            samples[key] = {"error": str(e)}

    con.close()

    out_file = "d:/VESTA/out/all_dataset_samples.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, default=default_serializer, ensure_ascii=False)
    print(f"Extracted {len(samples)} samples to {out_file}")

if __name__ == "__main__":
    get_samples()
