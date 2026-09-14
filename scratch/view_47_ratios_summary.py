"""scratch/view_47_ratios_summary.py

Extracts summary statistics and sample records from db/vesta_preprocessed_quant.duckdb
"""
import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_preprocessed_quant.duckdb", read_only=True)

print("=" * 90)
print("AUDIT: FULL 47 QUANT RATIOS ENRICHED IN STANDALONE DATABASE")
print("=" * 90)

cols = con.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'events'").df()
print(f"Total Columns in table 'events': {len(cols)}")
print("Columns list:")
col_names = list(cols["column_name"])
for i in range(0, len(col_names), 4):
    print("  " + ", ".join(f"{c:<25}" for c in col_names[i:i+4]))

print("\nSample Enriched Events across Distinct Sectors (HPG - Sản xuất, MWG - Bán lẻ, VCB - Ngân hàng):")
q = """
SELECT 
    symbol,
    event_date,
    headline_clean,
    pe_ratio,
    pb_ratio,
    roe,
    gross_margin,
    days_sales_outstanding,
    days_inventory_outstanding,
    cash_conversion_cycle,
    quick_ratio,
    debt_to_equity,
    bank_nim,
    bank_npl,
    bank_casa,
    bank_ldr,
    bank_cir
FROM events
WHERE symbol = 'VCB'
  AND pe_ratio IS NOT NULL
ORDER BY event_date DESC
LIMIT 1
"""
df_sample = con.execute(q).df()
for idx, r in df_sample.iterrows():
    print(f"\n[{idx+1}] Mã: {r['symbol']} | Ngày: {r['event_date']}")
    print(f" Tiêu đề          : {r['headline_clean']}")
    print(f" Định giá         : P/E={r['pe_ratio']:.2f} | P/B={r['pb_ratio']:.2f} | ROE={r['roe']*100:.2f}% | Biên gộp={r['gross_margin']*100:.2f}%")
    print(f" Vòng quay Vốn    : Thu tiền (DSO)={r['days_sales_outstanding']:.1f} ngày | Tồn kho (DIO)={r['days_inventory_outstanding']:.1f} ngày | Chu kỳ tiền={r['cash_conversion_cycle']:.1f} ngày")
    print(f" Thanh khoản & Nợ : Quick Ratio={r['quick_ratio']:.2f} | D/E={r['debt_to_equity']:.2f}")
    if r['bank_nim'] > 0 or r['bank_npl'] > 0 or r['bank_casa'] > 0:
        print(f" Đặc thù Bank     : NIM={r['bank_nim']*100:.2f}% | NPL={r['bank_npl']*100:.2f}% | CASA={r['bank_casa']*100:.2f}%")

con.close()
