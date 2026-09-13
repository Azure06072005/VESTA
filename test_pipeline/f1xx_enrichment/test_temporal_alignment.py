"""test_pipeline/f1xx_enrichment/test_temporal_alignment.py

Comprehensive Loop-Engineering Evaluation for 1. Temporal Alignment.
Audits:
1.1 Event Timestamp & Trading Session Alignment (Midnight 00:00:00 & After-Hours)
1.2 Fundamental Disclosure Lag (Point-in-Time Accounting & Look-ahead Check)
1.3 Forward Horizon Price Anchoring (T+1, T+5, T+30 Integrity, Zero-Prices, Rollovers)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import duckdb
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

def audit_subsequence_1_1_event_session(con: duckdb.DuckDBPyConnection) -> dict:
    """Audit 1.1: Event Timestamp and Trading Session Alignment."""
    print("\n" + "="*70)
    print(">>> 1.1 AUDIT: EVENT TIMESTAMP & TRADING SESSION ALIGNMENT <<<")
    print("="*70)
    
    # Analyze published_at timestamps in core.pit_events
    query = """
    SELECT 
        COUNT(*) as total_events,
        COUNT(CASE WHEN date_part('hour', published_at) = 0 AND date_part('minute', published_at) = 0 AND date_part('second', published_at) = 0 THEN 1 END) as midnight_count,
        COUNT(CASE WHEN date_part('hour', published_at) >= 15 THEN 1 END) as after_close_count,
        COUNT(CASE WHEN date_part('hour', published_at) >= 9 AND (date_part('hour', published_at) < 14 OR (date_part('hour', published_at) = 14 AND date_part('minute', published_at) <= 45)) THEN 1 END) as trading_hours_count,
        COUNT(CASE WHEN date_part('dow', published_at) IN (0, 6) THEN 1 END) as weekend_count
    FROM core.pit_events
    """
    row = con.execute(query).fetchone()
    total, midnight, after_close, trading_hours, weekend = row
    
    # Calculate percentages
    pct_midnight = (midnight / total) * 100 if total else 0
    pct_after_close = (after_close / total) * 100 if total else 0
    pct_trading_hours = (trading_hours / total) * 100 if total else 0
    pct_weekend = (weekend / total) * 100 if total else 0
    
    print(f"Total PIT Events:             {total:,}")
    print(f"Midnight timestamps (00:00:00): {midnight:,} ({pct_midnight:.2f}%)  <-- POTENTIAL LOOK-AHEAD RISK")
    print(f"After-market close (>=15:00):   {after_close:,} ({pct_after_close:.2f}%)")
    print(f"During trading hours (9:00-14:45): {trading_hours:,} ({pct_trading_hours:.2f}%)")
    print(f"Weekend publications (Sat/Sun): {weekend:,} ({pct_weekend:.2f}%)")
    
    # Check effective base_date mapping for midnight timestamps
    # Sample 5,000 midnight rows and compare published_at date vs actual price date
    sample_query = """
    SELECT p.symbol, p.published_at, p.price_at_publish, o.date as price_date, o.close as ohlcv_close
    FROM core.pit_events p
    JOIN core.market_ohlcv_daily o 
      ON p.symbol = o.symbol AND p.price_at_publish = o.close
    WHERE date_part('hour', p.published_at) = 0 
      AND date_part('minute', p.published_at) = 0 
      AND date_part('second', p.published_at) = 0
      AND p.price_at_publish IS NOT NULL
    LIMIT 1000
    """
    sample_df = con.execute(sample_query).df()
    
    same_day_midnight = 0
    next_day_midnight = 0
    if not sample_df.empty:
        for _, r in sample_df.iterrows():
            pub_date = r["published_at"].date()
            price_date = pd.Timestamp(r["price_date"]).date()
            if price_date == pub_date:
                same_day_midnight += 1
            elif price_date > pub_date:
                next_day_midnight += 1
                
    same_day_pct = (same_day_midnight / len(sample_df) * 100) if len(sample_df) else 0
    print(f"\n[Midnight Anchor Diagnostic on {len(sample_df):,} samples]:")
    print(f"  - Anchored to SAME-DAY close (T+0): {same_day_midnight} ({same_day_pct:.1f}%)")
    print(f"  - Anchored to NEXT-DAY close (T+1): {next_day_midnight} ({100-same_day_pct:.1f}%)")
    if same_day_pct > 0:
        print("  ⚠️ CRITICAL FINDING: Midnight 00:00:00 timestamps are currently anchored to SAME-DAY close.")
        print("    If a news item was published in the evening (e.g. 18:00) but crawled with 00:00:00,")
        print("    using T+0 close price introduces look-ahead bias (trading before publication).")
        
    return {
        "total": total,
        "midnight_count": midnight,
        "midnight_pct": pct_midnight,
        "after_close_pct": pct_after_close,
        "trading_hours_pct": pct_trading_hours,
        "weekend_pct": pct_weekend,
        "same_day_midnight_pct": same_day_pct,
    }


def audit_subsequence_1_2_fundamentals_lag(con: duckdb.DuckDBPyConnection) -> dict:
    """Audit 1.2: Fundamental Disclosure Lag and Point-in-Time Accounting Alignment."""
    print("\n" + "="*70)
    print(">>> 1.2 AUDIT: FUNDAMENTAL DISCLOSURE LAG & LOOK-AHEAD GATE <<<")
    print("="*70)
    
    # Check pit_events with fundamental attachments
    total_with_fund = con.execute("""
        SELECT COUNT(*) 
        FROM core.pit_events 
        WHERE fundamentals_json IS NOT NULL AND fundamentals_json != '{}'
    """).fetchone()[0]
    
    total_events = con.execute("SELECT COUNT(*) FROM core.pit_events").fetchone()[0]
    pct_fund = (total_with_fund / total_events) * 100 if total_events else 0
    print(f"PIT Events with Fundamental data: {total_with_fund:,} / {total_events:,} ({pct_fund:.2f}%)")
    
    # Check fundamentals table for available_at vs period_end
    fund_stats = con.execute("""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(CASE WHEN available_at IS NULL THEN 1 END) as null_available_at,
            COUNT(CASE WHEN available_at < period_end THEN 1 END) as available_before_period_end,
            AVG(date_diff('day', period_end, available_at)) as avg_lag_days,
            MIN(date_diff('day', period_end, available_at)) as min_lag_days,
            MAX(date_diff('day', period_end, available_at)) as max_lag_days
        FROM core.fundamentals
    """).fetchone()
    
    print(f"Total rows in core.fundamentals:  {fund_stats[0]:,}")
    print(f"Null available_at count:          {fund_stats[1]}")
    print(f"available_at < period_end (ILLEGAL): {fund_stats[2]} (Must be 0)")
    print(f"Average disclosure lag:           {fund_stats[3]:.1f} days")
    print(f"Min / Max disclosure lag:         {fund_stats[4]} days / {fund_stats[5]} days")
    
    # Check for actual look-ahead in pit_events join
    # An event at published_at must NOT use a fundamental row where published_at < available_at
    fund_leakage_query = """
    SELECT COUNT(*) 
    FROM core.pit_events p
    WHERE p.fundamentals_as_of IS NOT NULL 
      AND p.published_at < p.fundamentals_as_of
    """
    leakage_count = con.execute(fund_leakage_query).fetchone()[0]
    print(f"Events where published_at < fundamentals_as_of (Look-ahead violation): {leakage_count}")
    
    return {
        "total_with_fund": total_with_fund,
        "fund_coverage_pct": pct_fund,
        "null_available_at": fund_stats[1],
        "illegal_period_end_count": fund_stats[2],
        "avg_lag_days": float(fund_stats[3]) if fund_stats[3] else 0,
        "leakage_count": leakage_count,
    }


def audit_subsequence_1_3_forward_horizons(con: duckdb.DuckDBPyConnection) -> dict:
    """Audit 1.3: Forward Price Horizons (T+1, T+5, T+30) and Zero/Suspension Traps."""
    print("\n" + "="*70)
    print(">>> 1.3 AUDIT: FORWARD HORIZON INTEGRITY & PRICE ANCHORS <<<")
    print("="*70)
    
    q = """
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN price_at_publish IS NULL THEN 1 END) as null_publish,
        COUNT(CASE WHEN price_at_publish <= 0 THEN 1 END) as zero_publish,
        COUNT(CASE WHEN price_t1 IS NOT NULL THEN 1 END) as t1_count,
        COUNT(CASE WHEN price_t5 IS NOT NULL THEN 1 END) as t5_count,
        COUNT(CASE WHEN price_t30 IS NOT NULL THEN 1 END) as t30_count,
        COUNT(CASE WHEN price_t1 <= 0 THEN 1 END) as zero_t1,
        COUNT(CASE WHEN price_t5 <= 0 THEN 1 END) as zero_t5,
        COUNT(CASE WHEN price_t30 <= 0 THEN 1 END) as zero_t30,
        COUNT(CASE WHEN price_t1 = price_at_publish THEN 1 END) as stale_t1,
        COUNT(CASE WHEN price_t5 = price_at_publish THEN 1 END) as stale_t5,
        COUNT(CASE WHEN price_t30 = price_at_publish THEN 1 END) as stale_t30
    FROM core.pit_events
    """
    row = con.execute(q).fetchone()
    (total, null_pub, zero_pub, t1_cnt, t5_cnt, t30_cnt, 
     z_t1, z_t5, z_t30, stale_t1, stale_t5, stale_t30) = row
    
    pct_t1 = (t1_cnt / total) * 100 if total else 0
    pct_t5 = (t5_cnt / total) * 100 if total else 0
    pct_t30 = (t30_cnt / total) * 100 if total else 0
    
    print(f"Total PIT Events:                 {total:,}")
    print(f"Null Price at Publish:            {null_pub:,} ({null_pub/total*100:.2f}%)")
    print(f"Zero/Negative Price at Publish:   {zero_pub:,} (DIV-BY-ZERO HAZARD)")
    print(f"Horizon Coverage:")
    print(f"  - T+1 Coverage:                 {t1_cnt:,} ({pct_t1:.2f}%)")
    print(f"  - T+5 Coverage:                 {t5_cnt:,} ({pct_t5:.2f}%)")
    print(f"  - T+30 Coverage:                {t30_cnt:,} ({pct_t30:.2f}%)")
    print(f"Zero/Negative Prices in Horizons:")
    print(f"  - Zero T+1: {z_t1}, Zero T+5: {z_t5}, Zero T+30: {z_t30}")
    print(f"Stale Price Rollover (Price T+k == Price T_0):")
    print(f"  - Stale T+1:  {stale_t1:,} ({stale_t1/t1_cnt*100:.2f}% of T+1)")
    print(f"  - Stale T+5:  {stale_t5:,} ({stale_t5/t5_cnt*100:.2f}% of T+5)")
    print(f"  - Stale T+30: {stale_t30:,} ({stale_t30/t30_cnt*100:.2f}% of T+30)  <-- SUSPENSION / ILLIQUIDITY HAZARD")
    
    return {
        "total": total,
        "null_publish": null_pub,
        "zero_publish": zero_pub,
        "t1_coverage_pct": pct_t1,
        "t5_coverage_pct": pct_t5,
        "t30_coverage_pct": pct_t30,
        "zero_horizons_total": z_t1 + z_t5 + z_t30,
        "stale_t30_pct": (stale_t30 / t30_cnt * 100) if t30_cnt else 0,
    }


def run_temporal_alignment_audit(db_path: str = "db/test_db/vesta_test.duckdb"):
    print(f"Loading database from {db_path}...")
    if not os.path.exists(db_path):
        print(f"Error: {db_path} does not exist.")
        return
        
    con = duckdb.connect(db_path, read_only=True)
    res_1_1 = audit_subsequence_1_1_event_session(con)
    res_1_2 = audit_subsequence_1_2_fundamentals_lag(con)
    res_1_3 = audit_subsequence_1_3_forward_horizons(con)
    con.close()
    
    # Save results to JSON
    os.makedirs("test_pipeline/out", exist_ok=True)
    out_file = "test_pipeline/out/temporal_alignment_audit_report.json"
    report = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "database": db_path,
        "audit_1_1_event_session": res_1_1,
        "audit_1_2_fundamentals_lag": res_1_2,
        "audit_1_3_forward_horizons": res_1_3,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nAudit complete! Full report saved to {out_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default="db/test_db/vesta_test.duckdb")
    args = parser.parse_args()
    run_temporal_alignment_audit(args.db_path)
