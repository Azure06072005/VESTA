"""Unit tests for newly integrated sectoral crawlers (VNBA, VSA, VLA, Hội Dầu khí).

Tests verify:
1. Listing parsing and link discovery for each website.
2. Article detail extraction and mapping to canonical 11 columns in macro_policy.
3. Crawl delay compliance and deduplication logic.
"""

from __future__ import annotations

import datetime as dt
import pytest

from src.crawlers.vnba_crawler import parse_vnba_article, parse_vnba_date
from src.crawlers.vsa_crawler import parse_vsa_article
from src.crawlers.vla_crawler import parse_vla_article
from src.crawlers.hoidaukhi_crawler import parse_hdk_article

SAMPLE_HTML = """
<html>
  <head><title>Test Article</title></head>
  <body>
    <h1>Quy định mới về tỷ lệ an toàn vốn ngân hàng</h1>
    <span>Thứ hai, 07/09/2026</span>
    <p>Theo Thông tư 41/2016/TT-NHNN, các ngân hàng thương mại phải duy trì tỷ lệ an toàn vốn CAR tối thiểu 8%.</p>
    <p>Hiệp hội Ngân hàng Việt Nam (VNBA) đề nghị tiếp tục gia hạn một số chỉ tiêu tín dụng cho các doanh nghiệp vừa và nhỏ.</p>
  </body>
</html>
"""


