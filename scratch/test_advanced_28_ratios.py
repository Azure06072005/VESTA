"""scratch/test_advanced_28_ratios.py

Tests extraction of 28 Advanced Quant Ratios covering:
- Valuation (7)
- Profitability & Margins (7)
- Efficiency & Working Capital Cycle (6)
- Liquidity & Leverage (4)
- Banking Specifics (4)
"""
import sys
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta.duckdb", read_only=True)

q = """
SELECT 
    symbol,
    period_end,
    -- Valuation
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_PE') AS FLOAT) as pe_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_PB') AS FLOAT) as pb_ratio,
    -- Profitability & Margins
    TRY_CAST(json_extract(data_json, '$.RT_PRT_ROE') AS FLOAT) as roe,
    TRY_CAST(json_extract(data_json, '$.RT_PRT_EBIT_MARGIN') AS FLOAT) as ebit_margin,
    -- Efficiency & Cash Conversion Cycle
    TRY_CAST(json_extract(data_json, '$.RT_EFF_DSO') AS FLOAT) as days_sales_outstanding,
    TRY_CAST(json_extract(data_json, '$.RT_EFF_DIO') AS FLOAT) as days_inventory_outstanding,
    TRY_CAST(json_extract(data_json, '$.RT_EFF_CASH_CYCLE') AS FLOAT) as cash_conversion_cycle,
    -- Liquidity & Leverage
    TRY_CAST(json_extract(data_json, '$.RT_LQD_CR') AS FLOAT) as current_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_LQD_QR') AS FLOAT) as quick_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_LEV_DE') AS FLOAT) as debt_to_equity,
    -- Banking Specifics
    TRY_CAST(json_extract(data_json, '$.RT_BANK_NIM') AS FLOAT) as bank_nim,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_NPL') AS FLOAT) as bank_npl
FROM core.fundamentals 
WHERE report_type = 'ratio' 
  AND symbol IN ('HPG', 'VCB', 'MWG')
  AND period_end = '2024-03-31'
"""
df = con.execute(q).df()
print("=== DEMO: EXTRACTION OF ADVANCED RATIOS ACROSS DIFFERENT SECTORS ===")
print(df.to_string(index=False))

con.close()
