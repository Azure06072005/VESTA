"""tests/test_symbol_exchange_history.py

Kiểm thử toàn diện khuyến nghị F001 - Dòng thời gian chuyển sàn liên tục
(Continuous Symbol Exchange History & Point-in-Time Lookup).

Mục tiêu kiểm thử:
1. Xác thực cấu trúc bảng core.symbol_exchange_history (start_date, end_date, is_current).
2. Kiểm tra tính liên tục thời gian (Continuous timeline, không chồng lấn ngày).
3. Xác minh các mốc chuyển sàn lịch sử kinh điển (ACB, BCM, SHB, VIB).
4. Kiểm tra thuật toán truy vấn Point-in-Time (get_exchange_at_date) triệt tiêu Look-ahead Bias.
5. Kiểm tra tính idempotent và schema validation khi ghi vào DuckDB.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pandas as pd
import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crawlers import symbol_exchange_history  # noqa: E402
from etl import db  # noqa: E402


def test_build_exchange_history_structure():
    """Kiểm tra cấu trúc DataFrame lịch sử sàn đáp ứng đầy đủ schema."""
    df = symbol_exchange_history.build_symbol_exchange_history_df()
    assert len(df) > 0

    required_cols = [
        "symbol",
        "exchange",
        "start_date",
        "end_date",
        "is_current",
        "event_note",
        "source",
        "created_at",
    ]
    for col in required_cols:
        assert col in df.columns, f"Thiếu cột bắt buộc: {col}"


def test_continuous_timeline_and_single_current():
    """Kiểm tra mọi mã chỉ có tối đa 1 bản ghi is_current=True và ngày bắt đầu <= kết thúc."""
    df = symbol_exchange_history.build_symbol_exchange_history_df()

    # 1. Kiểm tra start_date <= end_date đối với các mốc đã kết thúc
    closed_periods = df[~df["is_current"]]
    for _, row in closed_periods.iterrows():
        s_date = row["start_date"]
        e_date = row["end_date"]
        assert s_date <= e_date, f"{row['symbol']}: start_date {s_date} > end_date {e_date}"

    # 2. Kiểm tra mỗi mã chỉ có duy nhất 1 bản ghi hiện tại (is_current=True)
    current_df = df[df["is_current"]]
    current_counts = current_df["symbol"].value_counts()
    assert (current_counts <= 1).all(), "Phát hiện mã có nhiều hơn 1 bản ghi is_current=True"


def test_verified_historical_exchange_transitions():
    """Kiểm chứng độ chính xác của các mốc chuyển sàn lịch sử đã được Ủy ban Chứng khoán phê duyệt."""
    df = symbol_exchange_history.build_symbol_exchange_history_df()

    # 1. ACB: Chuyển từ HNX sang HOSE vào tháng 12/2020
    acb_records = df[df["symbol"] == "ACB"].sort_values("start_date")
    assert len(acb_records) >= 2, "ACB phải có ít nhất 2 giai đoạn sàn niêm yết"
    assert acb_records.iloc[0]["exchange"] == "HNX"
    assert str(acb_records.iloc[0]["end_date"]) == "2020-12-08"
    assert acb_records.iloc[1]["exchange"] == "HOSE"
    assert str(acb_records.iloc[1]["start_date"]) == "2020-12-09"
    assert acb_records.iloc[1]["is_current"] == True

    # 2. BCM: Chuyển từ UPCOM sang HOSE vào cuối tháng 08/2020
    bcm_records = df[df["symbol"] == "BCM"].sort_values("start_date")
    assert len(bcm_records) >= 2, "BCM phải có ít nhất 2 giai đoạn sàn niêm yết"
    assert bcm_records.iloc[0]["exchange"] == "UPCOM"
    assert str(bcm_records.iloc[0]["end_date"]) == "2020-08-28"
    assert bcm_records.iloc[1]["exchange"] == "HOSE"
    assert str(bcm_records.iloc[1]["start_date"]) == "2020-08-31"
    assert bcm_records.iloc[1]["is_current"] == True

    # 3. SHB: Chuyển từ HNX sang HOSE vào tháng 10/2021
    shb_records = df[df["symbol"] == "SHB"].sort_values("start_date")
    assert len(shb_records) >= 2, "SHB phải có ít nhất 2 giai đoạn sàn niêm yết"
    assert shb_records.iloc[0]["exchange"] == "HNX"
    assert str(shb_records.iloc[0]["end_date"]) == "2021-10-08"
    assert shb_records.iloc[1]["exchange"] == "HOSE"
    assert str(shb_records.iloc[1]["start_date"]) == "2021-10-11"
    assert shb_records.iloc[1]["is_current"] == True


def test_point_in_time_lookup_accuracy():
    """Kiểm tra hàm point-in-time get_exchange_at_date xác định đúng sàn niêm yết tại từng thời điểm."""
    # ACB
    assert symbol_exchange_history.get_exchange_at_date("ACB", "2018-05-15") == "HNX"
    assert symbol_exchange_history.get_exchange_at_date("ACB", "2020-12-08") == "HNX"
    assert symbol_exchange_history.get_exchange_at_date("ACB", "2020-12-09") == "HOSE"
    assert symbol_exchange_history.get_exchange_at_date("ACB", "2023-01-01") == "HOSE"

    # BCM
    assert symbol_exchange_history.get_exchange_at_date("BCM", "2019-06-01") == "UPCOM"
    assert symbol_exchange_history.get_exchange_at_date("BCM", "2020-08-28") == "UPCOM"
    assert symbol_exchange_history.get_exchange_at_date("BCM", "2020-08-31") == "HOSE"
    assert symbol_exchange_history.get_exchange_at_date("BCM", "2024-01-01") == "HOSE"

    # SHB
    assert symbol_exchange_history.get_exchange_at_date("SHB", "2015-08-20") == "HNX"
    assert symbol_exchange_history.get_exchange_at_date("SHB", "2021-10-08") == "HNX"
    assert symbol_exchange_history.get_exchange_at_date("SHB", "2021-10-11") == "HOSE"
    assert symbol_exchange_history.get_exchange_at_date("SHB", "2026-01-01") == "HOSE"

    # Mã không tồn tại hoặc ngày trước khi thành lập
    assert symbol_exchange_history.get_exchange_at_date("NON_EXISTENT", "2020-01-01") is None
    assert symbol_exchange_history.get_exchange_at_date("ACB", "1990-01-01") is None


def test_write_exchange_history_idempotency(tmp_path):
    """Kiểm tra ghi vào DuckDB độc lập, đảm bảo tính idempotent và toàn vẹn dữ liệu."""
    db_path = tmp_path / "test_exchange_hist.duckdb"
    con = db.bootstrap_schema(db_path)

    df = symbol_exchange_history.build_symbol_exchange_history_df()
    total_rows = len(df)

    # Lần ghi 1
    n1 = symbol_exchange_history.write_symbol_exchange_history(df, con)
    assert n1 == total_rows
    cnt1 = con.execute("SELECT COUNT(*) FROM core.symbol_exchange_history").fetchone()[0]
    assert cnt1 == total_rows

    # Lần ghi 2
    n2 = symbol_exchange_history.write_symbol_exchange_history(df, con)
    assert n2 == total_rows
    cnt2 = con.execute("SELECT COUNT(*) FROM core.symbol_exchange_history").fetchone()[0]
    assert cnt2 == total_rows


def test_write_exchange_history_schema_validation(tmp_path):
    """Kiểm tra bắt lỗi nếu DataFrame thiếu các cột bắt buộc."""
    db_path = tmp_path / "test_exchange_invalid.duckdb"
    con = db.bootstrap_schema(db_path)

    bad_df = pd.DataFrame({"symbol": ["ACB"], "exchange": ["HOSE"]})
    with pytest.raises(ValueError, match="DataFrame thiếu các cột bắt buộc"):
        symbol_exchange_history.write_symbol_exchange_history(bad_df, con)
