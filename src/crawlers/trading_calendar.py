"""src/crawlers/trading_calendar.py

Lịch Giao Dịch & Quy Chuẩn Ngày Nghỉ Thị Trường Chứng Khoán Việt Nam (HOSE, HNX, UPCOM).
Bảo đảm kiểm soát tự động tiến trình cào dữ liệu theo quy luật giao dịch:
- Thứ Bảy & Chủ Nhật: Sở GDCK đóng cửa -> DỪNG cào OHLCV (nến 1m, 1D), chỉ số giá và đa tài sản.
- Ngày Nghỉ Lễ / Tết (Tết Dương lịch, Tết Nguyên Đán, Giỗ Tổ Hùng Vương, 30/4 - 1/5, Quốc khánh 2/9): DỪNG cào OHLCV.
- Tin tức tài chính (News Stream CafeF, Vietstock, văn bản pháp quy): VẪN HOẠT ĐỘNG 24/7 bình thường vì tin tức và thông báo doanh nghiệp vẫn được phát hành vào cuối tuần và ngày lễ.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional, Set, Tuple, Union

# =============================================================================
# DANH SÁCH NGÀY NGHỈ LỄ CHÍNH THỨC SỞ GDCK HOSE & HNX (2024 - 2027)
# (Bao gồm Tết Dương lịch, Tết Âm lịch, Giỗ Tổ, 30/4 - 1/5, Quốc khánh và ngày nghỉ bù)
# =============================================================================
VIETNAM_EXCHANGE_HOLIDAYS: Set[str] = {
    # --- NĂM 2024 ---
    "2024-01-01",  # Tết Dương lịch
    "2024-02-08", "2024-02-09", "2024-02-12", "2024-02-13", "2024-02-14",  # Tết Giáp Thìn (29 Tết đến mùng 5)
    "2024-04-18",  # Giỗ Tổ Hùng Vương (10/3 âm lịch)
    "2024-04-29", "2024-04-30", "2024-05-01",  # Ngày Thống nhất & Quốc tế Lao động
    "2024-09-02", "2024-09-03",  # Quốc khánh 2/9

    # --- NĂM 2025 ---
    "2025-01-01",  # Tết Dương lịch
    "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",  # Tết Ất Tỵ
    "2025-04-07",  # Giỗ Tổ Hùng Vương
    "2025-04-30", "2025-05-01", "2025-05-02",  # Chiến thắng 30/4 & Lao động 1/5
    "2025-09-01", "2025-09-02",  # Quốc khánh 2/9

    # --- NĂM 2026 ---
    "2026-01-01", "2026-01-02",  # Tết Dương lịch & ngày nghỉ liền kề
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",  # Tết Bính Ngọ (29 Tết đến mùng 4)
    "2026-04-27",  # Nghỉ bù Giỗ Tổ Hùng Vương (10/3 âm lịch rơi vào Chủ Nhật 26/04)
    "2026-04-30", "2026-05-01",  # Ngày Giải phóng miền Nam & Quốc tế Lao động
    "2026-09-01", "2026-09-02",  # Quốc khánh 2/9

    # --- NĂM 2027 ---
    "2027-01-01",  # Tết Dương lịch
    "2027-02-05", "2027-02-08", "2027-02-09", "2027-02-10", "2027-02-11",  # Tết Đinh Mùi
    "2027-04-16",  # Giỗ Tổ Hùng Vương
    "2027-04-30", "2027-05-03",  # 30/4 và nghỉ bù 1/5
    "2027-09-02", "2027-09-03",  # Quốc khánh 2/9
}

HOLIDAY_DESCRIPTIONS: Dict[str, str] = {
    "01-01": "Tết Dương Lịch",
    "04-30": "Ngày Giải Phóng Miền Nam (30/4)",
    "05-01": "Ngày Quốc Tế Lao Động (1/5)",
    "09-02": "Ngày Quốc Khánh Nước CHXHCN Việt Nam (2/9)",
}


def parse_date(date_val: Optional[Union[dt.date, dt.datetime, str]] = None) -> dt.date:
    """Chuẩn hóa đầu vào thành đối tượng datetime.date."""
    if date_val is None:
        return dt.date.today()
    if isinstance(date_val, dt.datetime):
        return date_val.date()
    if isinstance(date_val, dt.date):
        return date_val
    if isinstance(date_val, str):
        # Hỗ trợ YYYY-MM-DD
        return dt.datetime.strptime(date_val[:10], "%Y-%m-%d").date()
    return dt.date.today()


def is_weekend(target_date: Optional[Union[dt.date, str]] = None) -> bool:
    """Kiểm tra ngày mục tiêu có phải Thứ Bảy hoặc Chủ Nhật không."""
    d = parse_date(target_date)
    return d.weekday() in (5, 6)


def is_exchange_holiday(target_date: Optional[Union[dt.date, str]] = None) -> bool:
    """Kiểm tra ngày mục tiêu có phải ngày nghỉ lễ của HOSE/HNX hay không."""
    d = parse_date(target_date)
    date_str = d.strftime("%Y-%m-%d")
    return date_str in VIETNAM_EXCHANGE_HOLIDAYS


def is_trading_day(target_date: Optional[Union[dt.date, str]] = None) -> bool:
    """
    Kiểm tra xem ngày mục tiêu có phải là ngày giao dịch chứng khoán hợp lệ hay không.
    Trả về True chỉ khi là Thứ Hai đến Thứ Sáu VÀ không phải ngày nghỉ lễ/Tết.
    """
    d = parse_date(target_date)
    if is_weekend(d):
        return False
    if is_exchange_holiday(d):
        return False
    return True


def should_skip_ohlcv_crawl(
    target_date: Optional[Union[dt.date, str]] = None,
    force: bool = False,
) -> Tuple[bool, str]:
    """
    Kiểm tra xem có cần BỎ QUA cào OHLCV và chỉ số giá hay không.
    Nếu force=True, luôn trả về False (cho phép cào cưỡng bức khi test).
    
    Returns:
        (should_skip: bool, reason_description: str)
    """
    if force:
        return False, "FORCE_ENABLED: Cưỡng bức thu thập theo yêu cầu."

    d = parse_date(target_date)
    date_str = d.strftime("%Y-%m-%d")
    weekday_idx = d.weekday()

    if weekday_idx == 5:
        return True, f"Thứ Bảy ({date_str}) - Thị trường đóng cửa cuối tuần. Không có giao dịch khớp lệnh."
    if weekday_idx == 6:
        return True, f"Chủ Nhật ({date_str}) - Thị trường đóng cửa cuối tuần. Không có giao dịch khớp lệnh."

    if date_str in VIETNAM_EXCHANGE_HOLIDAYS:
        mmdd = date_str[5:]
        desc = HOLIDAY_DESCRIPTIONS.get(mmdd, "Kỳ Nghỉ Lễ / Tết Âm Lịch Sở GDCK")
        return True, f"Ngày Nghỉ Lễ ({date_str}: {desc}) - Thị trường tạm ngừng giao dịch theo quy định UBCKNN."

    return False, "Ngày làm việc bình thường (Monday - Friday). Thị trường mở cửa giao dịch."


def get_market_status(target_date: Optional[Union[dt.date, str]] = None) -> Dict[str, Any]:
    """
    Trả về cấu trúc trạng thái chi tiết của thị trường tại ngày chỉ định.
    """
    d = parse_date(target_date)
    date_str = d.strftime("%Y-%m-%d")
    is_trad = is_trading_day(d)
    skip_ohlcv, reason = should_skip_ohlcv_crawl(d)

    status_code = "TRADING_ACTIVE"
    if d.weekday() == 5:
        status_code = "WEEKEND_SATURDAY"
    elif d.weekday() == 6:
        status_code = "WEEKEND_SUNDAY"
    elif not is_trad:
        status_code = "PUBLIC_HOLIDAY"

    return {
        "date": date_str,
        "weekday": d.strftime("%A"),
        "weekday_number": d.weekday(),
        "is_trading_day": is_trad,
        "status_code": status_code,
        "reason": reason,
        "can_crawl_ohlcv": not skip_ohlcv,
        "can_crawl_indices": not skip_ohlcv,
        "can_crawl_derivatives": not skip_ohlcv,
        "can_crawl_news": True,  # Tin tức luôn luôn được phép cào
    }
