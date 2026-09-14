"""scratch/view_enriched_quant_sample.py

Prints sample enriched events with 14 quant ratios from db/vesta_preprocessed_quant.duckdb
"""
import sys
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_preprocessed_quant.duckdb", read_only=True)

df = con.execute("""
    SELECT 
        symbol,
        exchange,
        event_date,
        headline_clean,
        sentiment_score,
        rankgauss_sentiment_z,
        p0,
        p5,
        p30,
        winsorized_diff_pct,
        market_regime,
        bctc_period_end,
        bctc_available_at,
        pe_ratio,
        pb_ratio,
        ps_ratio,
        p_cf_ratio,
        ev_ebitda,
        dividend_yield,
        market_cap,
        roe,
        roa,
        roic,
        gross_margin,
        net_margin,
        debt_to_equity,
        current_ratio
    FROM events
    WHERE symbol IN ('VCB', 'HPG', 'FPT', 'SSI', 'VHM', 'BFC', 'DVP')
      AND pe_ratio IS NOT NULL
    ORDER BY event_date DESC
    LIMIT 4
""").df()

con.close()

print("=" * 85)
print("AUDIT: 4 ENRICHED EVENTS WITH 14 FLATTENED QUANT RATIOS (POINT-IN-TIME)")
print("=" * 85)

for idx, r in df.iterrows():
    print(f"\n[Bản ghi {idx+1}] Mã: {r['symbol']} ({r['exchange']}) | Ngày ra tin: {r['event_date']} | Chế độ: {r['market_regime']}")
    print(f" Tiêu đề tin tức      : {r['headline_clean']}")
    print(f" Giá P0 -> P5 -> P30  : {r['p0']:.2f} -> {r['p5']:.2f} -> {r['p30']:.2f} | Biến động Winsorized: {r['winsorized_diff_pct']:+.2f}%")
    print(f" Khớp BCTC Luật định  : Kỳ kết thúc {r['bctc_period_end']} (Khả dụng ngày {r['bctc_available_at']} <= {r['event_date']})")
    print(f" -> 1. Định giá (Valuation)    : P/E={r['pe_ratio']:.2f} | P/B={r['pb_ratio']:.2f} | P/S={r['ps_ratio']:.2f} | EV/EBITDA={r['ev_ebitda']:.2f} | Cổ tức={r['dividend_yield']:.2f}% | Vốn hóa={r['market_cap']/1e12:.1f} nghìn tỷ")
    print(f" -> 2. Sinh lời (Profitability): ROE={r['roe']*100:.2f}% | ROA={r['roa']*100:.2f}% | ROIC={r['roic']*100:.2f}% | Biên gộp={r['gross_margin']*100:.2f}% | Biên ròng={r['net_margin']*100:.2f}%")
    print(f" -> 3. Sức khỏe & Đòn bẩy     : D/E (Nợ/Vốn CSH)={r['debt_to_equity']:.2f} | Thanh toán hiện hành={r['current_ratio']:.2f}")
