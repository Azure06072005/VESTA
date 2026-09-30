"""Unit tests for News Ingestion Policy & Ethical Crawling Guardrails (crawl_policy.py)."""

from __future__ import annotations

import datetime as dt
from src.crawlers.crawl_policy import (
    is_url_allowed,
    sanitize_published_date,
    validate_and_clean_article,
)


def test_forbidden_denylist_rejection():
    """Kiểm tra từ chối 100% các trang trong danh sách cấm vĩnh viễn (WAF / Paywall / 403)."""
    blocked_urls = [
        "https://www.sbv.gov.vn/webcenter/portal/vi/menu/trangchu/chitiet?dDocName=SBV123",
        "https://sbv.gov.vn/portal/tin-tuc",
        "https://thuvienphapluat.vn/van-ban/Tai-chinh-Nha-nuoc/Thong-tu-41-2016-TT-NHNN.aspx",
        "https://luatvietnam.vn/nghi-dinh-08-2023-nd-cp.html",
        "https://vnba.com.vn/tin-tuc-su-kien",
        "https://vinasme.com.vn/hoat-dong",
        "https://vfaea.org.vn/news/123",
        "https://vpsaspice.org.vn/ho-tieu",
        "https://huba.vn/tin-doanh-nghiep",
        "https://tuoitre.vn/kinh-te-viet-nam-tang-truong-20260928.htm",
        "https://baodautu.vn/giai-ngan-dau-tu-cong-2026.html",
        "https://tienphong.vn/kinh-te-2026.tpo",
        "https://nguoiquansat.vn/chung-khoan-2026.html",
        "https://tapchicongthuong.vn/nang-luong-2026.htm",
    ]
    for url in blocked_urls:
        allowed, reason = is_url_allowed(url)
        assert not allowed, f"Lỗi: {url} phải bị từ chối truy cập!"
        assert "CẤM VĨNH VIỄN" in reason


def test_allowed_compliant_sites():
    """Kiểm tra chấp thuận các trang tin tức hợp lệ, có sitemap và không chặn bot."""
    valid_urls = [
        "https://cafef.vn/thi-truong-chung-khoan-2026.chn",
        "https://tinnhanhchungkhoan.vn/vcb-tang-truong-tin-dung-post123.html",
        "https://baochinhphu.vn/chi-dao-dieu-hanh-kinh-te-10223.htm",
        "https://vietstock.vn/2026/09/thi-truong-tai-chinh.htm",
        "https://thoibaonganhang.vn/lai-suat-lien-ngan-hang-ha-nhiet.html",
        "https://vneconomy.vn/kinh-te-so-viet-nam.htm",
        "https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG?locations=VN",
        "https://vasep.com.vn/xuat-khau-thuy-san.html",
        "https://horea.org.vn/kien-nghi-chinh-sach-bds.htm",
    ]
    for url in valid_urls:
        allowed, reason = is_url_allowed(url)
        assert allowed, f"Lỗi: {url} là trang hợp lệ nhưng bị từ chối: {reason}"


def test_date_sanitizer_anomalies():
    """Kiểm tra bộ lọc làm sạch ngày tháng, loại trừ các năm dị thường (1204, 1896, 2027)."""
    fallback = dt.datetime(2026, 9, 28, 0, 0, 0)

    # 1. Năm quá khứ xa bất thường (1204, 1896, 1980)
    d_1204 = dt.datetime(1204, 4, 9, 0, 0, 0)
    assert sanitize_published_date(d_1204, fallback_dt=fallback) == fallback

    d_1896 = dt.datetime(1896, 1, 8, 0, 0, 0)
    assert sanitize_published_date(d_1896, fallback_dt=fallback) == fallback

    # 2. Năm tương lai xa bất thường (2027, 2030)
    d_2027 = dt.datetime(2027, 3, 1, 0, 0, 0)
    assert sanitize_published_date(d_2027, fallback_dt=fallback) == fallback

    # 3. Ngày hợp lệ (2020 - 2026)
    d_valid = dt.datetime(2024, 5, 15, 10, 30, 0)
    assert sanitize_published_date(d_valid, fallback_dt=fallback) == d_valid


def test_validate_and_clean_article():
    """Kiểm tra xử lý bài viết: từ chối site cấm và tự động fallback thân bài nếu thiếu."""
    # Bài viết từ site cấm -> Bị loại bỏ hoàn toàn
    rec_blocked = {
        "source_url": "https://sbv.gov.vn/tin-tuc",
        "headline": "Ngân hàng Nhà nước hạ lãi suất",
        "body": "Nội dung...",
    }
    assert validate_and_clean_article(rec_blocked) is None

    # Bài viết hợp lệ nhưng thiếu thân bài -> Fallback về summary/headline
    rec_valid_no_body = {
        "source": "baochinhphu",
        "source_url": "https://baochinhphu.vn/nghi-quyet-123.htm",
        "headline": "Chính phủ ban hành Nghị quyết phát triển kinh tế",
        "summary": "Tóm tắt về định hướng tăng trưởng GDP cả năm 2026 đạt trên 7%.",
        "body": "",
        "published_at": dt.datetime(2026, 9, 15, 8, 0, 0),
    }
    cleaned = validate_and_clean_article(rec_valid_no_body)
    assert cleaned is not None
    assert cleaned["body"] == "Tóm tắt về định hướng tăng trưởng GDP cả năm 2026 đạt trên 7%."
    assert cleaned["published_at"] == dt.datetime(2026, 9, 15, 8, 0, 0)
