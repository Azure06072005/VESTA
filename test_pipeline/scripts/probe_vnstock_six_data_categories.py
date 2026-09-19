import os
import sys
import json
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
os.environ["VNSTOCK_API_KEY"] = "vnstock_f84ed9f3014e77c53a88e3eae1bc1be8"

from vnstock_data import Market, Fundamental, Reference

mkt = Market()
fun = Fundamental()
ref = Reference()

print("=" * 80)
print("TESTING 6 QUANTITATIVE DATA CATEGORIES IN VNSTOCK (SILVER TIER)")
print("=" * 80)

ticker = "VCB"

# -----------------------------------------------------------------------------
# 1. Sổ lệnh vi mô Level 2 / Tick Data (Order Book Depth, Trades, Price Depth)
# -----------------------------------------------------------------------------
print("\n[1] TEST: Order Book Depth & Microstructure (order_book, price_depth, trades, intraday)")
try:
    df_ob = mkt.equity(ticker).order_book()
    print(" -> order_book() shape:", df_ob.shape if hasattr(df_ob, 'shape') else type(df_ob))
    if isinstance(df_ob, pd.DataFrame) and not df_ob.empty:
        print(df_ob.head(5).to_string())
except Exception as e:
    print(" -> order_book() error:", e)

try:
    df_pd = mkt.equity(ticker).price_depth()
    print(" -> price_depth() shape:", df_pd.shape if hasattr(df_pd, 'shape') else type(df_pd))
    if isinstance(df_pd, pd.DataFrame) and not df_pd.empty:
        print(df_pd.head(5).to_string())
except Exception as e:
    print(" -> price_depth() error:", e)

try:
    df_trades = mkt.equity(ticker).trades()
    print(" -> trades() shape:", df_trades.shape if hasattr(df_trades, 'shape') else type(df_trades))
    if isinstance(df_trades, pd.DataFrame) and not df_trades.empty:
        print(df_trades.head(5).to_string())
except Exception as e:
    print(" -> trades() error:", e)

# -----------------------------------------------------------------------------
# 2. Dữ liệu Khớp lệnh Tự doanh Chi tiết Từng Mã (proprietary_flow)
# -----------------------------------------------------------------------------
print("\n[2] TEST: Tự doanh theo từng mã (proprietary_flow)")
try:
    df_prop = mkt.equity(ticker).proprietary_flow()
    print(" -> proprietary_flow() shape:", df_prop.shape if hasattr(df_prop, 'shape') else type(df_prop))
    if isinstance(df_prop, pd.DataFrame) and not df_prop.empty:
        print(df_prop.head(5).to_string())
except Exception as e:
    print(" -> proprietary_flow() error:", e)

# -----------------------------------------------------------------------------
# 3. Dữ liệu Khối ngoại Realtime Trong Phiên (foreign_flow)
# -----------------------------------------------------------------------------
print("\n[3] TEST: Khối ngoại Realtime / Intraday (foreign_flow)")
try:
    df_ff = mkt.equity(ticker).foreign_flow()
    print(" -> foreign_flow() shape:", df_ff.shape if hasattr(df_ff, 'shape') else type(df_ff))
    if isinstance(df_ff, pd.DataFrame) and not df_ff.empty:
        print(df_ff.head(5).to_string())
except Exception as e:
    print(" -> foreign_flow() error:", e)

# -----------------------------------------------------------------------------
# 4. Lợi suất Trái phiếu & Lãi suất Liên ngân hàng (Reference.bond, Market.bond)
# -----------------------------------------------------------------------------
print("\n[4] TEST: Trái phiếu Chính phủ & Lãi suất (Reference.bond / Market.bond)")
try:
    print(" -> Methods on Reference.bond():", [m for m in dir(ref.bond) if not m.startswith('_')])
    df_bond = ref.bond()
    print(" -> ref.bond() shape:", df_bond.shape if hasattr(df_bond, 'shape') else type(df_bond))
    if isinstance(df_bond, pd.DataFrame) and not df_bond.empty:
        print(df_bond.head(5).to_string())
except Exception as e:
    print(" -> ref.bond() error:", e)

try:
    print(" -> Methods on Market.bond():", [m for m in dir(mkt.bond) if not m.startswith('_')])
    df_mbond = mkt.bond()
    print(" -> mkt.bond() shape:", df_mbond.shape if hasattr(df_mbond, 'shape') else type(df_mbond))
    if isinstance(df_mbond, pd.DataFrame) and not df_mbond.empty:
        print(df_mbond.head(5).to_string())
except Exception as e:
    print(" -> mkt.bond() error:", e)

# -----------------------------------------------------------------------------
# 5. Thuyết minh BCTC Chuyên sâu (Fundamental.equity.note / filing)
# -----------------------------------------------------------------------------
print("\n[5] TEST: Thuyết minh BCTC (note / filing)")
try:
    df_note = fun.equity(ticker).note()
    print(" -> note() shape:", df_note.shape if hasattr(df_note, 'shape') else type(df_note))
    if isinstance(df_note, pd.DataFrame) and not df_note.empty:
        print(df_note.head(5).to_string())
except Exception as e:
    print(" -> note() error:", e)

try:
    df_filing = fun.equity(ticker).filing()
    print(" -> filing() shape:", df_filing.shape if hasattr(df_filing, 'shape') else type(df_filing))
    if isinstance(df_filing, pd.DataFrame) and not df_filing.empty:
        print(df_filing.head(5).to_string())
except Exception as e:
    print(" -> filing() error:", e)

# -----------------------------------------------------------------------------
# 6. Tỷ lệ sở hữu nước ngoài / Room ngoại còn lại
# -----------------------------------------------------------------------------
print("\n[6] TEST: Tỷ lệ sở hữu nước ngoài / Room ngoại (Reference.equity / company)")
try:
    df_comp = ref.company(ticker)
    print(" -> ref.company() shape:", df_comp.shape if hasattr(df_comp, 'shape') else type(df_comp))
    if isinstance(df_comp, pd.DataFrame) and not df_comp.empty:
        print(df_comp.head(5).to_string())
except Exception as e:
    print(" -> ref.company() error:", e)

try:
    df_req = ref.equity()
    print(" -> ref.equity() shape:", df_req.shape if hasattr(df_req, 'shape') else type(df_req))
    if isinstance(df_req, pd.DataFrame) and not df_req.empty:
        cols_with_foreign = [c for c in df_req.columns if 'foreign' in c.lower() or 'room' in c.lower()]
        print(" -> Foreign room columns:", cols_with_foreign)
        print(df_req[['symbol'] + cols_with_foreign].head(5).to_string())
except Exception as e:
    print(" -> ref.equity() error:", e)
