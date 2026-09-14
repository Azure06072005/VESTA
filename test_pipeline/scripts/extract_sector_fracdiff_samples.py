"""test_pipeline/scripts/extract_sector_fracdiff_samples.py

Extracts representative raw data tables for Dynamic Sector-Specific FracDiff:
1. Sector Parameter Master Table (All 11 Sectors).
2. Banking Sector Grid Progression (d=0.00 to 1.00).
3. Utilities Sector Grid Progression (d=0.00 to 1.00).
4. Actual Daily Time Series Samples at Key Historic Dates.
"""
import json
import os
import sys
import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from test_pipeline.f1xx_enrichment.test_fractional_differentiation import frac_diff_ffd
from test_pipeline.f1xx_enrichment.test_sector_specific_fracdiff import (
    extract_sector_price_series,
    DB_PATH,
    OUT_REPORT,
)


def extract_samples():
    with open(OUT_REPORT, "r", encoding="utf-8") as f:
        report = json.load(f)

    # 1. Master Table
    rows_master = []
    for r in report["results"]:
        stat_uniform = "ĐẠT (Dừng)" if r["uniform_d020_stationary"] else "TRƯỢT (Không dừng)"
        rows_master.append({
            "Nhóm Ngành (Sector)": r["sector"],
            "p-value Giá gốc (d=0)": f"{r['raw_p_value']:.4f}",
            "Bậc tối ưu (d*)": f"{r['optimal_d']:.2f}",
            "p-value ADF tại d*": f"{r['optimal_p_value']:.4e}",
            "Tương quan Trí nhớ (rho)": f"{r['optimal_corr']:.4f}",
            "Thử d=0.20 Toàn cục": stat_uniform,
            "Tương quan tại d=1.0": f"{r['corr_at_d1']:.4f}",
        })
    df_master = pd.DataFrame(rows_master).sort_values("Bậc tối ưu (d*)", ascending=False)

    # 2. Banking Grid Progression
    bank_data = next(r for r in report["results"] if r["sector"] == "Ngân hàng")
    df_bank_grid = pd.DataFrame(bank_data["grid_details"])[["d", "adf_stat", "p_val", "corr", "is_stationary", "window_len"]]
    df_bank_grid.columns = ["Bậc d", "ADF Stat", "p-value", "Tương quan (rho)", "Đạt tính dừng?", "Độ dài cửa sổ (k)"]
    df_bank_grid["Đạt tính dừng?"] = df_bank_grid["Đạt tính dừng?"].apply(lambda x: "CÓ (Dừng)" if x else "KHÔNG")

    # 3. Utilities Grid Progression
    util_data = next(r for r in report["results"] if r["sector"] == "Tiện ích Cộng đồng")
    df_util_grid = pd.DataFrame(util_data["grid_details"])[["d", "adf_stat", "p_val", "corr", "is_stationary", "window_len"]].head(6)
    df_util_grid.columns = ["Bậc d", "ADF Stat", "p-value", "Tương quan (rho)", "Đạt tính dừng?", "Độ dài cửa sổ (k)"]
    df_util_grid["Đạt tính dừng?"] = df_util_grid["Đạt tính dừng?"].apply(lambda x: "CÓ (Dừng)" if x else "KHÔNG")

    # 4. Daily Time Series Sample at Inflection Dates
    con = duckdb.connect(DB_PATH, read_only=True)
    sector_series = extract_sector_price_series(con)
    con.close()

    s_bank = sector_series["Ngân hàng"]
    fd_bank_opt = frac_diff_ffd(s_bank, 0.25)
    fd_bank_d1 = frac_diff_ffd(s_bank, 1.0)

    dates_interest = ["2020-03-24", "2020-03-25", "2020-03-26", "2021-06-04", "2022-04-05", "2022-11-15", "2022-11-16"]
    ts_rows = []
    for dt in dates_interest:
        dt_ts = pd.to_datetime(dt)
        if dt_ts in s_bank.index and dt_ts in fd_bank_opt.index and dt_ts in fd_bank_d1.index:
            p_geom = np.exp(s_bank.loc[dt_ts])
            log_p = s_bank.loc[dt_ts]
            fd_val = fd_bank_opt.loc[dt_ts]
            d1_val = fd_bank_d1.loc[dt_ts]
            ts_rows.append({
                "Ngày giao dịch": dt,
                "Giá rổ Ngân hàng (VND)": f"{p_geom:.2f}",
                "Log-Price (d=0)": f"{log_p:.4f}",
                "FracDiff (d*=0.25)": f"{fd_val:.4f}",
                "Integer Return (d=1.0)": f"{d1_val*100:+.2f}%",
                "Sự kiện thị trường": "Đáy Covid" if "2020-03" in dt else ("Đỉnh 1.500đ" if "2022-04" in dt else "Đáy trái phiếu 911đ"),
            })
    df_ts = pd.DataFrame(ts_rows)

    print("\n=== BẢNG 1: TỔNG HỢP THÔNG SỐ FRACDIFF 11 NHÓM NGÀNH ===")
    print(df_master.to_string(index=False))

    print("\n=== BẢNG 2: DIỄN BIẾN LƯỚI d NHÓM NGÂN HÀNG (MINH CHỨNG D* = 0.25) ===")
    print(df_bank_grid.head(8).to_string(index=False))

    print("\n=== BẢNG 3: DIỄN BIẾN LƯỚI d NHÓM TIỆN ÍCH CỘNG ĐỒNG (D* = 0.05) ===")
    print(df_util_grid.to_string(index=False))

    print("\n=== BẢNG 4: CHUỖI DỮ LIỆU THỰC TẾ TẠI CÁC ĐIỂM ĐẢO CHIỀU LỊCH SỬ (NGÂN HÀNG) ===")
    print(df_ts.to_string(index=False))


if __name__ == "__main__":
    extract_samples()
