"""src/pipeline/flatten_quant_fundamentals.py

Selective JSON Flattening & Point-in-Time Fundamental Enrichment for VESTA.
Excludes ONLY the 13 keys that have 100% Null/NaN.
Extracts ALL 47 active quantitative ratios into preprocessed.fundamentals_ratios:
1. Valuation (11 ratios): pe_ratio, pb_ratio, ps_ratio, p_cf_ratio, ev_ebitda, dividend_yield, market_cap,
   outstanding_shares, ebit, ebitda, equity_val.
2. Profitability (7 ratios): roe, roa, roic, gross_margin, ebit_margin, pre_tax_margin, net_margin.
3. Efficiency & Working Capital (6 ratios): asset_turnover, fixed_asset_turnover, days_sales_outstanding (DSO),
   days_inventory_outstanding (DIO), days_payable_outstanding (DPO), cash_conversion_cycle.
4. Liquidity & Leverage (8 ratios): current_ratio, quick_ratio, cash_ratio, debt_to_equity, loan_to_equity,
   financial_leverage, equity_to_liabilities, equity_to_assets.
5. Banking Specifics (15 ratios): bank_nim, bank_yiea, bank_cof, bank_noii, bank_cir, bank_loan_growth,
   bank_deposit_growth, bank_ldr, bank_npl, bank_npl_coverage, bank_provision_to_loans, bank_car, bank_casa,
   bank_equity_to_loans, bank_llr_to_loans.

Performs Strict Point-in-Time ASOF LEFT JOIN (available_at <= event_date) to enrich all 581,944 events.
"""
from __future__ import annotations

import os
import shutil
import sys
import time

import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_DB_PATH = "db/vesta.duckdb"
SOURCE_FULL_DB_PATH = "db/vesta_preprocessed_full.duckdb"
TARGET_QUANT_DB_PATH = "db/vesta_preprocessed_quant.duckdb"
PIPELINE_QUANT_DB_PATH = "test_pipeline/db/vesta_preprocessed_quant.duckdb"
CSV_PREVIEW_PATH = "test_pipeline/out/full_preprocessed_events_with_fundamentals_preview.csv"