def test_vnba_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VNBA chuẩn 11 cột."""
    rec = parse_vnba_article(SAMPLE_HTML, "https://vnba.org.vn/vi/test-article-1.htm", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vnba"
    assert rec["issuing_body"] == "Hiệp hội Ngân hàng Việt Nam (VNBA)"
    assert rec["headline"] == "Quy định mới về tỷ lệ an toàn vốn ngân hàng"
    assert rec["doc_number"] == "41/2016/TT-NHNN"
    assert "CAR tối thiểu 8%" in rec["body"]
    assert "source_url" in rec
    assert "fetched_at" in rec


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


def test_thuvienphapluat_crawler_parsing() -> None:
    """Kiểm tra bóc tách văn bản pháp luật Thư Viện Pháp Luật chuẩn 11 cột."""
    from src.crawlers.thuvienphapluat_crawler import parse_tvpl_article

    html = """
    <html>
      <body>
        <h1>Nghị định 52/2024/NĐ-CP về thanh toán không dùng tiền mặt</h1>
        <span>Ngày ban hành: 15/05/2024</span>
        <p>Chính phủ ban hành Nghị định 52/2024/NĐ-CP quy định chi tiết về hoạt động thanh toán không dùng tiền mặt tại Việt Nam.</p>
        <p>Nghị định này điều chỉnh việc mở và sử dụng tài khoản thanh toán, dịch vụ trung gian thanh toán và hệ thống thanh toán quốc tế.</p>
      </body>
    </html>
    """
    rec = parse_tvpl_article(html, "https://thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/nghi-dinh-52-2024-nd-cp", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "thuvienphapluat"
    assert rec["issuing_body"] == "Thư Viện Pháp Luật"
    assert rec["doc_type"] == "LEGAL_POLICY"
    assert rec["doc_number"] == "52/2024/NĐ-CP"
    assert "thanh toán không dùng tiền mặt" in rec["body"]


def test_luatvietnam_crawler_parsing() -> None:
    """Kiểm tra bóc tách văn bản pháp luật Luật Việt Nam chuẩn 11 cột."""
    from src.crawlers.luatvietnam_crawler import parse_lvn_article

    html = """
    <html>
      <body>
        <h1 class="the-article-title">Thông tư 12/2024/TT-NHNN hướng dẫn quản lý ngoại hối đối với vay trả nợ nước ngoài</h1>
        <div class="the-article-meta">Ngày đăng: 28/06/2024</div>
        <p>Ngân hàng Nhà nước Việt Nam ban hành Thông tư 12/2024/TT-NHNN hướng dẫn các biện pháp quản lý rủi ro tỷ giá và đăng ký hạn mức vay nước ngoài.</p>
        <p>Các tổ chức tín dụng phải báo cáo định kỳ dòng vốn chuyển giao quốc tế theo đúng quy chuẩn an toàn vĩ mô.</p>
      </body>
    </html>
    """
    rec = parse_lvn_article(html, "https://luatvietnam.vn/ngan-hang/thong-tu-12-2024-tt-nhnn.html", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "luatvietnam"
    assert rec["issuing_body"] == "Luật Việt Nam (LuatVietnam.vn)"
    assert rec["doc_type"] == "LEGAL_POLICY"
    assert rec["doc_number"] == "12/2024/TT-NHNN"
    assert "quản lý ngoại hối" in rec["headline"]
    assert "quản lý rủi ro" in rec["body"]


def test_thoibaotaichinh_crawler_parsing() -> None:
    """Kiểm tra bóc tách tin tức tài chính Thời báo Tài chính Việt Nam chuẩn 11 cột."""
    from src.crawlers.thoibaotaichinh_crawler import parse_tbtc_article

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
    assert "1726/QĐ-TTg" in rec["body"] or rec["doc_number"] is not None
    assert "FTSE Russell" in rec["body"]


def test_vietnamfinance_crawler_parsing() -> None:
    """Kiểm tra bóc tách tin tức VietnamFinance chuẩn 11 cột."""
    from src.crawlers.vietnamfinance_crawler import parse_vnf_article

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
    from src.crawlers.vntextile_crawler import parse_vitas_article

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
    from src.crawlers.vnpca_crawler import parse_vnpca_article

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
    assert "EU-GMP" in rec["headline"]


def test_vfaea_crawler_parsing() -> None:
    """Kiểm tra bóc tách ngành Phân bón VFAEA chuẩn 11 cột."""
    from src.crawlers.vfaea_crawler import parse_vfaea_article

    html = """
    <html>
      <body>
        <h1>Xuất khẩu phân bón Ure và NPK duy trì đà tăng trưởng ổn định</h1>
        <div class="date">22/08/2026</div>
        <p>Hiệp hội Phân bón Việt Nam đề xuất áp dụng thuế suất thuế GTGT 5% đối với mặt hàng phân bón để hỗ trợ các nhà sản xuất nội địa.</p>
        <p>Đạm Phú Mỹ và Đạm Cà Mau bảo đảm cung ứng đầy đủ nguồn cung phân bón chất lượng cao cho vụ mùa thu đông.</p>
      </body>
    </html>
    """
    rec = parse_vfaea_article(html, "https://vfaea.vn/tin-tuc/xuat-khau-phan-bon-2026", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vfaea"
    assert rec["issuing_body"] == "Hiệp hội Phân bón Việt Nam (VFAEA)"
    assert rec["doc_type"] == "FERTILIZER_INDUSTRY"
    assert "Đạm Phú Mỹ" in rec["body"]


def test_vra_crawler_parsing() -> None:
    """Kiểm tra bóc tách ngành Cao su VRA chuẩn 11 cột."""
    from src.crawlers.vra_crawler import parse_vra_article

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


def test_nguoiquansat_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài phân tích Người Quan Sát chuẩn 11 cột."""
    from src.crawlers.nguoiquansat_crawler import parse_nqs_article

    html = """
    <html>
      <body>
        <h1 class="the-article-title">Dòng tiền lớn đổ mạnh vào nhóm cổ phiếu VN30 giúp chỉ số vượt đỉnh</h1>
        <div class="the-article-meta">Ngày đăng: 07/09/2026</div>
        <p>Thị trường chứng khoán ghi nhận thanh khoản bùng nổ, khối ngoại đẩy mạnh mua ròng các mã ngân hàng và chứng khoán.</p>
        <p>Ủy ban Chứng khoán Nhà nước tiếp tục thúc đẩy triển khai hệ thống giao dịch KRX theo Quyết định 1726/QĐ-TTg.</p>
      </body>
    </html>
    """
    rec = parse_nqs_article(html, "https://nguoiquansat.vn/dong-tien-lon-vn30-12345.html", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "nguoiquansat"
    assert rec["issuing_body"] == "Người Quan Sát (Nguoiquansat.vn)"
    assert rec["doc_type"] == "EQUITY_COMMENTARY"
    assert "VN30" in rec["headline"]
    assert "thanh khoản bùng nổ" in rec["body"]


def test_tapchicongthuong_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết Tạp chí Công Thương chuẩn 11 cột."""
    from src.crawlers.tapchicongthuong_crawler import parse_tcct_article

    html = """
    <html>
      <body>
        <h1 class="title-detail">Bộ Công Thương đẩy mạnh phát triển năng lượng tái tạo và điện khí LNG</h1>
        <div class="date-time">04/09/2026 09:15</div>
        <p>Triển khai Quy hoạch Điện VIII, Bộ Công Thương đang hoàn thiện cơ chế mua bán điện trực tiếp DPPA theo Nghị định 80/2024/NĐ-CP.</p>
        <p>Các tập đoàn năng lượng đẩy nhanh tiến độ đầu tư để đảm bảo an ninh năng lượng quốc gia.</p>
      </body>
    </html>
    """
    rec = parse_tcct_article(html, "https://tapchicongthuong.vn/phat-trien-nang-luong-tai-tao-89123.htm", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "tcct"
    assert rec["issuing_body"] == "Tạp chí Công Thương (Bộ Công Thương)"
    assert rec["doc_type"] == "SECTOR_MAGAZINE"
    assert "80/2024/NĐ-CP" in rec["body"] or rec["doc_number"] is not None
    assert "Điện VIII" in rec["body"]


def test_nhandan_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết Báo Nhân Dân chuẩn 11 cột."""
    from src.crawlers.nhandan_crawler import parse_nhandan_article

    html = """
    <html>
      <body>
        <h1 class="title">Chính phủ ban hành kế hoạch hành động thực hiện Nghị quyết phát triển kinh tế vùng</h1>
        <div class="time">05/09/2026 15:30</div>
        <p>Thủ tướng Chính phủ yêu cầu các bộ, ngành đẩy nhanh giải ngân vốn đầu tư công các dự án đường cao tốc trọng điểm.</p>
        <p>Mục tiêu tăng trưởng GDP cả nước năm 2026 phấn đấu đạt từ 6,5% đến 7% theo Nghị quyết của Quốc hội.</p>
      </body>
    </html>
    """
    rec = parse_nhandan_article(html, "https://nhandan.vn/ke-hoach-hanh-dong-kinh-te-vung-post12345.html", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "nhandan"
    assert rec["issuing_body"] == "Báo Nhân Dân (Cơ quan ngôn luận Trung ương Đảng)"
    assert rec["doc_type"] == "OFFICIAL_PRESS"
    assert "đầu tư công" in rec["body"]


def test_tienphong_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết Báo Tiền Phong chuẩn 11 cột."""
    from src.crawlers.tienphong_crawler import parse_tienphong_article

    html = """
    <html>
      <body>
        <h1 class="article__title">Thị trường bất động sản khu công nghiệp đón làn sóng đầu tư mới</h1>
        <div class="article__time">06/09/2026 11:20</div>
        <p>Nhu cầu thuê đất công nghiệp tại Bình Dương, Bắc Ninh và Hải Phòng tăng cao nhờ dòng vốn FDI giải ngân mạnh mẽ.</p>
        <p>Các doanh nghiệp phát triển hạ tầng khu công nghiệp đẩy mạnh mở rộng quỹ đất theo quy hoạch mới.</p>
      </body>
    </html>
    """
    rec = parse_tienphong_article(html, "https://tienphong.vn/bat-dong-san-khu-cong-nghiep-don-song-fdi-post12345.tpo", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "tienphong"
    assert rec["issuing_body"] == "Báo Tiền Phong (Tienphong.vn)"
    assert rec["doc_type"] == "FINANCIAL_MEDIA"
    assert "FDI" in rec["body"]


def test_vecom_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VECOM chuẩn 11 cột."""
    from src.crawlers.vecom_crawler import parse_vecom_article

    html = """
    <html>
      <body>
        <h1>Báo cáo Chỉ số Thương mại điện tử Việt Nam EBI năm 2026</h1>
        <time datetime="2026-08-25">25/08/2026</time>
        <p>Quy mô thị trường thương mại điện tử Việt Nam tiếp tục duy trì tốc độ tăng trưởng trên 25% mỗi năm.</p>
        <p>Các doanh nghiệp bán lẻ công nghệ như MWG, DGW và FPT Shop đẩy mạnh mô hình bán hàng đa kênh omnichannel.</p>
      </body>
    </html>
    """
    rec = parse_vecom_article(html, "https://vecom.vn/bao-cao-ebi-2026.html", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vecom"
    assert rec["issuing_body"] == "Hiệp hội Thương mại Điện tử Việt Nam (VECOM)"
    assert rec["doc_type"] == "ECOMMERCE_TECH"
    assert "MWG" in rec["body"]


def test_vama_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VAMA chuẩn 11 cột."""
    from src.crawlers.vama_crawler import parse_vama_article

    html = """
    <html>
      <body>
        <h1>Báo cáo doanh số bán hàng thị trường ô tô toàn quốc tháng 8 năm 2026</h1>
        <span class="date">05/09/2026</span>
        <p>Doanh số bán ô tô của các đơn vị thành viên VAMA tăng mạnh nhờ chính sách giảm lệ phí trước bạ.</p>
        <p>Phân khúc xe điện và xe hybrid ghi nhận mức tăng trưởng vượt bậc so với cùng kỳ.</p>
      </body>
    </html>
    """
    rec = parse_vama_article(html, "http://vama.org.vn/doanh-so-thang-8-2026.html", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "vama"
    assert rec["issuing_body"] == "Hiệp hội các Nhà sản xuất Ô tô Việt Nam (VAMA)"
    assert rec["doc_type"] == "AUTOMOTIVE_INDUSTRY"
    assert "lệ phí trước bạ" in rec["body"]


def test_vafie_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VAFIE chuẩn 11 cột."""
    from src.crawlers.vafie_crawler import parse_vafie_article

    html = """
    <html>
      <body>
        <h1>Kinh tế tư nhân cần lớn lên trong hệ sinh thái liên kết với FDI</h1>
        <div class="date">04/09/2026 11:17</div>
        <p>Tại Hội thảo giải pháp tài chính kinh tế tư nhân, nhiều chuyên gia đề xuất tăng cường liên kết chuỗi cung ứng FDI.</p>
        <p>Các khu công nghiệp của KBC, BCM, IDC đang thu hút dòng vốn đầu tư công nghệ cao từ Mỹ và EU.</p>
      </body>
    </html>
    """
    rec = parse_vafie_article(html, "https://vafie.org.vn/kinh-te-tu-nhan-lien-ket-fdi-d858.html")
    assert rec is not None
    assert rec["source"] == "vafie"
    assert rec["issuing_body"] == "Hiệp hội Doanh nghiệp Đầu tư Nước ngoài (VAFIE)"
    assert rec["doc_type"] == "FDI_INVESTMENT"
    assert "KBC" in rec["body"]


def test_viea_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VEIA chuẩn 11 cột."""
    from src.crawlers.viea_crawler import parse_viea_article

    html = """
    <html>
      <body>
        <h1>Mở rộng kết nối chuỗi cung ứng điện tử bán dẫn và robot cao cấp</h1>
        <time>03/09/2026</time>
        <p>Hiệp hội Doanh nghiệp Điện tử Việt Nam chủ trì kết nối các nhà sản xuất linh kiện vi mạch bán dẫn.</p>
        <p>Mục tiêu nâng cao tỷ lệ nội địa hóa trong chuỗi sản xuất thiết bị công nghệ thông tin.</p>
      </body>
    </html>
    """
    rec = parse_viea_article(html, "https://veia.org.vn/chuoi-cung-ung-dien-tu-2026/")
    assert rec is not None
    assert rec["source"] == "viea"
    assert rec["issuing_body"] == "Hiệp hội Doanh nghiệp Điện tử Việt Nam (VEIA)"
    assert rec["doc_type"] == "ELECTRONICS_INDUSTRY"
    assert "bán dẫn" in rec["body"]


def test_huba_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết HUBA chuẩn 11 cột."""
    from src.crawlers.huba_crawler import parse_huba_article

    html = """
    <html>
      <body>
        <h1>Hiệp hội doanh nghiệp TP.HCM - Slogan</h1>
        <h2>Lịch công tác HUBA và tháo gỡ khó khăn tín dụng doanh nghiệp</h2>
        <div class="time">07/09/2026</div>
        <p>HUBA phối hợp với Ngân hàng Nhà nước chi nhánh TP.HCM tổ chức chương trình kết nối ngân hàng - doanh nghiệp.</p>
        <p>Gói tín dụng ưu đãi lãi suất thấp hỗ trợ các doanh nghiệp sản xuất xuất khẩu phục hồi đơn hàng.</p>
      </body>
    </html>
    """
    rec = parse_huba_article(html, "https://huba.vn/lich-cong-tac-2026/")
    assert rec is not None
    assert rec["source"] == "huba"
    assert rec["issuing_body"] == "Hiệp hội Doanh nghiệp TP.HCM (HUBA)"
    assert rec["doc_type"] == "ENTERPRISE_ALLIANCE"
    assert "Lịch công tác" in rec["headline"]


def test_tuoitre_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết Tuổi Trẻ chuẩn 11 cột."""
    from src.crawlers.tuoitre_crawler import parse_tuoitre_article

    html = """
    <html>
      <body>
        <h1>Vingroup đóng góp ngân sách gần 150.000 tỉ đồng năm 2026</h1>
        <p>Tập đoàn Vingroup tiếp tục dẫn đầu khối doanh nghiệp tư nhân trong việc đóng góp ngân sách nhà nước.</p>
        <p>Doanh thu từ lĩnh vực xe điện VinFast và bất động sản Vinhomes duy trì đà tăng trưởng ấn tượng.</p>
      </body>
    </html>
    """
    rec = parse_tuoitre_article(html, "https://tuoitre.vn/vingroup-dong-gop-ngan-sach-12345.htm", fallback_title="Test")
    assert rec is not None
    assert rec["source"] == "tuoitre"
    assert rec["issuing_body"] == "Báo Tuổi Trẻ (Tuoitre.vn)"
    assert "Vingroup" in rec["headline"]


def test_vpsaspice_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VPSA chuẩn 11 cột."""
    from src.crawlers.vpsaspice_crawler import parse_vpsa_article

    html = """
    <html>
      <body>
        <h1>Kim ngạch xuất khẩu hồ tiêu Việt Nam vượt mốc 1,2 tỷ USD năm 2026</h1>
        <time>03/09/2026</time>
        <p>Hiệp hội Hồ tiêu và Cây gia vị Việt Nam công bố kim ngạch xuất khẩu 8 tháng đầu năm đạt kết quả tích cực.</p>
        <p>Giá thu mua tiêu đen và tiêu trắng tại Tây Nguyên duy trì ở mức cao kỷ lục.</p>
      </body>
    </html>
    """
    rec = parse_vpsa_article(html, "https://vpsaspice.org/xuat-khau-ho-tieu-2026/")
    assert rec is not None
    assert rec["source"] == "vpsaspice"
    assert rec["issuing_body"] == "Hiệp hội Hồ tiêu và Cây gia vị Việt Nam (VPSA)"
    assert rec["doc_type"] == "SPICES_AGRI"


def test_hhbvt_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết HHBVT chuẩn 11 cột."""
    from src.crawlers.hhbvt_crawler import parse_hhbvt_article

    html = """
    <html>
      <body>
        <h1>Chính sách tự chủ viện phí và tháo gỡ vướng mắc bảo hiểm y tế</h1>
        <time>01/09/2026</time>
        <p>Hiệp hội Bệnh viện tư nhân kiến nghị Bộ Y tế hoàn thiện cơ chế thanh toán chi phí khám chữa bệnh BHYT.</p>
        <p>Khuyến khích thu hút nguồn lực xã hội hóa đầu tư trang thiết bị y tế hiện đại tại các cơ sở tư nhân.</p>
      </body>
    </html>
    """
    rec = parse_hhbvt_article(html, "https://hiephoibenhvientu.com.vn/chinh-sach-tu-chu-2026/")
    assert rec is not None
    assert rec["source"] == "hhbvt"
    assert rec["issuing_body"] == "Hiệp hội Bệnh viện tư nhân Việt Nam"
    assert rec["doc_type"] == "HEALTHCARE"


def test_avnuc_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết AVNUC chuẩn 11 cột."""
    from src.crawlers.avnuc_crawler import parse_avnuc_article

    html = """
    <html>
      <body>
        <h1>Định hướng phát triển năng lượng nguyên tử vì mục đích hòa bình năm 2026</h1>
        <time>02/09/2026</time>
        <p>Hội Năng lượng Nguyên tử Việt Nam thảo luận kế hoạch ứng dụng công nghệ bức xạ trong y tế và công nghiệp.</p>
        <p>Đồng thời nghiên cứu lộ trình phát triển các nguồn năng lượng sạch bền vững theo Quy hoạch Điện VIII.</p>
      </body>
    </html>
    """
    rec = parse_avnuc_article(html, "https://avnuc.vn/dinh-huong-nang-luong-2026/")
    assert rec is not None
    assert rec["source"] == "avnuc"
    assert rec["issuing_body"] == "Hội Năng lượng Nguyên tử / Sạch Việt Nam (AVNUC)"
    assert rec["doc_type"] == "CLEAN_ENERGY"


def test_vinasme_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VINASME chuẩn 11 cột."""
    from src.crawlers.vinasme_crawler import parse_vinasme_article

    html = """
    <html>
      <body>
        <h1>Chính sách tín dụng ưu đãi lãi suất cho doanh nghiệp vừa và nhỏ</h1>
        <time>06/09/2026</time>
        <p>Hiệp hội Doanh nghiệp Nhỏ và Vừa Việt Nam đề xuất nới lỏng điều kiện thế chấp tài sản vay vốn ngân hàng.</p>
        <p>Quỹ bảo lãnh tín dụng cần được mở rộng quy mô để hỗ trợ doanh nghiệp tiếp cận nguồn vốn phục hồi kinh doanh.</p>
      </body>
    </html>
    """
    rec = parse_vinasme_article(html, "https://vinasme.vn/tin-tuc/chinh-sach-tin-dung-sme-2026.html")
    assert rec is not None
    assert rec["source"] == "vinasme"
    assert rec["issuing_body"] == "Hiệp hội Doanh nghiệp Nhỏ và Vừa Việt Nam (VINASME)"
    assert rec["doc_type"] == "SME_COMMERCE"


def test_vacod_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VACOD chuẩn 11 cột."""
    from src.crawlers.vacod_crawler import parse_vacod_article

    html = """
    <html>
      <body>
        <h1>Thúc đẩy kích cầu tiêu dùng nội địa và xúc tiến thương mại hàng Việt Nam</h1>
        <time>05/09/2026</time>
        <p>Hiệp hội Phát triển Hàng tiêu dùng Việt Nam tổ chức tuần lễ tôn vinh hàng tiêu dùng chất lượng cao.</p>
        <p>Các chuỗi bán lẻ hiện đại tăng cường liên kết tiêu thụ nông sản và sản phẩm OCOP từ các hợp tác xã.</p>
      </body>
    </html>
    """
    rec = parse_vacod_article(html, "https://vacod.vn/kich-cau-tieu-dung-2026.htm")
    assert rec is not None
    assert rec["source"] == "vacod"
    assert rec["issuing_body"] == "Hiệp hội Phát triển Hàng tiêu dùng Việt Nam (VACOD)"
    assert rec["doc_type"] == "CONSUMER_GOODS"


def test_vusta_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VUSTA chuẩn 11 cột."""
    from src.crawlers.vusta_crawler import parse_vusta_article

    html = """
    <html>
      <body>
        <h1>Tư vấn phản biện chính sách khoa học công nghệ và đổi mới sáng tạo</h1>
        <time>04/09/2026</time>
        <p>Liên hiệp các Hội Khoa học và Kỹ thuật Việt Nam đẩy mạnh hoạt động tư vấn phản biện dự thảo luật.</p>
        <p>Đóng góp ý kiến hoàn thiện khung pháp lý về chuyển đổi số và phát triển kinh tế tuần hoàn.</p>
      </body>
    </html>
    """
    rec = parse_vusta_article(html, "https://vusta.vn/tu-van-phan-bien-khcn-2026.html")
    assert rec is not None
    assert rec["source"] == "vusta"
    assert rec["issuing_body"] == "Liên hiệp các Hội Khoa học & Kỹ thuật Việt Nam (VUSTA)"
    assert rec["doc_type"] == "SCIENCE_TECHNOLOGY"


def test_via_crawler_parsing() -> None:
    """Kiểm tra bóc tách bài viết VIA chuẩn 11 cột."""
    from src.crawlers.via_crawler import parse_via_article

    html = """
    <html>
      <body>
        <h1>Hiệp hội Internet Việt Nam</h1>
        <p>Chính sách mới về chuyển đổi số và phát triển trung tâm dữ liệu AI tại Việt Nam.</p>
        <p>Các doanh nghiệp viễn thông và công nghệ thông tin mở rộng hạ tầng cáp quang biển quốc tế.</p>
      </body>
    </html>
    """
    rec = parse_via_article(html, "https://via.org.vn/chinh-sach-ai-2026", fallback_title="Quy định mới về an toàn dữ liệu và trung tâm tính toán AI")
    assert rec is not None
    assert rec["source"] == "via"
    assert rec["issuing_body"] == "Hiệp hội Internet Việt Nam (VIA)"
    assert rec["doc_type"] == "TELECOM_INTERNET"
    assert "an toàn dữ liệu" in rec["headline"]


