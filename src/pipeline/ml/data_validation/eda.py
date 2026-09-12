"""
src/etl/eda.py — Comprehensive EDA & Profiling across all VESTA datasets.

Follows the project's data-exploration profiling framework:
  1. Table-level overview (schema, row count, column types)
  2. Null-rate and cardinality profiling
  3. Numeric and distribution statistics (mean, stddev, quantiles, zeros, negatives)
  4. Dataset-specific sanity & data-quality invariant checks

This script is READ-ONLY and additive. It does not mutate any tables.
Per Rule B3 (Numbers need a source): execute this script against the real
database to produce out/eda_full_report.json before drafting narrative findings.

Usage:
    python src/etl/eda.py --db db/vesta.duckdb --out-json out/eda_full_report.json
    # or if vesta.duckdb is locked by a writer:
    python src/etl/eda.py --db db/vesta_latest_backup.duckdb --out-json out/eda_full_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import duckdb


# =============================================================================
# Generic profiling helpers (shared across every dataset)
# =============================================================================

def table_overview(con: duckdb.DuckDBPyConnection, table: str) -> dict:
    """Return row count and column schema metadata for a table."""
    try:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        cols = con.execute(f"DESCRIBE {table}").fetchdf()
        return {
            "table": table,
            "row_count": int(n),
            "columns": cols.to_dict(orient="records"),
        }
    except Exception as e:
        return {"table": table, "error": str(e)}


def null_and_cardinality(con: duckdb.DuckDBPyConnection, table: str,
                          columns: list[str]) -> dict:
    """Compute null rates and distinct counts in a single vectorized SQL query."""
    n_total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if n_total == 0:
        return {col: {"null_count": 0, "null_rate": 0.0, "distinct_count": 0, "cardinality_ratio": 0.0} for col in columns}

    select_items = []
    for col in columns:
        select_items.append(f"COUNT(*) FILTER (WHERE {col} IS NULL) AS null_{col}")
        select_items.append(f"COUNT(DISTINCT {col}) AS dist_{col}")

    query = f"SELECT {', '.join(select_items)} FROM {table}"
    row = con.execute(query).fetchone()

    report = {}
    idx = 0
    for col in columns:
        n_null = int(row[idx])
        n_distinct = int(row[idx + 1])
        report[col] = {
            "null_count": n_null,
            "null_rate": round(n_null / n_total, 6),
            "distinct_count": n_distinct,
            "cardinality_ratio": round(n_distinct / n_total, 6),
        }
        idx += 2
    return report


def numeric_profile(con: duckdb.DuckDBPyConnection, table: str, expr: str,
                     where: str = "TRUE") -> dict:
    """Compute summary statistics for a numeric expression."""
    row = con.execute(f"""
        SELECT MIN({expr}), MAX({expr}), AVG({expr}), STDDEV({expr}),
               APPROX_QUANTILE({expr}, 0.01), APPROX_QUANTILE({expr}, 0.25),
               APPROX_QUANTILE({expr}, 0.50), APPROX_QUANTILE({expr}, 0.75),
               APPROX_QUANTILE({expr}, 0.99),
               COUNT(*) FILTER (WHERE {expr} = 0),
               COUNT(*) FILTER (WHERE {expr} < 0)
        FROM {table} WHERE {where}
    """).fetchone()
    keys = ["min", "max", "mean", "stddev", "p1", "p25", "p50", "p75", "p99",
            "zero_count", "negative_count"]
    return dict(zip(keys, [float(v) if v is not None else None for v in row]))


def top_values(con: duckdb.DuckDBPyConnection, table: str, column: str,
               n: int = 10, where: str = "TRUE") -> list[dict]:
    """Retrieve the top N frequent values and their frequencies."""
    return con.execute(f"""
        SELECT {column} AS value, COUNT(*) AS n
        FROM {table} WHERE {where}
        GROUP BY {column} ORDER BY n DESC LIMIT {n}
    """).fetchdf().to_dict(orient="records")


def date_range(con: duckdb.DuckDBPyConnection, table: str, column: str) -> dict:
    """Compute min, max, and future timestamp counts for a date/timestamp column."""
    lo, hi, future_n = con.execute(f"""
        SELECT MIN({column}), MAX({column}),
               COUNT(*) FILTER (WHERE {column} > NOW())
        FROM {table}
    """).fetchone()
    return {"min": str(lo), "max": str(hi), "future_count": int(future_n or 0)}


# =============================================================================
# Per-dataset EDA functions (All 12 Core & Meta VESTA Datasets)
# =============================================================================

def eda_dim_symbol(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.dim_symbol"
    dup = con.execute(f"""
        SELECT COUNT(*) FROM (SELECT symbol, COUNT(*) c FROM {t}
        GROUP BY symbol HAVING c > 1)
    """).fetchone()[0]
    return {
        "overview": table_overview(con, t),
        "nulls_and_cardinality": null_and_cardinality(
            con, t, ["symbol", "organ_name", "exchange", "industry_code", "delisted_date", "is_delisted"]),
        "exchange_distribution": top_values(con, t, "exchange"),
        "industry_distribution": top_values(con, t, "industry_name", n=25),
        "duplicate_symbol_rows": int(dup),
        "expected_finding_to_confirm":
            "delisted_date null_rate is expected to be 1.0 (F001 accepted gap per DECISIONS.md). "
            "is_delisted flags active vs delisted equity status.",
    }


def eda_dim_symbol_cafef(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.dim_symbol_cafef"
    overlap = con.execute(f"""
        SELECT COUNT(*) FROM {t} c JOIN core.dim_symbol d ON c.symbol = d.symbol
    """).fetchone()[0]
    return {
        "overview": table_overview(con, t),
        "nulls_and_cardinality": null_and_cardinality(
            con, t, ["symbol", "org_name", "exchange", "center_id"]),
        "exchange_distribution": top_values(con, t, "exchange"),
        "is_vn30_distribution": top_values(con, t, "is_vn30"),
        "is_hnx30_distribution": top_values(con, t, "is_hnx30"),
        "symbol_overlap_with_dim_symbol": int(overlap),
        "expected_finding_to_confirm":
            "F001b OTC/unlisted directory. Overlap with dim_symbol confirms consistency on listed tickers.",
    }


def eda_market_ohlcv_daily(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.market_ohlcv_daily"
    geom = con.execute(f"""
        SELECT COUNT(*) FILTER (WHERE high < low) AS high_lt_low,
               COUNT(*) FILTER (WHERE high < open OR high < close) AS high_lt_oc,
               COUNT(*) FILTER (WHERE low > open OR low > close) AS low_gt_oc,
               COUNT(*) FILTER (WHERE close = 0) AS zero_close,
               COUNT(*) FILTER (WHERE volume = 0) AS zero_volume
        FROM {t}
    """).fetchone()
    dup_pk = con.execute(f"""
        SELECT COUNT(*) FROM (SELECT symbol, date, COUNT(*) c FROM {t}
        GROUP BY symbol, date HAVING c > 1)
    """).fetchone()[0]
    spikes = con.execute(f"""
        WITH r AS (
          SELECT symbol, date, close,
                 close / NULLIF(LAG(close) OVER (PARTITION BY symbol ORDER BY date), 0) - 1 AS ret
          FROM {t}
        )
        SELECT COUNT(*) FILTER (WHERE ret > 3.0), COUNT(*) FILTER (WHERE ret < -0.8)
        FROM r
    """).fetchone()
    per_symbol = con.execute(f"""
        SELECT symbol, COUNT(*) n, MIN(date) first_date, MAX(date) last_date
        FROM {t} GROUP BY symbol ORDER BY n DESC LIMIT 5
    """).fetchdf()
    thinnest_symbols = con.execute(f"""
        SELECT symbol, COUNT(*) n FROM {t} GROUP BY symbol ORDER BY n ASC LIMIT 10
    """).fetchdf()
    return {
        "overview": table_overview(con, t),
        "date_range": date_range(con, t, "date"),
        "nulls_and_cardinality": null_and_cardinality(
            con, t, ["symbol", "date", "open", "high", "low", "close", "volume"]),
        "close_price_profile": numeric_profile(con, t, "close"),
        "volume_profile": numeric_profile(con, t, "volume"),
        "candlestick_geometry_violations": dict(zip(
            ["high_lt_low", "high_lt_open_or_close", "low_gt_open_or_close",
             "zero_close_rows", "zero_volume_rows"], geom)),
        "duplicate_pk_symbol_date_rows": int(dup_pk),
        "extreme_return_spikes": {"gt_300pct_up": int(spikes[0] or 0), "lt_80pct_down": int(spikes[1] or 0)},
        "top_5_symbols_by_row_count": per_symbol.to_dict(orient="records"),
        "10_thinnest_coverage_symbols": thinnest_symbols.to_dict(orient="records"),
    }


def eda_news(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.news"
    dup_url = con.execute(f"""
        SELECT COUNT(*) FROM (SELECT source_url, COUNT(*) c FROM {t}
        WHERE duplicate_of IS NULL GROUP BY source_url HAVING c > 1)
    """).fetchone()[0]
    hlen = con.execute(f"SELECT MIN(LENGTH(headline)), MAX(LENGTH(headline)), AVG(LENGTH(headline)) FROM {t}").fetchone()
    hour_dist = con.execute(f"""
        SELECT EXTRACT(HOUR FROM published_at) AS hr, COUNT(*) n
        FROM {t} GROUP BY hr ORDER BY hr
    """).fetchdf()
    orphans = con.execute(f"""
        SELECT COUNT(DISTINCT n.symbol) FROM {t} n
        LEFT JOIN core.dim_symbol d ON n.symbol = d.symbol
        LEFT JOIN core.dim_symbol_cafef c ON n.symbol = c.symbol
        WHERE d.symbol IS NULL AND c.symbol IS NULL AND n.symbol IS NOT NULL
    """).fetchone()[0]
    return {
        "overview": table_overview(con, t),
        "published_at_range": date_range(con, t, "published_at"),
        "nulls_and_cardinality": null_and_cardinality(
            con, t, ["symbol", "source", "published_at", "headline", "body",
                      "source_url", "duplicate_of"]),
        "source_distribution": top_values(con, t, "source"),
        "duplicate_primary_source_url_rows": int(dup_url),
        "headline_length_chars": {"min": hlen[0], "max": hlen[1], "avg": round(hlen[2] or 0, 1)},
        "published_hour_of_day_distribution": hour_dist.to_dict(orient="records"),
        "orphan_symbols_not_in_any_dim_table": int(orphans),
    }


def eda_fundamentals(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.fundamentals"
    report_types = con.execute(f"SELECT DISTINCT report_type FROM {t}").fetchdf()["report_type"].tolist()
    per_type = {}
    for rt in report_types:
        where = f"report_type = '{rt}'"
        n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE {where}").fetchone()[0]
        dmin, dmax = con.execute(f"SELECT MIN(period_end), MAX(period_end) FROM {t} WHERE {where}").fetchone()
        lag_avg, lag_min, lag_max = con.execute(f"""
            SELECT AVG(DATE_DIFF('day', period_end, available_at)),
                   MIN(DATE_DIFF('day', period_end, available_at)),
                   MAX(DATE_DIFF('day', period_end, available_at))
            FROM {t} WHERE {where}
        """).fetchone()
        empty_json = con.execute(f"""
            SELECT COUNT(*) FROM {t} WHERE {where}
              AND (data_json IS NULL OR CAST(data_json AS VARCHAR) IN ('{{}}', 'null', ''))
        """).fetchone()[0]
        dup_key = con.execute(f"""
            SELECT COUNT(*) FROM (
              SELECT symbol, report_type, period_end, fetched_at, COUNT(*) c
              FROM {t} WHERE {where}
              GROUP BY symbol, report_type, period_end, fetched_at HAVING c > 1)
        """).fetchone()[0]
        per_type[rt] = {
            "row_count": int(n),
            "period_end_range": [str(dmin), str(dmax)],
            "available_at_minus_period_end_days": {
                "avg": round(lag_avg, 2) if lag_avg is not None else None,
                "min": lag_min,
                "max": lag_max
            },
            "empty_data_json_rows": int(empty_json),
            "duplicate_pk_rows": int(dup_key),
        }
    return {
        "overview": table_overview(con, t),
        "per_report_type": per_type,
        "source_distribution": top_values(con, t, "source"),
    }


def eda_corporate_events(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.corporate_events"
    dup_id = con.execute(f"""
        SELECT COUNT(*) FROM (SELECT event_id, COUNT(*) c FROM {t}
        GROUP BY event_id HAVING c > 1)
    """).fetchone()[0]
    return {
        "overview": table_overview(con, t),
        "event_date_range": date_range(con, t, "event_date"),
        "nulls_and_cardinality": null_and_cardinality(
            con, t, ["symbol", "event_id", "event_type", "event_date", "detail_json"]),
        "event_type_distribution": top_values(con, t, "event_type"),
        "duplicate_event_id_rows": int(dup_id),
    }


def eda_pit_events(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.pit_events"
    dup_pk = con.execute(f"""
        SELECT COUNT(*) FROM (SELECT symbol, source_url, COUNT(*) c FROM {t}
        GROUP BY symbol, source_url HAVING c > 1)
    """).fetchone()[0]
    after_close = con.execute(f"""
        SELECT COUNT(*) FROM {t}
        WHERE EXTRACT(HOUR FROM published_at) >= 15 AND price_at_publish IS NOT NULL
    """).fetchone()[0]
    returns = {}
    for horizon in ["t1", "t5", "t30"]:
        expr = f"(price_{horizon} - price_at_publish) / NULLIF(price_at_publish, 0)"
        returns[horizon] = numeric_profile(con, t, expr, where=f"price_{horizon} IS NOT NULL AND price_at_publish IS NOT NULL")
    fill_rates = null_and_cardinality(
        con, t, ["sentiment", "price_t1", "price_t5", "price_t30", "fundamentals_json"])
    return {
        "overview": table_overview(con, t),
        "published_at_range": date_range(con, t, "published_at"),
        "duplicate_pk_symbol_source_url_rows": int(dup_pk),
        "fill_rates": fill_rates,
        "post_market_close_events_with_price_at_publish_filled": int(after_close),
        "note_on_after_close_count":
            "Confirm price_at_publish for these rows aligns with T+1 session, per F102 look-ahead bias test.",
        "return_distributions": returns,
    }


def eda_macro_policy(con: duckdb.DuckDBPyConnection) -> dict:
    """EDA for core.macro_policy (Regulatory, Ministry, Central Bank, and Press archives)."""
    t = "core.macro_policy"
    dup_url = con.execute(f"""
        SELECT COUNT(*) FROM (SELECT source_url, COUNT(*) c FROM {t}
        GROUP BY source_url HAVING c > 1)
    """).fetchone()[0]
    body_profile = numeric_profile(con, t, "LENGTH(body)", where="body IS NOT NULL")
    return {
        "overview": table_overview(con, t),
        "published_at_range": date_range(con, t, "published_at"),
        "nulls_and_cardinality": null_and_cardinality(
            con, t, ["source", "issuing_body", "doc_type", "doc_number", "headline", "body", "source_url"]),
        "source_distribution": top_values(con, t, "source", n=15),
        "issuing_body_distribution": top_values(con, t, "issuing_body", n=15),
        "doc_type_distribution": top_values(con, t, "doc_type", n=10),
        "body_length_profile": body_profile,
        "duplicate_source_url_rows": int(dup_url),
    }


def eda_realtime_quote_snapshot(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.realtime_quote_snapshot"
    dup_pk = con.execute(f"""
        SELECT COUNT(*) FROM (SELECT symbol, snapshot_at, COUNT(*) c FROM {t}
        GROUP BY symbol, snapshot_at HAVING c > 1)
    """).fetchone()[0]
    return {
        "overview": table_overview(con, t),
        "snapshot_at_range": date_range(con, t, "snapshot_at"),
        "nulls_and_cardinality": null_and_cardinality(con, t, ["symbol", "snapshot_at", "data_json"]),
        "duplicate_pk_rows": int(dup_pk),
        "symbol_count": con.execute(f"SELECT COUNT(DISTINCT symbol) FROM {t}").fetchone()[0],
    }


def eda_price_adjustment_events(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.price_adjustment_events"
    dup_pk = con.execute(f"""
        SELECT COUNT(*) FROM (SELECT symbol, ex_date, source_event_id, COUNT(*) c FROM {t}
        GROUP BY symbol, ex_date, source_event_id HAVING c > 1)
    """).fetchone()[0]
    return {
        "overview": table_overview(con, t),
        "nulls_and_cardinality": null_and_cardinality(
            con, t, ["symbol", "ex_date", "adjustment_type", "multiplier", "source_event_id"]),
        "adjustment_type_distribution": top_values(con, t, "adjustment_type"),
        "multiplier_profile": numeric_profile(con, t, "multiplier") if con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] > 0 else {},
        "duplicate_pk_rows": int(dup_pk),
    }


def eda_stock_research_reports(con: duckdb.DuckDBPyConnection) -> dict:
    t = "core.stock_research_reports"
    dup_id = con.execute(f"""
        SELECT COUNT(*) FROM (SELECT report_id, COUNT(*) c FROM {t}
        GROUP BY report_id HAVING c > 1)
    """).fetchone()[0]
    return {
        "overview": table_overview(con, t),
        "report_date_range": date_range(con, t, "report_date"),
        "nulls_and_cardinality": null_and_cardinality(
            con, t, ["report_id", "symbol", "broker", "title", "recommendation", "target_price", "upside_pct"]),
        "recommendation_distribution": top_values(con, t, "recommendation"),
        "broker_distribution": top_values(con, t, "broker", n=10),
        "upside_pct_profile": numeric_profile(con, t, "upside_pct", where="upside_pct IS NOT NULL"),
        "duplicate_report_id_rows": int(dup_id),
    }


def eda_crawl_progress(con: duckdb.DuckDBPyConnection) -> dict:
    t = "meta.crawl_progress"
    by_dataset = con.execute(f"""
        SELECT dataset_name, status, COUNT(*) n FROM {t}
        GROUP BY dataset_name, status ORDER BY dataset_name, status
    """).fetchdf()
    return {
        "overview": table_overview(con, t),
        "status_distribution": top_values(con, t, "status"),
        "by_dataset_and_status": by_dataset.to_dict(orient="records"),
        "retry_count_profile": numeric_profile(con, t, "retry_count"),
    }


# =============================================================================
# Dataset Registry (12 Core & Meta Datasets)
# =============================================================================

DATASETS = {
    "core.dim_symbol": eda_dim_symbol,
    "core.dim_symbol_cafef": eda_dim_symbol_cafef,
    "core.market_ohlcv_daily": eda_market_ohlcv_daily,
    "core.news": eda_news,
    "core.fundamentals": eda_fundamentals,
    "core.corporate_events": eda_corporate_events,
    "core.pit_events": eda_pit_events,
    "core.macro_policy": eda_macro_policy,
    "core.realtime_quote_snapshot": eda_realtime_quote_snapshot,
    "core.price_adjustment_events": eda_price_adjustment_events,
    "core.stock_research_reports": eda_stock_research_reports,
    "meta.crawl_progress": eda_crawl_progress,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="VESTA Comprehensive Dataset EDA Profiler")
    parser.add_argument("--db", default="db/vesta.duckdb", help="Path to DuckDB database file")
    parser.add_argument("--out-json", default="out/eda_full_report.json", help="Path to export report JSON")
    args = parser.parse_args()

    db_path = args.db
    # If the requested db file does not exist or is locked, check backup
    if not os.path.exists(db_path):
        alt_db = "db/vesta_latest_backup.duckdb"
        if os.path.exists(alt_db):
            print(f"Warning: {db_path} not found. Falling back to {alt_db}.")
            db_path = alt_db
        else:
            print(f"Error: DuckDB file {db_path} does not exist.", file=sys.stderr)
            sys.exit(1)

    print(f"Connecting to DuckDB at {db_path} (read_only=True)...")
    try:
        con = duckdb.connect(db_path, read_only=True)
    except Exception as e:
        print(f"Failed to connect to {db_path}: {e}")
        # Try fallback if primary was locked
        alt_db = "db/vesta_latest_backup.duckdb"
        if db_path != alt_db and os.path.exists(alt_db):
            print(f"Attempting fallback to {alt_db}...")
            con = duckdb.connect(alt_db, read_only=True)
            db_path = alt_db
        else:
            sys.exit(1)

    report = {"meta": {"db_path": db_path, "total_datasets": len(DATASETS)}, "datasets": {}}
    for name, fn in DATASETS.items():
        print(f"Profiling {name} ...", flush=True)
        try:
            report["datasets"][name] = fn(con)
            print(f"  [OK] {name}")
        except Exception as e:
            report["datasets"][name] = {"error": str(e)}
            print(f"  [FAILED] {name}: {e}")

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[DONE] Full EDA profiling report written to {out_path.resolve()}")


if __name__ == "__main__":
    main()