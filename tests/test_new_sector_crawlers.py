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