def run_flatten_fundamentals():
    start_time = time.time()
    print("=" * 85)
    print("ALL-ACTIVE QUANT JSON FLATTENING & POINT-IN-TIME ENRICHMENT (47 RATIOS)")
    print(f"Canonical DB : {CANONICAL_DB_PATH}")
    print(f"Target DB    : {TARGET_QUANT_DB_PATH}")
    print("=" * 85)

    con = duckdb.connect(CANONICAL_DB_PATH)

    # -------------------------------------------------------------------------
    # STEP 1: EXTRACT ALL 47 ACTIVE QUANT RATIOS INTO preprocessed.fundamentals_ratios
    # -------------------------------------------------------------------------
    print("\n>>> [1/3] Extracting 47 Active Quant Ratios from core.fundamentals.data_json...")
    t0 = time.time()
    
    q_flatten = """
    CREATE OR REPLACE TABLE preprocessed.fundamentals_ratios AS
    SELECT 
        symbol,
        period_end,
        available_at,
        report_type,
        -- 1. Valuation Ratios (11)
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_PE') AS FLOAT)                 AS pe_ratio,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_PB') AS FLOAT)                 AS pb_ratio,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_PS') AS FLOAT)                 AS ps_ratio,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_P_CF') AS FLOAT)               AS p_cf_ratio,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_EV_EBITDA') AS FLOAT)           AS ev_ebitda,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_DIVIDEND_YIELD') AS FLOAT)       AS dividend_yield,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_MARKET_CAP') AS FLOAT)         AS market_cap,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_OUTSTANDING_SHARES') AS FLOAT) AS outstanding_shares,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_EBIT') AS FLOAT)               AS ebit,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_EBITDA') AS FLOAT)             AS ebitda,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_EQUITY') AS FLOAT)             AS equity_val,
        -- 2. Profitability & Margins (7)
        TRY_CAST(json_extract(data_json, '$.RT_PRT_ROE') AS FLOAT)                  AS roe,
        TRY_CAST(json_extract(data_json, '$.RT_PRT_ROA') AS FLOAT)                  AS roa,
        TRY_CAST(json_extract(data_json, '$.RT_PRT_ROIC') AS FLOAT)                 AS roic,
        TRY_CAST(json_extract(data_json, '$.RT_PRT_GROSS_MARGIN') AS FLOAT)         AS gross_margin,
        TRY_CAST(json_extract(data_json, '$.RT_PRT_EBIT_MARGIN') AS FLOAT)          AS ebit_margin,
        TRY_CAST(json_extract(data_json, '$.RT_PRT_PRE_TAX_MARGIN') AS FLOAT)      AS pre_tax_margin,
        TRY_CAST(json_extract(data_json, '$.RT_PRT_NET_MARGIN') AS FLOAT)          AS net_margin,
        -- 3. Efficiency & Working Capital Cycle (6)
        TRY_CAST(json_extract(data_json, '$.RT_EFF_ATR') AS FLOAT)                  AS asset_turnover,
        TRY_CAST(json_extract(data_json, '$.RT_EFF_FATR') AS FLOAT)                 AS fixed_asset_turnover,
        TRY_CAST(json_extract(data_json, '$.RT_EFF_DSO') AS FLOAT)                  AS days_sales_outstanding,
        TRY_CAST(json_extract(data_json, '$.RT_EFF_DIO') AS FLOAT)                  AS days_inventory_outstanding,
        TRY_CAST(json_extract(data_json, '$.RT_EFF_DPO') AS FLOAT)                  AS days_payable_outstanding,
        TRY_CAST(json_extract(data_json, '$.RT_EFF_CASH_CYCLE') AS FLOAT)          AS cash_conversion_cycle,
        -- 4. Liquidity & Leverage (8)
        TRY_CAST(json_extract(data_json, '$.RT_LQD_CR') AS FLOAT)                   AS current_ratio,
        TRY_CAST(json_extract(data_json, '$.RT_LQD_QR') AS FLOAT)                   AS quick_ratio,
        TRY_CAST(json_extract(data_json, '$.RT_LQD_CASH_RATIO') AS FLOAT)          AS cash_ratio,
        TRY_CAST(json_extract(data_json, '$.RT_LEV_DE') AS FLOAT)                    AS debt_to_equity,
        TRY_CAST(json_extract(data_json, '$.RT_LEV_LOAN_EQUITY') AS FLOAT)          AS loan_to_equity,
        TRY_CAST(json_extract(data_json, '$.RT_LEV_FINANCIAL_LEVERAGE') AS FLOAT)   AS financial_leverage,
        TRY_CAST(json_extract(data_json, '$.RT_LEV_EQUITY_TO_LIABILITIES') AS FLOAT)AS equity_to_liabilities,
        TRY_CAST(json_extract(data_json, '$.RT_LEV_EQUITY_TO_ASSETS') AS FLOAT)     AS equity_to_assets,
        -- 5. Banking Specifics (15)
        TRY_CAST(json_extract(data_json, '$.RT_BANK_NIM') AS FLOAT)                 AS bank_nim,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_YIEA') AS FLOAT)                AS bank_yiea,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_COF') AS FLOAT)                 AS bank_cof,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_NOII') AS FLOAT)                AS bank_noii,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_CIR') AS FLOAT)                 AS bank_cir,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_LOAN_GROWTH') AS FLOAT)         AS bank_loan_growth,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_DEPOSIT_GROWTH') AS FLOAT)      AS bank_deposit_growth,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_LDR') AS FLOAT)                 AS bank_ldr,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_NPL') AS FLOAT)                 AS bank_npl,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_NPL_COVERAGE') AS FLOAT)        AS bank_npl_coverage,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_PROVISION_TO_LOANS') AS FLOAT) AS bank_provision_to_loans,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_CAR') AS FLOAT)                 AS bank_car,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_CASA') AS FLOAT)                AS bank_casa,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_EQUITY_TO_LOANS') AS FLOAT)     AS bank_equity_to_loans,
        TRY_CAST(json_extract(data_json, '$.RT_BANK_LLR_TO_LOANS') AS FLOAT)        AS bank_llr_to_loans,
        -- 6. Audit Provenance
        data_json AS raw_payload_json
    FROM core.fundamentals
    WHERE report_type = 'ratio' AND data_json IS NOT NULL;
    """
    con.execute(q_flatten)
    cnt_ratios = con.execute("SELECT count(*) FROM preprocessed.fundamentals_ratios").fetchone()[0]
    print(f" -> [OK] preprocessed.fundamentals_ratios created: {cnt_ratios:,} rows with 47 active ratios ({time.time()-t0:.2f}s)")

    # -------------------------------------------------------------------------
    # STEP 2: POINT-IN-TIME ASOF LEFT JOIN TO ENRICH ALL 581,944 EVENTS
    # -------------------------------------------------------------------------
    print("\n>>> [2/3] Enriching ALL 581,944 events via Point-in-Time ASOF LEFT JOIN...")
    t0 = time.time()

    con.execute(f"ATTACH '{SOURCE_FULL_DB_PATH}' AS orig_db (READ_ONLY);")

    q_enrich_events = """
    CREATE OR REPLACE TABLE preprocessed.events AS
    SELECT 
        e.*,
        r.period_end     AS bctc_period_end,
        r.available_at   AS bctc_available_at,
        -- Valuation (11)
        r.pe_ratio, r.pb_ratio, r.ps_ratio, r.p_cf_ratio, r.ev_ebitda, r.dividend_yield, r.market_cap,
        r.outstanding_shares, r.ebit, r.ebitda, r.equity_val,
        -- Profitability (7)
        r.roe, r.roa, r.roic, r.gross_margin, r.ebit_margin, r.pre_tax_margin, r.net_margin,
        -- Efficiency & Working Capital (6)
        r.asset_turnover, r.fixed_asset_turnover, r.days_sales_outstanding, r.days_inventory_outstanding,
        r.days_payable_outstanding, r.cash_conversion_cycle,
        -- Liquidity & Leverage (8)
        r.current_ratio, r.quick_ratio, r.cash_ratio, r.debt_to_equity, r.loan_to_equity,
        r.financial_leverage, r.equity_to_liabilities, r.equity_to_assets,
        -- Banking Specifics (15)
        r.bank_nim, r.bank_yiea, r.bank_cof, r.bank_noii, r.bank_cir, r.bank_loan_growth,
        r.bank_deposit_growth, r.bank_ldr, r.bank_npl, r.bank_npl_coverage, r.bank_provision_to_loans,
        r.bank_car, r.bank_casa, r.bank_equity_to_loans, r.bank_llr_to_loans
    FROM orig_db.events e
    ASOF LEFT JOIN preprocessed.fundamentals_ratios r
      ON e.symbol = r.symbol AND e.event_date >= r.available_at;
    """
    con.execute(q_enrich_events)
    con.execute("DETACH orig_db;")
    
    cnt_events = con.execute("SELECT count(*) FROM preprocessed.events").fetchone()[0]
    cnt_with_fund = con.execute("SELECT count(*) FROM preprocessed.events WHERE pe_ratio IS NOT NULL").fetchone()[0]
    print(f" -> [OK] preprocessed.events enriched: {cnt_events:,} events ({cnt_with_fund:,} matched with BCTC) ({time.time()-t0:.2f}s)")

    # -------------------------------------------------------------------------
    # STEP 3: SYNC TO STANDALONE DB & EXPORT PREVIEW CSV
    # -------------------------------------------------------------------------
    print(f"\n>>> [3/3] Synchronizing into Standalone DB: {TARGET_QUANT_DB_PATH}...")
    t0 = time.time()
    
    if os.path.exists(TARGET_QUANT_DB_PATH):
        os.remove(TARGET_QUANT_DB_PATH)
        
    con.execute(f"ATTACH '{TARGET_QUANT_DB_PATH}' AS target_db;")
    con.execute("CREATE TABLE target_db.market_regimes AS SELECT * FROM preprocessed.market_regimes;")
    con.execute("CREATE TABLE target_db.macro_policy AS SELECT * FROM preprocessed.macro_policy;")
    con.execute("CREATE TABLE target_db.fundamentals_ratios AS SELECT * FROM preprocessed.fundamentals_ratios;")
    con.execute("CREATE TABLE target_db.events AS SELECT * FROM preprocessed.events;")
    con.execute("DETACH target_db;")
    
    # Also sync to test_pipeline directory
    os.makedirs(os.path.dirname(PIPELINE_QUANT_DB_PATH), exist_ok=True)
    if os.path.exists(PIPELINE_QUANT_DB_PATH):
        os.remove(PIPELINE_QUANT_DB_PATH)
    shutil.copyfile(TARGET_QUANT_DB_PATH, PIPELINE_QUANT_DB_PATH)
    
    # Export 500 rows preview CSV
    df_preview = con.execute("""
        SELECT symbol, exchange, event_date, headline_clean, 
               sentiment_score, rankgauss_sentiment_z,
               p0, p5, p30, winsorized_diff_pct, market_regime,
               bctc_period_end, bctc_available_at, 
               pe_ratio, pb_ratio, roe, gross_margin,
               days_sales_outstanding, days_inventory_outstanding, cash_conversion_cycle,
               quick_ratio, debt_to_equity, bank_nim, bank_npl
        FROM preprocessed.events
        WHERE pe_ratio IS NOT NULL
        ORDER BY event_date DESC
        LIMIT 500
    """).df()
    df_preview.to_csv(CSV_PREVIEW_PATH, index=False, encoding="utf-8-sig")
    con.close()

    elapsed = time.time() - start_time
    print("\n" + "=" * 85)
    print("ALL-ACTIVE QUANT RATIO ENRICHMENT COMPLETED SUCCESSFULLY!")
    print(f"Total Processing Time: {elapsed:.2f} seconds")
    print(f"1. Canonical DB Updated: {CANONICAL_DB_PATH}")
    print(f"   - preprocessed.fundamentals_ratios : {cnt_ratios:,} rows (47 active quant ratios)")
    print(f"   - preprocessed.events (enriched)   : {cnt_events:,} rows ({cnt_with_fund:,} matched with BCTC)")
    print(f"2. Standalone DB Created: {TARGET_QUANT_DB_PATH} ({os.path.getsize(TARGET_QUANT_DB_PATH):,} bytes)")
    print(f"3. CSV Preview Exported : {CSV_PREVIEW_PATH} (500 rows with all active ratios)")
    print("=" * 85)


if __name__ == "__main__":
    run_flatten_fundamentals()
