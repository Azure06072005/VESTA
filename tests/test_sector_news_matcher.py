import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeline.sector_news_matcher import (
    match_sector_tier_a,
    match_sector_tier_b,
)


@pytest.fixture
def mock_symbol_sector_map():
    return {
        # Sector 3: Bất động sản
        "VIC": (3, "Bất động sản"),
        "VHM": (3, "Bất động sản"),
        "NVL": (3, "Bất động sản"),
        "PDR": (3, "Bất động sản"),
        "DXG": (3, "Bất động sản"),
        # Sector 11: Ngân hàng
        "VCB": (11, "Ngân hàng"),
        "BID": (11, "Ngân hàng"),
        "CTG": (11, "Ngân hàng"),
        "TCB": (11, "Ngân hàng"),
        # Sector 5: Chứng khoán
        "SSI": (5, "Chứng khoán"),
        "VND": (5, "Chứng khoán"),
        "HCM": (5, "Chứng khoán"),
        # Sector 21: Vật liệu xây dựng
        "HPG": (21, "Vật liệu xây dựng"),
        "NKG": (21, "Vật liệu xây dựng"),
        # Sector 6: Công nghệ
        "FPT": (6, "Công nghệ và thông tin"),
        # Sector 19: Thực phẩm
        "VNM": (19, "Thực phẩm - Đồ uống"),
    }


@pytest.fixture
def valid_symbols(mock_symbol_sector_map):
    return set(mock_symbol_sector_map.keys())


# ====================================================================
# TEST TIER A: POSITIVE CASES (Explicit sector keywords with market anchors)
# ====================================================================
@pytest.mark.parametrize(
    "title,expected_sector_id,expected_sector_name",
    [
        ("Nhóm cổ phiếu bất động sản đồng loạt giảm sàn phiên chiều", 3, "Bất động sản"),
        ("Cổ phiếu ngành ngân hàng bứt phá mạnh mẽ dẫn dắt VN-Index", 11, "Ngân hàng"),
        ("Sóng cổ phiếu chứng khoán bùng nổ trong phiên ATC", 5, "Chứng khoán"),
        ("Các mã cổ phiếu ngành thép đua nhau tăng trần", 21, "Vật liệu xây dựng"),
        ("Dòng tiền ngoại gom mạnh cổ phiếu dầu khí", 10, "Khai khoáng"),
        ("Rổ cổ phiếu công nghệ thông tin hút dòng tiền thông minh", 6, "Công nghệ và thông tin"),
        ("Cổ phiếu nhóm thủy sản đón sóng xuất khẩu cuối năm", 20, "Chế biến Thủy sản"),
        ("Nhóm ngành bán lẻ phục hồi ấn tượng", 7, "Bán lẻ"),
        ("Cổ phiếu ngành xây dựng hưởng lợi từ giải ngân đầu tư công", 24, "Xây dựng"),
    ],
)
def test_tier_a_positive_matches(title, expected_sector_id, expected_sector_name):
    matches = match_sector_tier_a(title, url="https://cafef.vn/art-1.chn")
    assert len(matches) >= 1
    matched_ids = [m["sector_id"] for m in matches]
    matched_names = [m["sector_name"] for m in matches]
    assert expected_sector_id in matched_ids
    assert expected_sector_name in matched_names


# ====================================================================
# TEST TIER A: NEGATIVE CASES (Civil / administrative / non-market traps)
# ====================================================================
@pytest.mark.parametrize(
    "headline",
    [
        # Pure administrative policy (no market anchor)
        "Bộ Xây dựng ban hành thông tư mới về quản lý bất động sản",
        "Bộ Tài chính đề xuất sửa đổi nghị định quản lý thuế bất động sản",
        "Bất động sản Hà Nội: Giá thuê văn phòng quý 3 có xu hướng giảm nhẹ",
        "Thép Trung Quốc ồ ạt tràn vào đe dọa ngành thép Việt Nam",
        "Nhu cầu tiêu thụ sữa tại khu vực nông thôn tiếp tục tăng trưởng",
        "Xuất khẩu dầu khí cả nước đạt kim ngạch 5 tỷ USD trong 8 tháng",
        "Thị trường phân bón thế giới biến động mạnh do xung đột địa chính trị",
        "Dự thảo quy định mới về phát triển nhà ở xã hội tại TP.HCM",
        "Ngân hàng Nhà nước duy trì mặt bằng lãi suất điều hành",
    ],
)
def test_tier_a_negative_traps_fail_closed(headline):
    matches = match_sector_tier_a(headline, url="https://cafef.vn/art-neg.chn")
    assert matches == []


# ====================================================================
# TEST TIER B: MULTI-SYMBOL COMPANY CO-OCCURRENCE
# ====================================================================
def test_tier_b_positive_same_sector(mock_symbol_sector_map, valid_symbols):
    # VIC, NVL, PDR all belong to Sector 3 (Bất động sản)
    title = "VIC, NVL, PDR đồng loạt giảm sàn phiên hôm nay"
    matches = match_sector_tier_b(title, mock_symbol_sector_map, valid_symbols)
    assert len(matches) == 1
    assert matches[0]["sector_id"] == 3
    assert matches[0]["sector_name"] == "Bất động sản"
    assert "VIC" in matches[0]["matched_keyword"]
    assert "NVL" in matches[0]["matched_keyword"]


def test_tier_b_negative_cross_sectors(mock_symbol_sector_map, valid_symbols):
    # VIC (BĐS), FPT (CNTT), VNM (Thực phẩm) - 3 different sectors
    title = "VIC, FPT, VNM diễn biến phân hóa trong phiên giao dịch"
    matches = match_sector_tier_b(title, mock_symbol_sector_map, valid_symbols)
    assert matches == []


def test_tier_b_single_symbol_does_not_trigger(mock_symbol_sector_map, valid_symbols):
    # Only 1 symbol (VIC) - must NOT trigger sector fan-out
    title = "VIC bất ngờ tăng mạnh cuối phiên"
    matches = match_sector_tier_b(title, mock_symbol_sector_map, valid_symbols)
    assert matches == []
