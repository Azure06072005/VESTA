"""scratch/test_47_quant_ratios.py

Tests extraction of all 47 non-null quant ratios in DuckDB
"""
import sys
import time
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta.duckdb", read_only=True)

t0 = time.time()
q = """
SELECT 
    symbol,
    period_end,
    -- 1. Valuation
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_PE') AS FLOAT) as pe_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_PB') AS FLOAT) as pb_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_PS') AS FLOAT) as ps_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_P_CF') AS FLOAT) as p_cf_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_EV_EBITDA') AS FLOAT) as ev_ebitda,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_DIVIDEND_YIELD') AS FLOAT) as dividend_yield,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_MARKET_CAP') AS FLOAT) as market_cap,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_OUTSTANDING_SHARES') AS FLOAT) as outstanding_shares,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_EBIT') AS FLOAT) as ebit,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_EBITDA') AS FLOAT) as ebitda,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_EQUITY') AS FLOAT) as equity_val,
    -- 2. Profitability
    TRY_CAST(json_extract(data_json, '$.RT_PRT_ROE') AS FLOAT) as roe,
    TRY_CAST(json_extract(data_json, '$.RT_PRT_ROA') AS FLOAT) as roa,
    TRY_CAST(json_extract(data_json, '$.RT_PRT_ROIC') AS FLOAT) as roic,
    TRY_CAST(json_extract(data_json, '$.RT_PRT_GROSS_MARGIN') AS FLOAT) as gross_margin,
    TRY_CAST(json_extract(data_json, '$.RT_PRT_EBIT_MARGIN') AS FLOAT) as ebit_margin,
    TRY_CAST(json_extract(data_json, '$.RT_PRT_PRE_TAX_MARGIN') AS FLOAT) as pre_tax_margin,
    TRY_CAST(json_extract(data_json, '$.RT_PRT_NET_MARGIN') AS FLOAT) as net_margin,
    -- 3. Efficiency & Working Capital
    TRY_CAST(json_extract(data_json, '$.RT_EFF_ATR') AS FLOAT) as asset_turnover,
    TRY_CAST(json_extract(data_json, '$.RT_EFF_FATR') AS FLOAT) as fixed_asset_turnover,
    TRY_CAST(json_extract(data_json, '$.RT_EFF_DSO') AS FLOAT) as days_sales_outstanding,
    TRY_CAST(json_extract(data_json, '$.RT_EFF_DIO') AS FLOAT) as days_inventory_outstanding,
    TRY_CAST(json_extract(data_json, '$.RT_EFF_DPO') AS FLOAT) as days_payable_outstanding,
    TRY_CAST(json_extract(data_json, '$.RT_EFF_CASH_CYCLE') AS FLOAT) as cash_conversion_cycle,
    -- 4. Liquidity & Leverage
    TRY_CAST(json_extract(data_json, '$.RT_LQD_CR') AS FLOAT) as current_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_LQD_QR') AS FLOAT) as quick_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_LQD_CASH_RATIO') AS FLOAT) as cash_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_LEV_DE') AS FLOAT) as debt_to_equity,
    TRY_CAST(json_extract(data_json, '$.RT_LEV_LOAN_EQUITY') AS FLOAT) as loan_to_equity,
    TRY_CAST(json_extract(data_json, '$.RT_LEV_FINANCIAL_LEVERAGE') AS FLOAT) as financial_leverage,
    TRY_CAST(json_extract(data_json, '$.RT_LEV_EQUITY_TO_LIABILITIES') AS FLOAT) as equity_to_liabilities,
    TRY_CAST(json_extract(data_json, '$.RT_LEV_EQUITY_TO_ASSETS') AS FLOAT) as equity_to_assets,
    -- 5. Banking Specifics
    TRY_CAST(json_extract(data_json, '$.RT_BANK_NIM') AS FLOAT) as bank_nim,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_YIEA') AS FLOAT) as bank_yiea,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_COF') AS FLOAT) as bank_cof,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_NOII') AS FLOAT) as bank_noii,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_CIR') AS FLOAT) as bank_cir,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_LOAN_GROWTH') AS FLOAT) as bank_loan_growth,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_DEPOSIT_GROWTH') AS FLOAT) as bank_deposit_growth,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_LDR') AS FLOAT) as bank_ldr,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_NPL') AS FLOAT) as bank_npl,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_NPL_COVERAGE') AS FLOAT) as bank_npl_coverage,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_PROVISION_TO_LOANS') AS FLOAT) as bank_provision_to_loans,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_CAR') AS FLOAT) as bank_car,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_CASA') AS FLOAT) as bank_casa,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_EQUITY_TO_LOANS') AS FLOAT) as bank_equity_to_loans,
    TRY_CAST(json_extract(data_json, '$.RT_BANK_LLR_TO_LOANS') AS FLOAT) as bank_llr_to_loans
FROM core.fundamentals 
WHERE report_type = 'ratio' 
  AND symbol IN ('VCB', 'HPG', 'SSI')
  AND period_end = '2024-03-31'
"""
df = con.execute(q).df()
t1 = time.time()

print(f"Executed 47-column query in {t1 - t0:.2f} seconds!")
print("Columns count:", len(df.columns))
print(df.to_string())

con.close()
