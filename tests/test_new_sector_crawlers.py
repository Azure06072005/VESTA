"""Unit tests cho các bộ cào ngành hợp lệ và xác thực cấm các trang bị decommission.

Tests verify:
1. Article detail extraction and mapping to canonical 11 columns in macro_policy cho các nguồn hợp lệ.
2. Xác nhận cơ chế Ethical Crawling từ chối tuyệt đối toàn bộ 17 website bị cấm/chặn (WAF, 403, 429).
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.crawl_policy import is_url_allowed, is_source_allowed
from crawlers.vsa_crawler import parse_vsa_article
from crawlers.vla_crawler import parse_vla_article
from crawlers.hoidaukhi_crawler import parse_hdk_article
from crawlers.thoibaotaichinh_crawler import parse_tbtc_article
from crawlers.vietnamfinance_crawler import parse_vnf_article
from crawlers.vntextile_crawler import parse_vitas_article
from crawlers.vnpca_crawler import parse_vnpca_article
from crawlers.vra_crawler import parse_vra_article
from crawlers.nhandan_crawler import parse_nhandan_article


# ==============================================================================
# 1. VERIFICATION CÁC NGUỒN CÀO HỢP LỆ (LEGAL & COMPLIANT CRAWLERS)
# ==============================================================================

def test_vsa_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VSA chuẩn 11 cột."""
    html = """
    <html>
      <body>
        <h1>Bản tin thị trường thép xây dựng tháng 8 năm 2026</h1>
        <time datetime="2026-08-15T08:00:00Z">15/08/2026</time>
        <p>Sản lượng tiêu thụ thép xây dựng và thép cuộn cán nóng HRC đạt mức tăng trưởng 18% so với cùng kỳ.</p>
        <p>Bộ Công Thương đang tiến hành thẩm tra vụ việc điều tra chống bán phá giá AD01 theo Quyết định 1535/QĐ-BCT.</p>
      </body>
    </html>
    """
    rec = parse_vsa_article(html, "https://vsa.com.vn/ban-tin-thep-thang-8-2026/", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vsa"
    assert rec["issuing_body"] == "Hiệp hội Thép Việt Nam (VSA)"
    assert rec["doc_type"] == "STEEL_INDUSTRY"
    assert "1535/QĐ-BCT" in rec["body"] or rec["doc_number"] is not None
    assert "HRC" in rec["body"]


def test_vla_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết logistics VLA chuẩn 11 cột."""
    html = """
    <html>
      <body>
        <h1 class="entry-title">Cập nhật giá cước vận tải container quốc tế tuyến Á - Mỹ</h1>
        <time datetime="2026-09-01T09:00:00Z">01/09/2026</time>
        <p>Chỉ số cước vận tải biển toàn cầu biến động mạnh do tình hình gián đoạn tại khu vực Biển Đỏ.</p>
        <p>Hiệp hội Doanh nghiệp Dịch vụ Logistics Việt Nam khuyến nghị các doanh nghiệp chủ động đàm phán hợp đồng dài hạn.</p>
      </body>
    </html>
    """
    rec = parse_vla_article(html, "https://vla.com.vn/cap-nhat-gia-cuoc-2026/", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vla"
    assert rec["issuing_body"] == "Hiệp hội Doanh nghiệp Dịch vụ Logistics Việt Nam (VLA)"
    assert "Biển Đỏ" in rec["body"]


def test_hoidaukhi_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết Hội Dầu Khí chuẩn 11 cột."""
    html = """
    <html>
      <body>
        <h1>Tiến độ triển khai chuỗi dự án khí điện Lô B - Ô Môn năm 2026</h1>
        <time datetime="2026-08-20T10:00:00Z">20/08/2026</time>
        <p>Chuỗi dự án Lô B đóng vai trò hạt nhân cung cấp nguồn khí tự nhiên bền vững cho trung tâm điện lực Ô Môn.</p>
        <p>Hội Dầu khí Việt Nam đề xuất các giải pháp tháo gỡ vướng mắc về cơ chế tiêu thụ khí theo Nghị quyết 55-NQ/TW.</p>
      </body>
    </html>
    """
    rec = parse_hdk_article(html, "https://hoidaukhi.vn/tien-do-lo-b-o-mon-2026/", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "hoidaukhi"
    assert rec["issuing_body"] == "Hội Dầu khí Việt Nam (VPA)"
    assert rec["doc_type"] == "ENERGY_POLICY"
    assert "Lô B" in rec["body"]


def test_thoibaotaichinh_crawler_parsing() -> None:
    """Kiểm tra bóc tách tin tức tài chính Thời báo Tài chính Việt Nam chuẩn 11 cột."""
    html = """
    <html>
      <body>
        <h1 class="article-title">Thị trường chứng khoán Việt Nam đón dòng vốn ngoại trở lại trong quý 3</h1>
        <div class="article-date">05/09/2026 08:30</div>
        <p>Ủy ban Chứng khoán Nhà nước tích cực triển khai các tiêu chuẩn FTSE Russell để nâng hạng thị trường chứng khoán theo Quyết định 1726/QĐ-TTg.</p>
        <p>Tổng giá trị giao dịch toàn thị trường tăng mạnh, khẳng định vị thế trung tâm tài chính đang được hoàn thiện.</p>
      </body>
    </html>
    """
    rec = parse_tbtc_article(html, "https://thoibaotaichinhvietnam.vn/chung-khoan/thi-truong-chung-khoan-don-dong-von-ngoai.html", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "thoibaotaichinh"
    assert rec["issuing_body"] == "Thời báo Tài chính Việt Nam (Bộ Tài chính)"
    assert rec["doc_type"] == "FISCAL_NEWS"
    assert "FTSE Russell" in rec["body"]


def test_vietnamfinance_crawler_parsing() -> None:
    """Kiểm tra bóc tách tin tức VietnamFinance chuẩn 11 cột."""
    html = """
    <html>
      <body>
        <h1 class="title">Thu hút vốn đầu tư FDI vào các khu công nghiệp tăng trưởng vượt bậc</h1>
        <time>03/09/2026 14:15</time>
        <p>Báo cáo của Cục Đầu tư nước ngoài cho thấy dòng vốn FDI giải ngân vào lĩnh vực công nghệ cao và bán dẫn đạt kỷ lục mới.</p>
        <p>Nhiều dự án hạ tầng lớn đang đẩy nhanh tiến độ nhằm đón đầu làn sóng dịch chuyển chuỗi cung ứng toàn cầu.</p>
      </body>
    </html>
    """
    rec = parse_vnf_article(html, "https://vietnamfinance.vn/thu-hut-von-fdi-khu-cong-nghiep.htm", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vietnamfinance"
    assert rec["issuing_body"] == "VietnamFinance (Tạp chí Đầu tư Tài chính)"
    assert rec["doc_type"] == "MARKET_NEWS"
    assert "FDI" in rec["body"]


def test_vntextile_crawler_parsing() -> None:
    """Kiểm tra bóc tách ngành Dệt May VITAS chuẩn 11 cột."""
    html = """
    <html>
      <body>
        <h1 class="entry-title">Kim ngạch xuất khẩu dệt may Việt Nam đạt mốc 44 tỷ USD</h1>
        <span>Ngày đăng: 02/09/2026</span>
        <p>Hiệp hội Dệt May Việt Nam (VITAS) công bố kết quả xuất khẩu tích cực sang thị trường Hoa Kỳ và Liên minh Châu Âu (EU).</p>
        <p>Các doanh nghiệp may mặc hàng đầu như May Sông Hồng, Dệt May Thành Công chủ động chuyển đổi sang sản xuất xanh theo chuẩn ESG.</p>
      </body>
    </html>
    """
    rec = parse_vitas_article(html, "https://vitas.org.vn/kim-ngach-xuat-khau-det-may-2026", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vntextile"
    assert rec["issuing_body"] == "Hiệp hội Dệt May Việt Nam (VITAS)"
    assert rec["doc_type"] == "TEXTILE_INDUSTRY"
    assert "VITAS" in rec["body"]


def test_vnpca_crawler_parsing() -> None:
    """Kiểm tra bóc tách ngành Dược phẩm VNPCA chuẩn 11 cột."""
    html = """
    <html>
      <body>
        <h1 class="post-title">Đẩy mạnh sản xuất thuốc generic đạt chuẩn EU-GMP tại Việt Nam</h1>
        <span>25/08/2026</span>
        <p>Hiệp hội Doanh nghiệp Dược Việt Nam (VNPCA) kiến nghị đẩy nhanh tiến độ gia hạn số đăng ký lưu hành thuốc theo Luật Dược sửa đổi.</p>
        <p>Dược Hậu Giang, Traphaco và Imexpharm tiếp tục nâng cấp dây chuyền sản xuất tiêu chuẩn quốc tế để phục vụ kênh đấu thầu bệnh viện ETC.</p>
      </body>
    </html>
    """
    rec = parse_vnpca_article(html, "https://vnpca.org.vn/tin-tuc/san-xuat-thuoc-generic-eu-gmp", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vnpca"
    assert rec["issuing_body"] == "Hiệp hội Doanh nghiệp Dược Việt Nam (VNPCA)"
    assert rec["doc_type"] == "PHARMA_INDUSTRY"
    assert "Dược Hậu Giang" in rec["body"]


def test_vra_crawler_parsing() -> None:
    """Kiểm tra bóc tách ngành Cao su VRA chuẩn 11 cột."""
    html = """
    <html>
      <body>
        <h1 class="entry-title">Giá mủ cao su thiên nhiên phục hồi mạnh mẽ trên thị trường thế giới</h1>
        <div class="meta-date">18/08/2026</div>
        <p>Hiệp hội Cao su Việt Nam (VRA) cho biết giá cao su xuất khẩu tăng do nguồn cung hạn chế tại các nước Đông Nam Á.</p>
        <p>Tập đoàn Công nghiệp Cao su Việt Nam (GVR) và Cao su Phước Hòa tiếp tục đẩy mạnh các dự án phát triển rừng cao su bền vững FSC.</p>
      </body>
    </html>
    """
    rec = parse_vra_article(html, "https://vra.com.vn/gia-mu-cao-su-thien-nhien-2026", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vra"
    assert rec["issuing_body"] == "Hiệp hội Cao su Việt Nam (VRA)"
    assert rec["doc_type"] == "RUBBER_INDUSTRY"
    assert "GVR" in rec["body"]


def test_nhandan_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết Báo Nhân Dân chuẩn 11 cột."""
    html = """
    <html>
      <body>
        <h1 class="title">Chính phủ ban hành kế hoạch hành động thực hiện Nghị quyết phát triển kinh tế vùng</h1>
        <div class="time">05/09/2026 15:30</div>
        <p>Thủ tướng Chính phủ yêu cầu các bộ, ngành đẩy nhanh giải ngân vốn đầu tư công các dự án đường cao tốc trọng điểm.</p>
      </body>
    </html>
    """
    rec = parse_nhandan_article(html, "https://nhandan.vn/ke-hoach-hanh-dong-kinh-te-vung-post12345.html", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "nhandan"
    assert "đầu tư công" in rec["body"]


# ==============================================================================
# 2. KIỂM THỬ XÁC THỰC TOÀN BỘ CÁC SITE BỊ CẤM / BỊ CHẶN BỊ LOẠI BỎ TRIỆT ĐỂ
# ==============================================================================

def test_all_decommissioned_forbidden_sites_blocked() -> None:
    """Xác nhận toàn diện các site bị cấm cào vĩnh viễn và bị chặn 100% bởi Crawl Policy."""
    forbidden_urls = [
        "https://sbv.gov.vn/vi/tin-tuc-su-kien",
        "https://thuvienphapluat.vn/chinh-sach-phap-luat-moi",
        "https://luatvietnam.vn/tin-phap-luat.html",
        "https://vnba.com.vn/tin-tuc-ngan-hang",
        "https://vnba.org.vn/vi/tin-hoat-dong-vnba",
        "https://vinasme.com.vn/tin-tuc",
        "https://vfaea.org.vn/tin-tuc",
        "https://vpsaspice.org.vn/tin-nganh-hang",
        "https://huba.vn/tin-doanh-nghiep",
        "https://vacod.com.vn/hoat-dong",
        "https://vama.org.vn/doanh-so",
        "https://vafie.org.vn/dau-tu-fdi",
        "https://viea.vn/nang-luong-sach",
        "https://vecom.vn/thuong-mai-dien-tu",
        "https://via.org.vn/chuyen-doi-so",
        "https://avnuc.vn/giao-duc",
        "https://hhbvt.vn/y-te-tu-nhan",
        "https://vusta.vn/khoa-hoc-ky-thuat",
        "https://baodautu.vn/tai-chinh-ngan-hang",
        "https://tuoitre.vn/kinh-doanh.htm",
        "https://tienphong.vn/kinh-te/",
        "https://nguoiquansat.vn/thi-truong-chung-khoan",
        "https://tapchicongthuong.vn/thuong-mai",
    ]

    for url in forbidden_urls:
        allowed, reason = is_url_allowed(url)
        assert not allowed, f"URL {url} đáng lẽ phải bị cấm nhưng lại được cho phép!"
        assert "CẤM VĨNH VIỄN" in reason

    forbidden_ids = [
        "sbv", "sbv_policy", "thuvienphapluat", "luatvietnam", "vnba",
        "vinasme", "vfaea", "vpsaspice", "huba", "vacod", "vama",
        "vafie", "viea", "vecom", "via", "avnuc", "hhbvt", "vusta",
        "baodautu", "tuoitre", "tienphong", "nguoiquansat", "tapchicongthuong", "tcct",
    ]

    for fid in forbidden_ids:
        assert not is_source_allowed(fid), f"Source ID '{fid}' đáng lẽ phải bị cấm nhưng lại được cho phép!"
