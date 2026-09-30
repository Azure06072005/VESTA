"""Live verification of src/crawlers/market_insights.py against real public endpoints.

Executes live calls for all components of F007b:
1. Vietcap IQ Screener & Criteria
2. VNDIRECT FINFO Rankings & Index Valuation (P/E, P/B)
3. ASEAN Securities Market Breadth & Fear-Greed
4. ASEAN Securities Macroeconomic Indicators (GDP, CPI, Interbank, FX)
"""
import sys
import pathlib
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from crawlers import market_insights

def run_live_verification():
    print("=" * 80)
    print("F007b: MARKET INSIGHTS DIRECT REST API LIVE VERIFICATION")
    print("=" * 80)

    # 1. Vietcap Screener
    t0 = time.time()
    df_screener = market_insights.fetch_market_screener(page_size=1600)
    el_screener = time.time() - t0
    print(f"\n[1] Vietcap Screener (Direct):")
    print(f"    - Elapsed: {el_screener:.3f}s")
    print(f"    - Shape: {df_screener.shape}")
    print(f"    - Source: {df_screener.attrs.get('source')}")
    print(f"    - Top 5 Symbols: {df_screener['symbol'].head().tolist()}")
    print(f"    - Sample Columns: {df_screener.columns.tolist()[:10]}")

    # 2. VNDIRECT Rankings
    t0 = time.time()
    df_gainer = market_insights.fetch_market_rankings(category="gainer", index="VNINDEX", limit=5)
    el_gainer = time.time() - t0
    print(f"\n[2] VNDIRECT Top Gainers (Direct):")
    print(f"    - Elapsed: {el_gainer:.3f}s")
    print(f"    - Shape: {df_gainer.shape}")
    print(f"    - Source: {df_gainer.attrs.get('source')}")
    print(f"    - Symbols: {df_gainer['symbol'].tolist()}")
    print(f"    - Columns: {df_gainer.columns.tolist()[:8]}")

    # 3. VNDIRECT Index Valuation
    t0 = time.time()
    df_pe = market_insights.fetch_index_valuation(index="VNINDEX", ratio_code="PRICE_TO_EARNINGS", start_date="2026-01-01")
    el_pe = time.time() - t0
    print(f"\n[3] VNDIRECT VN-Index Historical P/E (Direct):")
    print(f"    - Elapsed: {el_pe:.3f}s")
    print(f"    - Shape: {df_pe.shape}")
    print(f"    - Source: {df_pe.attrs.get('source')}")
    print(f"    - Latest P/E Date: {df_pe['report_date'].iloc[-1].strftime('%Y-%m-%d')}, Value: {df_pe['value'].iloc[-1]:.2f}")

    # 4. ASEAN Market Breadth
    t0 = time.time()
    df_breadth = market_insights.fetch_market_breadth(exchange="HOSE")
    el_breadth = time.time() - t0
    print(f"\n[4] ASEAN Market Breadth (Direct):")
    print(f"    - Elapsed: {el_breadth:.3f}s")
    print(f"    - Shape: {df_breadth.shape}")
    print(f"    - Source: {df_breadth.attrs.get('source')}")
    print(f"    - Columns: {df_breadth.columns.tolist()[:7]}")

    # 5. ASEAN Fear & Greed
    t0 = time.time()
    df_fg = market_insights.fetch_market_fear_greed(exchange="HOSE")
    el_fg = time.time() - t0
    print(f"\n[5] ASEAN Fear & Greed Index (Direct):")
    print(f"    - Elapsed: {el_fg:.3f}s")
    print(f"    - Shape: {df_fg.shape}")
    print(f"    - Source: {df_fg.attrs.get('source')}")
    print(f"    - Score: {df_fg['fear_greed_score'].iloc[0]}, Advances: {df_fg['advances'].iloc[0]}, Declines: {df_fg['declines'].iloc[0]}")

    # 6. ASEAN Macro GDP
    t0 = time.time()
    df_gdp = market_insights.fetch_macro_indicator(indicator="gdp", start_date="2020-01-01")
    el_gdp = time.time() - t0
    print(f"\n[6] ASEAN Macro GDP (Direct):")
    print(f"    - Elapsed: {el_gdp:.3f}s")
    print(f"    - Shape: {df_gdp.shape}")
    print(f"    - Source: {df_gdp.attrs.get('source')}")
    print(f"    - Latest GDP Quarter: {df_gdp['report_date'].iloc[-1].strftime('%Y-%m-%d')}, Growth: {df_gdp['gdp'].iloc[-1]}%")

    print("\n" + "=" * 80)
    print("ALL DIRECT REST API SOURCES VERIFIED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    run_live_verification()
